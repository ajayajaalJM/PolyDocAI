from __future__ import annotations

import platform

import structlog

logger = structlog.get_logger(__name__)


def detect_device() -> str:
    """Auto-detect best available compute device: CUDA → MPS → CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            device = "cuda:0"
            logger.info("device_detected", device=device)
            return device
        if platform.system() == "Darwin" and torch.backends.mps.is_available():
            device = "mps"
            logger.info("device_detected", device=device)
            return device
    except ImportError:
        logger.warning("torch_not_installed", fallback="cpu")
    device = "cpu"
    logger.info("device_detected", device=device)
    return device


def paddle_device() -> str:
    device = detect_device()
    if device.startswith("cuda"):
        return "gpu"
    return "cpu"
