"""Execute pipeline stages with timing and structured logging."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import structlog

from app.pipeline.types import StageError, StageErrorKind, StageResult

logger = structlog.get_logger(__name__)
T = TypeVar("T")


def run_stage(
    stage: str,
    fn: Callable[[], T],
    *,
    provider: str | None = None,
    cache_hit: bool = False,
) -> StageResult[T]:
    start = time.perf_counter()
    try:
        data = fn()
        elapsed = (time.perf_counter() - start) * 1000
        result = StageResult(
            stage=stage,
            success=True,
            data=data,
            elapsed_ms=elapsed,
            provider=provider,
            cache_hit=cache_hit,
        )
        logger.info(
            "pipeline_stage_complete",
            stage=stage,
            provider=provider,
            elapsed_ms=round(elapsed, 2),
            cache_hit=cache_hit,
        )
        return result
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.exception("pipeline_stage_failed", stage=stage, error=str(exc))
        return StageResult(
            stage=stage,
            success=False,
            elapsed_ms=elapsed,
            provider=provider,
            errors=[
                StageError(
                    kind=StageErrorKind.FATAL,
                    message=str(exc),
                    stage=stage,
                )
            ],
        )
