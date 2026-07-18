"""Sample font metrics from word boxes on page raster."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.models.document import TextBlock, TextStyle


def enrich_style_from_word_boxes(
    block: TextBlock,
    image_path: Path,
    *,
    page_width: float | None = None,
) -> TextStyle:
    """Refine font size and color from erase boxes on the page image."""
    style = block.style.model_copy(deep=True)
    boxes = block.metadata.get("erase_boxes") or []
    if not boxes:
        return style

    heights: list[float] = []
    colors: list[tuple[int, int, int]] = []

    with Image.open(image_path) as img:
        px = img.load()
        w, h = img.size
        for box in boxes:
            if len(box) < 4:
                continue
            x, y, bw, bh = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            if bh > 2:
                heights.append(bh)
            ix = int(max(0, min(w - 1, x + bw * 0.5)))
            iy = int(max(0, min(h - 1, y + bh * 0.5)))
            colors.append(px[ix, iy][:3])

    if heights:
        avg_h = sum(heights) / len(heights)
        style.font_size = round(max(7.0, min(72.0, avg_h * 0.85)), 1)

    if colors:
        r = sum(c[0] for c in colors) // len(colors)
        g = sum(c[1] for c in colors) // len(colors)
        b = sum(c[2] for c in colors) // len(colors)
        style.color = f"#{r:02x}{g:02x}{b:02x}"

    if page_width and block.bbox.width > page_width * 0.55:
        style.alignment = "center"
    elif page_width and block.bbox.x + block.bbox.width > page_width * 0.65:
        style.alignment = "right"

    return style
