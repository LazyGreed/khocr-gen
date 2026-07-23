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
    val_percent: float = 10.0
    seed: int = 42

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
            help="Random seed for deterministic train/val splitting",
        )
        g_corpus.add_argument(
            "--val-percent",
            type=float,
            default=10.0,
            metavar="PCT",
            help="Validation split percentage [0, 100) (default: 10.0)",
        )
        g_corpus.add_argument(
            "--count-only",
            action="store_true",
            help="Print filter statistics and estimated image count, then exit",
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
        defaults = cls()
        aug_kwargs: dict[str, AugMethodConfig] = {}
        for attr_name, _ in cls._AUG_METHODS:
            cli_key = attr_name.replace("_", "-")
            prob = getattr(args, f"{cli_key}_prob", None)
            v_min = getattr(args, f"{cli_key}_min", None)
            v_max = getattr(args, f"{cli_key}_max", None)

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
            fonts_dir=str(getattr(args, "fonts", "fonts/")),
            mixed_font_prob=float(getattr(args, "mixed_font_prob", 0.0)),
            font_mode=str(getattr(args, "font_mode", "random")),
            copies=int(getattr(args, "copies", 3)),
            min_length=int(getattr(args, "min_length", 1)),
            max_length=int(getattr(args, "max_length", 260)),
            max_lines=int(getattr(args, "lines", 0)),
            val_percent=float(getattr(args, "val_percent", 10.0)),
            seed=int(getattr(args, "seed", 42)),
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
            workers=int(getattr(args, "workers", 0)),
            worker_timeout=int(getattr(args, "worker_timeout", 300)),
            retry_limit=int(getattr(args, "retry_limit", 10)),
            pack_lmdb=bool(getattr(args, "pack_lmdb", False)),
            lmdb_jpeg_quality=int(getattr(args, "lmdb_jpeg_quality", 90)),
            lmdb_map_size_gb=int(getattr(args, "lmdb_map_size_gb", 256)),
            dpi_mode=str(dpi_mode),
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
