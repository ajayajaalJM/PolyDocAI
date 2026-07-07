from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from app.models.document import (
    Document,
    DocumentStatus,
    ImageBlock,
    PageStatus,
    PipelineProgress,
    TableBlock,
    TextBlock,
)
from app.modules.layout.doclayout_service import DocLayoutService
from app.modules.ocr.paddle_service import PaddleOCRService
from app.modules.ocr.structure_service import PPStructureService
from app.modules.pipeline.model_builder import DocumentModelBuilder
from app.modules.pipeline.quality import compute_quality_scores
from app.modules.preprocessing.image_extractor import crop_region
from app.modules.preprocessing.pdf_processor import ImageProcessor, PDFProcessor
from app.modules.reconstruction.engine import ReconstructionEngine
from app.modules.translation.service import TranslationService
from app.providers.repository import DocumentRepository
from app.providers.storage.base import StorageProvider
from app.providers.translators.errors import TranslationError

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[PipelineProgress], None]


class PipelineOrchestrator:
    STAGES = [
        ("preparing", "Preparing document..."),
        ("analyzing_structure", "Analyzing document structure..."),
        ("building_model", "Generating document model..."),
        ("matching_fonts", "Analyzing typography..."),
        ("translating", "Translating..."),
        ("review", "Ready for review..."),
        ("reconstructing", "Building translated pages..."),
        ("complete", "Processing complete."),
    ]

    def __init__(
        self,
        storage: StorageProvider,
        repository: DocumentRepository,
        ocr: PaddleOCRService,
        layout: DocLayoutService,
        structure: PPStructureService,
        translation: TranslationService,
        reconstruction: ReconstructionEngine,
        model_builder: DocumentModelBuilder | None = None,
        ocr_dpi: int = 300,
    ) -> None:
        self._storage = storage
        self._repository = repository
        self._ocr = ocr
        self._layout = layout
        self._structure = structure
        self._translation = translation
        self._reconstruction = reconstruction
        self._model_builder = model_builder or DocumentModelBuilder()
        self._ocr_dpi = ocr_dpi
        self._jobs: dict[str, asyncio.Task] = {}

    async def translate_only(
        self,
        document_id: str,
        source_lang: str | None = None,
        target_lang: str | None = None,
        *,
        reconstruct: bool = True,
        skip_edited: bool = True,
        block_ids: list[str] | None = None,
        page_numbers: list[int] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Document:
        start = time.perf_counter()
        document = await self._repository.get_or_raise(document_id)
        document.status = DocumentStatus.PROCESSING
        await self._repository.save(document)

        def emit(stage: str, message: str, progress: float) -> None:
            if on_progress:
                on_progress(
                    PipelineProgress(
                        document_id=document_id,
                        stage=stage,
                        message=message,
                        progress=progress,
                        elapsed_ms=(time.perf_counter() - start) * 1000,
                    )
                )

        emit("translating", "Translating existing text blocks...", 0.2)
        try:
            document = await self._translation.translate_document(
                document,
                source_lang=source_lang,
                target_lang=target_lang,
                skip_edited=skip_edited,
                block_ids=block_ids,
                page_numbers=page_numbers,
            )
        except TranslationError:
            await self._repository.save(document)
            raise

        document.metadata.processing_timings["translation_ms"] = (
            time.perf_counter() - start
        ) * 1000

        if reconstruct:
            pages_to_rebuild = page_numbers
            emit("reconstructing", "Building translated page images...", 0.7)
            await self._reconstruct_pages(document, page_numbers=pages_to_rebuild)
            document.status = DocumentStatus.RECONSTRUCTED
        else:
            document.status = DocumentStatus.TRANSLATED

        document.metadata.quality_scores = compute_quality_scores(
            document, storage_root=Path(self._storage.root)
        )
        document.metadata.processing_timings["total_ms"] = (time.perf_counter() - start) * 1000
        await self._repository.save(document)
        emit("review", "Ready for review.", 0.95)
        emit("complete", "Translation complete.", 1.0)
        return document

    async def reconstruct_only(
        self,
        document_id: str,
        page_numbers: list[int] | None = None,
    ) -> Document:
        document = await self._repository.get_or_raise(document_id)
        await self._reconstruct_pages(document, page_numbers=page_numbers)
        document.status = DocumentStatus.RECONSTRUCTED
        document.metadata.quality_scores = compute_quality_scores(
            document, storage_root=Path(self._storage.root)
        )
        document.touch()
        await self._repository.save(document)
        return document

    async def update_block(
        self,
        document_id: str,
        block_id: str,
        *,
        translated_text: str | None = None,
        translated_rows: list[list[str]] | None = None,
        reconstruct: bool = True,
    ) -> Document:
        document = await self._repository.get_or_raise(document_id)
        target_page = None
        for page in document.pages:
            for block in page.blocks:
                if block.id != block_id:
                    continue
                now = datetime.now(UTC)
                if isinstance(block, TextBlock) and translated_text is not None:
                    block.translated_text = translated_text
                    block.is_edited = True
                    block.edited_at = now
                    target_page = page.page_number
                elif isinstance(block, TableBlock) and translated_rows is not None:
                    block.translated_rows = translated_rows
                    block.is_edited = True
                    block.edited_at = now
                    target_page = page.page_number
                break

        if target_page is None:
            raise KeyError(f"Block {block_id} not found")

        document.touch()
        await self._repository.save(document)

        if reconstruct:
            await self._reconstruct_pages(document, page_numbers=[target_page])
            document.status = DocumentStatus.RECONSTRUCTED
            document.metadata.quality_scores = compute_quality_scores(
            document, storage_root=Path(self._storage.root)
        )
            await self._repository.save(document)

        return document

    async def _reconstruct_pages(
        self,
        document: Document,
        page_numbers: list[int] | None = None,
    ) -> None:
        storage_root = Path(self._storage.root)
        doc_dir = storage_root / "uploads" / document.id
        pages = document.pages
        if page_numbers:
            pages = [p for p in pages if p.page_number in page_numbers]

        for page in pages:
            for sub in ("translated", "stripped", "backgrounds"):
                path = doc_dir / sub / f"page_{page.page_number:04d}.png"
                path.unlink(missing_ok=True)

        upload_path = await self._storage.get_upload_path(document.id)

        for page in pages:
            page.translated_raster_path = None
            stripped_bytes = await asyncio.to_thread(
                self._reconstruction.render_stripped_page_png,
                page,
                storage_root=storage_root,
                document_id=document.id,
                upload_path=upload_path,
                dpi=self._ocr_dpi,
            )
            await self._storage.save_stripped_raster(
                document.id, page.page_number, stripped_bytes
            )

            png_bytes = await asyncio.to_thread(
                self._reconstruction.render_page_png,
                page,
                use_translated=True,
                storage_root=storage_root,
                document_id=document.id,
                upload_path=upload_path,
                dpi=self._ocr_dpi,
                source_type=document.metadata.source_type,
                target_language=document.target_language,
            )
            path = await self._storage.save_translated_raster(
                document.id, page.page_number, png_bytes
            )
            page.translated_raster_path = str(path.relative_to(storage_root))
            logger.info(
                "page_reconstructed",
                document_id=document.id,
                page=page.page_number,
                blocks=len(page.blocks),
            )

    async def process(
        self,
        document_id: str,
        source_lang: str | None = None,
        target_lang: str | None = None,
        skip_translation: bool = False,
        skip_reconstruction: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> Document:
        start = time.perf_counter()
        document = await self._repository.get_or_raise(document_id)
        document.status = DocumentStatus.PROCESSING
        document.metadata.warnings = []
        await self._repository.save(document)

        def emit(stage: str, message: str, progress: float, page: int | None = None) -> None:
            if on_progress:
                on_progress(
                    PipelineProgress(
                        document_id=document_id,
                        stage=stage,
                        message=message,
                        progress=progress,
                        page_number=page,
                        elapsed_ms=(time.perf_counter() - start) * 1000,
                    )
                )

        emit("preparing", "Preparing document...", 0.05)
        upload_path = await self._storage.get_upload_path(document_id)
        if upload_path is None:
            raise FileNotFoundError(f"No upload found for document {document_id}")

        pages_dir = Path(self._storage.root) / "uploads" / document_id / "pages"
        is_pdf = PDFProcessor.is_pdf(upload_path)
        if is_pdf:
            image_paths = PDFProcessor.rasterize(upload_path, pages_dir, dpi=self._ocr_dpi)
            if PDFProcessor.is_born_digital(upload_path):
                document.metadata.source_type = "vector_pdf"
                fonts_dir = Path(self._storage.root) / "fonts" / document_id
                PDFProcessor.extract_embedded_fonts(upload_path, fonts_dir)
            else:
                document.metadata.source_type = "scanned"
        else:
            image_paths = ImageProcessor.prepare_image(upload_path, pages_dir)
            document.metadata.source_type = "image"

        total = len(image_paths)
        built_pages = []
        use_structure = self._structure.is_available

        async def save_asset_cb(doc_id: str, name: str, content: bytes) -> str | None:
            path = await self._storage.save_asset(doc_id, name, content)
            return str(path.relative_to(self._storage.root))

        for idx, image_path in enumerate(image_paths):
            page_num = idx + 1
            progress_base = 0.1 + (idx / total) * 0.55

            structure_result = None
            ocr_result = None
            layout_result = None

            if use_structure:
                emit(
                    "analyzing_structure",
                    f"Analyzing structure on page {page_num}...",
                    progress_base,
                    page_num,
                )
                structure_result = await asyncio.to_thread(
                    self._structure.analyze_page, image_path, page_num
                )
                ocr_result = self._structure.to_ocr_result(structure_result)
                layout_result = self._structure.to_layout_result(structure_result)
            else:
                emit(
                    "analyzing_structure",
                    f"Detecting text on page {page_num}...",
                    progress_base,
                    page_num,
                )
                ocr_result = await asyncio.to_thread(self._ocr.extract_page, image_path, page_num)
                layout_result = await asyncio.to_thread(
                    self._layout.detect_page,
                    image_path,
                    page_num,
                    ocr_result.width,
                    ocr_result.height,
                )

            thumb_bytes = await asyncio.to_thread(PaddleOCRService.render_thumbnail, image_path)
            thumb_path = await self._storage.save_thumbnail(document_id, page_num, thumb_bytes)
            rel_thumb = str(thumb_path.relative_to(self._storage.root))
            rel_raster = str(image_path.relative_to(self._storage.root))

            pdf_spans = None
            if is_pdf:
                pdf_spans = await asyncio.to_thread(
                    PDFProcessor.extract_text_spans, upload_path, page_num, self._ocr_dpi
                )

            emit(
                "matching_fonts",
                f"Analyzing typography on page {page_num}...",
                progress_base + 0.08,
                page_num,
            )

            structure_tables = structure_result.tables if structure_result else None
            page = self._model_builder.merge_page(
                ocr_result,
                layout_result,
                thumbnail_path=rel_thumb,
                raster_path=rel_raster,
                pdf_spans=pdf_spans,
                structure_tables=structure_tables,
                image_path=image_path,
            )

            for block in page.blocks:
                if isinstance(block, ImageBlock) and not block.asset_path:
                    bbox = (block.bbox.x, block.bbox.y, block.bbox.width, block.bbox.height)
                    cropped = crop_region(image_path, bbox)
                    if cropped:
                        asset_name = f"page{page_num}_fig_{uuid4().hex[:8]}.png"
                        saved = await save_asset_cb(document_id, asset_name, cropped)
                        if saved:
                            block.asset_path = saved

            built_pages.append(page)

        emit("building_model", "Generating document model...", 0.72)
        document = self._model_builder.apply_to_document(document, built_pages)
        for page in document.pages:
            page.ocr_status = PageStatus.COMPLETE
        document.status = DocumentStatus.LAYOUT_COMPLETE
        document.metadata.processing_timings["ocr_layout_ms"] = (time.perf_counter() - start) * 1000
        await self._repository.save(document)

        if not skip_translation:
            emit("translating", "Translating...", 0.82)
            t_start = time.perf_counter()
            try:
                document = await self._translation.translate_document(
                    document, source_lang=source_lang, target_lang=target_lang
                )
            except TranslationError as exc:
                await self._repository.save(document)
                emit("translating", f"Translation failed: {exc}", 0.9)
                raise
            document.metadata.processing_timings["translation_ms"] = (
                time.perf_counter() - t_start
            ) * 1000
            await self._repository.save(document)
        else:
            for page in document.pages:
                page.translation_status = PageStatus.COMPLETE

        if not skip_reconstruction and not skip_translation:
            emit("reconstructing", "Building translated page images...", 0.92)
            await self._reconstruct_pages(document)
            document.status = DocumentStatus.RECONSTRUCTED
        elif not skip_translation:
            document.status = DocumentStatus.TRANSLATED

        document.metadata.quality_scores = compute_quality_scores(
            document, storage_root=Path(self._storage.root)
        )
        document.metadata.processing_timings["total_ms"] = (time.perf_counter() - start) * 1000
        await self._repository.save(document)

        emit("review", "Ready for review.", 0.98)
        emit("complete", "Processing complete.", 1.0)
        logger.info("pipeline_complete", document_id=document_id, pages=total)
        return document

    async def stream_progress(
        self, document_id: str, **kwargs
    ) -> AsyncIterator[PipelineProgress]:
        queue: asyncio.Queue[PipelineProgress | None] = asyncio.Queue()
        errors: list[BaseException] = []

        def callback(progress: PipelineProgress) -> None:
            queue.put_nowait(progress)

        async def run() -> None:
            try:
                await self.process(document_id, on_progress=callback, **kwargs)
            except Exception as exc:
                errors.append(exc)
                logger.exception("pipeline_stream_failed", document_id=document_id)
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        self._jobs[document_id] = task
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
            if errors:
                raise errors[0]
        finally:
            self._jobs.pop(document_id, None)
