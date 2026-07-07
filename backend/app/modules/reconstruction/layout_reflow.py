"""Expand text block boxes so translated content fits without shrinking to illegible sizes."""

from __future__ import annotations

from app.models.document import BoundingBox, TextBlock

_MAX_HEIGHT_SCALE = 2.8
_MIN_FONT_FLOOR = {
    "heading": 11.0,
    "header": 9.0,
    "footer": 8.0,
    "caption": 8.0,
    "paragraph": 7.0,
    "list": 7.0,
    "quote": 8.0,
    "sidebar": 7.0,
    "unknown": 7.0,
}


def min_font_size_for(block: TextBlock) -> float:
    return _MIN_FONT_FLOOR.get(block.layout_type, 7.0)


def estimate_line_count(text: str, box_width: float, font_size: float) -> int:
    chars_per_line = max(8.0, box_width / max(4.0, font_size * 0.52))
    words = max(1, len(text.split()))
    chars = max(1, len(text))
    by_chars = max(1, int(chars / chars_per_line))
    by_words = max(1, int(words / max(1.0, chars_per_line / 6.0)))
    return max(by_chars, by_words // 2)


def effective_compose_bbox(
    block: TextBlock,
    text: str,
    *,
    page_height: float,
    page_width: float,
) -> BoundingBox:
    """
    Grow block height (downward) when translation is longer than the original,
    keeping width fixed and staying inside the page.
    """
    orig = block.original_text or ""
    font_size = block.style.font_size or 12.0
    line_height = block.style.line_height or font_size * 1.2

    orig_lines = estimate_line_count(orig, block.bbox.width, font_size)
    new_lines = estimate_line_count(text, block.bbox.width, font_size)
    line_ratio = new_lines / max(1, orig_lines)
    char_ratio = len(text) / max(1, len(orig))
    growth = max(line_ratio, char_ratio * 0.85)
    growth = min(_MAX_HEIGHT_SCALE, max(1.0, growth))

    needed_h = new_lines * line_height + 6
    target_h = max(block.bbox.height, min(block.bbox.height * growth, needed_h))

    max_h = page_height - block.bbox.y - 4
    if block.bbox.x + block.bbox.width > page_width:
        pass
    target_h = min(target_h, max(block.bbox.height, max_h))

    return BoundingBox(
        x=block.bbox.x,
        y=block.bbox.y,
        width=block.bbox.width,
        height=target_h,
    )
