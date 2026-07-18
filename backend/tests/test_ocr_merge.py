from __future__ import annotations

from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion
from app.modules.ocr.ocr_merge import merge_ocr_results
from app.modules.ocr.paddle_service import OCRPageResult, OCRParagraph
from app.modules.pipeline.model_builder import DocumentModelBuilder, _should_emit_image_region


def _para(text: str, x: float, y: float, w: float, h: float, order: int = 0) -> OCRParagraph:
    return OCRParagraph(
        text=text,
        confidence=0.9,
        bbox=(x, y, w, h),
        reading_order=order,
    )


def test_merge_prefers_dense_paddle_when_structure_is_sparse():
    sparse = OCRPageResult(
        page_number=1,
        width=1000,
        height=1400,
        paragraphs=[
            _para("Header only", 0, 0, 900, 80, 0),
            _para("Summary line", 0, 500, 900, 60, 1),
        ],
    )
    dense = OCRPageResult(
        page_number=1,
        width=1000,
        height=1400,
        paragraphs=[
            _para("Header only", 0, 0, 900, 80, 0),
            _para("Experience item 1", 0, 200, 900, 40, 1),
            _para("Experience item 2", 0, 250, 900, 40, 2),
            _para("Experience item 3", 0, 300, 900, 40, 3),
        ],
    )
    merged = merge_ocr_results(sparse, dense)
    assert len(merged.paragraphs) >= 3


def test_should_not_emit_full_page_figure_when_text_present():
    region = LayoutRegion(
        element_type=LayoutElementType.FIGURE,
        confidence=0.9,
        bbox=(0, 0, 1000, 1400),
    )
    paragraphs = [
        _para("Name Surname", 50, 40, 400, 30),
        _para("Job title", 50, 80, 300, 24),
        _para("Experience bullet", 50, 200, 800, 24),
    ]
    assert _should_emit_image_region(region, paragraphs, 1000, 1400) is False


def test_model_builder_skips_misclassified_full_page_figure():
    builder = DocumentModelBuilder()
    ocr = OCRPageResult(
        page_number=1,
        width=1000,
        height=1400,
        paragraphs=[
            _para("Header", 0, 0, 900, 50, 0),
            _para("Summary text", 0, 80, 900, 40, 1),
            _para("Role at company", 0, 160, 900, 30, 2),
        ],
    )
    layout = LayoutPageResult(
        page_number=1,
        width=1000,
        height=1400,
        regions=[
            LayoutRegion(
                element_type=LayoutElementType.FIGURE,
                confidence=0.95,
                bbox=(0, 0, 1000, 1400),
            )
        ],
    )
    page = builder.merge_page(ocr, layout)
    text_blocks = [b for b in page.blocks if b.type == "text"]
    image_blocks = [b for b in page.blocks if b.type == "image"]
    assert len(text_blocks) >= 2
    assert len(image_blocks) == 0
