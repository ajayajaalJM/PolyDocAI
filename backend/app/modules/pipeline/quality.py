"""Document quality scoring for review workflow."""

from __future__ import annotations

from pathlib import Path

from app.models.document import Document, TableBlock, TextBlock


def compute_quality_scores(document: Document, storage_root: Path | None = None) -> dict[str, float]:
    text_blocks: list[TextBlock] = []
    table_blocks: list[TableBlock] = []
    for page in document.pages:
        text_blocks.extend(b for b in page.blocks if isinstance(b, TextBlock))
        table_blocks.extend(b for b in page.blocks if isinstance(b, TableBlock))

    if not text_blocks:
        return {
            "ocr_confidence": 0.0,
            "translation_qa": 0.0,
            "overflow_count": 0.0,
            "source_text_residual": 1.0,
        }

    ocr_scores = [b.confidence for b in text_blocks if b.confidence is not None]
    ocr_avg = sum(ocr_scores) / len(ocr_scores) if ocr_scores else 0.85

    qa_scores = [
        b.translation_confidence
        for b in text_blocks
        if b.translation_confidence is not None
    ]
    qa_avg = sum(qa_scores) / len(qa_scores) if qa_scores else 1.0

    overflow = 0
    for block in text_blocks:
        max_chars = block.metadata.get("max_chars")
        translated = block.translated_text or ""
        if max_chars and len(translated) > int(max_chars) * 1.15:
            overflow += 1

    translated_count = sum(1 for b in text_blocks if b.translated_text)
    edit_count = sum(1 for b in text_blocks if b.is_edited)

    residual_scores: list[float] = []
    if storage_root:
        from PIL import Image

        from app.modules.reconstruction.text_compositor import measure_strip_quality

        for page in document.pages:
            if not page.translated_raster_path:
                continue
            stripped_path = (
                storage_root
                / "uploads"
                / document.id
                / "stripped"
                / f"page_{page.page_number:04d}.png"
            )
            if not stripped_path.exists():
                continue
            page_text = [b for b in page.blocks if isinstance(b, TextBlock)]
            page_tables = [b for b in page.blocks if isinstance(b, TableBlock)]
            with Image.open(stripped_path) as img:
                residual_scores.append(measure_strip_quality(img, page_text, page_tables))

    residual_avg = (
        sum(residual_scores) / len(residual_scores) if residual_scores else 0.0
    )

    return {
        "ocr_confidence": round(ocr_avg, 3),
        "translation_qa": round(qa_avg, 3),
        "overflow_count": float(overflow),
        "blocks_total": float(len(text_blocks)),
        "blocks_translated": float(translated_count),
        "blocks_edited": float(edit_count),
        "source_text_residual": round(residual_avg, 3),
        "layout_quality": round(max(0.0, 1.0 - residual_avg - overflow * 0.05), 3),
    }
