"""`khocr-gen verify` - visual verification of augmentation methods.

Renders each augmentation method at MIN and MAX intensity on a clean canvas, producing side-by-side comparison images.
Every augmentation is applied in isolation, no stacking or combining of effects.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from .augmentation import _RGB_PREFERRED_METHODS, AUG_METHODS
from .config import GenerationConfig
from .fonts import FontManager
from .rendering import ImageRenderer

if TYPE_CHECKING:
    import argparse

_log = logging.getLogger("khocr_gen.verify")


# ── Sample texts ──────────────────────────────────────────────────────────

_FALLBACK_TEXTS = [
    "Hello World",
    "Khocr Gen verification",
    "ប្រព័ន្ធ OCR",
    "Invoice #1234",
    "Amount: $1,500.00",
    "Khmer: ភាសាខ្មែរ",
    "Mixed: English & ខ្មែរ",
    "Account 9876-5432-1098",
]


def _load_sample_texts(corpus_path: str | None, count: int, seed: int = 42) -> list[str]:
    """Load *count* sample lines from the corpus, falling back to built-ins."""
    texts: list[str] = []
    if corpus_path and Path(corpus_path).exists():
        rng = random.Random(seed)
        try:
            with open(corpus_path, encoding="utf-8") as fh:
                lines = [ln.strip() for ln in fh if ln.strip()]
            if lines:
                texts = rng.sample(lines, min(count, len(lines)))
        except OSError as exc:
            _log.warning("Could not read corpus %s: %s", corpus_path, exc)

    while len(texts) < count:
        texts.append(_FALLBACK_TEXTS[len(texts) % len(_FALLBACK_TEXTS)])

    return texts[:count]


# ── Grid helpers ──────────────────────────────────────────────────────────


def _stack_images(images: list[np.ndarray], target_w: int) -> np.ndarray:
    """Resize images to *target_w* preserving aspect ratio and vstack them."""
    resized: list[np.ndarray] = []
    for img in images:
        h, w = img.shape[:2]
        if w != target_w:
            new_h = max(1, int(h * target_w / w))
            img = cv2.resize(img, (target_w, new_h))
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        resized.append(img.astype(np.uint8))
    return np.vstack(resized) if resized else np.zeros((1, target_w, 3), dtype=np.uint8)


def _make_comparison_grid(
    low_grid: np.ndarray, high_grid: np.ndarray, method_name: str, image_width: int
) -> np.ndarray:
    """Stack low and high grids side by side with labels."""
    label_h = 28
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.55
    thickness = 1

    def _add_label(img: np.ndarray, text: str) -> np.ndarray:
        banner = np.full((label_h, img.shape[1], 3), 40, dtype=np.uint8)
        cv2.putText(banner, text, (6, 20), font, font_scale, (220, 220, 220), thickness)
        return np.vstack([banner, img])

    low_labeled = _add_label(low_grid, f"{method_name}  [MIN]")
    high_labeled = _add_label(high_grid, f"{method_name}  [MAX]")

    h_max = max(low_labeled.shape[0], high_labeled.shape[0])

    def _pad_h(img: np.ndarray, target_h: int) -> np.ndarray:
        diff = target_h - img.shape[0]
        if diff <= 0:
            return img
        pad = np.full((diff, img.shape[1], 3), 20, dtype=np.uint8)
        return np.vstack([img, pad])

    low_labeled = _pad_h(low_labeled, h_max)
    high_labeled = _pad_h(high_labeled, h_max)

    divider = np.full((h_max, 4, 3), 80, dtype=np.uint8)
    return np.hstack([low_labeled, divider, high_labeled])


# ── Main verification logic ───────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Entry point called by cli.py."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fonts_dir = args.fonts
    image_height: int = args.height
    image_width: int | None = args.width
    count: int = max(1, args.count)
    show: bool = args.show
    corpus_path: str | None = args.corpus
    repeats: int = max(1, args.repeats)

    # Build method list — all registered methods with min/max intensities
    all_methods: dict[str, Any] = dict(AUG_METHODS)

    requested = set(args.method) if args.method else None
    method_names = [name for name in all_methods if requested is None or name in requested]

    if not method_names:
        print(f"No matching augmentation methods for: {args.method}")
        return 1

    texts = _load_sample_texts(corpus_path, count)
    print(f"\nVerification samples : {count}")
    print(f"Fonts directory      : {fonts_dir}")
    print(f"Output directory     : {output_dir}")
    print(f"Methods              : {', '.join(method_names)}")
    print()

    # Build a minimal config and renderer
    cfg = GenerationConfig(
        fonts_dir=fonts_dir,
        image_height=image_height,
        image_width=image_width,
    )
    font_manager = FontManager(language="mixed", fonts_dir=fonts_dir)
    renderer = ImageRenderer(font_manager, cfg)

    saved: list[Path] = []

    for method_name in method_names:
        aug_fn = all_methods[method_name]
        print(f"  ── {method_name} ──")

        # Render clean base images (one per text, repeated for variety)
        clean_images: list[np.ndarray] = []
        for i, text in enumerate(texts):
            for _ in range(repeats):
                random.seed(42 + i)
                np.random.seed(42 + i)
                try:
                    img = renderer.render(text, augment=False)
                    if img is not None:
                        clean_images.append(img)
                except Exception as exc:
                    _log.debug("Render failed for %r: %s", text, exc)

        if not clean_images:
            print("    WARNING: no images rendered; skipping.")
            continue

        # Apply MIN intensity
        print("    Applying MIN intensity ...", end="", flush=True)
        min_images: list[np.ndarray] = []
        for img in clean_images:
            try:
                # For HSV and reverse methods, convert to RGB first
                if method_name in _RGB_PREFERRED_METHODS:
                    rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB) if img.ndim == 2 else img.copy()
                    result = aug_fn(rgb, 0.0)
                    if result is not None and result.ndim == 3:
                        result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
                else:
                    result = aug_fn(img.copy(), 0.0)
                if result is not None:
                    min_images.append(result)
            except Exception as exc:
                _log.debug("MIN aug failed: %s", exc)

        # Apply MAX intensity
        print(" MAX intensity ...", end="", flush=True)
        max_images: list[np.ndarray] = []
        for img in clean_images:
            try:
                if method_name in _RGB_PREFERRED_METHODS:
                    rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB) if img.ndim == 2 else img.copy()
                    result = aug_fn(rgb, 1.0)
                    if result is not None and result.ndim == 3:
                        result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
                else:
                    result = aug_fn(img.copy(), 1.0)
                if result is not None:
                    max_images.append(result)
            except Exception as exc:
                _log.debug("MAX aug failed: %s", exc)
        print(" done")

        if not min_images or not max_images:
            print("    WARNING: failed to apply augmentation; skipping.")
            continue

        target_w = image_width or max(
            max(img.shape[1] for img in min_images),
            max(img.shape[1] for img in max_images),
        )

        low_grid = _stack_images(min_images, target_w)
        high_grid = _stack_images(max_images, target_w)

        comparison = _make_comparison_grid(low_grid, high_grid, method_name, target_w)

        out_path = output_dir / f"verify_{method_name}.png"
        ok = cv2.imwrite(str(out_path), cv2.cvtColor(comparison, cv2.COLOR_RGB2BGR))
        if ok:
            print(f"    Saved -> {out_path}")
            saved.append(out_path)
        else:
            print(f"    WARNING: Failed to write {out_path}")

        if show:
            cv2.imshow(f"verify: {method_name}", cv2.cvtColor(comparison, cv2.COLOR_RGB2BGR))
            print("    Press any key to continue...")
            cv2.waitKey(0)
            cv2.destroyWindow(f"verify: {method_name}")

    if show:
        cv2.destroyAllWindows()

    print(f"\nVerification complete. {len(saved)} image(s) saved to {output_dir}\n")
    return 0


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register all verify sub-command arguments onto *parser*."""

    all_names = sorted(AUG_METHODS)

    parser.add_argument("--fonts", default="fonts/", metavar="DIR", help="Root fonts directory")
    parser.add_argument(
        "--corpus", default=None, metavar="FILE", help="Optional corpus file for sample texts"
    )
    parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        default="verify_output",
        metavar="DIR",
        help="Directory for comparison PNG images",
    )
    parser.add_argument(
        "--height", type=int, default=48, metavar="PX", help="Image height in pixels"
    )
    parser.add_argument(
        "--width", type=int, default=None, metavar="PX", help="Fixed image width; omit for variable"
    )
    parser.add_argument(
        "--count", type=int, default=6, metavar="N", help="Number of sample texts per method"
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
        metavar="N",
        help="Augmentation repeats per text for variety",
    )
    parser.add_argument(
        "--method",
        nargs="+",
        default=None,
        metavar="NAME",
        choices=all_names,
        help=f"Restrict to specific methods. Available: {', '.join(all_names)}",
    )
    parser.add_argument("--show", action="store_true", help="Display each comparison interactively")
