"""Logging utilities for khocr-gen."""

from __future__ import annotations

import logging

_DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure package logging once using a consistent format."""
    root_logger = logging.getLogger("khocr_gen")
    if root_logger.handlers:
        root_logger.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger rooted at khocr_gen."""
    return logging.getLogger(f"khocr_gen.{name}")
