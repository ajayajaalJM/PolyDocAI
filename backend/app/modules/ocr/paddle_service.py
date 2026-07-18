from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from PIL import Image

logger = structlog.get_logger(__name__)


@dataclass
class OCRWord:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]
    language: str | None = None


@dataclass
class OCRLine:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]
    words: list[OCRWord] = field(default_factory=list)


@dataclass
class OCRParagraph:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]
    lines: list[OCRLine] = field(default_factory=list)
    reading_order: int = 0


@dataclass
class OCRPageResult:
    page_number: int
    width: float
    height: float
    paragraphs: list[OCRParagraph] = field(default_factory=list)
    rotation: float = 0.0
    language: str | None = None


class PaddleOCRService:
    def __init__(self, lang: str = "en", use_gpu: bool = False) -> None:
        self._lang = lang
        self._use_gpu = use_gpu
        self._ocr = None
        self._available = False

    def initialize(self) -> None:
        try:
            from paddleocr import PaddleOCR

            device = "gpu:0" if self._use_gpu else "cpu"
            self._ocr = PaddleOCR(
                use_textline_orientation=True,
                lang=self._lang,
                device=device,
            )
            self._available = True
            logger.info("paddleocr_initialized", lang=self._lang, device=device)
        except ImportError:
            logger.warning("paddleocr_not_available", fallback="basic")
            self._available = False
        except Exception as exc:
            logger.warning("paddleocr_init_failed", error=str(exc), fallback="basic")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def extract_page(self, image_path: Path, page_number: int = 1) -> OCRPageResult:
        with Image.open(image_path) as img:
            width, height = img.size

        if self._available and self._ocr is not None:
            return self._extract_with_paddle(image_path, page_number, width, height)
        return self._extract_fallback(image_path, page_number, width, height)

    def _extract_with_paddle(
        self, image_path: Path, page_number: int, width: int, height: int
    ) -> OCRPageResult:
        assert self._ocr is not None
        from app.modules.ocr.geometry import detections_to_paragraphs

        start = time.perf_counter()
        raw = self._ocr.predict(str(image_path))
        detections: list[tuple[str, float, tuple[float, float, float, float]]] = []

        for page in raw:
            texts = self._ocr_field(page, "rec_texts")
            scores = self._ocr_field(page, "rec_scores")
            boxes = self._ocr_field(page, "rec_boxes")
            if not boxes:
                boxes = self._ocr_field(page, "rec_polys")

            for idx, text in enumerate(texts):
                if not text or not str(text).strip():
                    continue
                confidence = float(scores[idx]) if idx < len(scores) else 0.0
                bbox = self._normalize_bbox(boxes[idx] if idx < len(boxes) else None)
                if bbox[2] <= 0 or bbox[3] <= 0:
                    continue
                detections.append((str(text).strip(), confidence, bbox))

        paragraphs = detections_to_paragraphs(detections)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "ocr_page_complete",
            page=page_number,
            detections=len(detections),
            paragraphs=len(paragraphs),
            ms=elapsed,
        )
        return OCRPageResult(
            page_number=page_number,
            width=float(width),
            height=float(height),
            paragraphs=paragraphs,
        )

    @staticmethod
    def _ocr_field(data: object, key: str) -> list:
        try:
            value = data.get(key) if isinstance(data, dict) else data[key]
        except (AttributeError, KeyError, TypeError):
            return []
        if value is None:
            return []
        if hasattr(value, "tolist"):
            return value.tolist()
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    @staticmethod
    def _normalize_bbox(raw: object | None) -> tuple[float, float, float, float]:
        if raw is None:
            return (0.0, 0.0, 0.0, 0.0)
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        if not isinstance(raw, (list, tuple)) or not raw:
            return (0.0, 0.0, 0.0, 0.0)
        # [x1, y1, x2, y2]
        if len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw):
            x1, y1, x2, y2 = (float(v) for v in raw)
            return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))
        # polygon [[x,y], ...]
        if isinstance(raw[0], (list, tuple)):
            xs = [float(p[0]) for p in raw]
            ys = [float(p[1]) for p in raw]
            x1, y1 = min(xs), min(ys)
            return (x1, y1, max(xs) - x1, max(ys) - y1)
        return (0.0, 0.0, 0.0, 0.0)

    def _extract_fallback(
        self, image_path: Path, page_number: int, width: int, height: int
    ) -> OCRPageResult:
        logger.info("ocr_fallback_mode", page=page_number)
        return OCRPageResult(
            page_number=page_number,
            width=float(width),
            height=float(height),
            paragraphs=[
                OCRParagraph(
                    text="[OCR unavailable — install paddleocr for text extraction]",
                    confidence=0.0,
                    bbox=(40.0, 40.0, width - 80.0, 40.0),
                    reading_order=0,
                )
            ],
        )

    @staticmethod
    def render_thumbnail(image_path: Path, max_width: int = 200) -> bytes:
        with Image.open(image_path) as img:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            thumb = img.resize(new_size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            thumb.save(buf, format="PNG")
            return buf.getvalue()
