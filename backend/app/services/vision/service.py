"""Vision understanding layer — semantic enrichment of layout regions."""

from __future__ import annotations

from pathlib import Path

from app.modules.layout.doclayout_service import LayoutPageResult
from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult
from app.providers.vision.base import VisionProvider
from app.providers.vision.heuristic import HeuristicVisionProvider
from app.providers.vision.ollama import OllamaVisionProvider
from app.services.vision.types import VisionPageResult


class VisionService:
    """Enrich detected regions with semantic metadata. Never replaces OCR."""

    def __init__(
        self,
        provider: str = "heuristic",
        ollama_base_url: str = "http://localhost:11434",
        ollama_vision_model: str = "llama3.2-vision",
    ) -> None:
        self._providers: dict[str, VisionProvider] = {
            "heuristic": HeuristicVisionProvider(),
            "ollama": OllamaVisionProvider(ollama_base_url, ollama_vision_model),
        }
        self._active = provider if provider in self._providers else "heuristic"

    @property
    def provider_name(self) -> str:
        active = self._providers.get(self._active)
        if active and active.is_available():
            return active.name
        return "heuristic"

    def analyze_page(
        self,
        layout: LayoutPageResult,
        page_width: float,
        image_path: Path | None = None,
    ) -> StageResult[VisionPageResult]:
        provider = self._providers.get(self._active)
        if provider is None or not provider.is_available():
            provider = self._providers["heuristic"]

        return run_stage(
            "vision_understanding",
            lambda: provider.analyze_page(layout, page_width, image_path),
            provider=provider.name,
        )
