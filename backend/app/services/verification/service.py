"""Visual verification — structure-aware quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
from PIL import Image

from app.models.document import Document, Page, TableBlock, TextBlock
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult
from app.services.layout_solver.service import LayoutSolverService

logger = structlog.get_logger(__name__)


@dataclass
class VerificationResult:
    residual_score: float
    layout_score: float
    overflow_count: int
    iterations: int
    adjustments: list[str]
    acceptable: bool


class VerificationService:
    """Quality assurance with layout-solver feedback."""

    def __init__(
        self,
        layout_solver: LayoutSolverService,
        *,
        residual_threshold: float = 0.15,
        max_iterations: int = 3,
    ) -> None:
        self._layout_solver = layout_solver
        self._residual_threshold = residual_threshold
        self._max_iterations = max_iterations

    def verify_page(
        self,
        stripped_path: Path,
        page: Page,
    ) -> StageResult[VerificationResult]:
        return run_stage(
            "visual_verification",
            lambda: self._verify(stripped_path, page),
            provider="residual_check",
        )

    def verify_and_adjust(
        self,
        document: Document,
        stripped_paths: dict[int, Path],
    ) -> StageResult[tuple[Document, list[str]]]:
        return run_stage(
            "visual_verification",
            lambda: self._verify_document(document, stripped_paths),
            provider="residual_check",
        )

    def _verify_document(
        self,
        document: Document,
        stripped_paths: dict[int, Path],
    ) -> tuple[Document, list[str]]:
        adjustments: list[str] = []
        total_iterations = 0

        for page in document.pages:
            stripped = stripped_paths.get(page.page_number)
            if not stripped or not stripped.exists():
                continue

            for iteration in range(self._max_iterations):
                result = self._verify(stripped, page)
                page.verification_score = 1.0 - result.residual_score
                total_iterations = iteration + 1

                if result.acceptable:
                    break

                if "reduce_font_scale" in result.adjustments:
                    for block in page.blocks:
                        if isinstance(block, TextBlock) and block.style.font_size:
                            block.style.font_size = max(
                                7.0, round(block.style.font_size * 0.92, 1)
                            )
                    adjustments.append(f"page_{page.page_number}:reduce_font")

                if "expand_overflow_blocks" in result.adjustments:
                    page = self._layout_solver.solve_page(page, document.target_language)
                    adjustments.append(f"page_{page.page_number}:layout_solve")

                logger.info(
                    "verification_iteration",
                    page=page.page_number,
                    iteration=iteration + 1,
                    residual=result.residual_score,
                    overflow=result.overflow_count,
                )

        document.metadata.processing_timings["verification_iterations"] = float(total_iterations)
        return document, adjustments

    def _verify(self, stripped_path: Path, page: Page) -> VerificationResult:
        from app.modules.reconstruction.text_compositor import measure_strip_quality

        page_text = [b for b in page.blocks if isinstance(b, TextBlock)]
        page_tables = [b for b in page.blocks if isinstance(b, TableBlock)]

        with Image.open(stripped_path) as img:
            residual = measure_strip_quality(img, page_text, page_tables)

        overflow = 0
        for block in page_text:
            max_chars = block.metadata.get("max_chars")
            translated = block.translated_text or ""
            if max_chars and len(translated) > int(max_chars) * 1.15:
                overflow += 1
                block.metadata["overflow"] = True
            else:
                block.metadata.pop("overflow", None)

        layout_score = max(0.0, 1.0 - overflow * 0.08)
        acceptable = residual <= self._residual_threshold and overflow == 0

        adjustments: list[str] = []
        if not acceptable:
            if residual > self._residual_threshold:
                adjustments.append("re_strip_aggressive")
            if overflow > 0:
                adjustments.append("expand_overflow_blocks")
                adjustments.append("reduce_font_scale")

        return VerificationResult(
            residual_score=round(residual, 3),
            layout_score=round(layout_score, 3),
            overflow_count=overflow,
            iterations=1,
            adjustments=adjustments,
            acceptable=acceptable,
        )
