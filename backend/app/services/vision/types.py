"""Vision analysis result types."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.document import BlockRelationship, Section, VisionBlockData
from app.modules.layout.doclayout_service import LayoutRegion


@dataclass
class VisionRegionEnrichment:
    region_id: str
    region: LayoutRegion
    vision: VisionBlockData
    relationships: list[BlockRelationship] = field(default_factory=list)


@dataclass
class VisionPageResult:
    page_number: int
    enrichments: list[VisionRegionEnrichment]
    sections: list[Section] = field(default_factory=list)
    column_count: int = 1
