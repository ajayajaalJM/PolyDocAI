"""Script-aware font selection for translated document reconstruction."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.models.document import TextBlock
from app.providers.fonts.manager import FontManager

RTL_LANGUAGES = {"ar", "fa", "ur", "he"}

_ARABIC_FONT_MARKERS = (
    "arabic",
    "naskh",
    "geeza",
    "unicode",
    "trad",
    "kufi",
    "din",
    "alnile",
    "decotype",
    "noto",
    "amiri",
    "scheherazade",
)

_LATIN_FONT_MARKERS = (
    "arial",
    "helvetica",
    "times",
    "courier",
    "calibri",
    "cambria",
    "georgia",
    "verdana",
    "liberation",
    "dejavu",
    "roboto",
    "inter",
    "garamond",
    "palatino",
    "avenir",
    "futura",
)

ARABIC_FONT_PATHS: list[tuple[str, str | None]] = [
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
    ("/System/Library/Fonts/GeezaPro.ttc", "0"),
    ("/System/Library/Fonts/GeezaPro.ttc", "1"),
    ("/System/Library/Fonts/Supplemental/DecoTypeNaskh.ttc", "0"),
    ("/System/Library/Fonts/Supplemental/DecoTypeNaskh.ttc", "1"),
    ("/System/Library/Fonts/Supplemental/Al Nile.ttc", "0"),
    ("/Library/Fonts/Arial Unicode.ttf", None),
    ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf", None),
    ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf", None),
    ("/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf", None),
    ("/usr/share/fonts/opentype/noto/NotoNaskhArabic-Bold.ttf", None),
]

_BUNDLED_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def target_script(target_language: str | None) -> str:
    code = (target_language or "").lower()[:2]
    if code in RTL_LANGUAGES:
        return "arabic"
    if code in ("zh", "ja", "ko"):
        return "cjk"
    return "latin"


def needs_arabic_rendering(text: str, target_language: str | None, style) -> bool:
    if FontManager.contains_arabic(text):
        return True
    if style and getattr(style, "direction", None) == "rtl":
        return True
    return target_script(target_language) == "arabic"


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_arabic_capable_font(path: str, stem: str | None = None) -> bool:
    name = _normalize(stem or Path(path).stem)
    return any(marker in name for marker in _ARABIC_FONT_MARKERS)


def is_latin_only_font(path: str, stem: str | None = None) -> bool:
    name = _normalize(stem or Path(path).stem)
    if is_arabic_capable_font(path, name):
        return False
    return any(marker in name for marker in _LATIN_FONT_MARKERS)


def map_font_family_for_target(
    original_family: str | None,
    target_language: str | None,
    font_weight: str | None = None,
) -> str | None:
    script = target_script(target_language)
    if script == "latin":
        return original_family

    weight = font_weight or "normal"
    family = (original_family or "").lower()

    if script == "arabic":
        if any(k in family for k in ("naskh", "trad", "serif", "times", "georgia", "garamond")):
            return "DecoType Naskh" if weight != "bold" else "DecoType Naskh Bold"
        if "courier" in family or "mono" in family:
            return "Arial Unicode MS"
        return "Geeza Pro" if weight != "bold" else "Geeza Pro Bold"

    return original_family


def apply_target_typography(block: TextBlock, target_lang: str) -> None:
    code = (target_lang or "").lower()[:2]
    if code not in RTL_LANGUAGES:
        return

    block.style.direction = "rtl"
    if block.style.alignment == "left":
        block.style.alignment = "right"
    elif block.style.alignment == "right":
        block.style.alignment = "left"

    block.style.font_family = map_font_family_for_target(
        block.style.font_family,
        target_lang,
        block.style.font_weight,
    )


def resolve_arabic_font_path(
    *,
    font_weight: str | None = None,
    prefer_serif: bool = False,
    font_dirs: tuple[str, ...] = (),
) -> str | None:
    bold = font_weight == "bold"

    for font_dir in font_dirs:
        root = Path(font_dir)
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            if not is_arabic_capable_font(str(path)):
                continue
            if bold and "bold" not in _normalize(path.stem) and path.suffix.lower() != ".ttc":
                continue
            return str(path)

    ordered = list(ARABIC_FONT_PATHS)
    if prefer_serif:
        ordered = sorted(
            ordered,
            key=lambda item: 0 if "naskh" in item[0].lower() or "decotype" in item[0].lower() else 1,
        )

    for path, index in ordered:
        if bold and "Bold" in path and "GeezaPro" not in path and "DecoType" not in path:
            pass
        elif bold and path.endswith("Regular.ttf"):
            continue
        elif not bold and "Bold" in path and "GeezaPro" not in path and "DecoType" not in path:
            continue
        if os.path.isfile(path):
            return path if index is None else f"{path}#{index}"

    bundled = _BUNDLED_DIR / ("NotoNaskhArabic-Bold.ttf" if bold else "NotoNaskhArabic-Regular.ttf")
    if bundled.is_file():
        return str(bundled)
    return None


def parse_font_path(path: str) -> tuple[str, int | None]:
    if "#" in path:
        base, idx = path.rsplit("#", 1)
        return base, int(idx)
    return path, None
