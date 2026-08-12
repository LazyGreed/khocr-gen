"""Tests for augmentation methods (unified registry)."""

from __future__ import annotations

import numpy as np
import pytest

from khocr_gen.augmentation import (
    AUG_METHODS,
    apply_anisotropic_dilation,
    apply_background_texture,
    apply_blur,
    apply_brightness_contrast,
    apply_distortion,
    apply_elastic,
    apply_geo_warp,
    apply_gradient_illumination,
    apply_hsv,
    apply_jpeg_compression,
    apply_low_contrast_caption,
    apply_lowdpi,
    apply_morphological,
    apply_online_blur,
    apply_online_noise,
    apply_oversample,
    apply_perspective,
    apply_pixelation,
    apply_random_crop,
    apply_reverse,
    apply_rotation,
    apply_salt_pepper,
    apply_sauvola,
    apply_vertical_crop,
)


def _make_test_image(h: int = 48, w: int = 200, text_val: int = 0, bg_val: int = 255) -> np.ndarray:
    """Create a simple grayscale test image with text-like dark pixels."""
    img = np.full((h, w), bg_val, dtype=np.uint8)
    # Draw a horizontal stripe of "text"
    img[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = text_val
    return img


class TestSauvola:
    def test_basic(self):
        img = _make_test_image()
        result = apply_sauvola(img, 0.5)
        assert result is not None
        assert result.shape == img.shape
        assert result.dtype == np.uint8

    def test_low_intensity(self):
        img = _make_test_image()
        result = apply_sauvola(img, 0.0)
        assert result is not None
        assert result.shape == img.shape

    def test_high_intensity(self):
        img = _make_test_image()
        result = apply_sauvola(img, 1.0)
        assert result is not None
        assert result.shape == img.shape

    def test_tiny_image_passes(self):
        img = _make_test_image(h=10, w=10)
        result = apply_sauvola(img, 0.5)
        assert result is not None


class TestGeoWarp:
    def test_basic(self):
        img = _make_test_image()
        result = apply_geo_warp(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_geo_warp(img, 0.0)
        assert result is not None

    def test_max_intensity(self):
        img = _make_test_image()
        result = apply_geo_warp(img, 1.0)
        assert result is not None


class TestVerticalCrop:
    def test_basic(self):
        img = _make_test_image()
        result = apply_vertical_crop(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_vertical_crop(img, 0.0)
        assert result is not None


class TestBlur:
    def test_basic(self):
        img = _make_test_image()
        result = apply_blur(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_no_blur(self):
        img = _make_test_image()
        result = apply_blur(img, 0.0)
        assert result is not None


class TestRotation:
    def test_basic(self):
        img = _make_test_image()
        result = apply_rotation(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity_near_noop(self):
        img = _make_test_image()
        result = apply_rotation(img, 0.0)
        assert result is not None
        assert result.shape == img.shape


class TestSaltPepper:
    def test_basic(self):
        img = _make_test_image()
        result = apply_salt_pepper(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_salt_pepper(img, 0.0)
        # At zero intensity, very few pixels should change
        assert result is not None


class TestJPEGCompression:
    def test_basic(self):
        img = _make_test_image()
        result = apply_jpeg_compression(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_high_quality(self):
        img = _make_test_image()
        result = apply_jpeg_compression(img, 0.0)
        assert result is not None

    def test_low_quality(self):
        img = _make_test_image()
        result = apply_jpeg_compression(img, 1.0)
        assert result is not None


class TestBackgroundTexture:
    def test_basic(self):
        img = _make_test_image()
        result = apply_background_texture(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_background_texture(img, 0.0)
        assert result is not None

    def test_multiple_runs_exercise_all_modes_2d(self):
        img = _make_test_image(h=64, w=256)
        for _ in range(50):
            res = apply_background_texture(img, 0.7)
            assert res is not None
            assert res.shape == img.shape
            assert res.dtype == np.uint8

    def test_multiple_runs_exercise_all_modes_rgb(self):
        img_2d = _make_test_image(h=64, w=256)
        img_rgb = np.stack([img_2d] * 3, axis=-1)
        for _ in range(50):
            res = apply_background_texture(img_rgb, 0.7)
            assert res is not None
            assert res.shape == img_rgb.shape
            assert res.dtype == np.uint8


class TestLowDPI:
    def test_basic(self):
        img = _make_test_image()
        result = apply_lowdpi(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_lowdpi(img, 0.0)
        assert result is not None


class TestOversample:
    def test_basic(self):
        img = _make_test_image()
        result = apply_oversample(img, 0.5)
        assert result is not None
        assert result.shape == img.shape


class TestLowContrastCaption:
    def test_basic(self):
        img = _make_test_image()
        result = apply_low_contrast_caption(img, 0.5)
        assert result is not None
        assert result.shape == img.shape
        assert result.dtype == np.uint8

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_low_contrast_caption(img, 0.0)
        assert result is not None
        assert result.shape == img.shape

    def test_high_intensity_reduces_contrast(self):
        img = _make_test_image()
        result = apply_low_contrast_caption(img, 1.0)
        assert result is not None
        # Text (0) vs background (255) spread should shrink toward mid-gray.
        assert int(result.max()) - int(result.min()) < int(img.max()) - int(img.min())

    def test_tiny_image_passes(self):
        img = _make_test_image(h=3, w=3)
        result = apply_low_contrast_caption(img, 0.5)
        assert result is not None

    def test_rgb(self):
        img_2d = _make_test_image(h=48, w=200)
        img_rgb = np.stack([img_2d] * 3, axis=-1)
        result = apply_low_contrast_caption(img_rgb, 0.5)
        assert result is not None
        assert result.shape == img_rgb.shape


class TestDistortion:
    def test_basic(self):
        img = _make_test_image()
        result = apply_distortion(img, 0.5)
        assert result is not None
        assert result.shape == img.shape


class TestUnifiedRegistry:
    def test_has_25_methods(self):
        assert len(AUG_METHODS) == 25

    def test_expected_names(self):
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

    def test_all_accept_image_and_intensity(self):
        img = _make_test_image()
        for name, fn in AUG_METHODS.items():
            try:
                result = fn(img.copy(), 0.5)
                assert result is not None, f"{name} returned None"
                assert result.shape == img.shape, f"{name} changed shape"
            except Exception as e:
                pytest.fail(f"{name} raised {e}")


def _make_rgb_test_image(h: int = 48, w: int = 200) -> np.ndarray:
    """Create a simple RGB test image."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    img[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = 0
    return img


class TestPerspective:
    def test_basic(self):
        img = _make_test_image()
        result = apply_perspective(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_perspective(img, 0.0)
        assert result is not None

    def test_tiny_image(self):
        img = _make_test_image(h=5, w=5)
        result = apply_perspective(img, 0.5)
        assert result is not None


class TestElastic:
    def test_basic(self):
        img = _make_test_image()
        result = apply_elastic(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_tiny_image(self):
        img = _make_test_image(h=5, w=5)
        result = apply_elastic(img, 0.5)
        assert result is not None


class TestRandomCrop:
    def test_basic(self):
        img = _make_test_image()
        result = apply_random_crop(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_tiny_image(self):
        img = _make_test_image(h=3, w=10)
        result = apply_random_crop(img, 0.5)
        assert result is not None


class TestOnlineBlur:
    def test_basic(self):
        img = _make_test_image()
        result = apply_online_blur(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_online_blur(img, 0.0)
        assert result is not None


class TestOnlineNoise:
    def test_basic(self):
        img = _make_test_image()
        result = apply_online_noise(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_online_noise(img, 0.0)
        assert result is not None


class TestHSV:
    def test_basic_rgb(self):
        img = _make_rgb_test_image()
        result = apply_hsv(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_grayscale_passthrough(self):
        img = _make_test_image()
        result = apply_hsv(img, 0.5)
        assert result is not None
        assert result.shape == img.shape


class TestReverse:
    def test_basic(self):
        img = _make_test_image()
        result = apply_reverse(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_inverts_values(self):
        img = np.full((10, 10), 100, dtype=np.uint8)
        result = apply_reverse(img, 0.5)
        assert result[0, 0] == 155  # 255 - 100


class TestBrightnessContrast:
    def test_basic(self):
        img = _make_test_image()
        result = apply_brightness_contrast(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity_near_noop(self):
        img = _make_test_image()
        result = apply_brightness_contrast(img, 0.0)
        assert result is not None


class TestPixelation:
    def test_basic(self):
        img = _make_test_image()
        result = apply_pixelation(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_pixelation(img, 0.0)
        assert result is not None


class TestGradientIllumination:
    def test_basic(self):
        img = _make_test_image()
        result = apply_gradient_illumination(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_zero_intensity(self):
        img = _make_test_image()
        result = apply_gradient_illumination(img, 0.0)
        assert result is not None


class TestMorphological:
    def test_basic(self):
        img = _make_test_image()
        result = apply_morphological(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_with_khmer_flag(self):
        img = _make_test_image()
        result = apply_morphological(img, 0.5, has_khmer=True)
        assert result is not None

    def test_low_intensity_small_kernel(self):
        img = _make_test_image()
        result = apply_morphological(img, 0.2)
        assert result is not None


class TestAnisotropicDilation:
    def test_basic(self):
        img = _make_test_image()
        result = apply_anisotropic_dilation(img, 0.5)
        assert result is not None
        assert result.shape == img.shape

    def test_high_intensity_larger_kernel(self):
        img = _make_test_image()
        result = apply_anisotropic_dilation(img, 0.9)
        assert result is not None


class TestAlbumentationsFailureLogging:
    """A failing albumentations pipeline must fall back to the input image and
    log at DEBUG (not raise, not fail silently without a trace)."""

    def test_apply_blur_logs_debug_on_failure(self, monkeypatch, caplog):
        import logging

        import khocr_gen.augmentation as aug_mod

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(aug_mod.A, "OneOf", _raise)
        img = _make_test_image()

        with caplog.at_level(logging.DEBUG, logger="khocr_gen.augmentation"):
            result = apply_blur(img, 0.5)

        np.testing.assert_array_equal(result, img)
        assert any(
            "apply_blur" in record.message and record.levelno == logging.DEBUG
            for record in caplog.records
        )

    def test_apply_distortion_logs_debug_on_failure(self, monkeypatch, caplog):
        import logging

        import khocr_gen.augmentation as aug_mod

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(aug_mod.A, "OneOf", _raise)
        img = _make_test_image()

        with caplog.at_level(logging.DEBUG, logger="khocr_gen.augmentation"):
            result = apply_distortion(img, 0.5)

        np.testing.assert_array_equal(result, img)
        assert any(
            "apply_distortion" in record.message and record.levelno == logging.DEBUG
            for record in caplog.records
        )
