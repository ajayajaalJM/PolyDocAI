"""Tests for pipeline cache serializers."""

from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion
from app.modules.ocr.paddle_service import OCRLine, OCRPageResult, OCRParagraph, OCRWord
from app.pipeline.serializers import layout_from_dict, layout_to_dict, ocr_from_dict, ocr_to_dict


def test_layout_round_trip():
    layout = LayoutPageResult(
        page_number=1,
        width=600,
        height=800,
        regions=[
            LayoutRegion(LayoutElementType.PARAGRAPH, 0.9, (10, 20, 100, 30), reading_order=0),
        ],
    )
    restored = layout_from_dict(layout_to_dict(layout))
    assert restored.page_number == 1
    assert restored.regions[0].element_type == LayoutElementType.PARAGRAPH


def test_ocr_round_trip():
    word = OCRWord("hi", 0.95, (1, 2, 10, 8))
    line = OCRLine("hi", 0.95, (1, 2, 10, 8), words=[word])
    para = OCRParagraph("hi", 0.95, (1, 2, 10, 8), lines=[line], reading_order=0)
    ocr = OCRPageResult(page_number=1, width=100, height=100, paragraphs=[para])
    restored = ocr_from_dict(ocr_to_dict(ocr))
    assert restored.paragraphs[0].text == "hi"
    assert restored.paragraphs[0].lines[0].words[0].text == "hi"
