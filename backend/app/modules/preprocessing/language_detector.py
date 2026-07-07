"""Heuristic language detection from document text."""

from __future__ import annotations

import re

# ISO 639-1 codes
_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_CJK = re.compile(r"[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str, default: str = "en") -> str:
    """Return a best-guess ISO 639-1 language code from text sample."""
    if not text or not text.strip():
        return default

    sample = text[:8000]
    ar = len(_ARABIC.findall(sample))
    cy = len(_CYRILLIC.findall(sample))
    cjk = len(_CJK.findall(sample))
    lat = len(_LATIN.findall(sample))

    scores = {"ar": ar, "ru": cy, "zh": cjk, "en": lat}
    best = max(scores, key=scores.get)
    if scores[best] < 8:
        return default
    if best == "zh":
        if re.search(r"[\u3040-\u30FF]", sample):
            return "ja"
        if re.search(r"[\uAC00-\uD7AF]", sample):
            return "ko"
    return best


def detect_from_blocks(blocks: list, default: str = "en") -> str:
    texts = []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            texts.append(getattr(block, "original_text", ""))
        elif isinstance(block, dict) and block.get("type") == "text":
            texts.append(str(block.get("original_text", "")))
    return detect_language("\n".join(texts), default=default)
