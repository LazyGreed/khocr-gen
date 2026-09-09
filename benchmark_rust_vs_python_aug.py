"""Benchmark: Rust vs pure-Python augmentation kernels (khocr-gen).

Calls the compiled `_rust_accel` native functions and the pure-Python
`khocr_gen.augmentation.AUG_METHODS` fallbacks directly, in the same process,
on identical synthetic inputs -- an apples-to-apples per-call timing
comparison. Not run via CI; ad hoc benchmark for NIG-6.

Usage:
    uv run python benchmark_rust_vs_python_aug.py
"""

from __future__ import annotations

import statistics
import time

import _rust_accel as native
import numpy as np

from khocr_gen.augmentation import AUG_METHODS

N_RUNS = 50
INTENSITY = 0.6

# Representative line-crop sizes seen in the pipeline (grayscale, uint8).
SIZES = [(48, 320), (64, 640)]

_AUG_NAMES = [
    "apply_sauvola",
    "apply_geo_warp",
    "apply_vertical_crop",
    "apply_blur",
    "apply_salt_pepper",
    "apply_background_texture",
    "apply_jpeg_compression",
    "apply_rotation",
    "apply_lowdpi",
    "apply_oversample",
    "apply_perspective",
    "apply_elastic",
    "apply_random_crop",
    "apply_online_blur",
    "apply_online_noise",
    "apply_reverse",
    "apply_brightness_contrast",
    "apply_pixelation",
    "apply_gradient_illumination",
    "apply_morphological",
    "apply_anisotropic_dilation",
]


def _time_fn(fn, img: np.ndarray, n: int) -> float:
    # one untimed warmup call
    try:
        fn(img.copy(), INTENSITY)
    except Exception:
        return float("nan")
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn(img.copy(), INTENSITY)
        times.append(time.perf_counter() - t0)
    return statistics.median(times) * 1000  # ms


def main() -> None:
    rng = np.random.default_rng(0)
    print(f"{'augmentation':<28} {'size':<10} {'python(ms)':>12} {'rust(ms)':>12} {'speedup':>10}")
    print("-" * 78)

    rows = []
    for h, w in SIZES:
        img = rng.integers(0, 255, size=(h, w), dtype=np.uint8)
        for name in _AUG_NAMES:
            short_name = name.removeprefix("apply_")
            py_fn = AUG_METHODS.get(short_name)
            rust_fn = getattr(native, f"{name}_rust", None)
            if py_fn is None or rust_fn is None:
                continue
            py_ms = _time_fn(py_fn, img, N_RUNS)
            rust_ms = _time_fn(rust_fn, img, N_RUNS)
            speedup = py_ms / rust_ms if rust_ms and rust_ms > 0 else float("nan")
            rows.append((name, f"{h}x{w}", py_ms, rust_ms, speedup))
            print(f"{name:<28} {h}x{w:<6} {py_ms:>12.4f} {rust_ms:>12.4f} {speedup:>9.1f}x")

    print()
    valid = [r for r in rows if r[4] == r[4]]  # drop NaN
    if valid:
        avg_speedup = statistics.mean(r[4] for r in valid)
        print(f"Mean speedup across {len(valid)} (aug, size) pairs: {avg_speedup:.1f}x")


if __name__ == "__main__":
    main()
