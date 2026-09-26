# khocr-gen

[![PyPI](https://img.shields.io/pypi/v/khocr-gen.svg)](https://pypi.org/project/khocr-gen/)

Synthetic OCR training data generator for mixed Khmer/English text.

It renders corpus text with configurable fonts and layouts, applies OCR-oriented degradation, and writes datasets as raw images, LMDB, or both.

## Features

- Mixed Khmer/English rendering with per-span font selection.
- Variable and bucketed line heights without glyph clipping.
- Text decorations, visual effects, and 26 augmentation methods.
- Khmer text normalization with `khmernormalizer`.
- Multiprocess generation and deterministic dataset splitting.
- Optional Rust acceleration through `khocr-gen-core`.

## Install

```bash
pip install khocr-gen
```

Python 3.12+ is required.

To work from source:

```bash
git clone https://github.com/LazyGreed/khocr-gen.git
cd khocr-gen
uv sync --extra dev
```

The development extra builds the optional Rust extension.

## Generate a dataset

Prepare fonts:

```text
fonts/
├── khmer/
└── english/
```

Prepare a UTF-8 corpus with one sample per line:

```text
សួស្តី
Hello World
ស្វាគមន៍ Welcome
```

Then run:

```bash
khocr-gen generate \
  --corpus corpus/corpus.txt \
  --fonts fonts \
  --output data \
  --storage lmdb
```

For reproducible runs, start from the included config:

```bash
khocr-gen generate --config configs/generate.yml
```

CLI flags override values loaded from YAML.

## Commands

```bash
khocr-gen generate   # generate a dataset
khocr-gen combine    # merge generated datasets
khocr-gen verify     # render augmentation samples
khocr-gen view       # inspect or extract LMDB data
```

Run `khocr-gen <command> --help` for command-specific options.

## Development

```bash
uv sync --extra dev

uv run ruff check .
uv run pytest --cov=khocr_gen --cov-report=term-missing
uv run ty check
```

For the Rust extension:

```bash
cd rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo build --release
```

Python 3.12 and 3.13 are covered by CI. `ty`, Rust formatting, and Rust clippy are currently informational; Python lint/tests and the Rust release build are merge gates.

## Documentation

- [Documentation index](docs/README.md)
- [Getting Started](https://github.com/LazyGreed/khocr-gen/wiki/Getting-Started)
- [Configuration](docs/CONFIG.md)
- [CLI Reference](docs/CLI_REFERENCE.md)
- [Augmentation](docs/AUGMENTATION.md)
- [Rust acceleration](docs/RUST_ACCELERATION.md)
- [GitHub wiki](https://github.com/LazyGreed/khocr-gen/wiki)

Wiki source lives in `wiki/` and can be published with:

```bash
./scripts/publish_wiki.sh
```

## License

MIT
