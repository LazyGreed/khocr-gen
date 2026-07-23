# Rust Acceleration

`khocr-gen` ships an optional native extension, `_rust_accel`, that speeds up the hottest
paths in the generation pipeline: pixel-level augmentation and font glyph checking. It is
built with [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs) from the `rust/` crate
(package name `khocr-gen-core`) and installed as a regular editable dependency of the
`khocr-gen` Python project — no separate build step is required.

Every accelerated code path has a pure-Python fallback, so the project works with or
without a Rust toolchain. Acceleration is detected once at import time via
`khocr_gen._rust_accel.HAS_RUST_ACCEL`.

## Installation

```bash
uv sync            # also compiles and installs khocr-gen-core from rust/
uv sync --extra dev
```

Building `khocr-gen-core` requires a Rust toolchain (`cargo`/`rustc`, edition 2021) on
`PATH`. If it's missing, `uv sync` will fail on that package — installing Rust
(https://rustup.rs) resolves it. There is currently no pip/PyPI-only path that skips
compilation; if you need a pure-Python-only environment, remove the `khocr-gen-core`
line from the `dev`/`rust` extras in `pyproject.toml` before syncing.

```bash
uv run python -c "from khocr_gen import _rust_accel as ra; print(ra.HAS_RUST_ACCEL)"
```

### Manual iteration on the Rust crate

For fast edit/build/test cycles on `rust/src/*.rs` without going through `uv sync`
each time, build directly against the project's existing `.venv`:

```bash
VIRTUAL_ENV=/path/to/khocr-gen/.venv uv run --with maturin maturin develop --release --manifest-path rust/Cargo.toml
```

**Do not** `cd rust && uv run --with maturin maturin develop`. `rust/pyproject.toml`
declares its own (maturin) project, so a bare `uv run` from inside `rust/` treats it as
a separate project root and creates a stray `rust/.venv` — the extension gets installed
there instead of the real project environment, and it silently looks like the build
"isn't taking effect." Always pin `VIRTUAL_ENV` to the top-level `.venv` (or run from the
repo root with `--manifest-path`) when building manually.

Also note: `uv sync` re-resolves and re-installs declared dependencies on every
invocation. If you hand-build with `maturin develop` for a quick iteration, a later
`uv sync` may reinstall its own cached build of `khocr-gen-core` over yours. Run
`uv cache clean khocr-gen-core` if `uv sync` seems to reinstall a stale binary (e.g. a
build missing a class/function you just added).

## What's accelerated

### Augmentation (21 of 24 methods)

`khocr_gen.augmentation.AUG_METHODS` transparently swaps in the native implementation for
each method below when `HAS_RUST_ACCEL` is true; otherwise the pure-Python/OpenCV
implementation is used. See [AUGMENTATION.md](AUGMENTATION.md) for what each method does.

Accelerated: `sauvola`, `geo_warp`, `vertical_crop`, `blur`, `jpeg_compression`,
`rotation`, `salt_pepper`, `background_texture`, `lowdpi`, `oversample`, `perspective`,
`elastic`, `random_crop`, `online_blur`, `online_noise`, `hsv`, `reverse`,
`brightness_contrast`, `pixelation`, `morphological`, `anisotropic_dilation`.

Not accelerated (pure Python/Albumentations only): `distortion`, `albu_noise` (thin
wrappers around Albumentations' own compiled pipeline — no native win to be had), and
`gradient_illumination` (the Rust implementation is grayscale-only, but the renderer may
pass RGB arrays through `_RGB_PREFERRED_METHODS`, so it's excluded until an RGB path is
added).

### Font glyph checking (`FontFace`)

`ImageRenderer._is_text_supported` (in `rendering.py`) uses `_rust_accel.FontFace` for
O(1) cmap-table glyph-existence checks, replacing the previous approach of rasterizing
each candidate character with PIL and diffing it against the font's "tofu" (`.notdef`)
glyph. One `FontFace` is parsed and cached per font path
(`ImageRenderer._font_face_cache`); lookups after that are just a cmap binary search, no
rasterization. Falls back to the PIL rasterization/tofu-diff approach when Rust
acceleration is unavailable or a given font file fails to parse.

### Script-span splitting (`split_text_spans`)

`ImageRenderer._render_mixed_font` uses `_rust_accel.split_text_spans` to split mixed
Khmer/English text into contiguous per-script spans, instead of the equivalent
pure-Python `ImageRenderer._split_text_into_spans` (kept as the fallback implementation).

### Utilities

`estimate_bg`, `image_is_blank`, and `write_image` (background-color estimation,
blank-canvas detection, and JPEG/PNG encoding) all have native implementations wired
into `augmentation.py`'s helper calls.

### Built, but not yet wired up

- **`RustFontManager`** — a native counterpart to `khocr_gen.fonts.FontManager`
  (font loading, glyph/text support checks, Khmer detection). It's built and exported
  from `_rust_accel.py`, but the actual generation pipeline still uses the pure-Python
  `FontManager`, since it needs to hand back real `PIL.ImageFont` objects for
  `ImageDraw.text()` — `RustFontManager` doesn't produce those. It's available for
  anyone who wants fast font metadata/coverage queries independent of rendering.
- **`rendering.rs`** — a from-scratch Rust reimplementation of canvas rendering
  (clean-canvas draw, resize/pad, mixed-font compositing) exists in `rust/src/rendering.rs`
  but has no `#[pyclass]`/`#[pyfunction]` bindings and is not registered in the
  `_rust_accel` `#[pymodule]` in `lib.rs`. It compiles (with "never used" warnings) but
  is dead code from Python's perspective — a starting point for a future full-pipeline
  rendering port, not something currently exercised.

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

`pyproject.toml` (project root) declares `khocr-gen-core` as a path dependency via
`[tool.uv.sources]`, pointing at `rust/` with `editable = true`, under both the `rust`
and `dev` optional-dependency extras. That's what makes `uv sync` build and keep it
installed automatically.
