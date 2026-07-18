"""Build text-free page backgrounds without smearing graphics via bbox inpainting."""

from __future__ import annotations

from pathlib import Path

import structlog
from PIL import Image

from app.models.document import TableBlock, TextBlock
from app.modules.reconstruction.text_mask import mask_from_image

logger = structlog.get_logger(__name__)

_NEAR_WHITE = 248


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 6:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return 255, 255, 255


def _clamp_rect(x1, y1, x2, y2, w, h):
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)


def sample_region_background(
    img: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    ring: int = 14,
) -> tuple[int, int, int]:
    """Sample background color from a ring around the text bbox on the original page."""
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
        corners = (
            (max(0, x - 1), max(0, y - 1)),
            (min(width - 1, x + w), max(0, y - 1)),
            (max(0, x - 1), min(height - 1, y + h)),
            (min(width - 1, x + w), min(height - 1, y + h)),
        )
        for cx, cy in corners:
            samples.append(px[cx, cy][:3])

    r = sum(s[0] for s in samples) // len(samples)
    g = sum(s[1] for s in samples) // len(samples)
    b = sum(s[2] for s in samples) // len(samples)
    if min(r, g, b) >= _NEAR_WHITE - 8:
        return 255, 255, 255
    return r, g, b


def resolve_block_background(
    original: Image.Image,
    block: TextBlock,
) -> tuple[int, int, int]:
    if block.style.background_color:
        rgb = _hex_to_rgb(block.style.background_color)
        if min(rgb) >= _NEAR_WHITE - 8:
            return 255, 255, 255
        return rgb
    x, y = int(block.bbox.x), int(block.bbox.y)
    w, h = int(block.bbox.width), int(block.bbox.height)
    return sample_region_background(original, x, y, w, h)


def _tight_text_rects(block: TextBlock, img_w: int, img_h: int) -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []
    raw = block.metadata.get("erase_boxes") or []
    fs = block.style.font_size or 12
    pad = max(2, int(fs * 0.22))
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        x, y, bw, bh = float(item[0]), float(item[1]), float(item[2]), float(item[3])
        rects.append(_clamp_rect(int(x - pad), int(y - pad), int(x + bw + pad), int(y + bh + pad), img_w, img_h))

    if not rects:
        x, y = int(block.bbox.x), int(block.bbox.y)
        w, h = int(block.bbox.width), int(block.bbox.height)
        inset_x = max(1, int(w * 0.02))
        inset_y = max(1, int(h * 0.06))
        rects.append(
            _clamp_rect(x + inset_x, y + inset_y, x + w - inset_x, y + h - inset_y, img_w, img_h)
        )
    return rects


def _cell_rects(block: TableBlock, img_w: int, img_h: int) -> list[tuple[int, int, int, int]]:
    inset = 4
    rects: list[tuple[int, int, int, int]] = []
    if block.cells:
        for cell in block.cells:
            x, y = int(cell.bbox.x), int(cell.bbox.y)
            w, h = int(cell.bbox.width), int(cell.bbox.height)
            rects.append(
                _clamp_rect(x + inset, y + inset, x + w - inset, y + h - inset, img_w, img_h)
            )
        return rects

    rows = block.rows or []
    if not rows:
        return rects
    num_cols = max(len(r) for r in rows)
    x0, y0 = int(block.bbox.x), int(block.bbox.y)
    w, h = int(block.bbox.width), int(block.bbox.height)
    cw, rh = w / max(num_cols, 1), h / max(len(rows), 1)
    for ri in range(len(rows)):
        for ci in range(num_cols):
            cx, cy = x0 + ci * cw, y0 + ri * rh
            rects.append(
                _clamp_rect(
                    int(cx + inset),
                    int(cy + inset),
                    int(cx + cw - inset),
                    int(cy + rh - inset),
                    img_w,
                    img_h,
                )
            )
    return rects


def _paint_pixels(img_arr, mask, color: tuple[int, int, int]) -> None:
    import numpy as np

    if mask is None:
        return
    m = np.asarray(mask) > 127
    img_arr[m] = color


def remove_text_pixels(
    canvas: Image.Image,
    original: Image.Image,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None = None,
) -> Image.Image:
    """
    Replace only text pixels with the sampled background color.
    Avoids bbox inpainting that causes blur and color smears.
    """
    try:
        import numpy as np
    except ImportError:
        return canvas

    orig = original.convert("RGB")
    out = canvas.convert("RGB")
    if out.size != orig.size:
        out = out.resize(orig.size, Image.Resampling.LANCZOS)

    arr = np.array(out, dtype=np.uint8)

    for block in sorted(text_blocks, key=lambda b: b.reading_order):
        bg = resolve_block_background(orig, block)
        rects = _tight_text_rects(block, orig.width, orig.height)
        mask = mask_from_image(orig, rects)
        if mask is not None:
            _paint_pixels(arr, mask, bg)
        else:
            from app.modules.reconstruction.background_fill import fill_rect_adaptive

            for x1, y1, x2, y2 in rects:
                filled = fill_rect_adaptive(orig, (x1, y1, x2, y2), bg)
                arr[y1:y2, x1:x2] = np.array(filled)[y1:y2, x1:x2]

    for block in table_blocks or []:
        for rect in _cell_rects(block, orig.width, orig.height):
            x1, y1, x2, y2 = rect
            bg = sample_region_background(orig, x1, y1, x2 - x1, y2 - y1)
            mask = mask_from_image(orig, [rect])
            if mask is not None:
                _paint_pixels(arr, mask, bg)
            else:
                arr[y1:y2, x1:x2] = bg

    return Image.fromarray(arr)


def build_text_free_background(
    original_raster: Path,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None = None,
    *,
    pdf_background: Image.Image | None = None,
) -> Image.Image:
    """Produce a background layer identical to the original except text pixels are removed."""
    if pdf_background is not None:
        base = pdf_background.convert("RGB")
        return remove_text_pixels(base, Image.open(original_raster).convert("RGB"), text_blocks, table_blocks)

    original = Image.open(original_raster).convert("RGB")
    return remove_text_pixels(original.copy(), original, text_blocks, table_blocks)


def scrub_rects_from_original(
    canvas: Image.Image,
    original: Image.Image,
    rects: list[tuple[int, int, int, int]],
) -> Image.Image:
    """Paint residual source-text pixels using colors sampled from the original page."""
    try:
        import numpy as np
    except ImportError:
        return canvas

    arr = np.array(canvas.convert("RGB"), dtype=np.uint8)
    orig = original.convert("RGB")
    for x1, y1, x2, y2 in rects:
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        bg = sample_region_background(orig, x1, y1, w, h, ring=16)
        mask = mask_from_image(orig, [(x1, y1, x2, y2)])
        if mask is not None:
            _paint_pixels(arr, mask, bg)
        else:
            arr[y1:y2, x1:x2] = bg
    return Image.fromarray(arr)


def scrub_block_before_draw(
    canvas: Image.Image,
    original: Image.Image,
    block: TextBlock,
) -> None:
    """Final per-block scrub on the composed page using original-page colors."""
    cleaned = remove_text_pixels(canvas, original, [block], [])
    canvas.paste(cleaned)


def scrub_table_before_draw(
    canvas: Image.Image,
    original: Image.Image,
    block: TableBlock,
) -> None:
    cleaned = remove_text_pixels(canvas, original, [], [block])
    canvas.paste(cleaned)
