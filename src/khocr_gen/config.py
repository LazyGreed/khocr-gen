"""Generation configuration - single source of truth for all generation parameters.

Each augmentation method has three tunable knobs exposed to CLI and config YAML:

* `prob`: probability [0, 1] of applying this augmentation to a given text line
* `min` : minimum intensity level [0, 1] (normalised; mapped to physical units internally)
* `max` : maximum intensity level [0, 1]

The augmentation system is *isolated*:
a single generated image receives exactly one augmentation method on a clean rendered canvas (no stacked effects).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any, ClassVar

from .normalizer import NormalizerConfig

if TYPE_CHECKING:
    import argparse

# ──────────────────────────────────────────────────────────────────────────────
# Per-method augmentation config
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class AugMethodConfig:
    """Probability and intensity range for a single augmentation method."""

    prob: float = 0.0
    min: float = 0.0
    max: float = 1.0

    def __post_init__(self) -> None:
        self.prob = float(max(0.0, min(1.0, self.prob)))
        self.min = float(max(0.0, min(1.0, self.min)))
        self.max = float(max(self.min, min(1.0, self.max)))

    def sample_intensity(self) -> float:
        """Draw a random intensity in [min, max]."""
        if self.min >= self.max:
            return self.min
        import random

        return random.uniform(self.min, self.max)

    @property
    def enabled(self) -> bool:
        return self.prob > 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Per-line text decoration config
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class TextDecorationConfig:
    """Probabilities for per-line text decorations applied at render time.

    Decorations are rendering attributes (not augmentations): each image
    independently samples each decoration, so they can combine (e.g. bold +
    underline). All probabilities default to 0.0 (feature off).
    """

    color_prob: float = 0.0  # whole-line single random color (RGB mode only)
    underline_prob: float = 0.0  # underline under the whole line
    subscript_prob: float = 0.0  # lower 1-2 random ASCII chars
    superscript_prob: float = 0.0  # raise 1-2 random ASCII chars
    italic_prob: float = 0.0  # real italic/oblique variant font (no-op if absent)
    bold_prob: float = 0.0  # real bold variant font (no-op if absent)

    def __post_init__(self) -> None:
        self.color_prob = float(max(0.0, min(1.0, self.color_prob)))
        self.underline_prob = float(max(0.0, min(1.0, self.underline_prob)))
        self.subscript_prob = float(max(0.0, min(1.0, self.subscript_prob)))
        self.superscript_prob = float(max(0.0, min(1.0, self.superscript_prob)))
        self.italic_prob = float(max(0.0, min(1.0, self.italic_prob)))
        self.bold_prob = float(max(0.0, min(1.0, self.bold_prob)))

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.color_prob > 0.0,
                self.underline_prob > 0.0,
                self.subscript_prob > 0.0,
                self.superscript_prob > 0.0,
                self.italic_prob > 0.0,
                self.bold_prob > 0.0,
            )
        )

    @staticmethod
    def add_args(parser: argparse.ArgumentParser) -> None:
        g = parser.add_argument_group(
            "Text decoration",
            "Per-line text decorations applied at render time (can combine). "
            "Bold/italic require a matching variant font; random color requires --color-mode 3.",
        )
        g.add_argument(
            "--text-deco-color-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of a single random text color for the whole line (default: 0)",
        )
        g.add_argument(
            "--text-deco-underline-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of underlining the line (default: 0)",
        )
        g.add_argument(
            "--text-deco-subscript-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of lowering 1-2 random ASCII chars as subscript (default: 0)",
        )
        g.add_argument(
            "--text-deco-superscript-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of raising 1-2 random ASCII chars as superscript (default: 0)",
        )
        g.add_argument(
            "--text-deco-italic-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of italicizing via a real italic/oblique variant font (default: 0)",
        )
        g.add_argument(
            "--text-deco-bold-prob",
            type=float,
            default=None,
            metavar="F",
            help="Probability of bolding via a real bold variant font (default: 0)",
        )

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> TextDecorationConfig:
        def _get(name: str) -> float:
            value = getattr(args, f"text_deco_{name}_prob", None)
            return float(value) if value is not None else 0.0

        return cls(
            color_prob=_get("color"),
            underline_prob=_get("underline"),
            subscript_prob=_get("subscript"),
            superscript_prob=_get("superscript"),
            italic_prob=_get("italic"),
            bold_prob=_get("bold"),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_storage(args: argparse.Namespace) -> str:
    """Resolve storage mode from --storage flag, falling back to legacy flags."""
    storage = str(getattr(args, "storage", "raw"))
    if storage != "raw":
        return storage
    # Legacy flag resolution
    pack = bool(getattr(args, "pack_lmdb", False))
    keep = bool(getattr(args, "keep_raw", False))
    if pack and keep:
        return "both"
    if pack:
        return "lmdb"
    return "raw"


# ──────────────────────────────────────────────────────────────────────────────
# Master config
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class GenerationConfig:
    """All parameters that govern synthetic image generation and augmentation."""

    # ── Image sizing ───────────────────────────────────────────────────────
    image_height: int = 48
    image_width: int | None = None
    color_mode: int = 1  # 1 = grayscale, 3 = RGB
    random_align_when_padded: bool = False

    # ── Variable line height ───────────────────────────────────────────────
    line_height_mode: str = "fixed"  # "fixed" | "variable" | "bucketed"
    min_line_height: int = 32
    max_line_height: int = 96
    line_height_step: int = 8
    line_height_distribution: str = "uniform"  # "uniform" | "triangular"
    default_line_height: int | None = None  # triangular peak; defaults to range midpoint

    # Text scale / padding within the sampled canvas height
    font_size_mode: str = "fixed"  # "fixed" | "proportional"
    min_font_scale: float = 0.65
    max_font_scale: float = 0.9
    vertical_padding_mode: str = "fixed"  # "fixed" | "random"
    min_vertical_padding_ratio: float = 0.04
    max_vertical_padding_ratio: float = 0.18

    # Optional per-sample metadata sidecar
    record_metadata: bool = False

    # ── Font / language ────────────────────────────────────────────────────
    language: str = "mixed"
    fonts_dir: str = "fonts"
    mixed_font_prob: float = 0.0
    font_mode: str = "random"  # "random" | "all"
    copies: int = 3  # augmented copies per line when font_mode=random

    # ── Corpus ─────────────────────────────────────────────────────────────
    corpus_path: str = ""
    min_length: int = 1
    max_length: int = 260
    max_lines: int = 0
    val_percent: float | None = None
    test_percent: float | None = None
    split_ratios: tuple[float, float, float] | None = None
    seed: int = 42
    oversample_rare_chars: bool = False
    rare_char_percentile: float = 5.0
    rare_char_multiplier: float = 3.0

    # ── Output ─────────────────────────────────────────────────────────────
    output_dir: str = "data"
    vocab_path: str = ""
    skip_vocab: bool = False
    append: bool = False
    overwrite: bool = False
    output_format: str = "jpg"  # "png" | "jpg" | "tiff"
    jpeg_quality: int = 90  # JPEG quality for jpg output
    storage: str = "raw"  # "raw" | "lmdb" | "both"
    keep_raw: bool = False  # legacy; prefer storage="both"
    bg_color_mode: str = (
        "random"  # "default" | "paper_tones" | "colored" | "dark_mode" | "gradient" | "random"
    )

    # ── Worker reliability ─────────────────────────────────────────────────
    workers: int = 0  # 0 = auto
    worker_timeout: int = 300  # seconds; 0 = no timeout
    retry_limit: int = 10

    # ── LMDB packing ───────────────────────────────────────────────────────
    pack_lmdb: bool = False
    lmdb_jpeg_quality: int = 90
    lmdb_map_size_gb: int = 256

    # ── DPI rendering mode ─────────────────────────────────────────────────
    dpi_mode: str = "native"  # "native" | "oversample" | "lowdpi"

    # ───────────────────────────────────────────────────────────────────────
    # Augmentation methods - each has {prob, min, max}
    # ───────────────────────────────────────────────────────────────────────

    # ── Augmentation methods ──

    # Sauvola local-threshold degradation
    sauvola: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.2, min=0.1, max=0.9)
    )

    # 4-point perspective (geometric) warp
    geo_warp: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.2, min=0.1, max=0.9)
    )

    # Random vertical crop
    vertical_crop: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Albumentations blur branch (MotionBlur | MedianBlur | GaussianBlur)
    blur: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.4, min=0.1, max=0.9)
    )

    # Albumentations distortion (Optical | Grid | Elastic)
    distortion: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.3, min=0.1, max=0.9)
    )

    # Albumentations noise (GaussNoise | MultiplicativeNoise)
    albu_noise: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.4, min=0.1, max=0.9)
    )

    # JPEG compression artifacts
    jpeg_compression: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.4, min=0.1, max=0.9)
    )

    # Random rotation
    rotation: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Salt-and-pepper noise
    salt_pepper: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.15, min=0.1, max=0.9)
    )

    # Background texture overlay
    background_texture: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.35, min=0.1, max=0.9)
    )

    # Low-DPI rendering simulation
    lowdpi: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Oversample rendering
    oversample: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Low-contrast small caption text
    low_contrast_caption: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Perspective warp
    perspective: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Elastic distortion
    elastic: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Random height crop
    random_crop: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Gaussian/Motion blur
    online_blur: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Gaussian noise
    online_noise: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # HSV color jitter
    hsv: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Color reversal
    reverse: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.0, max=1.0)
    )

    # Brightness/contrast jitter
    brightness_contrast: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Pixelation (downscale-upscale)
    pixelation: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Gradient illumination overlay
    gradient_illumination: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Morphological erode/dilate
    morphological: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # Anisotropic dilation (dot-matrix spread)
    anisotropic_dilation: AugMethodConfig = field(
        default_factory=lambda: AugMethodConfig(prob=0.0, min=0.1, max=0.9)
    )

    # ── Normalizer config ──────────────────────────────────────────────────
    normalizer: NormalizerConfig = field(default_factory=NormalizerConfig)

    # ── Text decorations ──────────────────────────────────────────────────
    text_deco: TextDecorationConfig = field(default_factory=TextDecorationConfig)

    # ───────────────────────────────────────────────────────────────────────
    # Split ratio resolution
    # ───────────────────────────────────────────────────────────────────────

    def resolve_split_ratios(self) -> tuple[float, float, float]:
        """Resolve (train_ratio, val_ratio, test_ratio) from config fields.

        Resolution rules (highest priority first):

        1. ``split_ratios`` set explicitly:
           Normalise the three values so they sum to 1.0.
           Example: ``split_ratios=(70, 15, 15)`` -> ``(0.70, 0.15, 0.15)``.

        2. Both ``val_percent`` and ``test_percent`` set:
           ``train = 1 - val/100 - test/100``.

        3. Only ``val_percent`` set:
           ``test = 0``, ``train = 1 - val/100``.
           Example: ``--val-percent 15`` -> ``(0.85, 0.15, 0.0)``.

        4. Only ``test_percent`` set:
           ``val = 0``, ``train = 1 - test/100``.
           Example: ``--test-percent 15`` -> ``(0.85, 0.0, 0.15)``.

        5. Neither set (default):
           ``(0.80, 0.10, 0.10)``.

        To disable all splitting (100 % train), set:
        - ``--split-ratios 100 0 0``, or
        - ``--val-percent 0 --test-percent 0``.
        """
        if self.split_ratios is not None:
            a, b, c = self.split_ratios
            total = a + b + c
            if total <= 0.0:
                return (1.0, 0.0, 0.0)
            return (a / total, b / total, c / total)

        val_set = self.val_percent is not None
        test_set = self.test_percent is not None

        if val_set and test_set:
            v = max(0.0, min(100.0, float(self.val_percent)))  # type: ignore[arg-type]
            t = max(0.0, min(100.0, float(self.test_percent)))  # type: ignore[arg-type]
            tr = max(0.0, 100.0 - v - t)
            total = tr + v + t
            return (tr / total, v / total, t / total)

        if val_set:
            v = max(0.0, min(100.0, float(self.val_percent)))  # type: ignore[arg-type]
            tr = max(0.0, 100.0 - v)
            return (
                tr / (tr + v) if (tr + v) > 0 else 1.0,
                v / (tr + v) if (tr + v) > 0 else 0.0,
                0.0,
            )

        if test_set:
            t = max(0.0, min(100.0, float(self.test_percent)))  # type: ignore[arg-type]
            tr = max(0.0, 100.0 - t)
            return (
                tr / (tr + t) if (tr + t) > 0 else 1.0,
                0.0,
                t / (tr + t) if (tr + t) > 0 else 0.0,
            )

        # Default: 80/10/10
        return (0.80, 0.10, 0.10)

    # ───────────────────────────────────────────────────────────────────────
    # CLI
    # ───────────────────────────────────────────────────────────────────────

    # -- Helper to build AugMethodConfig CLI flags --
    _AUG_METHODS: ClassVar[tuple[tuple[str, str], ...]] = (
        # (attr_name, display_name)
        ("sauvola", "Sauvola threshold degradation"),
        ("geo_warp", "Geometric (4-point) perspective warp"),
        ("vertical_crop", "Random vertical crop"),
        ("blur", "Blur (MotionBlur|MedianBlur|GaussianBlur via Albumentations)"),
        ("distortion", "Distortion (Optical|Grid|Elastic via Albumentations)"),
        ("albu_noise", "Noise (GaussNoise|MultiplicativeNoise via Albumentations)"),
        ("jpeg_compression", "JPEG compression artifacts"),
        ("rotation", "Random rotation"),
        ("salt_pepper", "Salt-and-pepper impulse noise"),
        ("background_texture", "Background texture overlay"),
        ("lowdpi", "Low-DPI rendering simulation"),
        ("oversample", "Oversample rendering"),
        ("low_contrast_caption", "Low-contrast small caption text"),
        ("perspective", "Perspective warp"),
        ("elastic", "Elastic distortion"),
        ("random_crop", "Random height crop"),
        ("online_blur", "Gaussian/Motion blur"),
        ("online_noise", "Gaussian noise"),
        ("hsv", "HSV color jitter"),
        ("reverse", "Color reversal (dark to light)"),
        ("brightness_contrast", "Brightness/contrast jitter"),
        ("pixelation", "Pixelation (downscale-then-upscale)"),
        ("gradient_illumination", "Gradient illumination overlay"),
        ("morphological", "Morphological erode/dilate"),
        ("anisotropic_dilation", "Anisotropic dilation (dot-matrix spread)"),
    )

    @staticmethod
    def add_args(parser: argparse.ArgumentParser) -> None:
        """Register all CLI arguments for generation."""

        # ── Rendering ──────────────────────────────────────────────────────
        g_render = parser.add_argument_group("Rendering")
        g_render.add_argument(
            "--fonts",
            default="fonts/",
            help="Root fonts directory: <dir>/khmer/ and <dir>/english/ subdirs",
        )
        g_render.add_argument(
            "--height",
            type=int,
            default=48,
            metavar="PX",
            help="Image height in pixels (default: 48)",
        )
        g_render.add_argument(
            "--width",
            type=int,
            default=None,
            metavar="PX",
            help="Fixed image width; omit for variable width",
        )
        g_render.add_argument(
            "--color-mode",
            type=int,
            choices=[1, 3],
            default=1,
            metavar="{1,3}",
            help="Output colour channels: 1 = grayscale, 3 = RGB (default: 1)",
        )
        g_render.add_argument(
            "--random-align-when-padded",
            action="store_true",
            help="Random left/center/right alignment when --width pads the image",
        )

        # ── Variable line height ─────────────────────────────────────────────
        g_vh = parser.add_argument_group("Variable line height")
        g_vh.add_argument(
            "--line-height-mode",
            choices=["fixed", "variable", "bucketed"],
            default="fixed",
            help=(
                "'fixed' = every image uses --height (default, backward compatible). "
                "'variable' = sample a height per image from [--min-line-height, "
                "--max-line-height]. 'bucketed' = sample from the fixed set of heights "
                "spaced by --line-height-step across that range."
            ),
        )
        g_vh.add_argument(
            "--min-line-height",
            type=int,
            default=32,
            metavar="PX",
            help="Minimum sampled line height in pixels (default: 32)",
        )
        g_vh.add_argument(
            "--max-line-height",
            type=int,
            default=96,
            metavar="PX",
            help="Maximum sampled line height in pixels (default: 96)",
        )
        g_vh.add_argument(
            "--line-height-step",
            type=int,
            default=8,
            metavar="PX",
            help="Align sampled/bucketed heights to a multiple of this many pixels (default: 8)",
        )
        g_vh.add_argument(
            "--line-height-distribution",
            choices=["uniform", "triangular"],
            default="uniform",
            help=(
                "Shape of the height distribution for --line-height-mode=variable. "
                "'triangular' clusters samples around --default-line-height (default: uniform)"
            ),
        )
        g_vh.add_argument(
            "--default-line-height",
            type=int,
            default=None,
            metavar="PX",
            help="Peak height for the triangular distribution (default: midpoint of the range)",
        )
        g_vh.add_argument(
            "--font-size-mode",
            choices=["fixed", "proportional"],
            default="fixed",
            help=(
                "'fixed' = choose from the preloaded font sizes (default). "
                "'proportional' = choose a font size scaled to the sampled canvas height "
                "(--min-font-scale..--max-font-scale)"
            ),
        )
        g_vh.add_argument(
            "--min-font-scale",
            type=float,
            default=0.65,
            metavar="F",
            help="Minimum glyph height as a fraction of canvas height when font-size-mode=proportional (default: 0.65)",
        )
        g_vh.add_argument(
            "--max-font-scale",
            type=float,
            default=0.9,
            metavar="F",
            help="Maximum glyph height as a fraction of canvas height when font-size-mode=proportional (default: 0.9)",
        )
        g_vh.add_argument(
            "--vertical-padding-mode",
            choices=["fixed", "random"],
            default="fixed",
            help=(
                "'fixed' = existing constant pixel padding (default). "
                "'random' = sample top/bottom padding as a ratio of canvas height"
            ),
        )
        g_vh.add_argument(
            "--min-vertical-padding-ratio",
            type=float,
            default=0.04,
            metavar="F",
            help="Minimum vertical padding as a fraction of canvas height (default: 0.04)",
        )
        g_vh.add_argument(
            "--max-vertical-padding-ratio",
            type=float,
            default=0.18,
            metavar="F",
            help="Maximum vertical padding as a fraction of canvas height (default: 0.18)",
        )
        g_vh.add_argument(
            "--record-metadata",
            action="store_true",
            help="Write a metadata.jsonl sidecar (image/text/width/height) per split",
        )
        g_render.add_argument(
            "--font-mode",
            choices=["random", "all"],
            default="random",
            help="'random' = N augmented copies; 'all' = one image per font per line",
        )
        g_render.add_argument(
            "--copies",
            type=int,
            default=3,
            metavar="N",
            help="Augmented copies per text line when --font-mode=random (default: 3)",
        )
        g_render.add_argument(
            "--mixed-font-prob",
            type=float,
            default=0.0,
            metavar="F",
            help="Probability of per-span font rendering for mixed Khmer/English text",
        )
        g_render.add_argument(
            "--retry-limit",
            type=int,
            default=10,
            metavar="N",
            help="Font selection retries per image when font lacks glyphs",
        )

        # ── Corpus ─────────────────────────────────────────────────────────
        g_corpus = parser.add_argument_group("Corpus")
        g_corpus.add_argument(
            "--corpus",
            default="corpus/corpus.txt",
            metavar="FILE",
            help="Path to plain text corpus file",
        )
        g_corpus.add_argument(
            "--min-length",
            type=int,
            default=1,
            metavar="N",
            help="Minimum character length to include (default: 1)",
        )
        g_corpus.add_argument(
            "--max-length",
            type=int,
            default=260,
            metavar="N",
            help="Maximum character length to include (default: 260)",
        )
        g_corpus.add_argument(
            "--lines",
            type=int,
            default=0,
            metavar="N",
            help="Max lines to use after filtering; 0 = all",
        )
        g_corpus.add_argument(
            "--seed",
            type=int,
            default=42,
            metavar="N",
            help="Random seed for deterministic train/val/test splitting",
        )
        g_corpus.add_argument(
            "--val-percent",
            type=float,
            default=None,
            metavar="PCT",
            help=(
                "Validation split percentage [0, 100). "
                "If only this is set, test=0. "
                "If neither --val-percent nor --test-percent is set, defaults to 10%%."
            ),
        )
        g_corpus.add_argument(
            "--test-percent",
            type=float,
            default=None,
            metavar="PCT",
            help=(
                "Test split percentage [0, 100). "
                "If only this is set, val=0. "
                "If neither --val-percent nor --test-percent is set, defaults to 10%%."
            ),
        )
        g_corpus.add_argument(
            "--split-ratios",
            nargs=3,
            type=float,
            default=None,
            metavar=("TRAIN", "VAL", "TEST"),
            help=(
                "Explicit train/val/test split ratios (three values, e.g. 80 10 10). "
                "Values are normalised to sum to 1.0. "
                "Overrides --val-percent and --test-percent. "
                "Set '100 0 0' to disable splitting entirely."
            ),
        )
        g_corpus.add_argument(
            "--test-file",
            default=None,
            metavar="FILE",
            help="Path to a separate test corpus file (bypasses automatic test splitting)",
        )
        g_corpus.add_argument(
            "--count-only",
            action="store_true",
            help="Print filter statistics and estimated image count, then exit",
        )
        g_corpus.add_argument(
            "--oversample-rare-chars",
            action="store_true",
            help=(
                "Render extra copies of training lines that contain rare characters "
                "(does not affect val/test, which stay at 1 copy per line)"
            ),
        )
        g_corpus.add_argument(
            "--rare-char-percentile",
            type=float,
            default=5.0,
            metavar="PCT",
            help=(
                "Least-frequent PCT%% of distinct characters in the corpus are "
                "considered rare (default: 5.0)"
            ),
        )
        g_corpus.add_argument(
            "--rare-char-multiplier",
            type=float,
            default=3.0,
            metavar="F",
            help=(
                "Copies multiplier applied to training lines containing a rare "
                "character (default: 3.0)"
            ),
        )
        g_corpus.add_argument(
            "--image-dir",
            default=None,
            metavar="DIR",
            help="Path to existing images directory (bypass text rendering; "
            "corpus must be labels.txt file)",
        )

        # ── Output ─────────────────────────────────────────────────────────
        g_out = parser.add_argument_group("Output")
        g_out.add_argument(
            "--output",
            "--output-dir",
            dest="output",
            default="data",
            metavar="DIR",
            help="Output directory for generated dataset (default: data/)",
        )
        g_out_grp = g_out.add_mutually_exclusive_group()
        g_out_grp.add_argument(
            "--append",
            action="store_true",
            help="Append new samples if output directory exists",
        )
        g_out_grp.add_argument(
            "--overwrite",
            action="store_true",
            help="Delete and recreate if output directory exists",
        )
        g_out.add_argument(
            "--vocab",
            default="",
            metavar="FILE",
            help="Path to write vocab.json; auto-derived if not set",
        )
        g_out.add_argument(
            "--skip-vocab",
            action="store_true",
            help="Do not build vocab.json after generation",
        )
        g_out.add_argument(
            "--output-format",
            choices=["png", "jpg", "tiff"],
            default="jpg",
            help="Output image format (default: jpg)",
        )
        g_out.add_argument(
            "--jpeg-quality",
            type=int,
            default=90,
            metavar="N",
            help="JPEG quality for jpg output (default: 90; 0-100)",
        )
        g_out.add_argument(
            "--storage",
            choices=["raw", "lmdb", "both"],
            default="raw",
            help="Storage mode: raw = image files only, lmdb = pack and delete, both = save + pack + keep (default: raw)",
        )

        # ── LMDB packing ───────────────────────────────────────────────────
        g_lmdb = parser.add_argument_group("LMDB Packing")
        g_lmdb.add_argument(
            "--pack-lmdb",
            action="store_true",
            help="Pack generated dataset into LMDB databases after generation",
        )
        g_lmdb.add_argument(
            "--keep-raw",
            action="store_true",
            help="Keep raw image files after LMDB packing",
        )
        g_lmdb.add_argument(
            "--lmdb-jpeg-quality",
            type=int,
            default=90,
            metavar="N",
            help="JPEG quality for LMDB-stored images (default: 90)",
        )
        g_lmdb.add_argument(
            "--lmdb-map-size-gb",
            type=int,
            default=256,
            metavar="N",
            help="LMDB map size in GiB (default: 256)",
        )

        # ── Workers ────────────────────────────────────────────────────────
        g_workers = parser.add_argument_group("Workers")
        g_workers.add_argument(
            "--workers",
            type=int,
            default=0,
            metavar="N",
            help="Worker processes; 0 = auto, 1 = serial (default: 0)",
        )
        g_workers.add_argument(
            "--worker-timeout",
            type=int,
            default=300,
            metavar="SEC",
            help="Seconds before a worker batch times out (default: 300; 0 = no limit)",
        )

        # ── DPI ────────────────────────────────────────────────────────────
        g_dpi = parser.add_argument_group("DPI simulation")
        g_dpi.add_argument(
            "--dpi-mode",
            choices=["native", "oversample", "lowdpi"],
            default="native",
            help="DPI rendering strategy (default: native)",
        )

        # ── Rendering style ─────────────────────────────────────────────────
        g_style = parser.add_argument_group("Rendering style")
        g_style.add_argument(
            "--bg-color-mode",
            choices=["default", "paper_tones", "colored", "dark_mode", "gradient", "random"],
            default="random",
            help=(
                "Background colour palette for rendered images (default: random). "
                "'default': off-white/light-gray. "
                "'paper_tones': warm cream, sepia, recycled, blueprint. "
                "'colored': soft pastels. "
                "'dark_mode': dark background with light text. "
                "'gradient': brightness gradient overlay. "
                "'random': sample across all palettes when augmentation is enabled."
            ),
        )

        # ── Text decoration ──────────────────────────────────────────────────
        TextDecorationConfig.add_args(parser)

        # ── Augmentation methods: prob, min, max per method ────────────────
        g_aug = parser.add_argument_group(
            "Augmentation methods",
            "Each method has: --<name>-prob F, --<name>-min F, --<name>-max F\n"
            "One augmentation per image (isolated, not stacked).",
        )
        for attr_name, display_name in GenerationConfig._AUG_METHODS:
            g_aug.add_argument(
                f"--{attr_name.replace('_', '-')}-prob",
                type=float,
                default=None,
                metavar="F",
                help=f"Probability of applying {display_name} (0-1)",
            )
            g_aug.add_argument(
                f"--{attr_name.replace('_', '-')}-min",
                type=float,
                default=None,
                metavar="F",
                help=f"Minimum intensity for {display_name} (0-1)",
            )
            g_aug.add_argument(
                f"--{attr_name.replace('_', '-')}-max",
                type=float,
                default=None,
                metavar="F",
                help=f"Maximum intensity for {display_name} (0-1)",
            )

        # ── Normalizer ─────────────────────────────────────────────────────
        NormalizerConfig.add_args(parser)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> GenerationConfig:
        """Build a ``GenerationConfig`` from parsed CLI arguments."""

        # Build AugMethodConfig per method from CLI flags (or use defaults)
        # NOTE: argparse derives `dest` from the option string by replacing
        # "-" with "_", so the attribute name IS the lookup key (e.g.
        # --background-texture-min -> dest "background_texture_min"). Do NOT
        # dash-ify attr_name here: doing so previously produced lookup keys
        # like "background-texture_min", which never matched any argparse
        # dest (Python identifiers can't contain "-"), so getattr() always
        # returned None and every multi-word method silently fell back to
        # its dataclass default regardless of CLI/YAML configuration.
        defaults = cls()
        aug_kwargs: dict[str, AugMethodConfig] = {}
        for attr_name, _ in cls._AUG_METHODS:
            prob = getattr(args, f"{attr_name}_prob", None)
            v_min = getattr(args, f"{attr_name}_min", None)
            v_max = getattr(args, f"{attr_name}_max", None)

            default: AugMethodConfig = getattr(defaults, attr_name)
            aug_kwargs[attr_name] = AugMethodConfig(
                prob=float(prob) if prob is not None else default.prob,
                min=float(v_min) if v_min is not None else default.min,
                max=float(v_max) if v_max is not None else default.max,
            )

        dpi_mode = getattr(args, "dpi_mode", "native")

        config = cls(
            image_height=int(getattr(args, "height", 48)),
            image_width=getattr(args, "width", None),
            color_mode=int(getattr(args, "color_mode", 1)),
            random_align_when_padded=bool(getattr(args, "random_align_when_padded", False)),
            line_height_mode=str(getattr(args, "line_height_mode", "fixed")),
            min_line_height=int(getattr(args, "min_line_height", 32)),
            max_line_height=int(getattr(args, "max_line_height", 96)),
            line_height_step=int(getattr(args, "line_height_step", 8)),
            line_height_distribution=str(getattr(args, "line_height_distribution", "uniform")),
            default_line_height=(
                int(args.default_line_height)
                if getattr(args, "default_line_height", None) is not None
                else None
            ),
            font_size_mode=str(getattr(args, "font_size_mode", "fixed")),
            min_font_scale=float(getattr(args, "min_font_scale", 0.65)),
            max_font_scale=float(getattr(args, "max_font_scale", 0.9)),
            vertical_padding_mode=str(getattr(args, "vertical_padding_mode", "fixed")),
            min_vertical_padding_ratio=float(getattr(args, "min_vertical_padding_ratio", 0.04)),
            max_vertical_padding_ratio=float(getattr(args, "max_vertical_padding_ratio", 0.18)),
            record_metadata=bool(getattr(args, "record_metadata", False)),
            fonts_dir=str(getattr(args, "fonts", "fonts/")),
            mixed_font_prob=float(getattr(args, "mixed_font_prob", 0.0)),
            font_mode=str(getattr(args, "font_mode", "random")),
            copies=int(getattr(args, "copies", 3)),
            min_length=int(getattr(args, "min_length", 1)),
            max_length=int(getattr(args, "max_length", 260)),
            max_lines=int(getattr(args, "lines", 0)),
            val_percent=getattr(args, "val_percent", None),
            test_percent=getattr(args, "test_percent", None),
            split_ratios=(
                tuple(args.split_ratios)
                if getattr(args, "split_ratios", None) is not None
                else None
            ),
            seed=int(getattr(args, "seed", 42)),
            oversample_rare_chars=bool(getattr(args, "oversample_rare_chars", False)),
            rare_char_percentile=float(getattr(args, "rare_char_percentile", 5.0)),
            rare_char_multiplier=float(getattr(args, "rare_char_multiplier", 3.0)),
            corpus_path=str(getattr(args, "corpus", "")),
            output_dir=str(getattr(args, "output", "data")),
            vocab_path=str(getattr(args, "vocab", "")),
            skip_vocab=bool(getattr(args, "skip_vocab", False)),
            append=bool(getattr(args, "append", False)),
            overwrite=bool(getattr(args, "overwrite", False)),
            output_format=str(getattr(args, "output_format", "jpg")),
            jpeg_quality=int(getattr(args, "jpeg_quality", 90)),
            storage=_resolve_storage(args),
            keep_raw=bool(getattr(args, "keep_raw", False)),
            bg_color_mode=str(getattr(args, "bg_color_mode", "random")),
            workers=int(getattr(args, "workers", 0)),
            worker_timeout=int(getattr(args, "worker_timeout", 300)),
            retry_limit=int(getattr(args, "retry_limit", 10)),
            pack_lmdb=bool(getattr(args, "pack_lmdb", False)),
            lmdb_jpeg_quality=int(getattr(args, "lmdb_jpeg_quality", 90)),
            lmdb_map_size_gb=int(getattr(args, "lmdb_map_size_gb", 256)),
            dpi_mode=str(dpi_mode),
            text_deco=TextDecorationConfig.from_args(args),
            normalizer=NormalizerConfig.from_args(args),
        )
        for attr_name, aug_cfg in aug_kwargs.items():
            setattr(config, attr_name, aug_cfg)
        return config

    # ───────────────────────────────────────────────────────────────────────
    # Introspection helpers
    # ───────────────────────────────────────────────────────────────────────

    def iter_aug_methods(self) -> list[tuple[str, AugMethodConfig]]:
        """Yield (attr_name, AugMethodConfig) for every augmentation method."""
        result: list[tuple[str, AugMethodConfig]] = []
        for attr_name, _ in self._AUG_METHODS:
            cfg = getattr(self, attr_name)
            if isinstance(cfg, AugMethodConfig):
                result.append((attr_name, cfg))
        return result

    def enabled_aug_methods(self) -> list[tuple[str, AugMethodConfig]]:
        """Return only augmentation methods with prob > 0."""
        return [(name, cfg) for name, cfg in self.iter_aug_methods() if cfg.enabled]

    # ───────────────────────────────────────────────────────────────────────
    # Serialisation (for IPC / config file)
    # ───────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for cross-process IPC and YAML export."""
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, AugMethodConfig):
                result[f.name] = {"prob": value.prob, "min": value.min, "max": value.max}
            elif isinstance(value, NormalizerConfig):
                result["normalizer"] = {
                    "unicode_norm": value.unicode_norm,
                    "emoji_replacement": value.emoji_replacement,
                    "url_replacement": value.url_replacement,
                    "remove_zwsp": value.remove_zwsp,
                    "passthrough": value.passthrough,
                }
            elif isinstance(value, TextDecorationConfig):
                result[f.name] = {
                    "color_prob": value.color_prob,
                    "underline_prob": value.underline_prob,
                    "subscript_prob": value.subscript_prob,
                    "superscript_prob": value.superscript_prob,
                    "italic_prob": value.italic_prob,
                    "bold_prob": value.bold_prob,
                }
            else:
                result[f.name] = value
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GenerationConfig:
        """Reconstruct from a dict produced by :meth:`to_dict`.

        Unknown keys are silently ignored so workers started with an older
        config dict do not crash when new keys are added.
        """
        aug_method_names = {name for name, _ in cls._AUG_METHODS}
        aug_kwargs: dict[str, AugMethodConfig] = {}
        other_kwargs: dict[str, Any] = {}

        for key, value in d.items():
            if key in aug_method_names and isinstance(value, dict):
                aug_kwargs[key] = AugMethodConfig(
                    prob=float(value.get("prob", 0.0)),
                    min=float(value.get("min", 0.0)),
                    max=float(value.get("max", 1.0)),
                )
            elif key == "normalizer" and isinstance(value, dict):
                other_kwargs[key] = NormalizerConfig(
                    unicode_norm=value.get("unicode_norm", ""),
                    emoji_replacement=value.get("emoji_replacement", ""),
                    url_replacement=value.get("url_replacement", ""),
                    remove_zwsp=value.get("remove_zwsp", True),
                    passthrough=value.get("passthrough", False),
                )
            elif key == "text_deco" and isinstance(value, dict):
                other_kwargs[key] = TextDecorationConfig(
                    color_prob=float(value.get("color_prob", 0.0)),
                    underline_prob=float(value.get("underline_prob", 0.0)),
                    subscript_prob=float(value.get("subscript_prob", 0.0)),
                    superscript_prob=float(value.get("superscript_prob", 0.0)),
                    italic_prob=float(value.get("italic_prob", 0.0)),
                    bold_prob=float(value.get("bold_prob", 0.0)),
                )
            elif key not in aug_method_names:
                other_kwargs[key] = value

        # Map yaml-key names to attr names (e.g. "image_height" stays, "image-height" also works)
        known = {f.name for f in fields(cls)} - aug_method_names - {"normalizer"}
        filtered = {
            k: v
            for k, v in other_kwargs.items()
            if k.replace("-", "_") in known and k != "normalizer"
        }
        # Renormalise dashed keys
        remapped: dict[str, Any] = {}
        for k, v in filtered.items():
            remapped[k.replace("-", "_")] = v

        return cls(
            **remapped,
            **aug_kwargs,
            **({"normalizer": other_kwargs["normalizer"]} if "normalizer" in other_kwargs else {}),
        )
