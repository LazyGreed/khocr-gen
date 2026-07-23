"""Tests for YAML config loading utilities."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pytest

from khocr_gen.config_loader import (
    apply_config_defaults,
    load_yaml_config,
    resolve_config_path,
    validate_config_keys,
)


class TestLoadYamlConfig:
    def test_loads_simple_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("height: 64\nwidth: 512\n")
            tmp = Path(f.name)
        try:
            result = load_yaml_config(tmp)
            assert result["height"] == 64
            assert result["width"] == 512
        finally:
            tmp.unlink()

    def test_normalizes_hyphens_to_underscores(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("image-height: 64\nsome-long-key: value\n")
            tmp = Path(f.name)
        try:
            result = load_yaml_config(tmp)
            assert result["image_height"] == 64
            assert result["some_long_key"] == "value"
        finally:
            tmp.unlink()

    def test_empty_file_returns_empty_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("")
            tmp = Path(f.name)
        try:
            result = load_yaml_config(tmp)
            assert result == {}
        finally:
            tmp.unlink()

    def test_null_file_returns_empty_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("null\n")
            tmp = Path(f.name)
        try:
            result = load_yaml_config(tmp)
            assert result == {}
        finally:
            tmp.unlink()

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_yaml_config("/nonexistent/config.yml")

    def test_non_dict_toplevel_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("- item1\n- item2\n")
            tmp = Path(f.name)
        try:
            with pytest.raises(ValueError, match="YAML mapping"):
                load_yaml_config(tmp)
        finally:
            tmp.unlink()

    def test_nested_mapping_skipped_with_warning(self, caplog):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("height: 64\nnested:\n  key: value\n")
            tmp = Path(f.name)
        try:
            result = load_yaml_config(tmp)
            assert result["height"] == 64
            assert "nested" not in result
            assert "nested mapping" in caplog.text.lower()
        finally:
            tmp.unlink()


class TestApplyConfigDefaults:
    def test_sets_defaults_on_parser(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)
        parser.add_argument("--name", type=str, default="default-name")

        config = {"height": 96, "name": "from-yaml"}
        apply_config_defaults(parser, config)

        # Simulate CLI: no flags provided
        ns = parser.parse_args([])
        assert ns.height == 96
        assert ns.name == "from-yaml"

    def test_cli_flags_override_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)

        config = {"height": 96}
        apply_config_defaults(parser, config)

        # CLI flag overrides
        ns = parser.parse_args(["--height", "128"])
        assert ns.height == 128

    def test_empty_config_noop(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)
        apply_config_defaults(parser, {})
        ns = parser.parse_args([])
        assert ns.height == 48

    def test_hyphens_in_config_keys(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--image-height", type=int, default=48)
        config = {"image-height": 64}
        apply_config_defaults(parser, config)
        ns = parser.parse_args([])
        assert ns.image_height == 64


class TestValidateConfigKeys:
    def test_valid_keys_no_warning(self, caplog):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)
        validate_config_keys(parser, {"height": 64}, "test")
        assert "Unrecognized" not in caplog.text

    def test_invalid_key_logs_warning(self, caplog):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)
        validate_config_keys(parser, {"unknown_key": 99}, "test")
        assert "Unrecognized" in caplog.text

    def test_strict_mode_exits(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--height", type=int, default=48)
        with pytest.raises(SystemExit):
            validate_config_keys(parser, {"unknown_key": 99}, "test", strict=True)


class TestResolveConfigPath:
    def test_explicit_path_returned(self):
        result = resolve_config_path("/some/path.yml", "generate")
        assert result == Path("/some/path.yml")

    def test_none_when_no_config_found(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = resolve_config_path(None, "generate")
        assert result is None

    def test_finds_config_in_configs_dir(self, monkeypatch, tmp_path):
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()
        config_file = configs_dir / "generate.yml"
        config_file.write_text("height: 64")

        monkeypatch.chdir(tmp_path)
        result = resolve_config_path(None, "generate")
        assert result == config_file
