# Text Decorations and Effects

Two independent systems change how a line *looks* before any augmentation is applied:

- **Text decorations** — color, underline, subscript, superscript, italic, bold. They **combine**
  freely: any subset can apply to the same line.
- **Text effects** — Canva-style effects (shadow, glow, outline, …). They are **mutually
  exclusive**: at most one applies per line.

Both are sampled per line at render time, on the clean canvas, *before* augmentation, and both are
disabled by default (`prob: 0`).

## Why this matters

The rendered text is still the ground-truth OCR label. Every decoration and effect is designed to
change appearance without changing the underlying glyph shapes — so you can train a recogniser on
stylised text without corrupting its labels.

## Text decorations

| Flag | Config key | Effect |
|------|-----------|--------|
| `--text-deco-color-prob F` | `text-deco-color-prob` | A single random text color for the whole line |
| `--text-deco-underline-prob F` | `text-deco-underline-prob` | Underline the whole line |
| `--text-deco-subscript-prob F` | `text-deco-subscript-prob` | Lower 1–2 random ASCII characters |
| `--text-deco-superscript-prob F` | `text-deco-superscript-prob` | Raise 1–2 random ASCII characters |
| `--text-deco-italic-prob F` | `text-deco-italic-prob` | Italic via a real italic/oblique variant font |
| `--text-deco-bold-prob F` | `text-deco-bold-prob` | Bold via a real bold variant font |

Constraints and behaviour:

- **Random color requires `--color-mode 3`** (RGB). In grayscale output the color decoration
  cannot apply.
- **Bold and italic are skipped when no matching variant font exists.** They do not synthesise a
  fake bold/oblique — the renderer looks for a real variant in the font pools. See
  **[Fonts](Fonts)**.
- Subscript/superscript only move ASCII characters; Khmer combining marks are left alone.
- Decorations are applied on the clean canvas, so augmentations never interfere with them and vice
  versa.

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts \
  --color-mode 3 \
  --text-deco-color-prob 0.3 \
  --text-deco-underline-prob 0.2 \
  --text-deco-bold-prob 0.2 \
  --text-deco-italic-prob 0.2 \
  --text-deco-subscript-prob 0.1
```

## Text effects

Effects mirror a Canva-style effects panel: single-select. Each probability is rolled
independently in a fixed order and **the first hit wins**, so at most one effect applies per line
even if several probabilities are non-zero.

Roll order is alphabetical:

`background` → `echo` → `glitch` → `glow` → `hollow` → `huge` → `neon` → `outline` → `pixel` →
`shadow` → `tiny` → `transparent`

| Flag | Effect |
|------|--------|
| `--text-effect-background-prob F` | Highlight box behind the line |
| `--text-effect-echo-prob F` | Faint offset duplicate (echo/ghost) copies |
| `--text-effect-glitch-prob F` | Small offset colour-split copies |
| `--text-effect-glow-prob F` | Soft blurred halo behind the text |
| `--text-effect-hollow-prob F` | Outline-only glyphs with a background-colour interior |
| `--text-effect-huge-prob F` | Oversized text relative to the canvas |
| `--text-effect-neon-prob F` | Bright saturated fill with a neon-sign glow |
| `--text-effect-outline-prob F` | Solid fill with a contrasting stroke |
| `--text-effect-pixel-prob F` | Blocky / pixelated glyph edges |
| `--text-effect-shadow-prob F` | Offset blurred drop shadow |
| `--text-effect-tiny-prob F` | Undersized text relative to the canvas |
| `--text-effect-transparent-prob F` | Partially see-through fill |

Because effects are mutually exclusive, adding more `--text-effect-*-prob` flags increases the
share of *stylised* lines but never stacks two effects on one line. To raise the overall rate of
effects, raise several probabilities together — for example `huge 0.1 + tiny 0.1 + shadow 0.1`
gives roughly a 27% chance that *some* effect applies.

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts \
  --text-effect-huge-prob 0.1 \
  --text-effect-tiny-prob 0.1 \
  --text-effect-shadow-prob 0.1 \
  --text-effect-outline-prob 0.1 \
  --text-effect-hollow-prob 0.1 \
  --text-effect-echo-prob 0.1 \
  --text-effect-background-prob 0.1
```

## Combining decorations and effects

Decorations and effects are independent systems and combine freely:

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --color-mode 3 \
  --text-deco-color-prob 0.5 --text-deco-italic-prob 0.4 \
  --text-effect-shadow-prob 0.1 --text-effect-glow-prob 0.1
```

A line rendered with this recipe can be, for example, coloured *and* italic *and* shadowed —
at most one effect, any number of decorations.

## Verifying what you configured

`verify` can render any single decoration or effect at fixed intensity, one at a time, with all
other probabilities pinned to 0 — useful to confirm an effect looks the way you expect before
committing to a full generation run:

```bash
# One decoration
khocr-gen verify --fonts fonts --method text_deco_bold

# One effect
khocr-gen verify --fonts fonts --method text_effect_glow

# Several at once
khocr-gen verify --fonts fonts --method text_deco_underline text_effect_neon
```

The full set of `--method` names for these is `text_deco_{bold,color,italic,subscript,superscript,underline}`
and `text_effect_{background,echo,glitch,glow,hollow,huge,neon,outline,pixel,shadow,tiny,transparent}`.

## In metadata

When `--record-metadata` is set, the active decoration names are recorded per sample in
`metadata.jsonl` under the `decorations` key. See **[Output and Storage](Output-and-Storage)**.

## Configuration examples

```yaml
# Colored, occasionally italic lines with an occasional effect
color-mode: 3
text-deco-color-prob: 0.5
text-deco-italic-prob: 0.4
text-deco-bold-prob: 0.0
text-effect-huge-prob: 0.1
text-effect-shadow-prob: 0.1
text-effect-outline-prob: 0.1
```

> Remember that YAML augmentation-style nested mappings are not read — use the flat
> `text-deco-*` / `text-effect-*` keys. See **[Configuration](Configuration)**.
