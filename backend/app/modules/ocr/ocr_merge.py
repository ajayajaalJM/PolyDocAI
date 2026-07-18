"""Merge OCR results from PP-Structure and Paddle line OCR."""

from __future__ import annotations

from app.modules.ocr.paddle_service import OCRPageResult, OCRParagraph


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _paragraph_score(para: OCRParagraph) -> float:
    line_count = len(para.lines)
    word_count = sum(len(line.words) for line in para.lines)
    return len(para.text) + line_count * 12 + word_count * 4 + para.confidence * 10


def _pick_better(a: OCRParagraph, b: OCRParagraph) -> OCRParagraph:
    return a if _paragraph_score(a) >= _paragraph_score(b) else b


def _dedupe_paragraphs(paragraphs: list[OCRParagraph], *, iou_threshold: float = 0.45) -> list[OCRParagraph]:
    if not paragraphs:
        return []

    ordered = sorted(paragraphs, key=lambda p: (-_paragraph_score(p), p.reading_order, p.bbox[1], p.bbox[0]))
    kept: list[OCRParagraph] = []

    for para in ordered:
        duplicate_idx: int | None = None
        for idx, existing in enumerate(kept):
            if _iou(para.bbox, existing.bbox) >= iou_threshold:
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            kept.append(para)
        else:
            kept[duplicate_idx] = _pick_better(kept[duplicate_idx], para)

    kept.sort(key=lambda p: (p.bbox[1], p.bbox[0]))
    for order, para in enumerate(kept):
        para.reading_order = order
    return kept


def merge_ocr_results(primary: OCRPageResult, supplemental: OCRPageResult) -> OCRPageResult:
    """Combine structure OCR with dense Paddle line OCR."""
    primary_text = sum(len(p.text) for p in primary.paragraphs)
    supplemental_text = sum(len(p.text) for p in supplemental.paragraphs)

    if not supplemental.paragraphs:
        return primary
    if not primary.paragraphs:
        return supplemental
    if primary_text < 40 and supplemental_text > primary_text * 2:
        merged = list(supplemental.paragraphs)
    elif len(primary.paragraphs) <= 2 and len(supplemental.paragraphs) >= len(primary.paragraphs) * 3:
        merged = list(supplemental.paragraphs)
        for para in primary.paragraphs:
            if not any(_iou(para.bbox, s.bbox) >= 0.45 for s in merged):
                merged.append(para)
    else:
        merged = list(supplemental.paragraphs)
        for para in primary.paragraphs:
            if not any(_iou(para.bbox, s.bbox) >= 0.45 for s in merged):
                merged.append(para)

    deduped = _dedupe_paragraphs(merged)
    return OCRPageResult(
        page_number=primary.page_number,
        width=primary.width or supplemental.width,
        height=primary.height or supplemental.height,
        paragraphs=deduped,
        rotation=primary.rotation or supplemental.rotation,
        language=primary.language or supplemental.language,
    )
