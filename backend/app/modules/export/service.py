from __future__ import annotations

from pathlib import Path

import structlog

from app.models.document import Document, PageStatus
from app.services.rendering.service import RenderingService
from app.providers.rendering.base import RenderOptions

logger = structlog.get_logger(__name__)


class ExportService:
    def __init__(self, rendering: RenderingService, storage_root: Path) -> None:
        self._rendering = rendering
        self._storage_root = storage_root

    async def export(
        self,
        document: Document,
        fmt: str,
        use_translated: bool = True,
        semantic: bool = True,
    ) -> tuple[bytes, str]:
        if fmt == "pdf" or semantic:
            result = self._rendering.render(
                document,
                fmt,
                RenderOptions(use_translated=use_translated, storage_root=self._storage_root),
            )
            if not result.success or result.data is None:
                raise RuntimeError(f"Export failed: {result.errors}")
            content = result.data.content
            filename = result.data.filename
        else:
            content, filename = self._export_raster_fallback(document, fmt, use_translated)

        for page in document.pages:
            page.export_status = PageStatus.COMPLETE

        logger.info("export_complete", document_id=document.id, format=fmt, semantic=semantic)
        return content, filename

    def _export_raster_fallback(
        self, document: Document, fmt: str, use_translated: bool
    ) -> tuple[bytes, str]:
        """Legacy raster-embed export when semantic=False."""
        from app.modules.export.legacy import export_raster_docx, export_raster_html

        if fmt == "docx":
            return export_raster_docx(document, self._storage_root, use_translated)
        if fmt == "html":
            return export_raster_html(document, self._storage_root, use_translated)
        raise ValueError(f"Unsupported export format: {fmt}")
