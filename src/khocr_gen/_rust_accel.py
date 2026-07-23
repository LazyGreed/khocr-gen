"""Rust acceleration backend for khocr-gen.

This module wraps the native `_rust_accel` extension (built via maturin/PyO3).
If the native extension is not available, pure-Python fallbacks from the augmentation, fonts, and rendering modules are used instead.

Usage::

    from khocr_gen._rust_accel import (
        apply_sauvola, apply_blur,
        RustFontManager, FontFace, split_text_spans,
        estimate_bg, image_is_blank, write_image,
        HAS_RUST_ACCEL,
    )
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger("khocr_gen._rust_accel")

# ── Try to load the native Rust extension ──────────────────────────────────────

_native: Any = None

try:
    import _rust_accel as _native

    HAS_RUST_ACCEL = True
except ImportError:
    HAS_RUST_ACCEL = False
    _LOGGER.info("Rust extension not available, using pure-Python fallbacks.")


# ── Re-export flag ─────────────────────────────────────────────────────────────


def _log_available() -> None:
    if HAS_RUST_ACCEL:
        try:
            ver: str = getattr(_native, "__version__", "unknown")
        except Exception:
            ver = "unknown"
        _LOGGER.info("Rust acceleration enabled (native _rust_accel v%s)", ver)
    else:
        _LOGGER.info("Rust acceleration NOT available.")


# ══════════════════════════════════════════════════════════════════════════════════
# Augmentation functions
# ══════════════════════════════════════════════════════════════════════════════════

# Each entry: (function_name, has_rgb_variant)
_AUG_FUNCTIONS: list[tuple[str, bool]] = [
    ("apply_sauvola", False),
    ("apply_geo_warp", False),
    ("apply_vertical_crop", False),
    ("apply_blur", False),
    ("apply_salt_pepper", False),
    ("apply_background_texture", False),
    ("apply_jpeg_compression", False),
    ("apply_rotation", False),
    ("apply_lowdpi", False),
    ("apply_oversample", False),
    ("apply_perspective", False),
    ("apply_elastic", False),
    ("apply_random_crop", False),
    ("apply_online_blur", False),
    ("apply_online_noise", False),
    ("apply_reverse", True),
    ("apply_brightness_contrast", True),
    ("apply_pixelation", False),
    ("apply_gradient_illumination", False),
    ("apply_morphological", False),
    ("apply_anisotropic_dilation", False),
    ("apply_hsv", True),  # RGB-only in Rust
]


def _get_rust_aug_fn(name: str) -> Callable[..., Any] | None:
    """Return the native Rust augmentation function by name, or None."""
    if not HAS_RUST_ACCEL:
        return None
    assert _native is not None
    return getattr(_native, f"{name}_rust", None)


def _make_aug_fallback(name: str) -> Callable[..., Any]:
    """Create a fallback that delegates to the Python augmentation module."""

    def _fallback(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
        from khocr_gen.augmentation import AUG_METHODS

        fn = AUG_METHODS.get(name)
        if fn is None:
            return img
        return fn(img, intensity, **kwargs)

    _fallback.__name__ = name
    _fallback.__qualname__ = name
    return _fallback


def _export_aug_functions() -> None:
    """Populate the module globals with augmentation functions.

    For each augmentation method, the Rust variant is preferred when available;
    otherwise the pure-Python fallback is used.

    Grayscale-only methods dispatch directly.
    Methods with an RGB variant (`brightness_contrast`, `hsv`) are wrapped to handle both grayscale and RGB input arrays.
    """
    g = globals()

    for name, has_rgb in _AUG_FUNCTIONS:
        rust_fn = _get_rust_aug_fn(name)
        rust_rgb_fn: Callable[..., Any] | None = (
            _get_rust_aug_fn(f"{name}_rgb") if has_rgb else None
        )

        if has_rgb and HAS_RUST_ACCEL and (rust_fn is not None or rust_rgb_fn is not None):
            # Wrap to auto-detect channel count and dispatch.
            # Rust RGB functions return flat (h, w*3) 2D arrays; reshape to (h, w, 3).
            _gray_fn = rust_fn
            _rgb_fn = rust_rgb_fn

            # Capture the fallback factory by value so we can safely delete it later
            _fallback_factory = _make_aug_fallback

            def _make_rgb_wrapper(
                gray_fn: Callable[..., Any] | None,
                rgb_fn: Callable[..., Any] | None,
                fallback_name: str,
                fallback_factory: Callable[..., Any],
            ) -> Callable[..., Any]:
                def _wrapper(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
                    if img.ndim == 3 and img.shape[2] == 3:
                        if rgb_fn is not None:
                            h, w = img.shape[:2]
                            result = rgb_fn(img, intensity)
                            # Rust RGB fns return flat (h, w*3); reshape to (h, w, 3)
                            if result.ndim == 2 and result.shape[1] == w * 3:
                                return result.reshape(h, w, 3)
                            return result
                        if gray_fn is not None:
                            channels = [
                                gray_fn(np.ascontiguousarray(img[:, :, c]), intensity)
                                for c in range(3)
                            ]
                            return np.stack(channels, axis=-1)
                        return fallback_factory(fallback_name)(img, intensity)
                    if gray_fn is not None:
                        return gray_fn(img, intensity)
                    return fallback_factory(fallback_name)(img, intensity)

                return _wrapper

            g[name] = _make_rgb_wrapper(_gray_fn, _rgb_fn, name, _fallback_factory)
        elif rust_fn is not None:
            g[name] = rust_fn
        else:
            g[name] = _make_aug_fallback(name)


_export_aug_functions()

# Clean up the helpers so they don't pollute the module namespace.
# _make_aug_fallback and _AUG_FUNCTIONS are retained for closures referencing them.
del _export_aug_functions


# ══════════════════════════════════════════════════════════════════════════════════
# Font management
# ══════════════════════════════════════════════════════════════════════════════════

if HAS_RUST_ACCEL:
    assert _native is not None
    RustFontManager = _native.RustFontManager  # type: ignore[misc]
else:
    # Fallback: thin wrapper that delegates to the pure-Python FontManager
    class RustFontManager:  # type: ignore[no-redef]
        """Thin wrapper around the pure-Python `FontManager` for drop-in use."""

        def __init__(self) -> None:
            from khocr_gen.fonts import FontManager

            self._py = FontManager()

        def load(self, fonts_dir: str) -> None:
            # The Python FontManager loads in __init__, so this is a no-op
            pass

        def glyph_supported(self, font_path: str, ch: str) -> bool:
            font = self._py.get_font_by_path_and_size(font_path, 28)
            if font is None:
                return True
            try:
                mask = font.getmask(ch)
                return mask is not None and mask.getbbox() is not None
            except Exception:
                return True

        def text_supported(self, font_path: str, text: str) -> bool:
            for c in text:
                if c.isspace() or ord(c) < 32:
                    continue
                if not self.glyph_supported(font_path, c):
                    return False
            return True

        def text_has_khmer(self, text: str) -> bool:
            return self._py._text_has_khmer(text)

        def __len__(self) -> int:
            return len(self._py.all_fonts)

        def __repr__(self) -> str:
            return (
                f"RustFontManager(khmer={len(self._py.khmer_fonts)}, "
                f"english={len(self._py.english_fonts)}, "
                f"total={len(self._py.all_fonts)})"
            )


# ══════════════════════════════════════════════════════════════════════════════════
# Text span splitting
# ══════════════════════════════════════════════════════════════════════════════════

if HAS_RUST_ACCEL:
    assert _native is not None
    FontFace = _native.FontFace  # type: ignore[assignment]
else:
    FontFace = None  # type: ignore[assignment]


if HAS_RUST_ACCEL:
    assert _native is not None
    split_text_spans = _native.split_text_spans  # type: ignore[assignment]
else:

    def split_text_spans(text: str) -> list[tuple[str, str]]:  # type: ignore[no-redef]
        """Split text into contiguous script spans (pure-Python fallback)."""
        from khocr_gen.rendering import ImageRenderer

        return ImageRenderer._split_text_into_spans(text)


# ══════════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════════

if HAS_RUST_ACCEL:
    assert _native is not None
    estimate_bg = _native.estimate_bg_rust  # type: ignore[assignment]
    image_is_blank = _native.image_is_blank_rust  # type: ignore[assignment]
    write_image = _native.write_image_rust  # type: ignore[assignment]
else:

    def estimate_bg(img: np.ndarray) -> int:  # type: ignore[no-redef]
        """Estimate background colour from image border (pure-Python fallback)."""
        from khocr_gen.augmentation import _estimate_bg

        return int(_estimate_bg(img))

    def image_is_blank(  # type: ignore[no-redef]
        img: np.ndarray, threshold: int = 150, min_ratio: float = 0.002
    ) -> bool:
        """Check if image has too few dark pixels (pure-Python fallback)."""
        if img is None or img.size == 0:
            return True
        dark_pixels = int(np.sum(img < threshold))
        return (dark_pixels / img.size) < min_ratio

    def write_image(  # type: ignore[no-redef]
        img: np.ndarray, path: str, fmt: str = "jpg", quality: int = 90
    ) -> bool:
        """Write a numpy image to disk (pure-Python fallback)."""
        from pathlib import Path

        from khocr_gen.augmentation import write_output_image as _write

        return _write(Path(path), img, fmt=fmt, jpeg_quality=quality)


# ══════════════════════════════════════════════════════════════════════════════════
# Module-level init
# ══════════════════════════════════════════════════════════════════════════════════

_log_available()
del _log_available
