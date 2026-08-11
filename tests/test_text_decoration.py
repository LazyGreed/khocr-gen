"""Tests for text decoration sampling and rendering."""

from __future__ import annotations

import random
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np  # noqa: F401  # forward-declared for Task 4 tests
import pytest  # noqa: F401  # forward-declared for Task 4 tests

from khocr_gen.config import GenerationConfig, TextDecorationConfig
from khocr_gen.fonts import FontManager  # noqa: F401  # forward-declared for Task 4 tests
from khocr_gen.rendering import DecorStyle, ImageRenderer

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_FONTS_DIR / "khmer").is_dir() and any((_FONTS_DIR / "khmer").iterdir())


def _renderer(cfg: GenerationConfig) -> ImageRenderer:
    return ImageRenderer(MagicMock(), cfg)


class TestDecorStyle:
    def test_inactive_by_default(self):
        assert not DecorStyle().active

    def test_active_for_any_flag(self):
        assert DecorStyle(underline=True).active
        assert DecorStyle(sub_indices=[2]).active


class TestSampleDecorations:
    def test_no_deco_config_disabled(self):
        style = _renderer(GenerationConfig())._sample_decorations("Hello")
        assert not style.active

    def test_bold_and_superscript_combine(self):
        cfg = GenerationConfig(text_deco=TextDecorationConfig(bold_prob=1.0, superscript_prob=1.0))
        random.seed(0)
        # "H2" has exactly 2 ASCII-alnum candidates; a 1.0 superscript draw
        # raises both, so the outcome is seed-independent.
        style = _renderer(cfg)._sample_decorations("H2")
        assert style.bold
        assert sorted(style.super_indices) == [0, 1]

    def test_subscript_picks_ascii_alnum_only(self):
        cfg = GenerationConfig(text_deco=TextDecorationConfig(subscript_prob=1.0))
        random.seed(0)
        style = _renderer(cfg)._sample_decorations("សួស្តី H2O")
        assert style.sub_indices, "expected a subscript candidate"
        chars = ["សួស្តី H2O"[i] for i in style.sub_indices]
        assert all(c.isascii() and c.isalnum() for c in chars)

    def test_no_candidates_means_no_subscript(self):
        cfg = GenerationConfig(text_deco=TextDecorationConfig(subscript_prob=1.0))
        random.seed(0)
        style = _renderer(cfg)._sample_decorations("សួស្តី")
        assert style.sub_indices == []

    def test_color_not_sampled_in_grayscale(self):
        cfg = GenerationConfig(color_mode=1, text_deco=TextDecorationConfig(color_prob=1.0))
        random.seed(0)
        style = _renderer(cfg)._sample_decorations("Hello")
        assert not style.color

    def test_color_sampled_in_rgb(self):
        cfg = GenerationConfig(color_mode=3, text_deco=TextDecorationConfig(color_prob=1.0))
        random.seed(0)
        style = _renderer(cfg)._sample_decorations("Hello")
        assert style.color
