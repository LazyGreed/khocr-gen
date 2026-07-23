"""Font management and script-aware font selection."""

from __future__ import annotations

import random
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

    def __init__(self, language: str = "mixed", fonts_dir: str = "fonts") -> None:
        if not HAS_PIL:
            raise ImportError("Pillow is required. Install with: pip install Pillow")

        self.language = language
        self.fonts_dir = Path(fonts_dir)
        self.khmer_fonts: list[tuple[str, int, Any]] = []
        self.english_fonts: list[tuple[str, int, Any]] = []
        self.all_fonts: list[tuple[str, int, Any]] = []
        self._font_lookup: dict[tuple[str, int], Any] = {}
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
        """Load every font file under *directory* into *target_list*."""
        font_paths = self._collect_font_files(directory)
        added = 0
        for font_path in font_paths:
            for size in [28, 32, 36, 40, 44, 48]:
                try:
                    font = ImageFont.truetype(str(font_path), size)
                    entry = (str(font_path), size, font)
                    target_list.append(entry)
                    self.all_fonts.append(entry)
                    self._font_lookup[(str(font_path), size)] = font
                    added += 1
                except Exception:
                    pass
        return added

    def _load_fonts(self) -> None:
        """Load fonts from khmer/ and english/ subdirectories."""
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
                for size in [28, 32, 36, 40, 44, 48]:
                    try:
                        font = ImageFont.truetype(str(font_path), size)
                        entry = (str(font_path), size, font)
                        self.khmer_fonts.append(entry)
                        self.english_fonts.append(entry)
                        self.all_fonts.append(entry)
                        self._font_lookup[(str(font_path), size)] = font
                        n_root += 1
                    except Exception:
                        pass

        if not self.all_fonts:
            print("\n  No font files found.")
            print(
                f"  Please add fonts to:\n    Khmer   -> {khmer_dir.absolute()}\n    English -> {english_dir.absolute()}"
            )
            return

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

    def get_random_font(self, text: str) -> Any:
        """Get a random font appropriate for *text*."""
        has_khmer = self._text_has_khmer(text)
        if has_khmer and self.khmer_fonts:
            pool = self.khmer_fonts
        elif not has_khmer and self.english_fonts:
            pool = self.english_fonts
        else:
            pool = self.all_fonts
        if not pool:
            return None
        _, _, font = random.choice(pool)
        return font

    def get_random_font_for_script(self, script: str) -> tuple[Any, int] | tuple[None, None]:
        """Get a random font for a specific script ('khmer' or 'english')."""
        if script == "khmer" and self.khmer_fonts:
            _, size, font = random.choice(self.khmer_fonts)
            return font, size
        elif script == "english" and self.english_fonts:
            _, size, font = random.choice(self.english_fonts)
            return font, size
        elif self.all_fonts:
            _, size, font = random.choice(self.all_fonts)
            return font, size
        return None, None

    def get_font_by_ref(self, font_ref: Any) -> Any:
        """Resolve a `(path, size)` reference back to a loaded font."""
        if (
            isinstance(font_ref, tuple)
            and len(font_ref) >= 2
            and font_ref[0] is not None
            and font_ref[1] is not None
        ):
            return self._font_lookup.get((str(font_ref[0]), int(font_ref[1])))
        return font_ref

    def get_font_by_path_and_size(self, font_path: str, size: int) -> Any:
        """Get font by path and size, loading and caching dynamically."""
        key = (str(font_path), int(size))
        if key in self._font_lookup:
            return self._font_lookup[key]
        try:
            font = ImageFont.truetype(str(font_path), int(size))
            self._font_lookup[key] = font
            return font
        except Exception:
            return None
