# Rust Acceleration

`khocr-gen` ships an optional native extension, `_rust_accel`, that speeds up the hottest paths in
the generation pipeline: pixel-level augmentation and font glyph checking.

It is built with [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs) from the `rust/` crate
(package name `khocr-gen-core`) and installed as a regular editable dependency of the Python project
— there is no separate build step.

**Every accelerated code path has a pure-Python fallback**, so the project works with or without a
Rust toolchain. Acceleration is detected once at import time:

```python
from khocr_gen import _rust_accel as ra
print(ra.HAS_RUST_ACCEL)   # True when the native extension loaded
```

## Installation

```bash
uv sync              # also compiles and installs khocr-gen-core from rust/
uv sync --extra dev
```

Building `khocr-gen-core` requires a Rust toolchain (`cargo`/`rustc`, edition 2021) on `PATH`. If
it's missing, `uv sync` will fail on that package — installing Rust (<https://rustup.rs>) resolves
it.

There is currently **no pip/PyPI-only path that skips compilation**. The PyPI wheel is pure Python;
if you need a pure-Python-only environment from source, remove the `khocr-gen-core` entry from the
`dev`/`rust` extras in `pyproject.toml` before syncing.

```bash
uv run python -c "from khocr_gen import _rust_accel as ra; print(ra.HAS_RUST_ACCEL)"
```

## What's accelerated

### Augmentation — 21 of 26 methods

`khocr_gen.augmentation.AUG_METHODS` transparently swaps in the native implementation for each
method below when `HAS_RUST_ACCEL` is true; otherwise the pure-Python/OpenCV implementation is used.

**Accelerated:** `sauvola`, `geo_warp`, `vertical_crop`, `blur`, `jpeg_compression`, `rotation`,
`salt_pepper`, `background_texture`, `lowdpi`, `oversample`, `perspective`, `elastic`, `random_crop`,
`online_blur`, `online_noise`, `hsv`, `reverse`, `brightness_contrast`, `pixelation`,
`morphological`, `anisotropic_dilation`.

**Not accelerated:**

| Method | Why |
|--------|-----|
| `distortion`, `albu_noise` | Thin wrappers around Albumentations' own compiled pipeline — no native win to be had |
| `gradient_illumination` | The Rust implementation is grayscale-only, but the renderer may pass RGB arrays through `_RGB_PREFERRED_METHODS`, so it's excluded until an RGB path is added |
| `extreme_resize` | No native implementation yet |
| `low_contrast_caption` | No native implementation yet |

### Font glyph checking (`FontFace`)

`ImageRenderer._is_text_supported` uses `_rust_accel.FontFace` for **O(1) cmap-table glyph-existence
checks**, replacing the previous approach of rasterising each candidate character with PIL and
diffing it against the font's "tofu" (`.notdef`) glyph.

One `FontFace` is parsed and cached per font path (`ImageRenderer._font_face_cache`); lookups after
that are just a cmap binary search with no rasterisation. The PIL rasterisation/tofu-diff approach
remains the fallback when Rust acceleration is unavailable or a font file fails to parse.

### Script-span splitting (`split_text_spans`)

`ImageRenderer._render_mixed_font` uses `_rust_accel.split_text_spans` to split mixed Khmer/English
text into contiguous per-script spans, replacing the equivalent pure-Python
`ImageRenderer._split_text_into_spans` (kept as the fallback).

### Utilities

`estimate_bg`, `image_is_blank` and `write_image` — background-colour estimation, blank-canvas
detection and JPEG/PNG encoding — all have native implementations wired into `augmentation.py`'s
helper calls.

### Built but not wired up

- **`RustFontManager`** — a native counterpart to `khocr_gen.fonts.FontManager` (font loading, glyph
  and text support checks, Khmer detection). It is built and exported from `_rust_accel.py`, but the
  generation pipeline still uses the pure-Python `FontManager`, because it needs to hand back real
  `PIL.ImageFont` objects for `ImageDraw.text()` — `RustFontManager` does not produce those. It is
  available for anyone who wants fast font metadata/coverage queries independent of rendering.
- **`rendering.rs`** — a from-scratch Rust reimplementation of canvas rendering (clean-canvas draw,
  resize/pad, mixed-font compositing) exists in `rust/src/rendering.rs` but has no
  `#[pyclass]`/`#[pyfunction]` bindings and is not registered in the `_rust_accel` `#[pymodule]` in
  `lib.rs`. It compiles (with "never used" warnings) but is dead code from Python's perspective — a
  starting point for a future full-pipeline rendering port, not something currently exercised.

## Module layout

```text
rust/
├── Cargo.toml           # crate: khocr-gen-core, cdylib, PyO3 abi3-py312
├── pyproject.toml       # maturin build config (module-name = "_rust_accel")
└── src/
    ├── lib.rs           # PyO3 bindings + #[pymodule] registration (the only file Python sees)
    ├── augmentation.rs  # 20 accelerated augmentation methods + RGB variants
    ├── fonts.rs         # FontEntry/FontManager (native) + FontFace (cmap glyph lookup)
    ├── rendering.rs     # unwired canvas-rendering prototype (see above)
    └── utils.rs         # background estimation, blank-image check, clamp helpers
```

The project-root `pyproject.toml` declares `khocr-gen-core` as a path dependency via
`[tool.uv.sources]`, pointing at `rust/` with `editable = true`, under both the `rust` and `dev`
optional-dependency extras. That is what makes `uv sync` build and keep it installed automatically.

## Iterating on the Rust crate

For fast edit/build/test cycles on `rust/src/*.rs` without going through `uv sync` each time, build
directly against the project's existing `.venv`:

```bash
VIRTUAL_ENV=/path/to/khocr-gen/.venv uv run --with maturin maturin develop --release --manifest-path rust/Cargo.toml
```

> **Do not** `cd rust && uv run --with maturin maturin develop`. `rust/pyproject.toml` declares its
> own (maturin) project, so a bare `uv run` from inside `rust/` treats it as a separate project root
> and creates a stray `rust/.venv` — the extension gets installed there instead of the real project
> environment, and it silently looks like the build "isn't taking effect". Always pin `VIRTUAL_ENV`
> to the top-level `.venv` (or run from the repo root with `--manifest-path`) when building manually.

Also note: `uv sync` re-resolves and re-installs declared dependencies on every invocation. If you
hand-build with `maturin develop` for a quick iteration, a later `uv sync` may reinstall its own
cached build over yours. Run `uv cache clean khocr-gen-core` if `uv sync` seems to reinstall a stale
binary (for example a build missing a class or function you just added).

## Verifying acceleration is active

```bash
uv run python -c "from khocr_gen import _rust_accel as ra; print(ra.HAS_RUST_ACCEL)"
```

`True` means the extension is loaded and the registry swapped in the native methods. Generation
output is equivalent either way — the fallbacks implement the same behaviour — but pixel-identical
output between Rust and Python paths is not guaranteed for methods that draw from their own thread
RNG. See the note in **[Augmentation](Augmentation)** about `verify` reproducibility.

There is also a timing harness at the repo root:

```bash
uv run python benchmark_rust_vs_python_aug.py
```

## CI

`.github/workflows/ci.yml` runs two jobs:

- **python** — `ruff check`, `ty check` (non-blocking), and `pytest --cov` on a Python 3.12/3.13
  matrix, after `uv sync --extra dev` builds the extension via maturin.
- **rust** — `cargo fmt --check` (non-blocking), `cargo clippy -D warnings` (non-blocking), and
  `cargo build --release` (the real gate) in `rust/`.

## See also

- **[Augmentation](Augmentation)** — what each accelerated method does
- **[Development](Development)** — the full local dev loop
- **[Architecture](Architecture)** — where the extension plugs into the pipeline
