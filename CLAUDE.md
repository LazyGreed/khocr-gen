# CLAUDE.md

Orientation for `khocr-gen`. If you are changing the generator, the augmentation
pipeline, or the CLI, the detail you need is likely in here or in `docs/`.

Anything with words in it (docs, comments, commit messages, issues) follows
[HOUSE-STYLE.md](HOUSE-STYLE.md).

## Project

Synthetic OCR training data generator for mixed Khmer/English text. Renders text lines
from a corpus with per-method augmentation, then packs the result into an LMDB dataset.
Python `>=3.12`, dependencies managed with `uv`.

## Commands

```bash
uv sync --extra dev          # install (builds the Rust extension via maturin)
uv run khocr-gen --help      # generate | combine | verify | view

uv run khocr-gen generate -c configs/generate.yml
uv run khocr-gen combine  -c configs/combine.yml

uv run pytest -q             # tests
uv run pytest tests/test_config.py -q
uv run ruff check .          # lint
uv run ty check              # types, non-blocking in CI

cd rust && cargo build --release   # Rust acceleration crate on its own
```

CI (`.github/workflows/ci.yml`) runs the install, lint, type-check, test and Rust build steps
on Python 3.12 and 3.13. It never invokes `khocr-gen` itself, so the CLI surface is only
covered by whatever the tests import. Ruff is a hard gate; `ty`, `cargo fmt --check` and
`cargo clippy` are visible but allowed to fail.

## Layout

| Path | What's there |
| --- | --- |
| `src/khocr_gen/` | the package. `cli.py` dispatches to `generate`, `combine_cmd`, `verify`, `viewer` |
| `src/khocr_gen/config.py` | the option surface, roughly 1300 lines. Most flags live here |
| `src/khocr_gen/rendering.py` | glyph layout and line rendering |
| `src/khocr_gen/augmentation.py` | the augmentation methods |
| `src/khocr_gen/data_generator.py` | the generate pipeline, corpus to LMDB |
| `rust/` | `khocr-gen-core`, a PyO3 extension exposing `_rust_accel`. Optional |
| `configs/` | `generate.yml`, `combine.yml` |
| `docs/` | reference docs: config keys, CLI, augmentation |
| `wiki/` | source for the GitHub wiki. Edit here, then run `scripts/publish_wiki.sh` |
| `tests/` | pytest suite |

`corpus/`, `data/`, `fonts*/`, and `dist/` are gitignored. The repo carries a `uv.lock`
locally but does not commit it, so dependency resolution is from `pyproject.toml`.

## Gotchas

- `-c/--config` loads YAML and pushes its values in as argparse defaults, so a flag passed
  on the command line still beats the config file. Only `generate` and `combine` read config.
- `wiki/` is the wiki's source of truth. `scripts/publish_wiki.sh` copies `wiki/*.md` into
  the `<repo>.wiki.git` clone, so edit `wiki/`, not the published pages. `wiki/README.md` is
  the one file there that is not a wiki page.
- The docs link to each other by heading anchor, both across files
  (`docs/CLI_REFERENCE.md#variable-line-height`, linked from `README.md`) and within one page
  (`wiki/CLI-Reference.md#khocr-gen-verify`). Renaming a heading breaks them.
- The Rust extension is optional. Without it the Python path runs; `_rust_accel.py` is the
  shim that decides which one you get.
