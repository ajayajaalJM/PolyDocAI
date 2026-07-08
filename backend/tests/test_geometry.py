from app.core.geometry import expand_bbox, iou
from app.models.document import BoundingBox


def test_iou_identical_boxes():
    a = (0.0, 0.0, 100.0, 50.0)
    assert iou(a, a) == 1.0


def test_iou_no_overlap():
    assert iou((0, 0, 10, 10), (20, 20, 10, 10)) == 0.0


def test_iou_bounding_box_model():
    a = BoundingBox(x=0, y=0, width=100, height=100)
    b = BoundingBox(x=50, y=50, width=100, height=100)
    assert 0.0 < iou(a, b) < 1.0


def test_expand_bbox_clamps_to_page():
    bbox = expand_bbox((10, 10, 50, 50), padding=20, page_width=200, page_height=200)
    assert bbox[0] == 0.0
    assert bbox[1] == 0.0
