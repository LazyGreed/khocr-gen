"""Parallel data generation workers.

Each worker process renders text lines from a corpus
and applies exactly one augmentation method per rendered image (isolated augmentation model).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .augmentation import write_output_image
from .config import AugMethodConfig, GenerationConfig
from .fonts import FontManager
from .rendering import ImageRenderer

_LOGGER = logging.getLogger("khocr_gen.parallel")
_AUTO_PARALLEL_MIN_SAMPLES = 2_048
_DEFAULT_RENDER_CHUNK_SIZE = 64
_MAX_RENDER_CHUNK_SIZE = 256


def resolve_worker_count(workers: int, sample_count: int) -> int:
    """Determine how many worker processes to use.

    Returns 1 when auto-resolve decides parallelism isn't worthwhile.
    """
    requested = max(0, int(workers))
    cpu_count = os.cpu_count() or 1

    if sample_count <= 0 or cpu_count <= 1:
        return 1
    if requested == 1:
        return 1
    if requested > 1:
        return min(requested, cpu_count)
    if sample_count < _AUTO_PARALLEL_MIN_SAMPLES:
        return 1
    return max(1, cpu_count // 2)


def resolve_chunk_size(sample_count: int, workers: int) -> int:
    """Pick a batch size that balances load across workers."""
    if sample_count <= 0:
        return _DEFAULT_RENDER_CHUNK_SIZE
    if workers <= 1:
        return _DEFAULT_RENDER_CHUNK_SIZE

    target = sample_count // max(1, workers * 32)
    return max(16, min(_MAX_RENDER_CHUNK_SIZE, max(_DEFAULT_RENDER_CHUNK_SIZE, target)))


def resolve_mp_context() -> tuple[Any, str]:
    """Pick a multiprocessing context optimised for the host platform.

    - Linux: `fork` — no re-import overhead.
    - macOS / Windows: `spawn` (OS restriction or default).
    - Override: set `KHOCR_GEN_MP_START_METHOD` env var.
    """
    import multiprocessing as mp

    requested = os.environ.get("KHOCR_GEN_MP_START_METHOD", "").strip().lower()
    available = set(mp.get_all_start_methods())

    if requested:
        if requested in available:
            return mp.get_context(requested), requested
        return mp.get_context("spawn"), "spawn"

    if sys.platform == "linux" and "fork" in available:
        return mp.get_context("fork"), "fork"

    return mp.get_context("spawn"), "spawn"


# Per-process worker state
_WORKER_STATE: dict[str, Any] = {}


def _init_render_worker(config_dict: dict[str, Any]) -> None:
    """Initialise a worker process with its own renderer and config."""
    global _WORKER_STATE

    # Limit OpenCV threads in worker processes
    with contextlib.suppress(Exception):
        cv2.setNumThreads(1)
    with contextlib.suppress(Exception):
        cv2.ocl.setUseOpenCL(False)

    # Derive a per-worker seed from os.urandom
    seed = int.from_bytes(os.urandom(8), "little") ^ (os.getpid() << 16)
    random.seed(seed)
    np.random.seed(seed % (2**32))

    # Reconstruct GenerationConfig from serialised dict
    gen_cfg = GenerationConfig.from_dict(config_dict)

    font_manager = FontManager(language=gen_cfg.language, fonts_dir=gen_cfg.fonts_dir)
    renderer = ImageRenderer(font_manager, gen_cfg)

    _WORKER_STATE = {
        "renderer": renderer,
        "split_name": config_dict["split_name"],
        "output_images_dir": config_dict["output_images_dir"],
        "font_mode": config_dict["font_mode"],
        "retry_limit": config_dict["retry_limit"],
        "image_dir": config_dict.get("image_dir"),
        "output_format": config_dict.get("output_format", "jpg"),
        "jpeg_quality": config_dict.get("jpeg_quality", 90),
        "storage": config_dict.get("storage", "raw"),
        "record_metadata": config_dict.get("record_metadata", False),
    }


def _render_sample_batch(
    batch: list[tuple[int, str, Any]],
) -> tuple[list[str], int, int, list[str], list[str], list[int]]:
    """Render a batch of samples in the worker process.

    Each sample is rendered to a clean canvas,
    then exactly one augmentation method is applied (chosen probabilistically from the enabled methods).

    Returns:
        (labels_lines, attempted_count, success_count, error_messages, metadata_lines, heights)
    """
    renderer: ImageRenderer = _WORKER_STATE["renderer"]
    split_name: str = _WORKER_STATE["split_name"]
    output_images_dir = Path(_WORKER_STATE["output_images_dir"])
    font_mode: str = _WORKER_STATE["font_mode"]
    retry_limit: int = _WORKER_STATE["retry_limit"]
    record_metadata: bool = _WORKER_STATE.get("record_metadata", False)
    current_retry_limit = 1 if font_mode == "all" else retry_limit

    labels: list[str] = []
    meta_lines: list[str] = []
    heights: list[int] = []
    error_messages: list[str] = []
    success_count = 0

    image_dir = _WORKER_STATE.get("image_dir")

    # Get enabled augmentation methods once per batch
    enabled_methods: list[tuple[str, AugMethodConfig]] = renderer._cfg.enabled_aug_methods()

    for current_idx, text, font_ref_or_image in batch:
        try:
            meta: dict[str, Any] = {}
            if image_dir:
                # Image-dir mode: augment an existing image
                img_path = Path(image_dir) / font_ref_or_image
                img_array = cv2.imread(str(img_path))
                if img_array is None:
                    raise RuntimeError(f"Could not read image: {img_path}")

                if img_array.ndim == 3 and img_array.shape[2] == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

                # Apply one augmentation probabilistically
                result = renderer.render_with_one_augmentation(
                    text,
                    enabled_methods,
                    specific_font=font_ref_or_image,
                    retry_limit=current_retry_limit,
                )
                if result is None:
                    # Fallback: augment existing image directly
                    aug_results = renderer.augment_image(img_array, enabled_methods)
                    if not aug_results:
                        continue
                    _, img = aug_results[0]
                else:
                    _, img, meta = result
            else:
                # Text-rendering mode
                result = renderer.render_with_one_augmentation(
                    text,
                    enabled_methods,
                    specific_font=font_ref_or_image,
                    retry_limit=current_retry_limit,
                )
                if result is None:
                    continue
                _, img, meta = result

            if img is None:
                continue

            output_fmt = _WORKER_STATE.get("output_format", "jpg")
            jpeg_q = _WORKER_STATE.get("jpeg_quality", 90)
            img_filename = f"{split_name}_{current_idx:06d}.{output_fmt}"
            img_path = output_images_dir / img_filename
            write_ok = write_output_image(img_path, img, fmt=output_fmt, jpeg_quality=jpeg_q)
            if not write_ok:
                raise RuntimeError(f"cv2.imwrite failed for output path: {img_path}")

            labels.append(f"{img_filename}\t{text}\n")
            heights.append(int(img.shape[0]))
            if record_metadata:
                record = {
                    "image": img_filename,
                    "text": text,
                    "width": int(img.shape[1]),
                    "height": int(img.shape[0]),
                    "font": meta.get("font"),
                    "font_size": meta.get("font_size"),
                }
                meta_lines.append(json.dumps(record, ensure_ascii=False) + "\n")
            success_count += 1
        except Exception as exc:
            if len(error_messages) < 3:
                short_text = text[:30] if len(text) > 30 else text
                error_messages.append(f"    Failed for '{short_text}...': {exc}")

    return labels, len(batch), success_count, error_messages, meta_lines, heights
