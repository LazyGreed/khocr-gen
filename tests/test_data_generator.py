"""Tests for DatasetGenerator split orchestration.

generate_split is monkeypatched to avoid real font rendering: these tests exercise
the split-selection logic in generate_dataset / _split_lines_without_text_overlap,
not the rendering pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from khocr_gen.config import GenerationConfig
from khocr_gen.data_generator import DatasetGenerator

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_FONTS_DIR / "khmer").is_dir() and any((_FONTS_DIR / "khmer").iterdir())


class TestSplitLinesWithoutTextOverlap:
    def test_no_overlap_between_splits(self):
        lines = [f"line-{i}" for i in range(100)]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.2, test_ratio=0.1, seed=42
        )
        train_set, val_set, test_set = set(train), set(val), set(test)
        assert not (train_set & val_set)
        assert not (train_set & test_set)
        assert not (val_set & test_set)
        assert train_set | val_set | test_set == set(lines)

    def test_zero_test_ratio_yields_empty_test_and_keeps_all_lines(self):
        lines = [f"line-{i}" for i in range(50)]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.2, test_ratio=0.0, seed=42
        )
        assert test == []
        assert set(train) | set(val) == set(lines)

    def test_ratio_clamping_when_val_plus_test_exceeds_one(self):
        lines = [f"line-{i}" for i in range(20)]
        train, _val, _test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.7, test_ratio=0.6, seed=1
        )
        # Train must never go empty/negative even when ratios sum > 1.
        assert len(train) >= 1

    def test_duplicate_text_stays_in_one_split(self):
        lines = ["dup", "dup", "dup", "unique-a", "unique-b", "unique-c", "unique-d"]
        train, val, test = DatasetGenerator._split_lines_without_text_overlap(
            lines, val_ratio=0.2, test_ratio=0.2, seed=7
        )
        # all 3 "dup" copies must land in the same split
        counts_present = sum(1 for split in (train, val, test) if "dup" in split)
        assert counts_present == 1

    def test_empty_input(self):
        assert DatasetGenerator._split_lines_without_text_overlap([], 0.1, 0.1) == ([], [], [])


def _make_generator(tmp_path: Path) -> DatasetGenerator:
    cfg = GenerationConfig()
    cfg.fonts_dir = str(tmp_path / "fonts")
    return DatasetGenerator(cfg)


class TestGenerateDatasetTestFilePrecedence:
    """Regression test: an explicit test_file must be the sole source of the test
    split; the disjoint ratio-based split must not also carve out a test set
    (previously both wrote into output_dir/test and the counts["test"] silently
    reflected only the second, file-sourced call).
    """

    def test_explicit_test_file_is_sole_source_when_ratio_also_set(self, tmp_path, monkeypatch):
        corpus_path = tmp_path / "corpus.txt"
        corpus_path.write_text(
            "\n".join(f"train-or-val-{i}" for i in range(20)) + "\n", encoding="utf-8"
        )
        test_file = tmp_path / "test.txt"
        test_file.write_text("held-out-a\nheld-out-b\nheld-out-c\n", encoding="utf-8")

        output_dir = tmp_path / "data"
        generator = _make_generator(tmp_path)

        calls: list[tuple[str, int]] = []

        def fake_generate_split(self, text_file, output_dir, split_name, **kwargs):
            lines = [
                line for line in Path(text_file).read_text(encoding="utf-8").splitlines() if line
            ]
            calls.append((split_name, len(lines)))
            return len(lines)

        monkeypatch.setattr(DatasetGenerator, "generate_split", fake_generate_split)

        counts = generator.generate_dataset(
            corpus_path=corpus_path,
            output_dir=output_dir,
            test_file=test_file,
            val_ratio=0.2,
            test_ratio=0.3,  # would otherwise also carve a disjoint test split
            min_length=1,
            max_length=1000,
        )

        test_calls = [c for c in calls if c[0] == "test"]
        # generate_split must be invoked for the "test" split exactly once (file-sourced).
        assert len(test_calls) == 1
        assert test_calls[0][1] == 3  # the 3 lines in test_file
        assert counts["test"] == 3

    def test_disjoint_split_used_when_no_test_file(self, tmp_path, monkeypatch):
        corpus_path = tmp_path / "corpus.txt"
        corpus_path.write_text("\n".join(f"line-{i}" for i in range(30)) + "\n", encoding="utf-8")
        output_dir = tmp_path / "data"
        generator = _make_generator(tmp_path)

        calls: list[str] = []

        def fake_generate_split(self, text_file, output_dir, split_name, **kwargs):
            lines = [
                line for line in Path(text_file).read_text(encoding="utf-8").splitlines() if line
            ]
            calls.append(split_name)
            return len(lines)

        monkeypatch.setattr(DatasetGenerator, "generate_split", fake_generate_split)

        counts = generator.generate_dataset(
            corpus_path=corpus_path,
            output_dir=output_dir,
            val_ratio=0.2,
            test_ratio=0.2,
            min_length=1,
            max_length=1000,
        )

        assert calls.count("test") == 1
        assert counts["train"] + counts["val"] + counts["test"] == 30


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="project fonts/ directory not available")
class TestVariableHeightGenerateSplit:
    """End-to-end (real fonts, single process) coverage that variable-height
    generation preserves the labels.txt format and optionally writes a
    metadata.jsonl sidecar."""

    def _make_generator(self, cfg_overrides: dict) -> DatasetGenerator:
        cfg = GenerationConfig(fonts_dir=str(_FONTS_DIR), **cfg_overrides)
        return DatasetGenerator(cfg)

    def test_labels_format_unchanged_with_variable_height(self, tmp_path):
        text_file = tmp_path / "lines.txt"
        text_file.write_text("Hello World\nAnother line of text\n", encoding="utf-8")
        output_dir = tmp_path / "train"
        (output_dir / "images").mkdir(parents=True)

        generator = self._make_generator(
            {
                "line_height_mode": "variable",
                "min_line_height": 32,
                "max_line_height": 96,
            }
        )
        count = generator.generate_split(
            text_file=text_file,
            output_dir=output_dir,
            split_name="train",
            copies=1,
            workers=1,
        )
        assert count > 0
        labels_text = (output_dir / "labels.txt").read_text(encoding="utf-8")
        for line in labels_text.splitlines():
            filename, _, text = line.partition("\t")
            assert filename.startswith("train_") and filename.endswith(".jpg")
            assert text

    def test_metadata_sidecar_written_when_enabled(self, tmp_path):
        text_file = tmp_path / "lines.txt"
        text_file.write_text("Hello World\n", encoding="utf-8")
        output_dir = tmp_path / "train"
        (output_dir / "images").mkdir(parents=True)

        generator = self._make_generator(
            {
                "line_height_mode": "variable",
                "min_line_height": 32,
                "max_line_height": 96,
                "record_metadata": True,
            }
        )
        count = generator.generate_split(
            text_file=text_file,
            output_dir=output_dir,
            split_name="train",
            copies=2,
            workers=1,
        )
        assert count > 0
        meta_path = output_dir / "metadata.jsonl"
        assert meta_path.exists()
        records = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines()]
        assert len(records) == count
        for record in records:
            assert 32 <= record["height"] <= 96
            assert record["width"] > 0
            assert record["text"] == "Hello World"

    def test_no_metadata_file_when_disabled(self, tmp_path):
        text_file = tmp_path / "lines.txt"
        text_file.write_text("Hello World\n", encoding="utf-8")
        output_dir = tmp_path / "train"
        (output_dir / "images").mkdir(parents=True)

        generator = self._make_generator({"line_height_mode": "fixed"})
        generator.generate_split(
            text_file=text_file, output_dir=output_dir, split_name="train", copies=1, workers=1
        )
        assert not (output_dir / "metadata.jsonl").exists()
