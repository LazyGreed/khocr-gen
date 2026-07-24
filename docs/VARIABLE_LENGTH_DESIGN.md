## Variable Height Line Images

### Goal

Allow the synthetic data generator to create line images whose rendered text/canvas height varies within controlled bounds, improving robustness to real OCR crops.

### Functional Requirements

1. **Configurable Height Variation**

`khocr-gen generate` should support variable height output through explicit configuration.

Possible CLI/config options:

```bash
khocr-gen generate \
  --line-height-mode variable \
  --min-line-height 32 \
  --max-line-height 96
```

Or via `generate.yml`:

```yaml
line_height_mode: variable
min_line_height: 32
max_line_height: 96
```

**Recommended modes:**

- fixed: current behavior; all generated line images use the existing configured height.
- variable: each generated line image samples a height from a configured range.
- bucketed: generated heights are sampled from a small fixed set, e.g. 32, 48, 64, 80, 96.

Keep `fixed` the default for backward compatibility.

2. **Bounded Height Sampling**

When `line_height_mode=variable`, each generated sample should choose a line/canvas height from a bounded range.

**Example behavior:**

sample 1 -> height 48
sample 2 -> height 64
sample 3 -> height 40
sample 4 -> height 88

**Requirements:**

- The sampled height must be between `min_line_height` and `max_line_height`.
- Heights should probably be integer pixels.
- Optionally align to a multiple, e.g. `--line-height-step 8`, to avoid awkward shapes and improve batching.

**Example:**

```yaml
min_line_height: 32
max_line_height: 96
line_height_step: 8
```

**Then possible heights are:**

32, 40, 48, 56, 64, 72, 80, 88, 96

3. **Separate Text Scale From Canvas Height**

The generator should distinguish between:

- canvas height: total image height
- rendered text height / font size: how large the glyphs are inside the canvas
- vertical padding: empty space above/below text

This matters because these are not equivalent.

Good variable height generation should support both:

```yaml
line_height_mode: variable
min_line_height: 32
max_line_height: 96

font_size_mode: proportional
min_font_scale: 0.65
max_font_scale: 0.9

vertical_padding_mode: random
min_vertical_padding_ratio: 0.04
max_vertical_padding_ratio: 0.18
```

**Practical interpretation:**

- Generate a 64px-tall line image.
- Pick a font size that fits into roughly 65–90% of that height.
- Add random top/bottom padding.
- Render the text without clipping Khmer diacritics.

This is better than simply resizing a fixed height render up and down.

4. **Preserve Existing Label Format**

The existing `labels.txt` should remain valid.

**Current likely format:**

```text
path/to/image.png<TAB>text label
```

That should not need to change.

Variable height is encoded by the actual image dimensions, not by the label file.

5. **Optional Metadata Recording**

The generator may write metadata for debugging and reproducibility.

Example sidecar metadata:

```json
{
  "image": "data/train/000001.png",
  "text": "example text",
  "width": 384,
  "height": 64,
  "font_size": 42,
  "font": "KhmerOS.ttf",
  "augmentation_seed": 12345
}
```

This could be useful for:

- QA renders
- diagnosing clipping
- measuring height distribution
- reproducing bad samples

But it should be optional or additive.

6. **Prevent Glyph Clipping**

This is especially important for Khmer.

The generator must avoid cutting off:

- upper vowel marks
- lower vowel marks
- coeng/subscript forms
- stacked diacritics
- punctuation near boundaries

**Functional checks:**

- compute text bounding box before final crop/paste when possible
- include a minimum vertical safety margin
- avoid aggressive tight cropping unless explicitly enabled
- optionally reject and retry samples where rendered glyphs exceed the canvas

**Example requirement:**

If rendered text bbox exceeds the target canvas height, retry with smaller font size or larger sampled height.

Do not silently clip.

7. **Width Handling Should Remain Compatible**

Variable height will also affect natural text width if font size changes.

The generator should preserve current width behavior as much as possible:

- if current generation uses fixed width, keep fixed width unless changed separately
- if current generation uses dynamic width, continue dynamic width
- if generated width exceeds max width, use existing wrapping/scaling/truncation behavior

Avoid coupling this feature to a larger “variable width” redesign unless needed.

8. **LMDB Packing Must Support Variable Dimensions**

If generate `--pack-lmdb` is used, the packed data should preserve image bytes as generated.

**Requirements:**

- LMDB writer should not assume fixed dimensions.
- LMDB reader/training dataset should decode and normalize images as usual.
- No change to label semantics.

If the current LMDB path assumes fixed shape somewhere, that would need to be corrected.

9. **QA / Verification Output Should Expose Height Diversity**

`khocr-gen verify` or generation logs should make height variation visible.

**Useful outputs:**

- min/max/mean generated image height
- histogram of sampled heights
- count of rejected/retried samples due to clipping
- example render grid containing multiple heights

**Example log:**

Generated 10000 train samples
Line height mode: variable
Height range: 32..96 step 8
Observed heights: min=32 max=96 mean=63.7
Rejected for clipping: 42

### Non-Functional Requirements

1. **Backward Compatibility**

Existing commands should behave the same unless the new option is enabled.

**Required:**

`khocr-gen generate`

should produce the same style of fixed height dataset as before, except for unrelated randomness already present.

No breaking changes to:

- labels.txt
- vocab generation

2. **Reproducibility**

Height sampling must be deterministic under the generator seed.

If the user runs the same generation command with the same seed and inputs, sampled heights should be identical.

This means height sampling should use the generator's existing RNG path, not global uncontrolled randomness.

3. **Config File Support**

Because generate already supports `-c/--config`, every new CLI option should be supported through YAML config too.

Expected precedence should remain:

argparse defaults < YAML values < explicit CLI flags

So this should work:

`khocr-gen generate -c configs/generate.yml --max-line-height 80`

with CLI overriding YAML.

4. **Performance**

Variable height generation should not significantly slow down generation.

**Targets:**

- avoid expensive per-sample layout retries where possible
- cap retry count for clipping avoidance
- use efficient text bounding-box measurement
- avoid opening/reloading font files per sample if the current generator caches them

**Acceptable behavior:**

If a sample cannot be rendered without clipping after N retries, fall back to a safe height/font size combination or skip with a counted warning.

5. **Dataset Quality**

Generated variation should be realistic, not merely random.

**Requirements:**

- avoid extremely tiny text unless explicitly configured
- avoid mostly empty tall canvases
- avoid cramped canvases that clip marks
- keep sampled distribution controllable

A good default distribution is probably not uniform over all pixel heights. Better options:

- bucketed realistic heights
- weighted sampling around the current default height
- normal/triangular distribution clipped to min/max

**Example:**

```yaml
line_height_distribution: triangular
line_height_mode: variable
min_line_height: 32
default_line_height: 48
max_line_height: 96
```

This keeps most samples near normal while still producing larger/smaller lines.

6. **Clear Failure Modes**

Invalid configurations should fail early with actionable errors.

**Examples:**

--min-line-height must be > 0
--max-line-height must be >= --min-line-height
--line-height-step must be > 0
--line-height-mode fixed cannot be used with min/max line height unless explicitly allowed

For project consistency, these should probably use typed project errors where appropriate, then surface clean CLI messages.

7. **Testability**

The feature should be covered with targeted tests.

**Suggested test cases:**

- default generation remains fixed-height
- variable mode produces more than one height with a fixed seed
- sampled heights stay within configured bounds
- same seed gives same sequence of heights
- invalid min/max configuration fails
- generated labels remain unchanged in format
- LMDB packing still works with variable size images, if applicable
- no rendered sample has text bbox outside canvas, at least in a small deterministic fixture
