# Troubleshooting

Symptom → cause → fix.

---

## Installation

### `uv sync` fails building `khocr-gen-core`

**Cause:** no Rust toolchain on `PATH`. The `dev` and `rust` extras declare the native extension as
an editable path dependency, and it must be compiled.

**Fix:** install Rust from <https://rustup.rs>, or remove the `khocr-gen-core` entry from the
`dev`/`rust` extras in `pyproject.toml` and re-sync for a pure-Python environment.

### `maturin develop` "doesn't take effect"

**Cause:** you ran it from inside `rust/`. `rust/pyproject.toml` declares its own maturin project,
so a bare `uv run` there treats `rust/` as a separate project root and creates a stray
`rust/.venv` — the extension lands there, not in the real environment.

**Fix:** pin the environment and build from the repo root:

```bash
VIRTUAL_ENV=/path/to/khocr-gen/.venv uv run --with maturin maturin develop --release --manifest-path rust/Cargo.toml
```

Delete any stray `rust/.venv` afterward.

### `uv sync` reinstalls a stale extension

**Cause:** `uv sync` re-resolves and reinstalls declared dependencies every run, so it can overwrite
a hand-built `maturin develop` binary with its own cached build.

**Fix:**

```bash
uv cache clean khocr-gen-core
```

### `ModuleNotFoundError: No module named 'yaml'` when using `--config`

**Cause:** PyYAML is required for `--config`/`-c`.

**Fix:** `pip install pyyaml`.

---

## Fonts and rendering

### "No fonts found" / all lines skipped

**Cause:** the font directory layout is wrong, or the pool is empty.

**Fix:** the root given to `--fonts` must contain `khmer/` and/or `english/` subdirectories with
`.ttf`/`.otf`/`.ttc`/`.woff`/`.woff2` files (scanned recursively). Fonts placed directly in the root
join both pools as fallbacks. Check the path is what you think it is — `--fonts fonts` is relative to
the current working directory.

### Images are empty or missing while others render fine

**Cause:** no font in the pool covers the glyphs of those lines, and the retry budget was exhausted.
Khmer coverage varies a lot between fonts.

**Fix:** add more Khmer fonts (especially one with broad coverage), and raise `--retry-limit`.
Check `generation_errors.jsonl` in the split directory — it records render failures. See
**[Fonts](Fonts)**.

### Bold or italic lines never appear

**Cause:** bold/italic use **real variant fonts**. With no file tagged bold (or italic/oblique) in
the pool, the decoration is skipped rather than synthesised.

**Fix:** add variant files such as `NotoSansKhmer-Bold.ttf`. Tags are detected from the filename stem
and the internal style name (`bold`, `italic`, `oblique`).

### `--text-deco-color-prob` has no effect

**Cause:** random text colour requires RGB output.

**Fix:** add `--color-mode 3`.

### Text looks cut off at the top or bottom

**Cause:** this should not happen — the renderer resizes rather than crops. If you see clipping,
suspect a custom `_image-dir` input or a very small explicit `--height`/`--width` combination
pushing glyphs outside the canvas at render time.

**Fix:** reproduce with a minimal case and file an issue with the text, font and flags. As a
workaround, use `--line-height-mode variable` with `--font-size-mode proportional`, which keeps
glyphs inside the canvas by construction.

---

## Corpus and splits

### Zero images generated

**Cause:** every corpus line was filtered out by `--min-length` / `--max-length`, or the corpus file
is empty or not UTF-8.

**Fix:** run `--count-only` to see the filter statistics, and check `--corpus` points at the right
file.

### Expected val/test directories are missing

**Cause:** the split ratio is 0. Setting only one of `--val-percent` / `--test-percent` forces the
other to 0.

**Fix:** set both, or use `--split-ratios 80 10 10`. See
**[Corpus and Normalization](Corpus-and-Normalization)**.

### Two runs with the same `--seed` produced different images

**Cause:** `--seed` only seeds the train/val/test split shuffle; rendering, augmentation and
height sampling use the unseeded module-level RNG.

**Fix:** this is expected. The *split* is reproducible; pixel-level reproducibility is not exposed
as a CLI flag. See **[Variable Line Height](Variable-Line-Height)**.

### Rare characters are still underrepresented

**Cause:** rare-character oversampling is off by default, or the percentile is too strict.

**Fix:** enable `--oversample-rare-chars` and widen `--rare-char-percentile` (e.g. 20). Remember val
and test are never oversampled.

---

## Configuration

### My YAML values are ignored

**Cause (most likely):** a nested mapping. The loader reads **flat keys only**; nested mappings are
skipped with a warning and the default is kept.

**Fix:** replace

```yaml
sauvola:
  prob: 0.2
```

with

```yaml
sauvola-prob: 0.2
```

Watch stderr for `Config key 'sauvola' is a nested mapping; only flat keys are supported, skipping.`
(that line names the key that was dropped). A key that matches no flag warns instead with
`[config] WARNING: Unrecognized keys in 'generate' configuration: …`, which usually means a typo.
Note the fonts key is `fonts`, not `fonts-dir`. See **[Configuration](Configuration)**.

### CLI flags don't override my config

**Cause:** precedence is argparse defaults < YAML < explicit CLI flags. This normally works, but
values written *as* argparse defaults in a wrapper script can shadow the config.

**Fix:** pass flags directly on the command line rather than via a wrapper, or move the value into
the YAML.

### `--height` has no effect

**Cause:** you set `--line-height-mode variable` or `bucketed`. `--height` is only used in `fixed`
mode.

**Fix:** expected. Control heights with `--min-line-height` / `--max-line-height`.

---

## Performance and memory

### Generation is slower than expected

**Causes and fixes, in order of impact:**

1. **Rust acceleration is off** — check `HAS_RUST_ACCEL`. Building the extension is the single
   biggest win. See **[Rust Acceleration](Rust-Acceleration)**.
2. **Too few workers** — the default auto-resolves to `cpu_count // 2`; pass `--workers N`
   explicitly to use more.
3. **Small dataset** — below `2048` samples generation stays serial by design.
4. **`--font-mode all`** — touches every font at every standard size; much heavier than `random`.

### Memory grows during a long run

The font face caches are bounded (LRU, 1024 entries) and were specifically fixed to stop unbounded
growth. If you still see growth, `--workers` multiplies the per-process footprint — lower it, and
prefer `random` over `all` font mode. See the memory fixes in
[CHANGELOG.md](https://github.com/LazyGreed/khocr-gen/blob/main/CHANGELOG.md).

### LMDB packing fails with a map-size error

**Cause:** the dataset exceeds the LMDB map size (default 256 GiB is generous, but small
`--lmdb-map-size-gb` values or a constrained filesystem can bite).

**Fix:** raise `--lmdb-map-size-gb`, or `--map-size-gb` for `combine`.

---

## Multiprocessing

### Hangs or pickling errors on macOS / Windows

**Cause:** these platforms cannot use `fork`.

**Fix:** the tool already selects `spawn` there. If a payload is unpicklable in your environment,
force a method explicitly:

```bash
KHOCR_GEN_MP_START_METHOD=spawn khocr-gen generate ...
```

### Worker batches time out

**Cause:** `--worker-timeout` (default 300 s) is too low for a heavy batch, or a worker is stuck.

**Fix:** raise `--worker-timeout`, or run serially with `--workers 1` to isolate the problem.

---

## Verify

### `verify` output differs between runs

**Cause:** Rust-accelerated methods keep their own thread RNG. The per-image reseeding only makes
the pure-Python methods reproducible.

**Fix:** expected behaviour, not a bug. See **[Augmentation](Augmentation)**.

### `extreme_resize` verification looks wrong

**Cause:** `--min`/`--max` are pixel heights for this method, not `[0, 1]` intensities.

**Fix:** pass pixel values, e.g. `--min 16 --max 800`.

---

## Viewing and merging

### `view --lmdb` finds nothing

**Cause:** `--lmdb` must point at the directory containing `data.mdb` — usually
`data/<split>/lmdb`, not `data/` or `data/<split>`.

**Fix:** `khocr-gen view --lmdb data/train/lmdb --summary`.

### `combine` complains about the output directory

**Cause:** the output directory already exists. `combine` will not clobber it silently.

**Fix:** pass `--overwrite`, or choose a different `--output`.

### `combine` produced no `vocab.json`

**Cause:** `--skip-vocab` was set.

**Fix:** drop the flag. The merged vocabulary covers every character across all merged splits.

---

## Still stuck?

Open an issue at <https://github.com/LazyGreed/khocr-gen/issues> with:

- the exact command you ran,
- your config file, if you used one,
- the output of `khocr-gen --version`,
- for image-quality problems, a sample image plus the `verify_output` PNG for the method involved.
