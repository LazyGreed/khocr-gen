# CLI Reference

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

# Enable specific augmentation
khocr-gen generate --blur-prob 0.5 --blur-min 0.1 --blur-max 0.9

# Pack to LMDB after generation (using --storage)
khocr-gen generate --corpus corpus/corpus.txt --storage lmdb

# Pack to LMDB and keep raw files
khocr-gen generate --corpus corpus/corpus.txt --storage both
```

### Options

#### Rendering

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fonts DIR` | str | `fonts/` | Root fonts directory: `<dir>/khmer/` and `<dir>/english/` |
| `--height PX` | int | 48 | Image height in pixels |
| `--width PX` | int | *auto* | Fixed image width; omit for variable width |
| `--color-mode {1,3}` | int | 1 | Output colour channels: 1=grayscale, 3=RGB |
| `--random-align-when-padded` | flag | false | Random left/center/right alignment with fixed `--width` |
| `--font-mode` | str | `random` | `random` = N augmented copies; `all` = one image per font per line |
| `--copies N` | int | 3 | Augmented copies per text line (font-mode=random) |
| `--mixed-font-prob F` | float | 0.0 | Probability of per-span font for mixed Khmer/English |
| `--retry-limit N` | int | 10 | Font selection retries when font lacks glyphs |

#### Variable line height

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--line-height-mode {fixed,variable,bucketed}` | str | `fixed` | `fixed` = every image uses `--height` (backward compatible). `variable` = sample a height per image from the min/max range. `bucketed` = sample from the fixed set of heights spaced by `--line-height-step`. |
| `--min-line-height PX` | int | 32 | Minimum sampled line height |
| `--max-line-height PX` | int | 96 | Maximum sampled line height |
| `--line-height-step PX` | int | 8 | Align sampled/bucketed heights to a multiple of this many pixels |
| `--line-height-distribution {uniform,triangular}` | str | `uniform` | Shape of the `variable`-mode distribution; `triangular` clusters around `--default-line-height` |
| `--default-line-height PX` | int | *(range midpoint)* | Peak height for the triangular distribution |
| `--font-size-mode {fixed,proportional}` | str | `fixed` | `fixed` = choose from the preloaded font sizes. `proportional` = size the font relative to the sampled canvas height |
| `--min-font-scale F` | float | 0.65 | Minimum glyph height as a fraction of canvas height (font-size-mode=proportional) |
| `--max-font-scale F` | float | 0.9 | Maximum glyph height as a fraction of canvas height (font-size-mode=proportional) |
| `--vertical-padding-mode {fixed,random}` | str | `fixed` | `random` samples top/bottom padding as a ratio of canvas height instead of a constant pixel amount |
| `--min-vertical-padding-ratio F` | float | 0.04 | Minimum vertical padding as a fraction of canvas height |
| `--max-vertical-padding-ratio F` | float | 0.18 | Maximum vertical padding as a fraction of canvas height |
| `--record-metadata` | flag | false | Write a `metadata.jsonl` sidecar (image/text/width/height/font/font_size) per split |

Every generated image is produced by rendering onto a clean canvas at its
natural size and then uniformly *resizing* (never cropping) to the sampled
target height, so glyphs — including Khmer diacritics — are never clipped
regardless of which height gets sampled. `labels.txt` is unaffected: variable
height is encoded entirely in the image dimensions.

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

#### Corpus

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--corpus FILE` | str | `corpus/corpus.txt` | Path to plain text corpus |
| `--min-length N` | int | 1 | Minimum character length |
| `--max-length N` | int | 260 | Maximum character length |
| `--lines N` | int | 0 | Max lines to use (0 = all) |
| `--seed N` | int | 42 | Random seed for deterministic train/val/test splitting |
| `--val-percent PCT` | float | *(10.0 if unset)* | Validation split percentage [0, 100). If only this is set, test=0. |
| `--test-percent PCT` | float | *(10.0 if unset)* | Test split percentage [0, 100). If only this is set, val=0. |
| `--split-ratios TRAIN VAL TEST` | float×3 | *none* | Explicit ratios (e.g. `80 10 10`), normalised to sum to 1.0. Overrides `--val-percent`/`--test-percent`. Use `100 0 0` to disable splitting. |
| `--test-file FILE` | str | *none* | Separate test corpus file. When set, it is the sole source of the test split — the ratio-based split does not also carve one out. |
| `--count-only` | flag | - | Print filter stats and estimated image count, then exit |
| `--image-dir DIR` | str | *none* | Path to existing images (bypass text rendering) |

#### Output

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output DIR` | str | `data/` | Output directory |
| `--append` | flag | - | Append new samples if output exists |
| `--overwrite` | flag | - | Delete and recreate if output exists |
| `--vocab FILE` | str | *auto* | Path for vocab.json |
| `--skip-vocab` | flag | false | Do not build vocab.json |
| `--output-format` | str | `jpg` | Output image format: `png`, `jpg`, or `tiff` |
| `--jpeg-quality N` | int | 90 | JPEG quality for jpg output (0–100) |
| `--storage` | str | `raw` | Storage mode: `raw` (image files), `lmdb` (pack + delete), `both` (save + pack + keep) |

#### LMDB Packing

The preferred way to control storage is `--storage {raw,lmdb,both}` (see Output section above).
The legacy flags below are still supported:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--pack-lmdb` | flag | - | *(legacy)* Pack generated dataset into LMDB |
| `--keep-raw` | flag | - | *(legacy)* Keep raw image files after LMDB packing |
| `--lmdb-jpeg-quality N` | int | 90 | JPEG quality for LMDB-stored images |
| `--lmdb-map-size-gb N` | int | 256 | LMDB map size in GiB |
| `--lmdb-verbose` | flag | - | Print skipped/corrupt image warnings during LMDB packing |

#### Workers

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--workers N` | int | 0 | Worker processes; 0 = auto, 1 = serial |
| `--worker-timeout SEC` | int | 300 | Seconds before a worker batch times out |

#### DPI Simulation

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dpi-mode` | str | `native` | `native`, `oversample`, or `lowdpi` |

#### Text Normalization

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

#### Augmentation Methods

Each method has three flags: `--<name>-prob`, `--<name>-min`, `--<name>-max`.

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

---

## `khocr-gen verify`

Render every augmentation method at min and max intensity on clean canvases.

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
| `--repeats N` | int | 2 | Augmentation repeats per text, for variety |
| `--method NAME [NAME ...]` | str | *all* | Restrict verification to specific method(s) |
| `--show` | flag | - | Display each comparison interactively |

### Examples

```bash
# Verify every method using built-in sample texts
khocr-gen verify --fonts fonts/ --output-dir verify_output/

# Draw sample texts from a corpus, restrict to two methods
khocr-gen verify --fonts fonts/ --corpus corpus/corpus.txt --method blur rotation

# More samples per method, shown interactively
khocr-gen verify --fonts fonts/ --count 10 --show
```

Output: one PNG per augmentation method, showing min intensity (left) vs max intensity (right) side-by-side on a clean canvas.

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

Each input dataset may have `train/` and/or `val/` subdirectories.
Each split can be raw (`labels.txt` + `images/`) or LMDB (`lmdb/`).
The merged output is always LMDB.

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output DIR`, `-o` | str | `data_combined` | Output directory |
| `--overwrite` | flag | - | Overwrite existing output directory without prompting |
| `--keep-raw` | flag | - | Keep raw images after LMDB packing |
| `--jpeg-quality N` | int | 90 | JPEG quality |
| `--map-size-gb N` | int | 256 | LMDB map size in GiB |
| `--verbose` | flag | - | Print merge and LMDB packing progress |

### Examples

```bash
# Combine 3 datasets
khocr-gen combine data_run1/ data_run2/ data_run3/ --output data_merged/

# Combine with YAML config
khocr-gen combine --config configs/combine.yml data_run1/ data_run2/
```

---

## YAML Configuration

All `generate` and `combine` commands support `--config FILE` for loading defaults from YAML.
CLI flags override YAML values.

```bash
# Auto-detects configs/generate.yml if present
khocr-gen generate

# Explicit config path
khocr-gen generate --config my_config.yml

# Override specific values
khocr-gen generate --config my_config.yml --copies 10 --height 64
```

See [CONFIG.md](CONFIG.md) for detailed config file documentation.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `KHOCR_GEN_MP_START_METHOD` | Override multiprocessing start method (`fork` or `spawn`) |
