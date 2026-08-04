"""`khocr-gen generate` - synthetic dataset generation CLI command."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .config import GenerationConfig
from .corpus import count_corpus
from .errors import InputValidationError
from .line_height import validate_line_height_config


def _validation_percent(value: str) -> float:
    """Parse validation split percentage for auto-generated val sets."""
    try:
        percent = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("validation split percentage must be a number") from exc
    if not 0.0 <= percent < 100.0:
        raise argparse.ArgumentTypeError(
            "validation split percentage must be in the range [0, 100)."
        )
    return percent


def run(args: argparse.Namespace) -> int:
    """Entry point called by cli.py."""
    from .data_generator import DatasetGenerator

    output_dir = Path(args.output)
    corpus_path = Path(args.corpus)
    fonts_dir = Path(args.fonts)

    # --count-only mode
    if args.count_only:
        if not corpus_path.exists():
            print(f"Corpus file not found: {corpus_path}")
            return 2

        print(f"\nScanning corpus: {corpus_path}")
        print(f"   min_length={args.min_length}\n   max_length={args.max_length}")

        stats = count_corpus(
            corpus_path,
            min_length=args.min_length,
            max_length=args.max_length,
            workers=args.workers,
        )
        cap = args.lines if args.lines > 0 else stats["passing"]
        effective = min(stats["passing"], cap)
        print(f"\n   Total non-blank lines : {stats['total']:>12,}")
        print(f"   Too short (<{args.min_length:>3})      : {stats['too_short']:>12,}")
        print(f"   Too long  (>{args.max_length:<3})      : {stats['too_long']:>12,}")
        print(f"   Passing filter        : {stats['passing']:>12,}")
        print(f"   Cap (--lines)         : {cap:>12,}")
        print("   =====================================")
        print(f"   Lines to generate     : {effective:>12,}")
        print(f"   Augmented copies      : {args.copies}")
        if args.font_mode == "random":
            print(f"   Estimated images      : {effective * args.copies:>12,}")
        if getattr(args, "oversample_rare_chars", False):
            print(
                "   Rare-char oversampling: enabled "
                f"(bottom {args.rare_char_percentile:g}% chars, "
                f"{args.rare_char_multiplier:g}x copies) "
                "- estimate above does not include this boost"
            )
        return 0

    # Validate inputs
    if not corpus_path.exists():
        print(f"Corpus file not found: {corpus_path}")
        return 2
    if not fonts_dir.exists():
        print(f"Fonts directory not found: {fonts_dir}")
        return 2

    print(f"\nLoading corpus from: {corpus_path}")
    print(
        f"   min_length={args.min_length}\n"
        f"   max_length={args.max_length}\n"
        f"   lines_cap={args.lines or 'all'}"
    )

    existing_mode = "error"
    if args.append:
        existing_mode = "append"
    elif args.overwrite:
        existing_mode = "overwrite"

    if output_dir.exists() and any(output_dir.iterdir()) and existing_mode == "error":
        print(f"Dataset output already exists. Re-run with --append or --overwrite: {output_dir}")
        return 1

    # Build config
    gen_cfg = GenerationConfig.from_args(args)
    gen_cfg.fonts_dir = str(fonts_dir)

    try:
        validate_line_height_config(gen_cfg)
    except InputValidationError as exc:
        print(f"error: {exc}")
        return 2

    # Resolve train/val/test ratios using GenerationConfig rules
    _train_ratio, val_ratio, test_ratio = gen_cfg.resolve_split_ratios()

    generator = DatasetGenerator(gen_cfg)

    try:
        generator.generate_dataset(
            corpus_path=corpus_path,
            output_dir=output_dir,
            val_file=args.val_file if hasattr(args, "val_file") else None,
            test_file=getattr(args, "test_file", None),
            copies=args.copies,
            font_mode=args.font_mode,
            retry_limit=args.retry_limit,
            existing_mode=existing_mode,
            workers=args.workers,
            split_seed=args.seed,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
            image_dir=args.image_dir if hasattr(args, "image_dir") else None,
            min_length=args.min_length,
            max_length=args.max_length,
            max_lines=args.lines,
            oversample_rare_chars=getattr(args, "oversample_rare_chars", False),
            rare_char_percentile=getattr(args, "rare_char_percentile", 5.0),
            rare_char_multiplier=getattr(args, "rare_char_multiplier", 3.0),
        )
    except FileExistsError as exc:
        print(exc)
        return 1

    # Build vocab
    if not args.skip_vocab:
        vocab_path = Path(args.vocab) if args.vocab else output_dir / "vocab.json"
        if vocab_path.exists():
            print(f"\nVocabulary already exists at {vocab_path}. Skipping vocab generation.")
        else:
            labels_files = [
                str(output_dir / s / "labels.txt")
                for s in ("train", "val", "test")
                if (output_dir / s / "labels.txt").exists()
            ]
            if labels_files:
                DatasetGenerator._build_vocab(
                    labels_files=labels_files, output_path=str(vocab_path)
                )

    # Pack LMDB (via --storage lmdb|both or legacy --pack-lmdb)
    storage_mode = getattr(args, "storage", "raw")
    pack_lmdb_flag = getattr(args, "pack_lmdb", False)
    keep_raw_flag = getattr(args, "keep_raw", False)

    should_pack = storage_mode in ("lmdb", "both") or pack_lmdb_flag
    should_keep = storage_mode == "both" or (storage_mode == "raw" and keep_raw_flag)

    if should_pack:
        from .lmdb_pack import pack_lmdb

        print("\nPacking into LMDB databases...")
        for split in ["train", "val", "test"]:
            labels_file = output_dir / split / "labels.txt"
            if not labels_file.exists():
                continue
            images_dir = output_dir / split / "images"
            lmdb_dir = output_dir / split / "lmdb"
            lmdb_dir.mkdir(parents=True, exist_ok=True)

            n = pack_lmdb(
                labels_file=str(labels_file),
                images_dir=str(images_dir),
                out_dir=str(lmdb_dir),
                jpeg_quality=getattr(args, "lmdb_jpeg_quality", 90),
                map_size_gb=getattr(args, "lmdb_map_size_gb", 256),
                verbose=getattr(args, "lmdb_verbose", False),
            )
            print(f"   {split}: wrote {n} samples to {lmdb_dir}")

            if images_dir.exists() and not should_keep:
                shutil.rmtree(images_dir)
                print(f"   Removed images directory: {images_dir}")

        print("   LMDB packing complete.")

    print(f"\nGeneration complete. Dataset -> {output_dir}")
    return 0


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register all generate sub-command arguments onto *parser*."""

    parser.add_argument(
        "-c",
        "--config",
        default=None,
        metavar="FILE",
        help="YAML config file. Values override argparse defaults; CLI flags override YAML.",
    )

    # Rendering + Augmentation + Corpus + Output + LMDB + Workers (all flags from GenerationConfig)
    GenerationConfig.add_args(parser)

    # Extra generate-only flags
    g_lmdb = parser.add_argument_group("LMDB Packing (extra)")
    g_lmdb.add_argument("--lmdb-verbose", action="store_true", help="Print LMDB packing progress")
