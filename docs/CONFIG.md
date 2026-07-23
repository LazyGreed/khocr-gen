# Configuration Guide

`khocr-gen` supports YAML configuration files for reproducible generation recipes.
Config files provide defaults that can be overridden by CLI flags.

## Loading

```bash
# Auto-detects configs/generate.yml if present
khocr-gen generate

# Explicit path
khocr-gen generate --config my_config.yml

# Combine: auto-detects configs/combine.yml
khocr-gen combine data1/ data2/

# Explicit path
khocr-gen combine --config my_combine.yml data1/ data2/
```

## Priority

Final values are resolved in this order (highest priority wins):

1. **Argparse built-in defaults** (lowest)
2. **YAML config file values**
3. **Explicit CLI flags** (highest)

## Format

Top-level YAML mapping with flat keys. Both `snake_case` and `kebab-case`
keys are accepted (normalized to `snake_case`).

```yaml
# configs/generate.yml

# Rendering
height: 48
# width: null          # omit for variable width
color-mode: 1          # 1 = grayscale, 3 = RGB
fonts-dir: fonts/
font-mode: random
copies: 3
mixed-font-prob: 0.0
retry-limit: 10
random-align-when-padded: false

# Corpus
corpus: corpus/corpus.txt
min-length: 1
max-length: 260
lines: 0               # 0 = all
val-percent: 10.0
seed: 42

# Output
output: data/
append: false
overwrite: false
vocab: ""              # auto-derived
skip-vocab: false
output-format: jpg     # png | jpg | tiff
jpeg-quality: 90       # JPEG quality for jpg output
storage: raw           # raw | lmdb | both (replaces --pack-lmdb/--keep-raw)

# LMDB (legacy flags, prefer --storage)
pack-lmdb: false
keep-raw: false
lmdb-jpeg-quality: 90
lmdb-map-size-gb: 256

# Workers
workers: 0             # 0 = auto
worker-timeout: 300

# DPI
dpi-mode: native

# Text normalization
norm_unicode_norm: ""  # skipped by default; khmernormalizer normalizes internally
norm_emoji_replacement: ""
norm_url_replacement: ""
norm_no_remove_zwsp: false
norm_no_fix_encoding: false
norm_no_uncurl_quotes: false
norm_no_fix_line_breaks: false
norm_passthrough: false

# Augmentation methods
# Each method: prob (0-1), min intensity (0-1), max intensity (0-1)
# One augmentation applied per image (isolated, not stacked)

sauvola:
  prob: 0.2
  min: 0.1
  max: 0.9

geo_warp:
  prob: 0.2
  min: 0.1
  max: 0.9

vertical_crop:
  prob: 0.0
  min: 0.1
  max: 0.9

blur:
  prob: 0.4
  min: 0.1
  max: 0.9

distortion:
  prob: 0.3
  min: 0.1
  max: 0.9

albu_noise:
  prob: 0.4
  min: 0.1
  max: 0.9

jpeg_compression:
  prob: 0.4
  min: 0.1
  max: 0.9

rotation:
  prob: 0.0
  min: 0.1
  max: 0.9

salt_pepper:
  prob: 0.15
  min: 0.1
  max: 0.9

background_texture:
  prob: 0.35
  min: 0.1
  max: 0.9

lowdpi:
  prob: 0.0
  min: 0.1
  max: 0.9

oversample:
  prob: 0.0
  min: 0.1
  max: 0.9

# Online augmentations (default disabled)
perspective:
  prob: 0.0
  min: 0.1
  max: 0.9

elastic:
  prob: 0.0
  min: 0.1
  max: 0.9

random_crop:
  prob: 0.0
  min: 0.1
  max: 0.9

online_blur:
  prob: 0.0
  min: 0.1
  max: 0.9

online_noise:
  prob: 0.0
  min: 0.1
  max: 0.9

hsv:
  prob: 0.0
  min: 0.1
  max: 0.9

reverse:
  prob: 0.0
  min: 0.0
  max: 1.0

brightness_contrast:
  prob: 0.0
  min: 0.1
  max: 0.9

pixelation:
  prob: 0.0
  min: 0.1
  max: 0.9

gradient_illumination:
  prob: 0.0
  min: 0.1
  max: 0.9

morphological:
  prob: 0.0
  min: 0.1
  max: 0.9

anisotropic_dilation:
  prob: 0.0
  min: 0.1
  max: 0.9
```

## Augmentation Method Fields

Each augmentation method is configured with three values:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `prob` | float | [0, 1] | Probability weight for selecting this method |
| `min` | float | [0, 1] | Minimum intensity (normalized; clamped to ≥ 0) |
| `max` | float | [0, 1] | Maximum intensity (clamped to ≤ 1; ≥ min) |

**How intensities work:** The actual intensity for a given image is sampled uniformly from `[min, max]`.
The method maps this normalized value to physical units (pixel displacements, kernel sizes, noise sigmas, etc.).

**How selection works:** From all methods with `prob > 0`, one is chosen with probability proportional to its `prob` value.
A method with `prob: 0.4` is selected twice as often as one with `prob: 0.2`.

## Override Examples

### Aggressive blur, no other augmentation

```yaml
blur:
  prob: 1.0
  min: 0.3
  max: 0.9

# Disable all others by setting prob: 0
sauvola:
  prob: 0.0
geo_warp:
  prob: 0.0
# ... etc
```

### Production recipe via CLI overrides

```bash
khocr-gen generate --config configs/production.yml --copies 5 --height 64 --workers 8 --pack-lmdb
```
