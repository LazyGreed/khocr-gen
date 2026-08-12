"""Tests for augmentation methods imported from unified registry.

These tests verify that all 12 methods previously in online_aug.py are
now correctly importable from the unified augmentation module.
"""

from __future__ import annotations

from khocr_gen.augmentation import (
    AUG_METHODS,
    apply_anisotropic_dilation,
    apply_brightness_contrast,
    apply_elastic,
    apply_gradient_illumination,
    apply_hsv,
    apply_morphological,
    apply_online_blur,
    apply_online_noise,
    apply_perspective,
    apply_pixelation,
    apply_random_crop,
    apply_reverse,
)


class TestUnifiedImports:
    """Verify all 25 methods are available via the unified AUG_METHODS dict."""

    def test_has_25_methods(self):
        assert len(AUG_METHODS) == 25

    def test_all_expected_names_present(self):
        expected = {
            "sauvola",
            "geo_warp",
            "vertical_crop",
            "blur",
            "distortion",
            "albu_noise",
            "jpeg_compression",
            "rotation",
            "salt_pepper",
            "background_texture",
            "lowdpi",
            "oversample",
            "low_contrast_caption",
            "perspective",
            "elastic",
            "random_crop",
            "online_blur",
            "online_noise",
            "hsv",
            "reverse",
            "brightness_contrast",
            "pixelation",
            "gradient_illumination",
            "morphological",
            "anisotropic_dilation",
        }
        assert set(AUG_METHODS) == expected

    def test_all_callable(self):
        for name, fn in AUG_METHODS.items():
            assert callable(fn), f"{name} should be callable"

    def test_functions_directly_importable(self):
        """All 12 formerly-online functions are importable from augmentation."""
        funcs = [
            apply_perspective,
            apply_elastic,
            apply_random_crop,
            apply_online_blur,
            apply_online_noise,
            apply_hsv,
            apply_reverse,
            apply_brightness_contrast,
            apply_pixelation,
            apply_gradient_illumination,
            apply_morphological,
            apply_anisotropic_dilation,
        ]
        for fn in funcs:
            assert callable(fn)
