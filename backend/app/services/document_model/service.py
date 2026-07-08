"""Document model service — DOM validation, enrichment, versioning."""

from __future__ import annotations

import structlog

from app.models.document import (
    DOM_SCHEMA_VERSION,
    Document,
    InlineRun,
    Page,
    TextBlock,
)
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)


class DocumentModelService:
    """Central DOM operations — source of truth management."""

    def apply_pages(self, document: Document, pages: list[Page]) -> StageResult[Document]:
        return run_stage(
            "document_model",
            lambda: self._apply(document, pages),
            provider="pydantic",
        )

    def _apply(self, document: Document, pages: list[Page]) -> Document:
        document.schema_version = DOM_SCHEMA_VERSION
        document.pages = pages
        document.page_count = len(pages)
        self._enrich_inline_runs(document)
        self._validate(document)
        return document

    @staticmethod
    def _enrich_inline_runs(document: Document) -> None:
        for page in document.pages:
            for block in page.blocks:
                if not isinstance(block, TextBlock):
                    continue
                if block.inline_runs:
                    continue
                if block.ocr_data and block.ocr_data.lines:
                    block.inline_runs = [
                        InlineRun(
                            text=line.text,
                            style=block.style,
                            bbox=line.bbox,
                            confidence=line.confidence,
                        )
                        for line in block.ocr_data.lines
                    ]
                elif block.original_text:
                    block.inline_runs = [
                        InlineRun(text=block.original_text, style=block.style, bbox=block.bbox)
                    ]

    @staticmethod
    def _validate(document: Document) -> None:
        for page in document.pages:
            orders = [b.reading_order for b in page.blocks]
            if len(orders) != len(set(orders)):
                logger.warning(
                    "duplicate_reading_order",
                    document_id=document.id,
                    page=page.page_number,
                )

    def migrate_if_needed(self, document: Document) -> Document:
        if not document.schema_version:
            document.schema_version = "1.0.0"
        if document.schema_version == "1.0.0":
            document.schema_version = DOM_SCHEMA_VERSION
            self._enrich_inline_runs(document)
        return document
