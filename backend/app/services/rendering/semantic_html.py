"""Semantic HTML renderer — positioned DOM blocks."""

from __future__ import annotations

import html
from pathlib import Path

from app.models.document import Document, ImageBlock, TableBlock, TextBlock
from app.providers.rendering.base import RenderOptions, RenderResult


def _block_text(block: TextBlock, use_translated: bool) -> str:
    if use_translated and block.translated_text:
        return block.translated_text
    return block.original_text


def _text_style_css(block: TextBlock) -> str:
    parts = [
        "position:absolute",
        "overflow:hidden",
        f"left:{block.bbox.x}px",
        f"top:{block.bbox.y}px",
        f"width:{block.bbox.width}px",
        f"min-height:{block.bbox.height}px",
    ]
    style = block.style
    if style.font_size:
        parts.append(f"font-size:{style.font_size}px")
    if style.font_family:
        parts.append(f"font-family:{html.escape(style.font_family)}")
    if style.font_weight:
        parts.append(f"font-weight:{style.font_weight}")
    if style.color:
        parts.append(f"color:{style.color}")
    if style.background_color:
        parts.append(f"background-color:{style.background_color}")
    parts.append(f"text-align:{style.alignment}")
    if style.direction == "rtl":
        parts.append("direction:rtl")
    return ";".join(parts)


class SemanticHTMLRenderer:
    format = "html"

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root

    def render(self, document: Document, options: RenderOptions) -> RenderResult:
        use_translated = options.use_translated
        root = options.storage_root or self._storage_root
        parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='utf-8'/>",
            f"<title>{html.escape(document.name)}</title>",
            "<style>",
            "body{font-family:Georgia,serif;margin:2rem;background:#f0f0f0;}",
            ".doc-title{font-size:1.75rem;margin-bottom:2rem;}",
            ".page{position:relative;background:#fff;margin:2rem auto;box-shadow:0 2px 16px rgba(0,0,0,.1);}",
            ".block-text{white-space:pre-wrap;line-height:1.25;}",
            ".block-image img{display:block;width:100%;height:100%;object-fit:contain;}",
            ".block-table{position:absolute;border-collapse:collapse;font-size:12px;}",
            ".block-table td,.block-table th{border:1px solid #ccc;padding:4px 6px;}",
            "</style>",
            "</head>",
            "<body>",
            f"<h1 class='doc-title'>{html.escape(document.name)}</h1>",
        ]

        for page in document.pages:
            parts.append(
                f"<section class='page' data-page='{page.page_number}' "
                f"style='width:{page.width}px;height:{page.height}px'>"
            )
            for block in sorted(page.blocks, key=lambda b: b.reading_order):
                if isinstance(block, TextBlock):
                    tag = "h2" if block.layout_type == "heading" else "p"
                    if block.layout_type in ("header", "footer"):
                        tag = "span"
                    text = html.escape(_block_text(block, use_translated))
                    parts.append(
                        f"<{tag} class='block-text' data-block-id='{block.id}' "
                        f"style='{_text_style_css(block)}'>{text}</{tag}>"
                    )
                elif isinstance(block, ImageBlock) and block.asset_path:
                    asset = root / block.asset_path
                    src = block.asset_path
                    if asset.exists():
                        import base64

                        encoded = base64.b64encode(asset.read_bytes()).decode("ascii")
                        ext = asset.suffix.lower().lstrip(".") or "png"
                        src = f"data:image/{ext};base64,{encoded}"
                    parts.append(
                        f"<div class='block-image' data-block-id='{block.id}' "
                        f"style='position:absolute;left:{block.bbox.x}px;top:{block.bbox.y}px;"
                        f"width:{block.bbox.width}px;height:{block.bbox.height}px'>"
                        f"<img src='{src}' alt=''/></div>"
                    )
                elif isinstance(block, TableBlock):
                    rows = block.translated_rows if use_translated and block.translated_rows else block.rows
                    parts.append(
                        f"<table class='block-table' data-block-id='{block.id}' "
                        f"style='left:{block.bbox.x}px;top:{block.bbox.y}px;"
                        f"width:{block.bbox.width}px'>"
                    )
                    for row in rows:
                        parts.append("<tr>")
                        for cell in row:
                            parts.append(f"<td>{html.escape(cell)}</td>")
                        parts.append("</tr>")
                    parts.append("</table>")
            parts.append("</section>")

        parts.extend(["</body>", "</html>"])
        suffix = "translated" if use_translated else "original"
        return RenderResult(
            content="\n".join(parts).encode("utf-8"),
            mime_type="text/html",
            filename=f"{Path(document.name).stem}_{suffix}_semantic.html",
        )
