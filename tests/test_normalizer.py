"""Tests for the normalizer module — wraps khmernormalizer."""

from __future__ import annotations

import argparse

from khocr_gen.normalizer import NormalizerConfig, normalize


class TestNormalizerConfig:
    def test_defaults(self):
        cfg = NormalizerConfig()
        assert cfg.unicode_norm == ""
        assert cfg.emoji_replacement == ""
        assert cfg.url_replacement == ""
        assert cfg.remove_zwsp is True
        assert cfg.passthrough is False

    def test_passthrough_mode(self):
        cfg = NormalizerConfig(passthrough=True)
        assert cfg.passthrough is True

    def test_to_dict(self):
        cfg = NormalizerConfig(unicode_norm="NFC", remove_zwsp=False)
        d = cfg.to_dict()
        assert d["unicode_norm"] == "NFC"
        assert d["remove_zwsp"] is False

    def test_from_dict(self):
        d = {"unicode_norm": "NFD", "remove_zwsp": False, "emoji_replacement": ""}
        cfg = NormalizerConfig.from_dict(d)
        assert cfg.unicode_norm == "NFD"
        assert cfg.remove_zwsp is False

    def test_from_dict_unknown_keys_ignored(self):
        cfg = NormalizerConfig.from_dict({"unknown": True})
        assert cfg.unicode_norm == ""  # default

    def test_to_fix_text_config(self):
        cfg = NormalizerConfig(unescape_html="auto", fix_encoding=True)
        ft = cfg.to_fix_text_config()
        assert ft is not None
        assert ft.unescape_html == "auto"
        assert ft.fix_encoding is True

    def test_to_fix_text_config_passthrough(self):
        cfg = NormalizerConfig(passthrough=True)
        # In passthrough mode, to_fix_text_config may still return a config;
        # the passthrough flag is handled by normalize() instead
        result = cfg.to_fix_text_config()
        assert result is not None


class TestNormalizerAddArgs:
    def test_adds_arguments(self):
        parser = argparse.ArgumentParser()
        NormalizerConfig.add_args(parser)
        args = parser.parse_args([])
        assert hasattr(args, "norm_unicode_norm")

    def test_adds_arguments_with_prefix(self):
        parser = argparse.ArgumentParser()
        NormalizerConfig.add_args(parser, prefix="--my-")
        args = parser.parse_args([])
        assert hasattr(args, "my_unicode_norm")

    def test_from_args_reads_values(self):
        parser = argparse.ArgumentParser()
        NormalizerConfig.add_args(parser)
        args = parser.parse_args(["--norm-unicode-norm", "NFC", "--norm-no-remove-zwsp"])
        cfg = NormalizerConfig.from_args(args)
        assert cfg.unicode_norm == "NFC"
        assert cfg.remove_zwsp is False  # --norm-no-remove-zwsp sets to False

    def test_from_args_with_prefix(self):
        parser = argparse.ArgumentParser()
        NormalizerConfig.add_args(parser, prefix="--my-")
        args = parser.parse_args(["--my-unicode-norm", "NFD"])
        cfg = NormalizerConfig.from_args(args, prefix="my_")
        assert cfg.unicode_norm == "NFD"


class TestNormalize:
    def test_passthrough_returns_original(self):
        cfg = NormalizerConfig(passthrough=True)
        result = normalize("Hello សួស្តី", cfg)
        assert result == "Hello សួស្តី"

    def test_normalize_english(self):
        cfg = NormalizerConfig()
        result = normalize("Hello World!", cfg)
        # Should be at least the same length (normalization may change Unicode forms)
        assert len(result) > 0

    def test_normalize_khmer(self):
        cfg = NormalizerConfig()
        result = normalize("សួស្តី", cfg)
        assert len(result) > 0

    def test_normalize_mixed(self):
        cfg = NormalizerConfig()
        result = normalize("Hello សួស្តី 123", cfg)
        assert len(result) > 0
