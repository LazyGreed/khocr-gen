"""Khmer text normalization via khmernormalizer.

Wraps https://github.com/seanghay/khmernormalizer with configurable parameters exposed to the CLI and config file,
so users can tune normalization for their corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_HAS_KHMER_NORMALIZER = False
_normalize_fn: Any = None
_TextFixerConfig: Any = None


def _ensure_backend() -> tuple[Any, Any]:
    global _HAS_KHMER_NORMALIZER, _normalize_fn, _TextFixerConfig
    if _HAS_KHMER_NORMALIZER:
        return _normalize_fn, _TextFixerConfig

    try:
        from khmernormalizer import TextFixerConfig as _TFC
        from khmernormalizer import normalize as _nf

        _normalize_fn = _nf
        _TextFixerConfig = _TFC
        _HAS_KHMER_NORMALIZER = True
    except ImportError as exc:
        raise ImportError(
            "khmernormalizer is required for text normalization. "
            "Install with: pip install khmernormalizer"
        ) from exc
    return _normalize_fn, _TextFixerConfig


@dataclass
class NormalizerConfig:
    """Parameters for Khmer text normalization.

    All parameters map directly to `khmernormalizer.normalize` kwargs.
    """

    unicode_norm: str = ""
    emoji_replacement: str | None = ""
    url_replacement: str | None = ""
    remove_zwsp: bool = True

    # ftfy TextFixerConfig fields
    unescape_html: str = "auto"
    remove_terminal_escapes: bool = True
    fix_encoding: bool = True
    restore_byte_a0: bool = True
    replace_lossy_sequences: bool = True
    decode_inconsistent_utf8: bool = True
    fix_c1_controls: bool = True
    fix_latin_ligatures: bool = True
    fix_character_width: bool = True
    uncurl_quotes: bool = True
    fix_line_breaks: bool = True
    fix_surrogates: bool = True
    remove_control_chars: bool = True
    normalization: str = "NFC"
    max_decode_length: int = 1_000_000
    explain: bool = False

    # Shorthand for "apply no normalization at all"
    passthrough: bool = False

    def to_fix_text_config(self) -> Any:
        """Build a `TextFixerConfig` from this config."""
        _, TFC = _ensure_backend()
        return TFC(
            unescape_html=self.unescape_html,
            remove_terminal_escapes=self.remove_terminal_escapes,
            fix_encoding=self.fix_encoding,
            restore_byte_a0=self.restore_byte_a0,
            replace_lossy_sequences=self.replace_lossy_sequences,
            decode_inconsistent_utf8=self.decode_inconsistent_utf8,
            fix_c1_controls=self.fix_c1_controls,
            fix_latin_ligatures=self.fix_latin_ligatures,
            fix_character_width=self.fix_character_width,
            uncurl_quotes=self.uncurl_quotes,
            fix_line_breaks=self.fix_line_breaks,
            fix_surrogates=self.fix_surrogates,
            remove_control_chars=self.remove_control_chars,
            normalization=self.normalization,
            max_decode_length=self.max_decode_length,
            explain=self.explain,
        )

    @staticmethod
    def add_args(parser: Any, *, prefix: str = "--norm-") -> None:
        """Register normalizer flags on an argparse parser.

        Args:
            parser: An `argparse.ArgumentParser` or argument group.
            prefix: Prefix for flag names (default ``--norm-``).
        """
        g = parser.add_argument_group("Text normalization (khmernormalizer)")
        g.add_argument(
            f"{prefix}unicode-norm",
            default="",
            choices=["NFKC", "NFC", "NFD", "NFKD", "none"],
            help="Unicode normalization form (default: none). khmernormalizer already normalizes internally.",
        )
        g.add_argument(
            f"{prefix}emoji-replacement",
            default="",
            metavar="STR",
            help="Replacement string for emoji characters (default: '' = remove)",
        )
        g.add_argument(
            f"{prefix}url-replacement",
            default="",
            metavar="STR",
            help="Replacement string for URLs (default: '' = remove)",
        )
        g.add_argument(
            f"{prefix}no-remove-zwsp",
            action="store_true",
            help="Keep zero-width spaces instead of removing them",
        )
        g.add_argument(
            f"{prefix}no-fix-encoding",
            action="store_true",
            help="Disable ftfy encoding fixes",
        )
        g.add_argument(
            f"{prefix}no-uncurl-quotes",
            action="store_true",
            help="Disable quote uncurling",
        )
        g.add_argument(
            f"{prefix}no-fix-line-breaks",
            action="store_true",
            help="Disable line break normalization",
        )
        g.add_argument(
            f"{prefix}passthrough",
            action="store_true",
            help="Skip all normalization (text passes through unchanged)",
        )

    @classmethod
    def from_args(cls, args: Any, *, prefix: str = "norm_") -> NormalizerConfig:
        """Build a `NormalizerConfig` from parsed CLI args."""

        def _get(name: str) -> Any:
            return getattr(args, f"{prefix}{name}", None)

        unicode_norm_val = _get("unicode_norm")
        if unicode_norm_val and str(unicode_norm_val).lower() == "none":
            unicode_norm_val = ""

        return cls(
            unicode_norm=unicode_norm_val if unicode_norm_val else "",
            emoji_replacement=_get("emoji_replacement"),
            url_replacement=_get("url_replacement"),
            remove_zwsp=not bool(_get("no_remove_zwsp")),
            fix_encoding=not bool(_get("no_fix_encoding")),
            uncurl_quotes=not bool(_get("no_uncurl_quotes")),
            fix_line_breaks=not bool(_get("no_fix_line_breaks")),
            passthrough=bool(_get("passthrough")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for IPC."""
        return {
            "unicode_norm": self.unicode_norm,
            "emoji_replacement": self.emoji_replacement,
            "url_replacement": self.url_replacement,
            "remove_zwsp": self.remove_zwsp,
            "fix_text_config": self.to_fix_text_config(),
            "passthrough": self.passthrough,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizerConfig:
        """Reconstruct from a dict."""
        return cls(
            unicode_norm=d.get("unicode_norm", ""),
            emoji_replacement=d.get("emoji_replacement", ""),
            url_replacement=d.get("url_replacement", ""),
            remove_zwsp=d.get("remove_zwsp", True),
            passthrough=d.get("passthrough", False),
        )


def normalize(text: str, cfg: NormalizerConfig | None = None) -> str:
    """Normalize Khmer text.

    Args:
        text: Raw input text.
        cfg: Normalizer config. If *None*, a default `NormalizerConfig` is used.

    Returns:
        Normalized text, or the original text if `cfg.passthrough` is `True`.
    """
    if cfg is None:
        cfg = NormalizerConfig()

    if cfg.passthrough:
        return text

    nf, _ = _ensure_backend()

    kwargs: dict[str, Any] = {}
    if cfg.unicode_norm:
        kwargs["unicode_norm"] = cfg.unicode_norm

    kwargs["emoji_replacement"] = cfg.emoji_replacement
    kwargs["url_replacement"] = cfg.url_replacement
    kwargs["remove_zwsp"] = cfg.remove_zwsp
    kwargs["fix_text_config"] = cfg.to_fix_text_config()

    return nf(text, **kwargs)
