"""Font management and script-aware font selection."""

from __future__ import annotations

import random
from collections import OrderedDict
from pathlib import Path
from typing import Any, ClassVar

from PIL import ImageFont

try:
    from PIL import Image  # noqa: F401

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class FontManager:
    """Load and select fonts for Khmer and English text.

    Font files are expected under `<fonts_dir>/khmer/` and `<fonts_dir>/english/` subdirectories.
    Fonts placed directly in *fonts_dir* are added to both pools as a fallback.

    Supported formats: ttf, otf, ttc, woff, woff2.
    """

    _FONT_EXTENSIONS: ClassVar[set[str]] = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}

    # Sizes each font file is made available at (see `_load_fonts_from`).
    # Registration is metadata-only (path + size, no FreeType face); actual
    # faces are loaded lazily by `get_font_by_path_and_size`.
    _STANDARD_SIZES: ClassVar[list[int]] = [28, 32, 36, 40, 44, 48]

    # Bound on the font-face cache (see `get_font_by_path_and_size`).
    # Every (font_path, size) pair -- proportional sizing's near-continuous
    # scale as well as the standard sizes above -- is loaded lazily on first
    # use; without a cap, a long run (or `font_mode=all`, which touches every
    # font at every standard size) would pin every FreeType face it has ever
    # seen in memory at once, in every process.
    _DYNAMIC_FONT_CACHE_SIZE: ClassVar[int] = 1024

    def __init__(
        self,
        language: str = "mixed",
        fonts_dir: str = "fonts",
        verbose: bool = True,
        dynamic_font_cache_size: int = _DYNAMIC_FONT_CACHE_SIZE,
    ) -> None:
        if not HAS_PIL:
            raise ImportError("Pillow is required. Install with: pip install Pillow")

        self.language = language
        self.fonts_dir = Path(fonts_dir)
        self.verbose = verbose
        self.khmer_fonts: list[tuple[str, int, Any]] = []
        self.english_fonts: list[tuple[str, int, Any]] = []
        self.all_fonts: list[tuple[str, int, Any]] = []
        self._dynamic_font_cache_size = max(0, dynamic_font_cache_size)
        self._dynamic_font_cache: OrderedDict[tuple[str, int], Any] = OrderedDict()
        self._font_styles: dict[str, set[str]] = {}
        self._text_has_khmer_cache: dict[str, bool] = {}
        self._load_fonts()

    @classmethod
    def _collect_font_files(cls, directory: Path) -> list[Path]:
        """Recursively collect font files under *directory*."""
        files: list[Path] = []
        if not directory.exists():
            return files
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in cls._FONT_EXTENSIONS:
                files.append(path)
        return files

    def _load_fonts_from(self, directory: Path, target_list: list) -> int:
        """Register every font file under *directory* into *target_list*.

        Registration only records `(path, size, None)` entries; the actual
        FreeType face is loaded on first use (see `get_font_by_path_and_size`).
        """
        font_paths = self._collect_font_files(directory)
        added = 0
        for font_path in font_paths:
            for size in self._STANDARD_SIZES:
                entry = (str(font_path), size, None)
                target_list.append(entry)
                self.all_fonts.append(entry)
                added += 1
        return added

    def _load_fonts(self) -> None:
        """Load fonts from khmer/ and english/ subdirectories."""
        if self.verbose:
            print(f"\nLoading fonts from: {self.fonts_dir.absolute()}")

        if not self.fonts_dir.exists():
            print(f"  Warning: Fonts directory not found: {self.fonts_dir}")
            print("  Creating directory structure...")
            (self.fonts_dir / "khmer").mkdir(parents=True, exist_ok=True)
            (self.fonts_dir / "english").mkdir(parents=True, exist_ok=True)
            print("\n  No fonts found!")
            print(f"    Khmer   → {(self.fonts_dir / 'khmer').absolute()}")
            print(f"    English → {(self.fonts_dir / 'english').absolute()}")
            return

        khmer_dir = self.fonts_dir / "khmer"
        english_dir = self.fonts_dir / "english"

        _ = self._load_fonts_from(khmer_dir, self.khmer_fonts)
        _ = self._load_fonts_from(english_dir, self.english_fonts)

        # Fallback: fonts placed directly in fonts_dir go to both pools
        root_font_paths = [
            p for p in self._collect_font_files(self.fonts_dir) if p.parent == self.fonts_dir
        ]
        n_root = 0
        if root_font_paths:
            for font_path in root_font_paths:
                for size in self._STANDARD_SIZES:
                    entry = (str(font_path), size, None)
                    self.khmer_fonts.append(entry)
                    self.english_fonts.append(entry)
                    self.all_fonts.append(entry)
                    n_root += 1

        if not self.all_fonts:
            print("\n  No font files found.")
            print(
                f"  Please add fonts to:\n    Khmer   -> {khmer_dir.absolute()}\n    English -> {english_dir.absolute()}"
            )
            return

        if self.verbose:
            print("\n  Font Summary:")
            print(f"    Total entries  : {len(self.all_fonts)} (across all sizes)")
            print(f"    Khmer entries  : {len(self.khmer_fonts)}")
            print(f"    English entries: {len(self.english_fonts)}")

    def _text_has_khmer(self, text: str) -> bool:
        """Check if *text* contains any Khmer Unicode characters."""
        cached = self._text_has_khmer_cache.get(text)
        if cached is not None:
            return cached
        result = any("ក" <= c <= "៿" for c in text)
        if len(self._text_has_khmer_cache) >= 100_000:
            self._text_has_khmer_cache.clear()
        self._text_has_khmer_cache[text] = result
        return result

    def _pool_for(self, text: str) -> list:
        """Return the script-appropriate font-entry pool for *text*."""
        has_khmer = self._text_has_khmer(text)
        if has_khmer and self.khmer_fonts:
            return self.khmer_fonts
        if not has_khmer and self.english_fonts:
            return self.english_fonts
        return self.all_fonts

    @staticmethod
    def _detect_font_style(font_path: str) -> set[str]:
        """Detect bold/italic style tags for a font file from its name + filename."""
        tags: set[str] = set()
        stem = Path(font_path).stem.lower()
        if "bold" in stem:
            tags.add("bold")
        if "italic" in stem or "oblique" in stem:
            tags.add("italic")
        try:
            style_name = ImageFont.truetype(font_path, 28).getname()[1]
            style = style_name.lower() if style_name else ""
            if "bold" in style:
                tags.add("bold")
            if "italic" in style or "oblique" in style:
                tags.add("italic")
        except Exception:
            pass
        return tags

    def _style_tags(self, font_path: str) -> set[str]:
        """Cached style tags for a font path (see `_detect_font_style`)."""
        tags = self._font_styles.get(font_path)
        if tags is None:
            tags = self._detect_font_style(font_path)
            self._font_styles[font_path] = tags
        return tags

    def random_font_path_with_style(self, text: str, styles: set[str]) -> str | None:
        """Random font *path* from the script-appropriate pool whose style matches *styles*.

        - ``{"bold"}`` -> any font tagged bold (a bold-italic font qualifies).
        - ``{"italic"}`` -> any font tagged italic/oblique.
        - ``{"bold", "italic"}`` -> prefer a font tagged both, else a bold font.
        Returns ``None`` when no match exists.
        """
        if not styles:
            return None
        pool = self._pool_for(text)

        def _paths(required: set[str]) -> list[str]:
            return sorted({entry[0] for entry in pool if required <= self._style_tags(entry[0])})

        if styles == {"bold", "italic"}:
            both = _paths({"bold", "italic"})
            if both:
                return random.choice(both)
            bold = _paths({"bold"})
            if bold:
                return random.choice(bold)
            return None

        matches = _paths(styles)
        return random.choice(matches) if matches else None

    def get_random_font(self, text: str) -> Any:
        """Get a random font appropriate for *text*."""
        pool = self._pool_for(text)
        if not pool:
            return None
        path, size, _ = random.choice(pool)
        return self.get_font_by_path_and_size(path, size)

    def get_random_font_for_script(self, script: str) -> tuple[Any, int] | tuple[None, None]:
        """Get a random font for a specific script ('khmer' or 'english')."""
        if script == "khmer" and self.khmer_fonts:
            path, size, _ = random.choice(self.khmer_fonts)
        elif script == "english" and self.english_fonts:
            path, size, _ = random.choice(self.english_fonts)
        elif self.all_fonts:
            path, size, _ = random.choice(self.all_fonts)
        else:
            return None, None
        return self.get_font_by_path_and_size(path, size), size

    def get_font_by_ref(self, font_ref: Any) -> Any:
        """Resolve a `(path, size)` reference back to a font, loading lazily."""
        if (
            isinstance(font_ref, tuple)
            and len(font_ref) >= 2
            and font_ref[0] is not None
            and font_ref[1] is not None
        ):
            return self.get_font_by_path_and_size(str(font_ref[0]), int(font_ref[1]))
        return font_ref

    def get_font_by_path_and_size(self, font_path: str, size: int) -> Any:
        """Get font by path and size, loading and caching lazily.

        Every (font_path, size) pair -- including the standard sizes each
        font is registered at by `_load_fonts` -- is loaded on first use and
        served from a bounded LRU cache, so neither a long run nor
        `font_mode=all` (which touches every font at every standard size)
        can pin every FreeType face in memory at once.
        """
        key = (str(font_path), int(size))
        if key in self._dynamic_font_cache:
            self._dynamic_font_cache.move_to_end(key)
            return self._dynamic_font_cache[key]
        try:
            font = ImageFont.truetype(str(font_path), int(size))
        except Exception:
            return None
        if self._dynamic_font_cache_size > 0:
            self._dynamic_font_cache[key] = font
            self._dynamic_font_cache.move_to_end(key)
            while len(self._dynamic_font_cache) > self._dynamic_font_cache_size:
                self._dynamic_font_cache.popitem(last=False)
        return font
