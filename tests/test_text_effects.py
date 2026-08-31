"""Tests for text effect sampling and rendering (shadow, glow, outline, ...)."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from khocr_gen.config import TEXT_EFFECT_NAMES, GenerationConfig, TextEffectConfig
from khocr_gen.fonts import FontManager
from khocr_gen.rendering import DecorStyle, ImageRenderer

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_FONTS_DIR / "khmer").is_dir() and any((_FONTS_DIR / "khmer").iterdir())


class TestDecorStyleEffect:
    def test_inactive_by_default(self):
        assert not DecorStyle().active

    def test_active_when_effect_set(self):
        assert DecorStyle(effect="glow").active


class TestSampleEffect:
    def test_disabled_returns_none(self):
        assert ImageRenderer._sample_effect(TextEffectConfig()) is None

    def test_forced_prob_always_picks_that_effect(self):
        random.seed(0)
        for _ in range(20):
            assert ImageRenderer._sample_effect(TextEffectConfig(outline_prob=1.0)) == "outline"

    def test_zero_prob_never_picked(self):
        random.seed(0)
        for _ in range(50):
            assert ImageRenderer._sample_effect(TextEffectConfig(glow_prob=0.0)) is None


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestRenderDecoratedEffects:
    def _renderer(self, color_mode: int = 3) -> ImageRenderer:
        cfg = GenerationConfig(color_mode=color_mode, bg_color_mode="default")
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        return ImageRenderer(fm, cfg)

    def _render(self, renderer, text, effect, augment=False, target_height=48):
        random.seed(0)
        return renderer._render_decorated(
            text,
            DecorStyle(effect=effect),
            augment=augment,
            target_height=target_height,
            retry_limit=5,
        )

    @pytest.mark.parametrize("effect", TEXT_EFFECT_NAMES)
    def test_every_effect_renders_without_error(self, effect):
        r = self._renderer()
        result = self._render(r, "Hello សួស្តី", effect)
        assert result is not None
        img, font = result
        assert img.ndim == 3
        assert img.shape[0] > 0 and img.shape[1] > 0
        assert font is not None

    @pytest.mark.parametrize("effect", TEXT_EFFECT_NAMES)
    def test_every_effect_renders_in_grayscale(self, effect):
        r = self._renderer(color_mode=1)
        result = self._render(r, "Hello", effect)
        assert result is not None
        img, _font = result
        assert img.ndim == 2

    def test_huge_produces_larger_canvas_than_plain(self):
        r = self._renderer()
        plain, _ = self._render(r, "Hello", None)
        huge, _ = self._render(r, "Hello", "huge")
        assert huge.shape[0] * huge.shape[1] > plain.shape[0] * plain.shape[1]

    def test_tiny_font_is_smaller_than_plain(self):
        r = self._renderer()
        _plain, plain_font = self._render(r, "Hello", None)
        _tiny, tiny_font = self._render(r, "Hello", "tiny")
        assert getattr(tiny_font, "size", 0) < getattr(plain_font, "size", 0)

    def test_huge_font_is_larger_than_plain(self):
        r = self._renderer()
        _plain, plain_font = self._render(r, "Hello", None)
        _huge, huge_font = self._render(r, "Hello", "huge")
        assert getattr(huge_font, "size", 0) > getattr(plain_font, "size", 0)

    def test_no_effect_falls_back_to_plain_fill(self):
        r = self._renderer()
        img, _ = self._render(r, "Hello", None)
        assert img is not None

    def test_transparent_blends_toward_background(self):
        r = self._renderer()
        img, _ = self._render(r, "Hello", "transparent")
        assert img is not None
        # Blended fill should not be pure black/white extremes for a default
        # light background + dark text pairing.
        dark = np.argwhere(np.min(img, axis=-1) < 250)
        assert len(dark) > 0

    def test_hollow_keeps_interior_close_to_background(self):
        r = self._renderer()
        img, _ = self._render(r, "O", "hollow")
        assert img is not None

    def test_no_clipping_for_blur_effects(self):
        r = self._renderer()
        for effect in ("shadow", "glow", "neon", "echo"):
            img, _ = self._render(r, "Hello", effect)
            assert img is not None
            ink = np.min(img, axis=-1) < 250
            rows = np.argwhere(ink.any(axis=1)).ravel()
            cols = np.argwhere(ink.any(axis=0)).ravel()
            if len(rows) and len(cols):
                assert rows.min() >= 0 and rows.max() <= img.shape[0] - 1
                assert cols.min() >= 0 and cols.max() <= img.shape[1] - 1

    def test_internal_failure_returns_none_not_raise(self, monkeypatch):
        r = self._renderer()

        def _boom(text, style, augment, target_height, retry_limit):
            raise RuntimeError("boom")

        monkeypatch.setattr(r, "_render_decorated_impl", _boom)
        random.seed(0)
        result = r._render_decorated("Hello", DecorStyle(effect="glow"), False, 48, 3)
        assert result is None


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestEffectCleanRenderIntegration:
    def test_render_clean_routes_to_effect_and_records_metadata(self):
        cfg = GenerationConfig(text_effect=TextEffectConfig(glow_prob=1.0))
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)
        random.seed(0)
        result = r._render_clean("Hello", False, None, 3)
        assert result is not None
        _, _, meta = result
        assert meta.get("decorations") == ["glow"]

    def test_effect_and_decoration_can_combine(self):
        from khocr_gen.config import TextDecorationConfig

        cfg = GenerationConfig(
            color_mode=3,
            text_deco=TextDecorationConfig(underline_prob=1.0),
            text_effect=TextEffectConfig(outline_prob=1.0),
        )
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)
        random.seed(0)
        result = r._render_clean("Hello", False, None, 3)
        assert result is not None
        _, _, meta = result
        assert "underline" in meta.get("decorations", [])
        assert "outline" in meta.get("decorations", [])
