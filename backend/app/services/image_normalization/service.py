"""Image normalization service — deskew, denoise, contrast, borders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import structlog
from PIL import Image

from app.pipeline.stage_runner import run_stage
from app.pipeline.types import StageResult

logger = structlog.get_logger(__name__)


@dataclass
class NormalizationResult:
    output_path: Path
    width: float
    height: float
    rotation_deg: float = 0.0
    perspective_corrected: bool = False
    borders_removed: bool = False
    denoised: bool = False
    contrast_enhanced: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


class ImageNormalizationService:
  """Prepare page images before layout/OCR. No OCR occurs before this stage completes."""

  def __init__(
      self,
      *,
      enable_deskew: bool = True,
      enable_denoise: bool = True,
      enable_contrast: bool = True,
      enable_border_removal: bool = True,
      enable_perspective: bool = True,
  ) -> None:
      self._enable_deskew = enable_deskew
      self._enable_denoise = enable_denoise
      self._enable_contrast = enable_contrast
      self._enable_border_removal = enable_border_removal
      self._enable_perspective = enable_perspective

  def normalize_page(
      self,
      image_path: Path,
      output_dir: Path,
      page_number: int,
  ) -> StageResult[NormalizationResult]:
      return run_stage(
          "image_normalization",
          lambda: self._normalize(image_path, output_dir, page_number),
          provider="opencv",
      )

  def _normalize(self, image_path: Path, output_dir: Path, page_number: int) -> NormalizationResult:
      output_dir.mkdir(parents=True, exist_ok=True)
      out_path = output_dir / f"page_{page_number:04d}_normalized.png"

      with Image.open(image_path) as pil_img:
          img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)

      rotation = 0.0
      perspective = False
      borders = False
      denoised = False
      contrast = False
      warnings: list[str] = []

      if self._enable_border_removal:
          trimmed, did_trim = self._remove_borders(img)
          if did_trim:
              img = trimmed
              borders = True

      if self._enable_perspective:
          corrected, did_perspective = self._correct_perspective(img)
          if did_perspective:
              img = corrected
              perspective = True

      if self._enable_deskew:
          deskewed, angle = self._deskew(img)
          if abs(angle) > 0.3:
              img = deskewed
              rotation = angle

      if self._enable_denoise:
          img = cv2.fastNlMeansDenoisingColored(img, None, 6, 6, 7, 21)
          denoised = True

      if self._enable_contrast:
          img = self._enhance_contrast(img)
          contrast = True

      rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
      Image.fromarray(rgb).save(out_path, format="PNG")
      h, w = img.shape[:2]

      logger.info(
          "image_normalized",
          page=page_number,
          rotation=round(rotation, 2),
          size=(w, h),
      )

      return NormalizationResult(
          output_path=out_path,
          width=float(w),
          height=float(h),
          rotation_deg=rotation,
          perspective_corrected=perspective,
          borders_removed=borders,
          denoised=denoised,
          contrast_enhanced=contrast,
          metadata={"warnings": warnings},
      )

  @staticmethod
  def _deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
      gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
      gray = cv2.bitwise_not(gray)
      thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
      coords = np.column_stack(np.where(thresh > 0))
      if len(coords) < 100:
          return image, 0.0
      angle = cv2.minAreaRect(coords)[-1]
      if angle < -45:
          angle = -(90 + angle)
      else:
          angle = -angle
      if abs(angle) < 0.3 or abs(angle) > 15:
          return image, 0.0
      h, w = image.shape[:2]
      center = (w // 2, h // 2)
      matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
      rotated = cv2.warpAffine(
          image,
          matrix,
          (w, h),
          flags=cv2.INTER_CUBIC,
          borderMode=cv2.BORDER_REPLICATE,
      )
      return rotated, float(angle)

  @staticmethod
  def _enhance_contrast(image: np.ndarray) -> np.ndarray:
      lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
      l_channel, a, b = cv2.split(lab)
      clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
      l_channel = clahe.apply(l_channel)
      merged = cv2.merge((l_channel, a, b))
      return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

  @staticmethod
  def _remove_borders(image: np.ndarray) -> tuple[np.ndarray, bool]:
      gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
      _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
      coords = cv2.findNonZero(thresh)
      if coords is None:
          return image, False
      x, y, w, h = cv2.boundingRect(coords)
      margin = 4
      x = max(0, x - margin)
      y = max(0, y - margin)
      w = min(image.shape[1] - x, w + margin * 2)
      h = min(image.shape[0] - y, h + margin * 2)
      if w < image.shape[1] * 0.85 or h < image.shape[0] * 0.85:
          return image[y : y + h, x : x + w], True
      return image, False

  @staticmethod
  def _correct_perspective(image: np.ndarray) -> tuple[np.ndarray, bool]:
      gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
      blur = cv2.GaussianBlur(gray, (5, 5), 0)
      edges = cv2.Canny(blur, 50, 150)
      contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
      h, w = image.shape[:2]
      page_area = h * w
      best: np.ndarray | None = None
      best_area = 0.0
      for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
          peri = cv2.arcLength(contour, True)
          approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
          if len(approx) != 4:
              continue
          area = cv2.contourArea(approx)
          if area < page_area * 0.5:
              continue
          if area > best_area:
              best_area = area
              best = approx.reshape(4, 2).astype(np.float32)
      if best is None:
          return image, False
      rect = np.zeros((4, 2), dtype=np.float32)
      s = best.sum(axis=1)
      rect[0] = best[np.argmin(s)]
      rect[2] = best[np.argmax(s)]
      diff = np.diff(best, axis=1)
      rect[1] = best[np.argmin(diff)]
      rect[3] = best[np.argmax(diff)]
      max_w = int(max(np.linalg.norm(rect[0] - rect[1]), np.linalg.norm(rect[2] - rect[3])))
      max_h = int(max(np.linalg.norm(rect[0] - rect[3]), np.linalg.norm(rect[1] - rect[2])))
      if max_w < w * 0.6 or max_h < h * 0.6:
          return image, False
      dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
      matrix = cv2.getPerspectiveTransform(rect, dst)
      warped = cv2.warpPerspective(image, matrix, (max_w, max_h))
      return warped, True
