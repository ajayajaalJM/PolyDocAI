from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class LayoutElementType(StrEnum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    FIGURE = "figure"
    IMAGE = "image"
    LOGO = "logo"
    HEADER = "header"
    FOOTER = "footer"
    CAPTION = "caption"
    SIDEBAR = "sidebar"
    QUOTE = "quote"
    UNKNOWN = "unknown"


@dataclass
class LayoutRegion:
    element_type: LayoutElementType
    confidence: float
    bbox: tuple[float, float, float, float]
    reading_order: int = 0


@dataclass
class LayoutPageResult:
    page_number: int
    width: float
    height: float
    regions: list[LayoutRegion] = field(default_factory=list)


class DocLayoutService:
    def __init__(self, device: str = "cpu", confidence: float = 0.2, imgsz: int = 1024) -> None:
        self._device = device
        self._confidence = confidence
        self._imgsz = imgsz
        self._model = None
        self._available = False

    def initialize(self) -> None:
        try:
            from doclayout_yolo import YOLOv10
            from huggingface_hub import hf_hub_download

            weights = hf_hub_download(
                "juliozhao/DocLayout-YOLO-DocStructBench",
                "doclayout_yolo_docstructbench_imgsz1024.pt",
            )
            self._model = YOLOv10(weights)
            self._available = True
            logger.info("doclayout_initialized", device=self._device, weights=weights)
        except ImportError:
            logger.warning("doclayout_not_available", fallback="basic")
            self._available = False
        except Exception as exc:
            logger.warning("doclayout_init_failed", error=str(exc), fallback="basic")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def detect_page(
        self, image_path: Path, page_number: int, width: float, height: float
    ) -> LayoutPageResult:
        if self._available and self._model is not None:
            return self._detect_with_yolo(image_path, page_number, width, height)
        return self._detect_fallback(page_number, width, height)

    def _detect_with_yolo(
        self, image_path: Path, page_number: int, width: float, height: float
    ) -> LayoutPageResult:
        assert self._model is not None
        start = time.perf_counter()
        device = self._device if self._device != "mps" else "cpu"
        results = self._model.predict(
            str(image_path),
            imgsz=self._imgsz,
            conf=self._confidence,
            device=device,
        )
        regions: list[LayoutRegion] = []
        if results:
            result = results[0]
            boxes = result.boxes
            if boxes is not None:
                for idx, box in enumerate(boxes):
                    xyxy = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = xyxy
                    cls_id = int(box.cls[0].item()) if box.cls is not None else 0
                    conf = float(box.conf[0].item()) if box.conf is not None else 0.0
                    element_type = self._map_class(cls_id, result.names)
                    regions.append(
                        LayoutRegion(
                            element_type=element_type,
                            confidence=conf,
                            bbox=(x1, y1, x2 - x1, y2 - y1),
                            reading_order=idx,
                        )
                    )

        elapsed = (time.perf_counter() - start) * 1000
        logger.info("layout_page_complete", page=page_number, regions=len(regions), ms=elapsed)
        return LayoutPageResult(
            page_number=page_number,
            width=width,
            height=height,
            regions=sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0])),
        )

    @staticmethod
    def _map_class(cls_id: int, names: dict | None) -> LayoutElementType:
        if names and cls_id in names:
            name = str(names[cls_id]).lower()
            mapping = {
                "title": LayoutElementType.HEADING,
                "text": LayoutElementType.PARAGRAPH,
                "plain text": LayoutElementType.PARAGRAPH,
                "paragraph": LayoutElementType.PARAGRAPH,
                "table": LayoutElementType.TABLE,
                "list": LayoutElementType.LIST,
                "figure": LayoutElementType.FIGURE,
                "image": LayoutElementType.IMAGE,
                "logo": LayoutElementType.LOGO,
                "header": LayoutElementType.HEADER,
                "footer": LayoutElementType.FOOTER,
                "caption": LayoutElementType.CAPTION,
                "sidebar": LayoutElementType.SIDEBAR,
                "quote": LayoutElementType.QUOTE,
            }
            for key, val in mapping.items():
                if key in name:
                    return val
        return LayoutElementType.UNKNOWN

    def _detect_fallback(self, page_number: int, width: float, height: float) -> LayoutPageResult:
        margin = 40.0
        return LayoutPageResult(
            page_number=page_number,
            width=width,
            height=height,
            regions=[
                LayoutRegion(
                    element_type=LayoutElementType.PARAGRAPH,
                    confidence=1.0,
                    bbox=(margin, margin, width - 2 * margin, height - 2 * margin),
                    reading_order=0,
                )
            ],
        )
