"""Heuristic vision analysis logic."""

from __future__ import annotations

from uuid import uuid4

from app.core.geometry import iou
from app.models.document import BlockRelationship, Section, VisionBlockData
from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion
from app.services.vision.types import VisionPageResult, VisionRegionEnrichment

IMPORTANCE_MAP = {
    LayoutElementType.TITLE: 1.0,
    LayoutElementType.HEADING: 0.9,
    LayoutElementType.PARAGRAPH: 0.5,
    LayoutElementType.LIST: 0.55,
    LayoutElementType.TABLE: 0.7,
    LayoutElementType.FIGURE: 0.6,
    LayoutElementType.IMAGE: 0.55,
    LayoutElementType.LOGO: 0.4,
    LayoutElementType.CAPTION: 0.45,
    LayoutElementType.HEADER: 0.35,
    LayoutElementType.FOOTER: 0.3,
    LayoutElementType.SIDEBAR: 0.4,
    LayoutElementType.QUOTE: 0.5,
}


class HeuristicVisionAnalyzer:
    def analyze(self, layout: LayoutPageResult, page_width: float) -> VisionPageResult:
        regions = sorted(layout.regions, key=lambda r: (r.bbox[1], r.bbox[0]))
        enrichments: list[VisionRegionEnrichment] = []
        region_ids = {str(uuid4()): r for r in regions}

        for region_id, region in region_ids.items():
            importance = IMPORTANCE_MAP.get(region.element_type, 0.5)
            hierarchy = self.hierarchy_level(region.element_type)
            alignment = self.estimate_alignment(region.bbox, page_width)
            font_size = self.estimate_font_size(region)
            enrichments.append(
                VisionRegionEnrichment(
                    region_id=region_id,
                    region=region,
                    vision=VisionBlockData(
                        importance=importance,
                        hierarchy_level=hierarchy,
                        alignment=alignment,  # type: ignore[arg-type]
                        estimated_font_size=font_size,
                        is_decorative=region.element_type
                        in {LayoutElementType.LOGO, LayoutElementType.HEADER, LayoutElementType.FOOTER},
                    ),
                )
            )

        self.link_captions(enrichments)
        self.link_headers_footers(enrichments)
        sections = self.build_sections(enrichments)
        column_count = self.detect_columns(regions, page_width)

        for e in enrichments:
            section = next((s for s in sections if e.region_id in s.block_ids), None)
            if section:
                e.vision.section_id = section.id
                e.vision.column_index = self.column_index(e.region.bbox, page_width, column_count)

        return VisionPageResult(
            page_number=layout.page_number,
            enrichments=enrichments,
            sections=sections,
            column_count=column_count,
        )

    @staticmethod
    def hierarchy_level(element_type: LayoutElementType) -> int:
        if element_type in {LayoutElementType.TITLE, LayoutElementType.HEADING}:
            return 1
        if element_type in {LayoutElementType.HEADER, LayoutElementType.FOOTER}:
            return 0
        if element_type == LayoutElementType.CAPTION:
            return 2
        return 3

    @staticmethod
    def estimate_alignment(bbox: tuple[float, float, float, float], page_width: float) -> str:
        x, _, w, _ = bbox
        center = x + w / 2
        if center > page_width * 0.65:
            return "right"
        if center < page_width * 0.35:
            return "left"
        if abs(center - page_width / 2) < page_width * 0.08:
            return "center"
        return "left"

    @staticmethod
    def estimate_font_size(region: LayoutRegion) -> float:
        _, _, _, h = region.bbox
        if region.element_type in {LayoutElementType.TITLE, LayoutElementType.HEADING}:
            return round(min(h * 0.75, 48.0), 1)
        if region.element_type in {LayoutElementType.CAPTION, LayoutElementType.FOOTER, LayoutElementType.HEADER}:
            return round(max(8.0, h * 0.65), 1)
        return round(max(8.0, min(h * 0.85, 36.0)), 1)

    @staticmethod
    def link_captions(enrichments: list[VisionRegionEnrichment]) -> None:
        figures = [
            e
            for e in enrichments
            if e.region.element_type in {LayoutElementType.FIGURE, LayoutElementType.IMAGE}
        ]
        captions = [e for e in enrichments if e.region.element_type == LayoutElementType.CAPTION]
        for caption in captions:
            best: VisionRegionEnrichment | None = None
            best_dist = float("inf")
            cx, cy = caption.region.bbox[0], caption.region.bbox[1]
            for fig in figures:
                fx, fy, _, fh = fig.region.bbox
                dist = abs(cy - (fy + fh)) + abs(cx - fx)
                if dist < best_dist and iou(caption.region.bbox, fig.region.bbox) < 0.3:
                    best_dist = dist
                    best = fig
            if best and best_dist < 200:
                caption.relationships.append(
                    BlockRelationship(target_id=best.region_id, type="caption")
                )
                best.relationships.append(
                    BlockRelationship(target_id=caption.region_id, type="child")
                )

    @staticmethod
    def link_headers_footers(enrichments: list[VisionRegionEnrichment]) -> None:
        body = [
            e
            for e in enrichments
            if e.region.element_type
            not in {LayoutElementType.HEADER, LayoutElementType.FOOTER, LayoutElementType.LOGO}
        ]
        if not body:
            return
        for e in enrichments:
            if e.region.element_type == LayoutElementType.HEADER:
                below = [b for b in body if b.region.bbox[1] > e.region.bbox[1]]
                for b in below[:3]:
                    b.relationships.append(
                        BlockRelationship(target_id=e.region_id, type="header")
                    )

    @staticmethod
    def build_sections(enrichments: list[VisionRegionEnrichment]) -> list[Section]:
        sections: list[Section] = []
        current: Section | None = None
        order = 0
        for e in sorted(enrichments, key=lambda x: (x.region.bbox[1], x.region.bbox[0])):
            if e.region.element_type in {LayoutElementType.TITLE, LayoutElementType.HEADING}:
                current = Section(
                    title=None,
                    layout_type="heading",
                    reading_order=order,
                    hierarchy_level=e.vision.hierarchy_level,
                    block_ids=[e.region_id],
                )
                sections.append(current)
                order += 1
            elif current is not None:
                current.block_ids.append(e.region_id)
            else:
                current = Section(
                    layout_type="paragraph",
                    reading_order=order,
                    block_ids=[e.region_id],
                )
                sections.append(current)
                order += 1
        return sections

    @staticmethod
    def detect_columns(regions: list[LayoutRegion], page_width: float) -> int:
        if not regions:
            return 1
        centers = sorted(r.bbox[0] + r.bbox[2] / 2 for r in regions)
        mid = page_width / 2
        left = sum(1 for c in centers if c < mid * 0.9)
        right = sum(1 for c in centers if c > mid * 1.1)
        if left >= 3 and right >= 3:
            return 2
        return 1

    @staticmethod
    def column_index(
        bbox: tuple[float, float, float, float],
        page_width: float,
        column_count: int,
    ) -> int:
        if column_count <= 1:
            return 0
        center = bbox[0] + bbox[2] / 2
        return 1 if center > page_width / 2 else 0
