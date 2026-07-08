from pathlib import Path

import numpy as np
from PIL import Image

from app.services.image_normalization.service import ImageNormalizationService


def test_normalization_produces_output(tmp_path: Path):
    img_path = tmp_path / "page.png"
    Image.fromarray(np.full((120, 200, 3), 255, dtype=np.uint8)).save(img_path)

    svc = ImageNormalizationService(enable_perspective=False)
    result = svc.normalize_page(img_path, tmp_path / "normalized", 1)
    assert result.success
    assert result.data is not None
    assert result.data.output_path.exists()
    assert result.data.width > 0
