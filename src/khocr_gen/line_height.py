"""Variable line-height sampling for synthetic line images.

All sampling functions accept an optional `random.Random` instance so callers
can get a reproducible sequence under a fixed seed; when omitted they fall
back to the module-level `random` (matching the rest of the rendering
pipeline's RNG usage).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .errors import InputValidationError

if TYPE_CHECKING:
    from .config import GenerationConfig

_LINE_HEIGHT_MODES = ("fixed", "variable", "bucketed")
_DISTRIBUTIONS = ("uniform", "triangular")
_FONT_SIZE_MODES = ("fixed", "proportional")
_PADDING_MODES = ("fixed", "random")


def _round_to_step(value: float, base: int, step: int) -> int:
    if step <= 0:
        return round(value)
    steps = round((value - base) / step)
    return int(base + steps * step)


def resolve_height_buckets(cfg: GenerationConfig) -> list[int]:
    """Return the sorted set of candidate heights for bucketed mode."""
    lo, hi = int(cfg.min_line_height), int(cfg.max_line_height)
    step = int(cfg.line_height_step) or 1
    buckets = list(range(lo, hi + 1, step))
    if not buckets or buckets[-1] != hi:
        buckets.append(hi)
    return buckets


def sample_line_height(cfg: GenerationConfig, rng: random.Random | None = None) -> int:
    """Sample a canvas height in pixels according to `cfg.line_height_mode`."""
    if cfg.line_height_mode == "fixed":
        return int(cfg.image_height)

    r = rng if rng is not None else random

    if cfg.line_height_mode == "bucketed":
        return int(r.choice(resolve_height_buckets(cfg)))

    # "variable"
    lo, hi = int(cfg.min_line_height), int(cfg.max_line_height)
    if cfg.line_height_distribution == "triangular":
        peak = cfg.default_line_height if cfg.default_line_height is not None else (lo + hi) / 2.0
        peak = max(lo, min(hi, float(peak)))
        value = r.triangular(lo, hi, peak)
    else:
        value = r.uniform(lo, hi)

    height = _round_to_step(value, lo, int(cfg.line_height_step))
    return int(max(lo, min(hi, height)))


def sample_font_scale(cfg: GenerationConfig, rng: random.Random | None = None) -> float:
    """Sample the glyph-height-to-canvas-height ratio for proportional font sizing."""
    if cfg.font_size_mode != "proportional":
        return 1.0
    r = rng if rng is not None else random
    lo, hi = float(cfg.min_font_scale), float(cfg.max_font_scale)
    if lo >= hi:
        return lo
    return r.uniform(lo, hi)


def sample_vertical_padding_ratio(cfg: GenerationConfig, rng: random.Random | None = None) -> float:
    """Sample top/bottom padding as a fraction of canvas height."""
    if cfg.vertical_padding_mode != "random":
        return 0.0
    r = rng if rng is not None else random
    lo, hi = float(cfg.min_vertical_padding_ratio), float(cfg.max_vertical_padding_ratio)
    if lo >= hi:
        return lo
    return r.uniform(lo, hi)


def validate_line_height_config(cfg: GenerationConfig) -> None:
    """Raise `InputValidationError` on an invalid variable-height configuration."""
    if cfg.line_height_mode not in _LINE_HEIGHT_MODES:
        raise InputValidationError(
            f"--line-height-mode must be one of {list(_LINE_HEIGHT_MODES)}, "
            f"got: {cfg.line_height_mode!r}"
        )
    if cfg.min_line_height <= 0:
        raise InputValidationError("--min-line-height must be > 0")
    if cfg.max_line_height < cfg.min_line_height:
        raise InputValidationError("--max-line-height must be >= --min-line-height")
    if cfg.line_height_step <= 0:
        raise InputValidationError("--line-height-step must be > 0")
    if cfg.line_height_distribution not in _DISTRIBUTIONS:
        raise InputValidationError(
            f"--line-height-distribution must be one of {list(_DISTRIBUTIONS)}, "
            f"got: {cfg.line_height_distribution!r}"
        )

    if cfg.font_size_mode not in _FONT_SIZE_MODES:
        raise InputValidationError(
            f"--font-size-mode must be one of {list(_FONT_SIZE_MODES)}, got: {cfg.font_size_mode!r}"
        )
    if cfg.min_font_scale <= 0:
        raise InputValidationError("--min-font-scale must be > 0")
    if cfg.max_font_scale < cfg.min_font_scale:
        raise InputValidationError("--max-font-scale must be >= --min-font-scale")

    if cfg.vertical_padding_mode not in _PADDING_MODES:
        raise InputValidationError(
            f"--vertical-padding-mode must be one of {list(_PADDING_MODES)}, "
            f"got: {cfg.vertical_padding_mode!r}"
        )
    if cfg.min_vertical_padding_ratio < 0:
        raise InputValidationError("--min-vertical-padding-ratio must be >= 0")
    if cfg.max_vertical_padding_ratio < cfg.min_vertical_padding_ratio:
        raise InputValidationError(
            "--max-vertical-padding-ratio must be >= --min-vertical-padding-ratio"
        )
    if cfg.max_vertical_padding_ratio >= 0.5:
        raise InputValidationError("--max-vertical-padding-ratio must be < 0.5")
