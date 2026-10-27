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
    apply_luminous_halo,
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
    def test_has_27_methods(self):
        assert len(AUG_METHODS) == 27

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
            "extreme_resize",
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
            "luminous_halo",
        }
        assert set(AUG_METHODS) == expected

    def test_all_callable(self):
        for name, fn in AUG_METHODS.items():
            assert callable(fn), f"{name} should be callable"

    def test_all_accept_image_and_intensity(self):
        img = _make_test_image()
        # extreme_resize deliberately changes shape: its "intensity" is an
        # absolute target height in pixels, not a [0, 1] fraction, and the
        # resize back to line height happens in the rendering pipeline
        # (ImageRenderer._apply_augmentation), not in the aug function itself.
        shape_preserving = {name for name in AUG_METHODS if name != "extreme_resize"}
        for name, fn in AUG_METHODS.items():
            try:
                result = fn(img.copy(), 0.5)
                assert result is not None, f"{name} returned None"
                if name in shape_preserving:
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


class TestLuminousHalo:
    def _rgb_fixture(self) -> np.ndarray:
        img = np.full((64, 180, 3), 255, dtype=np.uint8)
        img[20:44, 50:130] = 0
        return img

    def test_rgb_near_white_core_green_halo(self, monkeypatch):
        import khocr_gen.augmentation as aug_mod

        monkeypatch.setattr(aug_mod.random, "random", lambda: 0.05)
        img = self._rgb_fixture()
        before = img.copy()
        result = apply_luminous_halo(img, 0.8)

        assert result.shape == img.shape
        assert result.ndim == 3
        assert result.dtype == np.uint8
        np.testing.assert_array_equal(img, before)

        core = result[31, 89]
        assert core.min() >= 235
        assert int(core.max()) - int(core.min()) <= 8

        near = result[17, 89]  # 3px outside the ink
        far = result[8, 89]
        assert int(near[1]) > int(near[0]) + 8
        assert int(near[1]) > int(near[2]) + 8
        near_excess = int(near[1]) - int(near[0])
        far_excess = int(far[1]) - int(far[0])
        assert near_excess > far_excess

        for corner in (result[0, 0], result[0, -1], result[-1, 0], result[-1, -1]):
            np.testing.assert_array_equal(corner, [255, 255, 255])

    def test_counters_stay_holes(self, monkeypatch):
        import khocr_gen.augmentation as aug_mod

        monkeypatch.setattr(aug_mod.random, "random", lambda: 0.05)
        img = np.full((100, 100, 3), 220, dtype=np.uint8)
        img[15:85, 15:85] = 0
        img[35:65, 35:65] = 220
        result = apply_luminous_halo(img, 0.5)
        assert result.shape == img.shape
        # Stroke is filled; the hole is not.
        assert result[20, 50].min() >= 235
        assert abs(int(result[50, 50, 0]) - 220) < 8

    def test_hue_mostly_green(self):
        import random

        img = self._rgb_fixture()
        greens = 0
        for seed in range(40):
            random.seed(seed)
            result = apply_luminous_halo(img, 0.8)
            near = result[17, 89]
            if int(near[1]) > int(near[0]) and int(near[1]) > int(near[2]):
                greens += 1
        assert greens >= 24

    def test_grayscale_keeps_dark_core(self):
        img = np.full((48, 160), 255, dtype=np.uint8)
        img[16:32, 40:120] = 0
        result = apply_luminous_halo(img, 0.8)
        assert result.ndim == 2
        assert result.shape == img.shape
        assert result.dtype == np.uint8
        assert result[24, 80] < 40
        assert result[24, 80] < int(result[0, 0])
        assert result[0, 0] == 255

        gray = np.full((48, 160), 200, dtype=np.uint8)
        gray[16:32, 40:120] = 0
        gray_result = apply_luminous_halo(gray, 0.8)
        assert gray_result.shape == gray.shape
        assert gray_result[24, 80] < 40
        assert gray_result[24, 80] < 235
        assert gray_result[14, 80] > 200  # fringe just outside the ink
        assert gray_result[0, 0] == 200

    def test_dark_background_skips_white_fill(self, monkeypatch):
        import khocr_gen.augmentation as aug_mod

        monkeypatch.setattr(aug_mod.random, "random", lambda: 0.05)
        img = np.full((48, 160, 3), 30, dtype=np.uint8)
        img[16:32, 40:120] = 220
        result = apply_luminous_halo(img, 0.8)
        assert result.shape == img.shape
        np.testing.assert_array_equal(result[24, 80], [220, 220, 220])

    def test_unchanged_on_empty_low_contrast_tiny_and_mostly_ink(self):
        blank = np.full((32, 32, 3), 255, dtype=np.uint8)
        np.testing.assert_array_equal(apply_luminous_halo(blank, 0.8), blank)

        faint = np.full((32, 48), 240, dtype=np.uint8)
        faint[8:24, 10:38] = 228
        np.testing.assert_array_equal(apply_luminous_halo(faint, 0.8), faint)

        tiny = np.zeros((2, 8), dtype=np.uint8)
        tiny[:, 2:6] = 255
        np.testing.assert_array_equal(apply_luminous_halo(tiny, 0.8), tiny)

        odd = np.zeros((8, 8, 4), dtype=np.uint8)
        np.testing.assert_array_equal(apply_luminous_halo(odd, 0.8), odd)

        mostly = np.zeros((40, 40), dtype=np.uint8)
        mostly[0, :] = 255
        mostly[-1, :] = 255
        mostly[:, 0] = 255
        mostly[:, -1] = 255
        np.testing.assert_array_equal(apply_luminous_halo(mostly, 0.8), mostly)

    def test_same_seed_same_result(self):
        import random

        img = self._rgb_fixture()
        random.seed(11)
        first = apply_luminous_halo(img, 0.8)
        random.seed(11)
        second = apply_luminous_halo(img, 0.8)
        np.testing.assert_array_equal(first, second)

        random.seed(12)
        other = apply_luminous_halo(img, 0.8)
        # Different seeds can land in the same hue bucket. At least one of a
        # handful must diverge, otherwise the draw is being ignored.
        diverged = not np.array_equal(first, other)
        for seed in range(13, 30):
            if diverged:
                break
            random.seed(seed)
            diverged = not np.array_equal(first, apply_luminous_halo(img, 0.8))
        assert diverged

    def test_not_rgb_preferred(self):
        from khocr_gen.augmentation import _RGB_PREFERRED_METHODS

        assert "luminous_halo" not in _RGB_PREFERRED_METHODS

    def test_tall_khmer_line_keeps_ink_span(self):
        from pathlib import Path

        from khocr_gen.config import GenerationConfig
        from khocr_gen.fonts import FontManager
        from khocr_gen.rendering import ImageRenderer

        fonts = Path(__file__).resolve().parent.parent / "fonts"
        if not (fonts / "khmer").is_dir() or not any((fonts / "khmer").iterdir()):
            pytest.skip("project fonts/ directory not available")

        cfg = GenerationConfig(
            fonts_dir=str(fonts),
            color_mode=3,
            image_height=96,
            bg_color_mode="default",
        )
        renderer = ImageRenderer(FontManager(language="mixed", fonts_dir=str(fonts)), cfg)
        text = "កិខីឃឹងឺចើឆោជេ"
        img = renderer.render(text, augment=False)
        if img is None:
            pytest.skip("Khmer line did not render")

        result = renderer._apply_augmentation(img, "luminous_halo", 0.8, target_height=img.shape[0])
        assert result is not None
        assert result.shape == img.shape

        bg = np.median(img.reshape(-1, img.shape[-1]), axis=0) if img.ndim == 3 else 255
        ink = np.max(np.abs(img.astype(np.int16) - bg), axis=2) > 28
        assert ink.any()
        ys, xs = np.nonzero(ink)

        out_dev = np.max(np.abs(result.astype(np.int16) - bg), axis=2)
        mark = out_dev > 8
        assert mark.any()
        oys, oxs = np.nonzero(mark)
        # Halo sits on the glyph. Nothing was cropped off the line.
        assert oys.min() <= ys.max() and oys.max() >= ys.min()
        assert oxs.min() <= xs.max() and oxs.max() >= xs.min()
        assert oys.min() >= 0 and oys.max() < result.shape[0]


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
