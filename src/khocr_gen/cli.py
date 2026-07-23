"""`khocr-gen` - CLI entrypoint for synthetic OCR data generation.

Supports four subcommands: generate, combine, verify, view.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Any

from . import __version__
from .config_loader import (
    apply_config_defaults,
    load_yaml_config,
    resolve_config_path,
    validate_config_keys,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Command module protocol ────────────────────────────────────────────────

CommandModule = Any  # duck-typed: has add_args(parser) and run(args) -> int


class _SubParser(argparse.ArgumentParser):
    """Subcommand parser that tracks whether its args have been lazily configured."""

    _lazy_loaded: bool = False


def _load_generate() -> CommandModule:
    from . import generate

    return generate


def _load_combine() -> CommandModule:
    from . import combine_cmd

    return combine_cmd


def _load_verify() -> CommandModule:
    from . import verify

    return verify


def _load_view() -> CommandModule:
    from . import viewer

    return viewer


_COMMAND_LOADERS: dict[str, Callable[[], CommandModule]] = {
    "generate": _load_generate,
    "combine": _load_combine,
    "verify": _load_verify,
    "view": _load_view,
}

_LEAF_HELP: dict[str, str] = {
    "generate": "Generate synthetic training images from a text corpus",
    "combine": "Combine multiple generated datasets into one merged LMDB dataset",
    "verify": "Visual verification of augmentation methods at MIN/MAX intensity",
    "view": "Preview and extract images from an LMDB (.mdb) database",
}

# Commands that support -c / --config YAML loading
_CONFIG_COMMANDS: frozenset[str] = frozenset({"generate", "combine"})


def _first_positional(tokens: list[str]) -> tuple[str | None, bool]:
    """Return (first non-flag token, whether a help/version flag preceded it)."""
    help_seen = False
    for token in tokens:
        if token == "--":
            return None, help_seen
        if token in {"-h", "--help", "-v", "--version"}:
            help_seen = True
            continue
        if token.startswith("-"):
            continue
        return token, help_seen
    return None, help_seen


def _extract_command(argv: list[str]) -> str | None:
    command, _ = _first_positional(argv)
    if command is None or command not in _COMMAND_LOADERS:
        return None
    return command


def _configure_subcommand(
    command: str,
    subparser: _SubParser,
) -> None:
    if subparser._lazy_loaded:
        return

    module = _COMMAND_LOADERS[command]()
    module.add_args(subparser)
    subparser.set_defaults(func=module.run)
    subparser._lazy_loaded = True


def _pre_config(argv: list[str]) -> str | None:
    """Extract the -c/--config value from *argv* without a full parse."""
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            break
        if token in ("-c", "--config") and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--config="):
            return token[len("--config=") :]
        if token.startswith("-c="):
            return token[3:]
        i += 1
    return None


def _apply_config_defaults(
    command: str,
    subparser: argparse.ArgumentParser,
    argv: list[str],
) -> None:
    """Load YAML config (if any) and push values as argparse defaults."""
    if command not in _CONFIG_COMMANDS:
        return

    explicit_config = _pre_config(argv)
    config_path = resolve_config_path(explicit_config, command)
    if config_path is None:
        return

    try:
        cfg = load_yaml_config(config_path)
    except FileNotFoundError as exc:
        if explicit_config is not None:
            print(f"error: {exc}")
            sys.exit(2)
        return
    except Exception as exc:
        print(f"error: failed to load config {config_path}: {exc}")
        sys.exit(2)

    cfg.pop("config", None)

    if cfg:
        validate_config_keys(subparser, cfg, command)
        apply_config_defaults(subparser, cfg)
        print(f"[config] loaded: {config_path}")


def _make_parser() -> tuple[argparse.ArgumentParser, dict[str, _SubParser]]:
    parser = argparse.ArgumentParser(
        prog="khocr-gen",
        description=(
            "khocr-gen - synthetic data generation for mixed Khmer/English "
            "text recognition with isolated augmentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-v", "--version", action="version", version=f"khocr-gen {__version__}")

    subparsers = parser.add_subparsers(
        dest="command", metavar="COMMAND", title="Commands", parser_class=_SubParser
    )
    subparsers.required = True

    command_parsers: dict[str, _SubParser] = {}
    for cmd_name in _COMMAND_LOADERS:
        command_parsers[cmd_name] = subparsers.add_parser(
            cmd_name,
            help=_LEAF_HELP[cmd_name],
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )

    return parser, command_parsers


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser, command_parsers = _make_parser()

    extracted = _extract_command(argv)
    if extracted is not None:
        command = extracted
        subparser = command_parsers[command]
        _configure_subcommand(command, subparser)
        _apply_config_defaults(command, subparser, argv)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.error(f"Command '{getattr(args, 'command', None)}' was not configured.")
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
