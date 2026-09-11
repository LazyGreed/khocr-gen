# Installation

## Requirements

| Requirement | Version | Needed for |
|-------------|---------|------------|
| Python | **≥ 3.12** | everything |
| pip | any recent | PyPI install |
| Rust toolchain (`cargo`, `rustc`) | edition 2021 | building the optional `_rust_accel` extension |
| `uv` | any recent | recommended for development |

No GPU is required — generation is CPU-bound image work.

## From PyPI

```bash
pip install khocr-gen
```

This installs the Python package. The Rust acceleration extension is **not** included in the
PyPI wheel; without it every accelerated code path transparently falls back to pure
Python/OpenCV. See **[Rust Acceleration](Rust-Acceleration)**.

Verify the install:

```bash
khocr-gen --version
khocr-gen --help
```

## From source

```bash
git clone https://github.com/LazyGreed/khocr-gen.git
cd khocr-gen
pip install .
```

## From source with `uv` (recommended for development)

```bash
uv sync --extra dev
```

`dev` (and `rust`) pull in `khocr-gen-core`, the native extension declared as an editable path
dependency in `pyproject.toml`:

```toml
[tool.uv.sources]
khocr-gen-core = { path = "rust", editable = true }
```

`uv sync` therefore **compiles the Rust crate via maturin** as part of dependency resolution. The
Python package then imports the extension as `khocr_gen._rust_accel`.

Check whether acceleration is active:

```bash
uv run python -c "from khocr_gen import _rust_accel as ra; print(ra.HAS_RUST_ACCEL)"
```

`HAS_RUST_ACCEL` is detected once at import time. `True` means the native extension loaded.

### If you don't have Rust

`uv sync --extra dev` will fail on the `khocr-gen-core` package if `cargo` is not on `PATH`.
Either:

- install Rust from <https://rustup.rs>, or
- remove the `khocr-gen-core` entry from the `dev` / `rust` extras in `pyproject.toml` before
  syncing to get a pure-Python environment.

## Optional extras

| Extra | Adds |
|-------|------|
| `rust` | `khocr-gen-core` only — the native acceleration extension |
| `dev` | `pytest`, `pytest-cov`, `ruff`, `ty`, plus `khocr-gen-core` |

```bash
uv sync --extra rust      # acceleration without the test/lint toolchain
uv sync --extra dev       # full development environment
```

## Runtime dependencies

| Package | Purpose |
|---------|---------|
| `opencv-python-headless` | image processing and augmentation kernels |
| `numpy` | array operations |
| `pillow` | font rendering and image creation |
| `albumentations` | augmentation primitives for `blur`, `distortion`, `albu_noise` |
| `tqdm` | progress bars |
| `khmernormalizer` | Khmer text normalization |
| `pyyaml` | `--config` YAML loading |
| `lmdb` | LMDB packing and reading |

## Platform notes

- **Linux / macOS / Windows** are all supported for the Python package.
- The Rust extension builds on all three; building requires a working C toolchain
  (`cc`/`link.exe`) in addition to `cargo`.
- On headless servers, `opencv-python-headless` avoids pulling GUI libraries.

## Next steps

- **[Getting Started](Getting-Started)** — first dataset end to end
- **[Rust Acceleration](Rust-Acceleration)** — building and iterating on `rust/`
- **[Development](Development)** — running the test suite and CI checks locally
