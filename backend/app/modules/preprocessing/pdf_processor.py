from __future__ import annotations

from pathlib import Path

import fitz
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

DEFAULT_DPI = 300


def _scale_bbox(bbox: tuple[float, ...], scale: float) -> list[float]:
    return [float(bbox[0]) * scale, float(bbox[1]) * scale, float(bbox[2]) * scale, float(bbox[3]) * scale]


def _parse_span_color(value: object) -> str:
    if isinstance(value, int):
        return f"#{value:06x}"
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        r, g, b = value[:3]
        if all(isinstance(c, float) and c <= 1.0 for c in (r, g, b)):
            r, g, b = int(r * 255), int(g * 255), int(b * 255)
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"
    return "#000000"


class PDFProcessor:
    @staticmethod
    def is_pdf(path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @staticmethod
    def rasterize(pdf_path: Path, output_dir: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf_path)
        paths: list[Path] = []
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        try:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                out_path = output_dir / f"page_{i + 1:04d}.png"
                pix.save(str(out_path))
                paths.append(out_path)
            logger.info("pdf_rasterized", pages=len(paths), pdf=pdf_path.name, dpi=dpi)
        finally:
            doc.close()
        return paths

    @staticmethod
    def rasterize_text_free_page(
        pdf_path: Path,
        page_number: int,
        output_path: Path,
        dpi: int = DEFAULT_DPI,
    ) -> Path:
        """Render a PDF page with vector text removed (graphics/images preserved)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf_path)
        try:
            page = doc[page_number - 1]
            for block in page.get_text("blocks"):
                if len(block) < 7 or block[6] != 0:
                    continue
                rect = fitz.Rect(block[:4])
                page.add_redact_annot(rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            pix.save(str(output_path))
            return output_path
        finally:
            doc.close()

    @staticmethod
    def get_page_count(pdf_path: Path) -> int:
        doc = fitz.open(pdf_path)
        try:
            return len(doc)
        finally:
            doc.close()

    @staticmethod
    def extract_text_spans(pdf_path: Path, page_number: int, dpi: int = DEFAULT_DPI) -> list[dict]:
        """Extract text with font metadata from born-digital PDFs (bbox scaled to raster pixels)."""
        scale = dpi / 72.0
        doc = fitz.open(pdf_path)
        try:
            page = doc[page_number - 1]
            spans: list[dict] = []
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_spans = line.get("spans", [])
                    if not line_spans:
                        continue
                    line_text = "".join(s.get("text", "") for s in line_spans).strip()
                    if not line_text:
                        continue
                    bbox = _scale_bbox(tuple(line.get("bbox", (0, 0, 0, 0))), scale)
                    primary = line_spans[0]
                    font_size = float(primary.get("size", 12.0)) * scale
                    font_name = primary.get("font", "Helvetica")
                    flags = int(primary.get("flags", 0))
                    is_bold = bool(flags & 2**4) or "bold" in str(font_name).lower()
                    is_italic = (
                        bool(flags & 2**1)
                        or "italic" in str(font_name).lower()
                        or "oblique" in str(font_name).lower()
                    )
                    color = _parse_span_color(primary.get("color", 0))
                    spans.append(
                        {
                            "text": line_text,
                            "bbox": bbox,
                            "font_size": font_size,
                            "font_family": font_name.split("+")[-1] if font_name else None,
                            "color": color,
                            "font_weight": "bold" if is_bold else "normal",
                            "font_style": "italic" if is_italic else "normal",
                        }
                    )
            return spans
        finally:
            doc.close()

    @staticmethod
    def is_born_digital(pdf_path: Path, min_spans: int = 3, min_chars: int = 40) -> bool:
        """Heuristic: PDF has extractable vector text on most pages."""
        if not PDFProcessor.is_pdf(pdf_path):
            return False
        page_count = PDFProcessor.get_page_count(pdf_path)
        digital_pages = 0
        for page_num in range(1, page_count + 1):
            spans = PDFProcessor.extract_text_spans(pdf_path, page_num, dpi=72)
            total_chars = sum(len(s.get("text", "")) for s in spans)
            if len(spans) >= min_spans and total_chars >= min_chars:
                digital_pages += 1
        return digital_pages >= max(1, page_count // 2)

    @staticmethod
    def extract_embedded_fonts(pdf_path: Path, output_dir: Path) -> list[Path]:
        """Extract embedded font files for reconstruction."""
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        doc = fitz.open(pdf_path)
        try:
            for i in range(doc.xref_length()):
                try:
                    xref_type = doc.xref_get_key(i, "Type")
                    if xref_type[1] != "/Font":
                        continue
                    name = doc.xref_get_key(i, "BaseFont")[1].replace("/", "")
                    extracted = doc.extract_font(i)
                    if extracted and extracted.get("ext"):
                        out = output_dir / f"{name}{extracted['ext']}"
                        out.write_bytes(extracted["content"])
                        saved.append(out)
                except Exception:
                    continue
        finally:
            doc.close()
        return saved


class ImageProcessor:
    @staticmethod
    def prepare_image(source: Path, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "page_0001.png"
        with Image.open(source) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(out_path, format="PNG", dpi=(200, 200))
        return [out_path]
