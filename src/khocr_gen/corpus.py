"""Corpus loading, filtering, and counting.

Handles UTF-8 plain-text corpora: streams lines, applies length filters after Khmer normalization,
and supports parallel count-only scans.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import InputValidationError
from .normalizer import NormalizerConfig, normalize

if TYPE_CHECKING:
    from collections.abc import Generator

_AUTO_PARALLEL_MIN_BYTES = 16 * 1024 * 1024

_SKIP = 0
_TOO_SHORT = 1
_TOO_LONG = 2
_PASS = 3


def _empty_stats() -> dict[str, int]:
    return {"total": 0, "passing": 0, "too_short": 0, "too_long": 0}


def _merge_stats(base: dict[str, int], update: dict[str, int]) -> dict[str, int]:
    for key, value in update.items():
        base[key] += value
    return base


def _update_stats_for_status(stats: dict[str, int], status: int) -> None:
    if status == _SKIP:
        return
    stats["total"] += 1
    if status == _TOO_SHORT:
        stats["too_short"] += 1
    elif status == _TOO_LONG:
        stats["too_long"] += 1
    else:
        stats["passing"] += 1


def _classify_raw_line(
    raw_line: str,
    min_length: int,
    max_length: int,
    normalizer: NormalizerConfig | None = None,
) -> tuple[int, str | None]:
    raw = raw_line.strip()
    if not raw:
        return _SKIP, None

    raw_len = len(raw)
    if raw_len < min_length:
        return _TOO_SHORT, None
    if raw_len > max_length:
        return _TOO_LONG, None

    # Normalize (Khmer canonical reorder) before length check
    line = normalize(raw, normalizer)
    line_len = len(line)
    if line_len < min_length:
        return _TOO_SHORT, None
    if line_len > max_length:
        return _TOO_LONG, None

    return _PASS, line


def _count_lines(
    lines, min_length: int, max_length: int, normalizer: NormalizerConfig | None = None
) -> dict[str, int]:
    stats = _empty_stats()
    for raw_line in lines:
        status, _ = _classify_raw_line(raw_line, min_length, max_length, normalizer)
        _update_stats_for_status(stats, status)
    return stats


def _count_file_chunk(
    path_str: str,
    start: int,
    end: int,
    min_length: int,
    max_length: int,
) -> dict[str, int]:
    _UTF8_BOM = b"\xef\xbb\xbf"
    with open(path_str, "rb") as fh:
        if start != 0:
            fh.seek(start - 1)
            if fh.read(1) not in {b"\n", b"\r"}:
                fh.readline()
        else:
            fh.seek(start)
            maybe_bom = fh.read(len(_UTF8_BOM))
            if not maybe_bom.startswith(_UTF8_BOM):
                fh.seek(start)

        stats = _empty_stats()
        while True:
            line_start = fh.tell()
            if line_start >= end:
                break
            raw_line = fh.readline()
            if not raw_line:
                break
            status, _ = _classify_raw_line(
                raw_line.decode("utf-8", errors="replace"),
                min_length=min_length,
                max_length=max_length,
            )
            _update_stats_for_status(stats, status)
    return stats


def _iter_chunk_ranges(path: Path, workers: int):
    file_size = path.stat().st_size
    chunk_size = max(1, file_size // workers)
    start = 0
    for worker_index in range(workers):
        end = file_size if worker_index == workers - 1 else start + chunk_size
        yield start, end
        start = end


def _resolve_worker_count(path: Path, workers: int) -> int:
    requested = max(0, int(workers))
    cpu_count = os.cpu_count() or 1
    if requested == 1:
        return 1
    if requested > 1:
        return min(requested, cpu_count)
    if cpu_count <= 1:
        return 1
    try:
        if path.stat().st_size < _AUTO_PARALLEL_MIN_BYTES:
            return 1
    except OSError:
        return 1
    return cpu_count


def _count_corpus_serial(
    path: Path,
    min_length: int,
    max_length: int,
    normalizer: NormalizerConfig | None = None,
) -> dict[str, int]:
    stats = _empty_stats()
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        batch_stats = _count_lines(fh, min_length, max_length, normalizer)
        _merge_stats(stats, batch_stats)
    return stats


def load_corpus(
    path: str | Path,
    min_length: int = 1,
    max_length: int = 260,
    max_lines: int = 0,
    normalizer: NormalizerConfig | None = None,
) -> Generator[str, None, None]:
    """Stream lines from a plain-text corpus file, applying filters.

    Args:
        path: Path to corpus text file (UTF-8, one string per line).
        min_length: Skip lines shorter than this many characters (after normalization).
        max_length: Skip lines longer than this many characters (after normalization).
        max_lines: Stop after yielding this many lines (0 = unlimited).
        normalizer: Khmer normalization config (uses defaults if None).

    Yields:
        Filtered, normalized text strings.
    """
    path = Path(path)
    if not path.exists():
        raise InputValidationError(f"Corpus file not found: {path}", code="corpus_not_found")

    yielded = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            status, line = _classify_raw_line(raw_line, min_length, max_length, normalizer)
            if status != _PASS or line is None:
                continue

            yield line
            yielded += 1
            if max_lines > 0 and yielded >= max_lines:
                break


def count_corpus(
    path: str | Path,
    min_length: int = 1,
    max_length: int = 260,
    workers: int = 0,
    normalizer: NormalizerConfig | None = None,
) -> dict[str, int]:
    """Scan the full corpus and return filter statistics.

    Returns a dict with keys:
        total, passing, too_short, too_long
    """
    path = Path(path)
    if not path.exists():
        raise InputValidationError(f"Corpus file not found: {path}", code="corpus_not_found")

    resolved_workers = _resolve_worker_count(path, workers)
    if resolved_workers <= 1:
        return _count_corpus_serial(path, min_length, max_length, normalizer)

    stats = _empty_stats()
    try:
        with mp.Pool(processes=resolved_workers) as pool:
            ranges = list(_iter_chunk_ranges(path, resolved_workers))
            for batch_stats in pool.starmap(
                _count_file_chunk,
                [(str(path), s, e, min_length, max_length) for s, e in ranges],
                chunksize=1,
            ):
                _merge_stats(stats, batch_stats)
    except (OSError, PermissionError):
        return _count_corpus_serial(path, min_length, max_length, normalizer)

    return stats
