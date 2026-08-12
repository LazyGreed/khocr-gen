"""Tests for text decoration sampling and rendering."""

from __future__ import annotations

import random
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import ImageFont

from khocr_gen.config import GenerationConfig, TextDecorationConfig
from khocr_gen.fonts import FontManager
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


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestRenderDecorated:
    def _cfg(self, **deco_kw) -> GenerationConfig:
        return GenerationConfig(
            color_mode=3,
            bg_color_mode="default",
            text_deco=TextDecorationConfig(**deco_kw),
        )

    def _renderer(self, **deco_kw) -> ImageRenderer:
        cfg = self._cfg(**deco_kw)
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        return ImageRenderer(fm, cfg)

    def _decorated(self, renderer, text, style):
        random.seed(0)
        return renderer._render_decorated(
            text, style, augment=False, target_height=48, retry_limit=3
        )

    def _ink_rows(self, img) -> np.ndarray:
        gray = img if img.ndim == 2 else np.min(img, axis=-1)
        return np.argwhere(gray < 128)

    def test_underline_adds_ink_below_text(self):
        r = self._renderer(underline_prob=1.0)
        img, _ = self._decorated(r, "Hello", DecorStyle(underline=True))
        plain, _ = self._decorated(self._renderer(), "Hello", DecorStyle())
        assert img is not None and plain is not None
        bottom = img.shape[0] // 2
        assert np.sum(np.min(img, axis=-1)[bottom:] < 128) > np.sum(
            np.min(plain, axis=-1)[bottom:] < 128
        )

    def test_superscript_raises_glyph(self):
        r = self._renderer()
        img_sup, _ = self._decorated(r, "H2O", DecorStyle(super_indices=[1]))
        img_plain, _ = self._decorated(self._renderer(), "H2O", DecorStyle())
        assert img_sup is not None and img_plain is not None
        assert self._ink_rows(img_sup)[:, 0].min() <= self._ink_rows(img_plain)[:, 0].min()

    def test_subscript_lowers_glyph(self):
        r = self._renderer()
        img_sub, _ = self._decorated(r, "H2O", DecorStyle(sub_indices=[1]))
        img_plain, _ = self._decorated(self._renderer(), "H2O", DecorStyle())
        assert img_sub is not None and img_plain is not None
        assert self._ink_rows(img_sub)[:, 0].max() >= self._ink_rows(img_plain)[:, 0].max()

    def test_color_applied_in_rgb(self):
        r = self._renderer(color_prob=1.0)
        img, _ = self._decorated(r, "Hello", DecorStyle(color=True))
        assert img is not None
        dark = np.argwhere(np.min(img, axis=-1) < 128)
        assert len(dark) > 0
        i, j = dark[0]
        cr, cg, cb = img[i, j]
        assert not (cr == cg == cb)  # colored text, not gray

    def test_no_clipping_when_decorated(self):
        r = self._renderer()
        style = DecorStyle(underline=True, super_indices=[1], sub_indices=[7], color=True)
        img, _ = self._decorated(r, "H2O Hello", style)
        assert img is not None
        ink = np.min(img, axis=-1) < 128
        rows = np.argwhere(ink.any(axis=1)).ravel()
        cols = np.argwhere(ink.any(axis=0)).ravel()
        assert rows.min() >= 1 and rows.max() <= img.shape[0] - 2
        assert cols.min() >= 1 and cols.max() <= img.shape[1] - 2

    def test_bold_uses_real_variant_font(self):
        r = self._renderer(bold_prob=1.0)
        _img, font = self._decorated(r, "Hello", DecorStyle(bold=True))
        assert font is not None
        style_name = ImageFont.truetype(getattr(font, "path", ""), 28).getname()[1]
        assert style_name is not None
        assert "bold" in style_name.lower()

    def test_bold_dropped_when_no_variant(self, monkeypatch):
        r = self._renderer(bold_prob=1.0)
        monkeypatch.setattr(
            r.font_manager, "random_font_path_with_style", lambda text, styles: None
        )
        style = DecorStyle(bold=True, underline=True)
        result = self._decorated(r, "Hello", style)
        assert result is not None
        assert style.bold is False  # dropped
        assert style.underline is True  # still applied

    def test_internal_failure_returns_none_not_raise(self, monkeypatch):
        r = self._renderer()

        def _boom(text, style, augment, target_height, retry_limit):
            raise RuntimeError("boom")

        monkeypatch.setattr(r, "_render_decorated_impl", _boom)
        result = self._decorated(r, "Hello", DecorStyle(underline=True))
        assert result is None  # swallowed by _render_decorated, never raised

    def test_italic_dropped_when_boldonly_fallback(self, monkeypatch):
        """bold+italic request falling back to a bold-only font clears `italic`."""
        r = self._renderer()
        fm = r.font_manager
        path = fm.get_random_font("Hello").path
        monkeypatch.setattr(fm, "random_font_path_with_style", lambda text, styles: path)
        monkeypatch.setattr(
            fm, "_style_tags", lambda p: {"bold"} if p == path else {"bold", "italic"}
        )
        style = DecorStyle(bold=True, italic=True)
        result = self._decorated(r, "Hello", style)
        assert result is not None
        assert style.bold is True
        assert style.italic is False


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestDecoratedCleanRender:
    def test_render_clean_routes_to_decorated(self):
        cfg = GenerationConfig(text_deco=TextDecorationConfig(underline_prob=1.0))
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)
        random.seed(0)
        result = r._render_clean("Hello", False, None, 3)
        assert result is not None
        _, _, meta = result
        assert "decorations" in meta
        assert "underline" in meta["decorations"]

    def test_specific_font_skips_decorations(self):
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        cfg = GenerationConfig(text_deco=TextDecorationConfig(underline_prob=1.0))
        r = ImageRenderer(fm, cfg)
        random.seed(0)
        font = fm.get_random_font("Hello")
        ref = (font.path, font.size)
        result = r._render_clean("Hello", False, ref, 3)
        assert result is not None
        _, _, meta = result
        assert "decorations" not in meta

    def test_render_with_one_augmentation_meta_carries_decorations(self):
        from khocr_gen.config import AugMethodConfig

        cfg = GenerationConfig(
            text_deco=TextDecorationConfig(underline_prob=1.0), bg_color_mode="default"
        )
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)
        enabled = [("blur", AugMethodConfig(prob=1.0, min=0.1, max=0.3))]
        random.seed(0)
        result = r.render_with_one_augmentation("Hello", enabled, retry_limit=3)
        assert result is not None
        _, _, meta = result
        assert meta.get("decorations") == ["underline"]

    def test_decorated_line_skips_mixed_font(self, monkeypatch):
        cfg = GenerationConfig(
            text_deco=TextDecorationConfig(underline_prob=1.0), mixed_font_prob=1.0
        )
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)

        def _boom(*args, **kwargs):
            raise AssertionError("mixed-font must not be used for decorated lines")

        monkeypatch.setattr(r, "_render_mixed_font", _boom)
        random.seed(0)
        img = r.render("Hello សួស្តី", augment=False)
        assert img is not None

    def test_decorated_failure_falls_back_to_clean(self, monkeypatch):
        cfg = GenerationConfig(text_deco=TextDecorationConfig(underline_prob=1.0))
        fm = FontManager(fonts_dir=str(_FONTS_DIR))
        r = ImageRenderer(fm, cfg)
        # Simulate a decoration failure: _render_decorated returns None.
        monkeypatch.setattr(r, "_render_decorated", lambda *a, **k: None)
        random.seed(0)
        result = r._render_clean("Hello", False, None, 3)
        assert result is not None
        _, _, meta = result
        assert "decorations" not in meta  # fell back to the clean-canvas path
