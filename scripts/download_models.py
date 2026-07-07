#!/usr/bin/env python3
"""Download and cache ML model weights for PolyDoc AI."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download PolyDoc AI ML models")
    parser.add_argument(
        "--storage",
        default=str(Path(__file__).resolve().parents[1] / "storage" / "models"),
        help="Model cache directory",
    )
    args = parser.parse_args()
    models_dir = Path(args.storage)
    models_dir.mkdir(parents=True, exist_ok=True)

    print("Initializing PaddleOCR (downloads weights on first use)...")
    try:
        from paddleocr import PaddleOCR

        PaddleOCR(use_textline_orientation=True, lang="en", device="cpu")
        print("  PaddleOCR ready.")
    except ImportError:
        print("  PaddleOCR not installed. Run: pip install -e backend[ml]")

    print("Initializing PP-StructureV3...")
    try:
        from paddleocr import PPStructureV3

        PPStructureV3(lang="en", device="cpu")
        print("  PP-StructureV3 ready.")
    except ImportError:
        print("  PP-StructureV3 not available. Run: pip install -e backend[ml]")
    except Exception as exc:
        print(f"  PP-StructureV3 download failed: {exc}")

    try:
        from doclayout_yolo import YOLOv10

        YOLOv10.from_pretrained("juliozhao/DocLayout-YOLO-DocStructBench")
        print("  DocLayout-YOLO ready.")
    except ImportError:
        print("  doclayout-yolo not installed. Run: pip install -e backend[ml]")
    except Exception as exc:
        print(f"  DocLayout-YOLO download failed: {exc}")

    print(f"\nModels cached under: {models_dir}")


if __name__ == "__main__":
    main()
