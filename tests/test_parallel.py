"""Tests for parallel worker utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from khocr_gen.config import GenerationConfig, TextDecorationConfig
from khocr_gen.parallel import (
    _init_render_worker,
    _render_sample_batch,
    resolve_chunk_size,
    resolve_mp_context,
    resolve_worker_count,
)

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_HAS_REAL_FONTS = (_FONTS_DIR / "khmer").is_dir() and any((_FONTS_DIR / "khmer").iterdir())


class TestResolveWorkerCount:
    def test_negative_workers_treated_as_auto(self):
        """Negative workers gets clamped to 0 (auto), which may return cpu_count."""
        result = resolve_worker_count(-1, 10_000)
        # With enough samples, auto resolves to cpu_count
        assert result >= 1

    def test_explicit_one(self):
        result = resolve_worker_count(1, 10_000)
        assert result == 1

    def test_explicit_more_than_cpu(self):
        cpu_count = os.cpu_count() or 1
        result = resolve_worker_count(999, 10_000)
        assert result == cpu_count

    def test_explicit_within_cpu(self):
        cpu_count = os.cpu_count() or 1
        if cpu_count >= 2:
            result = resolve_worker_count(2, 10_000)
            assert result == 2

    def test_auto_with_small_sample_count(self):
        result = resolve_worker_count(0, 100)
        assert result == 1

    def test_auto_with_large_sample_count(self):
        cpu_count = os.cpu_count() or 1
        result = resolve_worker_count(0, 100_000)
        expected = max(1, cpu_count // 2)
        assert result == expected

    def test_zero_samples_returns_one(self):
        result = resolve_worker_count(0, 0)
        assert result == 1

    def test_auto_single_cpu(self, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 1)
        result = resolve_worker_count(0, 10_000)
        assert result == 1

    def test_explicit_two_with_single_cpu(self, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 1)
        result = resolve_worker_count(2, 10_000)
        assert result == 1


class TestResolveChunkSize:
    def test_zero_samples(self):
        result = resolve_chunk_size(0, 4)
        assert result == 64  # _DEFAULT_RENDER_CHUNK_SIZE

    def test_single_worker(self):
        result = resolve_chunk_size(10_000, 1)
        assert result == 64

    def test_multi_worker_large_count(self):
        result = resolve_chunk_size(100_000, 8)
        # target = 100000 / (8*32) = 390
        # clamp: max(16, min(256, max(64, 390))) = 256
        assert result == 256

    def test_multi_worker_small_count(self):
        result = resolve_chunk_size(1_000, 4)
        # target = 1000 / (4*32) = 7
        # clamp: max(16, min(256, max(64, 7))) = 64
        assert result == 64

    def test_minimum_16(self):
        result = resolve_chunk_size(500, 16)
        # target = 500 / (16*32) = 0
        # clamp: max(16, min(256, max(64, 0))) = 64
        # Actually target is 0, so max(64, 0) = 64, min(256, 64) = 64
        assert result >= 16

    def test_maximum_256(self):
        result = resolve_chunk_size(1_000_000, 4)
        assert result <= 256


class TestResolveMpContext:
    def test_returns_context_and_name(self):
        ctx, name = resolve_mp_context()
        assert name in ("fork", "spawn")
        assert ctx is not None

    def test_env_override_valid(self, monkeypatch):
        monkeypatch.setenv("KHOCR_GEN_MP_START_METHOD", "spawn")
        _ctx, name = resolve_mp_context()
        assert name == "spawn"

    def test_env_override_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("KHOCR_GEN_MP_START_METHOD", "invalid_method")
        _ctx, name = resolve_mp_context()
        assert name == "spawn"

    def test_env_override_empty_uses_default(self, monkeypatch):
        monkeypatch.setenv("KHOCR_GEN_MP_START_METHOD", "")
        _ctx, name = resolve_mp_context()
        assert name in ("fork", "spawn")


@pytest.mark.skipif(not _HAS_REAL_FONTS, reason="real fonts not available")
class TestParallelWorkerRecordMetadata:
    def test_worker_record_includes_decorations(self, tmp_path):
        """Parallel worker sidecar records carry the `decorations` key (spec parity)."""
        cfg = GenerationConfig(
            fonts_dir=str(_FONTS_DIR), text_deco=TextDecorationConfig(underline_prob=1.0)
        )
        _init_render_worker(
            {
                **cfg.to_dict(),
                "split_name": "train",
                "output_images_dir": str(tmp_path),
                "font_mode": "random",
                "retry_limit": 3,
                "record_metadata": True,
                "output_format": "jpg",
                "jpeg_quality": 90,
            }
        )
        _labels, _attempted, success_count, _errors, meta_lines, _heights = _render_sample_batch(
            [(0, "Hello", None)]
        )
        assert success_count == 1
        assert len(meta_lines) == 1
        record = json.loads(meta_lines[0])
        assert "underline" in record["decorations"]
