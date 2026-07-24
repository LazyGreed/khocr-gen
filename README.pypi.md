# khocr-gen

Synthetic OCR training data generator for mixed Khmer/English text.

## Installation

```bash
pip install khocr-gen
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

### 4. View generated images

```bash
# Summary of an LMDB database
khocr-gen view --lmdb data/train/lmdb

# Extract images
khocr-gen view --lmdb data/train/lmdb --output-dir extracted

# Show labels only
khocr-gen view --lmdb data/train/lmdb --labels-only
```

## Configuration

All generation parameters can be specified via CLI flags, a YAML config file, or both (CLI overrides YAML).
See [CONFIG.md](https://github.com/LazyGreed/khocr-gen/blob/main/docs/CONFIG.md) for details.
Example: [generate.yml](https://github.com/LazyGreed/khocr-gen/blob/main/configs/generate.yml)

Config loading order (highest priority wins):
1. argparse built-in defaults
2. YAML config file values
3. Explicit CLI flags

## CLI Reference

See [CLI_REFERENCE.md](https://github.com/LazyGreed/khocr-gen/blob/main/docs/CLI_REFERENCE.md) for complete command documentation.

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
