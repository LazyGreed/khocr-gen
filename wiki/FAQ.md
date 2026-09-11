# FAQ

### What is khocr-gen for?

Generating synthetic OCR training data for **mixed Khmer/English** text. You give it a text corpus
and fonts; it produces labelled line images with realistic degradation, optionally packed into LMDB
for a training pipeline.

### Do I need a GPU?

No. Generation is CPU-bound image work, parallelised across processes.

### Do I need Rust?

No. The Rust extension is an optional accelerator. Every accelerated path has a pure-Python
fallback, so `pip install khocr-gen` works anywhere.

### Does the PyPI wheel include the Rust extension?

No. The PyPI wheel is pure Python; `HAS_RUST_ACCEL` will be `False` unless you build from source
with the `rust` or `dev` extra.

### How do I check whether acceleration is active?

```bash
uv run python -c "from khocr_gen import _rust_accel as ra; print(ra.HAS_RUST_ACCEL)"
```

### How many images will I get?

Roughly `filtered_lines × copies` for train, plus one image per line for val and test (or one per
font per line with `--font-mode all`). Oversampled training lines add more. Don't guess — run:

```bash
khocr-gen generate --corpus corpus/corpus.txt --count-only
```

### Why is exactly one augmentation applied per image?

Deliberate design. Stacking degradations compounds into unrealistic images and makes it impossible
to attribute quality changes to a method. One effect per image, chosen by weighted probability,
keeps the distribution controllable and the dataset interpretable.

### Can I apply two augmentations to the same image?

Not through the built-in pipeline. Generate twice with different settings and merge with
`khocr-gen combine` if you want a wider distribution.

### Why don't my bold/italic lines appear?

`--text-deco-bold-prob` and `--text-deco-italic-prob` use **real variant fonts**. If your font pool
has no file tagged bold (or italic/oblique), the decoration is skipped for that line rather than
faked. Add variant files to the pool. See **[Fonts](Fonts)**.

### Why does `--text-deco-color-prob` do nothing?

Random text colour requires `--color-mode 3` (RGB). In the default grayscale output there is no
colour to apply.

### Why do two `verify` runs differ?

The RNG is reseeded per image so pure-Python methods reproduce across runs, but **Rust-accelerated
methods keep their own thread RNG and still vary**. Some variation in `verify` output is expected
and not a bug.

### Does `--seed` give me reproducible images?

Partly. `--seed` controls the **train/val/test split** shuffle. It does not seed rendering,
decorations, effects, augmentation or variable-height sampling — those draw from the module-level
`random`. Same seed ⇒ same split; not necessarily the same pixels. See
**[Variable Line Height](Variable-Line-Height)**.

### Can heights vary between images in one dataset?

Yes — that's `--line-height-mode variable|bucketed`. See **[Variable Line Height](Variable-Line-Height)**.
Downstream loaders must handle non-uniform image dimensions.

### Will variable height clip Khmer diacritics?

No. Images are rendered at their natural size and then uniformly **resized** to the sampled height
— never cropped — so glyphs are never cut off. There are no retries or rejected samples.

### What's the difference between `raw`, `lmdb` and `both`?

`--storage raw` writes image files, `lmdb` packs and then deletes them, `both` keeps both. The
legacy `--pack-lmdb` / `--keep-raw` flags map onto the same behaviour.

### How do I read the LMDB files without this package?

The key layout is plain strings: `image-000000001`, `label-000000001`, and `num-samples`. Any LMDB
client can read it. See **[Output and Storage](Output-and-Storage)**.

### Can I add my own images to a generated dataset?

Yes — `--image-dir DIR` bypasses rendering and uses images you already have. The "corpus" must then
be a `labels.txt` in the standard format.

### Can I merge datasets generated with different settings?

Yes. `khocr-gen combine` merges any mix of raw and LMDB splits and always emits LMDB, along with a
merged `vocab.json`.

### Why was my val/test split empty?

If you set only one of `--val-percent` / `--test-percent`, the other becomes 0 — that's the
documented behaviour. Use `--split-ratios` for explicit control. See
**[Corpus and Normalization](Corpus-and-Normalization)**.

### Are synthetic val/test splits safe?

Yes. Splits are disjoint at the **text** level, so no text string appears in two splits, and an
augmented variant of a training line can never leak into val or test.

### Are val/test lines oversampled with `--oversample-rare-chars`?

No. Oversampling applies to `train` only; val and test stay at one copy per line so evaluation
reflects the natural corpus distribution.

### My config file changes have no effect. Why?

Almost certainly a **nested mapping**. The YAML loader only reads flat keys; a nested block is
dropped and the default is kept. Use `sauvola-prob: 0.2` rather than `sauvola: {prob: 0.2}`.
Watch stderr for `Config key 'sauvola' is a nested mapping; only flat keys are supported, skipping.`
See **[Configuration](Configuration)**.

### What's the difference between decorations and effects?

Decorations (color, underline, sub/superscript, bold, italic) **combine**. Effects (shadow, glow,
outline, …) are **mutually exclusive** — at most one per line, first probability hit wins. Both run
before augmentation. See **[Text Decorations and Effects](Text-Decorations-and-Effects)**.

### Do effects change the label?

No. Every effect and decoration preserves the underlying glyph shapes; the rendered text remains
the ground-truth OCR label.

### Which augmentation methods are *not* Rust-accelerated?

`distortion`, `albu_noise`, `gradient_illumination`, `extreme_resize` and `low_contrast_caption`.
See **[Rust Acceleration](Rust-Acceleration)** for the reasons.

### What does `extreme_resize`'s min/max mean?

Pixel heights, not `[0, 1]` intensities — it's the only method like that. Defaults are `8` and
`1920`.

### Can I run this in Docker / on a headless server?

Yes. Dependencies use `opencv-python-headless`, so no GUI libraries are needed.

### Is there a viewer?

Yes — `khocr-gen view --lmdb DIR --summary|--output-dir|--labels-only`. For augmenation QA use
`khocr-gen verify`.

### Is there a Python API?

The package is importable (`khocr_gen.rendering.ImageRenderer`,
`khocr_gen.data_generator.DatasetGenerator`, `khocr_gen.config.GenerationConfig`), but the supported
interface is the CLI. See **[Architecture](Architecture)** for the module map.

### How do I report a bug?

Open an issue at <https://github.com/LazyGreed/khocr-gen/issues>. Include the exact command, the
config file if you used one, the observed output, and the `khocr-gen --version` value. If images
look wrong, attach a sample and the `verify_output` render for the method involved.
