"""Combine multiple generated datasets into one merged dataset.

Supports n-way merge: `data_1 + data_2 + ... + data_n`.

Each input dataset is a directory containing `train/` and/or `val/` subdirectories,
where each split is either "raw" (`labels.txt` + `images/`) or "lmdb" (`lmdb/` subdirectory).
Inputs may use different formats independently per split; the merged output is always LMDB.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from tqdm import tqdm

from .lmdb_pack import pack_lmdb

if TYPE_CHECKING:
    from collections.abc import Iterator

SPLITS: tuple[str, ...] = ("train", "val")


def _detect_split_format(split_dir: Path) -> str | None:
    """Return "lmdb", "raw", or None (split absent/unrecognized)."""
    if (split_dir / "lmdb" / "data.mdb").exists():
        return "lmdb"
    if (split_dir / "labels.txt").exists():
        return "raw"
    return None


def _iter_raw_split_samples(split_dir: Path) -> Iterator[tuple[bytes, str, str]]:
    """Yield (image_bytes, file_extension, text) for a raw labels.txt + images/ split."""
    labels_path = split_dir / "labels.txt"
    images_dir = split_dir / "images"

    with labels_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            img_name, text = parts[0].strip(), parts[1]

            img_path = images_dir / img_name
            if not img_path.exists():
                img_path = split_dir / img_name
            if not img_path.exists():
                continue

            ext = img_path.suffix or ".jpg"
            yield img_path.read_bytes(), ext, text


def _iter_lmdb_split_samples(split_dir: Path) -> Iterator[tuple[bytes, str, str]]:
    """Yield (image_bytes, file_extension, text) for an lmdb/ split.

    Image bytes are the exact bytes stored in the LMDB (already JPEG-encoded).
    """
    import lmdb  # type: ignore[import-untyped]

    lmdb_dir = split_dir / "lmdb"
    env = lmdb.open(str(lmdb_dir), readonly=True, lock=False, readahead=False, meminit=False)
    try:
        with env.begin(write=False, buffers=True) as txn:
            raw = txn.get(b"num-samples")
            if raw is None:
                return
            num_samples = int(bytes(raw).decode())
            for i in range(1, num_samples + 1):
                img_bytes = txn.get(f"image-{i:09d}".encode())
                lbl_bytes = txn.get(f"label-{i:09d}".encode())
                if img_bytes is None or lbl_bytes is None:
                    continue
                yield bytes(img_bytes), ".jpg", bytes(lbl_bytes).decode("utf-8")
    finally:
        env.close()


def _iter_split_samples(split_dir: Path, fmt: str) -> Iterator[tuple[bytes, str, str]]:
    if fmt == "lmdb":
        yield from _iter_lmdb_split_samples(split_dir)
    else:
        yield from _iter_raw_split_samples(split_dir)


def combine_datasets(
    input_dirs: list[str | Path],
    output_dir: str | Path,
    *,
    keep_raw: bool = False,
    jpeg_quality: int = 90,
    map_size_gb: int = 256,
    verbose: bool = False,
) -> dict[str, int]:
    """Merge multiple datasets into *output_dir*, per split, as LMDB.

    Each dataset root may have either or both of `train/` and `val/`;
    a split missing from an input is simply skipped.
    A split absent from *all* inputs is skipped entirely.

    Args:
        input_dirs: List of dataset root directories to merge.
        output_dir: Where to write the merged dataset.
        keep_raw: If True, keep the intermediate images/ directory after LMDB pack.
        jpeg_quality: JPEG quality for stored images (1-100).
        map_size_gb: LMDB map size in GiB.
        verbose: Print progress messages.

    Returns:
        A dict of split -> merged sample count.
    """
    roots = [Path(d).expanduser().resolve() for d in input_dirs]
    out_root = Path(output_dir).expanduser().resolve()

    for root in roots:
        if not root.exists():
            raise FileNotFoundError(f"Dataset not found: {root}")

    counts: dict[str, int] = {}

    for split in SPLITS:
        # Collect all input splits that exist
        split_inputs: list[tuple[Path, str]] = []
        for root in roots:
            split_dir = root / split
            fmt = _detect_split_format(split_dir)
            if fmt is not None:
                split_inputs.append((split_dir, fmt))

        if not split_inputs:
            if verbose:
                print(f"  No '{split}' split found in any input, skipping")
            continue

        out_split = out_root / split
        merged_images = out_split / "images"
        merged_labels = out_split / "labels.txt"
        merged_images.mkdir(parents=True, exist_ok=True)

        n = 0
        with merged_labels.open("w", encoding="utf-8") as lf:
            for split_dir, fmt in split_inputs:
                if verbose:
                    print(f"  Merging {split_dir} ({fmt}) into {split}...")
                samples = tqdm(
                    _iter_split_samples(split_dir, fmt),
                    desc=f"  Merging {split}",
                    unit="img",
                )
                for img_bytes, ext, text in samples:
                    n += 1
                    img_name = f"img_{n:09d}{ext}"
                    (merged_images / img_name).write_bytes(img_bytes)
                    lf.write(f"{img_name}\t{text}\n")

        if n == 0:
            merged_labels.unlink(missing_ok=True)
            shutil.rmtree(merged_images, ignore_errors=True)
            continue

        counts[split] = n

        # Pack to LMDB
        lmdb_out = out_split / "lmdb"
        lmdb_out.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"  Packing LMDB for {split} ({n} samples)...")
        pack_lmdb(
            labels_file=str(merged_labels),
            images_dir=str(merged_images),
            out_dir=str(lmdb_out),
            jpeg_quality=jpeg_quality,
            map_size_gb=map_size_gb,
            verbose=verbose,
        )

        if not keep_raw:
            shutil.rmtree(merged_images)

    return counts
