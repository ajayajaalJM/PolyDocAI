from app.modules.preprocessing.style_analyzer import estimate_max_chars, infer_style


def test_infer_heading_style():
    style = infer_style((50, 50, 400, 36), "heading", 612)
    assert style.font_weight == "bold"
    assert style.font_size is not None and style.font_size > 12


def test_max_chars():
    chars = estimate_max_chars((0, 0, 200, 40), 12)
    assert chars > 20
