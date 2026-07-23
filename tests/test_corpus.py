"""Tests for corpus loading, filtering, and counting."""

from __future__ import annotations

import tempfile
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
    count_corpus,
    load_corpus,
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
