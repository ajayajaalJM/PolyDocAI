from __future__ import annotations

from app.modules.ocr.geometry import (
    dedupe_erase_boxes,
    group_detections_into_lines,
    group_lines_into_paragraphs,
    proportional_word_boxes,
)


def test_proportional_word_boxes_splits_line():
    boxes = proportional_word_boxes("Hello world", (10.0, 20.0, 100.0, 16.0))
    assert len(boxes) == 2
    assert boxes[0][0] == "Hello"


def test_group_lines_into_paragraphs_splits_long_runs():
    detections = [
        (f"line {i}", 0.95, (10.0, float(i * 18), 400.0, 14.0))
        for i in range(20)
    ]
    lines = group_detections_into_lines(detections)
    paragraphs = group_lines_into_paragraphs(lines)
    assert len(paragraphs) >= 2


def test_dedupe_erase_boxes():
    boxes = dedupe_erase_boxes([[1.0, 2.0, 10.0, 8.0], [1.1, 2.1, 10.0, 8.0], [50.0, 2.0, 10.0, 8.0]])
    assert len(boxes) == 2
