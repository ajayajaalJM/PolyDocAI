"""Rendering plugin interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models.document import Document


@dataclass
class RenderResult:
    content: bytes
    mime_type: str
    filename: str


@dataclass
class RenderOptions:
    use_translated: bool = True
    storage_root: Path | None = None
    dpi: int = 300


class RendererProvider(Protocol):
    format: str

    def render(self, document: Document, options: RenderOptions) -> RenderResult: ...
