"""Infer text styles from OCR bounding boxes and page dimensions."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.models.document import TextBlock, TextStyle

RTL_LANGUAGES = {"ar", "fa", "ur", "he"}


def infer_style(
    bbox: tuple[float, float, float, float],
    layout_type: str,
    page_width: float,
    language: str | None = None,
) -> TextStyle:
    _, _, width, height = bbox
    font_size = max(8.0, min(height * 0.85, 72.0))

    if layout_type == "heading":
        font_size = min(font_size * 1.35, 48.0)
        font_weight = "bold"
    elif layout_type in ("header", "footer", "caption"):
        font_size = max(8.0, font_size * 0.85)
        font_weight = "normal"
    else:
        font_weight = "normal"

    center_x = bbox[0] + width / 2
    if center_x > page_width * 0.65:
        alignment = "right"
    elif center_x < page_width * 0.35:
        alignment = "left"
    else:
        alignment = "center" if layout_type == "heading" else "left"

    return TextStyle(
        font_size=round(font_size, 1),
        font_weight=font_weight,
        alignment=alignment,  # type: ignore[arg-type]
        line_height=round(font_size * 1.2, 1),
        direction="rtl" if language and language.lower()[:2] in RTL_LANGUAGES else "ltr",
    )


def style_from_pdf_span(span: dict, layout_type: str, page_width: float) -> TextStyle:
    bbox = span.get("bbox", (0, 0, 0, 0))
    if len(bbox) == 4:
        tb = (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
    else:
        tb = (0, 0, page_width, 12)
    style = infer_style(tb, layout_type, page_width)
    style.font_size = span.get("font_size", style.font_size)
    style.font_family = span.get("font_family", style.font_family)
    style.color = span.get("color", style.color)
    style.font_weight = span.get("font_weight", style.font_weight)
    style.font_style = span.get("font_style", "normal")  # type: ignore[assignment]
    return style


def infer_style_from_image(
    image_path: Path,
    bbox: tuple[float, float, float, float],
    layout_type: str,
    page_width: float,
    language: str | None = None,
) -> TextStyle:
    """Enhance heuristic style with pixel sampling from bbox crop."""
    style = infer_style(bbox, layout_type, page_width, language)
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            img_rgb = img.convert("RGB")
            x, y, w, h = [int(v) for v in bbox]
            x2 = min(img_rgb.width, x + max(w, 1))
            y2 = min(img_rgb.height, y + max(h, 1))
            x = max(0, x)
            y = max(0, y)
            if x2 <= x or y2 <= y:
                return style
            crop = img_rgb.crop((x, y, x2, y2))
            arr = np.array(crop)
            if arr.size == 0:
                return style

            gray = arr.mean(axis=2)
            bg_mask = gray > np.percentile(gray, 70)
            fg_mask = gray < np.percentile(gray, 30)
            if fg_mask.any():
                fg_pixels = arr[fg_mask]
                color = fg_pixels.mean(axis=0).astype(int)
                style.color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            if bg_mask.any():
                bg_pixels = arr[bg_mask]
                bg = bg_pixels.mean(axis=0).astype(int)
                style.background_color = f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}"

            # Bold heuristic: high stroke density in horizontal projection
            if gray.shape[0] > 4:
                row_var = gray.std(axis=1).mean()
                if row_var > 25 and layout_type != "caption":
                    style.font_weight = "bold"
    except Exception:
        pass
    return style


def apply_target_typography(block: TextBlock, target_lang: str) -> None:
    """Adjust block typography for the translated script (RTL mirroring, etc.)."""
    code = (target_lang or "").lower()[:2]
    if code not in RTL_LANGUAGES:
        return
    block.style.direction = "rtl"
    if block.style.alignment == "left":
        block.style.alignment = "right"
    elif block.style.alignment == "right":
        block.style.alignment = "left"


def estimate_max_chars(bbox: tuple[float, float, float, float], font_size: float) -> int:
    """Estimate character capacity for length-aware translation."""
    _, _, width, height = bbox
    chars_per_line = max(10, int(width / (font_size * 0.55)))
    lines = max(1, int(height / (font_size * 1.25)))
    return chars_per_line * lines


def enforce_max_length(text: str, max_chars: int | None, layout_type: str) -> str:
    if not max_chars or len(text) <= max_chars:
        return text
    if layout_type in ("heading", "header", "footer", "caption"):
        return text[: max(0, max_chars - 1)].rstrip() + "…"
    return text[:max_chars]
