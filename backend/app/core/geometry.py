"""Shared geometry utilities for layout matching and region overlap."""

from __future__ import annotations

from app.models.document import BoundingBox


def bbox_tuple(bbox: BoundingBox | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(bbox, BoundingBox):
        return (bbox.x, bbox.y, bbox.width, bbox.height)
    return bbox


def iou(
    a: tuple[float, float, float, float] | BoundingBox,
    b: tuple[float, float, float, float] | BoundingBox,
) -> float:
    ax, ay, aw, ah = bbox_tuple(a)
    bx, by, bw, bh = bbox_tuple(b)
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def contains_point(
    bbox: tuple[float, float, float, float],
    x: float,
    y: float,
) -> bool:
    bx, by, bw, bh = bbox
    return bx <= x <= bx + bw and by <= y <= by + bh


def intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def expand_bbox(
    bbox: tuple[float, float, float, float],
    padding: float,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    x, y, w, h = bbox
    x = max(0.0, x - padding)
    y = max(0.0, y - padding)
    w = min(page_width - x, w + padding * 2)
    h = min(page_height - y, h + padding * 2)
    return (x, y, w, h)
