from __future__ import annotations

from pathlib import Path

import fitz
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

DEFAULT_DPI = 300


class PDFProcessor:
    @staticmethod
    def is_pdf(path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @staticmethod
    def rasterize(pdf_path: Path, output_dir: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf_path)
        paths: list[Path] = []
        try:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                out_path = output_dir / f"page_{i + 1:04d}.png"
                pix.save(str(out_path))
                paths.append(out_path)
            logger.info("pdf_rasterized", pages=len(paths), pdf=pdf_path.name, dpi=dpi)
        finally:
            doc.close()
        return paths

    @staticmethod
    def get_page_count(pdf_path: Path) -> int:
        doc = fitz.open(pdf_path)
        try:
            return len(doc)
        finally:
            doc.close()

    @staticmethod
    def extract_text_spans(pdf_path: Path, page_number: int) -> list[dict]:
        """Extract text with font metadata from born-digital PDFs."""
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
                    bbox = line.get("bbox", (0, 0, 0, 0))
                    primary = line_spans[0]
                    font_size = primary.get("size", 12.0)
                    font_name = primary.get("font", "Helvetica")
                    flags = int(primary.get("flags", 0))
                    is_bold = bool(flags & 2**4) or "bold" in font_name.lower()
                    is_italic = bool(flags & 2**1) or "italic" in font_name.lower() or "oblique" in font_name.lower()
                    c = primary.get("color", 0)
                    color = f"#{c:06x}" if isinstance(c, int) else "#000000"
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
        """Heuristic: PDF has extractable vector text."""
        if not PDFProcessor.is_pdf(pdf_path):
            return False
        spans = PDFProcessor.extract_text_spans(pdf_path, 1)
        total_chars = sum(len(s.get("text", "")) for s in spans)
        return len(spans) >= min_spans and total_chars >= min_chars

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
