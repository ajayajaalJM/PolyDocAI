from __future__ import annotations

import re
import structlog

logger = structlog.get_logger(__name__)

FONT_FALLBACKS: dict[str, list[str]] = {
    "latin": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
    "arabic": ["DecoType Naskh", "Arial Unicode MS", "Arial", "Tahoma", "Noto Naskh Arabic"],
    "spanish": ["Helvetica", "Arial", "DejaVu Sans"],
    "italian": ["Helvetica", "Times-Roman", "DejaVu Sans"],
}

ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
RTL_LANGUAGES = {"ar", "fa", "ur", "he"}


class FontManager:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def resolve(self, requested: str | None, language: str | None = None) -> str:
        if requested and requested in self._cache:
            return self._cache[requested]
        script = self._detect_script(language)
        fallbacks = FONT_FALLBACKS.get(script, FONT_FALLBACKS["latin"])
        resolved = requested if requested else fallbacks[0]
        if requested:
            self._cache[requested] = resolved
        return resolved

    @staticmethod
    def _detect_script(language: str | None) -> str:
        if not language:
            return "latin"
        lang = language.lower()
        if lang in ("ar", "arabic", "fa", "ur", "he"):
            return "arabic"
        if lang in ("es", "spanish"):
            return "spanish"
        if lang in ("it", "italian"):
            return "italian"
        return "latin"

    @staticmethod
    def contains_arabic(text: str) -> bool:
        return bool(ARABIC_SCRIPT_RE.search(text))

    @staticmethod
    def is_rtl_language(language: str | None) -> bool:
        return (language or "").lower()[:2] in RTL_LANGUAGES

    def shape_text(self, text: str, direction: str = "ltr") -> str:
        needs_rtl = direction == "rtl" or self.contains_arabic(text)
        if not needs_rtl:
            return text
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display

            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except ImportError:
            logger.warning("rtl_shaping_unavailable")
            return text
