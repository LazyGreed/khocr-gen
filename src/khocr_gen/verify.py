"""`khocr-gen verify` - visual verification of augmentation methods.

Renders each augmentation method at two fixed intensities on a clean canvas,
producing side-by-side comparison images. The two intensities default to 0.0
(MIN) and 1.0 (MAX) but are settable via ``--min`` / ``--max``; each column uses
exactly that intensity rather than a value sampled at random from the range.
The RNG is reseeded per image before each method runs so pure-Python methods
reproduce exactly across runs (Rust-accelerated methods use their own thread RNG
and still vary run to run). Every augmentation is applied in isolation, no
stacking or combining of effects.

Each individual `text_deco_*` (bold, italic, underline, color, subscript,
superscript) and `text_effect_*` (background, echo, glitch, ...) probability
is also verifiable the same way, one at a time: MIN/MAX pin just that one
probability to the fixed intensity (all others at 0) and re-render, rather
than applying an AUG_METHODS function to a clean canvas.

`extreme_resize` is verified like any other AUG_METHODS entry, but its
MIN/MAX columns are pixel heights (default 8/1920, its configured default
range) rather than [0, 1] fractions -- pass ``--method extreme_resize --min
16 --max 800`` to check a specific range.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from .augmentation import _RGB_PREFERRED_METHODS, AUG_METHODS
from .config import TEXT_EFFECT_NAMES, GenerationConfig, TextDecorationConfig, TextEffectConfig
from .fonts import FontManager
from .rendering import ImageRenderer

if TYPE_CHECKING:
    import argparse

_log = logging.getLogger("khocr_gen.verify")

# Rendering-time decorations/effects, not post-hoc augmentation functions --
# each is verified by re-rendering with exactly one text_deco_*/text_effect_*
# probability pinned to the fixed intensity (all others left at 0) instead of
# calling an AUG_METHODS entry on a clean canvas.
_TEXT_DECO_ATTRS: tuple[str, ...] = (
    "bold",
    "color",
    "italic",
    "subscript",
    "superscript",
    "underline",
)
_TEXT_PROB_METHODS: dict[str, tuple[str | None, str | None]] = {
    f"text_deco_{attr}": (attr, None) for attr in _TEXT_DECO_ATTRS
}
_TEXT_PROB_METHODS.update({f"text_effect_{name}": (None, name) for name in TEXT_EFFECT_NAMES})

# extreme_resize's min/max are absolute pixel heights, not [0, 1] fractions
# (see ExtremeResizeConfig) -- verified with its own configured/CLI range
# instead of the shared --min/--max intensity fractions used by every other
# AUG_METHODS entry.
_PIXEL_HEIGHT_METHODS: frozenset[str] = frozenset({"extreme_resize"})


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
    low_grid: np.ndarray,
    high_grid: np.ndarray,
    method_name: str,
    image_width: int,
    min_intensity: float,
    max_intensity: float,
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

    low_labeled = _add_label(low_grid, f"{method_name}  [MIN {min_intensity:.2f}]")
    high_labeled = _add_label(high_grid, f"{method_name}  [MAX {max_intensity:.2f}]")

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


def _apply_at_intensity(
    aug_fn: Any, method_name: str, clean_images: list[np.ndarray], intensity: float
) -> list[np.ndarray]:
    """Apply *aug_fn* at a fixed *intensity* to every clean image.

    The Python RNG is reseeded deterministically per image so pure-Python methods
    reproduce across runs (methods such as rotation draw their own randomness from
    the fixed intensity's range).
    """
    results: list[np.ndarray] = []
    for idx, img in enumerate(clean_images):
        random.seed(42 + idx)
        np.random.seed(42 + idx)
        try:
            if method_name in _RGB_PREFERRED_METHODS:
                rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB) if img.ndim == 2 else img.copy()
                result = aug_fn(rgb, intensity)
                if result is not None and result.ndim == 3:
                    result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
            else:
                result = aug_fn(img.copy(), intensity)
            if result is not None:
                results.append(result)
        except Exception as exc:
            _log.debug("aug %s @ %.3f failed: %s", method_name, intensity, exc)
    return results


def _render_with_single_prob(
    renderer: ImageRenderer,
    cfg: GenerationConfig,
    texts: list[str],
    repeats: int,
    prob: float,
    *,
    deco_attr: str | None,
    effect_attr: str | None,
) -> list[np.ndarray]:
    """Render *texts* with exactly one text_deco/text_effect probability pinned
    to *prob* (all its siblings left at 0), so each is verified in isolation.

    Decorations/effects are sampled inside rendering rather than applied to a
    clean canvas afterward, so this overrides ``cfg.text_deco``/``cfg.text_effect``
    (restored afterward) instead of calling an aug function. ``color`` is a
    no-op in grayscale mode (it only samples when ``color_mode == 3``), so the
    renderer is switched to RGB for that one method.
    """
    original_deco, original_effect = cfg.text_deco, cfg.text_effect
    original_color_mode, original_pil_mode = renderer.color_mode, renderer._pil_mode
    cfg.text_deco = TextDecorationConfig(**({f"{deco_attr}_prob": prob} if deco_attr else {}))
    cfg.text_effect = TextEffectConfig(**({f"{effect_attr}_prob": prob} if effect_attr else {}))
    if deco_attr == "color":
        renderer.color_mode = 3
        renderer._pil_mode = "RGB"
    results: list[np.ndarray] = []
    try:
        for i, text in enumerate(texts):
            for _ in range(repeats):
                random.seed(42 + i)
                np.random.seed(42 + i)
                try:
                    img = renderer.render(text, augment=False)
                    if img is not None:
                        results.append(img)
                except Exception as exc:
                    _log.debug(
                        "%s render failed for %r @ %.3f: %s",
                        deco_attr or effect_attr,
                        text,
                        prob,
                        exc,
                    )
    finally:
        cfg.text_deco, cfg.text_effect = original_deco, original_effect
        renderer.color_mode, renderer._pil_mode = original_color_mode, original_pil_mode
    return results


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

    raw_min = float(args.min_intensity)
    raw_max = float(args.max_intensity)

    min_intensity = float(min(max(raw_min, 0.0), 1.0))
    max_intensity = float(min(max(raw_max, 0.0), 1.0))
    if max_intensity < min_intensity:
        min_intensity, max_intensity = max_intensity, min_intensity

    # Build method list — all registered methods with min/max intensities,
    # plus each rendering-time text_deco/text_effect probability.
    all_methods: dict[str, Any] = dict(AUG_METHODS)
    all_method_names = sorted({*all_methods, *_TEXT_PROB_METHODS})

    requested = set(args.method) if args.method else None
    method_names = [name for name in all_method_names if requested is None or name in requested]

    if not method_names:
        print(f"No matching augmentation methods for: {args.method}")
        return 1

    texts = _load_sample_texts(corpus_path, count)
    print(f"\nVerification samples : {count}")
    print(f"Fonts directory      : {fonts_dir}")
    print(f"Output directory     : {output_dir}")
    print(f"Intensities          : MIN={min_intensity:.2f}  MAX={max_intensity:.2f}")
    if any(name in _PIXEL_HEIGHT_METHODS for name in method_names):
        print("                        (extreme_resize uses pixel heights instead, see below)")
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
        print(f"  ── {method_name} ──")

        # extreme_resize's min/max are pixel heights, not [0, 1] fractions:
        # use its own configured default range (8..1920) unless the user
        # explicitly overrode --min/--max, in which case those are taken as
        # literal pixel heights rather than clamped to [0, 1].
        local_min, local_max = min_intensity, max_intensity
        if method_name in _PIXEL_HEIGHT_METHODS:
            default_min, default_max = cfg.extreme_resize.min, cfg.extreme_resize.max
            local_min = raw_min if raw_min != 0.0 else default_min
            local_max = raw_max if raw_max != 1.0 else default_max
            if local_max < local_min:
                local_min, local_max = local_max, local_min

        if method_name in _TEXT_PROB_METHODS:
            # Rendering-time decoration/effect: re-render at each fixed
            # intensity rather than applying a post-hoc augmentation function.
            deco_attr, effect_attr = _TEXT_PROB_METHODS[method_name]
            print(f"    Applying MIN ({local_min:.2f}) ...", end="", flush=True)
            min_images = _render_with_single_prob(
                renderer,
                cfg,
                texts,
                repeats,
                local_min,
                deco_attr=deco_attr,
                effect_attr=effect_attr,
            )
            print(f" MAX ({local_max:.2f}) ...", end="", flush=True)
            max_images = _render_with_single_prob(
                renderer,
                cfg,
                texts,
                repeats,
                local_max,
                deco_attr=deco_attr,
                effect_attr=effect_attr,
            )
            print(" done")

            if not min_images or not max_images:
                print("    WARNING: no images rendered; skipping.")
                continue
        else:
            aug_fn = all_methods[method_name]

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

            # Apply both intensities (each column uses exactly one fixed value)
            print(f"    Applying MIN ({local_min:.2f}) ...", end="", flush=True)
            min_images = _apply_at_intensity(aug_fn, method_name, clean_images, local_min)
            print(f" MAX ({local_max:.2f}) ...", end="", flush=True)
            max_images = _apply_at_intensity(aug_fn, method_name, clean_images, local_max)
            print(" done")

            if not min_images or not max_images:
                print("    WARNING: failed to apply augmentation; skipping.")
                continue

            if method_name in _PIXEL_HEIGHT_METHODS:
                # The production pipeline always resizes an augmented image
                # back to line height right after augmenting (see
                # ImageRenderer._apply_augmentation); mirror that here so the
                # MAX column shows the actual post-normalisation artifact
                # instead of a literal 1920px-tall image.
                min_images = [renderer._resize_to_target(img) for img in min_images]
                max_images = [renderer._resize_to_target(img) for img in max_images]

        target_w = image_width or max(
            max(img.shape[1] for img in min_images),
            max(img.shape[1] for img in max_images),
        )

        low_grid = _stack_images(min_images, target_w)
        high_grid = _stack_images(max_images, target_w)

        comparison = _make_comparison_grid(
            low_grid, high_grid, method_name, target_w, local_min, local_max
        )

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

    all_names = sorted({*AUG_METHODS, *_TEXT_PROB_METHODS})

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
        "--min",
        dest="min_intensity",
        type=float,
        default=0.0,
        metavar="F",
        help=(
            "Fixed intensity in [0, 1] for the MIN column (default: 0.0). "
            "For --method extreme_resize this is a pixel height instead (default: 8)."
        ),
    )
    parser.add_argument(
        "--max",
        dest="max_intensity",
        type=float,
        default=1.0,
        metavar="F",
        help=(
            "Fixed intensity in [0, 1] for the MAX column (default: 1.0). "
            "For --method extreme_resize this is a pixel height instead (default: 1920)."
        ),
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
