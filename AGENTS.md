# AGENTS.md

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

---

## Verify

```bash
uv sync --extra dev                          # builds the Rust extension via maturin
uv run ruff check .                          # HARD gate
uv run ty check                              # non-blocking in CI
uv run pytest --cov=khocr_gen --cov-report=term-missing
cargo fmt --check                            # non-blocking
cargo clippy --all-targets -- -D warnings    # non-blocking
cargo build --release
```

Two CI jobs (`.github/workflows/ci.yml`) run on Python 3.12 and 3.13.

The python job: `uv sync --extra dev --python <version>`, `uv run ruff check .`
(**hard gate**), `uv run ty check` (allowed to fail), `uv run pytest
--cov=khocr_gen --cov-report=term-missing`.

The rust job: `cargo fmt --check` (allowed to fail), `cargo clippy --all-targets --
-D warnings` (allowed to fail), `cargo build --release`.

Only ruff can fail the build. Everything else is advisory, which means a green CI run
is not evidence that the types or the Rust side are clean.

CI never invokes the `khocr-gen` CLI itself, so the CLI surface is covered only by
whatever the tests import — a new subcommand or flag with no test is unverified.

`publish.yml` builds the sdist and wheel and pushes to PyPI with `uv publish`.

## Cross-repo couplings

- **Version floor.** `pyproject.toml`'s version is what `../fintech-ocr` pins
  (`khocr-gen>=0.1.12`), and `publish.yml` makes a release here an upstream event
  there. Bump deliberately: that floor is what protects the corpus and augmentation
  contract the other repo trains against.
- **Dataset shape.** The generated LMDB dataset layout and the augmentation method set
  are consumed by `fintech-ocr`'s training pipeline. Changing either crosses the
  boundary.
- **The Rust extension is optional.** `rust/` builds `khocr-gen-core`, a PyO3
  extension exposed as `_rust_accel`, and `_rust_accel.py` is the shim that decides
  which path you get. Without the extension the Python path must still run, so a
  Rust-only code path is a bug.
- **The wiki is generated from `wiki/`.** Edit the source here, then run
  `scripts/publish_wiki.sh`. Renaming a heading breaks incoming cross-links (see the
  note about `wiki/CLI-Reference.md#khocr-gen-verify`).
- **Shared house style.** `khocr-gen`, `fintech-ocr`, `khmerocr_api` and
  `khmerocr-portal` share a byte-identical `HOUSE-STYLE.md`. Load the `house-style`
  skill before writing docs, comments, commit messages or issue text in any of them.

## Operational Failure Ledger

| Date | Symptom | Root cause | Preventative rule |
| --- | --- | --- | --- |
| — | Machine-sounding prose shipped and had to be cleaned up twice | The house style's tells were not applied at write time; `0fc9884`, `d51e6cf`, `6515876`, `32e2391` and `747e01d` were all needed to undo it | Load the `house-style` skill before writing docs, comments or commit messages |
| — | Comment banners and comments that restated the code | Comments narrated the obvious instead of explaining why (`6515876`, `32e2391`) | Comments say why. No banner dividers, no restating the signature |
| — | The corpus was over-materialized and every process duplicated its own font loads | `292e7a9` / `cf306df` (NIG-29) | Bound corpus materialization and share font loading across processes |
| — | Decorations were missing from parallel metadata and unmatched bold/italic styles were dropped silently | `f719c4f` | Record every decoration in the metadata and reject unmatched styles loudly |
| — | The publish workflow was rejected by GitHub's secrets-in-`if` validation | `e687568` | A secret cannot be referenced in a workflow `if` condition |
