from __future__ import annotations


class TranslationError(Exception):
    """Translation could not be completed."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
