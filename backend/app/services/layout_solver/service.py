"""Layout solver — overflow, wrapping, RTL mirroring, table sizing."""

from __future__ import annotations

import copy

import structlog

from app.models.document import Document, Page, TableBlock, TextBlock, TextStyle
from app.modules.reconstruction.layout_reflow import effective_compose_bbox
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)

RTL_LANGUAGES = {"ar", "fa", "ur", "he"}


class LayoutSolverService:
    """Produce layout-adjusted DOM from original + translated content."""

    def solve_document(self, document: Document) -> StageResult[Document]:
        return run_stage(
            "layout_solver",
            lambda: self._solve(document),
            provider="layout_solver",
        )

    def solve_page(self, page: Page, target_language: str | None = None) -> Page:
        solved = copy.deepcopy(page)
        for block in solved.blocks:
            if isinstance(block, TextBlock):
                self._solve_text_block(block, solved.height, solved.width, target_language)
            elif isinstance(block, TableBlock):
                self._solve_table_block(block)
        solved.layout_solved = True
        return solved

    def _solve(self, document: Document) -> Document:
        solved_doc = copy.deepcopy(document)
        for page in solved_doc.pages:
            solved_page = self.solve_page(page, document.target_language)
            page.blocks = solved_page.blocks
            page.layout_solved = True
        return solved_doc

    def _solve_text_block(
        self,
        block: TextBlock,
        page_height: float,
        page_width: float,
        target_language: str | None,
    ) -> None:
        text = block.translated_text or block.original_text
        if not text:
            return

        compose_bbox = effective_compose_bbox(
            block,
            text,
            page_height=page_height,
            page_width=page_width,
        )
        block.metadata["compose_bbox"] = [
            compose_bbox.x,
            compose_bbox.y,
            compose_bbox.width,
            compose_bbox.height,
        ]

        max_chars = block.metadata.get("max_chars")
        if max_chars and len(text) > int(max_chars) * 1.1:
            scale = min(1.0, int(max_chars) / max(len(text), 1))
            if block.style.font_size:
                block.style.font_size = max(8.0, round(block.style.font_size * scale, 1))

        if target_language and target_language.lower()[:2] in RTL_LANGUAGES:
            block.style.direction = "rtl"
            if block.style.alignment == "left":
                block.style.alignment = "right"

    @staticmethod
    def _solve_table_block(block: TableBlock) -> None:
        rows = block.translated_rows or block.rows
        if not rows:
            return
        max_cols = max(len(r) for r in rows)
        if not block.col_widths and block.bbox.width > 0:
            cw = block.bbox.width / max(max_cols, 1)
            block.col_widths = [cw] * max_cols
        if not block.row_heights and block.bbox.height > 0:
            rh = block.bbox.height / max(len(rows), 1)
            block.row_heights = [rh] * len(rows)

        longest = max(len(" ".join(r)) for r in rows)
        original_len = max(len(" ".join(r)) for r in block.rows) if block.rows else longest
        if longest > original_len * 1.2 and block.row_heights:
            scale = original_len / max(longest, 1)
            block.row_heights = [max(h, h / scale) for h in block.row_heights]
