"""PIL compatibility shims for resampling across Pillow versions."""

from __future__ import annotations

from typing import Any

from PIL import Image


def _resolve_resample(name: str) -> Any:
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        value = getattr(resampling, name, None)
        if value is not None:
            return value

    legacy_value = getattr(Image, name, None)
    if legacy_value is not None:
        return legacy_value

    raise AttributeError(f"PIL.Image does not define resample mode '{name}'")


RESAMPLE_BILINEAR: Any = _resolve_resample("BILINEAR")
RESAMPLE_BICUBIC: Any = _resolve_resample("BICUBIC")
