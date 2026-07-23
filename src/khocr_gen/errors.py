"""Application-level error types for khocr-gen."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ErrorContext:
    """Machine-readable context attached to domain-level exceptions."""

    code: str
    detail: str


class KhocrGenError(Exception):
    """Base application exception."""

    def __init__(self, message: str, *, code: str = "internal_error") -> None:
        super().__init__(message)
        self.context = ErrorContext(code=code, detail=message)


class InputValidationError(KhocrGenError):
    """Raised when user input is invalid or incomplete."""


class GenerationError(KhocrGenError):
    """Raised when dataset generation fails."""


class FontLoadError(KhocrGenError):
    """Raised when a font file cannot be loaded."""
