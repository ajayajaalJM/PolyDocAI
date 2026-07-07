from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
import structlog
from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.models.document import Document, ImageBlock, TableBlock, TextBlock
from app.modules.reconstruction.text_compositor import (
    compose_translated_page,
    measure_strip_quality,
    pil_to_png_bytes,
    strip_text_from_page,
)
from app.modules.reconstruction.vector_pdf import VectorPDFRebuilder
from app.providers.fonts.manager import FontManager

logger = structlog.get_logger(__name__)

ALIGN_MAP = {
    "left": TA_LEFT,
    "center": TA_CENTER,
    "right": TA_RIGHT,
    "justify": TA_JUSTIFY,
}


class ReconstructionEngine:
    def __init__(self, font_manager: FontManager | None = None) -> None:
        self._fonts = font_manager or FontManager()

    def _font_dirs(self, document_id: str | None, storage_root: Path | None) -> tuple[str, ...]:
        if not document_id or not storage_root:
            return ()
        fonts_dir = storage_root / "fonts" / document_id
        if fonts_dir.is_dir():
            return (str(fonts_dir),)
        return ()

    def _backgrounds_dir(self, document_id: str, storage_root: Path) -> Path:
        return storage_root / "uploads" / document_id / "backgrounds"

    def _text_free_background_path(
        self,
        document_id: str,
        page_number: int,
        storage_root: Path,
    ) -> Path:
        return self._backgrounds_dir(document_id, storage_root) / f"page_{page_number:04d}.png"

    def _load_page_background(
        self,
        page,
        *,
        document_id: str | None,
        storage_root: Path | None,
        upload_path: Path | None = None,
        dpi: int = 300,
    ) -> Image.Image | None:
        if document_id and storage_root:
            bg_path = self._text_free_background_path(document_id, page.page_number, storage_root)
            if bg_path.exists():
                return Image.open(bg_path).convert("RGB")
        if upload_path and upload_path.suffix.lower() == ".pdf":
            if document_id and storage_root:
                bg_path = self._text_free_background_path(document_id, page.page_number, storage_root)
                if not bg_path.exists():
                    from app.modules.preprocessing.pdf_processor import PDFProcessor

                    try:
                        PDFProcessor.rasterize_text_free_page(
                            upload_path,
                            page.page_number,
                            bg_path,
                            dpi=dpi,
                        )
                        return Image.open(bg_path).convert("RGB")
                    except Exception as exc:
                        logger.debug("text_free_background_failed", error=str(exc))
        return None

    def _text_blocks(self, blocks: list) -> list[TextBlock]:
        return [b for b in blocks if isinstance(b, TextBlock)]

    def _table_blocks(self, blocks: list) -> list[TableBlock]:
        return [b for b in blocks if isinstance(b, TableBlock)]

    def render_stripped_page_png(
        self,
        page,
        storage_root: Path | None = None,
        *,
        document_id: str | None = None,
        upload_path: Path | None = None,
        dpi: int = 300,
    ) -> bytes:
        """Page raster with original text regions erased (graphics preserved)."""
        if not page.raster_path or not storage_root:
            raise ValueError("Page raster required for stripping")
        raster = storage_root / page.raster_path
        text_blocks = self._text_blocks(page.blocks)
        table_blocks = self._table_blocks(page.blocks)
        background = self._load_page_background(
            page,
            document_id=document_id,
            storage_root=storage_root,
            upload_path=upload_path,
            dpi=dpi,
        )
        img = strip_text_from_page(
            raster,
            text_blocks,
            table_blocks,
            background=background,
        )
        residual = measure_strip_quality(img, text_blocks, table_blocks)
        if residual > 0.12:
            logger.info(
                "strip_refine_pass",
                page=page.page_number,
                residual=round(residual, 3),
            )
            img = strip_text_from_page(
                raster,
                text_blocks,
                table_blocks,
                background=background,
                refine_passes=4,
                aggressive=True,
            )
        return pil_to_png_bytes(img)

    def _stripped_raster_path(
        self,
        document_id: str,
        page_number: int,
        storage_root: Path,
    ) -> Path:
        return (
            storage_root
            / "uploads"
            / document_id
            / "stripped"
            / f"page_{page_number:04d}.png"
        )

    def _load_stripped_background(
        self,
        document_id: str,
        page,
        storage_root: Path,
    ) -> Image.Image | None:
        stripped_path = self._stripped_raster_path(document_id, page.page_number, storage_root)
        if stripped_path.exists():
            return Image.open(stripped_path).convert("RGB")
        return None

    def _build_compose_background(
        self,
        page,
        raster: Path,
        text_blocks: list[TextBlock],
        table_blocks: list[TableBlock],
        *,
        document_id: str | None = None,
        storage_root: Path | None = None,
        upload_path: Path | None = None,
        dpi: int = 300,
    ) -> Image.Image:
        """Build a fresh text-free background from the original page (no stale cache)."""
        pdf_background = self._load_page_background(
            page,
            document_id=document_id,
            storage_root=storage_root,
            upload_path=upload_path,
            dpi=dpi,
        )
        background = strip_text_from_page(
            raster,
            text_blocks,
            table_blocks,
            background=pdf_background,
        )
        if measure_strip_quality(background, text_blocks, table_blocks) > 0.12:
            background = strip_text_from_page(
                raster,
                text_blocks,
                table_blocks,
                background=pdf_background,
                refine_passes=4,
                aggressive=True,
            )
        return background

    def render_page_png(
        self,
        page,
        *,
        use_translated: bool = True,
        storage_root: Path | None = None,
        document_id: str | None = None,
        upload_path: Path | None = None,
        dpi: int = 300,
        source_type: str | None = None,
        target_language: str | None = None,
    ) -> bytes:
        if not page.raster_path or not storage_root:
            raise ValueError("Page raster required for reconstruction")

        font_dirs = self._font_dirs(document_id, storage_root)

        if (
            source_type == "vector_pdf"
            and upload_path
            and upload_path.suffix.lower() == ".pdf"
            and use_translated
            and document_id
        ):
            rebuilder = VectorPDFRebuilder(
                font_dirs=font_dirs,
                shape_fn=self._fonts.shape_text,
                target_language=target_language,
            )
            pdf_bytes = rebuilder.rebuild_document_pdf(
                upload_path,
                Document(
                    id=document_id,
                    name=upload_path.name,
                    file_path="",
                    pages=[page],
                    target_language=target_language,
                ),
                use_translated=True,
                dpi=dpi,
            )
            if pdf_bytes:
                png = rebuilder.rasterize_page(pdf_bytes, page.page_number, dpi=dpi)
                if png:
                    return png

        raster = storage_root / page.raster_path
        text_blocks = self._text_blocks(page.blocks)
        table_blocks = self._table_blocks(page.blocks)
        background = self._build_compose_background(
            page,
            raster,
            text_blocks,
            table_blocks,
            document_id=document_id,
            storage_root=storage_root,
            upload_path=upload_path,
            dpi=dpi,
        )
        img = compose_translated_page(
            raster,
            text_blocks,
            use_translated=use_translated,
            shape_fn=self._fonts.shape_text,
            table_blocks=table_blocks,
            background=background,
            font_dirs=font_dirs,
            target_language=target_language,
            original_raster=raster,
        )
        return pil_to_png_bytes(img)

    def _draw_text_in_bbox(
        self,
        c: canvas.Canvas,
        block: TextBlock,
        text: str,
        x: float,
        y: float,
        box_w: float,
        box_h: float,
        page_height: float,
        page_raster: Path | None = None,
    ) -> None:
        """Legacy PDF path — prefer render_page_png for translated output."""
        text = self._fonts.shape_text(text, block.style.direction)
        font_size = block.style.font_size or 12
        font_name = self._fonts.resolve(block.style.font_family, block.language)

        lines = text.split("\n")
        while font_size > 6 and font_size * 1.25 * max(len(lines), 1) > box_h:
            font_size -= 0.5

        try:
            c.setFont(font_name, font_size)
        except Exception:
            c.setFont("Helvetica", font_size)

        color = block.style.color or "#000000"
        try:
            c.setFillColor(HexColor(color))
        except Exception:
            c.setFillColor(HexColor("#000000"))

        style = ParagraphStyle(
            name="block",
            fontName=font_name if font_name in ("Helvetica", "Times-Roman", "Courier") else "Helvetica",
            fontSize=font_size,
            leading=font_size * (block.style.line_height or 1.2) / font_size
            if block.style.line_height
            else font_size * 1.2,
            alignment=ALIGN_MAP.get(block.style.alignment or "left", TA_LEFT),
            textColor=HexColor(color),
        )
        para = Paragraph(text.replace("\n", "<br/>"), style)
        _, ph = para.wrap(box_w - 4, box_h)
        draw_y = y + box_h - ph - 2
        para.drawOn(c, x + 2, max(y + 2, draw_y))

    def rebuild_page_pdf(
        self,
        c: canvas.Canvas,
        page_width: float,
        page_height: float,
        blocks: list,
        use_translated: bool = True,
        storage_root: Path | None = None,
        page_raster: Path | None = None,
        composed_image: Image.Image | None = None,
        vector_mode: bool = False,
    ) -> None:
        c.setPageSize((page_width, page_height))

        if composed_image is not None:
            buf = BytesIO()
            composed_image.save(buf, format="PNG")
            buf.seek(0)
            from reportlab.lib.utils import ImageReader

            c.drawImage(ImageReader(buf), 0, 0, width=page_width, height=page_height)
            return

        if page_raster and page_raster.exists() and use_translated and not vector_mode:
            text_blocks = self._text_blocks(blocks)
            img = compose_translated_page(
                page_raster,
                text_blocks,
                use_translated=use_translated,
                shape_fn=self._fonts.shape_text,
                table_blocks=self._table_blocks(blocks),
                original_raster=page_raster,
            )
            self.rebuild_page_pdf(
                c,
                page_width,
                page_height,
                blocks,
                use_translated=use_translated,
                storage_root=storage_root,
                composed_image=img,
            )
            return

        if page_raster and page_raster.exists() and not vector_mode:
            try:
                c.drawImage(str(page_raster), 0, 0, width=page_width, height=page_height)
            except Exception as exc:
                logger.warning("page_raster_failed", error=str(exc))

        sorted_blocks = sorted(blocks, key=lambda b: (b.z_index, b.reading_order))
        for block in sorted_blocks:
            bbox = block.bbox
            x = bbox.x
            y = page_height - (bbox.y + bbox.height)
            box_w = bbox.width
            box_h = bbox.height

            if isinstance(block, TextBlock):
                text = block.translated_text if use_translated else block.original_text
                if use_translated and (not text or not str(text).strip()):
                    continue
                self._draw_text_in_bbox(c, block, text, x, y, box_w, box_h, page_height)

            elif isinstance(block, TableBlock):
                rows = block.translated_rows if use_translated and block.translated_rows else block.rows
                if rows:
                    row_h = box_h / max(len(rows), 1)
                    col_w = box_w / max(len(rows[0]), 1)
                    c.setFillColor(white)
                    c.rect(x, y, box_w, box_h, fill=1, stroke=0)
                    c.setStrokeColor(HexColor("#cccccc"))
                    for ri, row in enumerate(rows):
                        for ci, cell in enumerate(row):
                            cx = x + ci * col_w
                            cy = y + (len(rows) - ri - 1) * row_h
                            c.rect(cx, cy, col_w, row_h, stroke=1, fill=0)
                            c.setFont("Helvetica", 9)
                            c.setFillColor(HexColor("#000000"))
                            c.drawString(cx + 4, cy + row_h / 2 - 4, cell[:80])

    def render_document_pdf(
        self,
        document: Document,
        use_translated: bool = True,
        storage_root: Path | None = None,
    ) -> bytes:
        upload_path = None
        if storage_root and document.file_path:
            candidate = storage_root / document.file_path
            if candidate.exists():
                upload_path = candidate

        if (
            use_translated
            and document.metadata.source_type == "vector_pdf"
            and upload_path
            and upload_path.suffix.lower() == ".pdf"
        ):
            font_dirs = self._font_dirs(document.id, storage_root)
            rebuilder = VectorPDFRebuilder(
                font_dirs=font_dirs,
                shape_fn=self._fonts.shape_text,
                target_language=document.target_language,
            )
            vector_pdf = rebuilder.rebuild_document_pdf(
                upload_path,
                document,
                use_translated=True,
                dpi=300,
            )
            if vector_pdf:
                return vector_pdf

        buf = BytesIO()
        if not document.pages:
            c = canvas.Canvas(buf, pagesize=letter)
            c.drawString(inch, inch, "Empty document")
            c.save()
            return buf.getvalue()

        first = document.pages[0]
        c = canvas.Canvas(buf, pagesize=(first.width, first.height))

        for page in document.pages:
            if use_translated and page.translated_raster_path and storage_root:
                translated_path = storage_root / page.translated_raster_path
                if translated_path.exists():
                    c.setPageSize((page.width, page.height))
                    c.drawImage(
                        str(translated_path),
                        0,
                        0,
                        width=page.width,
                        height=page.height,
                        preserveAspectRatio=True,
                        anchor="sw",
                    )
                    c.showPage()
                    continue

            raster = None
            if page.raster_path and storage_root:
                raster = storage_root / page.raster_path
            font_dirs = self._font_dirs(document.id, storage_root)
            if use_translated and raster and raster.exists():
                text_blocks = self._text_blocks(page.blocks)
                upload_path = None
                if storage_root:
                    candidate = storage_root / document.file_path
                    if candidate.exists():
                        upload_path = candidate
                background = self._build_compose_background(
                    page,
                    raster,
                    text_blocks,
                    table_blocks,
                    document_id=document.id,
                    storage_root=storage_root,
                    upload_path=upload_path,
                    dpi=300,
                )
                img = compose_translated_page(
                    raster,
                    text_blocks,
                    use_translated=True,
                    shape_fn=self._fonts.shape_text,
                    table_blocks=self._table_blocks(page.blocks),
                    background=background,
                    font_dirs=font_dirs,
                    target_language=document.target_language,
                    original_raster=raster,
                )
                self.rebuild_page_pdf(
                    c,
                    page.width,
                    page.height,
                    page.blocks,
                    use_translated=use_translated,
                    storage_root=storage_root,
                    composed_image=img,
                )
                c.showPage()
                continue

            self.rebuild_page_pdf(
                c,
                page.width,
                page.height,
                page.blocks,
                use_translated=use_translated,
                storage_root=storage_root,
                page_raster=raster,
            )
            c.showPage()

        c.save()
        logger.info("pdf_reconstructed", document_id=document.id, pages=len(document.pages))
        return buf.getvalue()

    def render_single_page_pdf(
        self,
        page,
        *,
        use_translated: bool = True,
        storage_root: Path | None = None,
    ) -> bytes:
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(page.width, page.height))
        raster = None
        if page.raster_path and storage_root:
            raster = storage_root / page.raster_path
        self.rebuild_page_pdf(
            c,
            page.width,
            page.height,
            page.blocks,
            use_translated=use_translated,
            storage_root=storage_root,
            page_raster=raster,
        )
        c.save()
        return buf.getvalue()
