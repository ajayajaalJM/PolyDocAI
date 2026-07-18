"""Adaptive background fill — solid color vs OpenCV inpaint."""

from __future__ import annotations

from PIL import Image


def _ring_variance(img: Image.Image, x: int, y: int, w: int, h: int, ring: int = 12) -> float:
    try:
        import numpy as np
    except ImportError:
        return 0.0

    gray = np.array(img.convert("L"))
    height, width = gray.shape
    ox1 = max(0, x - ring)
    oy1 = max(0, y - ring)
    ox2 = min(width, x + w + ring)
    oy2 = min(height, y + h + ring)
    ix1, iy1, ix2, iy2 = x, y, min(width, x + w), min(height, y + h)

    samples = []
    for py in range(oy1, oy2):
        for px in range(ox1, ox2):
            if ix1 <= px < ix2 and iy1 <= py < iy2:
                continue
            samples.append(float(gray[py, px]))
    if len(samples) < 8:
        return 0.0
    return float(np.std(samples))


def fill_rect_adaptive(
    img: Image.Image,
    rect: tuple[int, int, int, int],
    solid_color: tuple[int, int, int],
    *,
    variance_threshold: float = 18.0,
) -> Image.Image:
    """Use inpaint when background is non-uniform (photos/gradients)."""
    x1, y1, x2, y2 = rect
    w, h = x2 - x1, y2 - y1
    if w <= 2 or h <= 2:
        return img

    variance = _ring_variance(img, x1, y1, w, h)
    if variance < variance_threshold:
        out = img.copy()
        from PIL import ImageDraw

        draw = ImageDraw.Draw(out)
        draw.rectangle([x1, y1, x2, y2], fill=solid_color)
        return out

    try:
        import cv2
        import numpy as np
    except ImportError:
        out = img.copy()
        from PIL import ImageDraw

        draw = ImageDraw.Draw(out)
        draw.rectangle([x1, y1, x2, y2], fill=solid_color)
        return out

    arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    mask = np.zeros(arr.shape[:2], dtype=np.uint8)
    mask[y1:y2, x1:x2] = 255
    inpainted = cv2.inpaint(arr, mask, 3, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))
