from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.models.document import BoundingBox, TextBlock, TextStyle
from app.modules.reconstruction.layout_reflow import effective_compose_bbox
from app.modules.reconstruction.text_compositor import measure_strip_quality, strip_text_from_page
from app.modules.reconstruction.text_residual import detect_residual_regions, measure_page_residual_score


def _make_text_page(tmp_path: Path, text: str) -> tuple[Path, TextBlock]:
    img = Image.new("RGB", (400, 100), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((30, 30), text, fill=(0, 0, 0), font=font)
    raster = tmp_path / "page.png"
    img.save(raster)
    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=20, y=20, width=220, height=40),
        reading_order=0,
        original_text=text,
        style=TextStyle(font_size=14),
        metadata={"erase_boxes": [[20.0, 20.0, 220.0, 40.0]]},
    )
    return raster, block


def test_refine_strip_reduces_residual(tmp_path: Path):
    raster, block = _make_text_page(tmp_path, "Source language text")
    stripped = strip_text_from_page(raster, [block], refine_passes=3)
    score = measure_strip_quality(stripped, [block])
    assert score < 0.5


def test_aggressive_strip_lower_residual_than_single_pass(tmp_path: Path):
    raster, block = _make_text_page(tmp_path, "Hello world text")
    light = strip_text_from_page(raster, [block], refine_passes=0)
    heavy = strip_text_from_page(raster, [block], refine_passes=4, aggressive=True)
    assert measure_strip_quality(heavy, [block]) <= measure_strip_quality(light, [block]) + 0.05


def test_effective_compose_bbox_grows_for_longer_translation():
    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=10, y=10, width=200, height=30),
        reading_order=0,
        original_text="Short",
        translated_text="This is a much longer translated sentence that needs more vertical space.",
        style=TextStyle(font_size=12),
    )
    bbox = effective_compose_bbox(
        block,
        block.translated_text or "",
        page_height=800,
        page_width=600,
    )
    assert bbox.height >= block.bbox.height


def test_detect_residual_on_unstripped_page(tmp_path: Path):
    raster, block = _make_text_page(tmp_path, "Visible")
    img = Image.open(raster)
    from app.modules.reconstruction.text_compositor import _text_erase_rects

    regions = detect_residual_regions(
        img,
        [block],
        lambda b, w, h: _text_erase_rects(b, w, h),
        threshold=0.2,
    )
    assert regions

    stripped = strip_text_from_page(raster, [block], refine_passes=3)
    score = measure_page_residual_score(
        stripped,
        [block],
        lambda b, w, h: _text_erase_rects(b, w, h),
    )
    assert score < 0.45
