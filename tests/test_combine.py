"""Tests for dataset combine functionality."""

from __future__ import annotations

import argparse

from khocr_gen import combine_cmd
from khocr_gen.combine import SPLITS, _detect_split_format


class TestCombineCmdArgs:
    def test_accepts_config_flag(self):
        """`--config`/`-c` must be registered so `khocr-gen combine --config ...` parses.

        cli.py treats "combine" as a config-capable command (alongside "generate") and
        docs/CONFIG.md documents `--config` for it, so the subparser must expose it.
        """
        parser = argparse.ArgumentParser()
        combine_cmd.add_args(parser)
        ns = parser.parse_args(["data1", "--config", "configs/combine.yml"])
        assert ns.config == "configs/combine.yml"


class TestDetectSplitFormat:
    def test_lmdb_detected(self, tmp_path):
        split_dir = tmp_path / "train"
        lmdb_dir = split_dir / "lmdb"
        lmdb_dir.mkdir(parents=True)
        (lmdb_dir / "data.mdb").touch()

        assert _detect_split_format(split_dir) == "lmdb"

    def test_raw_detected(self, tmp_path):
        split_dir = tmp_path / "train"
        split_dir.mkdir(parents=True)
        (split_dir / "labels.txt").touch()

        assert _detect_split_format(split_dir) == "raw"

    def test_none_for_missing_split(self, tmp_path):
        assert _detect_split_format(tmp_path / "nonexistent") is None

    def test_none_for_empty_split(self, tmp_path):
        split_dir = tmp_path / "train"
        split_dir.mkdir(parents=True)
        assert _detect_split_format(split_dir) is None

    def test_raw_wins_over_lmdb_when_no_mdb(self, tmp_path):
        """labels.txt exists but no data.mdb."""
        split_dir = tmp_path / "train"
        lmdb_dir = split_dir / "lmdb"
        lmdb_dir.mkdir(parents=True)
        (split_dir / "labels.txt").touch()
        # No data.mdb — should be "raw"
        assert _detect_split_format(split_dir) == "raw"


class TestSplits:
    def test_has_train_and_val(self):
        assert "train" in SPLITS
        assert "val" in SPLITS
        assert len(SPLITS) == 2
