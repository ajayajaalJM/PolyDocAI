"""Heuristic vision provider — layout-based semantic enrichment."""

from __future__ import annotations

from pathlib import Path

from app.modules.layout.doclayout_service import LayoutPageResult
from app.services.vision.heuristic import HeuristicVisionAnalyzer
from app.services.vision.types import VisionPageResult


class HeuristicVisionProvider:
    name = "heuristic"

    def __init__(self) -> None:
        self._analyzer = HeuristicVisionAnalyzer()

    def is_available(self) -> bool:
        return True

    def analyze_page(
        self,
        layout: LayoutPageResult,
        page_width: float,
        image_path: Path | None = None,
    ) -> VisionPageResult:
        return self._analyzer.analyze(layout, page_width)
