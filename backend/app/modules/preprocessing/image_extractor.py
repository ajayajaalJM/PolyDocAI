"""Extract image regions from page rasters."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def crop_region(image_path: Path, bbox: tuple[float, float, float, float]) -> bytes:
    x, y, w, h = bbox
    with Image.open(image_path) as img:
        left = max(0, int(x))
        top = max(0, int(y))
        right = min(img.width, int(x + w))
        bottom = min(img.height, int(y + h))
        if right <= left or bottom <= top:
            return b""
        cropped = img.crop((left, top, right, bottom))
        if cropped.mode not in ("RGB", "RGBA"):
            cropped = cropped.convert("RGB")
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()


def extract_pdf_embedded_images(pdf_path: Path, output_dir: Path) -> dict[int, list[tuple[bytes, tuple[float, float, float, float]]]]:
    """Extract embedded images from PDF pages with approximate positions."""
    import fitz

    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, list[tuple[bytes, tuple[float, float, float, float]]]] = {}
    doc = fitz.open(pdf_path)
    try:
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            images: list[tuple[bytes, tuple[float, float, float, float]]] = []
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base = doc.extract_image(xref)
                    if not base or not base.get("image"):
                        continue
                    rects = page.get_image_rects(xref)
                    for rect in rects:
                        bbox = (rect.x0, rect.y0, rect.x1 - rect.x0, rect.y1 - rect.y0)
                        images.append((base["image"], bbox))
                except Exception:
                    continue
            if images:
                result[page_num] = images
    finally:
        doc.close()
    return result
