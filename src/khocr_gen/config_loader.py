"""YAML configuration loader for CLI subcommands.

Loading order (highest priority wins):
    1. argparse built-in defaults          (lowest)
    2. YAML config file values             (middle)
    3. Explicit CLI flags                  (highest)

Keys in the YAML file may use either dashes or underscores;
both are normalized to underscores to match argparse `dest` names.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("khocr_gen.config_loader")


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return a flat `{dest: value}` dict.

    Keys are normalized: hyphens -> underscores (matching argparse dest names).
    Only top-level scalar / list values are supported; nested mappings are ignored with a warning.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ImportError: If PyYAML is not installed.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to use --config (-c). Install it with:  pip install pyyaml"
        ) from exc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        return {}

    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a YAML mapping (dict) at the top level: {path}")

    result: dict[str, Any] = {}
    for key, value in raw.items():
        norm_key = str(key).replace("-", "_")
        if isinstance(value, dict):
            _log.warning(
                "Config key %r is a nested mapping; only flat keys are supported, skipping.",
                key,
            )
            continue
        result[norm_key] = value

    return result


def _build_dest_aliases(parser: argparse.ArgumentParser) -> dict[str, str]:
    """Map option-string spellings to real `dest` names."""
    aliases: dict[str, str] = {}
    for action in parser._actions:
        dest = action.dest
        if not dest or dest == argparse.SUPPRESS:
            continue
        aliases[dest] = dest
        for opt in action.option_strings:
            if opt.startswith("--"):
                aliases.setdefault(opt[2:].replace("-", "_"), dest)
    return aliases


def _resolve_config_keys(parser: argparse.ArgumentParser, config: dict[str, Any]) -> dict[str, Any]:
    """Remap *config*'s keys to real argparse `dest` names where they differ."""
    aliases = _build_dest_aliases(parser)
    result: dict[str, Any] = {}
    for k, v in config.items():
        norm_k = str(k).replace("-", "_")
        result[aliases.get(norm_k, norm_k)] = v
    return result


def validate_config_keys(
    parser: argparse.ArgumentParser,
    config: dict[str, Any],
    command: str,
    strict: bool = False,
) -> None:
    """Validate that all keys in *config* correspond to registered arguments.

    If *strict*, exit with code 2 on unrecognized keys; otherwise log a warning.
    """
    valid_dests = {action.dest for action in parser._actions}
    aliases = _build_dest_aliases(parser)
    invalid_keys = [k for k in config if k not in valid_dests and k not in aliases]
    if invalid_keys:
        msg = (
            f"[config] WARNING: Unrecognized keys in '{command}' configuration: "
            f"{', '.join(sorted(invalid_keys))}"
        )
        if strict:
            import sys

            print(f"error: {msg}", file=sys.stderr)
            sys.exit(2)
        else:
            _log.warning("%s", msg)


def apply_config_defaults(
    parser: argparse.ArgumentParser,
    config: dict[str, Any],
) -> None:
    """Push *config* values into *parser* as low-priority defaults.

    argparse guarantees that values set via `set_defaults` are overridden
    by any matching CLI flag actually present on the command line.
    """
    if config:
        parser.set_defaults(**_resolve_config_keys(parser, config))


def resolve_config_path(
    config_arg: str | None,
    command: str,
    cwd: str | Path | None = None,
) -> Path | None:
    """Resolve the config file to load.

    Priority:
    1. Explicit `--config` / `-c` value.
    2. `configs/<command>.yml` relative to *cwd*.
    """
    if config_arg is not None:
        return Path(config_arg)

    base = Path(cwd) if cwd is not None else Path.cwd()
    candidate = base / "configs" / f"{command}.yml"
    if candidate.exists():
        return candidate

    return None
