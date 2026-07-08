"""Serialize pipeline stage payloads for disk cache."""

from __future__ import annotations

from typing import Any

from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion
from app.modules.ocr.paddle_service import OCRLine, OCRPageResult, OCRParagraph, OCRWord


def layout_to_dict(layout: LayoutPageResult) -> dict[str, Any]:
    return {
        "page_number": layout.page_number,
        "width": layout.width,
        "height": layout.height,
        "regions": [
            {
                "element_type": r.element_type.value,
                "confidence": r.confidence,
                "bbox": list(r.bbox),
                "reading_order": r.reading_order,
            }
            for r in layout.regions
        ],
    }


def layout_from_dict(data: dict[str, Any]) -> LayoutPageResult:
    regions = [
        LayoutRegion(
            element_type=LayoutElementType(item["element_type"]),
            confidence=float(item["confidence"]),
            bbox=tuple(item["bbox"]),  # type: ignore[arg-type]
            reading_order=int(item.get("reading_order", 0)),
        )
        for item in data.get("regions", [])
    ]
    return LayoutPageResult(
        page_number=int(data["page_number"]),
        width=float(data["width"]),
        height=float(data["height"]),
        regions=regions,
    )


def _word_from_dict(item: dict[str, Any]) -> OCRWord:
    bbox = item["bbox"]
    return OCRWord(
        text=item["text"],
        confidence=float(item["confidence"]),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
    )


def _line_from_dict(item: dict[str, Any]) -> OCRLine:
    bbox = item["bbox"]
    return OCRLine(
        text=item["text"],
        confidence=float(item["confidence"]),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        words=[_word_from_dict(w) for w in item.get("words", [])],
    )


def _paragraph_from_dict(item: dict[str, Any]) -> OCRParagraph:
    bbox = item["bbox"]
    return OCRParagraph(
        text=item["text"],
        confidence=float(item["confidence"]),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        lines=[_line_from_dict(line) for line in item.get("lines", [])],
        reading_order=int(item.get("reading_order", 0)),
    )


def ocr_to_dict(ocr: OCRPageResult) -> dict[str, Any]:
    paragraphs = []
    for para in ocr.paragraphs:
        paragraphs.append(
            {
                "text": para.text,
                "confidence": para.confidence,
                "bbox": list(para.bbox),
                "reading_order": para.reading_order,
                "lines": [
                    {
                        "text": line.text,
                        "confidence": line.confidence,
                        "bbox": list(line.bbox),
                        "words": [
                            {
                                "text": w.text,
                                "confidence": w.confidence,
                                "bbox": list(w.bbox),
                            }
                            for w in line.words
                        ],
                    }
                    for line in para.lines
                ],
            }
        )
    return {
        "page_number": ocr.page_number,
        "width": ocr.width,
        "height": ocr.height,
        "paragraphs": paragraphs,
        "rotation": ocr.rotation,
        "language": ocr.language,
    }


def ocr_from_dict(data: dict[str, Any]) -> OCRPageResult:
    return OCRPageResult(
        page_number=int(data["page_number"]),
        width=float(data["width"]),
        height=float(data["height"]),
        paragraphs=[_paragraph_from_dict(p) for p in data.get("paragraphs", [])],
        rotation=float(data.get("rotation", 0.0)),
        language=data.get("language"),
    )


def normalization_to_dict(output_path: str, width: float, height: float, **extra: object) -> dict[str, Any]:
    return {"output_path": output_path, "width": width, "height": height, **extra}
