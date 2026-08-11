"""Tests for FontManager.

Full font-loading tests require actual TTF/OTF fonts on disk and are
skipped by default. This module tests the structural and error-handling
aspects of FontManager.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from khocr_gen.fonts import FontManager


class TestFontManagerInit:
    def test_creates_dirs_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fonts_dir = tmp_path / "fonts"

        # Should not crash; should create khmer/ and english/ subdirs
        fm = FontManager(fonts_dir=str(fonts_dir))
        assert (fonts_dir / "khmer").exists()
        assert (fonts_dir / "english").exists()
        assert len(fm.all_fonts) == 0

    def test_initial_state_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert fm.khmer_fonts == []
        assert fm.english_fonts == []
        assert fm.all_fonts == []

    def test_default_language_mixed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert fm.language == "mixed"

    def test_custom_language(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(language="khmer", fonts_dir=str(tmp_path / "fonts"))
        assert fm.language == "khmer"


class TestFontManagerTextHasKhmer:
    def test_khmer_text_detected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        # សួស្តី contains Khmer characters
        assert fm._text_has_khmer("សួស្តី") is True

    def test_english_text_not_khmer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert fm._text_has_khmer("Hello World") is False

    def test_mixed_text_detected_as_khmer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert fm._text_has_khmer("Hello សួស្តី") is True

    def test_cache_works(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        # First call
        result1 = fm._text_has_khmer("test")
        # Second call should use cache
        result2 = fm._text_has_khmer("test")
        assert result1 == result2
        # Cache entry exists
        assert "test" in fm._text_has_khmer_cache

    def test_cache_limits(self, tmp_path, monkeypatch):
        """Cache should not grow unbounded."""
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        # Pre-fill the cache
        fm._text_has_khmer_cache = {str(i): False for i in range(100_001)}
        fm._text_has_khmer("overflow")
        assert len(fm._text_has_khmer_cache) <= 1


class TestFontManagerGetFontsWithoutFonts:
    def test_get_random_font_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        font = fm.get_random_font("Hello")
        assert font is None

    def test_get_random_font_for_script_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        font, size = fm.get_random_font_for_script("khmer")
        assert font is None
        assert size is None

    def test_get_font_by_ref_returns_font_arg_itself(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        result = fm.get_font_by_ref("some_ref")
        assert result == "some_ref"

    def test_get_font_by_ref_with_tuple_not_found_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        result = fm.get_font_by_ref(("/nonexistent.ttf", 32))
        assert result is None

    def test_get_font_by_path_and_size_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        result = fm.get_font_by_path_and_size("/nonexistent.ttf", 32)
        assert result is None


class TestFontManagerCollectFontFiles:
    def test_empty_directory(self, tmp_path):
        files = FontManager._collect_font_files(tmp_path)
        assert files == []

    def test_filters_by_extension(self, tmp_path):
        (tmp_path / "font.ttf").touch()
        (tmp_path / "font.otf").touch()
        (tmp_path / "readme.txt").touch()
        files = FontManager._collect_font_files(tmp_path)
        assert len(files) == 2
        suffixes = {f.suffix for f in files}
        assert suffixes == {".ttf", ".otf"}

    def test_recursive_collection(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.ttf").touch()
        (sub / "b.ttf").touch()
        files = FontManager._collect_font_files(tmp_path)
        assert len(files) == 2


_PROJECT_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_PROJECT_FONTS_DIR / "khmer").is_dir() and any(
    (_PROJECT_FONTS_DIR / "khmer").iterdir()
)


class TestFontStyleDetection:
    def test_style_tags_from_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert "bold" in fm._style_tags("/tmp/Fake-Bold.ttf")
        assert "italic" in fm._style_tags("/tmp/Fake-Italic.ttf")
        assert {"bold", "italic"} <= fm._style_tags("/tmp/Fake-BoldItalic.ttf")
        assert fm._style_tags("/tmp/Fake-Regular.ttf") == set()

    def test_random_font_path_with_style_empty_pool_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = FontManager(fonts_dir=str(tmp_path / "fonts"))
        assert fm.random_font_path_with_style("Hello", {"bold"}) is None


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestFontStyleWithRealFonts:
    def test_random_bold_path_is_bold(self):
        fm = FontManager(fonts_dir=str(_PROJECT_FONTS_DIR))
        path = fm.random_font_path_with_style("Hello World", {"bold"})
        assert path is not None
        assert "bold" in fm._style_tags(path)

    def test_random_italic_path_is_italic(self):
        fm = FontManager(fonts_dir=str(_PROJECT_FONTS_DIR))
        path = fm.random_font_path_with_style("Hello World", {"italic"})
        assert path is not None
        assert "italic" in fm._style_tags(path)

    def test_random_bold_italic_prefers_dual_variant(self):
        fm = FontManager(fonts_dir=str(_PROJECT_FONTS_DIR))
        for _ in range(20):
            path = fm.random_font_path_with_style("Hello World", {"bold", "italic"})
            assert path is not None
            assert {"bold", "italic"} <= fm._style_tags(path)
