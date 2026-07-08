"""Per-page pipeline executing all analysis stages in order."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import structlog
from PIL import Image

from app.models.document import Page
from app.modules.layout.doclayout_service import LayoutPageResult
from app.modules.ocr.paddle_service import OCRPageResult, PaddleOCRService
from app.modules.ocr.structure_service import StructurePageResult
from app.modules.pipeline.model_builder import DocumentModelBuilder
from app.modules.preprocessing.image_extractor import crop_region
from app.modules.preprocessing.pdf_processor import PDFProcessor
from app.pipeline.cache import PipelineCache
from app.pipeline.context import PageContext
from app.pipeline.serializers import (
    layout_from_dict,
    layout_to_dict,
    normalization_to_dict,
    ocr_from_dict,
    ocr_to_dict,
)
from app.pipeline.types import StageResult
from app.services.image_normalization.service import ImageNormalizationService, NormalizationResult
from app.services.layout.service import LayoutService
from app.services.ocr.service import OCRService
from app.services.vision.service import VisionService
from app.services.vision.types import VisionPageResult

logger = structlog.get_logger(__name__)


@dataclass
class PagePipelineResult:
    page: Page
    normalization: NormalizationResult | None
    layout: LayoutPageResult | None
    vision: VisionPageResult | None
    ocr: OCRPageResult | None
    warnings: list[str]
    stage_timings: dict[str, float]
    cache_hits: dict[str, bool] = field(default_factory=dict)


class PagePipeline:
    """
    Target pipeline per page:
    Normalization → Layout → Vision → OCR → Style+DOM (via model builder)
    """

    def __init__(
        self,
        normalization: ImageNormalizationService,
        layout: LayoutService,
        vision: VisionService,
        ocr: OCRService,
        model_builder: DocumentModelBuilder,
        cache: PipelineCache | None = None,
        *,
        enable_cache: bool = True,
    ) -> None:
        self._normalization = normalization
        self._layout = layout
        self._vision = vision
        self._ocr = ocr
        self._model_builder = model_builder
        self._cache = cache
        self._enable_cache = enable_cache and cache is not None

    def process_page(
        self,
        ctx: PageContext,
        *,
        thumbnail_path: str | None = None,
        raster_path: str | None = None,
        pdf_spans: list[dict] | None = None,
        structure_tables: list | None = None,
        save_asset_cb=None,
        storage_root: Path | None = None,
    ) -> PagePipelineResult:
        warnings: list[str] = []
        timings: dict[str, float] = {}
        cache_hits: dict[str, bool] = {}

        source_hash = PipelineCache.hash_file(ctx.source_path) if self._cache else ""

        norm_data, work_path, norm_hit = self._normalize_page(ctx, source_hash, timings, warnings)
        cache_hits["normalization"] = norm_hit

        with Image.open(work_path) as img:
            width, height = float(img.size[0]), float(img.size[1])

        work_hash = PipelineCache.hash_file(work_path) if self._cache else source_hash

        layout_data, layout_hit = self._detect_layout(
            ctx, work_path, work_hash, width, height, timings
        )
        cache_hits["layout"] = layout_hit

        text_regions = self._layout.text_regions(layout_data)

        vision_result = self._vision.analyze_page(layout_data, width, image_path=work_path)
        timings["vision_ms"] = vision_result.elapsed_ms
        vision_data = vision_result.data if vision_result.success else None
        if vision_result.warnings:
            warnings.extend(vision_result.warnings)

        structure_result: StructurePageResult | None = None
        if self._layout.provider_name == "pp_structure":
            structure_result = self._layout.get_structure_tables(work_path, ctx.page_number)
            if structure_result and structure_result.tables:
                structure_tables = structure_result.tables

        ocr_data, ocr_hit = self._extract_ocr(
            ctx,
            work_path,
            work_hash,
            width,
            height,
            text_regions,
            structure_result,
            timings,
        )
        cache_hits["ocr"] = ocr_hit

        if ctx.is_pdf and ctx.upload_path and not pdf_spans:
            pdf_spans = PDFProcessor.extract_text_spans(ctx.upload_path, ctx.page_number, ctx.dpi)

        page = self._model_builder.merge_page(
            ocr_data,
            layout_data,
            thumbnail_path=thumbnail_path,
            raster_path=raster_path,
            pdf_spans=pdf_spans,
            structure_tables=structure_tables,
            image_path=work_path,
            vision_result=vision_data,
            ocr_provider=self._ocr.provider_name,
        )
        if vision_data:
            page.sections = vision_data.sections

        if storage_root and norm_data:
            try:
                page.normalized_raster_path = str(
                    norm_data.output_path.relative_to(storage_root)
                )
            except ValueError:
                pass

        for block in page.blocks:
            if block.type == "image" and not block.asset_path and save_asset_cb:
                bbox = (block.bbox.x, block.bbox.y, block.bbox.width, block.bbox.height)
                cropped = crop_region(work_path, bbox)
                if cropped:
                    asset_name = f"page{ctx.page_number}_fig_{uuid4().hex[:8]}.png"
                    saved = save_asset_cb(asset_name, cropped)
                    if saved:
                        block.asset_path = saved

        return PagePipelineResult(
            page=page,
            normalization=norm_data,
            layout=layout_data,
            vision=vision_data,
            ocr=ocr_data,
            warnings=warnings,
            stage_timings=timings,
            cache_hits=cache_hits,
        )

    def _normalize_page(
        self,
        ctx: PageContext,
        source_hash: str,
        timings: dict[str, float],
        warnings: list[str],
    ) -> tuple[NormalizationResult | None, Path, bool]:
        cache_hit = False
        if self._enable_cache and self._cache:
            cached = self._cache.get(ctx.document_id, ctx.page_number, "normalization", source_hash)
            if cached:
                out = Path(str(cached["output_path"]))
                if out.exists():
                    cache_hit = True
                    timings["normalization_ms"] = 0.0
                    ctx.normalized_path = out
                    return (
                        NormalizationResult(
                            output_path=out,
                            width=float(cached["width"]),
                            height=float(cached["height"]),
                            rotation_deg=float(cached.get("rotation_deg", 0)),
                        ),
                        out,
                        True,
                    )

        norm_result = self._normalization.normalize_page(
            ctx.source_path,
            ctx.source_path.parent / "normalized",
            ctx.page_number,
        )
        timings["normalization_ms"] = norm_result.elapsed_ms
        if not norm_result.success or norm_result.data is None:
            warnings.append(f"Normalization failed: {norm_result.errors}")
            return None, ctx.source_path, cache_hit

        norm_data = norm_result.data
        ctx.normalized_path = norm_data.output_path
        if self._enable_cache and self._cache:
            self._cache.put(
                ctx.document_id,
                ctx.page_number,
                "normalization",
                source_hash,
                normalization_to_dict(
                    str(norm_data.output_path),
                    norm_data.width,
                    norm_data.height,
                    rotation_deg=norm_data.rotation_deg,
                ),
            )
        return norm_data, norm_data.output_path, cache_hit

    def _detect_layout(
        self,
        ctx: PageContext,
        work_path: Path,
        work_hash: str,
        width: float,
        height: float,
        timings: dict[str, float],
    ) -> tuple[LayoutPageResult, bool]:
        cache_hit = False
        if self._enable_cache and self._cache:
            cached = self._cache.get(ctx.document_id, ctx.page_number, "layout", work_hash)
            if cached:
                cache_hit = True
                timings["layout_ms"] = 0.0
                return layout_from_dict(cached), True

        layout_result = self._layout.detect_page(work_path, ctx.page_number, width, height)
        timings["layout_ms"] = layout_result.elapsed_ms
        if not layout_result.success or layout_result.data is None:
            raise RuntimeError(f"Layout detection failed on page {ctx.page_number}")

        layout_data = layout_result.data
        if self._enable_cache and self._cache:
            self._cache.put(
                ctx.document_id,
                ctx.page_number,
                "layout",
                work_hash,
                layout_to_dict(layout_data),
            )
        return layout_data, cache_hit

    def _extract_ocr(
        self,
        ctx: PageContext,
        work_path: Path,
        work_hash: str,
        width: float,
        height: float,
        text_regions: list,
        structure_result: StructurePageResult | None,
        timings: dict[str, float],
    ) -> tuple[OCRPageResult, bool]:
        cache_hit = False
        ocr_key = f"{work_hash}_{self._ocr.provider_name}"

        if structure_result and structure_result.paragraphs:
            ocr_page = self._ocr.from_structure(structure_result)
            timings["ocr_ms"] = 0.0
            return ocr_page, False

        if self._enable_cache and self._cache:
            cached = self._cache.get(ctx.document_id, ctx.page_number, "ocr", ocr_key)
            if cached:
                cache_hit = True
                timings["ocr_ms"] = 0.0
                return ocr_from_dict(cached), True

        ocr_result = self._ocr.extract_page(
            work_path,
            ctx.page_number,
            width,
            height,
            text_regions=text_regions,
        )
        timings["ocr_ms"] = ocr_result.elapsed_ms
        if not ocr_result.success or ocr_result.data is None:
            raise RuntimeError(f"OCR failed on page {ctx.page_number}")

        ocr_data = ocr_result.data
        if self._enable_cache and self._cache:
            self._cache.put(
                ctx.document_id,
                ctx.page_number,
                "ocr",
                ocr_key,
                ocr_to_dict(ocr_data),
            )
        return ocr_data, cache_hit

    @staticmethod
    def render_thumbnail(image_path: Path) -> bytes:
        return PaddleOCRService.render_thumbnail(image_path)
