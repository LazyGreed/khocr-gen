"""Tests for LMDB packing utility."""

from __future__ import annotations

import numpy as np
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


def _write_fake_dataset(tmp_path, n: int, heights: list[int] | None = None):
    import cv2

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    labels_file = tmp_path / "labels.txt"
    lines = []
    for i in range(n):
        h = heights[i] if heights else 16
        img = np.full((h, 32), i % 256, dtype=np.uint8)
        name = f"img_{i:03d}.jpg"
        cv2.imwrite(str(images_dir / name), img)
        lines.append(f"{name}\ttext-{i}")
    labels_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return labels_file, images_dir


class TestPackLmdbRoundTrip:
    def test_key_format_and_round_trip(self, tmp_path):
        import lmdb

        labels_file, images_dir = _write_fake_dataset(tmp_path, 3)
        out_dir = tmp_path / "lmdb"

        n = pack_lmdb(labels_file=labels_file, images_dir=images_dir, out_dir=out_dir)
        assert n == 3

        env = lmdb.open(str(out_dir), readonly=True, lock=False)
        with env.begin() as txn:
            assert txn.get(b"num-samples") == b"3"
            for i in range(1, 4):
                img_bytes = txn.get(f"image-{i:09d}".encode())
                lbl_bytes = txn.get(f"label-{i:09d}".encode())
                assert img_bytes is not None
                assert lbl_bytes is not None
                assert lbl_bytes.decode("utf-8") == f"text-{i - 1}"
            # no sample at index 0 or past the written count
            assert txn.get(b"image-000000000") is None
            assert txn.get(f"image-{4:09d}".encode()) is None
        env.close()

    def test_variable_dimensions_round_trip(self, tmp_path):
        """LMDB packing makes no fixed-shape assumption: images of different
        heights (as produced by variable line-height generation) must all
        decode back to their original per-sample dimensions."""
        import cv2
        import lmdb

        heights = [32, 48, 64, 96]
        labels_file, images_dir = _write_fake_dataset(tmp_path, len(heights), heights=heights)
        out_dir = tmp_path / "lmdb"

        n = pack_lmdb(labels_file=labels_file, images_dir=images_dir, out_dir=out_dir)
        assert n == len(heights)

        env = lmdb.open(str(out_dir), readonly=True, lock=False)
        with env.begin() as txn:
            for i, expected_h in enumerate(heights, start=1):
                img_bytes = txn.get(f"image-{i:09d}".encode())
                assert img_bytes is not None
                decoded = cv2.imdecode(
                    np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED
                )
                assert decoded is not None
                assert decoded.shape[0] == expected_h
                assert decoded.shape[1] == 32
        env.close()

    def test_commit_every_boundary_writes_all_samples(self, tmp_path):
        import lmdb

        labels_file, images_dir = _write_fake_dataset(tmp_path, 5)
        out_dir = tmp_path / "lmdb"

        n = pack_lmdb(
            labels_file=labels_file, images_dir=images_dir, out_dir=out_dir, commit_every=2
        )
        assert n == 5

        env = lmdb.open(str(out_dir), readonly=True, lock=False)
        with env.begin() as txn:
            assert txn.get(b"num-samples") == b"5"
            for i in range(1, 6):
                assert txn.get(f"image-{i:09d}".encode()) is not None
                assert txn.get(f"label-{i:09d}".encode()) is not None
        env.close()

    def test_skips_missing_images_and_counts_errors(self, tmp_path, capsys):
        labels_file, images_dir = _write_fake_dataset(tmp_path, 2)
        # Append a label line pointing at a nonexistent image.
        with labels_file.open("a", encoding="utf-8") as fh:
            fh.write("missing.jpg\tghost text\n")

        out_dir = tmp_path / "lmdb"
        n = pack_lmdb(labels_file=labels_file, images_dir=images_dir, out_dir=out_dir, verbose=True)
        assert n == 2  # the missing-image line is skipped, not counted
        assert "Skipped 1 samples" in capsys.readouterr().err
