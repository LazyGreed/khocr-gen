# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Rust acceleration extension (`khocr-gen-core`, in `rust/`): native implementations of
  21/24 augmentation methods, O(1) cmap-based font glyph checking (`FontFace`), and
  script-span splitting, with automatic pure-Python fallback when unavailable. Built and
  installed automatically by `uv sync` via a `[tool.uv.sources]` path dependency. See
  [docs/RUST_ACCELERATION.md](docs/RUST_ACCELERATION.md).

### Fixed
- `ImageRenderer._render_mixed_font` passed a `(text, script)` tuple to `draw.text()`
  instead of the span's text string, which would have crashed any mixed-font render
  (dead code path prior to this fix, since `mixed_font_prob` defaults to `0.0`).
