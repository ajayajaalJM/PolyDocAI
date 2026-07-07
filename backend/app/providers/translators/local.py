from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
import structlog

from app.models.document import TextBlock
from app.providers.translators.base import Glossary
from app.providers.translators.errors import TranslationError

logger = structlog.get_logger(__name__)

PRESERVE_PATTERN = re.compile(
    r"(\{[^}]+\}|\[\[[^\]]+\]\]|[$€£¥]\s?[\d,.]+|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\b\d{4}\b|@[\w.-]+\.\w+)"
)

LANG_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "tr": "Turkish",
}

LAYOUT_INSTRUCTIONS: dict[str, str] = {
    "heading": "Keep concise — headings must fit the same visual space.",
    "caption": "Short caption style; preserve figure references.",
    "header": "Keep very short; do not translate brand names.",
    "footer": "Keep very short; preserve page numbers and dates.",
    "list": "Preserve bullet/number structure and line breaks.",
    "quote": "Preserve quotation marks and attribution.",
}

# Concurrent batch requests to Ollama (each batch = 1 API call for N blocks)
_OLLAMA_BATCH_CONCURRENCY = 3
_OLLAMA_READ_TIMEOUT = 300.0
_OLLAMA_MAX_RETRIES = 2


def _lang_label(code: str) -> str:
    return LANG_NAMES.get(code.lower(), code)


def _wrap_preserve(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counter = 0

    def replacer(match: re.Match[str]) -> str:
        nonlocal counter
        key = f"__KEEP_{counter}__"
        mapping[key] = match.group(0)
        counter += 1
        return key

    wrapped = PRESERVE_PATTERN.sub(replacer, text)
    return wrapped, mapping


def _unwrap_preserve(text: str, mapping: dict[str, str]) -> str:
    for key, val in mapping.items():
        text = text.replace(key, val)
        # Models sometimes mangle placeholder underscores
        text = text.replace(key.strip("_"), val)
        bare = key.replace("__", "")
        text = text.replace(bare, val)
    return text


def _http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return (
            "Ollama did not respond in time (3 minute limit). "
            "Try a faster model in Settings (e.g. gemma3:1b), or re-translate."
        )
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _parse_single_translation(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationError(
            f"Model returned invalid JSON: {content[:200]!r}",
            provider="ollama",
        ) from exc

    if isinstance(payload, str) and payload.strip():
        return payload.strip()

    if isinstance(payload, dict):
        for key in ("translation", "translated", "text", "output"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        translations = payload.get("translations")
        if isinstance(translations, list) and translations:
            first = translations[0]
            if isinstance(first, str):
                return first.strip()
            if isinstance(first, dict):
                return str(
                    first.get("translation") or first.get("text") or first.get("output") or ""
                ).strip()

    raise TranslationError(
        f"Model JSON missing translation field. Got: {content[:200]!r}",
        provider="ollama",
    )


def _parse_batch_translations(content: str, expected_count: int) -> list[str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationError(
            f"Model returned invalid JSON: {content[:200]!r}",
            provider="ollama",
        ) from exc

    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        if len(payload) == expected_count:
            return [item.strip() for item in payload]
        raise TranslationError(
            f"Batch returned {len(payload)} strings, expected {expected_count}.",
            provider="ollama",
        )

    if not isinstance(payload, dict):
        raise TranslationError(
            f"Unexpected batch JSON shape: {content[:200]!r}",
            provider="ollama",
        )

    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise TranslationError(
            f"Batch JSON missing translations array. Got: {content[:200]!r}",
            provider="ollama",
        )

    if translations and all(isinstance(item, str) for item in translations):
        if len(translations) == expected_count:
            return [item.strip() for item in translations]
        raise TranslationError(
            f"Batch returned {len(translations)} strings, expected {expected_count}.",
            provider="ollama",
        )

    by_id: dict[int, str] = {}
    for item in translations:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if raw_id is None:
            continue
        text = item.get("text") or item.get("translation") or item.get("output") or ""
        if isinstance(text, str) and text.strip():
            by_id[int(raw_id)] = text.strip()

    if len(by_id) == expected_count and all(i in by_id for i in range(expected_count)):
        return [by_id[i] for i in range(expected_count)]

    raise TranslationError(
        f"Batch returned {len(by_id)}/{expected_count} keyed translations.",
        provider="ollama",
    )


def _build_batch_system_prompt(
    source_lang: str,
    target_lang: str,
    count: int,
    glossary: Glossary | None,
) -> str:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    base = (
        f"You are a professional translator. Translate ALL {count} numbered items "
        f"from {src} to {tgt}.\n\n"
        "Rules:\n"
        f"- Every output string MUST be in {tgt}, not {src}.\n"
        f"- Return EXACTLY {count} translations — one per input id, same order.\n"
        "- Preserve __KEEP_N__ placeholders exactly as-is.\n"
        "- Preserve numbers, dates, currency amounts, URLs, and email addresses.\n"
        "- Preserve bullet points (•) and line breaks.\n"
        "- Do not merge, skip, or add items.\n"
        "- Do not add notes or explanations.\n"
        '- Return ONLY JSON: {"translations": [{"id": 0, "text": "..."}, ...]}\n'
    )
    if glossary and glossary.entries:
        pairs = "\n".join(f'  "{k}" → "{v}"' for k, v in glossary.entries.items())
        base += f"\nGlossary:\n{pairs}\n"
    return base


def _build_batch_user_prompt(blocks: list[TextBlock], all_blocks: list[TextBlock] | None = None) -> str:
    items: list[dict[str, Any]] = []
    block_index = {b.id: i for i, b in enumerate(all_blocks or blocks)}
    for i, block in enumerate(blocks):
        wrapped, _ = _wrap_preserve(block.original_text)
        entry: dict[str, Any] = {
            "id": i,
            "type": block.layout_type,
            "text": wrapped,
        }
        hint = LAYOUT_INSTRUCTIONS.get(block.layout_type, "")
        if hint:
            entry["hint"] = hint
        max_chars = block.metadata.get("max_chars")
        if max_chars:
            entry["max_chars"] = max_chars
        if all_blocks:
            idx = block_index.get(block.id, i)
            if idx > 0:
                entry["prev"] = all_blocks[idx - 1].original_text[:120]
            if idx < len(all_blocks) - 1:
                entry["next"] = all_blocks[idx + 1].original_text[:120]
        items.append(entry)
    return json.dumps({"items": items}, ensure_ascii=False)


def _build_single_system_prompt(
    source_lang: str,
    target_lang: str,
    glossary: Glossary | None,
) -> str:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    base = (
        f"You are a professional translator. Translate the user's text from {src} to {tgt}.\n\n"
        "Rules:\n"
        f"- Output MUST be in {tgt}, not {src}.\n"
        "- Preserve __KEEP_N__ placeholders exactly as-is.\n"
        "- Preserve numbers, dates, currency amounts, URLs, and email addresses.\n"
        "- Preserve bullet points (•) and line breaks.\n"
        "- Do not add notes or explanations.\n"
        '- Return ONLY JSON: {"translation": "..."}\n'
    )
    if glossary and glossary.entries:
        pairs = "\n".join(f'  "{k}" → "{v}"' for k, v in glossary.entries.items())
        base += f"\nGlossary:\n{pairs}\n"
    return base


def _build_single_user_prompt(block: TextBlock) -> str:
    wrapped, _ = _wrap_preserve(block.original_text)
    hint = LAYOUT_INSTRUCTIONS.get(block.layout_type, "")
    parts = [f"Translate this {block.layout_type} text:"]
    if hint:
        parts.append(f"Hint: {hint}")
    parts.append(wrapped)
    return "\n".join(parts)


def _parse_ollama_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except Exception:
        pass
    return response.text or response.reason_phrase or "Unknown error"


def _model_installed(model: str, available: list[str]) -> bool:
    if not model:
        return False
    if model in available:
        return True
    return any(name == model or name.startswith(f"{model}:") for name in available)


class OllamaTranslator:
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code == 200:
                    return [m["name"] for m in resp.json().get("models", [])]
        except httpx.HTTPError:
            pass
        return []

    async def _chat(self, payload: dict[str, Any]) -> str:
        if "qwen3" in self._model.lower():
            payload = {**payload, "think": False}
        timeout = httpx.Timeout(10.0, read=_OLLAMA_READ_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content") or ""
            if not content.strip():
                raise TranslationError(
                    "Ollama returned an empty response.",
                    provider=self.name,
                )
            return content

    async def _translate_one(
        self,
        block: TextBlock,
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None,
        strict: bool = False,
    ) -> None:
        wrapped, mapping = _wrap_preserve(block.original_text)
        system = _build_single_system_prompt(source_lang, target_lang, glossary)
        user = _build_single_user_prompt(block)

        if strict:
            tgt = _lang_label(target_lang)
            user += f"\n\nIMPORTANT: The translation must be written in {tgt}."

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }

        content = await self._chat(payload)
        translated = _unwrap_preserve(_parse_single_translation(content), mapping)
        block.translated_text = translated

    async def _translate_batch(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None,
        strict: bool = False,
        all_blocks: list[TextBlock] | None = None,
    ) -> None:
        mappings = [_wrap_preserve(b.original_text)[1] for b in blocks]
        system = _build_batch_system_prompt(
            source_lang, target_lang, len(blocks), glossary
        )
        user = _build_batch_user_prompt(blocks, all_blocks)
        if strict:
            tgt = _lang_label(target_lang)
            user += f"\n\nIMPORTANT: Every translation must be written in {tgt}."

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        content = await self._chat(payload)
        texts = _parse_batch_translations(content, len(blocks))
        for block, text, mapping in zip(blocks, texts, mappings, strict=True):
            block.translated_text = _unwrap_preserve(text, mapping)

    async def _translate_blocks_individually(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None,
    ) -> int:
        sem = asyncio.Semaphore(2)
        failures = 0

        async def run_block(block: TextBlock) -> None:
            nonlocal failures
            last_error = ""
            async with sem:
                for attempt in range(_OLLAMA_MAX_RETRIES):
                    try:
                        await self._translate_one(
                            block,
                            source_lang=source_lang,
                            target_lang=target_lang,
                            glossary=glossary,
                            strict=attempt > 0,
                        )
                        return
                    except httpx.HTTPStatusError as exc:
                        detail = _parse_ollama_error(exc.response)
                        if exc.response.status_code == 404 and "not found" in detail.lower():
                            raise TranslationError(
                                f"Ollama model {self._model!r} is not installed ({detail}).",
                                provider=self.name,
                            ) from exc
                        last_error = detail
                    except TranslationError as exc:
                        last_error = str(exc)
                    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                        last_error = (
                            _http_error_message(exc)
                            if isinstance(exc, httpx.HTTPError)
                            else str(exc)
                        )
                    if attempt + 1 < _OLLAMA_MAX_RETRIES:
                        await asyncio.sleep(1.0 * (attempt + 1))

                failures += 1
                block.translated_text = block.original_text
                logger.warning(
                    "block_translation_failed",
                    text=block.original_text[:80],
                    error=last_error or "unknown",
                    attempts=_OLLAMA_MAX_RETRIES,
                )

        await asyncio.gather(*(run_block(b) for b in blocks))
        return failures

    async def translate_blocks(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
        all_blocks: list[TextBlock] | None = None,
        **_: Any,
    ) -> tuple[list[TextBlock], int]:
        if not blocks:
            return blocks, 0
        if not await self.is_available():
            raise TranslationError(
                f"Ollama is not reachable at {self._base_url}. Start Ollama and pull model {self._model!r}.",
                provider=self.name,
            )

        available = await self.list_models()
        if not _model_installed(self._model, available):
            hint = ", ".join(available[:6]) if available else "none"
            raise TranslationError(
                f"Ollama model {self._model!r} is not installed. "
                f"Run `ollama pull {self._model}` or pick an installed model in Settings. "
                f"Available: {hint}.",
                provider=self.name,
            )

        last_error = ""
        for attempt in range(_OLLAMA_MAX_RETRIES):
            try:
                await self._translate_batch(
                    blocks,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    glossary=glossary,
                    strict=attempt > 0,
                    all_blocks=all_blocks,
                )
                logger.info(
                    "ollama_batch_complete",
                    blocks=len(blocks),
                    failures=0,
                    model=self._model,
                    target=target_lang,
                    mode="batch",
                )
                return blocks, 0
            except httpx.HTTPStatusError as exc:
                detail = _parse_ollama_error(exc.response)
                if exc.response.status_code == 404 and "not found" in detail.lower():
                    raise TranslationError(
                        f"Ollama model {self._model!r} is not installed ({detail}).",
                        provider=self.name,
                    ) from exc
                last_error = detail
            except TranslationError as exc:
                last_error = str(exc)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                last_error = (
                    _http_error_message(exc)
                    if isinstance(exc, httpx.HTTPError)
                    else str(exc)
                )
            if attempt + 1 < _OLLAMA_MAX_RETRIES:
                await asyncio.sleep(1.0 * (attempt + 1))

        logger.warning(
            "ollama_batch_fallback",
            blocks=len(blocks),
            error=last_error or "batch misalignment",
            model=self._model,
        )
        failures = await self._translate_blocks_individually(
            blocks,
            source_lang=source_lang,
            target_lang=target_lang,
            glossary=glossary,
        )
        logger.info(
            "ollama_batch_complete",
            blocks=len(blocks),
            failures=failures,
            model=self._model,
            target=target_lang,
            mode="fallback",
        )
        return blocks, failures

    async def translate_text(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
    ) -> str:
        from app.models.document import BoundingBox

        block = TextBlock(
            page_number=1,
            bbox=BoundingBox(x=0, y=0, width=100, height=20),
            original_text=text,
        )
        await self._translate_one(
            block, source_lang=source_lang, target_lang=target_lang, glossary=glossary
        )
        return block.translated_text or text


class OpenAICompatibleTranslator:
    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if resp.status_code == 200:
                    return [m["id"] for m in resp.json().get("data", [])]
        except httpx.HTTPError:
            pass
        return []

    async def translate_blocks(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
        all_blocks: list[TextBlock] | None = None,
        **_: Any,
    ) -> tuple[list[TextBlock], int]:
        if not blocks:
            return blocks, 0
        if not await self.is_available():
            raise TranslationError(
                f"OpenAI-compatible server is not reachable at {self._base_url}.",
                provider=self.name,
            )

        mappings = [_wrap_preserve(b.original_text)[1] for b in blocks]
        timeout = httpx.Timeout(10.0, read=_OLLAMA_READ_TIMEOUT)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": _build_batch_system_prompt(
                        source_lang, target_lang, len(blocks), glossary
                    ),
                },
                {"role": "user", "content": _build_batch_user_prompt(blocks, all_blocks)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
            texts = _parse_batch_translations(content, len(blocks))
            for block, text, mapping in zip(blocks, texts, mappings, strict=True):
                block.translated_text = _unwrap_preserve(text, mapping)
            return blocks, 0
        except Exception as exc:
            logger.warning("openai_batch_fallback", error=str(exc), blocks=len(blocks))
            failures = 0
            sem = asyncio.Semaphore(2)
            async def run_block(block: TextBlock) -> None:
                nonlocal failures
                async with sem:
                    wrapped, mapping = _wrap_preserve(block.original_text)
                    single_payload = {
                        "model": self._model,
                        "messages": [
                            {
                                "role": "system",
                                "content": _build_single_system_prompt(
                                    source_lang, target_lang, glossary
                                ),
                            },
                            {"role": "user", "content": _build_single_user_prompt(block)},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                    }
                    try:
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            resp = await client.post(
                                f"{self._base_url}/chat/completions",
                                json=single_payload,
                                headers={"Authorization": f"Bearer {self._api_key}"},
                            )
                            resp.raise_for_status()
                            content = resp.json()["choices"][0]["message"]["content"]
                            block.translated_text = _unwrap_preserve(
                                _parse_single_translation(content), mapping
                            )
                    except Exception as inner:
                        failures += 1
                        block.translated_text = block.original_text
                        logger.warning("block_translation_failed", error=str(inner))
            await asyncio.gather(*(run_block(b) for b in blocks))
            return blocks, failures


class NoOpTranslator:
    name = "noop"

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["pass-through"]

    async def translate_blocks(
        self,
        blocks: list[TextBlock],
        *,
        source_lang: str,
        target_lang: str,
        glossary: Glossary | None = None,
    ) -> tuple[list[TextBlock], int]:
        for block in blocks:
            block.translated_text = block.original_text
        return blocks, 0
