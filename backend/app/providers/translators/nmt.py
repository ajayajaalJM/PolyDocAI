"""Neural machine translation via Argos Translate (offline)."""

from __future__ import annotations

import asyncio

import structlog

from app.models.document import TextBlock
from app.providers.translators.base import Glossary
from app.providers.translators.errors import TranslationError

logger = structlog.get_logger(__name__)

# Common language pairs supported by Argos out of the box
ARGOS_PAIRS: set[tuple[str, str]] = {
    ("en", "es"), ("es", "en"),
    ("en", "fr"), ("fr", "en"),
    ("en", "de"), ("de", "en"),
    ("en", "it"), ("it", "en"),
    ("en", "pt"), ("pt", "en"),
    ("en", "nl"), ("nl", "en"),
    ("en", "pl"), ("pl", "en"),
    ("en", "ru"), ("ru", "en"),
    ("en", "zh"), ("zh", "en"),
    ("en", "ja"), ("ja", "en"),
    ("en", "ar"), ("ar", "en"),
}


class NMTTranslator:
    name = "nmt"

    def __init__(self) -> None:
        self._installed = False

    async def is_available(self) -> bool:
        return await asyncio.to_thread(self._check_available)

    def _check_available(self) -> bool:
        try:
            import argostranslate.package  # noqa: F401
            import argostranslate.translate  # noqa: F401
            return True
        except ImportError:
            return False

    async def list_models(self) -> list[str]:
        if not await self.is_available():
            return []
        return [f"{a}-{b}" for a, b in sorted(ARGOS_PAIRS)]

    def _ensure_pair(self, src: str, tgt: str) -> None:
        import argostranslate.package
        import argostranslate.translate

        src, tgt = src.lower()[:2], tgt.lower()[:2]
        if (src, tgt) not in ARGOS_PAIRS:
            raise TranslationError(
                f"NMT does not support {src}→{tgt}. Use LLM or DeepL provider.",
                provider=self.name,
            )
        installed = argostranslate.translate.get_installed_languages()
        codes = {lang.code for lang in installed}
        if src not in codes or tgt not in codes:
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            pkg = next(
                (p for p in available if p.from_code == src and p.to_code == tgt),
                None,
            )
            if pkg is None:
                raise TranslationError(
                    f"No Argos package for {src}→{tgt}",
                    provider=self.name,
                )
            download_path = pkg.download()
            argostranslate.package.install_from_path(download_path)

    def _translate_text(self, text: str, src: str, tgt: str, glossary: Glossary) -> str:
        import argostranslate.translate

        self._ensure_pair(src, tgt)
        wrapped, mapping = glossary.wrap_terms(text)
        result = argostranslate.translate.translate(wrapped, src[:2], tgt[:2])
        return glossary.unwrap_terms(result, mapping)

    async def translate_blocks(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
        all_blocks: list[TextBlock] | None = None,
        **_: object,
    ) -> tuple[list[TextBlock], int]:
        glossary = glossary or Glossary()
        failures = 0
        for block in blocks:
            try:
                block.translated_text = await asyncio.to_thread(
                    self._translate_text,
                    block.original_text,
                    source_lang,
                    target_lang,
                    glossary,
                )
            except Exception as exc:
                logger.warning("nmt_block_failed", block_id=block.id, error=str(exc))
                block.translated_text = block.original_text
                failures += 1
        return blocks, failures

    async def translate_text(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
    ) -> str:
        glossary = glossary or Glossary()
        return await asyncio.to_thread(
            self._translate_text, text, source_lang, target_lang, glossary
        )
