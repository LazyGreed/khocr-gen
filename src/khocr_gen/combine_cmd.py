"""`khocr-gen combine` - merge multiple generated datasets into one."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def run(args: argparse.Namespace) -> int:
    """Entry point called by cli.py."""
    from .combine import combine_datasets

    input_dirs: list[Path] = [Path(d).expanduser().resolve() for d in args.datasets]
    output_dir = Path(args.output).expanduser().resolve()

    for d in input_dirs:
        if not d.exists():
            print(f"Dataset not found: {d}", file=sys.stderr)
            return 2

    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.overwrite:
            print(f"Output directory already exists. Re-run with --overwrite: {output_dir}")
            return 1
        import shutil

        shutil.rmtree(output_dir)

    print(f"\nCombining {len(input_dirs)} datasets:")
    for d in input_dirs:
        print(f"   {d}")
    print(f"   -> {output_dir}")

    try:
        counts = combine_datasets(
            input_dirs=[str(d) for d in input_dirs],
            output_dir=output_dir,
            keep_raw=getattr(args, "keep_raw", False),
            jpeg_quality=args.jpeg_quality,
            map_size_gb=args.map_size_gb,
            verbose=args.verbose,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not counts:
        print("Nothing to combine, no dataset has a train, val, or test split.")
        return 1

    for split, n in counts.items():
        print(f"   {split}: wrote {n} samples to {output_dir / split / 'lmdb'}")

    print(f"\nCombine complete. Dataset -> {output_dir}")
    return 0


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register all combine sub-command arguments onto *parser*."""

    parser.add_argument(
        "-c",
        "--config",
        default=None,
        metavar="FILE",
        help="YAML config file. Values override argparse defaults; CLI flags override YAML.",
    )
    parser.add_argument(
        "datasets",
        nargs="+",
        metavar="DATASET",
        help="One or more dataset directories to merge (data_1 data_2 ... data_n)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data_combined",
        metavar="DIR",
        help="Output directory for the merged dataset",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output directory without prompting",
    )
    parser.add_argument(
        "--keep-raw", action="store_true", help="Keep raw image files on disk after LMDB packing"
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=90,
        metavar="N",
        help="JPEG compression quality for LMDB images",
    )
    parser.add_argument(
        "--map-size-gb", type=int, default=256, metavar="N", help="LMDB map size in GiB"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print merge and LMDB packing progress"
    )
