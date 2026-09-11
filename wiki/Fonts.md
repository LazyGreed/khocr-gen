# Fonts

Fonts drive everything about how text looks, and the generator is **script-aware**: Khmer text and
English text are drawn from separate pools.

## Directory layout

```text
fonts/
├── khmer/     <- .ttf / .otf / .ttc / .woff / .woff2 Khmer fonts
├── english/   <- .ttf / .otf / .ttc / .woff / .woff2 English fonts
└── *.ttf      <- files directly here join BOTH pools as fallbacks
```

The root directory is set with `--fonts DIR` (default `fonts/`) or the YAML key `fonts`. The
`khmer/` and `english/` subdirectories are scanned **recursively**, so you can organise fonts into
further subfolders.

## Supported formats

| Extension | Notes |
|-----------|-------|
| `.ttf` | TrueType — the common case |
| `.otf` | OpenType |
| `.ttc` | TrueType collection |
| `.woff` | Web Open Font Format |
| `.woff2` | Web Open Font Format 2 |

## Script selection

For each text line the generator decides which pool to draw from:

- Text containing Khmer characters → the **Khmer** pool.
- Pure Latin text → the **English** pool.
- Mixed Khmer/English → the pool for the dominant script, **plus** per-span font switching when
  `--mixed-font-prob` is non-zero (see below).

Fonts sitting directly in `fonts/` are always eligible, which makes them a useful fallback when one
pool is thin.

## Glyph coverage

Not every font covers every glyph. Before using a font the renderer checks that it can actually
draw the text via `ImageRenderer._is_text_supported`:

- With Rust acceleration, this is an **O(1) cmap-table lookup** (`_rust_accel.FontFace`), cached per
  font path — no rasterisation involved.
- Without it, the fallback rasterises candidate characters with PIL and diffs them against the
  font's `.notdef` ("tofu") glyph.

When a font cannot draw the text, the generator retries: `--retry-limit N` (default 10) controls how
many alternative fonts it will try before giving up on that line. Keep this in mind if your Khmer
pool is small — raise the limit, or add more fonts.

## Width selection and font sizes

Fonts are registered at a set of standard sizes (`28, 32, 36, 40, 44, 48`). Actual FreeType faces
are loaded **lazily** on first use and kept in a bounded LRU cache (1024 entries) so a long run
does not pin every face it has ever touched in memory.

With `--font-size-mode proportional`, sizes are instead derived per image from the sampled canvas
height — see **[Variable Line Height](Variable-Line-Height)**.

## Bold and italic variants

Bold and italic text decorations use **real variant fonts**, not synthesised weight/slant. A font
file is tagged by inspecting its filename stem and its internal style name:

- `bold` in the name (or style name) → tagged `bold`
- `italic` or `oblique` in the name (or style name) → tagged `italic`

Selection rules for `--text-deco-bold-prob` / `--text-deco-italic-prob`:

| Requested | Behaviour |
|-----------|-----------|
| bold | any font tagged bold (a bold-italic font qualifies) |
| italic | any font tagged italic/oblique |
| bold **and** italic | prefer a font tagged both, else fall back to a bold font |

If no matching variant exists in the pool, the decoration is **skipped** for that line rather than
faking it — so `--text-deco-bold-prob 0.5` on a pool with no bold fonts simply produces no bold
lines. Ship real variant files (e.g. `NotoSansKhmer-Bold.ttf`, `NotoSansKhmer-Italic.ttf`) if you
want these decorations to fire.

## Mixed-script rendering

`--mixed-font-prob F` (default `0.0`) sets the probability that a line containing both scripts is
rendered with **per-span font selection** — each contiguous run of Khmer or Latin text gets a font
drawn from its own pool. At `0.0` the whole line uses a single font chosen for the dominant script.

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --mixed-font-prob 0.6
```

Span splitting is accelerated in Rust (`_rust_accel.split_text_spans`) with an equivalent pure-Python
fallback. See **[Rust Acceleration](Rust-Acceleration)**.

## `--font-mode`

| Value | Behaviour |
|-------|-----------|
| `random` *(default)* | Render `--copies` augmented copies per text line, each with a randomly chosen font |
| `all` | Render one image per font per line |

`font-mode=all` touches every font at every standard size, which is the heaviest path for the font
cache — expect a longer warm-up and more memory than `random`.

## Practical advice

- **More fonts beat more copies.** A pool of 3–5 Khmer fonts gives far more useful variation than
  raising `--copies` on a single font.
- **Include one broadly-covering Khmer font** as a fallback — Khmer coverage varies a lot between
  fonts, and missing glyphs cause retries and skipped lines.
- **Check what you have.** Run a tiny generation with `--count-only` first, then generate a few
  hundred samples and inspect them with `khocr-gen view`.
- **Add variant files deliberately** if you plan to use bold/italic decorations.

## See also

- **[Getting Started](Getting-Started)** — first setup walkthrough
- **[Text Decorations and Effects](Text-Decorations-and-Effects)** — what bold/italic do
- **[Variable Line Height](Variable-Line-Height)** — proportional font sizing
- **[Troubleshooting](Troubleshooting)** — what to do when lines come out empty
