"""Structured pipeline stage results and error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class StageErrorKind(StrEnum):
    RECOVERABLE = "recoverable"
    FATAL = "fatal"


@dataclass
class StageError:
    kind: StageErrorKind
    message: str
    stage: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class StageResult(Generic[T]):
    stage: str
    success: bool
    data: T | None = None
    warnings: list[str] = field(default_factory=list)
    confidence: float = 1.0
    errors: list[StageError] = field(default_factory=list)
    elapsed_ms: float = 0.0
    cache_hit: bool = False
    provider: str | None = None

    @property
    def fatal(self) -> bool:
        return any(e.kind == StageErrorKind.FATAL for e in self.errors)

    def ok(self, data: T, **kwargs: object) -> StageResult[T]:
        return StageResult(stage=self.stage, success=True, data=data, **kwargs)  # type: ignore[arg-type]

    def fail(self, message: str, *, fatal: bool = True, **kwargs: object) -> StageResult[T]:
        kind = StageErrorKind.FATAL if fatal else StageErrorKind.RECOVERABLE
        errors = list(self.errors)
        errors.append(StageError(kind=kind, message=message, stage=self.stage))
        return StageResult(
            stage=self.stage,
            success=False,
            data=self.data,
            errors=errors,
            **kwargs,  # type: ignore[arg-type]
        )
