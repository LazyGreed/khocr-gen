# Augmentation

`khocr-gen` provides **26 augmentation methods** in a unified registry. Each generated image
receives **exactly one** augmentation applied to a clean rendered canvas — effects are never
stacked.

21 of the 26 methods run through the native Rust extension when it is available (falling back to
pure Python/OpenCV otherwise). The five that are not accelerated are `distortion`, `albu_noise`,
`gradient_illumination`, `extreme_resize`, and `low_contrast_caption` — see
**[Rust Acceleration](Rust-Acceleration)**.

## How it works

```text
clean canvas ──▶ pick 1 method (weighted by prob) ──▶ sample intensity ∈ [min, max] ──▶ apply ──▶ output
```

### Selection

From all methods with `prob > 0`, one is chosen with probability proportional to its `prob` weight:

```text
P(method_i) = prob_i / Σ prob_j        (over all enabled methods j)
```

A method with `blur-prob: 0.4` is selected twice as often as one with `sauvola-prob: 0.2`. Setting
its `-prob` to `0.0` disables a method entirely. Keys are written `<method>-prob`,
`<method>-min`, `<method>-max` — see **[Configuration](Configuration)**.

### Intensity

Once a method is chosen, its intensity is sampled **uniformly** from its configured `[min, max]`
range — both in `[0, 1]` for every method except `extreme_resize`, whose `min`/`max` are absolute
pixel heights. The method maps the normalized value to physical units:

| Method | intensity → physical |
|--------|---------------------|
| `blur` | kernel size [3, 15] |
| `rotation` | degrees [0.5, 8.0] |
| `salt_pepper` | pixel density [0.001, 0.04] |
| `jpeg_compression` | quality [95, 25] (inverted: higher intensity = lower quality) |
| `sauvola` | k value [0.05, 0.50] |
| `geo_warp` | corner displacement [0.5, 12] px |
| `lowdpi` | downsample ratio [0.15, 0.80] |

Individual methods' mappings are listed below.

---

## Scanner / camera degradations

### `sauvola` — Sauvola local threshold degradation

Simulates degraded binarization artifacts common in scanned documents.

- **Intensity → k parameter** [0.05, 0.50]
- Adaptive window (25 px, capped by image size)
- Blends the binary result with the original via a weighted alpha

### `geo_warp` — Geometric perspective warp

4-point perspective distortion simulating camera angle or page curl.

- **Intensity → corner displacement** [0.5, 12] px
- Background colour estimated from the image border; the border is filled with it

### `vertical_crop` — Vertical crop

Crops and pads the top or bottom edge, simulating misaligned scanning.

- **Intensity → crop amount** [1, 8] px
- Crops from the foreground region edge; pads with the estimated background colour

### `blur` — Blur (motion / median / gaussian)

Uses an Albumentations `OneOf` pipeline (falls back to OpenCV `GaussianBlur`).

- **Intensity → kernel size** [3, 15] (odd)
- Random choice of MotionBlur, MedianBlur or GaussianBlur
- Pure OpenCV fallback when Albumentations is unavailable

### `distortion` — Distortion (optical / grid / elastic)

Uses an Albumentations `OneOf` pipeline (no-op fallback without Albumentations).

- **Intensity → `distort_limit`** [0.05, 0.30]
- Random choice of OpticalDistortion, GridDistortion or ElasticTransform
- Grid uses 5 steps; elastic uses sigma 20

### `albu_noise` — Noise (gaussian / multiplicative)

Uses an Albumentations `OneOf` pipeline (OpenCV fallback available).

- **Intensity → standard deviation** [0.005, 0.20] normalized units
- Random choice of GaussNoise or MultiplicativeNoise
- Fallback: additive Gaussian noise, σ [3, 25]

### `jpeg_compression` — JPEG compression artifacts

Encodes and decodes the image at configurable quality levels.

- **Intensity → JPEG quality** [95, 25] (inverted)
- `cv2.imencode` / `cv2.imdecode` round-trip
- Handles both grayscale and RGB

### `rotation` — Random rotation

Small-angle rotation with border fill.

- **Intensity → max degrees** [0.5, 8.0]
- Direction: random clockwise or counter-clockwise
- Border filled with the estimated background colour

### `salt_pepper` — Salt-and-pepper noise

Impulse noise: random white (salt) and black (pepper) pixels.

- **Intensity → pixel density** [0.001, 0.04]
- Equal distribution of salt and pepper
- Works on grayscale and RGB

### `background_texture` — Background texture overlay

Procedural paper-like texture with three modes:

1. **Fine grain** — per-pixel Gaussian noise
2. **Coarse blotches** — low-resolution noise upscaled and blurred
3. **Streaks** — horizontal line artifacts (scanner streaks)

- **Intensity → blend alpha** [0.05, 0.30]
- Texture is suppressed over dark ink regions to preserve legibility

### `lowdpi` — Low-DPI simulation

Downscale-then-upscale using NEAREST to downsample and LANCZOS4 to upsample.

- **Intensity → downsample ratio** [0.15, 0.80] (inverted: higher = smaller = lower DPI)
- Minimum output dimension: 2 px

### `oversample` — Oversample rendering

Post-hoc sharpening filter (the *rendering-mode* oversample is handled in the renderer, not here).

- **Intensity → sharpen strength** [1.0, 1.5]
- Uses a 3×3 unsharp mask kernel

### `extreme_resize` — Extreme source-resolution simulation

Isotropically resizes the clean canvas to a sampled target height in pixels (width scales with it)
before the pipeline resizes it back to line height — simulating a tiny/pixelated source (small end
of the range, e.g. `8`) or a huge scan later shrunk down (large end, e.g. `1920`).

- **Intensity is an absolute pixel height, not a `[0, 1]` fraction** — the only method where this
  is true. Default range `min=8`, `max=1920`; disabled by default (`prob: 0.0`).
- Downscale uses `INTER_AREA`, upscale uses `INTER_LINEAR`
- CLI: `--extreme-resize-prob` / `-min` / `-max`

### `low_contrast_caption` — Low-contrast small caption text

Simulates faded, small-point captions/footnotes common in scanned documents: dynamic range
compresses toward mid-gray and fine stroke detail softens as if the text were rendered at a small
point size.

- **Intensity → contrast compression** [0.15, 0.65]
- **Intensity → downscale ratio** [0.85, 0.45] (inverted)
- Compression blends pixel values toward `0.6 × background + 0.4 × neutral gray`
- Detail loss via `INTER_AREA` downscale followed by `INTER_LINEAR` upscale

---

## Training-time augmentations

These simulate augmentations typically applied *during* OCR training. They are disabled by default
(`prob: 0.0`) but can be enabled to make generated data more closely match training-time
conditions.

### `perspective` — Online perspective warp

Mild perspective distortion via `cv2.getPerspectiveTransform`.

- **Intensity → max displacement fraction** [0.02, 0.12] of image size
- Border filled with gray (128)

### `elastic` — Online elastic distortion

Displacement-field-based elastic deformation.

- **Intensity → displacement sigma** [0.02×size, 0.12×size]
- Coarse grid scaled to full resolution

### `random_crop` — Online random height crop

Crop top or bottom and resize back to the original dimensions.

- **Intensity → crop fraction** [0.01, 0.08] of height

### `online_blur` — Online blur

Gaussian or motion blur.

- **Intensity → kernel size** [3, 7] (odd)
- 50% chance of MotionBlur when Albumentations is available

### `online_noise` — Online Gaussian noise

Additive Gaussian noise.

- **Intensity → noise sigma** [3, 30]

### `hsv` — HSV color jitter

Saturation and value adjustments (grayscale images pass through unchanged).

- **Intensity → jitter factor** [0.60, 0.95]
- Independent random multiplier for the S and V channels

### `reverse` — Color reversal

Inverts pixel values (dark ↔ light). Common for handling negative / white-on-black text.

- **Intensity ignored** — binary on/off effect
- `255 - pixel` for every pixel

### `brightness_contrast` — Brightness/contrast jitter

Alpha (contrast) and beta (brightness) adjustments via `cv2.convertScaleAbs`.

- **Intensity → contrast spread** [0.02, 0.25], brightness [0, ±30]

### `pixelation` — Pixelation

Downscale then upscale to produce blocky artifacts.

- **Intensity → scale fraction** [0.2, 0.9] (inverted: higher = more pixelated)
- Random interpolation: NEAREST or LINEAR

### `gradient_illumination` — Gradient illumination

Linear gradient overlay simulating uneven lighting.

- **Intensity → gradient strength** [0.1, 0.6]
- Random direction: horizontal or vertical, either way round

### `morphological` — Morphological operations

Erosion or dilation with a small kernel.

- **Intensity 0.0–0.5 → kernel size 2; 0.5–1.0 → kernel size 3**
- Khmer-aware mode: 70% erode, 30% horizontal dilate
- English mode: 50/50 erode/dilate with a square kernel

### `anisotropic_dilation` — Anisotropic dilation

Directional dilation simulating dot-matrix printer spread.

- **Intensity 0.0–0.5 → kernel size 2; 0.5–1.0 → kernel size 3 or 4**
- Random direction: horizontal or vertical kernel

---

## Verifying augmentations

Render every method at fixed MIN and MAX intensity on clean canvases:

```bash
khocr-gen verify --fonts fonts --output verify_output
```

This produces one PNG per method showing the clean canvas with the method applied at the MIN
intensity (left) and the MAX intensity (right). Restrict to specific methods with `--method`:

```bash
khocr-gen verify --fonts fonts --method blur rotation salt_pepper

# extreme_resize: --min/--max are pixel heights here, not [0, 1]
khocr-gen verify --fonts fonts --method extreme_resize --min 16 --max 800
```

See **[CLI Reference](CLI-Reference#khocr-gen-verify)** for all `verify` options.

## Configuring augmentations

Via CLI, each method has three flags:

```bash
khocr-gen generate --blur-prob 0.5 --blur-min 0.1 --blur-max 0.9
```

Via YAML (flat keys — nested mappings are skipped):

```yaml
blur-prob: 0.5
blur-min: 0.1
blur-max: 0.9
```

See **[Configuration](Configuration)** for the full key list and precedence rules.
