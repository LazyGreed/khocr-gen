"""Tests for variable line-height sampling and validation."""

from __future__ import annotations

import random

import pytest

from khocr_gen.config import GenerationConfig
from khocr_gen.errors import InputValidationError
from khocr_gen.line_height import (
    resolve_height_buckets,
    sample_font_scale,
    sample_line_height,
    sample_vertical_padding_ratio,
    validate_line_height_config,
)


def _cfg(**overrides) -> GenerationConfig:
    return GenerationConfig(**overrides)


class TestSampleLineHeightFixed:
    def test_fixed_mode_always_returns_image_height(self):
        cfg = _cfg(line_height_mode="fixed", image_height=48)
        rng = random.Random(1)
        heights = {sample_line_height(cfg, rng) for _ in range(20)}
        assert heights == {48}

    def test_fixed_mode_ignores_min_max(self):
        cfg = _cfg(
            line_height_mode="fixed", image_height=48, min_line_height=10, max_line_height=200
        )
        assert sample_line_height(cfg) == 48


class TestSampleLineHeightVariable:
    def test_stays_within_bounds(self):
        cfg = _cfg(
            line_height_mode="variable", min_line_height=32, max_line_height=96, line_height_step=8
        )
        rng = random.Random(0)
        for _ in range(500):
            h = sample_line_height(cfg, rng)
            assert 32 <= h <= 96

    def test_produces_more_than_one_distinct_height(self):
        cfg = _cfg(line_height_mode="variable", min_line_height=32, max_line_height=96)
        rng = random.Random(0)
        heights = {sample_line_height(cfg, rng) for _ in range(50)}
        assert len(heights) > 1

    def test_heights_aligned_to_step(self):
        cfg = _cfg(
            line_height_mode="variable", min_line_height=32, max_line_height=96, line_height_step=8
        )
        rng = random.Random(3)
        for _ in range(200):
            h = sample_line_height(cfg, rng)
            assert (h - 32) % 8 == 0

    def test_same_seed_gives_same_sequence(self):
        cfg = _cfg(line_height_mode="variable", min_line_height=32, max_line_height=96)
        seq1 = [sample_line_height(cfg, random.Random(42)) for _ in range(30)]
        seq2 = [sample_line_height(cfg, random.Random(42)) for _ in range(30)]
        assert seq1 == seq2

    def test_different_seeds_can_differ(self):
        cfg = _cfg(line_height_mode="variable", min_line_height=32, max_line_height=96)
        seq1 = [sample_line_height(cfg, random.Random(1)) for _ in range(30)]
        seq2 = [sample_line_height(cfg, random.Random(2)) for _ in range(30)]
        assert seq1 != seq2

    def test_triangular_distribution_clusters_near_peak(self):
        cfg = _cfg(
            line_height_mode="variable",
            min_line_height=32,
            max_line_height=96,
            line_height_step=1,
            line_height_distribution="triangular",
            default_line_height=48,
        )
        rng = random.Random(5)
        heights = [sample_line_height(cfg, rng) for _ in range(2000)]
        near_peak = sum(1 for h in heights if 40 <= h <= 56)
        # A uniform distribution would put ~25% of mass in this 16px window
        # out of the 64px range; triangular clustering should exceed that.
        assert near_peak / len(heights) > 0.35


class TestSampleLineHeightBucketed:
    def test_only_returns_bucket_values(self):
        cfg = _cfg(
            line_height_mode="bucketed", min_line_height=32, max_line_height=96, line_height_step=16
        )
        expected = set(resolve_height_buckets(cfg))
        rng = random.Random(9)
        for _ in range(200):
            assert sample_line_height(cfg, rng) in expected

    def test_resolve_height_buckets_includes_max_even_if_not_aligned(self):
        cfg = _cfg(min_line_height=32, max_line_height=90, line_height_step=16)
        buckets = resolve_height_buckets(cfg)
        assert buckets[0] == 32
        assert buckets[-1] == 90


class TestSampleFontScale:
    def test_fixed_font_size_mode_returns_one(self):
        cfg = _cfg(font_size_mode="fixed", min_font_scale=0.5, max_font_scale=0.6)
        assert sample_font_scale(cfg) == 1.0

    def test_proportional_within_bounds(self):
        cfg = _cfg(font_size_mode="proportional", min_font_scale=0.65, max_font_scale=0.9)
        rng = random.Random(0)
        for _ in range(200):
            scale = sample_font_scale(cfg, rng)
            assert 0.65 <= scale <= 0.9


class TestSampleVerticalPaddingRatio:
    def test_fixed_mode_returns_zero(self):
        cfg = _cfg(vertical_padding_mode="fixed")
        assert sample_vertical_padding_ratio(cfg) == 0.0

    def test_random_mode_within_bounds(self):
        cfg = _cfg(
            vertical_padding_mode="random",
            min_vertical_padding_ratio=0.04,
            max_vertical_padding_ratio=0.18,
        )
        rng = random.Random(0)
        for _ in range(200):
            ratio = sample_vertical_padding_ratio(cfg, rng)
            assert 0.04 <= ratio <= 0.18


class TestValidateLineHeightConfig:
    def test_valid_default_config_passes(self):
        validate_line_height_config(_cfg())

    def test_min_line_height_must_be_positive(self):
        with pytest.raises(InputValidationError, match="--min-line-height"):
            validate_line_height_config(_cfg(min_line_height=0))

    def test_max_must_be_gte_min(self):
        with pytest.raises(InputValidationError, match="--max-line-height"):
            validate_line_height_config(_cfg(min_line_height=96, max_line_height=32))

    def test_step_must_be_positive(self):
        with pytest.raises(InputValidationError, match="--line-height-step"):
            validate_line_height_config(_cfg(line_height_step=0))

    def test_invalid_mode_rejected(self):
        with pytest.raises(InputValidationError, match="--line-height-mode"):
            validate_line_height_config(_cfg(line_height_mode="bogus"))

    def test_invalid_distribution_rejected(self):
        with pytest.raises(InputValidationError, match="--line-height-distribution"):
            validate_line_height_config(_cfg(line_height_distribution="bogus"))

    def test_font_scale_bounds(self):
        with pytest.raises(InputValidationError, match="--min-font-scale"):
            validate_line_height_config(_cfg(min_font_scale=0))
        with pytest.raises(InputValidationError, match="--max-font-scale"):
            validate_line_height_config(_cfg(min_font_scale=0.9, max_font_scale=0.5))

    def test_padding_ratio_bounds(self):
        with pytest.raises(InputValidationError, match="--min-vertical-padding-ratio"):
            validate_line_height_config(_cfg(min_vertical_padding_ratio=-0.1))
        with pytest.raises(InputValidationError, match="--max-vertical-padding-ratio"):
            validate_line_height_config(
                _cfg(min_vertical_padding_ratio=0.3, max_vertical_padding_ratio=0.1)
            )
        with pytest.raises(InputValidationError, match="--max-vertical-padding-ratio"):
            validate_line_height_config(_cfg(max_vertical_padding_ratio=0.6))
