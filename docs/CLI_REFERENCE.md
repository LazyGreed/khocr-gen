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

#### Corpus

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--corpus FILE` | str | `corpus/corpus.txt` | Path to plain text corpus |
| `--min-length N` | int | 1 | Minimum character length |
| `--max-length N` | int | 260 | Maximum character length |
| `--lines N` | int | 0 | Max lines to use (0 = all) |
| `--seed N` | int | 42 | Random seed for train/val split |
| `--val-percent PCT` | float | 10.0 | Validation split percentage [0, 100) |
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
| `--output DIR` | str | `verify_output/` | Output directory for comparison images |
| `--height PX` | int | 48 | Image height |
| `--width PX` | int | *auto* | Image width |
| `--text STR` | str | `Hello សួស្តី` | Text to render on verification images |

### Example

```bash
khocr-gen verify --fonts fonts/ --output verify_output/ --text "សួស្តី"
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
| `--lmdb DIR` | str | `data/train/lmdb/` | Path to LMDB database |
| `--summary` | flag | - | Print summary (count, key stats) |
| `--output-dir DIR` | str | *none* | Extract all images to directory |
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
| `--output DIR` | str | `data/combined/` | Output directory |
| `--keep-raw` | flag | - | Keep raw images after LMDB packing |
| `--jpeg-quality N` | int | 90 | JPEG quality |
| `--map-size-gb N` | int | 256 | LMDB map size in GiB |

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
