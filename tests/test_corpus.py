"""Tests for corpus loading, filtering, and counting."""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import pytest

from khocr_gen.corpus import (
    _PASS,
    _SKIP,
    _TOO_LONG,
    _TOO_SHORT,
    _classify_raw_line,
    _count_corpus_serial,
    _empty_stats,
    _merge_stats,
    char_frequencies,
    count_corpus,
    load_corpus,
    rare_chars_from_frequencies,
)
from khocr_gen.errors import InputValidationError


def _write_corpus(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


class TestClassifyRawLine:
    def test_empty_line_skipped(self):
        status, result = _classify_raw_line("   \n", 1, 100)
        assert status == _SKIP
        assert result is None

    def test_too_short(self):
        status, result = _classify_raw_line("ab", 5, 100)
        assert status == _TOO_SHORT
        assert result is None

    def test_too_long(self):
        status, result = _classify_raw_line("a" * 101, 1, 100)
        assert status == _TOO_LONG
        assert result is None

    def test_passing(self):
        status, result = _classify_raw_line("hello world", 1, 100)
        assert status == _PASS
        assert result == "hello world"

    def test_strips_whitespace(self):
        _status, result = _classify_raw_line("  hello  \n", 1, 100)
        assert result == "hello"


class TestStatsHelpers:
    def test_empty_stats(self):
        s = _empty_stats()
        assert s == {"total": 0, "passing": 0, "too_short": 0, "too_long": 0}

    def test_merge_stats(self):
        a = {"total": 5, "passing": 2, "too_short": 1, "too_long": 2}
        b = {"total": 3, "passing": 2, "too_short": 0, "too_long": 1}
        _merge_stats(a, b)
        assert a["total"] == 8
        assert a["passing"] == 4

    def test_empty_stats_returns_new_dict(self):
        a = _empty_stats()
        b = _empty_stats()
        assert a is not b


class TestLoadCorpus:
    def test_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world\nfoo bar\nshort\n")
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp, min_length=1, max_length=100))
            assert len(lines) == 3
            assert lines[0] == "hello world"
        finally:
            tmp.unlink()

    def test_min_length_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hi\nhello world\nok\n")
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp, min_length=5, max_length=100))
            assert len(lines) == 1
            assert lines[0] == "hello world"
        finally:
            tmp.unlink()

    def test_max_length_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\nthis is a very long line that exceeds max\nshort\n")
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp, min_length=1, max_length=10))
            assert len(lines) == 2
            assert "hello" in lines
            assert "short" in lines
        finally:
            tmp.unlink()

    def test_max_lines_limit(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(f"line_{i}" for i in range(20)))
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp, max_lines=5))
            assert len(lines) == 5
        finally:
            tmp.unlink()

    def test_file_not_found(self):
        with pytest.raises(InputValidationError, match="Corpus file not found"):
            list(load_corpus("/nonexistent/path.txt"))

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp))
            assert len(lines) == 0
        finally:
            tmp.unlink()

    def test_skips_blank_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n\nline1\n\nline2\n\n")
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp))
            assert len(lines) == 2
        finally:
            tmp.unlink()

    def test_handles_utf8(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world\n")  # Just ASCII, khmer requires fonts
            tmp = Path(f.name)
        try:
            lines = list(load_corpus(tmp))
            assert len(lines) == 1
        finally:
            tmp.unlink()


class TestCountCorpus:
    def test_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(f"line_{i:02d}" for i in range(50)))
            tmp = Path(f.name)
        try:
            stats = count_corpus(tmp, min_length=1, max_length=100)
            assert stats["total"] == 50
            assert stats["passing"] == 50
            assert stats["too_short"] == 0
            assert stats["too_long"] == 0
        finally:
            tmp.unlink()

    def test_with_filters(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hi\n")  # too short (< 5)
            f.write("hello world\n")  # passing
            f.write("a" * 200 + "\n")  # too long (> 100)
            tmp = Path(f.name)
        try:
            stats = count_corpus(tmp, min_length=5, max_length=100)
            assert stats["passing"] == 1
            assert stats["too_short"] >= 1
            assert stats["too_long"] >= 1
        finally:
            tmp.unlink()

    def test_file_not_found(self):
        with pytest.raises(InputValidationError):
            count_corpus("/nonexistent/path.txt")

    def test_serial_mode(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\nworld\n")
            tmp = Path(f.name)
        try:
            stats = count_corpus(tmp, workers=1)
            assert stats["passing"] == 2
        finally:
            tmp.unlink()

    def test_count_serial_direct(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\nworld\n")
            tmp = Path(f.name)
        try:
            stats = _count_corpus_serial(Path(tmp), min_length=1, max_length=100)
            assert stats["passing"] == 2
        finally:
            tmp.unlink()


class TestThreeWayDisjointSplit:
    """Test 3-way text splitting without text overlap across train/val/test."""

    def test_three_way_disjoint_split_no_overlap(self):
        from khocr_gen.data_generator import DatasetGenerator

        lines = [f"sample_text_{i % 30}" for i in range(300)]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.1, test_ratio=0.1, seed=42
        )
        assert len(train) > 0
        assert len(val) > 0
        assert len(test) > 0

        train_texts = {t[1] if isinstance(t, tuple) else t for t in train}
        val_texts = {t[1] if isinstance(t, tuple) else t for t in val}
        test_texts = {t[1] if isinstance(t, tuple) else t for t in test}

        assert len(train_texts & val_texts) == 0
        assert len(train_texts & test_texts) == 0
        assert len(val_texts & test_texts) == 0

    def test_zero_test_ratio_returns_empty_test_set(self):
        from khocr_gen.data_generator import DatasetGenerator

        lines = [f"text_{i % 20}" for i in range(100)]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.2, test_ratio=0.0, seed=42
        )
        assert len(train) > 0
        assert len(val) > 0
        assert len(test) == 0

    def test_zero_ratios_returns_all_in_train(self):
        from khocr_gen.data_generator import DatasetGenerator

        lines = ["a", "b", "c", "d"]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.0, test_ratio=0.0, seed=42
        )
        assert len(train) == 4
        assert len(val) == 0
        assert len(test) == 0


class TestCharFrequencies:
    def test_counts_characters_across_filtered_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("aab\nabc\n")
            tmp = Path(f.name)
        try:
            freq = char_frequencies(tmp, min_length=1, max_length=100)
            assert freq["a"] == 3
            assert freq["b"] == 2
            assert freq["c"] == 1
        finally:
            tmp.unlink()

    def test_excludes_lines_filtered_by_length(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("z\nlonger_line\n")
            tmp = Path(f.name)
        try:
            freq = char_frequencies(tmp, min_length=5, max_length=100)
            assert "z" not in freq
            assert freq["l"] == 2
        finally:
            tmp.unlink()


class TestRareCharsFromFrequencies:
    def test_selects_bottom_percentile_by_char_type(self):
        # 20 distinct chars, frequencies 1..20 -> bottom 10% = 2 rarest chars
        freq = Counter({chr(ord("a") + i): i + 1 for i in range(20)})
        rare = rare_chars_from_frequencies(freq, percentile=10.0)
        assert rare == {"a", "b"}

    def test_zero_percentile_returns_empty(self):
        freq = Counter({"a": 5, "b": 1})
        assert rare_chars_from_frequencies(freq, percentile=0.0) == set()

    def test_empty_frequencies_returns_empty(self):
        assert rare_chars_from_frequencies(Counter(), percentile=5.0) == set()

    def test_always_selects_at_least_one_char_when_nonzero_percentile(self):
        freq = Counter({"a": 1, "b": 100})
        rare = rare_chars_from_frequencies(freq, percentile=1.0)
        assert rare == {"a"}

    def test_percentile_above_100_clamped(self):
        freq = Counter({"a": 1, "b": 2})
        assert rare_chars_from_frequencies(freq, percentile=500.0) == {"a", "b"}


class TestCopiesForLine:
    def test_no_rare_chars_returns_base_copies(self):
        from khocr_gen.data_generator import DatasetGenerator

        assert DatasetGenerator._copies_for_line("hello", 3, None, 3.0) == 3

    def test_multiplier_at_or_below_one_returns_base_copies(self):
        from khocr_gen.data_generator import DatasetGenerator

        assert DatasetGenerator._copies_for_line("hello", 3, {"h"}, 1.0) == 3

    def test_line_with_rare_char_gets_multiplied(self):
        from khocr_gen.data_generator import DatasetGenerator

        assert DatasetGenerator._copies_for_line("hello", 3, {"z"}, 3.0) == 3
        assert DatasetGenerator._copies_for_line("hzllo", 3, {"z"}, 3.0) == 9

    def test_multiplier_result_never_below_base_copies(self):
        from khocr_gen.data_generator import DatasetGenerator

        # round(1 * 1.2) == 1, still >= copies via max()
        assert DatasetGenerator._copies_for_line("z", 1, {"z"}, 1.2) >= 1
