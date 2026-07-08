from pathlib import Path

from app.modules.reconstruction.font_resolver import load_pil_font, resolve_font_path
from app.modules.reconstruction.script_fonts import apply_target_typography, map_font_family_for_target
from app.models.document import BoundingBox, TextBlock, TextStyle
from PIL import Image, ImageDraw
import arabic_reshaper
from bidi.algorithm import get_display


def test_arabic_font_skips_embedded_latin():
    path = resolve_font_path(
        font_family="Arial",
        font_weight="normal",
        arabic=True,
        font_dirs=("/tmp/testfonts",),
    )
    assert path is not None
    assert "Arial.ttf" not in path or "Unicode" in path or "Geeza" in path or "Naskh" in path


def _sample_latin_font() -> bytes:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        p = Path(path)
        if p.exists():
            return p.read_bytes()
    raise FileNotFoundError("No sample Latin font found for test")


def test_arabic_renders_not_tofu(tmp_path):
    latin = tmp_path / "Arial.ttf"
    latin.write_bytes(_sample_latin_font())

    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=0, y=0, width=100, height=30),
        reading_order=0,
        original_text="Hello",
        style=TextStyle(font_family="Arial", font_size=14),
    )
    apply_target_typography(block, "ar")
    assert block.style.direction == "rtl"

    font = load_pil_font(
        24,
        font_family=block.style.font_family,
        font_weight=block.style.font_weight,
        arabic=True,
        font_dirs=(str(tmp_path),),
    )
    text = get_display(arabic_reshaper.reshape("مرحبا بالعالم"))
    img = Image.new("RGB", (240, 60), "white")
    draw = ImageDraw.Draw(img)
    draw.text((5, 10), text, fill="#222222", font=font)
    bbox = draw.textbbox((5, 10), text, font=font)
    assert bbox[2] - bbox[0] > 80


def test_map_font_family_for_arabic():
    assert "Naskh" in (map_font_family_for_target("Times-Roman", "ar") or "")
    assert "Geeza" in (map_font_family_for_target("Arial", "ar") or "")
