from __future__ import annotations

import re
from typing import Protocol

from app.models.document import TextBlock


class Glossary:
    """Terminology injection for consistent translations."""

    def __init__(self, entries: dict[str, str] | None = None) -> None:
        self.entries = entries or {}

    def wrap_terms(self, text: str) -> tuple[str, dict[str, str]]:
        if not self.entries:
            return text, {}
        mapping: dict[str, str] = {}
        counter = 0
        result = text
        for term, translation in sorted(self.entries.items(), key=lambda x: -len(x[0])):
            if not term or term not in result:
                continue
            key = f"__GLOSS_{counter}__"
            mapping[key] = translation
            result = result.replace(term, key)
            counter += 1
        return result, mapping

    def unwrap_terms(self, text: str, mapping: dict[str, str]) -> str:
        for key, val in mapping.items():
            text = text.replace(key, val)
        return text

    def prompt_hint(self) -> str:
        if not self.entries:
            return ""
        pairs = ", ".join(f'"{k}" → "{v}"' for k, v in list(self.entries.items())[:20])
        return f"Use these exact translations for terms: {pairs}."


class Translator(Protocol):
    @property
    def name(self) -> str: ...

    async def is_available(self) -> bool: ...

    async def list_models(self) -> list[str]: ...

    async def translate_blocks(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
    ) -> tuple[list[TextBlock], int]: ...

    async def translate_text(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
    ) -> str: ...
