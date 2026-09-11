# Variable Line Height

By default every generated image is rendered at a fixed `--height`. `--line-height-mode` samples a
**per-image canvas height** instead, which makes the synthetic data match the ragged crop heights a
real OCR pipeline sees.

Three independent knobs control the result:

| Knob | What it controls | Flag(s) |
|------|------------------|---------|
| Canvas height | Total image height | `--line-height-mode`, `--min-line-height`, `--max-line-height`, `--line-height-step`, `--line-height-distribution`, `--default-line-height` |
| Font scale | Glyph size *inside* the canvas | `--font-size-mode`, `--min-font-scale`, `--max-font-scale` |
| Vertical padding | Empty space above/below the text | `--vertical-padding-mode`, `--min-vertical-padding-ratio`, `--max-vertical-padding-ratio` |

These are genuinely separate: a 64 px canvas with 65–90% font scale is a different (and more
realistic) sample than a 48 px render stretched to 64 px.

## Height modes

| Mode | Behaviour |
|------|-----------|
| `fixed` *(default)* | Every image uses `--height`. Backward compatible. |
| `variable` | Sample a height per image from `[--min-line-height, --max-line-height]`. |
| `bucketed` | Sample from the fixed set of heights spaced by `--line-height-step`. |

### Alignment

`--line-height-step` snaps sampled and bucketed heights to a multiple, which keeps image shapes
tidy and improves batching:

```text
min=32, max=96, step=8  →  32, 40, 48, 56, 64, 72, 80, 88, 96
```

### Distribution

`--line-height-distribution {uniform,triangular}` shapes the `variable` mode:

- `uniform` *(default)* — every height in range equally likely.
- `triangular` — clusters around `--default-line-height` (defaults to the range midpoint), which
  produces mostly "normal" lines with a tail of larger/smaller ones.

```yaml
line-height-mode: variable
line-height-distribution: triangular
min-line-height: 32
default-line-height: 48
max-line-height: 96
```

## Font scale

`--font-size-mode {fixed,proportional}`:

- `fixed` *(default)* — choose from the preloaded font sizes.
- `proportional` — size the font relative to the sampled canvas height, with the glyph height kept
  within `[--min-font-scale, --max-font-scale]` of the canvas height.

```yaml
font-size-mode: proportional
min-font-scale: 0.65
max-font-scale: 0.9
```

## Vertical padding

`--vertical-padding-mode {fixed,random}`. In `random` mode the top/bottom padding is sampled as a
ratio of canvas height rather than a constant pixel amount:

```yaml
vertical-padding-mode: random
min-vertical-padding-ratio: 0.04
max-vertical-padding-ratio: 0.18
```

## No glyph clipping — ever

This is the core guarantee of the feature, and it matters most for Khmer.

Every image is rendered on a clean canvas at its **natural size** and then uniformly **resized**
(never cropped) to the sampled target height. Glyphs — including Khmer upper vowels, lower vowels,
coeng/subscript forms and stacked diacritics — are therefore never cut off, regardless of which
height is sampled. There are no retry loops and no rejected samples: the resize is unconditional
and lossless with respect to glyph coverage.

`labels.txt` is **unaffected** — variable height is encoded entirely in the image dimensions. The
label file format does not change, and neither does vocab generation.

## Randomness and reproducibility

Height, font-scale and padding are sampled at render time from the **module-level `random`** RNG.
The sampler functions in `khocr_gen/line_height.py` accept an optional `random.Random` argument,
but the renderer does not pass one.

`--seed` controls the **train/val/test split shuffle only** — it does not pin the sampled heights.
Two runs with the same `--seed` therefore produce the same split but different height draws. If you
need bit-identical images across runs, pin the global `random` state inside your own driver script
before calling into the generator; the CLI does not expose a render-level seed.

See **[Corpus and Normalization](Corpus-and-Normalization)** for how `--seed` drives the split.

## Metadata sidecar

Add `--record-metadata` to write a `metadata.jsonl` next to `labels.txt` in each split, with one
JSON object per generated image:

```json
{"image": "data/train/images/000001.png", "text": "example text", "width": 384, "height": 64, "font": "KhmerOS.ttf", "font_size": 42, "decorations": ["bold"]}
```

Useful for QA renders, diagnosing clipping, measuring the height distribution, and reproducing
individual samples. See **[Output and Storage](Output-and-Storage)**.

## Examples

```bash
# Sample heights in [32, 96], aligned to 8px steps
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 --line-height-step 8

# Vary font scale and padding too, and record per-sample metadata
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 \
  --font-size-mode proportional --min-font-scale 0.65 --max-font-scale 0.9 \
  --vertical-padding-mode random --min-vertical-padding-ratio 0.04 --max-vertical-padding-ratio 0.18 \
  --record-metadata

# A tight, bucketed set of realistic crop heights
khocr-gen generate --corpus corpus/corpus.txt \
  --line-height-mode bucketed --min-line-height 32 --max-line-height 64 --line-height-step 16
```

The equivalent YAML:

```yaml
line-height-mode: variable
min-line-height: 32
max-line-height: 96
line-height-step: 8
line-height-distribution: uniform
font-size-mode: proportional
min-font-scale: 0.65
max-font-scale: 0.9
vertical-padding-mode: random
min-vertical-padding-ratio: 0.04
max-vertical-padding-ratio: 0.18
record-metadata: true
```

## Interactions

- **LMDB packing** — image bytes are stored exactly as generated; the writer does not assume fixed
  dimensions. Variable-size images pack and read back normally.
- **`combine`** — merges datasets whose images have differing dimensions without complaint.
- **`--height`** — ignored when `--line-height-mode` is `variable` or `bucketed`.

## See also

- **[CLI Reference](CLI-Reference)** — the full flag table
- **[Output and Storage](Output-and-Storage)** — where `metadata.jsonl` lives
- **[Fonts](Fonts)** — how font sizes are preloaded and selected
