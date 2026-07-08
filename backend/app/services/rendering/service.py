"""Rendering service — plugin-based output from DOM."""

from __future__ import annotations

from pathlib import Path

import structlog

from app.models.document import Document
from app.modules.reconstruction.engine import ReconstructionEngine
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult
from app.providers.rendering.base import RenderOptions, RenderResult, RendererProvider

logger = structlog.get_logger(__name__)


class RasterRenderer:
    format = "png"

    def __init__(self, reconstruction: ReconstructionEngine) -> None:
        self._reconstruction = reconstruction

    def render_page_png(
        self,
        document: Document,
        page_number: int,
        *,
        use_translated: bool,
        storage_root: Path,
        dpi: int,
    ) -> bytes:
        page = next(p for p in document.pages if p.page_number == page_number)
        upload_path = storage_root / document.file_path if document.file_path else None
        return self._reconstruction.render_page_png(
            page,
            use_translated=use_translated,
            storage_root=storage_root,
            document_id=document.id,
            upload_path=upload_path,
            dpi=dpi,
            source_type=document.metadata.source_type,
            target_language=document.target_language,
        )


class PDFRenderer:
    format = "pdf"

    def __init__(self, reconstruction: ReconstructionEngine) -> None:
        self._reconstruction = reconstruction

    def render(self, document: Document, options: RenderOptions) -> RenderResult:
        root = options.storage_root or Path(".")
        content = self._reconstruction.render_document_pdf(
            document,
            use_translated=options.use_translated,
            storage_root=root,
        )
        suffix = "translated" if options.use_translated else "original"
        return RenderResult(
            content=content,
            mime_type="application/pdf",
            filename=f"{Path(document.name).stem}_{suffix}.pdf",
        )


class RenderingService:
    """Registry of renderer plugins consuming the same DOM."""

    def __init__(self, reconstruction: ReconstructionEngine) -> None:
        self._reconstruction = reconstruction
        self._raster = RasterRenderer(reconstruction)
        self._renderers: dict[str, RendererProvider] = {
            "pdf": PDFRenderer(reconstruction),
        }

    def get_renderer(self, fmt: str) -> RendererProvider:
        renderer = self._renderers.get(fmt)
        if renderer is None:
            raise ValueError(f"No renderer for format: {fmt}")
        return renderer

    def render(
        self,
        document: Document,
        fmt: str,
        options: RenderOptions | None = None,
    ) -> StageResult[RenderResult]:
        opts = options or RenderOptions()
        renderer = self.get_renderer(fmt)
        return run_stage(
            "rendering",
            lambda: renderer.render(document, opts),
            provider=fmt,
        )

    @property
    def raster(self) -> RasterRenderer:
        return self._raster
