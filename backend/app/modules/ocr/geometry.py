"""OCR bounding-box geometry: line grouping, word splitting, deduplication."""

from __future__ import annotations

from app.modules.ocr.paddle_service import OCRLine, OCRParagraph, OCRWord

MAX_LINES_PER_PARAGRAPH = 10


def proportional_word_boxes(
    text: str,
    bbox: tuple[float, float, float, float],
) -> list[tuple[str, tuple[float, float, float, float]]]:
    x, y, w, h = bbox
    parts = [p for p in str(text).split() if p]
    if not parts:
        return []
    if len(parts) == 1:
        return [(parts[0], (x, y, w, h))]

    weights = [len(p) + 0.35 for p in parts[:-1]] + [len(parts[-1])]
    total = sum(weights)
    if total <= 0:
        return [(text.strip(), (x, y, w, h))]

    cx = x
    result: list[tuple[str, tuple[float, float, float, float]]] = []
    for part, weight in zip(parts, weights, strict=False):
        ww = w * (weight / total)
        result.append((part, (cx, y, ww, h)))
        cx += ww
    return result


def _y_center(bbox: tuple[float, float, float, float]) -> float:
    return bbox[1] + bbox[3] / 2


def _x_start(bbox: tuple[float, float, float, float]) -> float:
    return bbox[0]


def _merge_bboxes(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x1, y1, x2 - x1, y2 - y1)


def group_detections_into_lines(
    detections: list[tuple[str, float, tuple[float, float, float, float]]],
) -> list[list[tuple[str, float, tuple[float, float, float, float]]]]:
    if not detections:
        return []

    ordered = sorted(detections, key=lambda d: (_y_center(d[2]), _x_start(d[2])))
    heights = sorted(d[2][3] for d in ordered if d[2][3] > 0)
    median_h = heights[len(heights) // 2] if heights else 16.0
    line_tol = max(6.0, median_h * 0.55)

    lines: list[list[tuple[str, float, tuple[float, float, float, float]]]] = []
    current_line: list[tuple[str, float, tuple[float, float, float, float]]] = []
    current_y: float | None = None

    for item in ordered:
        yc = _y_center(item[2])
        if current_y is None or abs(yc - current_y) <= line_tol:
            current_line.append(item)
            current_y = yc if current_y is None else (current_y + yc) / 2
        else:
            if current_line:
                current_line.sort(key=lambda d: _x_start(d[2]))
                lines.append(current_line)
            current_line = [item]
            current_y = yc

    if current_line:
        current_line.sort(key=lambda d: _x_start(d[2]))
        lines.append(current_line)

    return lines


def group_lines_into_paragraphs(
    lines: list[list[tuple[str, float, tuple[float, float, float, float]]]],
) -> list[list[list[tuple[str, float, tuple[float, float, float, float]]]]]:
    if not lines:
        return []

    paragraphs: list[list[list[tuple[str, float, tuple[float, float, float, float]]]]] = []
    current: list[list[tuple[str, float, tuple[float, float, float, float]]]] = []
    prev_bottom: float | None = None
    prev_height: float = 16.0
    paragraph_top: float | None = None

    for line in lines:
        line_bbox = _merge_bboxes([d[2] for d in line])
        top = line_bbox[1]
        height = line_bbox[3]
        gap = (top - prev_bottom) if prev_bottom is not None else 0.0
        max_gap = max(prev_height, height) * 1.35

        force_break = False
        if current:
            if len(current) >= MAX_LINES_PER_PARAGRAPH:
                force_break = True
            elif paragraph_top is not None:
                span = (line_bbox[1] + line_bbox[3]) - paragraph_top
                if span > max(prev_height, height) * MAX_LINES_PER_PARAGRAPH * 1.1:
                    force_break = True

        if prev_bottom is not None and (gap > max_gap or force_break) and current:
            paragraphs.append(current)
            current = []
            paragraph_top = None

        if not current:
            paragraph_top = top
        current.append(line)
        prev_bottom = line_bbox[1] + line_bbox[3]
        prev_height = height

    if current:
        paragraphs.append(current)

    return paragraphs


def build_line_from_detections(
    detections: list[tuple[str, float, tuple[float, float, float, float]]],
) -> OCRLine:
    detections = sorted(detections, key=lambda d: _x_start(d[2]))
    text = " ".join(d[0].strip() for d in detections if d[0].strip())
    confidences = [d[1] for d in detections]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    line_bbox = _merge_bboxes([d[2] for d in detections])

    words: list[OCRWord] = []
    for det_text, det_conf, det_bbox in detections:
        subwords = proportional_word_boxes(det_text, det_bbox)
        if subwords:
            for word_text, word_bbox in subwords:
                words.append(OCRWord(text=word_text, confidence=det_conf, bbox=word_bbox))
        else:
            words.append(OCRWord(text=det_text, confidence=det_conf, bbox=det_bbox))

    if not words and text:
        for word_text, word_bbox in proportional_word_boxes(text, line_bbox):
            words.append(OCRWord(text=word_text, confidence=confidence, bbox=word_bbox))

    return OCRLine(text=text, confidence=confidence, bbox=line_bbox, words=words)


def build_paragraph_from_lines(lines: list[OCRLine], reading_order: int) -> OCRParagraph:
    text = "\n".join(line.text for line in lines if line.text.strip())
    confidences = [line.confidence for line in lines]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    bbox = _merge_bboxes([line.bbox for line in lines])
    return OCRParagraph(
        text=text.replace("\n", " ").strip(),
        confidence=confidence,
        bbox=bbox,
        lines=lines,
        reading_order=reading_order,
    )


def detections_to_paragraphs(
    detections: list[tuple[str, float, tuple[float, float, float, float]]],
) -> list[OCRParagraph]:
    line_groups = group_detections_into_lines(detections)
    paragraph_groups = group_lines_into_paragraphs(line_groups)
    paragraphs: list[OCRParagraph] = []
    for order, para_lines in enumerate(paragraph_groups):
        ocr_lines = [build_line_from_detections(line) for line in para_lines]
        if not ocr_lines:
            continue
        paragraphs.append(build_paragraph_from_lines(ocr_lines, order))
    return paragraphs


def dedupe_erase_boxes(boxes: list[list[float]], *, min_dist: float = 2.0) -> list[list[float]]:
    unique: list[list[float]] = []
    for box in boxes:
        if len(box) < 4:
            continue
        x, y, w, h = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        if w <= 0 or h <= 0:
            continue
        duplicate = False
        for ux, uy, uw, uh in unique:
            if abs(x - ux) < min_dist and abs(y - uy) < min_dist and abs(w - uw) < min_dist:
                duplicate = True
                break
        if not duplicate:
            unique.append([x, y, w, h])
    return unique


def word_erase_boxes_from_paragraph(para: OCRParagraph) -> list[list[float]]:
    boxes: list[list[float]] = []
    for line in para.lines:
        if line.bbox[2] > 0 and line.bbox[3] > 0:
            boxes.append([line.bbox[0], line.bbox[1], line.bbox[2], line.bbox[3]])
        if line.words:
            for word in line.words:
                if word.bbox[2] > 0 and word.bbox[3] > 0:
                    boxes.append([word.bbox[0], word.bbox[1], word.bbox[2], word.bbox[3]])
        elif line.bbox[2] > 0:
            for _text, wb in proportional_word_boxes(line.text, line.bbox):
                boxes.append([wb[0], wb[1], wb[2], wb[3]])
    if not boxes and para.bbox[2] > 0:
        boxes.append([para.bbox[0], para.bbox[1], para.bbox[2], para.bbox[3]])
        for _text, wb in proportional_word_boxes(para.text, para.bbox):
            boxes.append([wb[0], wb[1], wb[2], wb[3]])
    return dedupe_erase_boxes(boxes)
