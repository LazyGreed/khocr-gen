# khocr-gen

[![PyPI](https://img.shields.io/pypi/v/khocr-gen.svg)](https://pypi.org/project/khocr-gen/)

Synthetic OCR training data generator for mixed Khmer/English text.

## Features

- **Mixed-script rendering:** per-span font selection for Khmer + English
- **24 augmentation methods:** unified registry covering scanner/camera degradations and training-time transforms
- **Rust acceleration:** 21/24 augmentation methods plus font glyph checking run through a native PyO3 extension, with automatic pure-Python fallback
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

## Augmentation

24 methods in a unified registry (21 of them Rust-accelerated).
Each generated image receives exactly one augmentation, chosen probabilistically by weight.
See [AUGMENTATION.md](docs/AUGMENTATION.md) for the full catalog and visual examples.

## CLI Reference

See [CLI_REFERENCE.md](docs/CLI_REFERENCE.md) for complete command documentation.

## Rust Acceleration

See [RUST_ACCELERATION.md](docs/RUST_ACCELERATION.md) for what's accelerated, how the
native extension is built/installed, and how to iterate on the `rust/` crate.

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
