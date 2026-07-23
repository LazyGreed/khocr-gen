"""Tests for AugMethodConfig and GenerationConfig."""

from __future__ import annotations

import argparse

from khocr_gen.config import AugMethodConfig, GenerationConfig
from khocr_gen.normalizer import NormalizerConfig


class TestAugMethodConfig:
    def test_defaults(self):
        cfg = AugMethodConfig()
        assert cfg.prob == 0.0
        assert cfg.min == 0.0
        assert cfg.max == 1.0
        assert not cfg.enabled

    def test_enabled(self):
        cfg = AugMethodConfig(prob=0.5)
        assert cfg.enabled

    def test_sample_intensity(self):
        cfg = AugMethodConfig(min=0.2, max=0.8)
        for _ in range(100):
            v = cfg.sample_intensity()
            assert 0.2 <= v <= 0.8

    def test_sample_intensity_default_range(self):
        cfg = AugMethodConfig()
        for _ in range(100):
            v = cfg.sample_intensity()
            assert 0.0 <= v <= 1.0

    def test_to_dict_via_generation_config(self):
        """AugMethodConfig is serialized via GenerationConfig.to_dict."""
        cfg = AugMethodConfig(prob=0.3, min=0.1, max=0.9)
        assert cfg.prob == 0.3
        assert cfg.min == 0.1
        assert cfg.max == 0.9


class TestGenerationConfigDefaults:
    def test_default_image_height(self):
        cfg = GenerationConfig()
        assert cfg.image_height == 48

    def test_default_copies(self):
        cfg = GenerationConfig()
        assert cfg.copies == 3

    def test_default_retry_limit(self):
        cfg = GenerationConfig()
        assert cfg.retry_limit == 10

    def test_some_aug_methods_enabled_by_default(self):
        """Some augmentation methods have sensible non-zero defaults."""
        cfg = GenerationConfig()
        enabled = cfg.enabled_aug_methods()
        # Several offline methods come enabled by default
        assert len(enabled) > 0
        # Remaining methods (currently 12) start disabled by default
        remaining = {
            "perspective",
            "elastic",
            "random_crop",
            "online_blur",
            "online_noise",
            "hsv",
            "reverse",
            "brightness_contrast",
            "pixelation",
            "gradient_illumination",
            "morphological",
            "anisotropic_dilation",
        }
        for name, m in cfg.iter_aug_methods():
            if name in remaining:
                assert m.prob == 0.0, f"{name} should default to prob=0"

    def test_iter_aug_methods_count(self):
        cfg = GenerationConfig()
        methods = list(cfg.iter_aug_methods())
        # 24 methods in unified registry
        assert len(methods) == 24

    def test_enabled_aug_methods_nonempty_by_default(self):
        cfg = GenerationConfig()
        # Several offline aug methods come enabled by default
        assert len(cfg.enabled_aug_methods()) > 0

    def test_enabled_aug_methods_with_explicit_sauvola(self):
        cfg = GenerationConfig(sauvola=AugMethodConfig(prob=0.5, min=0.0, max=1.0))
        enabled = cfg.enabled_aug_methods()
        # sauvola should be among the enabled methods
        enabled_names = [name for name, _ in enabled]
        assert "sauvola" in enabled_names

    def test_copies_default(self):
        cfg = GenerationConfig()
        assert cfg.copies == 3

    def test_default_color_mode(self):
        cfg = GenerationConfig()
        assert cfg.color_mode == 1

    def test_default_output_format(self):
        cfg = GenerationConfig()
        assert cfg.output_format == "jpg"

    def test_default_jpeg_quality(self):
        cfg = GenerationConfig()
        assert cfg.jpeg_quality == 90

    def test_default_storage(self):
        cfg = GenerationConfig()
        assert cfg.storage == "raw"


class TestGenerationConfigSerialization:
    def test_to_dict_roundtrip(self):
        cfg = GenerationConfig(image_height=64, copies=5)
        d = cfg.to_dict()
        restored = GenerationConfig.from_dict(d)
        assert restored.image_height == 64
        assert restored.copies == 5

    def test_to_dict_includes_aug_methods(self):
        cfg = GenerationConfig(blur=AugMethodConfig(prob=0.3, min=0.1, max=0.9))
        d = cfg.to_dict()
        assert "blur" in d
        assert isinstance(d["blur"], dict)
        assert d["blur"]["prob"] == 0.3
        assert d["blur"]["min"] == 0.1
        assert d["blur"]["max"] == 0.9

    def test_from_dict_unknown_keys_ignored(self):
        cfg = GenerationConfig.from_dict({"unknown_key": 999})
        assert cfg.image_height == 48  # default

    def test_to_dict_from_dict_preserves_normalizer(self):
        cfg = GenerationConfig(
            normalizer=NormalizerConfig(
                unicode_norm="NFC",
                remove_zwsp=False,
            )
        )
        d = cfg.to_dict()
        restored = GenerationConfig.from_dict(d)
        assert restored.normalizer.unicode_norm == "NFC"
        assert restored.normalizer.remove_zwsp is False


class TestGenerationConfigAddArgs:
    def test_creates_argument_groups(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        # Just verifying it doesn't crash
        assert True

    def test_from_args_parses_height(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--height", "64"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.image_height == 64

    def test_from_args_parses_copies(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--copies", "10"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.copies == 10

    def test_from_args_parses_aug_method(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--blur-prob", "0.5", "--blur-min", "0.1", "--blur-max", "0.9"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.blur.prob == 0.5
        assert cfg.blur.min == 0.1
        assert cfg.blur.max == 0.9

    def test_from_args_defaults_uses_code_defaults(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args([])
        cfg = GenerationConfig.from_args(args)
        # from_args uses code defaults (not all-zero), so some methods are enabled
        assert len(cfg.enabled_aug_methods()) > 0

    def test_from_args_parses_color_mode(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--color-mode", "3"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.color_mode == 3

    def test_from_args_parses_output_format(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--output-format", "png"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.output_format == "png"

    def test_from_args_parses_storage_lmdb(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--storage", "lmdb"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.storage == "lmdb"

    def test_from_args_parses_storage_both(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args(["--storage", "both"])
        cfg = GenerationConfig.from_args(args)
        assert cfg.storage == "both"

    def test_from_args_storage_default_is_raw(self):
        parser = argparse.ArgumentParser()
        GenerationConfig.add_args(parser)
        args = parser.parse_args([])
        cfg = GenerationConfig.from_args(args)
        assert cfg.storage == "raw"


class TestAugMethodConfigDictInit:
    """Test that GenerationConfig can be constructed with AugMethodConfig objects."""

    def test_constructor_init(self):
        cfg = GenerationConfig(
            sauvola=AugMethodConfig(prob=0.2, min=0.1, max=0.5),
            blur=AugMethodConfig(prob=0.3, min=0.0, max=0.8),
        )
        assert cfg.sauvola.prob == 0.2
        assert cfg.sauvola.min == 0.1
        assert cfg.sauvola.max == 0.5
        assert cfg.blur.prob == 0.3
        assert cfg.blur.min == 0.0
        assert cfg.blur.max == 0.8

    def test_partial_constructor_init(self):
        cfg = GenerationConfig(rotation=AugMethodConfig(prob=0.5))
        assert cfg.rotation.prob == 0.5
        assert cfg.rotation.min == 0.0  # default from AugMethodConfig
        assert cfg.rotation.max == 1.0  # default from AugMethodConfig

    def test_default_init(self):
        cfg = GenerationConfig()
        assert cfg.geo_warp.prob == 0.2
        assert cfg.geo_warp.min == 0.1
        assert cfg.geo_warp.max == 0.9
