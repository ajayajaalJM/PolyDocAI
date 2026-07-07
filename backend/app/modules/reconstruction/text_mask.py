"""Detect text pixels inside OCR/PDF bounding boxes for precise removal."""

from __future__ import annotations

from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


def _clamp_rect(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    return max(0, x1), max(0, y1), min(width, x2), min(height, y2)


def build_text_pixel_mask(
    img_width: int,
    img_height: int,
    rects: Iterable[tuple[int, int, int, int]],
    *,
    rgb_bytes: bytes | None = None,
) -> "object | None":
    """
    Build a binary mask of likely text pixels inside the given rectangles.
    Uses adaptive thresholding per region so anti-aliased glyphs are captured.
    """
    rects = [r for r in rects if r[2] > r[0] and r[3] > r[1]]
    if not rects:
        return None

    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return None

    if rgb_bytes is None:
        return None

    arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape((img_height, img_width, 3))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    full_mask = np.zeros(gray.shape, dtype=np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    for x1, y1, x2, y2 in rects:
        roi = gray[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        bg = float(np.median(roi))
        if bg >= 128:
            _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        binary = cv2.dilate(binary, kernel, iterations=1)
        full_mask[y1:y2, x1:x2] = cv2.bitwise_or(full_mask[y1:y2, x1:x2], binary)

    if not full_mask.any():
        return None
    return full_mask


def merge_rect_mask_with_pixel_mask(
    img_size: tuple[int, int],
    rect_mask: "object",
    pixel_mask: "object | None",
) -> "object":
    import numpy as np

    if pixel_mask is None:
        return rect_mask
    return np.maximum(np.asarray(rect_mask), np.asarray(pixel_mask))


def mask_from_image(
    img: "Image.Image",
    rects: Iterable[tuple[int, int, int, int]],
) -> "object | None":
    from PIL import Image

    if not isinstance(img, Image.Image):
        return None
    rgb = img.convert("RGB")
    w, h = rgb.size
    pixel_mask = build_text_pixel_mask(w, h, rects, rgb_bytes=rgb.tobytes())
    if pixel_mask is None:
        return None
    return pixel_mask
