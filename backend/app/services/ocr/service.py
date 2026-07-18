"""OCR service — region-scoped text extraction with full metadata retention."""

from __future__ import annotations

from pathlib import Path

import structlog

from app.core.geometry import expand_bbox, iou
from app.models.document import BoundingBox, OCRBlockData, OCRLineData, OCRParagraphData, OCRWordData
from app.modules.layout.doclayout_service import LayoutElementType, LayoutRegion
from app.modules.ocr.paddle_service import (
    OCRPageResult,
    OCRParagraph,
    PaddleOCRService,
)
from app.modules.ocr.structure_service import PPStructureService, StructurePageResult
from app.modules.preprocessing.image_extractor import crop_region
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)

TEXT_TYPES = {
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


class OCRService:
    """OCR only on confirmed text regions; preserves words, lines, paragraphs."""

    def __init__(
        self,
        paddle: PaddleOCRService,
        structure: PPStructureService,
    ) -> None:
        self._paddle = paddle
        self._structure = structure

    @property
    def provider_name(self) -> str:
        if self._structure.is_available:
            return "pp_structure"
        if self._paddle.is_available:
            return "paddleocr"
        return "fallback"

    def extract_page(
        self,
        image_path: Path,
        page_number: int,
        width: float,
        height: float,
        text_regions: list[LayoutRegion] | None = None,
    ) -> StageResult[OCRPageResult]:
        return run_stage(
            "ocr",
            lambda: self._extract(image_path, page_number, width, height, text_regions),
            provider=self.provider_name,
        )

    def from_structure(self, result: StructurePageResult) -> OCRPageResult:
        return self._structure.to_ocr_result(result)

    def _extract(
        self,
        image_path: Path,
        page_number: int,
        width: float,
        height: float,
        text_regions: list[LayoutRegion] | None,
    ) -> OCRPageResult:
        if self._structure.is_available and not text_regions:
            structure = self._structure.analyze_page(image_path, page_number, width, height)
            if structure.paragraphs:
                return self._structure.to_ocr_result(structure)

        if text_regions:
            return self._extract_regions(image_path, page_number, width, height, text_regions)

        return self._paddle.extract_page(image_path, page_number)

    def _extract_regions(
        self,
        image_path: Path,
        page_number: int,
        width: float,
        height: float,
        text_regions: list[LayoutRegion],
    ) -> OCRPageResult:
        regions = [r for r in text_regions if r.element_type in TEXT_TYPES]
        if not regions:
            return self._paddle.extract_page(image_path, page_number)

        full_page = self._paddle.extract_page(image_path, page_number)
        assigned: dict[int, tuple[OCRParagraph, float]] = {}
        order = 0

        for region in sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0])):
            best_para: OCRParagraph | None = None
            best_score = 0.0
            for para in full_page.paragraphs:
                score = iou(para.bbox, region.bbox)
                if self._center_inside(para.bbox, region.bbox):
                    score = max(score, 0.35)
                if score >= 0.35 and score > best_score:
                    best_para = para
                    best_score = score

            if best_para is not None:
                pid = id(best_para)
                if pid not in assigned or best_score > assigned[pid][1]:
                    assigned[pid] = (best_para, best_score)
                continue

            expanded = expand_bbox(region.bbox, padding=4.0, page_width=width, page_height=height)
            cropped = crop_region(image_path, expanded)
            if not cropped:
                continue
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(cropped)
                tmp_path = Path(tmp.name)
            try:
                region_result = self._paddle.extract_page(tmp_path, page_number)
            finally:
                tmp_path.unlink(missing_ok=True)

            for para in region_result.paragraphs:
                ox, oy = expanded[0], expanded[1]
                adj_bbox = (para.bbox[0] + ox, para.bbox[1] + oy, para.bbox[2], para.bbox[3])
                para.bbox = adj_bbox
                para.reading_order = order
                assigned[id(para)] = (para, 1.0)
                order += 1

        paragraphs: list[OCRParagraph] = []
        seen_ids: set[int] = set()
        for para in sorted(assigned.values(), key=lambda item: (item[0].bbox[1], item[0].bbox[0])):
            p = para[0]
            if id(p) in seen_ids:
                continue
            seen_ids.add(id(p))
            p.reading_order = len(paragraphs)
            paragraphs.append(p)

        unmatched = [
            p
            for p in full_page.paragraphs
            if id(p) not in seen_ids
            and not any(iou(p.bbox, r.bbox) >= 0.35 for r in regions)
        ]
        for para in unmatched:
            para.reading_order = len(paragraphs)
            paragraphs.append(para)

        if not paragraphs:
            return full_page

        avg_conf = sum(p.confidence for p in paragraphs) / len(paragraphs)
        logger.info(
            "ocr_regions_complete",
            page=page_number,
            regions=len(regions),
            paragraphs=len(paragraphs),
            confidence=round(avg_conf, 3),
        )
        return OCRPageResult(
            page_number=page_number,
            width=width,
            height=height,
            paragraphs=paragraphs,
            language=full_page.language,
        )

    @staticmethod
    def _center_inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
        cx = inner[0] + inner[2] / 2
        cy = inner[1] + inner[3] / 2
        ox, oy, ow, oh = outer
        return ox <= cx <= ox + ow and oy <= cy <= oy + oh

    @staticmethod
    def to_dom_ocr_data(ocr: OCRPageResult, provider: str) -> OCRBlockData:
        paragraphs: list[OCRParagraphData] = []
        all_words: list[OCRWordData] = []
        all_lines: list[OCRLineData] = []

        for para in ocr.paragraphs:
            line_models: list[OCRLineData] = []
            for line in para.lines:
                word_models = [
                    OCRWordData(
                        text=w.text,
                        confidence=w.confidence,
                        bbox=BoundingBox(x=w.bbox[0], y=w.bbox[1], width=w.bbox[2], height=w.bbox[3]),
                    )
                    for w in line.words
                ]
                all_words.extend(word_models)
                line_model = OCRLineData(
                    text=line.text,
                    confidence=line.confidence,
                    bbox=BoundingBox(
                        x=line.bbox[0], y=line.bbox[1], width=line.bbox[2], height=line.bbox[3]
                    ),
                    words=word_models,
                )
                line_models.append(line_model)
                all_lines.append(line_model)

            if not line_models and para.text:
                word = OCRWordData(
                    text=para.text,
                    confidence=para.confidence,
                    bbox=BoundingBox(
                        x=para.bbox[0], y=para.bbox[1], width=para.bbox[2], height=para.bbox[3]
                    ),
                )
                line_models = [
                    OCRLineData(
                        text=para.text,
                        confidence=para.confidence,
                        bbox=word.bbox,
                        words=[word],
                    )
                ]
                all_words.append(word)
                all_lines.extend(line_models)

            paragraphs.append(
                OCRParagraphData(
                    text=para.text,
                    confidence=para.confidence,
                    bbox=BoundingBox(
                        x=para.bbox[0], y=para.bbox[1], width=para.bbox[2], height=para.bbox[3]
                    ),
                    lines=line_models,
                    reading_order=para.reading_order,
                )
            )

        return OCRBlockData(
            words=all_words,
            lines=all_lines,
            paragraphs=paragraphs,
            reading_order=0,
            provider=provider,
        )

    @staticmethod
    def paragraph_ocr_data(para: OCRParagraph, provider: str) -> OCRBlockData:
        result = OCRPageResult(
            page_number=1,
            width=1,
            height=1,
            paragraphs=[para],
        )
        return OCRService.to_dom_ocr_data(result, provider)
