# Development

## Setup

```bash
git clone https://github.com/LazyGreed/khocr-gen.git
cd khocr-gen

uv sync --extra dev      # installs dev deps AND builds the Rust extension via maturin
```

`uv sync --extra dev` resolves `khocr-gen-core` from `rust/` as an editable path dependency, so the
native extension is built and installed as part of the sync. A Rust toolchain
(`cargo`/`rustc`, edition 2021) is required for this step — see
**[Rust Acceleration](Rust-Acceleration)** if you want to skip it.

## Everyday commands

```bash
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pytest            # tests (addopts + coverage config from pyproject.toml)
uv run ty check          # type check (informational; not yet a merge gate)
```

Run a single test file or test:

```bash
uv run pytest tests/test_rendering.py
uv run pytest tests/test_line_height.py -k sample
```

With coverage, as CI does:

```bash
uv run pytest --cov=khocr_gen --cov-report=term-missing
```

## Code style

Ruff is configured in `pyproject.toml`:

| Setting | Value |
|---------|-------|
| `target-version` | `py312` |
| `line-length` | 100 |
| Enabled rules | `E`, `W`, `F`, `I`, `B`, `C4`, `UP`, `SIM`, `TCH`, `RUF` |
| Ignored | `E501` (line too long — handled by the formatter), `B008` |
| isort first-party | `khocr_gen` |
| Format | double quotes, space indent, magic trailing comma preserved |

Because `E501` is ignored, the formatter — not the linter — decides line breaks. Run
`uv run ruff format .` before committing.

## Tests

Roughly 364 tests live in `tests/`, mirroring the module layout:

```text
tests/
├── test_augmentation.py      test_combine.py        test_config.py
├── test_config_loader.py     test_corpus.py         test_data_generator.py
├── test_errors.py            test_fonts.py          test_generate.py
├── test_line_height.py       test_lmdb_pack.py      test_normalizer.py
├── test_online_aug.py        test_parallel.py       test_rendering.py
├── test_text_decoration.py   test_text_effects.py
```

`pytest` is configured with `testpaths = ["tests"]` and `pythonpath = ["src"]`, so tests import the
working tree without an install. Coverage uses branch coverage over `src/khocr_gen` and omits
`_rust_accel.py`.

When you add behaviour, add a test in the matching file. When you fix a bug, add the regression test
that would have caught it.

## Type checking

`ty` runs against `src` with `extra-paths = ["typings"]`. It is currently **informational** —
non-blocking in CI — so treat its output as guidance while the codebase converges. Don't let a new
`ty` error in though; keep the count from growing.

## CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests targeting `main`.

### `python` job — matrix 3.12, 3.13

1. Install Rust toolchain
2. Install `uv` (cache keyed from `pyproject.toml`)
3. `uv sync --extra dev --python <version>` — builds the Rust extension
4. `uv run ruff check .` — **gate**
5. `uv run ty check` — non-blocking (`continue-on-error: true`)
6. `uv run pytest --cov=khocr_gen --cov-report=term-missing` — **gate**

`fail-fast: false`, so both Python versions report even if one fails.

### `rust` job

1. `cargo fmt --check` — non-blocking
2. `cargo clippy --all-targets -- -D warnings` — non-blocking
3. `cargo build --release` — **the real gate**

Formatting and clippy are deliberately non-blocking because the existing code is not yet fully
clean; the comment in the workflow says this cleanup will happen separately. Don't make them
blocking without doing that cleanup first.

> The `python` job's cache comment notes the project intentionally has no `uv.lock`, and
> `uv.lock` is listed in `.gitignore`.

## Releasing

Publishing is automated by `.github/workflows/publish.yml`:

- Triggered by **any tag push** or manually via `workflow_dispatch`.
- Builds `sdist` and wheel with `uv build`, then runs `uv publish`.
- The publish step is **skipped gracefully when the `PYPI_TOKEN` secret is not configured**
  (`if: env.PYPI_TOKEN != ''`) instead of failing the run.

Release checklist:

1. Move the `[Unreleased]` entries in [CHANGELOG.md](https://github.com/LazyGreed/khocr-gen/blob/main/CHANGELOG.md)
   under a new version heading with today's date.
2. Bump `version` in `pyproject.toml`.
3. Commit, then tag: `git tag v0.1.13 && git push origin v0.1.13`.
4. Confirm the publish workflow ran and the version appears on
   [PyPI](https://pypi.org/project/khocr-gen/).

The changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Working on the Rust crate

See **[Rust Acceleration](Rust-Acceleration#iterating-on-the-rust-crate)** — in particular the
warning about `cd rust && uv run …` creating a stray `rust/.venv`, and about `uv sync` overwriting a
hand-built extension.

## Docs

`README.md` is the PyPI-facing page for the repository; `README.pypi.md` is what PyPI renders as the
package description. `docs/` holds the long-form guides, and this wiki mirrors and extends them.

**Any change that affects behaviour, setup, configuration or usage must update the affected docs in
the same change** — `README.md`, the relevant `docs/*.md`, and the matching wiki page here.

## See also

- **[Architecture](Architecture)** — module map and pipeline
- **[Rust Acceleration](Rust-Acceleration)** — native extension workflow
- **[Troubleshooting](Troubleshooting)** — when the dev loop misbehaves
