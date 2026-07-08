"""Visual verification — compare rendered output against original."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog
from PIL import Image

from app.models.document import Document, Page
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult
from app.services.layout_solver.service import LayoutSolverService

logger = structlog.get_logger(__name__)


@dataclass
class VerificationResult:
    similarity: float
    layout_score: float
    iterations: int
    adjustments: list[str]
    acceptable: bool


class VerificationService:
    """Quality assurance loop with feedback into layout solver."""

    def __init__(
        self,
        layout_solver: LayoutSolverService,
        *,
        similarity_threshold: float = 0.82,
        max_iterations: int = 3,
    ) -> None:
        self._layout_solver = layout_solver
        self._threshold = similarity_threshold
        self._max_iterations = max_iterations

    def verify_page(
        self,
        original_path: Path,
        rendered_path: Path,
        page: Page,
    ) -> StageResult[VerificationResult]:
        return run_stage(
            "visual_verification",
            lambda: self._verify(original_path, rendered_path, page),
            provider="structural_diff",
        )

    def verify_and_adjust(
        self,
        document: Document,
        original_paths: dict[int, Path],
        rendered_paths: dict[int, Path],
    ) -> StageResult[Document]:
        return run_stage(
            "visual_verification",
            lambda: self._verify_document(document, original_paths, rendered_paths),
            provider="structural_diff",
        )

    def _verify_document(
        self,
        document: Document,
        original_paths: dict[int, Path],
        rendered_paths: dict[int, Path],
    ) -> Document:
        adjusted = document
        total_iterations = 0
        for page in adjusted.pages:
            orig = original_paths.get(page.page_number)
            rend = rendered_paths.get(page.page_number)
            if not orig or not rend or not orig.exists() or not rend.exists():
                continue

            for iteration in range(self._max_iterations):
                result = self._verify(orig, rend, page)
                page.verification_score = result.similarity
                total_iterations = iteration + 1
                if result.acceptable:
                    break
                page = self._layout_solver.solve_page(page, document.target_language)
                logger.info(
                    "verification_iteration",
                    page=page.page_number,
                    iteration=iteration + 1,
                    similarity=result.similarity,
                )

        adjusted.metadata.processing_timings["verification_iterations"] = float(total_iterations)
        return adjusted

    def _verify(self, original_path: Path, rendered_path: Path, page: Page) -> VerificationResult:
        with Image.open(original_path) as orig_img, Image.open(rendered_path) as rend_img:
            orig = np.array(orig_img.convert("L").resize((256, 256)))
            rend = np.array(rend_img.convert("L").resize((256, 256)))

        diff = np.abs(orig.astype(np.float32) - rend.astype(np.float32))
        mae = float(np.mean(diff) / 255.0)
        similarity = max(0.0, 1.0 - mae)

        layout_score = self._layout_score(page)
        combined = similarity * 0.6 + layout_score * 0.4
        acceptable = combined >= self._threshold

        adjustments: list[str] = []
        if not acceptable:
            if layout_score < 0.7:
                adjustments.append("expand_overflow_blocks")
            if similarity < 0.75:
                adjustments.append("reduce_font_scale")

        return VerificationResult(
            similarity=round(similarity, 3),
            layout_score=round(layout_score, 3),
            iterations=1,
            adjustments=adjustments,
            acceptable=acceptable,
        )

    @staticmethod
    def _layout_score(page: Page) -> float:
        if not page.blocks:
            return 1.0
        overflow = 0
        for block in page.blocks:
            if block.type != "text":
                continue
            max_chars = block.metadata.get("max_chars")
            translated = getattr(block, "translated_text", None) or ""
            if max_chars and len(translated) > int(max_chars) * 1.15:
                overflow += 1
        return max(0.0, 1.0 - overflow * 0.08)
