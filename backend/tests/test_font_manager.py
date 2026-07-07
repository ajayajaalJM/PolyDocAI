from app.providers.fonts.manager import FontManager


def test_font_manager_latin_default():
    fm = FontManager()
    font = fm.resolve(None, "en")
    assert font == "Helvetica"


def test_font_manager_arabic_script():
    fm = FontManager()
    font = fm.resolve(None, "ar")
    assert font == "DecoType Naskh"


def test_rtl_shape_passthrough():
    fm = FontManager()
    assert fm.shape_text("hello", "ltr") == "hello"
