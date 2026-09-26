# AGENTS.md

`khocr-gen` generates synthetic OCR training data for mixed Khmer/English text.

Python 3.12+ owns the pipeline. `rust/` provides optional PyO3 acceleration. Keep the Python path working when the Rust extension is unavailable.

## Read first

- `HOUSE-STYLE.md` for prose and comments.
- `src/khocr_gen/config.py` for the generation option surface.
- `docs/` for reference behavior.
- `wiki/` for user-facing documentation.

Code and tests are the source of truth when documentation disagrees.

## Layout

- `src/khocr_gen/` — CLI, rendering, normalization, augmentation, generation, storage.
- `rust/` — optional `khocr-gen-core` acceleration.
- `configs/` — example generation and combine configs.
- `tests/` — pytest suite.
- `docs/` — detailed reference docs.
- `wiki/` — source for the GitHub wiki.

## Invariants

- OCR labels must match the text represented by the rendered image.
- Augmentations may degrade appearance, not silently change label semantics.
- Keep Khmer normalization behavior explicit and tested.
- CLI flags override YAML values; YAML overrides built-in defaults.
- Seeded generation should stay reproducible where the pipeline promises determinism.
- Dataset splits must remain disjoint according to their documented semantics.
- Variable-height rendering must not clip glyphs.
- Rust acceleration is optional. Preserve a compatible Python fallback.

## Working rules

Inspect the relevant implementation and tests before editing.

Keep changes scoped. Don't mix unrelated cleanup into behavioral work.

When adding or changing an option, update its parser/config path, tests, example config where useful, and affected docs.

When touching Rust acceleration, check the Python fallback and boundary in `src/khocr_gen/_rust_accel.py`.

Don't add generated datasets, fonts, build output, or local environments to the repository.

## Validation

For Python changes:

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest --cov=khocr_gen --cov-report=term-missing
uv run ty check
```

`ty` is currently informational in CI.

For Rust changes:

```bash
cd rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo build --release
```

Existing Rust format or clippy debt may be non-blocking in CI. Don't introduce new failures.

Run focused tests while iterating, then the relevant full checks before claiming completion.
