"""Per-document pipeline execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PageContext:
    document_id: str
    page_number: int
    source_path: Path
    normalized_path: Path | None = None
    upload_path: Path | None = None
    is_pdf: bool = False
    dpi: int = 300
    warnings: list[str] = field(default_factory=list)


@dataclass
class PipelineContext:
    document_id: str
    storage_root: Path
    upload_path: Path
    is_pdf: bool
    dpi: int = 300
    source_type: str = "image"
    warnings: list[str] = field(default_factory=list)
    stage_timings: dict[str, float] = field(default_factory=dict)
