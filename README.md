# khocr-gen

[![PyPI](https://img.shields.io/pypi/v/khocr-gen.svg)](https://pypi.org/project/khocr-gen/)

Synthetic OCR training data generator for mixed Khmer/English text.

## Features

- **Mixed-script rendering:** per-span font selection for Khmer + English
- **Variable line height:** sample per-image canvas height (fixed/variable/bucketed), with optional proportional font scaling and random padding, no glyph clipping
- **Text decorations:** per-line color, underline, subscript/superscript, italic, and bold sampled at render time (can combine, isolated from augmentations)
- **25 augmentation methods:** unified registry covering scanner/camera degradations and training-time transforms
- **Rust acceleration:** 21/25 augmentation methods plus font glyph checking run through a native PyO3 extension, with automatic pure-Python fallback
- **Isolated augmentation:** one effect per image, weighted by configurable probabilities
- **Configurable intensity ranges:** per-method `[min, max]` with linear sampling
- **Multiprocess generation:** parallel workers for throughput
- **LMDB packing:** efficient key–value storage for training pipelines
- **n-way dataset combine:** merge multiple generated datasets into one
- **Built-in viewer:** preview and extract images from LMDB databases
- **YAML config files:** reproducible generation recipes
- **Khmer normalization:** canonical character ordering via `khmernormalizer`

## Installation

### From PyPI

```bash
pip install khocr-gen
```

### From source

```bash
git clone https://github.com/LazyGreed/khocr-gen.git
cd khocr-gen
pip install .
```

### Requirements

- Python >= 3.12
- Rust toolchain (`cargo`/`rustc`, edition 2021) - only needed to build the optional acceleration extension

## Quick Start

### 1. Prepare fonts

```text
fonts/
├── khmer/     <- .ttf / .otf Khmer fonts
└── english/   <- .ttf / .otf English fonts
```

Fonts placed directly in `fonts/` (not in a subdirectory) are added to both pools as fallbacks.

### 2. Prepare corpus

A plain UTF-8 text file, one string per line:

```text
សួស្តី
Hello World
ស្វាគមន៍ Welcome
```

### 3. Generate a dataset

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --output data --copies 3 --storage lmdb
```

### 4. Verify augmentation quality

Renders every augmentation method at min and max intensity on clean canvases:

```bash
khocr-gen verify --fonts fonts --output verify_output
```

### 5. View generated images

```bash
# Summary of an LMDB database
khocr-gen view --lmdb data/train/lmdb

# Extract images
khocr-gen view --lmdb data/train/lmdb --output-dir extracted

# Show labels only
khocr-gen view --lmdb data/train/lmdb --labels-only
```

### 6. Combine multiple datasets

```bash
khocr-gen combine data_run1 data_run2 data_run3 --output data_merged
```

## Configuration

All generation parameters can be specified via CLI flags, a YAML config file, or both (CLI overrides YAML).
See [CONFIG.md](docs/CONFIG.md) for details.
Example: [generate.yml](configs/generate.yml)

```bash
khocr-gen generate --config configs/generate.yml
```

Config loading order (highest priority wins):
1. argparse built-in defaults
2. YAML config file values
3. Explicit CLI flags

### Dataset Splitting

Synthetic dataset generation supports 3-way disjoint text splitting (`train`, `val`, `test`):

- **Default:** 80% train / 10% val / 10% test (neither flag specified).
- **Only `--val-percent`:** test split set to 0% (e.g. `--val-percent 15` -> 85% train / 15% val / 0% test).
- **Only `--test-percent`:** val split set to 0% (e.g. `--test-percent 15` -> 85% train / 0% val / 15% test).
- **Custom ratios:** `--split-ratios 70 15 15`.
- **Disable split:** `--split-ratios 100 0 0` or `--val-percent 0 --test-percent 0`.

### Background Textures & Colors

- **Textures:** 8 procedural texture overlay modes (`apply_background_texture`) including fine grain, coarse Gaussian, paper fibers, crease/fold lines, watermarks/stains, antique parchment, lined/grid paper, and scanner dust speckles.
- **Color Palettes:** `--bg-color-mode {default, paper_tones, colored, dark_mode, gradient, random}` to render off-white, warm cream/sepia/recycled paper, soft pastels, dark mode (invert), or gradient backgrounds.

### Variable Line Height

By default every image is rendered at a fixed `--height`. `--line-height-mode {variable,bucketed}`
samples a per-image canvas height instead:

```bash
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 --line-height-step 8 \
  --font-size-mode proportional --vertical-padding-mode random
```

Each canvas is rendered at its natural size and uniformly resized (never cropped) to the sampled
height, so glyphs are never clipped. `labels.txt` is unchanged; add `--record-metadata` to also
write a `metadata.jsonl` sidecar with per-image width/height/font info. See
[CLI_REFERENCE.md](docs/CLI_REFERENCE.md#variable-line-height) for the full flag list.

### Text decorations

Per-line text decorations are sampled at render time on the clean canvas (before
augmentation) and can combine. Bold/italic use real variant fonts and are skipped
when no matching variant exists; random colors require `--color-mode 3`.

```text
khocr-gen generate --text-deco-color-prob 0.3 --text-deco-underline-prob 0.2 \
          --text-deco-bold-prob 0.2 --color-mode 3 ...
```

## Augmentation

25 methods in a unified registry (21 of them Rust-accelerated).
Each generated image receives exactly one augmentation, chosen probabilistically by weight.
See [AUGMENTATION.md](docs/AUGMENTATION.md) for the full catalog and visual examples.

## CLI Reference

See [CLI_REFERENCE.md](docs/CLI_REFERENCE.md) for complete command documentation.

## Rust Acceleration

See [RUST_ACCELERATION.md](docs/RUST_ACCELERATION.md) for what's accelerated,
how the native extension is built/installed, and how to iterate on the `rust/` crate.

## Development

```bash
uv sync --extra dev      # installs dev deps + builds the Rust extension via maturin
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pytest            # tests + coverage config from pyproject.toml
uv run ty check          # type check (informational; not yet a merge gate)
```

CI (`.github/workflows/ci.yml`) runs the same commands on a Python 3.12/3.13 matrix, plus a
separate job that builds the `rust/` crate (`cargo build --release`). See
[RUST_ACCELERATION.md](docs/RUST_ACCELERATION.md) for iterating on the Rust crate directly.

## Acknowledgments

khocr-gen builds on excellent open-source libraries:

- [khmernormalizer](https://github.com/seanghay/khmernormalizer) (MIT) - Khmer text normalization
- [OpenCV](https://opencv.org/) (Apache 2.0) - Image processing and augmentation
- [Pillow](https://python-pillow.org/) (HPND) - Font rendering and image creation
- [Albumentations](https://albumentations.ai/) (MIT) - Augmentation primitives
- [NumPy](https://numpy.org/) (BSD-3-Clause) - Numerical operations
- [LMDB](https://www.symas.com/lmdb) (OpenLDAP 2.8) - Embedded database for training pipelines

## License

MIT
