"""Tests for the `khocr-gen generate` CLI entry point (generate.run)."""

from __future__ import annotations

import argparse

from khocr_gen.generate import add_args, run


def _build_args(**overrides) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_args(parser)
    args = parser.parse_args([])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class TestRunValidation:
    def test_missing_corpus_returns_2(self, tmp_path, capsys):
        args = _build_args(
            corpus=str(tmp_path / "does_not_exist.txt"),
            fonts=str(tmp_path / "fonts"),
            output=str(tmp_path / "data"),
        )
        rc = run(args)
        assert rc == 2
        assert "Corpus file not found" in capsys.readouterr().out

    def test_missing_fonts_returns_2(self, tmp_path, capsys):
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("hello\nworld\n", encoding="utf-8")
        args = _build_args(
            corpus=str(corpus),
            fonts=str(tmp_path / "does_not_exist_fonts"),
            output=str(tmp_path / "data"),
        )
        rc = run(args)
        assert rc == 2
        assert "Fonts directory not found" in capsys.readouterr().out

    def test_existing_nonempty_output_without_flag_returns_1(self, tmp_path, capsys):
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("hello\nworld\n", encoding="utf-8")
        fonts_dir = tmp_path / "fonts"
        fonts_dir.mkdir()
        output_dir = tmp_path / "data"
        output_dir.mkdir()
        (output_dir / "marker.txt").write_text("existing", encoding="utf-8")

        args = _build_args(
            corpus=str(corpus),
            fonts=str(fonts_dir),
            output=str(output_dir),
            append=False,
            overwrite=False,
        )
        rc = run(args)
        assert rc == 1
        assert "already exists" in capsys.readouterr().out


class TestRunLineHeightValidation:
    def test_invalid_line_height_range_returns_2(self, tmp_path, capsys):
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("hello\nworld\n", encoding="utf-8")
        fonts_dir = tmp_path / "fonts"
        fonts_dir.mkdir()
        args = _build_args(
            corpus=str(corpus),
            fonts=str(fonts_dir),
            output=str(tmp_path / "data"),
            line_height_mode="variable",
            min_line_height=96,
            max_line_height=32,
        )
        rc = run(args)
        assert rc == 2
        assert "--max-line-height" in capsys.readouterr().out

    def test_valid_line_height_config_proceeds_past_validation(self, tmp_path, capsys):
        """An invalid *fonts* dir should now be the failure, not line-height validation."""
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("hello\nworld\n", encoding="utf-8")
        args = _build_args(
            corpus=str(corpus),
            fonts=str(tmp_path / "does_not_exist_fonts"),
            output=str(tmp_path / "data"),
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
        )
        rc = run(args)
        assert rc == 2
        assert "Fonts directory not found" in capsys.readouterr().out


class TestRunCountOnly:
    def test_count_only_missing_corpus_returns_2(self, tmp_path, capsys):
        args = _build_args(
            corpus=str(tmp_path / "missing.txt"),
            count_only=True,
        )
        rc = run(args)
        assert rc == 2
        assert "Corpus file not found" in capsys.readouterr().out

    def test_count_only_reports_stats(self, tmp_path, capsys):
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("a longer line here\n" * 5 + "hi\n", encoding="utf-8")
        args = _build_args(corpus=str(corpus), count_only=True)
        rc = run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "Passing filter" in out
        assert "Lines to generate" in out

    def test_count_only_respects_min_length_filter(self, tmp_path, capsys):
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("hi\nlong enough line\n", encoding="utf-8")
        args = _build_args(corpus=str(corpus), count_only=True, min_length=5)
        rc = run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "Too short" in out
