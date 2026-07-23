"""Tests for LMDB packing utility.

Heavier round-trip tests are skipped by default — they need actual images on disk.
"""

from __future__ import annotations

import pytest

from khocr_gen.lmdb_pack import pack_lmdb


class TestPackLmdbErrors:
    def test_missing_labels_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Labels file not found"):
            pack_lmdb(
                labels_file=tmp_path / "nonexistent.txt",
                images_dir=tmp_path / "images",
                out_dir=tmp_path / "lmdb",
            )

    def test_missing_images_dir(self, tmp_path):
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="Images directory not found"):
            pack_lmdb(
                labels_file=labels_file,
                images_dir=tmp_path / "nonexistent_images",
                out_dir=tmp_path / "lmdb",
            )
