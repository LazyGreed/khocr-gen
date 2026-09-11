# khocr-gen

[![PyPI](https://img.shields.io/pypi/v/khocr-gen.svg)](https://pypi.org/project/khocr-gen/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/LazyGreed/khocr-gen/blob/main/LICENSE)

**Synthetic OCR training data generator for mixed Khmer/English text.**

`khocr-gen` turns a plain text corpus into a labelled image dataset in one command. It renders
each line of text onto a clean canvas with per-span font selection, samples variable canvas
heights, decorations and Canva-style text effects, then applies exactly one augmentation from a
26-method registry — optionally packing the result straight into LMDB for training.

```text
UTF-8 corpus                                                       training data
text lines  ──▶  font selection ──▶  render ──▶  decorate/effect ──▶  1 augmentation  ──▶  images + labels.txt (+ LMDB)
                  (Khmer/English)     (clean     (per line,          (26 methods,
                                       canvas)     optional)          isolated)
```

## Quick start

```bash
# 1. Install
pip install khocr-gen

# 2. Lay out fonts and a corpus
#    fonts/khmer/*.ttf     fonts/english/*.ttf
#    corpus/corpus.txt     (one UTF-8 string per line)

# 3. Generate
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --output data --copies 3 --storage lmdb

# 4. Inspect what you built
khocr-gen view --lmdb data/train/lmdb --summary

# 5. Eyeball the augmentations
khocr-gen verify --fonts fonts --output verify_output
```

New here? Start with **[Getting Started](Getting-Started)**.

## Feature overview

| Area | What you get |
|------|--------------|
| **Rendering** | Mixed-script (Khmer + English) line rendering with per-span font selection |
| **Fonts** | `khmer/` and `english/` font pools, real bold/italic variant detection, glyph-coverage checks |
| **Variable line height** | `fixed` / `variable` / `bucketed` canvas heights with proportional font sizing and random padding — glyphs are never clipped |
| **Text decorations** | Per-line color, underline, subscript/superscript, italic, bold — combinable |
| **Text effects** | Canva-style huge/tiny, transparent, shadow, glow, outline, hollow, echo, background, neon, glitch, pixel — mutually exclusive |
| **Backgrounds** | 6 colour palettes (paper tones, pastels, dark mode, gradient, random) and 8 procedural paper textures |
| **Augmentation** | 26 methods in one registry, one effect per image, configurable `[min, max]` intensity |
| **Rust acceleration** | 21/26 augmentation methods plus font glyph checking via a native PyO3 extension, with pure-Python fallback |
| **Throughput** | Multiprocess generation with auto worker/chunk sizing |
| **Storage** | Raw images, LMDB, or both; n-way dataset merging with `combine` |
| **Text handling** | Khmer normalization, filtering by length, rare-character oversampling, deterministic 3-way splits |

## Documentation map

### Using it

| Page | Contents |
|------|----------|
| **[Getting Started](Getting-Started)** | Install → fonts → corpus → first dataset, end to end |
| **[Installation](Installation)** | PyPI, source, `uv`, Rust toolchain, optional extras |
| **[CLI Reference](CLI-Reference)** | Every command and flag: `generate`, `verify`, `view`, `combine` |
| **[Configuration](Configuration)** | YAML recipes, precedence rules, full key reference |
| **[Corpus and Normalization](Corpus-and-Normalization)** | Corpus format, filtering, splits, rare-character oversampling |
| **[Fonts](Fonts)** | Directory layout, script selection, bold/italic variants, coverage checks |
| **[Variable Line Height](Variable-Line-Height)** | Height modes, proportional font sizing, padding, metadata sidecar |
| **[Text Decorations and Effects](Text-Decorations-and-Effects)** | All `--text-deco-*` and `--text-effect-*` options |
| **[Augmentation](Augmentation)** | The 26 methods, selection rules, intensity → physical-unit mapping |
| **[Output and Storage](Output-and-Storage)** | Dataset layout, `labels.txt`, `vocab.json`, `metadata.jsonl`, LMDB, `combine` |

### Understanding and extending it

| Page | Contents |
|------|----------|
| **[Architecture](Architecture)** | Module map, generation pipeline, parallelism model |
| **[Rust Acceleration](Rust-Acceleration)** | What is accelerated, how the extension is built, how to iterate on `rust/` |
| **[Development](Development)** | Dev setup, lint/test/type-check, CI, releasing |
| **[FAQ](FAQ)** | Common questions answered briefly |
| **[Troubleshooting](Troubleshooting)** | Symptom → cause → fix |

## Project links

- **Repository:** <https://github.com/LazyGreed/khocr-gen>
- **Issues:** <https://github.com/LazyGreed/khocr-gen/issues>
- **PyPI:** <https://pypi.org/project/khocr-gen/>
- **Changelog:** [CHANGELOG.md](https://github.com/LazyGreed/khocr-gen/blob/main/CHANGELOG.md)

## Requirements

- Python **≥ 3.12**
- Rust toolchain (`cargo` / `rustc`, edition 2021) — only to build the optional acceleration extension
- No GPU required; generation is CPU-bound image work

## License

MIT — see [LICENSE](https://github.com/LazyGreed/khocr-gen/blob/main/LICENSE).
