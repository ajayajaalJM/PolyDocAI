from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_container_from_request
from app.core.container import Container
from app.models.document import (
    BlockUpdateRequest,
    ConnectionTestResponse,
    Document,
    DocumentSummary,
    ExportRequest,
    ExportResponse,
    ProcessRequest,
    ReconstructRequest,
    SettingsResponse,
    TranslateRequest,
    TranslatorSettings,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    container: Container = Depends(get_container_from_request),
) -> UploadResponse:
    content = await file.read()
    try:
        document = await container.upload.upload(
            filename=file.filename or "document.pdf",
            content=content,
            content_type=file.content_type,
        )
        thumb = await container.upload.generate_placeholder_thumbnail(document.id)
        from app.models.document import Page

        if document.pages:
            document.pages[0].thumbnail_path = thumb
        else:
            document.pages = [
                Page(page_number=1, width=612, height=792, thumbnail_path=thumb)
            ]
            document.page_count = 1
        await container.document_repository.save(document)
        return UploadResponse(document=document, message="Upload complete")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    container: Container = Depends(get_container_from_request),
) -> list[DocumentSummary]:
    docs = await container.document_repository.list_all()
    return [
        DocumentSummary(
            id=d.id,
            name=d.name,
            status=d.status,
            page_count=d.page_count,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=Document)
async def get_document(
    document_id: str,
    container: Container = Depends(get_container_from_request),
) -> Document:
    try:
        return await container.document_repository.get_or_raise(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    container: Container = Depends(get_container_from_request),
) -> dict[str, bool]:
    deleted = await container.document_repository.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@router.post("/{document_id}/process", response_model=Document)
async def process_document(
    document_id: str,
    body: ProcessRequest,
    container: Container = Depends(get_container_from_request),
) -> Document:
    try:
        return await container.pipeline.process(
            document_id,
            source_lang=body.source_language,
            target_lang=body.target_language,
            skip_translation=body.skip_translation,
            skip_reconstruction=body.skip_reconstruction,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        from app.providers.translators.errors import TranslationError

        if isinstance(exc, TranslationError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise


@router.post("/{document_id}/translate", response_model=Document)
async def translate_document(
    document_id: str,
    body: TranslateRequest,
    container: Container = Depends(get_container_from_request),
) -> Document:
    try:
        return await container.pipeline.translate_only(
            document_id,
            source_lang=body.source_language,
            target_lang=body.target_language,
            reconstruct=body.reconstruct,
            skip_edited=body.skip_edited,
            block_ids=body.block_ids,
            page_numbers=body.page_numbers,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        from app.providers.translators.errors import TranslationError

        if isinstance(exc, TranslationError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise


@router.patch("/{document_id}/blocks/{block_id}", response_model=Document)
async def update_block(
    document_id: str,
    block_id: str,
    body: BlockUpdateRequest,
    container: Container = Depends(get_container_from_request),
) -> Document:
    try:
        return await container.pipeline.update_block(
            document_id,
            block_id,
            translated_text=body.translated_text,
            translated_rows=body.translated_rows,
            reconstruct=True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/reconstruct", response_model=Document)
async def reconstruct_document(
    document_id: str,
    body: ReconstructRequest,
    container: Container = Depends(get_container_from_request),
) -> Document:
    try:
        return await container.pipeline.reconstruct_only(
            document_id,
            page_numbers=body.page_numbers,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/process/stream")
async def process_document_stream(
    document_id: str,
    source_language: str | None = None,
    target_language: str | None = None,
    skip_translation: bool = False,
    container: Container = Depends(get_container_from_request),
) -> EventSourceResponse:
    async def event_generator():
        try:
            async for progress in container.pipeline.stream_progress(
                document_id,
                source_lang=source_language,
                target_lang=target_language,
                skip_translation=skip_translation,
            ):
                yield {"event": "progress", "data": progress.model_dump_json()}
            doc = await container.document_repository.get_or_raise(document_id)
            yield {"event": "complete", "data": doc.model_dump_json()}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


@router.post("/{document_id}/export", response_model=ExportResponse)
async def export_document(
    document_id: str,
    body: ExportRequest,
    container: Container = Depends(get_container_from_request),
) -> ExportResponse:
    try:
        document = await container.document_repository.get_or_raise(document_id)
        content, filename = await container.export.export(
            document,
            body.format,
            use_translated=body.use_translated,
            semantic=body.semantic,
        )
        path = await container.storage.save_output(document_id, filename, content)
        rel = str(path.relative_to(container.storage.root))
        return ExportResponse(
            document_id=document_id,
            format=body.format,
            output_path=rel,
            download_url=f"/api/v1/documents/{document_id}/download/{body.format}",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{document_id}/download/{fmt}")
async def download_export(
    document_id: str,
    fmt: str,
    container: Container = Depends(get_container_from_request),
) -> FileResponse:
    out_dir = container.storage.outputs / document_id
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    ext_map = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}
    suffix = ext_map.get(fmt)
    if not suffix:
        raise HTTPException(status_code=400, detail="Invalid format")
    files = list(out_dir.glob(f"*{suffix}"))
    if not files:
        raise HTTPException(status_code=404, detail="Export file not found")
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
    }
    return FileResponse(files[0], media_type=media[fmt], filename=files[0].name)


@router.get("/{document_id}/raster/{page_number}")
async def get_page_raster(
    document_id: str,
    page_number: int,
    variant: str = "original",
    container: Container = Depends(get_container_from_request),
) -> FileResponse:
    import asyncio

    if variant == "translated":
        path = (
            container.storage.uploads
            / document_id
            / "translated"
            / f"page_{page_number:04d}.png"
        )
    elif variant == "stripped":
        path = (
            container.storage.uploads
            / document_id
            / "stripped"
            / f"page_{page_number:04d}.png"
        )
        if not path.exists():
            try:
                document = await container.document_repository.get_or_raise(document_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            page = next((p for p in document.pages if p.page_number == page_number), None)
            if page is None:
                raise HTTPException(status_code=404, detail="Page not found")
            if not page.raster_path:
                raise HTTPException(
                    status_code=404,
                    detail="Page raster not ready — wait for OCR to finish",
                )
            storage_root = Path(container.storage.root)
            upload_path = await container.storage.get_upload_path(document_id)
            try:
                png_bytes = await asyncio.to_thread(
                    container.reconstruction.render_stripped_page_png,
                    page,
                    storage_root=storage_root,
                    document_id=document_id,
                    upload_path=upload_path,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            path = await container.storage.save_stripped_raster(
                document_id, page_number, png_bytes
            )
    else:
        path = container.storage.uploads / document_id / "pages" / f"page_{page_number:04d}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page raster not found")
    return FileResponse(path, media_type="image/png")


@router.get("/{document_id}/assets/{asset_name}")
async def get_asset(
    document_id: str,
    asset_name: str,
    container: Container = Depends(get_container_from_request),
) -> FileResponse:
    path = container.storage.uploads / document_id / "assets" / asset_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path, media_type="image/png")


@router.get("/{document_id}/thumbnail/{page_number}")
async def get_thumbnail(
    document_id: str,
    page_number: int,
    container: Container = Depends(get_container_from_request),
) -> FileResponse:
    path = container.storage.uploads / document_id / "thumbnails" / f"page_{page_number:04d}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path, media_type="image/png")
