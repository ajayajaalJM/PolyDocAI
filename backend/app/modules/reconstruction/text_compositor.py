"""Compose translated pages: erase original text regions, draw translated text in place."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont

from app.models.document import TableBlock, TextBlock
from app.providers.fonts.manager import FontManager

logger = structlog.get_logger(__name__)

# (regular, bold) — checked in order
_FONT_CANDIDATES: list[tuple[str, str]] = [
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
]

_ARABIC_FONT_CANDIDATES: list[tuple[str, str]] = [
    (
        "/System/Library/Fonts/Supplemental/DecoTypeNaskh.ttc",
        "/System/Library/Fonts/Supplemental/DecoTypeNaskh.ttc",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]

_ERASE_PAD = 10
_BORDER_RING = 10
_BBOX_EXPAND_X = 0.18
_BBOX_EXPAND_Y = 0.22


def _load_font(
    size: int,
    weight: str | None = None,
    *,
    arabic: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(6, int(round(size)))
    bold = weight == "bold"
    candidates = _ARABIC_FONT_CANDIDATES if arabic else _FONT_CANDIDATES
    for regular, bold_path in candidates:
        path = bold_path if bold and os.path.isfile(bold_path) else regular
        if os.path.isfile(path):
            try:
                if path.endswith(".ttc"):
                    return ImageFont.truetype(path, size, index=1 if bold else 0)
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 6:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return 0, 0, 0


def _sample_border_background(
    img: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    ring: int = _BORDER_RING,
) -> tuple[int, int, int]:
    """Sample pixels from a ring around the bbox (excludes the text interior)."""
    px = img.load()
    width, height = img.size
    ox1 = max(0, x - ring)
    oy1 = max(0, y - ring)
    ox2 = min(width, x + w + ring)
    oy2 = min(height, y + h + ring)
    ix1, iy1, ix2, iy2 = x, y, x + w, y + h

    samples: list[tuple[int, int, int]] = []
    for py in range(oy1, oy2):
        for px_ in range(ox1, ox2):
            if ix1 <= px_ < ix2 and iy1 <= py < iy2:
                continue
            samples.append(px[px_, py][:3])

    if not samples:
        # Fall back to corner samples just outside the box
        for cx, cy in (
            (max(0, x - 1), max(0, y - 1)),
            (min(width - 1, x + w), max(0, y - 1)),
            (max(0, x - 1), min(height - 1, y + h)),
            (min(width - 1, x + w), min(height - 1, y + h)),
        ):
            samples.append(px[cx, cy][:3])

    r = sum(s[0] for s in samples) // len(samples)
    g = sum(s[1] for s in samples) // len(samples)
    b = sum(s[2] for s in samples) // len(samples)
    return r, g, b


def _expanded_erase_rect(
    block: TextBlock,
    img_width: int,
    img_height: int,
    *,
    pad: int = _ERASE_PAD,
) -> tuple[int, int, int, int]:
    """Expand OCR bbox so painted erase covers anti-aliased text edges."""
    fs = block.style.font_size or 12
    extra = max(pad, int(fs * 0.65))
    expand_x = max(6.0, block.bbox.width * _BBOX_EXPAND_X)
    expand_y = max(5.0, block.bbox.height * _BBOX_EXPAND_Y)
    x1 = int(block.bbox.x - expand_x - extra)
    y1 = int(block.bbox.y - expand_y - extra)
    x2 = int(block.bbox.x + block.bbox.width + expand_x + extra)
    y2 = int(block.bbox.y + block.bbox.height + expand_y + extra)
    return (
        max(0, x1),
        max(0, y1),
        min(img_width, x2),
        min(img_height, y2),
    )


def _erase_bbox(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    bbox,
    background_color: str | None = None,
    pad: int = _ERASE_PAD,
) -> None:
    x = int(bbox.x)
    y = int(bbox.y)
    w = int(bbox.width)
    h = int(bbox.height)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.width, x + w + pad)
    y2 = min(img.height, y + h + pad)

    if background_color:
        fill = _hex_to_rgb(background_color)
    else:
        fill = _sample_border_background(img, x, y, w, h)

    draw.rectangle([x1, y1, x2, y2], fill=fill)


def _erase_text_region(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    block: TextBlock,
    pad: int = _ERASE_PAD,
) -> None:
    x1, y1, x2, y2 = _expanded_erase_rect(block, img.width, img.height, pad=pad)
    if block.style.background_color:
        fill = _hex_to_rgb(block.style.background_color)
    else:
        fill = _sample_border_background(
            img,
            int(block.bbox.x),
            int(block.bbox.y),
            int(block.bbox.width),
            int(block.bbox.height),
        )
    draw.rectangle([x1, y1, x2, y2], fill=fill)


def _erase_table_region(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    block: TableBlock,
    pad: int = _ERASE_PAD,
) -> None:
    x = int(block.bbox.x)
    y = int(block.bbox.y)
    w = int(block.bbox.width)
    h = int(block.bbox.height)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.width, x + w + pad)
    y2 = min(img.height, y + h + pad)
    fill = _sample_border_background(img, x, y, w, h)
    draw.rectangle([x1, y1, x2, y2], fill=fill)


def _wrap_lines(text: str, font: ImageFont.ImageFont, max_width: float, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            trial = f"{current} {word}".strip() if current else word
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def _fit_font_size(
    text: str,
    font_size: float,
    font_weight: str | None,
    max_width: float,
    max_height: float,
    line_height: float,
    draw: ImageDraw.ImageDraw,
    *,
    arabic: bool = False,
) -> tuple[ImageFont.ImageFont, list[str]]:
    size = font_size
    while size >= 6:
        font = _load_font(size, font_weight, arabic=arabic)
        lines = _wrap_lines(text, font, max_width, draw)
        block_height = len(lines) * line_height
        if block_height <= max_height + 2:
            return font, lines
        size -= 0.5
    font = _load_font(6, font_weight, arabic=arabic)
    return font, _wrap_lines(text, font, max_width, draw)


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    block: TextBlock,
    text: str,
    shape_fn,
) -> None:
    use_arabic = block.style.direction == "rtl" or FontManager.contains_arabic(text)
    text = shape_fn(text, "rtl" if use_arabic else (block.style.direction or "ltr"))
    x = int(block.bbox.x)
    y = int(block.bbox.y)
    w = int(block.bbox.width)
    h = int(block.bbox.height)

    font_size = block.style.font_size or 12
    line_height = block.style.line_height or font_size * 1.2
    color = block.style.color or "#000000"
    fill = _hex_to_rgb(color)

    font, lines = _fit_font_size(
        text,
        font_size,
        block.style.font_weight,
        max(w - 2, 8),
        h,
        line_height,
        draw,
        arabic=use_arabic,
    )

    alignment = block.style.alignment or ("right" if use_arabic else "left")
    total_text_h = len(lines) * line_height
    start_y = y + max(0, (h - total_text_h) / 2)

    for i, line in enumerate(lines):
        if not line:
            continue
        line_w = draw.textlength(line, font=font)
        if alignment == "center":
            tx = x + (w - line_w) / 2
        elif alignment == "right":
            tx = x + w - line_w
        else:
            tx = x
        ty = start_y + i * line_height
        draw.text((tx, ty), line, fill=fill, font=font)


def _draw_table_block(
    draw: ImageDraw.ImageDraw,
    block: TableBlock,
    *,
    use_translated: bool,
    shape_fn,
) -> None:
    if block.cells:
        for cell in block.cells:
            text = (
                cell.translated_text
                if use_translated and cell.translated_text
                else cell.text
            )
            if not str(text).strip():
                continue
            use_arabic = FontManager.contains_arabic(str(text))
            shaped = shape_fn(str(text), "rtl" if use_arabic else "ltr")
            fs = cell.style.font_size if cell.style and cell.style.font_size else 10
            font = _load_font(int(fs), cell.style.font_weight if cell.style else None, arabic=use_arabic)
            cx = int(cell.bbox.x) + 3
            cy = int(cell.bbox.y) + 2
            color = _hex_to_rgb(cell.style.color if cell.style and cell.style.color else "#000000")
            draw.text((cx, cy), shaped[:300], fill=color, font=font)
        return

    rows = block.translated_rows if use_translated and block.translated_rows else block.rows
    if not rows:
        return

    num_rows = len(rows)
    num_cols = max(len(row) for row in rows)
    if num_cols == 0:
        return

    x = int(block.bbox.x)
    y = int(block.bbox.y)
    w = int(block.bbox.width)
    h = int(block.bbox.height)
    cell_w = w / num_cols
    cell_h = h / max(num_rows, 1)
    font_size = max(6, min(14, int(cell_h * 0.5)))

    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            text = str(cell).strip()
            if not text:
                continue
            use_arabic = FontManager.contains_arabic(text)
            shaped = shape_fn(text, "rtl" if use_arabic else "ltr")
            font = _load_font(font_size, arabic=use_arabic)
            cx = x + ci * cell_w + 3
            cy = y + ri * cell_h + 2
            draw.text((cx, cy), shaped[:300], fill=(0, 0, 0), font=font)


def strip_text_from_page(
    page_raster: Path,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None = None,
) -> Image.Image:
    """Return a copy of the page raster with text/table regions erased."""
    img = Image.open(page_raster).convert("RGB")
    draw = ImageDraw.Draw(img)
    mask = Image.new("L", img.size, 0)
    mask_draw = ImageDraw.Draw(mask)

    for block in sorted(text_blocks, key=lambda b: b.reading_order):
        x1, y1, x2, y2 = _expanded_erase_rect(block, img.width, img.height)
        if block.style.background_color:
            fill = _hex_to_rgb(block.style.background_color)
            draw.rectangle([x1, y1, x2, y2], fill=fill)
        else:
            mask_draw.rectangle([x1, y1, x2, y2], fill=255)
    for block in table_blocks or []:
        x = int(block.bbox.x)
        y = int(block.bbox.y)
        w = int(block.bbox.width)
        h = int(block.bbox.height)
        x1 = max(0, x - _ERASE_PAD)
        y1 = max(0, y - _ERASE_PAD)
        x2 = min(img.width, x + w + _ERASE_PAD)
        y2 = min(img.height, y + h + _ERASE_PAD)
        mask_draw.rectangle([x1, y1, x2, y2], fill=255)

    if mask.getbbox():
        try:
            import cv2
            import numpy as np

            img_arr = np.array(img)
            mask_arr = np.array(mask)
            inpainted = cv2.inpaint(img_arr, mask_arr, 3, cv2.INPAINT_TELEA)
            img = Image.fromarray(inpainted)
        except Exception:
            draw = ImageDraw.Draw(img)
            for block in sorted(text_blocks, key=lambda b: b.reading_order):
                _erase_text_region(draw, img, block)
            for block in table_blocks or []:
                _erase_table_region(draw, img, block)
    else:
        for block in table_blocks or []:
            draw = ImageDraw.Draw(img)
            _erase_table_region(draw, img, block)

    return img


def compose_translated_page(
    page_raster: Path,
    text_blocks: list[TextBlock],
    *,
    use_translated: bool = True,
    shape_fn,
    table_blocks: list[TableBlock] | None = None,
) -> Image.Image:
    """Rebuild page from stripped background + translated text (no original text layer)."""
    img = strip_text_from_page(page_raster, text_blocks, table_blocks)
    draw = ImageDraw.Draw(img)

    for block in sorted(text_blocks, key=lambda b: b.reading_order):
        if use_translated:
            content = block.translated_text or block.original_text
        else:
            content = block.original_text
        if not content.strip():
            continue
        _draw_text_block(draw, block, content, shape_fn)

    for block in table_blocks or []:
        _draw_table_block(draw, block, use_translated=use_translated, shape_fn=shape_fn)

    return img


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
