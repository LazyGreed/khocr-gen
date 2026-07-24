"""Tests for ImageRenderer rendering styles and background color sampling."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from khocr_gen.config import GenerationConfig
from khocr_gen.fonts import FontManager
from khocr_gen.rendering import AUG_METHODS, ImageRenderer

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_FONTS_DIR / "khmer").is_dir() and any((_FONTS_DIR / "khmer").iterdir())


class TestImageRendererColorSampling:
    def test_default_mode_grayscale(self):
        cfg = GenerationConfig(color_mode=1, bg_color_mode="default")
        renderer = ImageRenderer(MagicMock(), cfg)
        bg, text = renderer._sample_bg_and_text_colors(augment=True)
        assert isinstance(bg, int)
        assert isinstance(text, int)
        assert 235 <= bg <= 255
        assert 0 <= text <= 30

    def test_default_mode_rgb(self):
        cfg = GenerationConfig(color_mode=3, bg_color_mode="default")
        renderer = ImageRenderer(MagicMock(), cfg)
        bg, text = renderer._sample_bg_and_text_colors(augment=True)
        assert isinstance(bg, tuple) and len(bg) == 3
        assert isinstance(text, tuple) and len(text) == 3

    def test_paper_tones_rgb(self):
        cfg = GenerationConfig(color_mode=3, bg_color_mode="paper_tones")
        renderer = ImageRenderer(MagicMock(), cfg)
        for _ in range(20):
            bg, text = renderer._sample_bg_and_text_colors(augment=True)
            assert isinstance(bg, tuple) and len(bg) == 3
            assert isinstance(text, tuple) and len(text) == 3

    def test_colored_rgb(self):
        cfg = GenerationConfig(color_mode=3, bg_color_mode="colored")
        renderer = ImageRenderer(MagicMock(), cfg)
        for _ in range(20):
            bg, text = renderer._sample_bg_and_text_colors(augment=True)
            assert isinstance(bg, tuple) and len(bg) == 3
            assert isinstance(text, tuple) and len(text) == 3

    def test_dark_mode_grayscale(self):
        cfg = GenerationConfig(color_mode=1, bg_color_mode="dark_mode")
        renderer = ImageRenderer(MagicMock(), cfg)
        bg, text = renderer._sample_bg_and_text_colors(augment=True)
        assert isinstance(bg, int)
        assert isinstance(text, int)
        assert bg < text  # dark background, bright text

    def test_dark_mode_rgb(self):
        cfg = GenerationConfig(color_mode=3, bg_color_mode="dark_mode")
        renderer = ImageRenderer(MagicMock(), cfg)
        bg, text = renderer._sample_bg_and_text_colors(augment=True)
        assert isinstance(bg, tuple) and len(bg) == 3
        assert isinstance(text, tuple) and len(text) == 3
        assert bg[0] < text[0]  # dark background, bright text

    def test_no_augment_always_uses_clean_defaults(self):
        cfg = GenerationConfig(color_mode=3, bg_color_mode="dark_mode")
        renderer = ImageRenderer(MagicMock(), cfg)
        bg, text = renderer._sample_bg_and_text_colors(augment=False)
        assert bg == (255, 255, 255)
        assert text == (0, 0, 0)


class TestApplyAugmentationFailureLogging:
    """A raising augmentation method must be swallowed (returns None, doesn't
    crash the pipeline) but logged at WARNING with the method name, so failures
    stay observable during a long generation run."""

    def test_logs_warning_and_returns_none_on_failure(self, monkeypatch, caplog):
        cfg = GenerationConfig(color_mode=1)
        renderer = ImageRenderer(MagicMock(), cfg)

        def _raise(img, intensity, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setitem(AUG_METHODS, "_test_failing_method", _raise)
        img = np.zeros((48, 200), dtype=np.uint8)

        with caplog.at_level(logging.WARNING, logger="khocr_gen.rendering"):
            result = renderer._apply_augmentation(img, "_test_failing_method", 0.5)

        assert result is None
        assert any(
            "_test_failing_method" in record.message and record.levelno == logging.WARNING
            for record in caplog.records
        )


@pytest.fixture(scope="module")
def real_font_manager() -> FontManager:
    if not _HAS_REAL_FONTS:
        pytest.skip("project fonts/ directory not available")
    return FontManager(language="mixed", fonts_dir=str(_FONTS_DIR))


_SAMPLE_TEXTS = ["Hello World", "ភាសាខ្មែរ", "Mixed English & ខ្មែរ 123"]


class TestVariableHeightRendering:
    """Integration coverage for `khocr-gen generate --line-height-mode variable`."""

    def test_fixed_mode_default_matches_image_height(self, real_font_manager):
        cfg = GenerationConfig(fonts_dir=str(_FONTS_DIR), image_height=48)
        renderer = ImageRenderer(real_font_manager, cfg)
        for text in _SAMPLE_TEXTS:
            img = renderer.render(text, augment=False)
            assert img is not None
            assert img.shape[0] == 48

    def test_variable_mode_stays_within_configured_bounds(self, real_font_manager):
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
            line_height_step=8,
        )
        renderer = ImageRenderer(real_font_manager, cfg)
        for _ in range(15):
            img = renderer.render(random.choice(_SAMPLE_TEXTS), augment=False)
            assert img is not None
            assert 32 <= img.shape[0] <= 96
            assert (img.shape[0] - 32) % 8 == 0

    def test_variable_mode_produces_more_than_one_height(self, real_font_manager):
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
        )
        renderer = ImageRenderer(real_font_manager, cfg)
        heights = set()
        for _ in range(25):
            img = renderer.render(random.choice(_SAMPLE_TEXTS), augment=False)
            assert img is not None
            heights.add(img.shape[0])
        assert len(heights) > 1

    def test_same_seed_gives_same_height_sequence(self, real_font_manager):
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
        )
        renderer = ImageRenderer(real_font_manager, cfg)

        def _run() -> list[int]:
            random.seed(1234)
            out = []
            for i in range(10):
                img = renderer.render(_SAMPLE_TEXTS[i % len(_SAMPLE_TEXTS)], augment=False)
                assert img is not None
                out.append(img.shape[0])
            return out

        assert _run() == _run()

    def test_proportional_font_and_random_padding_render_without_error(self, real_font_manager):
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
            font_size_mode="proportional",
            min_font_scale=0.65,
            max_font_scale=0.9,
            vertical_padding_mode="random",
            min_vertical_padding_ratio=0.04,
            max_vertical_padding_ratio=0.18,
        )
        renderer = ImageRenderer(real_font_manager, cfg)
        for text in _SAMPLE_TEXTS:
            img = renderer.render(text, augment=False)
            assert img is not None
            assert 32 <= img.shape[0] <= 96
            assert img.shape[1] > 0

    def test_no_glyph_clipping_at_top_and_bottom_row(self, real_font_manager):
        """With augment=False, background/text colors are deterministic
        (white/black), so top and bottom rows must stay background-colored
        across the sampled height range -- if a glyph got clipped, ink would
        touch the very edge row instead."""
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
            line_height_step=8,
            font_size_mode="proportional",
            min_font_scale=0.65,
            max_font_scale=0.9,
            vertical_padding_mode="random",
            min_vertical_padding_ratio=0.04,
            max_vertical_padding_ratio=0.18,
        )
        renderer = ImageRenderer(real_font_manager, cfg)
        random.seed(7)
        checked = 0
        for _ in range(20):
            text = random.choice(_SAMPLE_TEXTS)
            img = renderer.render(text, augment=False)
            if img is None:
                continue
            top_row_mean = float(np.mean(img[0]))
            bottom_row_mean = float(np.mean(img[-1]))
            assert top_row_mean > 230, f"top row not background-clean: mean={top_row_mean}"
            assert bottom_row_mean > 230, f"bottom row not background-clean: mean={bottom_row_mean}"
            checked += 1
        assert checked > 0


class TestVariableHeightLabelsFormatUnchanged:
    def test_render_with_one_augmentation_returns_method_image_and_metadata(
        self, real_font_manager
    ):
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
        )
        cfg.blur.prob = 1.0
        renderer = ImageRenderer(real_font_manager, cfg)
        result = renderer.render_with_one_augmentation("Hello World", cfg.enabled_aug_methods())
        assert result is not None
        method_name, img, meta = result
        assert isinstance(method_name, str)
        assert isinstance(img, np.ndarray)
        assert 32 <= img.shape[0] <= 96
        assert meta["width"] == img.shape[1]
        assert meta["height"] == img.shape[0]
