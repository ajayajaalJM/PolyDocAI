"""PP-StructureV3 unified document analysis — layout, OCR, tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion
from app.modules.ocr.paddle_service import OCRPageResult, OCRParagraph

logger = structlog.get_logger(__name__)

LAYOUT_TYPE_MAP: dict[str, LayoutElementType] = {
    "title": LayoutElementType.TITLE,
    "text": LayoutElementType.PARAGRAPH,
    "paragraph": LayoutElementType.PARAGRAPH,
    "figure": LayoutElementType.FIGURE,
    "figure_caption": LayoutElementType.CAPTION,
    "table": LayoutElementType.TABLE,
    "table_caption": LayoutElementType.CAPTION,
    "header": LayoutElementType.HEADER,
    "footer": LayoutElementType.FOOTER,
    "reference": LayoutElementType.PARAGRAPH,
    "equation": LayoutElementType.PARAGRAPH,
    "formula": LayoutElementType.PARAGRAPH,
    "list": LayoutElementType.LIST,
    "image": LayoutElementType.IMAGE,
}


@dataclass
class TableCellResult:
    row: int
    col: int
    bbox: tuple[float, float, float, float]
    text: str
    confidence: float = 1.0


@dataclass
class StructureTableResult:
    bbox: tuple[float, float, float, float]
    rows: list[list[str]]
    cells: list[TableCellResult] = field(default_factory=list)
    col_widths: list[float] = field(default_factory=list)
    row_heights: list[float] = field(default_factory=list)


@dataclass
class StructurePageResult:
    page_number: int
    width: float
    height: float
    paragraphs: list[OCRParagraph]
    layout_regions: list[LayoutRegion]
    tables: list[StructureTableResult]
    language: str | None = None


class PPStructureService:
    """Unified layout + OCR via PaddleOCR PP-StructureV3."""

    def __init__(self, lang: str = "en", use_gpu: bool = False) -> None:
        self._lang = lang
        self._use_gpu = use_gpu
        self._engine: Any = None
        self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def initialize(self) -> None:
        try:
            from paddleocr import PPStructureV3

            device = "gpu:0" if self._use_gpu else "cpu"
            self._engine = PPStructureV3(lang=self._lang, device=device)
            self._available = True
            logger.info("pp_structure_initialized", device=device)
        except Exception as exc:
            logger.warning("pp_structure_unavailable", error=str(exc))
            self._available = False

    def analyze_page(
        self,
        image_path: Path,
        page_number: int,
        width: float | None = None,
        height: float | None = None,
    ) -> StructurePageResult:
        if not self._available or self._engine is None:
            return StructurePageResult(
                page_number=page_number,
                width=width or 612,
                height=height or 792,
                paragraphs=[],
                layout_regions=[],
                tables=[],
            )

        from PIL import Image

        with Image.open(image_path) as img:
            w, h = img.size
        page_w = width or float(w)
        page_h = height or float(h)

        try:
            raw = self._engine.predict(str(image_path))
        except Exception as exc:
            logger.warning("pp_structure_predict_failed", error=str(exc))
            return StructurePageResult(
                page_number=page_number,
                width=page_w,
                height=page_h,
                paragraphs=[],
                layout_regions=[],
                tables=[],
            )

        paragraphs: list[OCRParagraph] = []
        layout_regions: list[LayoutRegion] = []
        tables: list[StructureTableResult] = []
        order = 0

        for page_data in raw if isinstance(raw, list) else [raw]:
            blocks = self._extract_blocks(page_data)
            for block in blocks:
                label = str(block.get("label", block.get("type", "text"))).lower()
                bbox = self._normalize_bbox(block.get("bbox") or block.get("box"), page_w, page_h)
                if bbox is None:
                    continue

                element_type = LAYOUT_TYPE_MAP.get(label, LayoutElementType.UNKNOWN)
                layout_regions.append(
                    LayoutRegion(
                        element_type=element_type,
                        bbox=bbox,
                        confidence=float(block.get("score", block.get("confidence", 0.9))),
                    )
                )

                if label == "table":
                    table = self._parse_table(block, bbox)
                    if table:
                        tables.append(table)
                    continue

                text = self._block_text(block)
                if element_type in {
                    LayoutElementType.FIGURE,
                    LayoutElementType.IMAGE,
                    LayoutElementType.LOGO,
                } and not text.strip():
                    continue

                if not text.strip():
                    continue

                from app.modules.ocr.geometry import proportional_word_boxes
                from app.modules.ocr.paddle_service import OCRLine, OCRWord

                confidence = float(block.get("score", block.get("confidence", 0.85)))
                words = [
                    OCRWord(text=w, confidence=confidence, bbox=wb)
                    for w, wb in proportional_word_boxes(text.strip(), bbox)
                ]
                line = OCRLine(
                    text=text.strip(),
                    confidence=confidence,
                    bbox=bbox,
                    words=words,
                )
                paragraphs.append(
                    OCRParagraph(
                        text=text.strip(),
                        bbox=bbox,
                        confidence=confidence,
                        lines=[line],
                        reading_order=order,
                    )
                )
                order += 1

        layout_regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
        paragraphs.sort(key=lambda p: p.reading_order)

        return StructurePageResult(
            page_number=page_number,
            width=page_w,
            height=page_h,
            paragraphs=paragraphs,
            layout_regions=layout_regions,
            tables=tables,
        )

    def to_ocr_result(self, result: StructurePageResult) -> OCRPageResult:
        return OCRPageResult(
            page_number=result.page_number,
            width=result.width,
            height=result.height,
            paragraphs=result.paragraphs,
            language=result.language,
        )

    def to_layout_result(self, result: StructurePageResult) -> LayoutPageResult:
        return LayoutPageResult(
            page_number=result.page_number,
            width=result.width,
            height=result.height,
            regions=result.layout_regions,
        )

    @staticmethod
    def _extract_blocks(page_data: Any) -> list[dict]:
        if isinstance(page_data, dict):
            for key in ("parsing_res_list", "layout_res", "res", "blocks", "layout"):
                val = page_data.get(key)
                if isinstance(val, list):
                    return [b for b in val if isinstance(b, dict)]
            if "bbox" in page_data or "box" in page_data:
                return [page_data]
        return []

    @staticmethod
    def _normalize_bbox(
        raw: Any,
        page_w: float,
        page_h: float,
    ) -> tuple[float, float, float, float] | None:
        if raw is None:
            return None
        try:
            if isinstance(raw, dict):
                x = float(raw.get("x", raw.get("x1", 0)))
                y = float(raw.get("y", raw.get("y1", 0)))
                w = float(raw.get("width", raw.get("w", 0)))
                h = float(raw.get("height", raw.get("h", 0)))
                if w <= 0 and "x2" in raw:
                    w = float(raw["x2"]) - x
                if h <= 0 and "y2" in raw:
                    h = float(raw["y2"]) - y
            elif len(raw) >= 4:
                coords = [float(v) for v in raw[:4]]
                if coords[2] > page_w or coords[3] > page_h:
                    # x1,y1,x2,y2 format
                    x, y, x2, y2 = coords[0], coords[1], coords[2], coords[3]
                    w, h = x2 - x, y2 - y
                else:
                    x, y, w, h = coords[0], coords[1], coords[2], coords[3]
            else:
                return None
            return (max(0, x), max(0, y), max(1, w), max(1, h))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _block_text(block: dict) -> str:
        for key in ("text", "content", "transcription", "rec_text"):
            val = block.get(key)
            if isinstance(val, str) and val.strip():
                return val
        res = block.get("res")
        if isinstance(res, dict):
            for key in ("text", "html", "content"):
                val = res.get(key)
                if isinstance(val, str):
                    return val
        if isinstance(res, list):
            parts = []
            for item in res:
                if isinstance(item, dict):
                    t = item.get("text") or item.get("content")
                    if t:
                        parts.append(str(t))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(parts)
        return ""

    def _parse_table(
        self,
        block: dict,
        table_bbox: tuple[float, float, float, float],
    ) -> StructureTableResult | None:
        res = block.get("res") or block.get("html") or block
        cells: list[TableCellResult] = []
        rows_data: list[list[str]] = []

        if isinstance(res, dict) and "cells" in res:
            cell_list = res["cells"]
            max_row, max_col = 0, 0
            for cell in cell_list:
                if not isinstance(cell, dict):
                    continue
                ri = int(cell.get("row", cell.get("row_idx", 0)))
                ci = int(cell.get("col", cell.get("col_idx", 0)))
                max_row = max(max_row, ri)
                max_col = max(max_col, ci)
                cb = self._normalize_bbox(cell.get("bbox") or cell.get("box"), 9999, 9999)
                if cb is None:
                    tx, ty, tw, th = table_bbox
                    cw = tw / max(max_col + 1, 1)
                    ch = th / max(max_row + 1, 1)
                    cb = (tx + ci * cw, ty + ri * ch, cw, ch)
                text = str(cell.get("text", cell.get("content", "")))
                cells.append(TableCellResult(row=ri, col=ci, bbox=cb, text=text))

            for ri in range(max_row + 1):
                row: list[str] = []
                for ci in range(max_col + 1):
                    match = next((c for c in cells if c.row == ri and c.col == ci), None)
                    row.append(match.text if match else "")
                rows_data.append(row)
        elif isinstance(res, str) and "<tr" in res.lower():
            rows_data = self._html_table_to_rows(res)
        else:
            text = self._block_text(block)
            if text:
                rows_data = [[line] for line in text.splitlines() if line.strip()]

        if not rows_data:
            return None

        col_widths = [table_bbox[2] / max(len(rows_data[0]), 1)] * max(len(rows_data[0]), 1)
        row_heights = [table_bbox[3] / max(len(rows_data), 1)] * max(len(rows_data), 1)

        if not cells and rows_data:
            tx, ty, tw, th = table_bbox
            nrows, ncols = len(rows_data), max(len(r) for r in rows_data)
            cw, ch = tw / max(ncols, 1), th / max(nrows, 1)
            for ri, row in enumerate(rows_data):
                for ci, cell_text in enumerate(row):
                    cells.append(
                        TableCellResult(
                            row=ri,
                            col=ci,
                            bbox=(tx + ci * cw, ty + ri * ch, cw, ch),
                            text=cell_text,
                        )
                    )

        return StructureTableResult(
            bbox=table_bbox,
            rows=rows_data,
            cells=cells,
            col_widths=col_widths,
            row_heights=row_heights,
        )

    @staticmethod
    def _html_table_to_rows(html: str) -> list[list[str]]:
        import re

        rows: list[list[str]] = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
            if cells:
                cleaned = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                rows.append(cleaned)
        return rows
