# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-07-24

### Fixed
- `apply_hsv` / `apply_brightness_contrast` (Rust acceleration, `rust/src/augmentation.rs`):
  at `intensity == 0.0` (the MIN-intensity case exercised by `khocr-gen verify`), the sampled
  `rand::gen_range` bounds collapsed to a single point (e.g. `1.0..1.0` for `hsv`'s saturation/
  value multiplier, `0.0..0.0` for `brightness_contrast`'s beta offset). `rand` panics on an
  empty range, and since the crate builds with `panic = "abort"`, this crashed the whole
  process (SIGABRT) rather than raising a catchable Python exception — `khocr-gen verify`
  aborted partway through generating comparison images. Both call sites now fall back to the
  degenerate point directly instead of sampling when the range is empty.
- `apply_gradient_illumination` (`augmentation.py`): the gradient array was shaped `(1, w)`/
  `(h, 1)` for grayscale broadcasting, but the method is RGB-preferred and always receives
  `(h, w, 3)` arrays from the renderer/`verify`, causing a `ValueError` on the multiply that
  `verify.py` silently swallowed and reported as "failed to apply augmentation; skipping."
  Added a trailing channel axis so the gradient broadcasts correctly against RGB input.
- `_wrap_grayscale_rust_fn`'s inner wrapper (`augmentation.py`) was annotated to always return
  `np.ndarray` but could return `None` (already handled correctly by callers); widened the
  return type to `np.ndarray | None` to fix a `ty check` diagnostic with no behavior change.

## [0.1.2] - 2026-07-24

### Added
- Variable line-height generation: `--line-height-mode {fixed,variable,bucketed}` samples a
  per-image canvas height from `--min-line-height`/`--max-line-height` (optionally aligned to
  `--line-height-step`, with a `uniform` or `triangular` distribution). `--font-size-mode
  proportional` and `--vertical-padding-mode random` let glyph scale and top/bottom padding
  scale with the sampled height instead of the previous fixed-pixel behavior. Height sampling
  is deterministic under a given RNG seed, every generated canvas is scaled (never cropped) to
  its target height so Khmer diacritics are never clipped, and `labels.txt` is unaffected —
  variable height is encoded purely in image dimensions. Optional `--record-metadata` writes a
  `metadata.jsonl` sidecar (image/text/width/height/font/font_size) per split, and each split's
  generation summary now reports the observed height range. Default behavior (`--line-height-mode
  fixed`) is unchanged. See [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md#variable-line-height)
  and [docs/CONFIG.md](docs/CONFIG.md).
- GitHub Actions CI (`.github/workflows/ci.yml`):
  a `python` job (3.12/3.13 matrix) running `ruff check`, `ruff format --check`, `pytest --cov`,
  and a non-blocking `ty check`;
  a `rust` job building the `khocr-gen-core` crate (`cargo build --release`),
  with non-blocking `cargo fmt --check`/`clippy` until the existing Rust source is brought in line separately.
- `ty` added to the `dev` extra as the project's type checker
  (config for it already existed in `pyproject.toml` but was unused).
- Warning/debug-level logging around augmentation failures
  (`rendering._apply_augmentation`, and the Albumentations fallback paths in `augmentation.py`)
  so a systematically failing augmentation is now observable in logs instead of silently degrading samples.
- Test coverage for previously untested modules: `data_generator` split orchestration,
  `generate.run()`, `combine_datasets` (mixed raw/LMDB merge, skipped-split handling),
  and expanded `lmdb_pack` round-trip/commit-boundary tests.

### Fixed
- `DatasetGenerator.generate_dataset`: when `--test-file` was combined with a nonzero
  `--test-percent`/`--split-ratios` test ratio, the disjoint ratio-based split *also* carved
  out a test set and both writers wrote into the same `test/` directory, silently mixing
  samples and overwriting the reported count. An explicit `--test-file` now always disables
  the ratio-based test split (mirrors existing `val_file` precedence).
- `ImageRenderer._sample_bg_and_text_colors`: the default-mode RGB text color was built via
  `(random.randint(0, 30),) * 3`, which `ty` flagged as untyped as an exact 3-tuple. Sampled
  once into a local and repeated explicitly instead, fixing the type error with no behavior
  change.

## [0.1.1] - 2026-07-23

### Added
- 3-way disjoint dataset splitting (`train`/`val`/`test`) with configurable ratios (`--test-percent`, `--split-ratios`, `--test-file`) and clear ratio resolution logic.
- Expanded procedural background textures in `apply_background_texture()` with 5 new modes (document creases/folds, watermarks/stains, antique parchment, lined/grid paper, scanner dust speckles).
- Background color palette modes (`--bg-color-mode {default, paper_tones, colored, dark_mode, gradient, random}`) supporting warm paper tones, soft pastels, dark mode (invert), and brightness gradients.
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
