"""Detect leftover ink (source text) after stripping so we can refine removal."""

from __future__ import annotations

from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)

_DARK_DELTA = 22
_MIN_DARK_RATIO = 0.012
_MIN_EDGE_DENSITY = 0.025

BlockRectFn = Callable[[object, int, int], list[tuple[int, int, int, int]]]


def _rect_area(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(0, x2 - x1) * max(0, y2 - y1)


def _ink_score_in_rect(gray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Return 0..1 score — higher means more text-like ink remains."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return 0.0

    h, w = gray.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return 0.0

    roi = gray[y1:y2, x1:x2]
    ring = max(2, min(8, min(roi.shape) // 6))
    border_samples = np.concatenate(
        [
            roi[:ring, :].reshape(-1),
            roi[-ring:, :].reshape(-1),
            roi[:, :ring].reshape(-1),
            roi[:, -ring:].reshape(-1),
        ]
    )
    bg = float(np.median(border_samples))
    inner = roi[ring:-ring, ring:-ring] if roi.shape[0] > ring * 2 and roi.shape[1] > ring * 2 else roi
    if inner.size == 0:
        return 0.0

    if bg >= 128:
        dark = inner < (bg - _DARK_DELTA)
    else:
        dark = inner > (bg + _DARK_DELTA)

    dark_ratio = float(np.mean(dark))
    edges = cv2.Canny(inner, 50, 150)
    edge_density = float(np.mean(edges > 0))

    score = max(dark_ratio / _MIN_DARK_RATIO, edge_density / _MIN_EDGE_DENSITY)
    return min(1.0, score)


def detect_residual_regions(
    img: object,
    blocks: list,
    rect_fn: BlockRectFn,
    *,
    threshold: float = 0.35,
) -> list[tuple[int, int, int, int]]:
    """Find block regions that still contain visible text strokes."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return []

    if isinstance(img, Image.Image):
        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        width, height = img.size
    else:
        gray = img
        height, width = gray.shape

    residual: list[tuple[int, int, int, int]] = []
    for block in blocks:
        for rect in rect_fn(block, width, height):
            score = _ink_score_in_rect(gray, *rect)
            if score >= threshold:
                residual.append(rect)
    return residual


def measure_page_residual_score(
    img: object,
    blocks: list,
    rect_fn: BlockRectFn,
) -> float:
    """Aggregate residual ink score (0 = clean, 1 = heavy bleed)."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return 0.0

    if isinstance(img, Image.Image):
        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        width, height = img.size
    else:
        gray = img
        height, width = gray.shape

    scores: list[float] = []
    weights: list[int] = []

    for block in blocks:
        for x1, y1, x2, y2 in rect_fn(block, width, height):
            score = _ink_score_in_rect(gray, x1, y1, x2, y2)
            scores.append(score)
            weights.append(max(1, _rect_area(x1, y1, x2, y2)))

    if not scores:
        return 0.0
    return sum(s * w for s, w in zip(scores, weights, strict=False)) / sum(weights)


def expand_rects(
    rects: list[tuple[int, int, int, int]],
    img_width: int,
    img_height: int,
    *,
    pad: int = 6,
) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in rects:
        out.append(
            (
                max(0, x1 - pad),
                max(0, y1 - pad),
                min(img_width, x2 + pad),
                min(img_height, y2 + pad),
            )
        )
    return out
