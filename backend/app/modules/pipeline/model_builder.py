from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models.document import (
    BoundingBox,
    Document,
    ImageBlock,
    ImageResolution,
    Page,
    PageStatus,
    TableBlock,
    TableCell,
    TextBlock,
)
from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult
from app.modules.ocr.paddle_service import OCRPageResult
from app.modules.preprocessing.style_analyzer import estimate_max_chars, infer_style, style_from_pdf_span

LAYOUT_TO_TEXT_TYPE: dict[LayoutElementType, str] = {
    LayoutElementType.HEADING: "heading",
    LayoutElementType.TITLE: "heading",
    LayoutElementType.PARAGRAPH: "paragraph",
    LayoutElementType.LIST: "list",
    LayoutElementType.CAPTION: "caption",
    LayoutElementType.QUOTE: "quote",
    LayoutElementType.HEADER: "header",
    LayoutElementType.FOOTER: "footer",
    LayoutElementType.SIDEBAR: "sidebar",
}

IMAGE_REGION_TYPES = {
    LayoutElementType.FIGURE,
    LayoutElementType.IMAGE,
    LayoutElementType.LOGO,
}

IOU_IMAGE_FILTER = 0.65
IOU_LAYOUT_MATCH = 0.15
IOU_SPAN_COVER = 0.45
MIN_VECTOR_SPANS = 3


def _bbox_tuple_to_model(bbox: tuple[float, float, float, float]) -> BoundingBox:
    return BoundingBox(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _is_inside_image_region(
    text_bbox: tuple[float, float, float, float],
    image_regions: list[tuple[float, float, float, float]],
) -> bool:
    for ib in image_regions:
        if _iou(text_bbox, ib) >= IOU_IMAGE_FILTER:
            return True
    return False


def _span_to_bbox(span: dict) -> tuple[float, float, float, float]:
    sb = span["bbox"]
    return (sb[0], sb[1], sb[2] - sb[0], sb[3] - sb[1])


def _covered_by_spans(
    bbox: tuple[float, float, float, float], spans: list[dict], threshold: float = IOU_SPAN_COVER
) -> bool:
    return any(_iou(bbox, _span_to_bbox(span)) >= threshold for span in spans)


def _erase_boxes_from_paragraph(para) -> list[list[float]]:
    """Collect line/word bounding boxes for precise text removal during reconstruction."""
    boxes: list[list[float]] = []
    for line in getattr(para, "lines", []) or []:
        if line.bbox:
            boxes.append([line.bbox[0], line.bbox[1], line.bbox[2], line.bbox[3]])
        for word in getattr(line, "words", []) or []:
            if word.bbox:
                boxes.append([word.bbox[0], word.bbox[1], word.bbox[2], word.bbox[3]])
    if not boxes and para.bbox:
        boxes.append([para.bbox[0], para.bbox[1], para.bbox[2], para.bbox[3]])
    return boxes


def _erase_boxes_from_span(span: dict) -> list[list[float]]:
    sb = span.get("bbox")
    if not sb or len(sb) < 4:
        return []
    if len(sb) == 4 and float(sb[2]) > float(sb[0]):
        return [[float(sb[0]), float(sb[1]), float(sb[2]) - float(sb[0]), float(sb[3]) - float(sb[1])]]
    return [[float(sb[0]), float(sb[1]), float(sb[2]), float(sb[3])]]


def _merge_vector_spans(spans: list[dict]) -> list[dict]:
    """Merge adjacent line spans into paragraph blocks for better translation context."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    merged: list[dict] = []
    current: dict | None = None

    for span in ordered:
        if current is None:
            current = {**span, "text": str(span.get("text", "")).strip()}
            current["_erase_boxes"] = _erase_boxes_from_span(span)
            continue

        cb = current["bbox"]
        sb = span["bbox"]
        fs = float(current.get("font_size") or 12)
        same_line = abs(float(cb[1]) - float(sb[1])) <= fs * 0.55
        gap = float(sb[0]) - float(cb[2])
        close = gap <= fs * 1.8
        if same_line and close:
            current["text"] = f"{current['text']} {str(span.get('text', '')).strip()}".strip()
            x1 = min(float(cb[0]), float(sb[0]))
            y1 = min(float(cb[1]), float(sb[1]))
            x2 = max(float(cb[2]), float(sb[2]))
            y2 = max(float(cb[3]), float(sb[3]))
            current["bbox"] = [x1, y1, x2, y2]
            erase = list(current.get("_erase_boxes") or [])
            erase.extend(_erase_boxes_from_span(span))
            current["_erase_boxes"] = erase
        else:
            merged.append(current)
            current = {**span, "text": str(span.get("text", "")).strip()}
            if "_erase_boxes" not in current:
                current["_erase_boxes"] = _erase_boxes_from_span(span)

    if current:
        merged.append(current)
    return merged


class DocumentModelBuilder:
    def merge_page(
        self,
        ocr: OCRPageResult,
        layout: LayoutPageResult,
        thumbnail_path: str | None = None,
        raster_path: str | None = None,
        pdf_spans: list[dict] | None = None,
        structure_tables: list | None = None,
        image_path: Path | None = None,
    ) -> Page:
        blocks: list[TextBlock | ImageBlock | TableBlock] = []

        image_regions = [
            r.bbox
            for r in layout.regions
            if r.element_type in IMAGE_REGION_TYPES
        ]
        table_regions = [r for r in layout.regions if r.element_type == LayoutElementType.TABLE]

        use_vector = bool(
            pdf_spans
            and len(pdf_spans) >= MIN_VECTOR_SPANS
            and sum(len(s.get("text", "")) for s in pdf_spans) > 40
        )
        vector_spans = _merge_vector_spans(pdf_spans or [])

        if use_vector:
            for span in vector_spans:
                text = str(span.get("text", "")).strip()
                if not text:
                    continue
                bbox = _span_to_bbox(span)
                if _is_inside_image_region(bbox, image_regions):
                    continue
                layout_type = self._match_layout_type(bbox, layout.regions)
                style = style_from_pdf_span(span, layout_type, ocr.width)
                max_chars = estimate_max_chars(bbox, style.font_size or 12)
                blocks.append(
                    TextBlock(
                        page_number=ocr.page_number,
                        bbox=_bbox_tuple_to_model(bbox),
                        confidence=1.0,
                        layout_type=layout_type,  # type: ignore[arg-type]
                        original_text=text,
                        style=style,
                        language=ocr.language,
                        metadata={
                            "max_chars": max_chars,
                            "source": "pdf_vector",
                            "erase_boxes": span.get("_erase_boxes") or _erase_boxes_from_span(span),
                        },
                    )
                )

        # OCR blocks for regions not covered by vector text (scanned areas / gaps)
        for para in sorted(ocr.paragraphs, key=lambda p: p.reading_order):
            if _is_inside_image_region(para.bbox, image_regions):
                continue
            if use_vector and _covered_by_spans(para.bbox, vector_spans):
                continue

            layout_type = self._match_layout_type(para.bbox, layout.regions)
            if image_path:
                from app.modules.preprocessing.style_analyzer import infer_style_from_image

                style = infer_style_from_image(
                    image_path, para.bbox, layout_type, ocr.width, ocr.language
                )
            else:
                style = infer_style(para.bbox, layout_type, ocr.width, ocr.language)

            if pdf_spans and not use_vector:
                for span in pdf_spans:
                    span_bbox = _span_to_bbox(span)
                    if _iou(para.bbox, span_bbox) > 0.3:
                        style.font_size = span.get("font_size", style.font_size)
                        style.font_family = span.get("font_family", style.font_family)
                        style.color = span.get("color", style.color)
                        break

            max_chars = estimate_max_chars(para.bbox, style.font_size or 12)
            blocks.append(
                TextBlock(
                    page_number=ocr.page_number,
                    bbox=_bbox_tuple_to_model(para.bbox),
                    confidence=para.confidence,
                    layout_type=layout_type,  # type: ignore[arg-type]
                    original_text=para.text,
                    style=style,
                    language=ocr.language,
                    metadata={
                        "max_chars": max_chars,
                        "source": "ocr",
                        "erase_boxes": _erase_boxes_from_paragraph(para),
                    },
                )
            )

        # --- Table blocks ---
        if structure_tables:
            for table in structure_tables:
                cells = [
                    TableCell(
                        row=c.row,
                        col=c.col,
                        bbox=_bbox_tuple_to_model(c.bbox),
                        text=c.text,
                    )
                    for c in table.cells
                ]
                blocks.append(
                    TableBlock(
                        page_number=ocr.page_number,
                        bbox=_bbox_tuple_to_model(table.bbox),
                        rows=table.rows,
                        cells=cells,
                        col_widths=table.col_widths,
                        row_heights=table.row_heights,
                        layer="content",
                    )
                )
        else:
            for region in table_regions:
                table_texts = [
                    p.text
                    for p in ocr.paragraphs
                    if _iou(p.bbox, region.bbox) >= IOU_LAYOUT_MATCH
                ]
                if table_texts:
                    rows = [[t] for t in table_texts]
                else:
                    rows = [[" "]]
                blocks.append(
                    TableBlock(
                        page_number=ocr.page_number,
                        bbox=_bbox_tuple_to_model(region.bbox),
                        confidence=region.confidence,
                        rows=rows,
                        layer="content",
                    )
                )

        # --- Image blocks (assets cropped in orchestrator) ---
        for region in layout.regions:
            if region.element_type not in IMAGE_REGION_TYPES:
                continue
            blocks.append(
                ImageBlock(
                    page_number=ocr.page_number,
                    bbox=_bbox_tuple_to_model(region.bbox),
                    confidence=region.confidence,
                    layout_type=region.element_type.value,  # type: ignore[arg-type]
                    asset_path="",
                    layer="content",
                    z_index=1,
                    resolution=ImageResolution(
                        width=int(region.bbox[2]),
                        height=int(region.bbox[3]),
                    ),
                    metadata={"region_bbox": list(region.bbox)},
                )
            )

        # Global reading order: top-to-bottom, left-to-right
        blocks.sort(key=lambda b: (b.bbox.y, b.bbox.x))
        for i, block in enumerate(blocks):
            block.reading_order = i

        return Page(
            page_number=ocr.page_number,
            width=ocr.width,
            height=ocr.height,
            thumbnail_path=thumbnail_path,
            raster_path=raster_path,
            ocr_status=PageStatus.COMPLETE,
            blocks=blocks,
        )

    @staticmethod
    def _match_layout_type(
        bbox: tuple[float, float, float, float], regions: list
    ) -> str:
        layout_type = "paragraph"
        best_iou = 0.0
        for region in regions:
            iou = _iou(bbox, region.bbox)
            if iou > best_iou and iou >= IOU_LAYOUT_MATCH:
                best_iou = iou
                layout_type = LAYOUT_TO_TEXT_TYPE.get(region.element_type, "paragraph")
        return layout_type

    def apply_to_document(self, document: Document, pages: list[Page]) -> Document:
        document.pages = pages
        document.page_count = len(pages)
        return document
