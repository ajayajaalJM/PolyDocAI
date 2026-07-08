"""Style extraction service — presentation separate from content."""

from __future__ import annotations

from pathlib import Path

import structlog

from app.models.document import TextStyle
from app.modules.preprocessing.style_analyzer import infer_style, infer_style_from_image, style_from_pdf_span
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)


class StyleService:
    """Extract colours, fonts, alignment, spacing from regions and spans."""

    def extract_block_style(
        self,
        bbox: tuple[float, float, float, float],
        layout_type: str,
        page_width: float,
        *,
        image_path: Path | None = None,
        language: str | None = None,
        pdf_span: dict | None = None,
        vision_font_size: float | None = None,
    ) -> StageResult[TextStyle]:
        return run_stage(
            "style_extraction",
            lambda: self._extract(
                bbox,
                layout_type,
                page_width,
                image_path=image_path,
                language=language,
                pdf_span=pdf_span,
                vision_font_size=vision_font_size,
            ),
            provider="style_analyzer",
        )

    def _extract(
        self,
        bbox: tuple[float, float, float, float],
        layout_type: str,
        page_width: float,
        *,
        image_path: Path | None,
        language: str | None,
        pdf_span: dict | None,
        vision_font_size: float | None,
    ) -> TextStyle:
        if pdf_span:
            style = style_from_pdf_span(pdf_span, layout_type, page_width)
        elif image_path:
            style = infer_style_from_image(image_path, bbox, layout_type, page_width, language)
        else:
            style = infer_style(bbox, layout_type, page_width, language)

        if vision_font_size and not pdf_span:
            style.font_size = vision_font_size
        return style
