"""`khocr-gen view` - preview images stored in an LMDB (.mdb) database."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from tqdm import tqdm

if TYPE_CHECKING:
    import argparse


def _read_lmdb_samples(lmdb_dir: Path, max_samples: int = 0) -> list[tuple[bytes, str]]:
    """Read (image_bytes, label) pairs from an LMDB database.

    Args:
        lmdb_dir: Path to the LMDB directory (containing data.mdb).
        max_samples: Maximum samples to read (0 = all).

    Returns:
        List of (jpeg_bytes, text_label) tuples.
    """
    import lmdb  # type: ignore[import-untyped]

    env = lmdb.open(str(lmdb_dir), readonly=True, lock=False, readahead=False, meminit=False)
    samples: list[tuple[bytes, str]] = []
    try:
        with env.begin(write=False, buffers=True) as txn:
            raw = txn.get(b"num-samples")
            if raw is None:
                return []
            total = int(bytes(raw).decode())
            count = total if max_samples <= 0 else min(max_samples, total)
            for i in range(1, count + 1):
                img_bytes = txn.get(f"image-{i:09d}".encode())
                lbl_bytes = txn.get(f"label-{i:09d}".encode())
                if img_bytes is None:
                    continue
                label = bytes(lbl_bytes).decode("utf-8") if lbl_bytes else ""
                samples.append((bytes(img_bytes), label))
    finally:
        env.close()
    return samples


def _show_summary(lmdb_dir: Path) -> int:
    """Print a summary of the LMDB database and return total sample count."""
    import lmdb  # type: ignore[import-untyped]

    env = lmdb.open(str(lmdb_dir), readonly=True, lock=False, readahead=False, meminit=False)
    try:
        with env.begin(write=False, buffers=True) as txn:
            raw = txn.get(b"num-samples")
            if raw is None:
                print("Database is empty (no num-samples key).")
                return 0
            total = int(bytes(raw).decode())
            print(f"LMDB directory : {lmdb_dir}")
            print(f"Total samples  : {total:,}")

            # Show first few labels
            print("\nFirst 5 samples:")
            for i in range(1, min(6, total + 1)):
                lbl_bytes = txn.get(f"label-{i:09d}".encode())
                label = bytes(lbl_bytes).decode("utf-8") if lbl_bytes else "(no label)"
                shape_info = ""
                img_bytes = txn.get(f"image-{i:09d}".encode())
                if img_bytes:
                    import cv2
                    import numpy as np

                    arr = np.frombuffer(bytes(img_bytes), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        h, w = img.shape[:2]
                        c = img.shape[2] if img.ndim == 3 else 1
                        shape_info = f"  [{w}x{h}x{c}c, {len(bytes(img_bytes)):,} bytes JPEG]"
                print(f"  {i:>5d}. {label[:80]}{shape_info}")
            return total
    finally:
        env.close()


def run(args: argparse.Namespace) -> int:
    """Entry point - called by cli.py."""
    lmdb_path = Path(args.lmdb).expanduser().resolve()

    if not lmdb_path.exists():
        print(f"LMDB directory not found: {lmdb_path}", file=sys.stderr)
        return 1

    data_mdb = lmdb_path / "data.mdb" if lmdb_path.is_dir() else lmdb_path
    if data_mdb.is_file():
        lmdb_path = data_mdb.parent
    elif not (lmdb_path / "data.mdb").exists():
        print(f"No data.mdb found in: {lmdb_path}", file=sys.stderr)
        return 1

    # Summary mode
    if args.summary:
        _show_summary(lmdb_path)
        return 0

    # Read samples
    samples = _read_lmdb_samples(
        lmdb_path, max_samples=args.count if args.count > 0 else args.max_count
    )
    if not samples:
        print("No samples found in database.", file=sys.stderr)
        return 1

    # Output mode
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        labels_path = out_dir / "labels.txt"

        with labels_path.open("w", encoding="utf-8") as lf:
            for idx, (jpeg_bytes, label) in enumerate(
                tqdm(samples, desc="  Extracting", unit="img"), start=1
            ):
                img_name = f"img_{idx:06d}.jpg"
                (out_dir / img_name).write_bytes(jpeg_bytes)
                lf.write(f"{img_name}\t{label}\n")

        print(f"Extracted {len(samples)} samples to {out_dir}")
        return 0

    # Print text mode (labels only)
    if args.labels_only:
        for idx, (_, label) in enumerate(samples, start=1):
            print(f"{idx:>6d}. {label}")
        return 0

    # Default: show info about samples
    print(f"LMDB directory : {lmdb_path}")
    _show_summary(lmdb_path)
    print("\nUse --count N to extract N samples, or --output-dir DIR to export all.")
    return 0


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register all view sub-command arguments onto *parser*."""

    parser.add_argument(
        "--lmdb", required=True, metavar="DIR", help="Path to LMDB directory (containing data.mdb)"
    )
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        metavar="N",
        help="Number of samples to read (0 = all, capped)",
    )
    parser.add_argument(
        "--max-count",
        type=int,
        default=100,
        metavar="N",
        help="Default max samples without --count",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        metavar="DIR",
        help="Extract images and labels to a directory",
    )
    parser.add_argument("--labels-only", action="store_true", help="Print only labels (text mode)")
