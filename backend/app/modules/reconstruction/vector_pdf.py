"""Native vector PDF reconstruction — redact source text, insert translations."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Callable

import fitz
import structlog

from app.models.document import BoundingBox, Document, TableBlock, TextBlock, TextStyle
from app.modules.reconstruction.script_fonts import (
    needs_arabic_rendering,
    parse_font_path,
    resolve_arabic_font_path,
)
from app.providers.fonts.manager import FontManager

logger = structlog.get_logger(__name__)

_ALIGN = {
    "left": fitz.TEXT_ALIGN_LEFT,
    "center": fitz.TEXT_ALIGN_CENTER,
    "right": fitz.TEXT_ALIGN_RIGHT,
    "justify": fitz.TEXT_ALIGN_JUSTIFY,
}


def _hex_to_rgb_float(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    if len(color) == 6:
        return (
            int(color[0:2], 16) / 255.0,
            int(color[2:4], 16) / 255.0,
            int(color[4:6], 16) / 255.0,
        )
    return (0.0, 0.0, 0.0)


class VectorPDFRebuilder:
    """Rebuild translated PDFs by redacting vector text and inserting translations."""

    def __init__(
        self,
        font_dirs: tuple[str, ...] = (),
        shape_fn: Callable[[str, str], str] | None = None,
        target_language: str | None = None,
    ) -> None:
        self._font_dirs = font_dirs
        self._shape_fn = shape_fn or (lambda t, _d: t)
        self._target_language = target_language

    def _pixel_to_pdf_rect(
        self,
        bbox,
        page_height_px: float,
        scale: float,
    ) -> fitz.Rect:
        x0 = bbox.x / scale
        y0 = bbox.y / scale
        x1 = (bbox.x + bbox.width) / scale
        y1 = (bbox.y + bbox.height) / scale
        pdf_y0 = page_height_px / scale - y1
        pdf_y1 = page_height_px / scale - y0
        return fitz.Rect(x0, pdf_y0, x1, pdf_y1)

    def _resolve_fontfile(self, block: TextBlock, text: str) -> str | None:
        use_arabic = needs_arabic_rendering(text, self._target_language, block.style)
        if use_arabic:
            prefer_serif = bool(
                block.style.font_family
                and any(k in block.style.font_family.lower() for k in ("serif", "times", "naskh"))
            )
            resolved = resolve_arabic_font_path(
                font_weight=block.style.font_weight,
                prefer_serif=prefer_serif,
                font_dirs=self._font_dirs,
            )
            if resolved:
                base, _ = parse_font_path(resolved)
                return base

        if self._font_dirs:
            d = Path(self._font_dirs[0])
            if d.is_dir():
                for f in d.iterdir():
                    if f.suffix.lower() in (".ttf", ".otf"):
                        return str(f)
        return None

    def _insert_text(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        block: TextBlock,
        text: str,
    ) -> None:
        use_arabic = needs_arabic_rendering(text, self._target_language, block.style)
        direction = "rtl" if use_arabic else (block.style.direction or "ltr")
        shaped = self._shape_fn(str(text), direction)
        fs = (block.style.font_size or 12) / (300 / 72.0)
        color = _hex_to_rgb_float(block.style.color or "#000000")
        align = _ALIGN.get(block.style.alignment or ("right" if use_arabic else "left"), fitz.TEXT_ALIGN_LEFT)

        fontfile = self._resolve_fontfile(block, text)
        if fontfile:
            page.insert_textbox(
                rect,
                shaped,
                fontname="custom",
                fontfile=fontfile,
                fontsize=fs,
                color=color,
                align=align,
            )
            return

        fontname = "times" if block.style.font_family and "times" in block.style.font_family.lower() else "helv"
        page.insert_textbox(
            rect,
            shaped,
            fontname=fontname,
            fontsize=fs,
            color=color,
            align=align,
        )

    def rebuild_document_pdf(
        self,
        pdf_path: Path,
        document: Document,
        *,
        use_translated: bool = True,
        dpi: int = 300,
    ) -> bytes | None:
        if not pdf_path.exists():
            return None

        try:
            src = fitz.open(pdf_path)
            out = fitz.open()
            scale = dpi / 72.0

            for page_model in document.pages:
                pno = page_model.page_number - 1
                if pno >= len(src):
                    break
                src_page = src[pno]
                out_page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
                out_page.show_pdf_page(out_page.rect, src, pno)

                for block in src_page.get_text("blocks"):
                    if len(block) >= 7 and block[6] == 0:
                        out_page.add_redact_annot(fitz.Rect(block[:4]))
                out_page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                for block in sorted(page_model.blocks, key=lambda b: b.reading_order):
                    if not isinstance(block, TextBlock):
                        continue
                    text = (
                        block.translated_text
                        if use_translated and block.translated_text
                        else block.original_text
                    )
                    if use_translated and (not text or not str(text).strip()):
                        continue
                    if not str(text).strip():
                        continue

                    rect = self._pixel_to_pdf_rect(block.bbox, page_model.height, scale)
                    self._insert_text(out_page, rect, block, str(text))

                for block in page_model.blocks:
                    if not isinstance(block, TableBlock):
                        continue
                    rows = (
                        block.translated_rows
                        if use_translated and block.translated_rows
                        else block.rows
                    )
                    if not rows:
                        continue
                    num_rows = len(rows)
                    num_cols = max(len(r) for r in rows)
                    cell_w = block.bbox.width / max(num_cols, 1)
                    cell_h = block.bbox.height / max(num_rows, 1)
                    for ri, row in enumerate(rows):
                        for ci, cell in enumerate(row):
                            cell_text = str(cell).strip()
                            if not cell_text:
                                continue
                            cell_bbox = BoundingBox(
                                x=block.bbox.x + ci * cell_w,
                                y=block.bbox.y + ri * cell_h,
                                width=cell_w,
                                height=cell_h,
                            )
                            rect = self._pixel_to_pdf_rect(cell_bbox, page_model.height, scale)
                            cell_style = TextStyle(font_size=10)
                            if block.cells:
                                for c in block.cells:
                                    if c.row == ri and c.col == ci and c.style:
                                        cell_style = c.style
                                        break
                            stub = TextBlock(
                                page_number=page_model.page_number,
                                bbox=cell_bbox,
                                original_text=cell_text,
                                style=cell_style,
                            )
                            self._insert_text(out_page, rect, stub, cell_text)

            buf = BytesIO()
            out.save(buf, garbage=4, deflate=True)
            src.close()
            out.close()
            logger.info("vector_pdf_rebuilt", document_id=document.id, pages=len(document.pages))
            return buf.getvalue()
        except Exception as exc:
            logger.warning("vector_pdf_rebuild_failed", error=str(exc))
            return None

    def rasterize_page(
        self,
        pdf_bytes: bytes,
        page_number: int,
        dpi: int = 300,
    ) -> bytes | None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc[page_number - 1]
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            png = pix.tobytes("png")
            doc.close()
            return png
        except Exception as exc:
            logger.warning("vector_rasterize_failed", error=str(exc))
            return None
