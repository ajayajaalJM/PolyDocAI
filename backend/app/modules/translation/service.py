from __future__ import annotations

import asyncio
import random

import structlog

from app.models.document import Document, DocumentStatus, PageStatus, TableBlock, TextBlock, TranslatorSettings
from app.modules.preprocessing.language_detector import detect_from_blocks
from app.modules.preprocessing.style_analyzer import apply_target_typography, enforce_max_length
from app.providers.translators.base import Glossary
from app.providers.translators.deepl import DeepLTranslator
from app.providers.translators.errors import TranslationError
from app.providers.translators.local import (
    NoOpTranslator,
    OllamaTranslator,
    OpenAICompatibleTranslator,
    _model_installed,
)
from app.providers.translators.nmt import NMTTranslator

logger = structlog.get_logger(__name__)


class TranslationService:
    BATCH_SIZE = 10
    BATCH_CONCURRENCY = 3
    QA_SAMPLE_RATE = 0.2
    QA_THRESHOLD = 0.7

    def __init__(
        self,
        settings: TranslatorSettings,
        glossary: Glossary | None = None,
    ) -> None:
        self._settings = settings
        self._glossary = glossary or Glossary()
        self._translators = self._build_translators(settings)

    @staticmethod
    def _build_translators(settings: TranslatorSettings) -> dict:
        return {
            "ollama": OllamaTranslator(settings.ollama_base_url, settings.ollama_model),
            "openai_compatible": OpenAICompatibleTranslator(
                settings.openai_compatible_base_url,
                settings.openai_compatible_model,
                settings.openai_compatible_api_key,
            ),
            "nmt": NMTTranslator(),
            "deepl": DeepLTranslator(settings.deepl_api_key),
            "noop": NoOpTranslator(),
        }

    def update_settings(self, settings: TranslatorSettings) -> None:
        self._settings = settings
        self._translators = self._build_translators(settings)

    def update_glossary(self, glossary: Glossary) -> None:
        self._glossary = glossary

    def get_translator(self):
        return self._translators.get(self._settings.provider, self._translators["noop"])

    @staticmethod
    def _text_blocks(document: Document) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        for page in document.pages:
            blocks.extend(b for b in page.blocks if isinstance(b, TextBlock))
        return blocks

    @staticmethod
    def _filter_blocks(
        document: Document,
        *,
        skip_edited: bool,
        block_ids: list[str] | None,
        page_numbers: list[int] | None,
    ) -> list[TextBlock]:
        blocks = TranslationService._text_blocks(document)
        if block_ids:
            id_set = set(block_ids)
            blocks = [b for b in blocks if b.id in id_set]
        if page_numbers:
            pages = set(page_numbers)
            blocks = [b for b in blocks if b.page_number in pages]
        if skip_edited:
            blocks = [b for b in blocks if not b.is_edited]
        return blocks

    @staticmethod
    def _translation_stats(blocks: list[TextBlock]) -> tuple[int, int, int]:
        total = len(blocks)
        translated = sum(1 for b in blocks if b.translated_text)
        unchanged = sum(
            1
            for b in blocks
            if b.translated_text is not None and b.translated_text.strip() == b.original_text.strip()
        )
        return total, translated, unchanged

    async def _translate_block_batches(
        self,
        blocks: list[TextBlock],
        translator,
        src: str,
        tgt: str,
        all_blocks: list[TextBlock],
    ) -> int:
        if not blocks:
            return 0
        batches = [
            blocks[i : i + self.BATCH_SIZE] for i in range(0, len(blocks), self.BATCH_SIZE)
        ]
        sem = asyncio.Semaphore(self.BATCH_CONCURRENCY)
        total_failures = 0

        async def run_batch(batch: list[TextBlock]) -> int:
            async with sem:
                _, fails = await translator.translate_blocks(
                    batch,
                    source_lang=src,
                    target_lang=tgt,
                    glossary=self._glossary,
                    all_blocks=all_blocks,
                )
                for block in batch:
                    max_chars = block.metadata.get("max_chars")
                    if block.translated_text and max_chars:
                        block.translated_text = enforce_max_length(
                            block.translated_text,
                            int(max_chars),
                            block.layout_type,
                        )
                return fails

        results = await asyncio.gather(*(run_batch(batch) for batch in batches))
        return sum(results)

    async def _qa_pass(
        self,
        blocks: list[TextBlock],
        translator,
        src: str,
        tgt: str,
    ) -> None:
        if not blocks or self._settings.provider == "noop":
            return

        sample = [b for b in blocks if random.random() < self.QA_SAMPLE_RATE]
        if not sample:
            sample = blocks[: min(3, len(blocks))]

        for block in blocks:
            if block.translation_confidence is None:
                block.translation_confidence = 0.85

        for block in sample:
            if not block.translated_text:
                block.translation_confidence = 0.0
                continue
            try:
                if hasattr(translator, "translate_text"):
                    back = await translator.translate_text(
                        block.translated_text,
                        source_lang=tgt,
                        target_lang=src,
                        glossary=self._glossary,
                    )
                else:
                    continue
                orig = block.original_text.lower().strip()
                back_norm = back.lower().strip()
                if orig == back_norm:
                    block.translation_confidence = 1.0
                elif orig in back_norm or back_norm in orig:
                    block.translation_confidence = 0.75
                else:
                    overlap = len(set(orig.split()) & set(back_norm.split()))
                    ratio = overlap / max(len(orig.split()), 1)
                    block.translation_confidence = min(0.9, ratio)
                    if block.translation_confidence < self.QA_THRESHOLD:
                        _, fails = await translator.translate_blocks(
                            [block],
                            source_lang=src,
                            target_lang=tgt,
                            glossary=self._glossary,
                        )
                        if fails == 0:
                            block.translation_confidence = 0.8
            except Exception:
                block.translation_confidence = 0.5

    async def translate_document(
        self,
        document: Document,
        source_lang: str | None = None,
        target_lang: str | None = None,
        *,
        auto_detect_source: bool = True,
        skip_edited: bool = True,
        block_ids: list[str] | None = None,
        page_numbers: list[int] | None = None,
    ) -> Document:
        all_text_blocks = self._text_blocks(document)
        text_blocks = self._filter_blocks(
            document,
            skip_edited=skip_edited,
            block_ids=block_ids,
            page_numbers=page_numbers,
        )
        src = source_lang or self._settings.source_language
        tgt = target_lang or self._settings.target_language

        if auto_detect_source and all_text_blocks:
            detected = detect_from_blocks(all_text_blocks, default=src)
            if detected != src:
                document.metadata.warnings.append(
                    f"Auto-detected source language '{detected}' (settings had '{src}')."
                )
                src = detected

        if src == tgt and self._settings.provider != "noop":
            document.metadata.warnings.append(
                f"Source and target language are both '{src}'; translation may appear unchanged."
            )

        translator = self.get_translator()
        document.metadata.warnings = [
            w for w in document.metadata.warnings if not w.startswith("Translation failed:")
        ]

        if self._settings.provider == "noop":
            document.metadata.warnings.append(
                "Translation provider is set to pass-through (noop); text will not be translated."
            )

        try:
            if not await translator.is_available():
                raise TranslationError(
                    f"Translation provider '{translator.name}' is unavailable.",
                    provider=translator.name,
                )

            block_failures = 0
            for page in document.pages:
                if page_numbers and page.page_number not in page_numbers:
                    continue
                id_set = {b.id for b in text_blocks}
                page_blocks = [
                    b
                    for b in page.blocks
                    if isinstance(b, TextBlock) and b.id in id_set
                ]
                if not page_blocks and not block_ids:
                    page_blocks = [
                        b
                        for b in page.blocks
                        if isinstance(b, TextBlock)
                        and not (skip_edited and b.is_edited)
                    ]
                page.translation_status = PageStatus.PROCESSING
                ordered = sorted(page_blocks, key=lambda b: b.reading_order)
                page_failures = await self._translate_block_batches(
                    ordered, translator, src, tgt, all_text_blocks
                )
                block_failures += page_failures

                table_blocks = [b for b in page.blocks if isinstance(b, TableBlock)]
                for table in table_blocks:
                    if skip_edited and table.is_edited:
                        continue
                    await self._translate_table(table, translator, src, tgt)

                page.translation_status = PageStatus.COMPLETE

            await self._qa_pass(text_blocks, translator, src, tgt)

            total, translated, unchanged = self._translation_stats(all_text_blocks)
            if block_failures:
                document.metadata.warnings.append(
                    f"{block_failures} text block(s) could not be translated "
                    f"(timeout or model error) — original text kept for those regions."
                )
            if total and block_failures == len(text_blocks) and text_blocks:
                raise TranslationError(
                    "Every text block failed to translate. Check translation provider settings.",
                    provider=translator.name,
                )
            if total and unchanged == total and self._settings.provider != "noop" and text_blocks:
                document.metadata.warnings.append(
                    "Translation completed but all blocks match the original text. "
                    "Check source/target languages and that your translator is running."
                )
            elif total and translated < total:
                document.metadata.warnings.append(
                    f"Only {translated}/{total} text blocks received translations."
                )

            document.source_language = src
            document.target_language = tgt
            for block in all_text_blocks:
                apply_target_typography(block, tgt)
            document.status = DocumentStatus.TRANSLATED
            logger.info(
                "translation_complete",
                document_id=document.id,
                provider=translator.name,
                target=tgt,
                blocks=len(text_blocks),
                failures=block_failures,
            )
        except TranslationError as exc:
            for page in document.pages:
                if page.translation_status == PageStatus.PROCESSING:
                    page.translation_status = PageStatus.ERROR
            has_content = any(p.raster_path or p.blocks for p in document.pages)
            document.status = (
                DocumentStatus.LAYOUT_COMPLETE if has_content else DocumentStatus.ERROR
            )
            document.metadata.warnings.append(f"Translation failed: {exc}")
            logger.warning("translation_failed", document_id=document.id, error=str(exc))
            raise

        return document

    async def _translate_table(
        self, table: TableBlock, translator, src: str, tgt: str
    ) -> None:
        if table.cells:
            flat: list[TextBlock] = []
            for cell in table.cells:
                if not cell.text.strip():
                    continue
                flat.append(
                    TextBlock(
                        page_number=table.page_number,
                        bbox=cell.bbox,
                        original_text=cell.text,
                        layout_type="paragraph",
                        metadata={"table_row": cell.row, "table_col": cell.col},
                    )
                )
            if flat:
                await self._translate_block_batches(flat, translator, src, tgt, flat)
                for cell, block in zip(
                    [c for c in table.cells if c.text.strip()],
                    flat,
                    strict=False,
                ):
                    cell.translated_text = block.translated_text
                translated_rows: list[list[str]] = []
                for row in table.rows:
                    out_row: list[str] = []
                    for cell_text in row:
                        match = next(
                            (
                                c
                                for c in table.cells
                                if c.text == cell_text and c.translated_text
                            ),
                            None,
                        )
                        out_row.append(match.translated_text if match else cell_text)
                    translated_rows.append(out_row)
                table.translated_rows = translated_rows
            return

        flat = []
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row):
                if not str(cell).strip():
                    continue
                flat.append(
                    TextBlock(
                        page_number=table.page_number,
                        bbox=table.bbox,
                        original_text=str(cell),
                        layout_type="paragraph",
                        metadata={"table_row": ri, "table_col": ci},
                    )
                )
        if not flat:
            return
        await self._translate_block_batches(flat, translator, src, tgt, flat)
        idx = 0
        translated_rows = []
        for row in table.rows:
            out_row = []
            for cell in row:
                if str(cell).strip() and idx < len(flat):
                    out_row.append(flat[idx].translated_text or cell)
                    idx += 1
                else:
                    out_row.append(cell)
            translated_rows.append(out_row)
        table.translated_rows = translated_rows

    async def test_connection(self, provider: str | None = None) -> tuple[bool, str, list[str]]:
        key = provider or self._settings.provider
        translator = self._translators.get(key, self._translators["noop"])
        if key == "noop":
            return True, "Pass-through mode (no translation)", ["pass-through"]

        available = await translator.is_available()
        models = await translator.list_models() if available else []
        if not available:
            return False, f"Provider '{key}' is unreachable", models

        if key == "nmt":
            return True, "NMT (Argos Translate) available", models
        if key == "deepl":
            return True, "DeepL API configured", models

        configured = (
            self._settings.ollama_model
            if key == "ollama"
            else self._settings.openai_compatible_model
        )
        if key == "ollama" and not _model_installed(configured, models):
            hint = ", ".join(models[:6]) if models else "none"
            return (
                False,
                f"Model {configured!r} is not installed. Run `ollama pull {configured}` "
                f"or choose one of: {hint}.",
                models,
            )
        if key == "openai_compatible" and models and configured not in models:
            hint = ", ".join(models[:6])
            return (
                False,
                f"Model {configured!r} was not found on the server. Available: {hint}.",
                models,
            )

        return True, f"Connected — using model {configured!r}", models
