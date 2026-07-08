"""Vision provider protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.modules.layout.doclayout_service import LayoutPageResult
from app.services.vision.types import VisionPageResult


class VisionProvider(Protocol):
    @property
    def name(self) -> str: ...

    def is_available(self) -> bool: ...

    def analyze_page(
        self,
        layout: LayoutPageResult,
        page_width: float,
        image_path: Path | None = None,
    ) -> VisionPageResult: ...
