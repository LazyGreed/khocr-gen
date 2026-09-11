# Configuration

`khocr-gen` supports YAML configuration files for reproducible generation recipes. A config file
provides defaults that CLI flags can override.

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

The autodetect path is `configs/<command>.yml` relative to the current working directory. An
explicit `-c/--config` always wins over autodetection.

## Priority

Final values are resolved in this order (highest wins):

1. **Argparse built-in defaults** (lowest)
2. **YAML config file values**
3. **Explicit CLI flags** (highest)

```bash
# YAML says copies: 3, CLI overrides to 10
khocr-gen generate --config configs/generate.yml --copies 10
```

## Format

A top-level YAML mapping with **flat keys**. Both `snake_case` and `kebab-case` keys are accepted
and normalized to the argument names, so `text-deco-bold-prob` and `text_deco_bold_prob` are
equivalent (`--sauvola-prob` → `sauvola-prob` or `sauvola_prob`).

Two distinct warnings to watch for, both on **stderr**:

| You wrote | Message | Effect |
|-----------|---------|--------|
| A nested mapping (`sauvola:\n  prob: 0.2`) | `Config key 'sauvola' is a nested mapping; only flat keys are supported, skipping.` | The whole block is dropped; the default is kept. |
| A key that matches no flag (`typo-key: 1`) | `[config] WARNING: Unrecognized keys in 'generate' configuration: typo_key` | The key is dropped; the default is kept. |

Neither is an error, so a mistake silently leaves the default in place — watch the log output when
editing a config.

> **Note:** the fonts directory key is `fonts` (matching `--fonts`), not `fonts-dir`.

## Full example

```yaml
# configs/generate.yml

# Rendering
height: 48                            # only used when line-height-mode=fixed
# width: null                         # omit for variable width
color-mode: 1                         # 1 = grayscale, 3 = RGB
fonts: fonts/
font-mode: random
copies: 3
mixed-font-prob: 0.0
retry-limit: 10
random-align-when-padded: false

# Variable line height (all optional; default renders every image at --height)
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
count-only: false
oversample-rare-chars: false  # extra copies of training lines containing rare chars
rare-char-percentile: 5.0     # least-frequent % of distinct chars considered rare
rare-char-multiplier: 3.0     # copy multiplier for lines containing a rare char
# image-dir: ""               # bypass text rendering; corpus must be labels.txt

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

# Rendering style
bg-color-mode: random  # default | paper_tones | colored | dark_mode | gradient | random

# Text decoration (each a probability in [0, 1]; 0 disables)
text-deco-color-prob: 0.0
text-deco-underline-prob: 0.0
text-deco-subscript-prob: 0.0
text-deco-superscript-prob: 0.0
text-deco-italic-prob: 0.0
text-deco-bold-prob: 0.0

# Text effects (mutually exclusive; each a probability in [0, 1]; 0 disables)
text-effect-background-prob: 0.0
text-effect-echo-prob: 0.0
text-effect-glitch-prob: 0.0
text-effect-glow-prob: 0.0
text-effect-hollow-prob: 0.0
text-effect-huge-prob: 0.0
text-effect-neon-prob: 0.0
text-effect-outline-prob: 0.0
text-effect-pixel-prob: 0.0
text-effect-shadow-prob: 0.0
text-effect-tiny-prob: 0.0
text-effect-transparent-prob: 0.0

# Text normalization
norm_unicode_norm: ""  # skipped by default; khmernormalizer normalizes internally
norm_emoji_replacement: ""
norm_url_replacement: ""
norm_no_remove_zwsp: false
norm_no_fix_encoding: false
norm_no_uncurl_quotes: false
norm_no_fix_line_breaks: false
norm_passthrough: false

# Augmentation methods: prob (0-1), min intensity, max intensity
# One augmentation applied per image (isolated, not stacked).
# Exception: extreme_resize's min/max are absolute pixel heights, not [0, 1].
# NOTE: augmentation methods must use flat keys — see the warning below.
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

# extreme_resize: min/max are absolute pixel heights, not [0, 1]
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

### Augmentation keys must be flat

Only **flat** keys are supported by the YAML loader. A nested mapping is dropped with a warning and
the method silently keeps its default:

```yaml
# ✗ WRONG — nested mapping, skipped with a warning
sauvola:
  prob: 0.2
  min: 0.1
  max: 0.9
```

```yaml
# ✓ CORRECT — flat keys
sauvola-prob: 0.2
sauvola-min: 0.1
sauvola-max: 0.9
```

Nested mappings for `normalizer`, `text_deco` and `text_effect` are likewise not read from YAML —
use the flat `norm_*`, `text-deco-*` and `text-effect-*` keys documented above.

## Augmentation method fields

Each method takes three flat keys, named `<method>-prob`, `<method>-min` and `<method>-max`, where
`<method>` is the method name with underscores written as hyphens (`geo_warp` → `geo-warp-prob`):

| Key | Type | Range | Description |
|-------|------|-------|-------------|
| `<method>-prob` | float | [0, 1] | Probability weight for selecting this method |
| `<method>-min` | float | [0, 1] | Minimum intensity (normalized; clamped to ≥ 0) |
| `<method>-max` | float | [0, 1] | Maximum intensity (clamped to ≤ 1; ≥ min) |

**Exception:** `extreme-resize-min`/`extreme-resize-max` are absolute target heights in *pixels*
(default `8`/`1920`, clamped to `min ≥ 1` and `max ≥ min`), not normalized `[0, 1]` values — see
**[Augmentation](Augmentation)**.

**How intensities work:** the actual intensity for a given image is sampled uniformly from
`[min, max]`. The method maps this normalized value to physical units (pixel displacements,
kernel sizes, noise sigmas, …).

**How selection works:** from all methods with `prob > 0`, one is chosen with probability
proportional to its `prob` value. A method with `blur-prob: 0.4` is selected twice as often as one
with `sauvola-prob: 0.2`.

## Text decoration keys

Per-line decorations applied at render time (before augmentation). Each key is a probability in
`[0, 1]`; the default `0` disables that decoration. Decorations can combine. Bold/italic require a
matching variant font and are skipped otherwise. Random color requires `color-mode: 3`.

| Key | Effect |
|-----|--------|
| `text-deco-color-prob` | single random text color for the whole line (RGB only) |
| `text-deco-underline-prob` | underline the whole line |
| `text-deco-subscript-prob` | lower 1–2 random ASCII chars |
| `text-deco-superscript-prob` | raise 1–2 random ASCII chars |
| `text-deco-italic-prob` | italic via a real italic/oblique variant font |
| `text-deco-bold-prob` | bold via a real bold variant font |

## Text effect keys

Canva-style per-line effects applied at render time (before augmentation), on the same clean canvas
as text decorations. Unlike decorations, effects are **mutually exclusive**: each probability is
rolled independently in a fixed order and the first hit wins, so at most one effect applies per
line. They combine freely with `text-deco-*`. Every effect keeps the underlying glyph shapes
intact — the rendered text is still the ground-truth label.

| Key | Effect |
|-----|--------|
| `text-effect-background-prob` | highlight box behind the line |
| `text-effect-echo-prob` | faint offset duplicate (echo/ghost) copies |
| `text-effect-glitch-prob` | small offset colour-split copies |
| `text-effect-glow-prob` | soft blurred halo behind the text |
| `text-effect-hollow-prob` | outline-only glyphs, background-colour interior |
| `text-effect-huge-prob` | oversized text relative to the canvas |
| `text-effect-neon-prob` | bright saturated fill with a neon-sign glow |
| `text-effect-outline-prob` | solid fill with a contrasting stroke |
| `text-effect-pixel-prob` | blocky/pixelated glyph edges |
| `text-effect-shadow-prob` | offset blurred drop shadow |
| `text-effect-tiny-prob` | undersized text relative to the canvas |
| `text-effect-transparent-prob` | partially see-through fill |

## Recipes

### Aggressive blur, nothing else

```yaml
blur-prob: 1.0
blur-min: 0.3
blur-max: 0.9

# Disable all others
sauvola-prob: 0.0
geo-warp-prob: 0.0
# ... etc
```

### Low-contrast multilingual documents

```yaml
fonts: fonts/
color-mode: 3
bg-color-mode: random
line-height-mode: variable
min-line-height: 32
max-line-height: 96
line-height-step: 8
font-size-mode: proportional
vertical-padding-mode: random

low-contrast-caption-prob: 0.2
background-texture-prob: 0.35
jpeg-compression-prob: 0.4
lowdpi-prob: 0.3
```

### Reproducible split for a benchmark

```yaml
corpus: corpus/corpus.txt
split-ratios: [80, 10, 10]
seed: 42
count-only: true
```

## `combine` config

`khocr-gen combine` accepts the same `--config` flag and auto-detects `configs/combine.yml`. Its
keys mirror the `combine` CLI flags:

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

The dataset directories to merge are always given as positional arguments on the command line, not
in the config file:

```bash
khocr-gen combine --config configs/combine.yml data_run1/ data_run2/
```

## See also

- **[CLI Reference](CLI-Reference)** — the flag behind every key
- **[Corpus and Normalization](Corpus-and-Normalization)** — split semantics and normalization keys
- **[Augmentation](Augmentation)** — what each method does with its intensity
