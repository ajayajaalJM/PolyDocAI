"""Layout detection service — regions before OCR."""

from __future__ import annotations

from pathlib import Path

import structlog

from app.modules.layout.doclayout_service import (
    DocLayoutService,
    LayoutElementType,
    LayoutPageResult,
    LayoutRegion,
)
from app.modules.ocr.structure_service import PPStructureService, StructurePageResult
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)

TEXT_REGION_TYPES = {
    LayoutElementType.TITLE,
    LayoutElementType.HEADING,
    LayoutElementType.PARAGRAPH,
    LayoutElementType.LIST,
    LayoutElementType.CAPTION,
    LayoutElementType.QUOTE,
    LayoutElementType.HEADER,
    LayoutElementType.FOOTER,
    LayoutElementType.SIDEBAR,
    LayoutElementType.TABLE,
}


class LayoutService:
    """Detect logical document regions before OCR runs."""

    def __init__(
        self,
        doclayout: DocLayoutService,
        structure: PPStructureService,
    ) -> None:
        self._doclayout = doclayout
        self._structure = structure

    @property
    def provider_name(self) -> str:
        if self._structure.is_available:
            return "pp_structure"
        if self._doclayout.is_available:
            return "doclayout_yolo"
        return "fallback"

    def detect_page(
        self,
        image_path: Path,
        page_number: int,
        width: float,
        height: float,
    ) -> StageResult[LayoutPageResult]:
        return run_stage(
            "layout_detection",
            lambda: self._detect(image_path, page_number, width, height),
            provider=self.provider_name,
        )

    def _detect(
        self,
        image_path: Path,
        page_number: int,
        width: float,
        height: float,
    ) -> LayoutPageResult:
        if self._structure.is_available:
            structure = self._structure.analyze_page(image_path, page_number, width, height)
            if structure.layout_regions:
                return self._structure.to_layout_result(structure)
            logger.warning("pp_structure_empty_fallback", page=page_number)

        result = self._doclayout.detect_page(image_path, page_number, width, height)
        if not result.regions:
            result.regions = [
                LayoutRegion(
                    element_type=LayoutElementType.PARAGRAPH,
                    confidence=0.5,
                    bbox=(0.0, 0.0, width, height),
                )
            ]
        for i, region in enumerate(
            sorted(result.regions, key=lambda r: (r.bbox[1], r.bbox[0]))
        ):
            region.reading_order = i
        return result

    def text_regions(self, layout: LayoutPageResult) -> list[LayoutRegion]:
        return [r for r in layout.regions if r.element_type in TEXT_REGION_TYPES]

    def get_structure_tables(self, image_path: Path, page_number: int) -> StructurePageResult | None:
        if not self._structure.is_available:
            return None
        return self._structure.analyze_page(image_path, page_number)
