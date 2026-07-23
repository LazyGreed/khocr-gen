# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-07-23

### Added
- Real-time `tqdm` progress bars for LMDB packing (`pack_lmdb`), dataset merging (`combine`),
  LMDB image extraction (`view --output-dir`), and corpus filtering during train/val split generation,
  replacing periodic/no-op print statements.
- `configs/combine.yml`: example config file for `khocr-gen combine`, documented in [docs/CONFIG.md](docs/CONFIG.md).

### Fixed
- `khocr-gen combine --config FILE` crashed with `unrecognized arguments: --config`
  because the `combine` subcommand never registered a `-c`/`--config` flag,
  even though it was documented and handled as config-capable by the CLI's YAML-loading logic.
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md): corrected the `verify` options table
  (it documented a nonexistent `--text` flag and omitted `--corpus`, `--count`, `--repeats`,
  `--method`, `--show`), the `view` table (wrong default for `--lmdb`, missing `--count`/
  `--max-count`), the `combine` table (missing `--overwrite`/`--verbose`, wrong default
  output directory), and the `generate` LMDB table (missing `--lmdb-verbose`).

## [0.1.0] - Unreleased

### Added
- Initial release: synthetic OCR dataset generation for Khmer/English text
- `generate` command: render text corpus to training images with augmentations
- `combine` command: merge multiple datasets into one
- `verify` command: render augmentation comparison grids for QA
- `view` command: preview LMDB dataset contents
- Configurable augmentation pipeline with min/max/prob per method
- Multi-process parallel rendering
- LMDB output packing
- Khmer text normalization via khmernormalizer
- Rust acceleration extension (`khocr-gen-core`, in `rust/`): native implementations of 21/24 augmentation methods,
  O(1) cmap-based font glyph checking (`FontFace`), and script-span splitting, with automatic pure-Python fallback when unavailable.
  Built and installed automatically by `uv sync` via a `[tool.uv.sources]` path dependency.
  See [docs/RUST_ACCELERATION.md](docs/RUST_ACCELERATION.md).

### Fixed
- `ImageRenderer._render_mixed_font` passed a `(text, script)` tuple to `draw.text()` instead of the span's text string,
  which would have crashed any mixed-font render (dead code path prior to this fix, since `mixed_font_prob` defaults to `0.0`).
