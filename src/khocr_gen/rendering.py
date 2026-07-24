"""ImageRenderer - synthetic text-to-image rendering with isolated augmentation.

Core design: each text line is rendered to a clean canvas (no augmentation),
then for each enabled augmentation method a copy of the clean canvas is produced with exactly one augmentation effect applied.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import _rust_accel as _ra
from .augmentation import _RGB_PREFERRED_METHODS, AUG_METHODS
from .line_height import sample_font_scale, sample_line_height, sample_vertical_padding_ratio
from .logging import get_logger

if TYPE_CHECKING:
    from .config import AugMethodConfig, GenerationConfig
    from .fonts import FontManager

HAS_PIL = True  # Import of PIL.Image above verifies this

_LOGGER = get_logger("rendering")


class _BoundedCache(dict):
    """Dict that evicts the oldest entries (FIFO) when maxsize is exceeded."""

    def __init__(self, maxsize: int) -> None:
        super().__init__()
        self._maxsize = maxsize
        self._keys: list[Any] = []

    def __setitem__(self, key: Any, value: Any) -> None:
        if key not in self:
            if len(self) >= self._maxsize:
                evict = max(1, self._maxsize // 10)
                for _ in range(evict):
                    if self._keys:
                        oldest = self._keys.pop(0)
                        super().pop(oldest, None)
            self._keys.append(key)
        super().__setitem__(key, value)


class ImageRenderer:
    """Render text to images with isolated augmentation.

    Each enabled augmentation method receives a copy of the clean rendered canvas and applies exactly one effect;
    no stacked/combined augmentations.
    """

    def __init__(self, font_manager: FontManager, cfg: GenerationConfig) -> None:
        self._cfg = cfg
        self.font_manager = font_manager
        self.image_height = cfg.image_height
        self.image_width = cfg.image_width
        self.color_mode = int(cfg.color_mode)
        self.random_align_when_padded = bool(cfg.random_align_when_padded)
        self.dpi_mode = cfg.dpi_mode
        self.mixed_font_prob = float(max(0.0, min(1.0, cfg.mixed_font_prob)))
        self.font_size_mode = getattr(cfg, "font_size_mode", "fixed")
        self.vertical_padding_mode = getattr(cfg, "vertical_padding_mode", "fixed")

        # Derived properties
        self._pil_mode: str = "L" if self.color_mode == 1 else "RGB"
        self._bg_color_mode: str = getattr(cfg, "bg_color_mode", "random")

        # Caches
        self._font_ref_cache: _BoundedCache = _BoundedCache(maxsize=1_000)
        self._glyph_support_cache: _BoundedCache = _BoundedCache(maxsize=50_000)
        self._text_support_cache: _BoundedCache = _BoundedCache(maxsize=10_000)
        self._measurement_draw = ImageDraw.Draw(Image.new(self._pil_mode, (1, 1)))
        self._probe_failed_fonts: set[Any] = set()
        self._font_face_cache: dict[str, Any] = {}

    # ── Font caching helpers ────────────────────────────────────────────────

    @staticmethod
    def _font_cache_key(font: Any) -> Any:
        font_path = getattr(font, "path", None)
        font_size = getattr(font, "size", None)
        if font_path is not None and font_size is not None:
            return (str(font_path), int(font_size))
        return id(font)

    def _get_font_face(self, font_path: str) -> Any | None:
        """Get a cached Rust `FontFace` for O(1) cmap-based glyph queries.

        Returns `None` when Rust acceleration is unavailable or the font file fails to parse,
        in which case callers should fall back to the PIL rasterization-based glyph check.
        """
        if not _ra.HAS_RUST_ACCEL or _ra.FontFace is None:
            return None
        if font_path in self._font_face_cache:
            return self._font_face_cache[font_path]
        try:
            face = _ra.FontFace.from_file(str(font_path))
        except Exception:
            face = None
        self._font_face_cache[font_path] = face
        return face

    def _get_reference_glyph_signature(self, font: Any) -> tuple[Any, Any]:
        """Get cached signature of the font's undefined (tofu) glyph."""
        font_key = self._font_cache_key(font)
        if font_key in self._font_ref_cache:
            return self._font_ref_cache[font_key]

        undefined_chars = ["￿", "\U0010ffff", "\0"]
        ref_signature = None
        for uc in undefined_chars:
            try:
                ref_mask = font.getmask(uc)
                if ref_mask:
                    bbox = ref_mask.getbbox()
                    if bbox is not None:
                        ref_signature = (bbox, bytes(ref_mask))
                        break
            except Exception:
                continue

        if ref_signature is None:
            ref_signature = (None, None)

        self._font_ref_cache[font_key] = ref_signature
        return ref_signature

    def _is_char_supported(self, font: Any, char: str, ref_bbox: Any, ref_bytes: bytes) -> bool:
        """Check if a font supports a single character."""
        font_key = self._font_cache_key(font)
        cache_key = (font_key, char)
        cached = self._glyph_support_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            char_mask = font.getmask(char)
            char_bbox = char_mask.getbbox()
            if ref_bbox is None:
                supported = char_bbox is not None
            else:
                supported = not (char_bbox == ref_bbox and bytes(char_mask) == ref_bytes)
        except Exception:
            supported = False

        self._glyph_support_cache[cache_key] = supported
        return supported

    def _is_text_supported(self, font: Any, text: str) -> bool:
        """Check if font supports all characters in text."""
        try:
            font_key = self._font_cache_key(font)
            text_cache_key = (font_key, text)
            cached = self._text_support_cache.get(text_cache_key)
            if cached is not None:
                return cached

            font_path = getattr(font, "path", None)
            if font_path is not None:
                face = self._get_font_face(font_path)
                if face is not None:
                    supported = face.text_supported(text)
                    self._text_support_cache[text_cache_key] = supported
                    return supported

            ref_bbox, ref_bytes = self._get_reference_glyph_signature(font)
            for char in text:
                if char.isspace() or ord(char) < 32:
                    continue
                if not self._is_char_supported(font, char, ref_bbox, ref_bytes):
                    self._text_support_cache[text_cache_key] = False
                    return False

            self._text_support_cache[text_cache_key] = True
            return True
        except Exception:
            return True

    def _image_is_blank(
        self, img_array: np.ndarray, threshold: int = 150, min_ratio: float = 0.002
    ) -> bool:
        """Check if image has too few dark/text pixels."""
        if img_array is None or img_array.size == 0:
            return True
        dark_pixels = np.sum(img_array < threshold)
        return (dark_pixels / img_array.size) < min_ratio

    # ── Background/text colour sampling ────────────────────────────────────

    def _sample_bg_and_text_colors(
        self, augment: bool
    ) -> tuple[int | tuple[int, int, int], int | tuple[int, int, int]]:
        """Sample (bg_color, text_color) according to ``bg_color_mode``.

        Palette catalogue
        -----------------
        default
            Off-white / light grey background (235-255) with near-black text (0-30).
            Always used when ``augment=False``.

        paper_tones
            Warm cream, aged sepia, recycled grey, or blueprint blue background
            with dark text. Works in both grayscale (L) and RGB modes.

        colored
            Soft pastel backgrounds (light green, pink, yellow, cyan) with dark text.

        dark_mode
            Dark near-black background with light near-white text.

        gradient
            Same bg/text as 'default' but a gradient overlay is applied to the
            canvas *after* rendering (handled in the render pipeline).
            Falls back to default sampling here.

        random
            Randomly selects from all palettes (excluding 'gradient') when
            ``augment=True``; falls back to 'default' when ``augment=False``.

        To disable splitting entirely (100 % train), pass
        ``--split-ratios 100 0 0`` or ``--val-percent 0 --test-percent 0``.
        """
        if not augment:
            bg: int | tuple[int, int, int]
            text: int | tuple[int, int, int]
            if self._pil_mode == "RGB":
                bg = (255, 255, 255)
                text = (0, 0, 0)
            else:
                bg = 255
                text = 0
            return bg, text

        mode = self._bg_color_mode
        if mode == "random":
            mode = random.choice(["default", "paper_tones", "colored", "dark_mode"])

        if mode == "paper_tones":
            palettes = [
                ((248, 243, 230), (20, 15, 10)),  # warm cream
                ((242, 230, 205), (30, 20, 10)),  # aged sepia
                ((225, 225, 220), (25, 25, 30)),  # recycled grey
                ((228, 238, 248), (15, 20, 40)),  # blueprint blue
            ]
            bg_rgb, text_rgb = random.choice(palettes)
            if self._pil_mode == "RGB":
                return bg_rgb, text_rgb
            # Grayscale approximation
            return (
                int(0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2]),
                int(0.299 * text_rgb[0] + 0.587 * text_rgb[1] + 0.114 * text_rgb[2]),
            )

        if mode == "colored":
            palettes = [
                ((230, 248, 230), (20, 40, 20)),  # pastel green
                ((248, 230, 240), (40, 15, 30)),  # pastel pink
                ((248, 248, 215), (35, 35, 10)),  # pastel yellow
                ((220, 240, 248), (15, 30, 45)),  # pastel cyan
            ]
            bg_rgb, text_rgb = random.choice(palettes)
            if self._pil_mode == "RGB":
                return bg_rgb, text_rgb
            return (
                int(0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2]),
                int(0.299 * text_rgb[0] + 0.587 * text_rgb[1] + 0.114 * text_rgb[2]),
            )

        if mode == "dark_mode":
            if self._pil_mode == "RGB":
                bg_rgb = (
                    random.randint(20, 45),
                    random.randint(20, 45),
                    random.randint(25, 50),
                )
                text_rgb = (
                    random.randint(210, 240),
                    random.randint(210, 240),
                    random.randint(215, 245),
                )
                return bg_rgb, text_rgb
            bg_l = random.randint(20, 45)
            text_l = random.randint(210, 240)
            return bg_l, text_l

        # mode == "default" or "gradient" (gradient uses default colors, overlay applied separately)
        if self._pil_mode == "RGB":
            v = random.randint(235, 255)
            t = random.randint(0, 30)
            return (v, v, v), (t, t, t)
        return random.randint(235, 255), random.randint(0, 30)

    # ── Text base rendering ─────────────────────────────────────────────────

    def _render_clean_canvas(
        self,
        text: str,
        font: Any,
        augment: bool,
        has_khmer: bool = False,
        target_height: int | None = None,
    ) -> tuple[np.ndarray, int] | None:
        """Render text on a clean canvas (no augmentation)."""
        try:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            offset_y = -bbox[1]
        except Exception:
            text_w, text_h = font.getmask(text).size
            offset_y = 0

        padding_x = random.randint(10, 30) if augment else 20
        if self.vertical_padding_mode == "random" and target_height:
            ratio = sample_vertical_padding_ratio(self._cfg)
            padding_y = max(1, round(target_height * ratio))
        else:
            padding_y = random.randint(5, 15) if augment else 10
        img_w = max(1, text_w + padding_x * 2)
        img_h = max(1, text_h + padding_y * 2)

        bg_color, text_color = self._sample_bg_and_text_colors(augment)

        img = Image.new(self._pil_mode, (img_w, img_h), color=bg_color)
        draw = ImageDraw.Draw(img)
        x = padding_x + (random.randint(-3, 3) if augment else 0)
        y = padding_y + offset_y + (random.randint(-2, 2) if augment else 0)
        draw.text((x, y), text, font=font, fill=text_color)

        img_array = np.array(img)
        # Return bg as a scalar for compatibility; use 0th channel for RGB
        bg_scalar = bg_color if isinstance(bg_color, int) else bg_color[0]
        return img_array, bg_scalar

    # ── Mixed-font rendering ────────────────────────────────────────────────

    @staticmethod
    def _split_text_into_spans(text: str) -> list[tuple[str, str]]:
        """Split text into contiguous script spans."""
        if not text:
            return []

        def _char_script(c: str) -> str:
            cp = ord(c)
            if (0x1780 <= cp <= 0x17FF) or (0x19E0 <= cp <= 0x19FF):
                return "khmer"
            if (0x41 <= cp <= 0x5A) or (0x61 <= cp <= 0x7A) or (0x30 <= cp <= 0x39):
                return "english"
            return "other"

        spans: list[tuple[str, str]] = []
        cur_script = _char_script(text[0])
        cur_buf = text[0]
        for ch in text[1:]:
            s = _char_script(ch)
            if s == "other" or s == cur_script:
                cur_buf += ch
            else:
                spans.append((cur_buf, cur_script))
                cur_script = s
                cur_buf = ch
        spans.append((cur_buf, cur_script))
        return spans

    def _render_mixed_font(
        self, text: str, augment: bool, has_khmer: bool
    ) -> tuple[np.ndarray, Any] | None:
        """Render with per-span font selection for mixed Khmer/English text."""
        spans = (
            _ra.split_text_spans(text) if _ra.HAS_RUST_ACCEL else self._split_text_into_spans(text)
        )
        if len(spans) <= 1:
            return None

        scripts_present = {s for _, s in spans if s != "other"}
        if len(scripts_present) <= 1:
            return None

        first_script = next((s for _, s in spans if s != "other"), "khmer")
        result = self.font_manager.get_random_font_for_script(first_script)
        if result[0] is None or result[1] is None:
            return None
        base_font, base_size = result

        padding_x = random.randint(10, 30) if augment else 20
        padding_y = random.randint(5, 15) if augment else 10
        bg_color, text_color = self._sample_bg_and_text_colors(augment)

        # Measure spans
        span_texts: list[str] = []
        span_fonts: list[Any] = []
        span_bboxes: list[tuple[int, int, int, int]] = []
        for span_text, script in spans:
            if script == "other" or script == first_script:
                font = base_font
            else:
                alt_result = self.font_manager.get_random_font_for_script(script)
                if alt_result[0] is None:
                    return None
                alt_font, _ = alt_result
                alt_path = getattr(alt_font, "path", None)
                if alt_path:
                    sized = self.font_manager.get_font_by_path_and_size(alt_path, base_size)
                    font = sized if sized is not None else alt_font
                else:
                    font = alt_font

            if not self._is_text_supported(font, span_text):
                return None

            try:
                bbox = font.getbbox(span_text)
            except Exception:
                try:
                    w, h = font.getmask(span_text).size
                    bbox = (0, 0, w, h)
                except Exception:
                    return None

            span_texts.append(span_text)
            span_fonts.append(font)
            span_bboxes.append(bbox)

        total_text_w = sum(b[2] - b[0] for b in span_bboxes)
        max_text_h = max((b[3] - b[1]) for b in span_bboxes) if span_bboxes else 0
        if total_text_w <= 0 or max_text_h <= 0:
            return None

        img_w = total_text_w + padding_x * 2
        img_h = max_text_h + padding_y * 2

        img = Image.new(self._pil_mode, (img_w, img_h), color=bg_color)
        draw = ImageDraw.Draw(img)
        x = padding_x + (random.randint(-3, 3) if augment else 0)
        y_base = padding_y + (random.randint(-2, 2) if augment else 0)

        for span_text, font, bbox in zip(span_texts, span_fonts, span_bboxes, strict=False):
            offset_y = -bbox[1]
            draw.text((x, y_base + offset_y), span_text, font=font, fill=text_color)
            x += bbox[2] - bbox[0]

        return np.array(img), base_font

    # ── Font selection ──────────────────────────────────────────────────────

    def _select_font(self, text: str, target_height: int, retry_limit: int) -> Any | None:
        """Pick a font for *text*, sized proportionally to *target_height* when configured."""
        if self.font_size_mode == "proportional":
            has_khmer = any("ក" <= c <= "៿" for c in text)
            pool = self.font_manager.khmer_fonts if has_khmer else self.font_manager.english_fonts
            if not pool:
                pool = self.font_manager.all_fonts
            if not pool:
                return None
            for _ in range(retry_limit):
                scale = sample_font_scale(self._cfg)
                desired_size = max(8, round(target_height * scale))
                font_path, _, _ = random.choice(pool)
                candidate = self.font_manager.get_font_by_path_and_size(font_path, desired_size)
                if candidate is not None and self._is_text_supported(candidate, text):
                    return candidate
            return None

        for _ in range(retry_limit):
            candidate = self.font_manager.get_random_font(text)
            if candidate and self._is_text_supported(candidate, text):
                return candidate
        return None

    def _sample_target_height(self) -> int:
        return sample_line_height(self._cfg)

    # ── Main render entrypoint ──────────────────────────────────────────────

    def render(
        self,
        text: str,
        augment: bool = True,
        specific_font: Any = None,
        retry_limit: int = 10,
    ) -> np.ndarray | None:
        """Render text to an image.

        Returns a grayscale HxW uint8 array, or None if rendering fails.
        """
        clean = self._render_clean(text, augment, specific_font, retry_limit)
        return clean[0] if clean is not None else None

    def _render_clean(
        self,
        text: str,
        augment: bool,
        specific_font: Any,
        retry_limit: int,
    ) -> tuple[np.ndarray, int, dict[str, Any]] | None:
        """Render text on a clean canvas at a sampled target height.

        Returns `(image, target_height, metadata)` where *metadata* carries
        best-effort font info for the optional metadata sidecar, or `None` if
        rendering fails.
        """
        target_height = self._sample_target_height()

        if specific_font:
            font = self.font_manager.get_font_by_ref(specific_font)
            if font is None or not self._is_text_supported(font, text):
                return None
        else:
            font = self._select_font(text, target_height, retry_limit)
        if font is None:
            return None

        has_khmer = any("ក" <= c <= "៿" for c in text)

        # Try mixed-font rendering
        if (
            not specific_font
            and self.mixed_font_prob > 0.0
            and random.random() < self.mixed_font_prob
        ):
            mixed_result = self._render_mixed_font(text, augment, has_khmer)
            if mixed_result is not None:
                mixed_img, mixed_font = mixed_result
                img = self._resize_to_target(mixed_img, target_height)
                meta = {
                    "font": getattr(mixed_font, "path", None),
                    "font_size": getattr(mixed_font, "size", None),
                }
                return img, target_height, meta

        result = self._render_clean_canvas(text, font, augment, has_khmer, target_height)
        if result is None:
            return None
        img_array, _ = result

        img = self._resize_to_target(img_array, target_height)
        meta = {
            "font": getattr(font, "path", None),
            "font_size": getattr(font, "size", None),
        }
        return img, target_height, meta

    def render_with_one_augmentation(
        self,
        text: str,
        enabled_methods: list[tuple[str, AugMethodConfig]],
        specific_font: Any = None,
        retry_limit: int = 10,
    ) -> tuple[str, np.ndarray, dict[str, Any]] | None:
        """Render text to a clean canvas, then apply exactly one augmentation.

        The augmentation method is chosen probabilistically from *enabled_methods* weighted by each method's `prob` field.
        Returns `(method_name, image, metadata)` or `None` if rendering fails or no method is selected.
        """
        clean_result = self._render_clean(text, False, specific_font, retry_limit)
        if clean_result is None:
            return None
        clean, target_height, meta = clean_result

        # Weighted random selection
        methods = [(n, c) for n, c in enabled_methods if c.enabled and c.prob > 0.0]
        if not methods:
            return None

        names = [n for n, _ in methods]
        weights = [c.prob for _, c in methods]
        total_weight = sum(weights)
        if total_weight <= 0.0:
            return None

        # Normalize and pick one
        r = random.random() * total_weight
        cumulative = 0.0
        chosen_name = names[0]
        chosen_cfg = methods[0][1]
        for name, cfg in methods:
            cumulative += cfg.prob
            if r <= cumulative:
                chosen_name = name
                chosen_cfg = cfg
                break

        intensity = chosen_cfg.sample_intensity()
        aug_img = self._apply_augmentation(clean, chosen_name, intensity, target_height)
        if aug_img is None:
            return None

        meta = {**meta, "width": int(aug_img.shape[1]), "height": int(aug_img.shape[0])}
        return chosen_name, aug_img, meta

    def render_with_augmentations(
        self,
        text: str,
        enabled_methods: list[tuple[str, AugMethodConfig]],
        retry_limit: int = 10,
    ) -> list[tuple[str, np.ndarray, dict[str, Any]]]:
        """Render text to a clean canvas, then produce one image per enabled method.

        Returns a list of `(method_name, image_array, metadata)` tuples.
        Each image has exactly one augmentation applied.
        """
        clean_result = self._render_clean(text, False, None, retry_limit)
        if clean_result is None:
            return []
        clean, target_height, meta = clean_result

        results: list[tuple[str, np.ndarray, dict[str, Any]]] = []
        for method_name, method_cfg in enabled_methods:
            if not method_cfg.enabled:
                continue

            intensity = method_cfg.sample_intensity()
            aug_img = self._apply_augmentation(clean, method_name, intensity, target_height)
            if aug_img is not None:
                sample_meta = {
                    **meta,
                    "width": int(aug_img.shape[1]),
                    "height": int(aug_img.shape[0]),
                }
                results.append((method_name, aug_img, sample_meta))

        return results

    def _apply_augmentation(
        self,
        img: np.ndarray,
        method_name: str,
        intensity: float,
        target_height: int | None = None,
    ) -> np.ndarray | None:
        """Apply a single augmentation method on a copy of *img*."""
        aug_fn = AUG_METHODS.get(method_name)
        if aug_fn is None:
            return None

        try:
            if method_name in _RGB_PREFERRED_METHODS and img.ndim == 2:
                # Grayscale image + RGB-requiring method: convert, augment, convert back
                rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                result = aug_fn(rgb, intensity)
                if result is not None and result.ndim == 3:
                    result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
            else:
                # RGB image or method works on any channel count
                result = aug_fn(img.copy(), intensity)

            return self._resize_to_target(result, target_height)
        except Exception as exc:
            _LOGGER.warning("augmentation %r failed: %s", method_name, exc)
            return None

    # ── Augment existing image (image-dir mode) ─────────────────────────────

    def augment_image(
        self,
        img_array: np.ndarray,
        enabled_methods: list[tuple[str, AugMethodConfig]],
    ) -> list[tuple[str, np.ndarray]]:
        """Apply isolated augmentations to an existing image.

        Returns one image per enabled method.
        """
        results: list[tuple[str, np.ndarray]] = []
        for method_name, method_cfg in enabled_methods:
            if not method_cfg.enabled:
                continue

            intensity = method_cfg.sample_intensity()
            aug_img = self._apply_augmentation(img_array, method_name, intensity)
            if aug_img is not None:
                results.append((method_name, aug_img))

        return results

    # ── Resize to target dimensions ─────────────────────────────────────────

    def _resize_to_target(self, img: np.ndarray, target_height: int | None = None) -> np.ndarray:
        """Resize image to target height, optionally to fixed width.

        *target_height* defaults to `self.image_height` (the fixed-mode canvas
        height); callers on the variable-height path pass the per-sample
        sampled height instead. Scaling (never cropping) the whole canvas to
        this height is what keeps glyphs from ever being clipped: the drawn
        text always fits inside its clean canvas by construction, and a
        uniform resize preserves that.
        """
        h, w = img.shape[:2]
        if h <= 0:
            return img

        th = target_height if target_height is not None else self.image_height
        scale = th / h
        new_w = max(1, round(w * scale))
        img = cv2.resize(img, (new_w, th), interpolation=cv2.INTER_LINEAR)

        if self.image_width is None:
            return img

        if new_w < self.image_width:
            bg_val = self._estimate_bg(img)
            border_val: tuple[float, ...] = (
                (float(bg_val),) if img.ndim == 2 else (float(bg_val),) * img.shape[2]
            )
            x_offset = 0
            if self.random_align_when_padded:
                remaining = self.image_width - new_w
                x_offset = random.choice([0, remaining // 2, remaining])
            left_pad = int(max(0, x_offset))
            right_pad = int(max(0, self.image_width - (x_offset + new_w)))
            img = cv2.copyMakeBorder(
                img,
                top=0,
                bottom=0,
                left=left_pad,
                right=right_pad,
                borderType=cv2.BORDER_CONSTANT,
                value=border_val,
            )
        elif new_w > self.image_width:
            img = cv2.resize(img, (self.image_width, th))

        return img

    @staticmethod
    def _estimate_bg(img: np.ndarray) -> int:
        """Estimate background color from border."""
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
        border = np.concatenate((gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]))
        return int(np.median(border))
