# CLI Reference

```text
khocr-gen [-h] [-v] COMMAND ...
```

| Command | Purpose |
|---------|---------|
| [`generate`](#khocr-gen-generate) | Generate synthetic training images from a text corpus |
| [`verify`](#khocr-gen-verify) | Visual verification of augmentation methods at fixed MIN/MAX intensity |
| [`view`](#khocr-gen-view) | Preview and extract images from an LMDB database |
| [`combine`](#khocr-gen-combine) | Merge multiple generated datasets into one merged LMDB dataset |

Global flags: `-h, --help`, `-v, --version`.

Every `generate` and `combine` invocation also accepts `-c, --config FILE` (YAML) — see
**[Configuration](Configuration)** for precedence rules.

---

## `khocr-gen generate`

Generate a synthetic OCR dataset from a text corpus.

```bash
khocr-gen generate [OPTIONS]
```

### Quick examples

```bash
# Minimal generation
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --output data

# With YAML config
khocr-gen generate --config configs/generate.yml

# Override specific values from YAML
khocr-gen generate --config configs/generate.yml --copies 5 --height 64

# Count-only mode (no generation)
khocr-gen generate --corpus corpus/corpus.txt --count-only

# Enable specific augmentations
khocr-gen generate --blur-prob 0.5 --blur-min 0.1 --blur-max 0.9

# Pack to LMDB after generation
khocr-gen generate --corpus corpus/corpus.txt --storage lmdb

# Pack to LMDB and keep raw files
khocr-gen generate --corpus corpus/corpus.txt --storage both
```

### Rendering

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fonts DIR` | str | `fonts/` | Root fonts directory: `<dir>/khmer/` and `<dir>/english/` |
| `--height PX` | int | 48 | Image height in pixels (used when `--line-height-mode fixed`) |
| `--width PX` | int | *auto* | Fixed image width; omit for variable width |
| `--color-mode {1,3}` | int | 1 | Output colour channels: 1 = grayscale, 3 = RGB |
| `--random-align-when-padded` | flag | false | Random left/center/right alignment with fixed `--width` |
| `--font-mode {random,all}` | str | `random` | `random` = N augmented copies; `all` = one image per font per line |
| `--copies N` | int | 3 | Augmented copies per text line (`font-mode=random`) |
| `--mixed-font-prob F` | float | 0.0 | Probability of per-span font selection for mixed Khmer/English |
| `--retry-limit N` | int | 10 | Font selection retries when a font lacks glyphs |

### Text decorations

Per-line decorations sampled at render time on the clean canvas, before augmentation. They can
combine freely. Bold/italic use real variant fonts and are skipped when no matching variant
exists; `--text-deco-color-prob` requires `--color-mode 3`.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--text-deco-color-prob F` | float | 0 | Probability of a single random text color for the whole line (RGB only) |
| `--text-deco-underline-prob F` | float | 0 | Probability of underlining the whole line |
| `--text-deco-subscript-prob F` | float | 0 | Probability of lowering 1–2 random ASCII chars |
| `--text-deco-superscript-prob F` | float | 0 | Probability of raising 1–2 random ASCII chars |
| `--text-deco-italic-prob F` | float | 0 | Probability of italic via a real italic/oblique variant font |
| `--text-deco-bold-prob F` | float | 0 | Probability of bold via a real bold variant font |

### Text effects

Canva-style per-line effects, also sampled on the clean canvas before augmentation. They are
**mutually exclusive with each other** — each probability is rolled independently in a fixed
order and the first hit wins — but combine freely with the `--text-deco-*` decorations above.

| Flag | Default | Description |
|------|---------|-------------|
| `--text-effect-background-prob F` | 0 | Highlight box behind the line |
| `--text-effect-echo-prob F` | 0 | Faint offset duplicate (echo/ghost) copies |
| `--text-effect-glitch-prob F` | 0 | Small offset colour-split glitch look |
| `--text-effect-glow-prob F` | 0 | Soft blurred glow halo behind the text |
| `--text-effect-hollow-prob F` | 0 | Outline-only glyphs with a background-colour interior |
| `--text-effect-huge-prob F` | 0 | Oversized text relative to the canvas |
| `--text-effect-neon-prob F` | 0 | Bright neon-sign fill and glow |
| `--text-effect-outline-prob F` | 0 | Solid fill with a contrasting stroke outline |
| `--text-effect-pixel-prob F` | 0 | Blocky/pixelated glyph edges |
| `--text-effect-shadow-prob F` | 0 | Offset blurred drop shadow |
| `--text-effect-tiny-prob F` | 0 | Undersized text relative to the canvas |
| `--text-effect-transparent-prob F` | 0 | Partially see-through fill |

Full details and examples: **[Text Decorations and Effects](Text-Decorations-and-Effects)**.

### Variable line height

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--line-height-mode {fixed,variable,bucketed}` | str | `fixed` | `fixed` = every image uses `--height`. `variable` = sample a height per image from the min/max range. `bucketed` = sample from the fixed set of heights spaced by `--line-height-step`. |
| `--min-line-height PX` | int | 32 | Minimum sampled line height |
| `--max-line-height PX` | int | 96 | Maximum sampled line height |
| `--line-height-step PX` | int | 8 | Align sampled/bucketed heights to a multiple of this many pixels |
| `--line-height-distribution {uniform,triangular}` | str | `uniform` | Shape of the `variable`-mode distribution; `triangular` clusters around `--default-line-height` |
| `--default-line-height PX` | int | *(range midpoint)* | Peak height for the triangular distribution |
| `--font-size-mode {fixed,proportional}` | str | `fixed` | `fixed` = choose from preloaded font sizes. `proportional` = size the font relative to the sampled canvas height. |
| `--min-font-scale F` | float | 0.65 | Minimum glyph height as a fraction of canvas height (`font-size-mode=proportional`) |
| `--max-font-scale F` | float | 0.9 | Maximum glyph height as a fraction of canvas height (`font-size-mode=proportional`) |
| `--vertical-padding-mode {fixed,random}` | str | `fixed` | `random` samples top/bottom padding as a ratio of canvas height instead of a constant pixel amount |
| `--min-vertical-padding-ratio F` | float | 0.04 | Minimum vertical padding as a fraction of canvas height |
| `--max-vertical-padding-ratio F` | float | 0.18 | Maximum vertical padding as a fraction of canvas height |
| `--record-metadata` | flag | false | Write a `metadata.jsonl` sidecar (`image`/`text`/`width`/`height`/`font`/`font_size`) per split |

Every image is rendered on a clean canvas at its natural size and then uniformly **resized**
(never cropped) to the sampled target height, so glyphs — including Khmer diacritics — are never
clipped. `labels.txt` is unaffected: variable height is encoded entirely in the image dimensions.

```bash
# Sample heights in [32, 96], aligned to 8px steps
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 --line-height-step 8

# Also vary font scale and padding, and record per-sample metadata
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 \
  --font-size-mode proportional --min-font-scale 0.65 --max-font-scale 0.9 \
  --vertical-padding-mode random --min-vertical-padding-ratio 0.04 --max-vertical-padding-ratio 0.18 \
  --record-metadata
```

See **[Variable Line Height](Variable-Line-Height)**.

### Corpus

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--corpus FILE` | str | `corpus/corpus.txt` | Path to plain text corpus |
| `--min-length N` | int | 1 | Minimum character length |
| `--max-length N` | int | 260 | Maximum character length |
| `--lines N` | int | 0 | Max lines to use (0 = all) |
| `--seed N` | int | 42 | Random seed for deterministic train/val/test splitting |
| `--val-percent PCT` | float | *(10.0 if unset)* | Validation split percentage [0, 100). If only this is set, test = 0. |
| `--test-percent PCT` | float | *(10.0 if unset)* | Test split percentage [0, 100). If only this is set, val = 0. |
| `--split-ratios TRAIN VAL TEST` | float×3 | *none* | Explicit ratios (e.g. `80 10 10`), normalised to sum to 1.0. Overrides `--val-percent`/`--test-percent`. Use `100 0 0` to disable splitting. |
| `--test-file FILE` | str | *none* | Separate test corpus file. When set it is the sole source of the test split — the ratio-based split does not also carve one out. |
| `--count-only` | flag | - | Print filter stats and estimated image count, then exit |
| `--image-dir DIR` | str | *none* | Path to an existing images directory (bypass text rendering; the corpus must be a `labels.txt` file) |
| `--oversample-rare-chars` | flag | false | Render extra copies of training lines containing rare characters. Does not affect val/test, which stay at 1 copy per line. |
| `--rare-char-percentile PCT` | float | 5.0 | Least-frequent PCT% of distinct characters in the corpus are considered rare |
| `--rare-char-multiplier F` | float | 3.0 | Copies multiplier applied to training lines containing a rare character |

See **[Corpus and Normalization](Corpus-and-Normalization)**.

### Output

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output DIR` | str | `data/` | Output directory |
| `--append` | flag | - | Append new samples if output exists |
| `--overwrite` | flag | - | Delete and recreate if output exists |
| `--vocab FILE` | str | *auto* | Path for `vocab.json` |
| `--skip-vocab` | flag | false | Do not build `vocab.json` |
| `--output-format {png,jpg,tiff}` | str | `jpg` | Output image format |
| `--jpeg-quality N` | int | 90 | JPEG quality for `jpg` output (0–100) |
| `--storage {raw,lmdb,both}` | str | `raw` | `raw` = image files, `lmdb` = pack and delete raw images, `both` = save and pack and keep |

`--append` and `--overwrite` are mutually exclusive.

### LMDB packing

The preferred way to control storage is `--storage {raw,lmdb,both}`. These legacy flags are still
supported:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--pack-lmdb` | flag | - | *(legacy)* Pack the generated dataset into LMDB |
| `--keep-raw` | flag | - | *(legacy)* Keep raw image files after LMDB packing |
| `--lmdb-jpeg-quality N` | int | 90 | JPEG quality for LMDB-stored images |
| `--lmdb-map-size-gb N` | int | 256 | LMDB map size in GiB |
| `--lmdb-verbose` | flag | - | Print skipped/corrupt image warnings during LMDB packing |

### Workers

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--workers N` | int | 0 | Worker processes; 0 = auto, 1 = serial |
| `--worker-timeout SEC` | int | 300 | Seconds before a worker batch times out |

### DPI simulation

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dpi-mode {native,oversample,lowdpi}` | str | `native` | DPI rendering strategy |

### Rendering style

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--bg-color-mode {default,paper_tones,colored,dark_mode,gradient,random}` | str | `random` | Background colour palette. `default`: off-white/light-gray. `paper_tones`: warm cream, sepia, recycled, blueprint. `colored`: soft pastels. `dark_mode`: dark background (invert). `gradient`: gradient backgrounds. `random`: pick one per image. |

### Text normalization

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--norm-unicode-norm` | str | `NFKC` | Unicode normalization form |
| `--norm-emoji-replacement STR` | str | `""` | Replacement string for emoji |
| `--norm-url-replacement STR` | str | `""` | Replacement string for URLs |
| `--norm-no-remove-zwsp` | flag | - | Keep zero-width spaces |
| `--norm-no-fix-encoding` | flag | - | Disable ftfy encoding fixes |
| `--norm-no-uncurl-quotes` | flag | - | Disable quote uncurling |
| `--norm-no-fix-line-breaks` | flag | - | Disable line break normalization |
| `--norm-passthrough` | flag | - | Skip all normalization |

### Augmentation methods

Each method has three flags: `--<name>-prob`, `--<name>-min`, `--<name>-max`. `prob` is the
selection weight; the applied intensity is sampled uniformly from `[min, max]`.

| Method | Prob | Min | Max | Description |
|--------|------|-----|-----|-------------|
| `sauvola` | 0.2 | 0.1 | 0.9 | Sauvola local-threshold degradation |
| `geo-warp` | 0.2 | 0.1 | 0.9 | 4-point perspective warp |
| `vertical-crop` | 0.0 | 0.1 | 0.9 | Random vertical crop |
| `blur` | 0.4 | 0.1 | 0.9 | Motion/Median/Gaussian blur |
| `distortion` | 0.3 | 0.1 | 0.9 | Optical/Grid/Elastic distortion |
| `albu-noise` | 0.4 | 0.1 | 0.9 | Gaussian/Multiplicative noise |
| `jpeg-compression` | 0.4 | 0.1 | 0.9 | JPEG compression artifacts |
| `rotation` | 0.0 | 0.1 | 0.9 | Random rotation |
| `salt-pepper` | 0.15 | 0.1 | 0.9 | Salt-and-pepper impulse noise |
| `background-texture` | 0.35 | 0.1 | 0.9 | Procedural paper texture |
| `lowdpi` | 0.0 | 0.1 | 0.9 | Low-DPI rendering simulation |
| `oversample` | 0.0 | 0.1 | 0.9 | Oversample rendering |
| `extreme-resize` | 0.0 | 8 | 1920 | Extreme source-resolution simulation (**`min`/`max` are pixel heights, not `[0, 1]`**) |
| `low-contrast-caption` | 0.0 | 0.1 | 0.9 | Low-contrast small caption text |
| `perspective` | 0.0 | 0.1 | 0.9 | Perspective warp |
| `elastic` | 0.0 | 0.1 | 0.9 | Elastic distortion |
| `random-crop` | 0.0 | 0.1 | 0.9 | Random height crop |
| `online-blur` | 0.0 | 0.1 | 0.9 | Gaussian/Motion blur |
| `online-noise` | 0.0 | 0.1 | 0.9 | Additive Gaussian noise |
| `hsv` | 0.0 | 0.1 | 0.9 | HSV color jitter |
| `reverse` | 0.0 | 0.0 | 1.0 | Color reversal |
| `brightness-contrast` | 0.0 | 0.1 | 0.9 | Brightness/contrast jitter |
| `pixelation` | 0.0 | 0.1 | 0.9 | Pixelation (downscale-upscale) |
| `gradient-illumination` | 0.0 | 0.1 | 0.9 | Gradient illumination overlay |
| `morphological` | 0.0 | 0.1 | 0.9 | Morphological erode/dilate |
| `anisotropic-dilation` | 0.0 | 0.1 | 0.9 | Anisotropic dilation |

Full catalogue with the intensity → physical-unit mapping: **[Augmentation](Augmentation)**.

---

## `khocr-gen verify`

Render every augmentation method at two **fixed** intensities on clean canvases. The two
intensities default to `0.0` and `1.0` and are settable with `--min` / `--max`; each column uses
exactly that intensity rather than a value sampled at random from the range.

Each individual `text_deco_*` (bold, italic, underline, color, subscript, superscript) and
`text_effect_*` (background, echo, glitch, glow, hollow, huge, neon, outline, pixel, shadow, tiny,
transparent) probability is verifiable the same way, one at a time — pass e.g.
`--method text_deco_bold` or `--method text_effect_glow` — pinning just that probability to the
fixed intensity (all others at 0) and re-rendering, rather than applying an augmentation function
to a clean canvas.

```bash
khocr-gen verify [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fonts DIR` | str | `fonts/` | Root fonts directory |
| `--corpus FILE` | str | *none* | Optional corpus file to draw sample texts from (falls back to built-in samples) |
| `--output-dir DIR`, `--output` | str | `verify_output/` | Directory for comparison PNG images |
| `--height PX` | int | 48 | Image height in pixels |
| `--width PX` | int | *auto* | Fixed image width; omit for variable width |
| `--count N` | int | 6 | Number of sample texts per method |
| `--min F` | float | 0.0 | Fixed intensity in `[0, 1]` for the MIN column. For `--method extreme_resize` this is a pixel height instead (default: 8). |
| `--max F` | float | 1.0 | Fixed intensity in `[0, 1]` for the MAX column. For `--method extreme_resize` this is a pixel height instead (default: 1920). |
| `--repeats N` | int | 2 | Augmentation repeats per text, for variety |
| `--method NAME [NAME ...]` | str | *all* | Restrict verification to specific method(s), including `text_deco_*`/`text_effect_*` names |
| `--show` | flag | - | Display each comparison interactively |

### Examples

```bash
# Verify every method using built-in sample texts
khocr-gen verify --fonts fonts/ --output-dir verify_output/

# Draw sample texts from a corpus, restrict to two methods
khocr-gen verify --fonts fonts/ --corpus corpus/corpus.txt --method blur rotation

# More samples per method, shown interactively
khocr-gen verify --fonts fonts/ --count 10 --show

# Compare two intensities from the middle of the range
khocr-gen verify --fonts fonts/ --min 0.3 --max 0.6

# extreme_resize: --min/--max are pixel heights here, not [0, 1] fractions
khocr-gen verify --fonts fonts/ --method extreme_resize --min 16 --max 800
```

Output: one PNG per augmentation method, showing the MIN intensity (left) vs the MAX intensity
(right) side by side on a clean canvas. The RNG is reseeded per image so pure-Python methods
reproduce across runs (Rust-accelerated methods keep their own thread RNG and still vary).

---

## `khocr-gen view`

Preview and extract images from LMDB databases.

```bash
khocr-gen view [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--lmdb DIR` | str | *required* | Path to LMDB directory (containing `data.mdb`) |
| `--summary` | flag | - | Print summary (count, key stats) |
| `--count N` | int | 0 | Number of samples to read (0 = all, capped by `--max-count`) |
| `--max-count N` | int | 100 | Default max samples read when `--count` is not given |
| `--output-dir DIR`, `-o` | str | *none* | Extract all read samples to a directory |
| `--labels-only` | flag | - | Print labels only, no images |

### Examples

```bash
# View summary
khocr-gen view --lmdb data/train/lmdb/ --summary

# Extract all images
khocr-gen view --lmdb data/train/lmdb/ --output-dir extracted/

# Print labels only
khocr-gen view --lmdb data/train/lmdb/ --labels-only
```

---

## `khocr-gen combine`

Merge multiple datasets into one (n-way merge).

```bash
khocr-gen combine DATASET [DATASET ...] [OPTIONS]
```

Each input dataset may have `train/` and/or `val/` subdirectories. Each split can be raw
(`labels.txt` + `images/`) or LMDB (`lmdb/`). The merged output is always LMDB. A merged
`vocab.json`, covering every character across all merged splits, is written to the output
directory too.

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-c, --config FILE` | str | *none* | YAML config file (`configs/combine.yml` auto-detected) |
| `--output DIR`, `-o` | str | `data_combined` | Output directory |
| `--overwrite` | flag | - | Overwrite existing output directory without prompting |
| `--keep-raw` | flag | - | Keep raw images after LMDB packing |
| `--jpeg-quality N` | int | 90 | JPEG quality |
| `--map-size-gb N` | int | 256 | LMDB map size in GiB |
| `--vocab FILE` | str | `OUTPUT/vocab.json` | Path to write merged `vocab.json` |
| `--skip-vocab` | flag | - | Do not build a merged `vocab.json` |
| `--verbose` | flag | - | Print merge and LMDB packing progress |

### Examples

```bash
# Combine 3 datasets
khocr-gen combine data_run1/ data_run2/ data_run3/ --output data_merged/

# Combine with YAML config
khocr-gen combine --config configs/combine.yml data_run1/ data_run2/
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `KHOCR_GEN_MP_START_METHOD` | Override the multiprocessing start method (`fork` or `spawn`) |
