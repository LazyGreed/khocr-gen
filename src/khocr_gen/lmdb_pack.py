"""Pack a labels.txt + image directory into an LMDB database.

Key format:
    b"num-samples"       -> ASCII count of samples written
    b"image-{i:09d}"     -> raw JPEG bytes for sample *i* (1-indexed)
    b"label-{i:09d}"     -> UTF-8 text label for sample *i* (1-indexed)
"""

from __future__ import annotations

import sys
from pathlib import Path

from tqdm import tqdm

_DEFAULT_COMMIT_EVERY_BYTES = 256 * 1024 * 1024  # 256 MiB


def _count_non_empty_lines(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def pack_lmdb(
    labels_file: str | Path,
    images_dir: str | Path,
    out_dir: str | Path,
    *,
    jpeg_quality: int = 90,
    map_size_gb: int = 256,
    verbose: bool = False,
    commit_every: int = 5_000,
    commit_every_bytes: int = _DEFAULT_COMMIT_EVERY_BYTES,
) -> int:
    """Write an LMDB database from *labels_file* and *images_dir*.

    Pending encoded images are flushed to LMDB when either *commit_every*
    samples or *commit_every_bytes* of encoded image data have accumulated,
    whichever comes first -- a count-only bound lets a run of large images
    balloon the transient buffer to gigabytes before a single flush.

    Returns the number of samples written.
    """
    import cv2
    import lmdb

    labels_path = Path(labels_file).expanduser().resolve()
    images_path = Path(images_dir).expanduser().resolve()
    out_path = Path(out_dir).expanduser().resolve()

    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels file not found: {labels_path}")
    if not images_path.is_dir():
        raise FileNotFoundError(f"Images directory not found: {images_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    map_size = map_size_gb * (1024**3)
    env = lmdb.open(str(out_path), map_size=map_size)

    samples_written = 0
    errors = 0
    total_lines = _count_non_empty_lines(labels_path)

    # Batch writes to avoid holding the LMDB write lock for too long
    pending_pairs: list[tuple[bytes, bytes, bytes, bytes]] = []
    pending_bytes = 0

    def _flush(txn, pairs: list) -> None:
        for img_key, img_bytes, lbl_key, lbl_bytes in pairs:
            txn.put(img_key, img_bytes)
            txn.put(lbl_key, lbl_bytes)
        pairs.clear()

    with labels_path.open("r", encoding="utf-8") as fh:
        lines = (ln.rstrip("\n") for ln in fh if ln.strip())

        for line in tqdm(lines, total=total_lines, desc="  Packing LMDB", unit="img"):
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            img_name, label = parts[0].strip(), parts[1]
            img_path = images_path / img_name
            if not img_path.exists():
                # Try next to the labels file
                img_path = labels_path.parent / img_name
            if not img_path.exists():
                if verbose:
                    print(f"  [SKIP] image not found: {img_name}", file=sys.stderr)
                errors += 1
                continue

            img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
            if img is None:
                if verbose:
                    print(f"  [SKIP] cv2.imread failed: {img_name}", file=sys.stderr)
                errors += 1
                continue

            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if not ok:
                errors += 1
                continue

            samples_written += 1
            idx = samples_written
            img_key = f"image-{idx:09d}".encode()
            lbl_key = f"label-{idx:09d}".encode()
            img_bytes = bytes(buf)
            pending_pairs.append((img_key, img_bytes, lbl_key, label.encode("utf-8")))
            pending_bytes += len(img_bytes)

            if len(pending_pairs) >= commit_every or pending_bytes >= commit_every_bytes:
                with env.begin(write=True) as txn:
                    _flush(txn, pending_pairs)
                pending_bytes = 0

    # Flush remaining and write final count
    with env.begin(write=True) as txn:
        _flush(txn, pending_pairs)
        txn.put(b"num-samples", str(samples_written).encode())

    env.close()

    if verbose and errors:
        print(f"  Skipped {errors} samples due to missing/corrupt images", file=sys.stderr)

    return samples_written
