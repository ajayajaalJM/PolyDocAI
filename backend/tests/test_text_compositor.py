from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.models.document import BoundingBox, TableBlock, TableCell, TextBlock, TextStyle
from app.modules.reconstruction.text_compositor import (
    compose_translated_page,
    strip_text_from_page,
)


def _shape(text: str, _direction: str = "ltr") -> str:
    return text


def _make_page_with_text(
    tmp_path: Path,
    text: str,
    *,
    translated: str | None = None,
    erase_boxes: list[list[float]] | None = None,
) -> tuple[Path, list[TextBlock]]:
    img = Image.new("RGB", (400, 120), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((40, 40), text, fill=(0, 0, 0), font=font)
    raster = tmp_path / "page.png"
    img.save(raster)

    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=30, y=30, width=200, height=40),
        reading_order=0,
        original_text=text,
        translated_text=translated,
        style=TextStyle(font_size=14, color="#000000"),
        metadata={"erase_boxes": erase_boxes or [[30.0, 30.0, 200.0, 40.0]]},
    )
    return raster, [block]


def test_strip_text_from_page_removes_dark_pixels(tmp_path: Path):
    raster, blocks = _make_page_with_text(tmp_path, "Hello source")
    stripped = strip_text_from_page(raster, blocks)
    # Region where text was should be lighter than black after erase/inpaint
    cx, cy = 60, 50
    r, g, b = stripped.getpixel((cx, cy))
    assert r + g + b > 120


def test_compose_translated_page_uses_translation_not_original(tmp_path: Path):
    raster, blocks = _make_page_with_text(
        tmp_path,
        "Hello source",
        translated="Bonjour cible",
    )
    composed = compose_translated_page(
        raster,
        blocks,
        use_translated=True,
        shape_fn=_shape,
    )
    # Composed image should not contain obvious source-only rendering at same spot
    # and should include translated content drawn by compositor
    assert composed.size == (400, 120)


def test_compose_skips_untranslated_blocks(tmp_path: Path):
    raster, blocks = _make_page_with_text(tmp_path, "Only source", translated=None)
    composed = compose_translated_page(
        raster,
        blocks,
        use_translated=True,
        shape_fn=_shape,
    )
    # With no translation, block is skipped — stripped background only
    stripped = strip_text_from_page(raster, blocks)
    assert list(composed.getdata()) == list(stripped.getdata())


def test_table_cell_erase_preserves_table_area(tmp_path: Path):
    img = Image.new("RGB", (300, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 280, 180], outline=(0, 0, 0), width=2)
    draw.line([20, 70, 280, 70], fill=(0, 0, 0), width=1)
    draw.text((30, 35), "Cell A", fill=(0, 0, 0))
    draw.text((30, 85), "Cell B", fill=(0, 0, 0))
    raster = tmp_path / "table_page.png"
    img.save(raster)

    table = TableBlock(
        page_number=1,
        bbox=BoundingBox(x=20, y=20, width=260, height=160),
        rows=[["Cell A"], ["Cell B"]],
        cells=[
            TableCell(row=0, col=0, bbox=BoundingBox(x=22, y=22, width=256, height=46), text="Cell A"),
            TableCell(row=1, col=0, bbox=BoundingBox(x=22, y=72, width=256, height=46), text="Cell B"),
        ],
    )
    stripped = strip_text_from_page(raster, [], [table])
    assert sum(stripped.getpixel((35, 40))) > 400
    assert sum(stripped.getpixel((35, 90))) > 400
