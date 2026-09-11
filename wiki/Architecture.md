# Architecture

This page is for people reading or changing the code. It maps the modules, traces the generation
pipeline, and explains the parallelism model.

## Repository layout

```text
khocr-gen/
├── src/khocr_gen/        # the Python package (~7.6k lines)
├── rust/                 # khocr-gen-core — the optional PyO3 extension
├── configs/              # example YAML recipes (generate.yml, combine.yml)
├── docs/                 # in-repo documentation (this wiki mirrors and extends it)
├── tests/                # pytest suite (~364 tests)
├── typings/              # type stubs used by `ty`
└── .github/workflows/    # ci.yml, publish.yml
```

## Module map

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `cli.py` | 208 | Top-level entrypoint, subcommand dispatch, config-default injection |
| `config.py` | 1301 | `GenerationConfig` — the single source of truth for every generation parameter |
| `config_loader.py` | 149 | YAML loading, key normalisation, key validation, default injection |
| `rendering.py` | 1260 | `ImageRenderer` — text-to-image rendering, decorations, effects, mixed-font compositing |
| `augmentation.py` | 1013 | The 26-method registry and their pure-Python/OpenCV implementations |
| `data_generator.py` | 827 | `DatasetGenerator` — orchestration, splits, output files, vocab |
| `verify.py` | 471 | `khocr-gen verify` — side-by-side MIN/MAX method renders |
| `_rust_accel.py` | 296 | Rust extension loader and graceful fallback shim |
| `corpus.py` | 279 | Corpus loading, filtering, counting, character frequencies |
| `fonts.py` | 269 | `FontManager` — font discovery, pools, style tags, lazy face cache |
| `parallel.py` | 226 | Worker-count/chunk-size resolution, multiprocessing context, chunk dispatch |
| `normalizer.py` | 217 | Khmer normalization wrappers and `NormalizerConfig` |
| `combine.py` / `combine_cmd.py` | 214 / 125 | n-way dataset merging |
| `generate.py` | 210 | `khocr-gen generate` command wiring |
| `viewer.py` | 172 | `khocr-gen view` — LMDB preview and extraction |
| `lmdb_pack.py` | 132 | labels.txt + images → LMDB packing |
| `line_height.py` | 127 | Height/font-scale/padding sampling and validation |
| `errors.py` | 33 | `KhocrGenError` hierarchy |
| `logging.py` | 25 | Logging setup |
| `_pil_compat.py` | 25 | Pillow resampling-constant shims |

### Configuration is centralised

`GenerationConfig` (in `config.py`) is the single source of truth. It owns:

- `add_args(parser)` — registers every CLI flag,
- `from_args(args)` — builds the config from parsed arguments,
- `iter_aug_methods()` / `enabled_aug_methods()` — drives the augmentation registry,
- `resolve_split_ratios()` — normalises the train/val/test ratios,
- `to_dict()` / `from_dict()` — serialisation for worker processes.

Sub-configs are dataclasses: `AugMethodConfig` (with `ExtremeResizeConfig` overriding the
pixel-height semantics), `TextDecorationConfig`, `TextEffectConfig`, and `NormalizerConfig`.

### Errors

```text
KhocrGenError
├── InputValidationError    # bad corpus / flags / config
├── GenerationError         # failures during generation
└── FontLoadError           # font discovery or parsing problems
```

Validation failures are raised as typed errors and surfaced as clean CLI messages rather than
tracebacks.

## The generation pipeline

```text
corpus file
   │  corpus.py — load, filter by length, dedupe
   ▼
text lines
   │  data_generator.DatasetGenerator._split_lines — seeded shuffle, disjoint train/val/test
   ▼
per-split text lists
   │  (optional) rare-character oversampling — train only
   ▼
for each line × copies:
   ├── font selection        fonts.FontManager (script pool, style variants, glyph coverage)
   ├── clean render          rendering.ImageRenderer (decorations → effects → mixed-font spans)
   ├── height/font/padding   line_height.sample_*   (variable line-height modes)
   ├── resize to target      rendering._resize_to_target (uniform resize, never crop)
   └── one augmentation      augmentation.AUG_METHODS (weighted pick, sampled intensity)
   ▼
image + label
   │  data_generator — images/, labels.txt, metadata.jsonl, generation_errors.jsonl
   ▼
   ├── vocab.json            built by scanning the written labels files
   └── lmdb_pack.pack_lmdb   optional: image-N / label-N / num-samples keys
```

Key invariants:

1. **One augmentation per image.** Methods are never stacked; selection is a weighted draw across
   all methods with `prob > 0`.
2. **Decorations and effects happen on the clean canvas**, before augmentation, so an augmentation
   can never corrupt the glyph shapes that make the label correct.
3. **Resize, never crop.** Variable line height is achieved by resizing the naturally-sized canvas,
   so glyphs are never clipped.
4. **Splits are disjoint at the text level.** No text string appears in two splits.

## Parallelism

Generation is chunked across worker processes:

| Concern | Module | Behaviour |
|---------|--------|-----------|
| Worker count | `parallel.resolve_worker_count` | `--workers 0` → auto; 1 when the workload is small (`< 2048` samples), the host has one CPU, or `--workers 1`; otherwise `cpu_count // 2`. An explicit `--workers N` is clamped to `cpu_count`. |
| Chunk size | `parallel.resolve_chunk_size` | Derived from sample count and worker count, clamped to `[64, 256]` (`_DEFAULT_RENDER_CHUNK_SIZE` / `_MAX_RENDER_CHUNK_SIZE`). Serial runs use the default chunk size. |
| Start method | `parallel.resolve_mp_context` | Linux → `fork` (no re-import overhead); macOS/Windows → `spawn`. Override with `KHOCR_GEN_MP_START_METHOD`. |
| Timeout | `--worker-timeout` | Seconds before a worker batch is considered timed out (default 300). |

Config objects are passed to workers via `GenerationConfig.to_dict()` / `from_dict()`. `from_dict`
silently ignores unknown keys, so workers started with an older config dict do not crash when new
keys are added — a deliberate forward-compatibility choice worth preserving when you add fields.

`_AUTO_PARALLEL_MIN_SAMPLES = 2048` in both `augmentation.py` and `parallel.py` gates the automatic
switch to multiprocessing.

## Rendering internals

`ImageRenderer` is the most intricate module. Things worth knowing before changing it:

- **Font face caching** — `_font_face_cache` (Rust `FontFace` per font path) and
  `FontManager._dynamic_font_cache` (bounded LRU, 1024 entries) exist to avoid pinning every
  FreeType face a long run touches. See the memory-fix history in
  [CHANGELOG.md](https://github.com/LazyGreed/khocr-gen/blob/main/CHANGELOG.md).
- **`_RGB_PREFERRED_METHODS`** — the renderer may hand RGB arrays to augmentation methods; that set
  is why `gradient_illumination` is excluded from Rust acceleration.
- **Effects are single-select** — `TEXT_EFFECT_NAMES` is ordered, and sampling walks it taking the
  first probability hit.
- **`DecorStyle`** — the sampled per-line decoration state (active flags, color, sub/superscript
  targets) carried from sampling into drawing.

## Rust boundary

`_rust_accel.py` is the only place Python touches native code. It exposes:

- `HAS_RUST_ACCEL` — the import-time capability flag,
- `FontFace` — cmap glyph lookup,
- `split_text_spans` — mixed-script span splitting,
- `estimate_bg`, `image_is_blank`, `write_image` — utilities,
- `RustFontManager` — built but unused by the pipeline,
- the accelerated `apply_*` augmentation kernels.

Everything is optional: `augmentation.AUG_METHODS` swaps in native implementations when the flag is
set, and `rendering.py` falls back to the pure-Python span splitter and tofu-diff glyph check.
Details in **[Rust Acceleration](Rust-Acceleration)**.

## Testing

`tests/` holds roughly 364 tests across 18 files, mirroring the module layout —
`test_rendering.py`, `test_augmentation.py`, `test_config.py`, `test_line_height.py`,
`test_text_decoration.py`, `test_text_effects.py`, `test_parallel.py`, `test_lmdb_pack.py`,
`test_combine.py`, and others.

Coverage is configured in `pyproject.toml` with branch coverage over `src/khocr_gen`, omitting
`_rust_accel.py` (it is a thin loader over code tested on the Rust side).

## See also

- **[Development](Development)** — build, lint, test, release
- **[Rust Acceleration](Rust-Acceleration)** — the native extension in depth
- **[Output and Storage](Output-and-Storage)** — the files this pipeline produces
