"""DeepL cloud translation provider."""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.models.document import TextBlock
from app.providers.translators.base import Glossary
from app.providers.translators.errors import TranslationError

logger = structlog.get_logger(__name__)

DEEPL_FREE_URL = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO_URL = "https://api.deepl.com/v2/translate"


class DeepLTranslator:
    name = "deepl"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.strip()
        self._base_url = DEEPL_FREE_URL if self._api_key.endswith(":fx") else DEEPL_PRO_URL

    async def is_available(self) -> bool:
        return bool(self._api_key)

    async def list_models(self) -> list[str]:
        return ["deepl"]

    async def _call(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        if not self._api_key:
            raise TranslationError("DeepL API key not configured", provider=self.name)

        payload = {
            "text": texts,
            "source_lang": source_lang.upper()[:2],
            "target_lang": target_lang.upper()[:2],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._base_url,
                data=payload,
                headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
            )
            if resp.status_code >= 400:
                raise TranslationError(
                    f"DeepL error {resp.status_code}: {resp.text[:200]}",
                    provider=self.name,
                )
            data = resp.json()
            translations = data.get("translations", [])
            return [t.get("text", "") for t in translations]

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
        if not blocks:
            return blocks, 0

        texts = [block.original_text for block in blocks]
        wrapped_texts = []
        mappings = []
        for t in texts:
            w, m = glossary.wrap_terms(t)
            wrapped_texts.append(w)
            mappings.append(m)

        try:
            results = await self._call(wrapped_texts, source_lang, target_lang)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(str(exc), provider=self.name) from exc

        failures = 0
        for block, result, mapping in zip(blocks, results, mappings, strict=False):
            if result:
                block.translated_text = glossary.unwrap_terms(result, mapping)
            else:
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
        wrapped, mapping = glossary.wrap_terms(text)
        results = await self._call([wrapped], source_lang, target_lang)
        return glossary.unwrap_terms(results[0] if results else text, mapping)
