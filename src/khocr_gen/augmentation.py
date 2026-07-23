"""Augmentation methods (unified registry).

Every augmentation method receives a clean canvas (no prior augmentation applied)
and applies exactly one effect based on its sampled intensity.

All methods follow the signature:

    apply_<name>(img: np.ndarray, intensity: float, **kwargs) -> np.ndarray

where *img* is a HxW or HxWxC uint8 numpy array and *intensity* is in [0, 1].
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

if TYPE_CHECKING:
    from pathlib import Path

try:
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    import albumentations as A

    HAS_ALBUMENTATIONS = True
except ImportError:
    HAS_ALBUMENTATIONS = False

# ── Constants ─────────────────────────────────────────────────────────────────

_AUTO_PARALLEL_MIN_SAMPLES = 2_048
_DEFAULT_RENDER_CHUNK_SIZE = 64
_MAX_RENDER_CHUNK_SIZE = 256
_MAX_ERROR_MESSAGES = 10


# ── Helper ────────────────────────────────────────────────────────────────────


def _normalize_odd_kernel_limit(value: int, minimum: int = 3) -> int:
    limit = max(int(minimum), int(value))
    if limit % 2 == 0:
        limit += 1
    return limit


# ── Output helpers ────────────────────────────────────────────────────────────


def write_output_image(
    path: Path,
    img: np.ndarray,
    fmt: str = "jpg",
    jpeg_quality: int = 90,
) -> bool:
    """Write a numpy image to disk with format-aware encoding.

    Handles RGB->BGR conversion for OpenCV and sets appropriate params for JPEG quality, PNG compression, and TIFF output.
    """
    output = img
    if img.ndim == 3 and img.shape[2] == 3:
        output = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    params: list[int] = []
    if fmt in ("jpg", "jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, max(0, min(100, jpeg_quality))]
    elif fmt == "png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
    elif fmt in ("tiff", "tif"):
        params = [cv2.IMWRITE_TIFF_XDPI, 300, cv2.IMWRITE_TIFF_YDPI, 300]

    ext = f".{fmt}" if not fmt.startswith(".") else fmt
    out_path = path if path.suffix else path.with_suffix(ext)
    return cv2.imwrite(str(out_path), output, params)


# ──────────────────────────────────────────────────────────────────────────────
# Augmentation method implementations
# ──────────────────────────────────────────────────────────────────────────────


def _estimate_bg(img: np.ndarray) -> int:
    """Estimate background color from image border."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    border = np.concatenate((gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]))
    return int(np.median(border))


# ── Sauvola ───────────────────────────────────────────────────────────────────


def apply_sauvola(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Sauvola local-threshold degradation.

    intensity -> k value in [0.05, 0.50]
    """
    h, w = img.shape[:2]
    if h < 3 or w < 3:
        return img

    window = 25
    max_window = min(h, w)
    if max_window % 2 == 0:
        max_window -= 1
    window = min(window, max_window)
    if window % 2 == 0:
        window -= 1
    window = max(3, window)

    k = 0.05 + intensity * 0.45  # [0.05, 0.50]

    img_f = img.astype(np.float32)
    mean = cv2.boxFilter(img_f, ddepth=-1, ksize=(window, window))
    sq_mean = cv2.boxFilter(img_f * img_f, ddepth=-1, ksize=(window, window))
    var = np.maximum(sq_mean - mean * mean, 0.0)
    std = np.sqrt(var)

    r = 128.0
    threshold = mean * (1.0 + k * ((std / r) - 1.0))
    binary = np.where(img_f > threshold, 255.0, 0.0).astype(np.uint8)

    alpha = 0.45 + intensity * 0.35
    degraded = cv2.addWeighted(img, 1.0 - alpha, binary, alpha, 0.0)
    return degraded


# ── Geometric warp ────────────────────────────────────────────────────────────


def apply_geo_warp(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """4-point perspective warp. intensity -> radius [0.5, 12] pixels."""
    h, w = img.shape[:2]
    if h < 8 or w < 8:
        return img

    radius = 0.5 + intensity * 11.5
    bg = _estimate_bg(img)

    src = np.array(
        [[0.0, 0.0], [float(w - 1), 0.0], [0.0, float(h - 1)], [float(w - 1), float(h - 1)]],
        dtype=np.float32,
    )
    dst = src.copy()
    for i in range(4):
        dx = random.uniform(-radius, radius)
        dy = random.uniform(-radius, radius)
        dst[i] = [
            float(np.clip(dst[i, 0] + dx, 0, w - 1)),
            float(np.clip(dst[i, 1] + dy, 0, h - 1)),
        ]

    mat = cv2.getPerspectiveTransform(src, dst)
    border_value = (float(bg),)
    warped = cv2.warpPerspective(
        img,
        mat,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    return warped


# ── Vertical crop ─────────────────────────────────────────────────────────────


def apply_vertical_crop(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Crop top/bottom edge and pad back. intensity -> crop [1, 8] px."""
    h, w = img.shape[:2]
    if h < 4:
        return img

    crop_px = max(1, int(1 + intensity * 7))
    crop_px = min(crop_px, h - 1)
    bg = _estimate_bg(img)

    fg_threshold = max(0, int(bg) - 20)
    fg_rows = np.where(np.any(img < fg_threshold, axis=1))[0]

    if random.random() < 0.5:
        shift_px = min(h - 1, crop_px + int(fg_rows[0]) if fg_rows.size > 0 else crop_px)
        pad = np.full((shift_px, w), int(bg), dtype=img.dtype)
        cropped = img[shift_px:, :]
        return np.vstack((cropped, pad))
    else:
        bottom_margin = int((h - 1) - fg_rows[-1]) if fg_rows.size > 0 else 0
        shift_px = min(h - 1, crop_px + bottom_margin)
        pad = np.full((shift_px, w), int(bg), dtype=img.dtype)
        cropped = img[:-shift_px, :]
        return np.vstack((pad, cropped))


# ── Blur ──────────────────────────────────────────────────────────────────────


def apply_blur(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Blur via Albumentations OneOf(MotionBlur|MedianBlur|GaussianBlur).
    intensity -> kernel size [3, 15].
    """
    if not HAS_ALBUMENTATIONS:
        # Pure OpenCV fallback
        kernel = _normalize_odd_kernel_limit(int(3 + intensity * 12))
        return cv2.GaussianBlur(img, (kernel, kernel), 0)

    limit = _normalize_odd_kernel_limit(int(3 + intensity * 12))
    try:
        pipeline = A.OneOf(
            [
                A.MotionBlur(blur_limit=limit, p=1.0),
                A.MedianBlur(blur_limit=limit, p=1.0),
                A.Blur(blur_limit=limit, p=1.0),
            ],
            p=1.0,
        )
        return pipeline(image=img)["image"]
    except Exception:
        return img


# ── Distortion ────────────────────────────────────────────────────────────────


def apply_distortion(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Distortion via Albumentations OneOf(Optical|Grid|Elastic).
    intensity -> distort_limit [0.05, 0.30].
    """
    if not HAS_ALBUMENTATIONS:
        return img

    limit = 0.05 + intensity * 0.25
    try:
        pipeline = A.OneOf(
            [
                A.OpticalDistortion(distort_limit=limit, p=1.0),
                A.GridDistortion(num_steps=5, distort_limit=limit, p=1.0),
                A.ElasticTransform(alpha=float(1 + intensity * 3), sigma=20, p=1.0),
            ],
            p=1.0,
        )
        return pipeline(image=img)["image"]
    except Exception:
        return img


# ── Noise ─────────────────────────────────────────────────────────────────────


def apply_albu_noise(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Noise via Albumentations.
    intensity -> std [0.005, 0.20] in [0,1] units.
    """
    if not HAS_ALBUMENTATIONS:
        sigma = 3 + intensity * 22
        noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
        return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    std_hi = 0.005 + intensity * 0.195
    std_lo = std_hi * 0.15
    try:
        pipeline = A.OneOf(
            [
                A.GaussNoise(std_range=(std_lo, std_hi), p=1.0),
                A.MultiplicativeNoise(
                    multiplier=(1.0 - intensity * 0.2, 1.0 + intensity * 0.2),
                    elementwise=True,
                    p=1.0,
                ),
            ],
            p=1.0,
        )
        return pipeline(image=img)["image"]
    except Exception:
        return img


# ── JPEG compression ──────────────────────────────────────────────────────────


def apply_jpeg_compression(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """JPEG compression artifacts.
    intensity -> quality [95, 25] (inverted).
    """
    quality = max(5, int(95 - intensity * 70))
    encode_arr = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", encode_arr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return img
    flag = cv2.IMREAD_GRAYSCALE if img.ndim == 2 else cv2.IMREAD_COLOR
    decoded = cv2.imdecode(buf, flag)
    if decoded is None:
        return img
    if img.ndim == 3:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    return decoded


# ── Rotation ──────────────────────────────────────────────────────────────────


def apply_rotation(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Random rotation.
    intensity -> max degrees [0.5, 8.0].
    """
    angle = random.uniform(-(0.5 + intensity * 7.5), 0.5 + intensity * 7.5)
    if abs(angle) < 0.01:
        return img

    h, w = img.shape[:2]
    bg = _estimate_bg(img)
    cx, cy = w / 2.0, h / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    border_val: tuple[float, ...] = (float(bg),) if img.ndim == 2 else (float(bg),) * img.shape[2]
    rotated = cv2.warpAffine(
        img,
        M,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_val,
    )
    return rotated


# ── Salt-and-pepper noise ─────────────────────────────────────────────────────


def apply_salt_pepper(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Salt-and-pepper noise.
    intensity -> density [0.001, 0.04].
    """
    density = 0.001 + intensity * 0.039
    out = img.copy()
    total = img.size
    n_noise = max(1, int(total * density))

    if img.ndim == 2:
        # Salt (white)
        rows = np.random.randint(0, img.shape[0], n_noise // 2)
        cols = np.random.randint(0, img.shape[1], n_noise // 2)
        out[rows, cols] = 255
        # Pepper (black)
        rows = np.random.randint(0, img.shape[0], n_noise // 2)
        cols = np.random.randint(0, img.shape[1], n_noise // 2)
        out[rows, cols] = 0
    else:
        h, w = img.shape[:2]
        rows = np.random.randint(0, h, n_noise // 2)
        cols = np.random.randint(0, w, n_noise // 2)
        out[rows, cols] = 255
        rows = np.random.randint(0, h, n_noise // 2)
        cols = np.random.randint(0, w, n_noise // 2)
        out[rows, cols] = 0
    return out


# ── Background texture ────────────────────────────────────────────────────────


def apply_background_texture(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Procedural paper texture overlay.
    intensity -> blend alpha [0.05, 0.30].
    """
    h, w = img.shape[:2]
    bg = _estimate_bg(img)
    out = img.astype(np.float32)

    mode = random.randint(0, 2)
    if mode == 0:
        sigma = 1.0 + intensity * 10.0
        grain = np.random.normal(0.0, sigma, (h, w)).astype(np.float32)
        alpha = 0.05 + intensity * 0.25
        out = out + grain * alpha
    elif mode == 1:
        coarse = np.random.normal(0.0, 20.0, (max(1, h // 4), max(1, w // 4))).astype(np.float32)
        coarse = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_LINEAR)
        coarse = cv2.GaussianBlur(coarse, (0, 0), sigmaX=max(1.0, w * 0.05))
        alpha = 0.03 + intensity * 0.20
        out = out + coarse * alpha
    else:
        if out.ndim == 2:
            streak_count = random.randint(3, 12)
            for _ in range(streak_count):
                y = random.randint(0, h - 1)
                intensity_streak = random.uniform(-12.0, 12.0)
                angle = random.uniform(-0.05, 0.05)
                for dy in range(random.randint(1, 2)):
                    row = y + dy
                    if row >= h:
                        break
                    xs = np.arange(w, dtype=np.float32)
                    ys = np.clip((row + xs * angle).astype(np.int32), 0, h - 1)
                    out[ys, np.arange(w)] += intensity_streak

    # Suppress texture over dark ink
    if img.ndim == 2:
        bg_f = float(bg)
        ink_strength = np.clip((bg_f - img.astype(np.float32)) / max(1.0, bg_f), 0.0, 1.0)
        out = out * (1.0 - ink_strength) + img.astype(np.float32) * ink_strength

    return np.clip(out, 0.0, 255.0).astype(np.uint8)


# ── Low DPI ───────────────────────────────────────────────────────────────────


def apply_lowdpi(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Simulate low-DPI rendering via downscale-then-upscale.
    intensity -> downsample ratio [0.15, 0.80].
    """
    h, w = img.shape[:2]
    ratio = 0.80 - intensity * 0.65  # [0.15, 0.80]
    small_h = max(2, int(h * ratio))
    small_w = max(2, int(w * ratio))
    small = cv2.resize(img, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LANCZOS4)


# ── Oversample ────────────────────────────────────────────────────────────────


def apply_oversample(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Oversample rendering.
    intensity -> scale factor [1.5, 4.0] then downscale.
    Requires *font* kwarg for rendering hint; this is a rendering-mode augmentation.
    """
    # Oversample is handled differently — it's a rendering mode, not post-hoc.
    # When called post-hoc, just do a mild sharpen.
    alpha = 1.0 + intensity * 0.5
    kernel = np.array([[-0.5, -0.5, -0.5], [-0.5, 5.0 * alpha, -0.5], [-0.5, -0.5, -0.5]])
    return cv2.filter2D(img, -1, kernel)


# ── Perspective warp (online) ─────────────────────────────────────────────────


def apply_perspective(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Mild perspective warp.
    intensity -> max displacement fraction [0.02, 0.12].
    """
    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    d = min(h, w) * (0.02 + intensity * 0.10)
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array(
        [
            [random.uniform(0, d), random.uniform(0, d)],
            [w - random.uniform(0, d), random.uniform(0, d)],
            [w - random.uniform(0, d), h - random.uniform(0, d)],
            [random.uniform(0, d), h - random.uniform(0, d)],
        ],
        dtype=np.float32,
    )
    m = cv2.getPerspectiveTransform(src, dst)
    border_val: tuple[int, int, int] | tuple[int] = (128, 128, 128) if img.ndim == 3 else (128,)
    return cv2.warpPerspective(img, m, (w, h), borderValue=border_val)


# ── Elastic distortion ────────────────────────────────────────────────────────


def apply_elastic(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Elastic distortion via displacement field.
    intensity -> sigma [0.02*size, 0.12*size].
    """
    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    sigma = min(h, w) * (0.02 + intensity * 0.10)
    scale = 8
    ch, cw = max(2, h // scale), max(2, w // scale)
    dx = (np.random.rand(ch, cw).astype(np.float32) * 2 - 1) * sigma
    dy = (np.random.rand(ch, cw).astype(np.float32) * 2 - 1) * sigma
    dx = cv2.resize(dx, (w, h), interpolation=cv2.INTER_LINEAR)
    dy = cv2.resize(dy, (w, h), interpolation=cv2.INTER_LINEAR)
    x_coords, y_coords = np.meshgrid(np.arange(w), np.arange(h))
    map_x = np.clip(x_coords + dx, 0, w - 1).astype(np.float32)
    map_y = np.clip(y_coords + dy, 0, h - 1).astype(np.float32)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR)


# ── Random height crop ────────────────────────────────────────────────────────


def apply_random_crop(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Crop up to a fraction of height from top/bottom, resize back.
    intensity -> crop fraction [0.01, 0.08].
    """
    h, w = img.shape[:2]
    if h < 8:
        return img

    max_cut = max(1, int(h * (0.01 + intensity * 0.07)))
    cut = random.randint(1, max_cut)
    cropped = img[cut:, :] if random.random() < 0.5 else img[: h - cut, :]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)


# ── Online blur ───────────────────────────────────────────────────────────────


def apply_online_blur(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Gaussian or Motion blur.
    intensity -> kernel size [3, 7].
    """
    kernel = _normalize_odd_kernel_limit(int(3 + intensity * 4))

    if HAS_ALBUMENTATIONS and random.random() < 0.5:
        try:
            result = A.MotionBlur(blur_limit=kernel, p=1.0)(image=img)["image"]
            return result
        except Exception:
            pass

    return cv2.GaussianBlur(img, (kernel, kernel), 0)


# ── Online noise ──────────────────────────────────────────────────────────────


def apply_online_noise(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Additive Gaussian noise.
    intensity -> sigma [3, 30].
    """
    sigma = 3.0 + intensity * 27.0
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


# ── HSV color jitter ──────────────────────────────────────────────────────────


def apply_hsv(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """HSV saturation/value jitter.
    intensity -> shift factor [0.05, 0.40].
    Grayscale images pass through unchanged.
    """
    if img.ndim != 3:
        return img

    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV).astype(np.float32)
    factor = 1.0 - intensity * 0.40  # [0.60, 0.95]
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * random.uniform(factor, 2.0 - factor), 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * random.uniform(factor, 2.0 - factor), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)


# ── Color reversal ────────────────────────────────────────────────────────────


def apply_reverse(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Color reversal (dark <-> light).
    intensity is ignored (binary on/off effect).
    """
    return (255 - img).astype(np.uint8)


# ── Brightness/contrast ───────────────────────────────────────────────────────


def apply_brightness_contrast(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Brightness/contrast jitter.
    intensity -> adjustment range [0.02, 0.25].
    """
    spread = 0.02 + intensity * 0.23
    alpha = random.uniform(1.0 - spread, 1.0 + spread)  # Contrast
    beta = int(random.uniform(-30 * intensity, 30 * intensity))  # Brightness
    return cv2.convertScaleAbs(img, alpha=alpha, beta=beta)


# ── Pixelation ────────────────────────────────────────────────────────────────


def apply_pixelation(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Downscale-then-upscale pixelation.
    intensity -> scale fraction [0.2, 0.9].
    """
    h, w = img.shape[:2]
    scale = 0.9 - intensity * 0.7  # [0.2, 0.9]
    small_w = max(1, int(w * scale))
    small_h = max(1, int(h * scale))
    interp = random.choice([cv2.INTER_NEAREST, cv2.INTER_LINEAR])
    small = cv2.resize(img, (small_w, small_h), interpolation=interp)
    return cv2.resize(small, (w, h), interpolation=interp)


# ── Gradient illumination ─────────────────────────────────────────────────────


def apply_gradient_illumination(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Gradient illumination overlay.
    intensity -> gradient strength [0.1, 0.6].
    """
    h, w = img.shape[:2]
    strength = 0.1 + intensity * 0.5

    if random.random() < 0.5:
        gradient = np.linspace(1.0 - strength, 1.0, w)
        if random.random() < 0.5:
            gradient = gradient[::-1]
        gradient = gradient[np.newaxis, :]
    else:
        gradient = np.linspace(1.0 - strength, 1.0, h)
        if random.random() < 0.5:
            gradient = gradient[::-1]
        gradient = gradient[:, np.newaxis]

    return np.clip(img.astype(np.float32) * gradient, 0, 255).astype(np.uint8)


# ── Morphological ─────────────────────────────────────────────────────────────


def apply_morphological(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Morphological erode/dilate.
    intensity -> kernel size [2, 3].
    """
    has_khmer = kwargs.get("has_khmer", False)
    kernel_size = 2 if intensity < 0.5 else 3

    if has_khmer:
        if random.random() < 0.7:
            kernel = np.ones((kernel_size, kernel_size), np.uint8)
            return cv2.erode(img, kernel, iterations=1)
        else:
            kernel = np.ones((1, kernel_size), np.uint8)
            return cv2.dilate(img, kernel, iterations=1)
    else:
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        if random.random() < 0.5:
            return cv2.erode(img, kernel, iterations=1)
        else:
            return cv2.dilate(img, kernel, iterations=1)


# ── Anisotropic dilation ──────────────────────────────────────────────────────


def apply_anisotropic_dilation(img: np.ndarray, intensity: float, **kwargs: Any) -> np.ndarray:
    """Anisotropic dilation (dot-matrix spread).
    intensity -> kernel size [2, 4].
    """
    kernel_size = 2 if intensity < 0.5 else random.choice([3, 4])
    if random.random() < 0.5:
        kernel = np.ones((1, kernel_size), np.uint8)
    else:
        kernel = np.ones((kernel_size, 1), np.uint8)
    return cv2.dilate(img, kernel, iterations=1)


# ─── Registry ─────────────────────────────────────────────────────────────────

# Methods that produce better results when operating on RGB input rather than grayscale.
_RGB_PREFERRED_METHODS: frozenset[str] = frozenset(
    {
        "hsv",
        "reverse",
        "brightness_contrast",
        "gradient_illumination",
    }
)

# Unified registry: all 24 augmentation methods.
AUG_METHODS: dict[str, Any] = {
    # Generator-side (scanner/camera degradation simulation)
    "sauvola": apply_sauvola,
    "geo_warp": apply_geo_warp,
    "vertical_crop": apply_vertical_crop,
    "blur": apply_blur,
    "distortion": apply_distortion,
    "albu_noise": apply_albu_noise,
    "jpeg_compression": apply_jpeg_compression,
    "rotation": apply_rotation,
    "salt_pepper": apply_salt_pepper,
    "background_texture": apply_background_texture,
    "lowdpi": apply_lowdpi,
    "oversample": apply_oversample,
    # Training-time simulation
    "perspective": apply_perspective,
    "elastic": apply_elastic,
    "random_crop": apply_random_crop,
    "online_blur": apply_online_blur,
    "online_noise": apply_online_noise,
    "hsv": apply_hsv,
    "reverse": apply_reverse,
    "brightness_contrast": apply_brightness_contrast,
    "pixelation": apply_pixelation,
    "gradient_illumination": apply_gradient_illumination,
    "morphological": apply_morphological,
    "anisotropic_dilation": apply_anisotropic_dilation,
}

# ── Replace with Rust-accelerated implementations when available ─────────────

_RUST_METHODS = [
    "sauvola",
    "geo_warp",
    "vertical_crop",
    "blur",
    "jpeg_compression",
    "rotation",
    "salt_pepper",
    "background_texture",
    "lowdpi",
    "oversample",
    "perspective",
    "elastic",
    "random_crop",
    "online_blur",
    "online_noise",
    "hsv",
    "reverse",
    "brightness_contrast",
    "pixelation",
    # NOTE: gradient_illumination excluded;
    # Rust is grayscale-only but the rendering pipeline passes RGB for _RGB_PREFERRED_METHODS members.
    "morphological",
    "anisotropic_dilation",
]

try:
    from . import _rust_accel as _ra  # type: ignore[import-untyped,assignment]

    if _ra.HAS_RUST_ACCEL:
        _replaced = 0
        for _method in _RUST_METHODS:
            _rust_fn = getattr(_ra, f"apply_{_method}", None)
            if _rust_fn is not None and _method in AUG_METHODS:
                AUG_METHODS[_method] = _rust_fn
                _replaced += 1
        if _replaced:
            import logging

            _LOGGER = logging.getLogger("khocr_gen.augmentation")
            _LOGGER.info(
                "Rust acceleration: %d/%d augmentation methods using native code",
                _replaced,
                len(_RUST_METHODS),
            )
except ImportError:
    pass

del _RUST_METHODS

# Backward-compatibility alias.
OFFLINE_AUG_METHODS = AUG_METHODS
