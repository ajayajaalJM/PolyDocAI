"""Per-page pipeline executing all analysis stages in order."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import structlog

from app.models.document import Page
from app.modules.layout.doclayout_service import LayoutPageResult
from app.modules.ocr.paddle_service import OCRPageResult, PaddleOCRService
from app.modules.ocr.structure_service import StructurePageResult
from app.modules.pipeline.model_builder import DocumentModelBuilder
from app.modules.preprocessing.image_extractor import crop_region
from app.modules.preprocessing.pdf_processor import PDFProcessor
from app.pipeline.context import PageContext
from app.pipeline.types import StageResult
from app.services.image_normalization.service import ImageNormalizationService, NormalizationResult
from app.services.layout.service import LayoutService
from app.services.ocr.service import OCRService
from app.services.vision.service import VisionPageResult, VisionService

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
    ) -> None:
        self._normalization = normalization
        self._layout = layout
        self._vision = vision
        self._ocr = ocr
        self._model_builder = model_builder

    def process_page(
        self,
        ctx: PageContext,
        *,
        thumbnail_path: str | None = None,
        raster_path: str | None = None,
        pdf_spans: list[dict] | None = None,
        structure_tables: list | None = None,
        save_asset_cb=None,
    ) -> PagePipelineResult:
        warnings: list[str] = []
        timings: dict[str, float] = {}

        norm_result = self._normalization.normalize_page(
            ctx.source_path,
            ctx.source_path.parent / "normalized",
            ctx.page_number,
        )
        timings["normalization_ms"] = norm_result.elapsed_ms
        if not norm_result.success or norm_result.data is None:
            warnings.append(f"Normalization failed: {norm_result.errors}")
            work_path = ctx.source_path
            norm_data = None
        else:
            work_path = norm_result.data.output_path
            norm_data = norm_result.data
            ctx.normalized_path = work_path

        with __import__("PIL").Image.open(work_path) as img:
            width, height = float(img.size[0]), float(img.size[1])

        layout_result = self._layout.detect_page(work_path, ctx.page_number, width, height)
        timings["layout_ms"] = layout_result.elapsed_ms
        if not layout_result.success or layout_result.data is None:
            raise RuntimeError(f"Layout detection failed on page {ctx.page_number}")

        layout_data = layout_result.data
        text_regions = self._layout.text_regions(layout_data)

        vision_result = self._vision.analyze_page(layout_data, width)
        timings["vision_ms"] = vision_result.elapsed_ms
        vision_data = vision_result.data if vision_result.success else None
        if vision_result.warnings:
            warnings.extend(vision_result.warnings)

        structure_result: StructurePageResult | None = None
        if self._layout.provider_name == "pp_structure":
            structure_result = self._layout.get_structure_tables(work_path, ctx.page_number)
            if structure_result and structure_result.tables:
                structure_tables = structure_result.tables

        if structure_result and structure_result.paragraphs:
            from app.modules.ocr.structure_service import StructurePageResult as SPR

            sr: SPR = structure_result
            ocr_page = self._ocr.from_structure(sr)
            ocr_result = StageResult(
                stage="ocr",
                success=True,
                data=ocr_page,
                provider="pp_structure",
                elapsed_ms=0.0,
            )
        else:
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
        )

    @staticmethod
    def render_thumbnail(image_path: Path) -> bytes:
        return PaddleOCRService.render_thumbnail(image_path)
