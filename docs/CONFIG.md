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
fonts: fonts/           # root with khmer/ and english/ subdirs
font-mode: random
copies: 3
mixed-font-prob: 0.0
retry-limit: 10
random-align-when-padded: false

# Variable line height (all optional; default is fixed --height for every image)
line-height-mode: fixed        # fixed | variable | bucketed
min-line-height: 32
max-line-height: 96
line-height-step: 8
line-height-distribution: uniform  # uniform | triangular
# default-line-height: 48          # triangular peak; defaults to range midpoint
font-size-mode: fixed           # fixed | proportional
min-font-scale: 0.65
max-font-scale: 0.9
vertical-padding-mode: fixed    # fixed | random
min-vertical-padding-ratio: 0.04
max-vertical-padding-ratio: 0.18
record-metadata: false          # write metadata.jsonl per split

# Corpus
corpus: corpus/corpus.txt
min-length: 1
max-length: 260
lines: 0               # 0 = all
val-percent: 10.0
# test-percent: 10.0          # if only val-percent is set, test defaults to 0
# split-ratios: [80, 10, 10]  # overrides val-percent/test-percent
# test-file: ""               # separate test corpus; sole source of the test split when set
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
# Each method takes three flat keys: <name>-prob (0-1), <name>-min, <name>-max.
# Exception: extreme_resize's min/max are absolute pixel heights, not [0, 1]
# One augmentation applied per image (isolated, not stacked)

sauvola-prob: 0.2
sauvola-min: 0.1
sauvola-max: 0.9

geo-warp-prob: 0.2
geo-warp-min: 0.1
geo-warp-max: 0.9

vertical-crop-prob: 0.0
vertical-crop-min: 0.1
vertical-crop-max: 0.9

blur-prob: 0.4
blur-min: 0.1
blur-max: 0.9

distortion-prob: 0.3
distortion-min: 0.1
distortion-max: 0.9

albu-noise-prob: 0.4
albu-noise-min: 0.1
albu-noise-max: 0.9

jpeg-compression-prob: 0.4
jpeg-compression-min: 0.1
jpeg-compression-max: 0.9

rotation-prob: 0.0
rotation-min: 0.1
rotation-max: 0.9

salt-pepper-prob: 0.15
salt-pepper-min: 0.1
salt-pepper-max: 0.9

background-texture-prob: 0.35
background-texture-min: 0.1
background-texture-max: 0.9

lowdpi-prob: 0.0
lowdpi-min: 0.1
lowdpi-max: 0.9

oversample-prob: 0.0
oversample-min: 0.1
oversample-max: 0.9

# min/max are absolute pixel heights (not [0, 1]) -- see Augmentation Method Fields below
extreme-resize-prob: 0.0
extreme-resize-min: 8
extreme-resize-max: 1920

low-contrast-caption-prob: 0.0
low-contrast-caption-min: 0.1
low-contrast-caption-max: 0.9

# Online augmentations (default disabled)
perspective-prob: 0.0
perspective-min: 0.1
perspective-max: 0.9

elastic-prob: 0.0
elastic-min: 0.1
elastic-max: 0.9

random-crop-prob: 0.0
random-crop-min: 0.1
random-crop-max: 0.9

online-blur-prob: 0.0
online-blur-min: 0.1
online-blur-max: 0.9

online-noise-prob: 0.0
online-noise-min: 0.1
online-noise-max: 0.9

hsv-prob: 0.0
hsv-min: 0.1
hsv-max: 0.9

reverse-prob: 0.0
reverse-min: 0.0
reverse-max: 1.0

brightness-contrast-prob: 0.0
brightness-contrast-min: 0.1
brightness-contrast-max: 0.9

pixelation-prob: 0.0
pixelation-min: 0.1
pixelation-max: 0.9

gradient-illumination-prob: 0.0
gradient-illumination-min: 0.1
gradient-illumination-max: 0.9

morphological-prob: 0.0
morphological-min: 0.1
morphological-max: 0.9

anisotropic-dilation-prob: 0.0
anisotropic-dilation-min: 0.1
anisotropic-dilation-max: 0.9
```

> **Augmentation keys must be flat.** The YAML loader reads top-level keys only;
> a nested mapping (`sauvola: {prob: 0.2}`) is skipped with a warning and the
> default is kept. See [Augmentation Method Fields](#augmentation-method-fields).

## Text decoration

Per-line decorations applied at render time (before augmentation). Each key is a
probability in `[0, 1]`; default `0` disables that decoration. Decorations can
combine. Bold/italic require a matching variant font and are skipped otherwise.
Random color requires `color-mode: 3`.

- `text-deco-color-prob` — single random text color for the whole line (RGB only)
- `text-deco-underline-prob` — underline the whole line
- `text-deco-subscript-prob` — lower 1–2 random ASCII chars
- `text-deco-superscript-prob` — raise 1–2 random ASCII chars
- `text-deco-italic-prob` — italic via a real italic/oblique variant font
- `text-deco-bold-prob` — bold via a real bold variant font

## Text effects

Canva-style per-line effects applied at render time (before augmentation), on top of
the same clean canvas as text decorations. Unlike decorations, effects are
**mutually exclusive** with each other: each probability is rolled independently in
a fixed order and the first hit wins, so at most one effect applies per line. They
combine freely with `text-deco-*`. Default `0` disables an effect. Every effect keeps
the underlying glyph shapes intact — the rendered text is still the ground-truth label.

- `text-effect-background-prob` — highlight box behind the line
- `text-effect-echo-prob` — faint offset duplicate (echo/ghost) copies
- `text-effect-glitch-prob` — small offset colour-split copies
- `text-effect-glow-prob` — soft blurred halo behind the text
- `text-effect-hollow-prob` — outline-only glyphs, background-colour interior
- `text-effect-huge-prob` — oversized text relative to the canvas
- `text-effect-neon-prob` — bright saturated fill with a neon-sign glow
- `text-effect-outline-prob` — solid fill with a contrasting stroke
- `text-effect-pixel-prob` — blocky/pixelated glyph edges
- `text-effect-shadow-prob` — offset blurred drop shadow
- `text-effect-tiny-prob` — undersized text relative to the canvas
- `text-effect-transparent-prob` — partially see-through fill

## Augmentation Method Fields

Each augmentation method is configured with three **flat top-level keys** named
`<method>-prob`, `<method>-min` and `<method>-max`, where `<method>` is the method
name with underscores written as hyphens (`geo_warp` → `geo-warp-prob`):

| Key | Type | Range | Description |
|-------|------|-------|-------------|
| `<method>-prob` | float | [0, 1] | Probability weight for selecting this method |
| `<method>-min` | float | [0, 1] | Minimum intensity (normalized; clamped to ≥ 0) |
| `<method>-max` | float | [0, 1] | Maximum intensity (clamped to ≤ 1; ≥ min) |

Nested mappings are **not** read — `sauvola: {prob: 0.2}` is dropped with
`Config key 'sauvola' is a nested mapping; only flat keys are supported, skipping.` on stderr and
the default is kept. (A key matching no flag warns separately with
`[config] WARNING: Unrecognized keys …` — that one usually means a typo.)

**Exception:** `extreme_resize`'s `min`/`max` are absolute target heights in *pixels*
(default `8`/`1920`, clamped to `min ≥ 1` and `max ≥ min`), not normalized `[0, 1]`
values — see [AUGMENTATION.md](AUGMENTATION.md#extreme_resize-extreme-source-resolution-simulation).

**How intensities work:** The actual intensity for a given image is sampled uniformly from `[min, max]`.
The method maps this normalized value to physical units (pixel displacements, kernel sizes, noise sigmas, etc.).

**How selection works:** From all methods with `prob > 0`, one is chosen with probability proportional to its `prob` value.
A method with `prob: 0.4` is selected twice as often as one with `prob: 0.2`.

## Override Examples

### Aggressive blur, no other augmentation

```yaml
blur-prob: 1.0
blur-min: 0.3
blur-max: 0.9

# Disable all others by setting prob to 0
sauvola-prob: 0.0
geo-warp-prob: 0.0
# ... etc
```

## `combine` Config

`khocr-gen combine` accepts the same `--config FILE` flag and auto-detects `configs/combine.yml`.
Its keys mirror the `combine` CLI flags:

```yaml
# configs/combine.yml
output: data_combined
overwrite: false
keep-raw: false
jpeg-quality: 90
map-size-gb: 256
vocab: null           # defaults to OUTPUT/vocab.json
skip-vocab: false
verbose: true
```

The dataset directories to merge are always given as positional arguments on the command line, not in the config file:

```bash
khocr-gen combine --config configs/combine.yml data_run1/ data_run2/
```
