"""Re-read typography from the original page raster before drawing translations."""

from __future__ import annotations

from pathlib import Path

from app.models.document import TextBlock, TextStyle
from app.modules.preprocessing.style_analyzer import infer_style_from_image


def sync_compose_style(
    block: TextBlock,
    original_raster: Path | None,
    *,
    target_language: str | None = None,
) -> TextStyle:
    """
    Return a style for composition that matches the original region's appearance
    while keeping target-script font family and direction from the block.
    """
    from app.modules.reconstruction.script_fonts import map_font_family_for_target

    base = block.style.model_copy(deep=True)
    if original_raster is None or not original_raster.exists():
        return base

    bbox = (
        block.bbox.x,
        block.bbox.y,
        block.bbox.width,
        block.bbox.height,
    )
    sampled = infer_style_from_image(
        original_raster,
        bbox,
        block.layout_type,
        block.bbox.x + block.bbox.width,
        block.language,
    )

    base.font_size = sampled.font_size or base.font_size
    base.color = sampled.color or base.color
    base.background_color = sampled.background_color or base.background_color
    base.font_weight = sampled.font_weight or base.font_weight
    base.line_height = sampled.line_height or base.line_height
    if not base.alignment:
        base.alignment = sampled.alignment

    if target_language:
        mapped = map_font_family_for_target(
            sampled.font_family or base.font_family,
            target_language,
            base.font_weight,
        )
        if mapped:
            base.font_family = mapped

    return base
