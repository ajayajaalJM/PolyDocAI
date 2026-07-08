"""Optional Ollama vision model provider for semantic page understanding."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import httpx
import structlog

from app.modules.layout.doclayout_service import LayoutPageResult
from app.providers.vision.heuristic import HeuristicVisionProvider
from app.services.vision.heuristic import HeuristicVisionAnalyzer
from app.services.vision.types import VisionPageResult

logger = structlog.get_logger(__name__)


class OllamaVisionProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2-vision",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._fallback = HeuristicVisionProvider()

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                return any(self._model in name for name in models)
        except (httpx.HTTPError, json.JSONDecodeError):
            return False

    def analyze_page(
        self,
        layout: LayoutPageResult,
        page_width: float,
        image_path: Path | None = None,
    ) -> VisionPageResult:
        base = self._fallback.analyze_page(layout, page_width, image_path)
        if image_path is None or not image_path.exists() or not self.is_available():
            return base

        try:
            hints = self._query_vision_model(image_path, layout)
            return self._merge_hints(base, hints, page_width)
        except Exception as exc:
            logger.warning("ollama_vision_failed", error=str(exc))
            return base

    def _query_vision_model(self, image_path: Path, layout: LayoutPageResult) -> dict:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        region_summary = [
            f"{r.element_type.value}@{int(r.bbox[0])},{int(r.bbox[1])}"
            for r in layout.regions[:20]
        ]
        prompt = (
            "Analyze this document page. Return ONLY valid JSON with keys: "
            '{"column_count": int, "sections": [{"title": str|null, "importance": float}], '
            '"region_notes": [{"index": int, "hierarchy_level": int, "importance": float}]}. '
            f"Detected regions: {', '.join(region_summary)}"
        )
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "format": "json",
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return {}
        return json.loads(match.group())

    def _merge_hints(
        self,
        base: VisionPageResult,
        hints: dict,
        page_width: float,
    ) -> VisionPageResult:
        if not hints:
            return base

        column_count = int(hints.get("column_count") or base.column_count)
        notes = hints.get("region_notes") or []
        for note in notes:
            idx = int(note.get("index", -1))
            if 0 <= idx < len(base.enrichments):
                e = base.enrichments[idx]
                if "importance" in note:
                    e.vision.importance = float(note["importance"])
                if "hierarchy_level" in note:
                    e.vision.hierarchy_level = int(note["hierarchy_level"])

        section_hints = hints.get("sections") or []
        for i, section in enumerate(base.sections):
            if i < len(section_hints) and section_hints[i].get("title"):
                section.title = str(section_hints[i]["title"])

        base.column_count = column_count
        analyzer = HeuristicVisionAnalyzer()
        for e in base.enrichments:
            e.vision.column_index = analyzer.column_index(
                e.region.bbox, page_width, column_count
            )
        return base
