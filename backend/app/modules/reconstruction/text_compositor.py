"""Compose translated pages: erase original text regions, draw translated text in place."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont

from app.models.document import BoundingBox, TableBlock, TextBlock, TextStyle
from app.modules.reconstruction.font_resolver import load_pil_font
from app.modules.reconstruction.layout_reflow import effective_compose_bbox, min_font_size_for
from app.modules.reconstruction.script_fonts import needs_arabic_rendering, target_script
from app.modules.reconstruction.style_sync import sync_compose_style
from app.modules.reconstruction.text_mask import mask_from_image
from app.modules.reconstruction.text_residual import (
    detect_residual_regions,
    expand_rects,
    measure_page_residual_score,
)
from app.providers.fonts.manager import FontManager

logger = structlog.get_logger(__name__)

_ERASE_PAD = 12
_BORDER_RING = 12
_BBOX_EXPAND_X = 0.24
_BBOX_EXPAND_Y = 0.30
_CELL_ERASE_PAD = 4
_INPAINT_RADIUS = 7
_MASK_DILATE_ITERATIONS = 2
_REFINE_PASSES = 3
_MIN_COMPOSE_SIZE = 6

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 6:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return 0, 0, 0


def _clamp_rect(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    img_width: int,
    img_height: int,
) -> tuple[int, int, int, int]:
    return max(0, x1), max(0, y1), min(img_width, x2), min(img_height, y2)


def _bbox_to_rect(
    bbox: BoundingBox | tuple[float, float, float, float],
    img_width: int,
    img_height: int,
    *,
    pad: int = 0,
    expand_x: float = 0.0,
    expand_y: float = 0.0,
) -> tuple[int, int, int, int]:
    if isinstance(bbox, BoundingBox):
        x, y, w, h = bbox.x, bbox.y, bbox.width, bbox.height
    else:
        x, y, w, h = bbox
    extra_x = max(pad, w * expand_x)
    extra_y = max(pad, h * expand_y)
    return _clamp_rect(
        int(x - extra_x),
        int(y - extra_y),
        int(x + w + extra_x),
        int(y + h + extra_y),
        img_width,
        img_height,
    )


def _sample_border_background(
    img: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    ring: int = _BORDER_RING,
) -> tuple[int, int, int]:
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
    fs = block.style.font_size or 12
    extra = max(pad, int(fs * 0.8))
    return _bbox_to_rect(
        block.bbox,
        img_width,
        img_height,
        pad=extra,
        expand_x=_BBOX_EXPAND_X,
        expand_y=_BBOX_EXPAND_Y,
    )


def _metadata_erase_rects(
    block: TextBlock,
    img_width: int,
    img_height: int,
) -> list[tuple[int, int, int, int]]:
    raw_boxes = block.metadata.get("erase_boxes") or []
    rects: list[tuple[int, int, int, int]] = []
    fs = block.style.font_size or 12
    pad = max(4, int(fs * 0.4))
    for item in raw_boxes:
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        rects.append(
            _bbox_to_rect(
                (float(item[0]), float(item[1]), float(item[2]), float(item[3])),
                img_width,
                img_height,
                pad=pad,
                expand_x=0.10,
                expand_y=0.14,
            )
        )
    return rects


def _text_erase_rects(
    block: TextBlock,
    img_width: int,
    img_height: int,
) -> list[tuple[int, int, int, int]]:
    rects = _metadata_erase_rects(block, img_width, img_height)
    rects.append(_expanded_erase_rect(block, img_width, img_height))
    return rects


def _table_cell_erase_rects(
    block: TableBlock,
    img_width: int,
    img_height: int,
) -> list[tuple[int, int, int, int]]:
    border_inset = 3
    rects: list[tuple[int, int, int, int]] = []
    if block.cells:
        for cell in block.cells:
            fs = cell.style.font_size if cell.style and cell.style.font_size else 10
            pad = max(_CELL_ERASE_PAD, int(fs * 0.35))
            x1, y1, x2, y2 = _bbox_to_rect(
                cell.bbox,
                img_width,
                img_height,
                pad=pad,
                expand_x=0.05,
                expand_y=0.10,
            )
            rects.append(
                _clamp_rect(
                    x1 + border_inset,
                    y1 + border_inset,
                    x2 - border_inset,
                    y2 - border_inset,
                    img_width,
                    img_height,
                )
            )
        return rects

    rows = block.rows or []
    if not rows:
        return rects

    num_rows = len(rows)
    num_cols = max(len(row) for row in rows)
    if num_cols == 0:
        return rects

    x = int(block.bbox.x)
    y = int(block.bbox.y)
    w = int(block.bbox.width)
    h = int(block.bbox.height)
    col_widths = block.col_widths or [w / num_cols] * num_cols
    row_heights = block.row_heights or [h / max(num_rows, 1)] * num_rows

    cy = y
    for ri in range(num_rows):
        cx = x
        rh = row_heights[ri] if ri < len(row_heights) else h / num_rows
        for ci in range(num_cols):
            cw = col_widths[ci] if ci < len(col_widths) else w / num_cols
            rects.append(
                _clamp_rect(
                    int(cx + border_inset),
                    int(cy + border_inset),
                    int(cx + cw - border_inset),
                    int(cy + rh - border_inset),
                    img_width,
                    img_height,
                )
            )
            cx += cw
        cy += rh
    return rects


def _apply_solid_fills(
    draw: ImageDraw.ImageDraw,
    rects: list[tuple[int, int, int, int]],
    fill_rgb: tuple[int, int, int],
) -> None:
    for x1, y1, x2, y2 in rects:
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle([x1, y1, x2, y2], fill=fill_rgb)


def _block_erase_rects(block: TextBlock | TableBlock, img_width: int, img_height: int) -> list[tuple[int, int, int, int]]:
    if isinstance(block, TextBlock):
        return _text_erase_rects(block, img_width, img_height)
    return _table_cell_erase_rects(block, img_width, img_height)


def _uniform_fill_color(img: Image.Image, x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int] | None:
    """If the region background is uniform (e.g. white box), return fill color."""
    try:
        import numpy as np
    except ImportError:
        return None

    crop = img.crop((x1, y1, x2, y2)).convert("RGB")
    arr = np.array(crop, dtype=np.float32)
    if arr.size == 0:
        return None
    std = float(arr.std())
    if std < 12.0:
        med = np.median(arr, axis=(0, 1))
        return int(med[0]), int(med[1]), int(med[2])
    return None


def _build_combined_mask(
    img: Image.Image,
    mask_rects: list[tuple[int, int, int, int]],
    *,
    aggressive: bool = False,
) -> Image.Image | None:
    if not mask_rects:
        return None

    mask = Image.new("L", img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    for x1, y1, x2, y2 in mask_rects:
        if x2 <= x1 or y2 <= y1:
            continue
        mask_draw.rectangle([x1, y1, x2, y2], fill=255)

    try:
        import cv2
        import numpy as np

        mask_arr = np.array(mask)
        pixel_mask = mask_from_image(img, mask_rects)
        if pixel_mask is not None:
            mask_arr = np.maximum(mask_arr, np.asarray(pixel_mask))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        iterations = _MASK_DILATE_ITERATIONS + (2 if aggressive else 0)
        mask_arr = cv2.dilate(mask_arr, kernel, iterations=iterations)
        return Image.fromarray(mask_arr)
    except Exception:
        return mask


def _inpaint_masked_regions(img: Image.Image, mask: Image.Image) -> Image.Image:
    if not mask.getbbox():
        return img
    try:
        import cv2
        import numpy as np

        img_arr = np.array(img)
        mask_arr = np.array(mask)
        inpainted = cv2.inpaint(img_arr, mask_arr, _INPAINT_RADIUS, cv2.INPAINT_NS)
        return Image.fromarray(inpainted)
    except Exception as exc:
        logger.warning("inpaint_failed", error=str(exc))
        draw = ImageDraw.Draw(img)
        for y in range(0, mask.height, 4):
            for x in range(0, mask.width, 4):
                if mask.getpixel((x, y)) < 128:
                    continue
                fill = _sample_border_background(img, x, y, 4, 4, ring=10)
                draw.rectangle([x, y, min(mask.width, x + 4), min(mask.height, y + 4)], fill=fill)
        return img


def _refine_strip(
    page_raster: Path,
    img: Image.Image,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None,
    *,
    refine_passes: int = _REFINE_PASSES,
    aggressive: bool = False,
) -> Image.Image:
    """Iteratively erase residual source-text pixels without bbox inpainting."""
    from app.modules.reconstruction.background_builder import (
        build_text_free_background,
        scrub_rects_from_original,
    )

    original = Image.open(page_raster).convert("RGB")
    all_blocks: list[TextBlock | TableBlock] = list(text_blocks) + list(table_blocks or [])
    threshold = 0.22 if aggressive else 0.30

    for pass_idx in range(refine_passes):
        residual = detect_residual_regions(
            img,
            all_blocks,
            _block_erase_rects,
            threshold=threshold,
        )
        if not residual:
            break
        pad = 10 if aggressive else 5
        residual = expand_rects(residual, img.width, img.height, pad=pad + pass_idx * 2)
        img = scrub_rects_from_original(img, original, residual)

    if aggressive:
        img = build_text_free_background(
            page_raster,
            text_blocks,
            table_blocks,
            pdf_background=img,
        )
    return img


def strip_text_from_page(
    page_raster: Path,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None = None,
    *,
    background: Image.Image | None = None,
    refine_passes: int = _REFINE_PASSES,
    aggressive: bool = False,
) -> Image.Image:
    """Return page raster with text/table regions erased (graphics preserved)."""
    from app.modules.reconstruction.background_builder import build_text_free_background

    img = build_text_free_background(
        page_raster,
        text_blocks,
        table_blocks,
        pdf_background=background,
    )
    if refine_passes > 0:
        img = _refine_strip(
            page_raster,
            img,
            text_blocks,
            table_blocks,
            refine_passes=refine_passes,
            aggressive=aggressive,
        )
    return img


def measure_strip_quality(
    img: Image.Image,
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock] | None = None,
) -> float:
    """0 = clean background, 1 = significant source text remaining."""
    blocks: list[TextBlock | TableBlock] = list(text_blocks) + list(table_blocks or [])
    return measure_page_residual_score(img, blocks, _block_erase_rects)


def _scrub_block_region(
    img: Image.Image,
    block: TextBlock,
    *,
    original: Image.Image | None = None,
    aggressive: bool = False,
) -> None:
    """Paint out the source-text region immediately before drawing the translation."""
    if original is not None:
        from app.modules.reconstruction.background_builder import scrub_block_before_draw

        scrub_block_before_draw(img, original, block)
        return

    rects = _text_erase_rects(block, img.width, img.height)
    if aggressive:
        rects = [
            (
                max(0, x1 - 4),
                max(0, y1 - 4),
                min(img.width, x2 + 4),
                min(img.height, y2 + 4),
            )
            for x1, y1, x2, y2 in rects
        ]
    draw = ImageDraw.Draw(img)
    for rect in rects:
        if block.style.background_color:
            _apply_solid_fills(draw, [rect], _hex_to_rgb(block.style.background_color))
            continue
        solid = _uniform_fill_color(img, *rect)
        if solid:
            _apply_solid_fills(draw, [rect], solid)


def _scrub_table_cells(
    img: Image.Image,
    block: TableBlock,
    *,
    original: Image.Image | None = None,
) -> None:
    if original is not None:
        from app.modules.reconstruction.background_builder import scrub_table_before_draw

        scrub_table_before_draw(img, original, block)
        return

    rects = _table_cell_erase_rects(block, img.width, img.height)
    draw = ImageDraw.Draw(img)
    for rect in rects:
        solid = _uniform_fill_color(img, *rect)
        if solid:
            _apply_solid_fills(draw, [rect], solid)


def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _use_arabic(text: str, block: TextBlock, target_language: str | None) -> bool:
    return needs_arabic_rendering(text, target_language, block.style)


def _wrap_lines(
    text: str,
    font: ImageFont.ImageFont,
    max_width: float,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue

        if _is_cjk(paragraph):
            current = ""
            for ch in paragraph:
                if ch.isspace():
                    if current:
                        lines.append(current)
                        current = ""
                    continue
                trial = current + ch
                if draw.textlength(trial, font=font) <= max_width:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    current = ch
            if current:
                lines.append(current)
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
                if draw.textlength(word, font=font) > max_width:
                    chunk = ""
                    for ch in word:
                        trial_chunk = chunk + ch
                        if draw.textlength(trial_chunk, font=font) <= max_width:
                            chunk = trial_chunk
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = ch
                    current = chunk
                else:
                    current = word
        if current:
            lines.append(current)
    return lines or [""]


def _fit_font_size(
    text: str,
    font_size: float,
    block: TextBlock,
    max_width: float,
    max_height: float,
    line_height: float,
    draw: ImageDraw.ImageDraw,
    *,
    font_dirs: tuple[str, ...] = (),
    arabic: bool = False,
    cjk: bool = False,
) -> tuple[ImageFont.ImageFont, list[str], float]:
    size = font_size
    min_size = min_font_size_for(block)
    if block.style.font_size:
        min_size = max(min_size, block.style.font_size * 0.82)

    while size >= min_size:
        font = load_pil_font(
            int(round(size)),
            font_family=block.style.font_family,
            font_weight=block.style.font_weight,
            font_style=block.style.font_style,
            arabic=arabic,
            cjk=cjk,
            font_dirs=font_dirs,
        )
        lines = _wrap_lines(text, font, max_width, draw)
        block_height = len(lines) * line_height
        longest = max((draw.textlength(line, font=font) for line in lines if line), default=0)
        if block_height <= max_height + 2 and longest <= max_width + 1:
            return font, lines, size
        size -= 0.5

    font = load_pil_font(
        min_size,
        font_family=block.style.font_family,
        font_weight=block.style.font_weight,
        font_style=block.style.font_style,
        arabic=arabic,
        cjk=cjk,
        font_dirs=font_dirs,
    )
    return font, _wrap_lines(text, font, max_width, draw), float(min_size)


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    block: TextBlock,
    text: str,
    shape_fn,
    *,
    font_dirs: tuple[str, ...] = (),
    page_height: float,
    page_width: float,
    target_language: str | None = None,
    original: Image.Image | None = None,
) -> None:
    _scrub_block_region(img, block, original=original, aggressive=True)

    use_arabic = _use_arabic(text, block, target_language)
    use_cjk = target_script(target_language) == "cjk" or _is_cjk(text)
    direction = "rtl" if use_arabic else (block.style.direction or "ltr")
    text = shape_fn(text, direction)

    compose_bbox = effective_compose_bbox(
        block,
        text,
        page_height=page_height,
        page_width=page_width,
    )
    x = int(compose_bbox.x)
    y = int(compose_bbox.y)
    w = int(compose_bbox.width)
    h = int(compose_bbox.height)

    font_size = block.style.font_size or 12
    line_height = block.style.line_height or font_size * 1.2
    color = block.style.color or "#000000"
    fill = _hex_to_rgb(color)

    font, lines, _ = _fit_font_size(
        text,
        font_size,
        block,
        max(w - 4, 8),
        h,
        line_height,
        draw,
        font_dirs=font_dirs,
        arabic=use_arabic,
        cjk=use_cjk,
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
            tx = x + w - line_w - 1
        else:
            tx = x + 1
        ty = start_y + i * line_height
        draw.text((tx, ty), line, fill=fill, font=font)


def _draw_text_in_cell(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    text: str,
    cell_bbox: BoundingBox,
    *,
    font_size: float,
    font_weight: str | None,
    color: str,
    shape_fn,
    font_dirs: tuple[str, ...],
    target_language: str | None = None,
) -> None:
    use_arabic = _use_arabic(text, TextBlock(page_number=1, bbox=cell_bbox, original_text=text), target_language)
    use_cjk = _is_cjk(text)
    shaped = shape_fn(text, "rtl" if use_arabic else "ltr")
    x = int(cell_bbox.x) + 4
    y = int(cell_bbox.y) + 2
    w = int(cell_bbox.width) - 8
    h = int(cell_bbox.height) - 4
    if w <= 0 or h <= 0:
        return

    stub = TextBlock(
        page_number=1,
        bbox=cell_bbox,
        original_text=text,
        style=TextStyle(font_size=font_size, font_weight=font_weight, color=color),
    )
    line_height = font_size * 1.15
    font, lines, _ = _fit_font_size(
        shaped,
        font_size,
        stub,
        max(w, 8),
        h,
        line_height,
        draw,
        font_dirs=font_dirs,
        arabic=use_arabic,
        cjk=use_cjk,
    )
    fill = _hex_to_rgb(color)
    total_h = len(lines) * line_height
    start_y = y + max(0, (h - total_h) / 2)
    for i, line in enumerate(lines):
        if not line:
            continue
        draw.text((x, start_y + i * line_height), line, fill=fill, font=font)


def _draw_table_block(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    block: TableBlock,
    *,
    use_translated: bool,
    shape_fn,
    font_dirs: tuple[str, ...] = (),
    target_language: str | None = None,
    original: Image.Image | None = None,
) -> None:
    _scrub_table_cells(img, block, original=original)
    if block.cells:
        for cell in block.cells:
            if use_translated:
                text = cell.translated_text
                if not text or not str(text).strip():
                    continue
            else:
                text = cell.text
            if not str(text).strip():
                continue
            fs = cell.style.font_size if cell.style and cell.style.font_size else 10
            fw = cell.style.font_weight if cell.style else None
            color = cell.style.color if cell.style and cell.style.color else "#000000"
            _draw_text_in_cell(
                draw,
                img,
                str(text),
                cell.bbox,
                font_size=float(fs),
                font_weight=fw,
                color=color,
                shape_fn=shape_fn,
                font_dirs=font_dirs,
                target_language=target_language,
            )
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
    col_widths = block.col_widths or [w / num_cols] * num_cols
    row_heights = block.row_heights or [h / max(num_rows, 1)] * num_rows
    font_size = max(7, min(14, int(min(row_heights) * 0.45)))

    cy = y
    for ri, row in enumerate(rows):
        cx = x
        rh = row_heights[ri] if ri < len(row_heights) else h / num_rows
        for ci, cell in enumerate(row):
            cw = col_widths[ci] if ci < len(col_widths) else w / num_cols
            text = str(cell).strip()
            if text:
                cell_bbox = BoundingBox(x=cx, y=cy, width=cw, height=rh)
                _draw_text_in_cell(
                    draw,
                    img,
                    text,
                    cell_bbox,
                    font_size=float(font_size),
                    font_weight=None,
                    color="#000000",
                    shape_fn=shape_fn,
                    font_dirs=font_dirs,
                    target_language=target_language,
                )
            cx += cw
        cy += rh


def compose_translated_page(
    page_raster: Path,
    text_blocks: list[TextBlock],
    *,
    use_translated: bool = True,
    shape_fn,
    table_blocks: list[TableBlock] | None = None,
    background: Image.Image | None = None,
    font_dirs: tuple[str, ...] = (),
    target_language: str | None = None,
    original_raster: Path | None = None,
) -> Image.Image:
    """Rebuild page from stripped background + translated text (no original text layer)."""
    source_path = original_raster or page_raster
    original_img = Image.open(source_path).convert("RGB")

    img = (
        background.copy()
        if background is not None
        else strip_text_from_page(page_raster, text_blocks, table_blocks)
    )
    draw = ImageDraw.Draw(img)

    for block in sorted(text_blocks, key=lambda b: b.reading_order):
        if use_translated:
            content = block.translated_text
            if not content or not str(content).strip():
                continue
        else:
            content = block.original_text
        if not str(content).strip():
            continue
        draw_block = block.model_copy(deep=True)
        draw_block.style = sync_compose_style(
            block,
            source_path,
            target_language=target_language,
        )
        _draw_text_block(
            draw,
            img,
            draw_block,
            str(content),
            shape_fn,
            font_dirs=font_dirs,
            page_height=img.height,
            page_width=img.width,
            target_language=target_language,
            original=original_img,
        )

    for block in table_blocks or []:
        _draw_table_block(
            draw,
            img,
            block,
            use_translated=use_translated,
            shape_fn=shape_fn,
            font_dirs=font_dirs,
            target_language=target_language,
            original=original_img,
        )

    return img


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
