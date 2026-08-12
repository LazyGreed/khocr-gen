# Augmentation Reference

`khocr-gen` provides 25 augmentation methods in a unified registry.
Each generated image receives **exactly one** augmentation applied to a clean rendered canvas; effects are never stacked.

21 of the 25 methods run through a native Rust extension when available (falling back to
pure Python/OpenCV otherwise) — `distortion`, `albu_noise`, `gradient_illumination`, and
`low_contrast_caption` are the exceptions. See [RUST_ACCELERATION.md](RUST_ACCELERATION.md) for details.

## Architecture

```text
Clean canvas -> pick 1 method (weighted by prob) -> sample intensity ∈ [min, max] -> apply -> output
```

### Selection

From all methods with `prob > 0`, one is chosen with probability proportional to its `prob` weight:

```
P(method_i) = prob_i / Σ prob_j    (for all enabled methods j)
```

### Intensity

Once a method is chosen, its intensity is sampled uniformly from its configured `[min, max]` range (both in [0, 1]).
The method maps this to physical units:

| Method | intensity -> physical |
|--------|---------------------|
| blur | kernel size [3, 15] |
| rotation | degrees [0.5, 8.0] |
| salt_pepper | pixel density [0.001, 0.04] |
| jpeg_compression | quality [95, 25] (inverted) |
| sauvola | k value [0.05, 0.50] |
| geo_warp | corner displacement [0.5, 12] px |
| lowdpi | downsample ratio [0.15, 0.80] |

---

## Augmentation Methods (25 methods)

All methods are applied in isolation; one effect per image, chosen probabilistically from the unified registry.

### `sauvola`: Sauvola Local Threshold Degradation

Simulates degraded binarization artifacts common in scanned documents.

- **Intensity -> k parameter** [0.05, 0.50]
- Uses adaptive window (25 px, capped by image size)
- Blends binary result with original via weighted alpha

### `geo_warp`: Geometric Perspective Warp

4-point perspective distortion simulating camera angle or page curl.

- **Intensity -> corner displacement** [0.5, 12] px
- Background color estimated from image border
- Border filled with estimated background

### `vertical_crop`: Vertical Crop

Crops and pads top or bottom edge, simulating misaligned scanning.

- **Intensity -> crop amount** [1, 8] px
- Crops from foreground region edge
- Pads with estimated background color

### `blur`: Blur (Motion/Median/Gaussian)

Uses Albumentations `OneOf` pipeline (falls back to OpenCV GaussianBlur).

- **Intensity -> kernel size** [3, 15] (odd)
- Random choice: MotionBlur, MedianBlur, or GaussianBlur
- Pure OpenCV fallback if Albumentations unavailable

### `distortion`: Distortion (Optical/Grid/Elastic)

Uses Albumentations `OneOf` pipeline (no-op fallback without Albumentations).

- **Intensity -> distort_limit** [0.05, 0.30]
- Random choice: OpticalDistortion, GridDistortion, or ElasticTransform
- Grid uses 5 steps; Elastic uses 20 sigma

### `albu_noise`: Noise (Gaussian/Multiplicative)

Uses Albumentations `OneOf` pipeline (OpenCV fallback available).

- **Intensity -> std deviation** [0.005, 0.20] normalized units
- Random choice: GaussNoise or MultiplicativeNoise
- Fallback: additive Gaussian noise σ [3, 25]

### `jpeg_compression`: JPEG Compression Artifacts

Encodes and decodes the image at configurable quality levels.

- **Intensity -> JPEG quality** [95, 25] (inverted: higher intensity = lower quality)
- Uses cv2.imencode/imdecode round-trip
- Handles both grayscale and RGB

### `rotation`: Random Rotation

Small-angle rotation with border fill.

- **Intensity -> max degrees** [0.5, 8.0]
- Direction: random clockwise or counter-clockwise
- Border filled with estimated background color

### `salt_pepper`: Salt-and-Pepper Noise

Impulse noise: random white (salt) and black (pepper) pixels.

- **Intensity -> pixel density** [0.001, 0.04]
- Equal distribution of salt and pepper
- Works on both grayscale and RGB

### `background_texture`: Background Texture Overlay

Procedural paper-like texture with three modes:

1. **Fine grain**: per-pixel Gaussian noise
2. **Coarse blotches**: low-resolution noise upscaled and blurred
3. **Streaks**: horizontal line artifacts (scanner streaks)

- **Intensity -> blend alpha** [0.05, 0.30]
- Texture suppressed over dark ink regions (preserves text legibility)

### `lowdpi`: Low-DPI Simulation

Downscale-then-upscale using NEAREST for downsample and LANCZOS4 for upsample.

- **Intensity -> downsample ratio** [0.15, 0.80] (inverted: higher = smaller = lower DPI)
- Minimum output dimension: 2 px

### `oversample`: Oversample Rendering

Post-hoc sharpening filter (the rendering-mode oversample is handled in
the renderer, not here).

- **Intensity -> sharpen strength** [1.0, 1.5]
- Uses a 3×3 unsharp mask kernel

### `low_contrast_caption`: Low-Contrast Small Caption Text

Simulates faded, small-point captions/footnotes common in scanned documents:
dynamic range compresses toward mid-gray and fine stroke detail softens as if
the text were rendered at a small point size.

- **Intensity -> contrast compression** [0.15, 0.65]
- **Intensity -> downscale ratio** [0.85, 0.45] (inverted: higher intensity = smaller = softer)
- Compression blends pixel values toward `0.6 × background + 0.4 × neutral gray`
- Detail loss via `INTER_AREA` downscale followed by `INTER_LINEAR` upscale

---

## Training-time Augmentations

These methods simulate augmentations typically applied during OCR training.
They are disabled by default (`prob: 0.0`) but can be enabled to make generated data more closely match training-time conditions.

### `perspective`: Online Perspective Warp

Mild perspective distortion via OpenCV `getPerspectiveTransform`.

- **Intensity -> max displacement fraction** [0.02, 0.12] of image size
- Border filled with gray (128)

### `elastic`: Online Elastic Distortion

Displacement-field-based elastic deformation.

- **Intensity -> displacement sigma** [0.02×size, 0.12×size]
- Coarse grid scaled to full resolution

### `random_crop`: Online Random Height Crop

Crop top or bottom and resize back to original dimensions.

- **Intensity -> crop fraction** [0.01, 0.08] of height

### `online_blur`: Online Blur

Gaussian or Motion blur.

- **Intensity -> kernel size** [3, 7] (odd)
- 50% chance of MotionBlur if Albumentations available

### `online_noise`: Online Gaussian Noise

Additive Gaussian noise.

- **Intensity -> noise sigma** [3, 30]

### `hsv`: HSV Color Jitter

Saturation and value adjustments (grayscale images pass through unchanged).

- **Intensity -> jitter factor** [0.60, 0.95]
- Independent random multiplier for S and V channels

### `reverse`: Color Reversal

Inverts pixel values (dark <-> light). Common for handling negative/white-on-black text.

- **Intensity ignored**: binary on/off effect
- `255 - pixel` for every pixel

### `brightness_contrast`: Brightness/Contrast Jitter

Alpha (contrast) and beta (brightness) adjustments via `cv2.convertScaleAbs`.

- **Intensity -> contrast spread** [0.02, 0.25], brightness [0, ±30]

### `pixelation`: Pixelation

Downscale then upscale to produce blocky/pixelated artifacts.

- **Intensity -> scale fraction** [0.2, 0.9] (inverted: higher = more pixelated)
- Random interpolation: NEAREST or LINEAR

### `gradient_illumination`: Gradient Illumination

Linear gradient overlay simulating uneven lighting.

- **Intensity -> gradient strength** [0.1, 0.6]
- Random direction: horizontal or vertical, left-to-right or right-to-left

### `morphological`: Morphological Operations

Erosion or dilation with a small kernel.

- **Intensity 0.0–0.5 -> kernel size 2**; **0.5–1.0 -> kernel size 3**
- Khmer-aware mode: 70% erode, 30% horizontal dilate
- English mode: 50/50 erode/dilate with square kernel

### `anisotropic_dilation`: Anisotropic Dilation

Directional dilation simulating dot-matrix printer spread.

- **Intensity 0.0–0.5 -> kernel size 2**; **0.5–1.0 -> kernel size 3 or 4**
- Random direction: horizontal or vertical kernel

---

## Verify Command

To see every method at min and max intensity on a clean canvas:

```bash
khocr-gen verify --fonts fonts --output verify_output
```

This produces one PNG per method showing the clean canvas with the method applied at intensity 0.0 (left half) and 1.0 (right half).
