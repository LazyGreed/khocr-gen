"""Tests for dataset combine functionality."""

from __future__ import annotations

import argparse

import numpy as np

from khocr_gen import combine_cmd
from khocr_gen.combine import SPLITS, _detect_split_format, combine_datasets
from khocr_gen.lmdb_pack import pack_lmdb


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
    def test_has_train_val_test(self):
        assert "train" in SPLITS
        assert "val" in SPLITS
        assert "test" in SPLITS
        assert len(SPLITS) == 3


def _make_raw_split(split_dir, n: int, prefix: str):
    import cv2

    images_dir = split_dir / "images"
    images_dir.mkdir(parents=True)
    lines = []
    for i in range(n):
        img = np.full((16, 32), i % 256, dtype=np.uint8)
        name = f"{prefix}_{i:03d}.jpg"
        cv2.imwrite(str(images_dir / name), img)
        lines.append(f"{name}\t{prefix}-text-{i}")
    (split_dir / "labels.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_lmdb_split(split_dir, n: int, prefix: str, tmp_path):
    raw_tmp = tmp_path / f"_raw_{prefix}"
    _make_raw_split(raw_tmp, n, prefix)
    lmdb_dir = split_dir / "lmdb"
    lmdb_dir.mkdir(parents=True)
    pack_lmdb(
        labels_file=raw_tmp / "labels.txt",
        images_dir=raw_tmp / "images",
        out_dir=lmdb_dir,
    )


class TestCombineDatasets:
    def test_merges_mixed_raw_and_lmdb_inputs(self, tmp_path):
        ds1 = tmp_path / "ds1"
        ds2 = tmp_path / "ds2"
        _make_raw_split(ds1 / "train", 3, "raw")
        _make_lmdb_split(ds2 / "train", 2, "lmdb", tmp_path)

        out_dir = tmp_path / "merged"
        counts = combine_datasets([ds1, ds2], out_dir)

        assert counts == {"train": 5}
        assert (out_dir / "train" / "lmdb" / "data.mdb").exists()
        # val/test absent from every input -> skipped entirely, no dirs created
        assert not (out_dir / "val").exists()
        assert not (out_dir / "test").exists()

    def test_split_absent_from_all_inputs_is_skipped(self, tmp_path):
        ds1 = tmp_path / "ds1"
        ds2 = tmp_path / "ds2"
        _make_raw_split(ds1 / "train", 2, "a")
        _make_raw_split(ds2 / "train", 2, "b")
        # neither dataset has val/ or test/

        out_dir = tmp_path / "merged"
        counts = combine_datasets([ds1, ds2], out_dir)

        assert "val" not in counts
        assert "test" not in counts
        assert counts["train"] == 4

    def test_split_present_in_only_one_input_is_still_merged(self, tmp_path):
        ds1 = tmp_path / "ds1"
        ds2 = tmp_path / "ds2"
        _make_raw_split(ds1 / "train", 2, "a")
        _make_raw_split(ds1 / "val", 1, "a-val")
        _make_raw_split(ds2 / "train", 2, "b")
        # ds2 has no val/ split at all

        out_dir = tmp_path / "merged"
        counts = combine_datasets([ds1, ds2], out_dir)

        assert counts["val"] == 1
        assert counts["train"] == 4
