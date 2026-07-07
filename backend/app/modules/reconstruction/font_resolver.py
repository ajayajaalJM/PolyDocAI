"""Resolve PIL font files from document-extracted fonts and system fallbacks."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import structlog
from PIL import ImageFont

from app.modules.reconstruction.script_fonts import (
    is_arabic_capable_font,
    parse_font_path,
    resolve_arabic_font_path,
)

logger = structlog.get_logger(__name__)

_SYSTEM_CANDIDATES: list[tuple[str, str]] = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Helvetica.ttc"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
]

_CJK_CANDIDATES: list[tuple[str, str]] = [
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc"),
    ("/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/STHeiti Light.ttc"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]

_FONT_EXT = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@lru_cache(maxsize=128)
def _index_font_dir(font_dir: str) -> tuple[tuple[str, str], ...]:
    root = Path(font_dir)
    if not root.is_dir():
        return ()
    entries: list[tuple[str, str]] = []
    for path in root.iterdir():
        if path.suffix.lower() not in _FONT_EXT:
            continue
        entries.append((_normalize_name(path.stem), str(path)))
    return tuple(entries)


def _load_truetype(path: str, size: int, *, font_weight: str | None = None) -> ImageFont.FreeTypeFont:
    base, index = parse_font_path(path)
    if base.endswith(".ttc"):
        idx = index if index is not None else (1 if font_weight == "bold" else 0)
        return ImageFont.truetype(base, size, index=idx)
    return ImageFont.truetype(base, size)


def resolve_font_path(
    *,
    font_family: str | None,
    font_weight: str | None = None,
    font_style: str | None = None,
    arabic: bool = False,
    cjk: bool = False,
    font_dirs: tuple[str, ...] = (),
) -> str | None:
    if arabic:
        prefer_serif = bool(font_family and any(k in font_family.lower() for k in ("serif", "times", "naskh")))
        return resolve_arabic_font_path(
            font_weight=font_weight,
            prefer_serif=prefer_serif,
            font_dirs=font_dirs,
        )

    bold = font_weight == "bold"
    want_italic = font_style == "italic"
    target = _normalize_name(font_family or "")

    for font_dir in font_dirs:
        for norm_name, path in _index_font_dir(font_dir):
            if target and target not in norm_name and norm_name not in target:
                continue
            if want_italic and "italic" not in norm_name and "oblique" not in norm_name:
                continue
            if bold and "bold" not in norm_name and "black" not in norm_name and not path.endswith(".ttc"):
                continue
            if os.path.isfile(path):
                return path

    candidates = _CJK_CANDIDATES if cjk else _SYSTEM_CANDIDATES
    for regular, bold_path in candidates:
        path = bold_path if bold and os.path.isfile(bold_path) else regular
        if os.path.isfile(path):
            return path
    return None


def load_pil_font(
    size: int,
    *,
    font_family: str | None = None,
    font_weight: str | None = None,
    font_style: str | None = None,
    arabic: bool = False,
    cjk: bool = False,
    font_dirs: tuple[str, ...] = (),
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(6, int(round(size)))
    path = resolve_font_path(
        font_family=font_family,
        font_weight=font_weight,
        font_style=font_style,
        arabic=arabic,
        cjk=cjk,
        font_dirs=font_dirs,
    )
    if path:
        try:
            return _load_truetype(path, size, font_weight=font_weight)
        except OSError as exc:
            logger.warning("font_load_failed", path=path, error=str(exc))
            if arabic:
                fallback = resolve_arabic_font_path(font_weight=font_weight, font_dirs=())
                if fallback and fallback != path:
                    try:
                        return _load_truetype(fallback, size, font_weight=font_weight)
                    except OSError:
                        pass

    if arabic:
        logger.error("arabic_font_unavailable")
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()
