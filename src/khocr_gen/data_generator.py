"""DatasetGenerator - orchestrates synthetic data generation.

Coordinates corpus loading, font selection, rendering with isolated augmentation, and parallel worker dispatch.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cv2
from tqdm import tqdm

from .augmentation import write_output_image
from .corpus import char_frequencies, load_corpus, rare_chars_from_frequencies
from .fonts import FontManager
from .parallel import (
    _init_render_worker,
    _render_sample_batch,
    resolve_chunk_size,
    resolve_mp_context,
    resolve_worker_count,
)
from .rendering import ImageRenderer

if TYPE_CHECKING:
    from .config import GenerationConfig

_log = logging.getLogger("khocr_gen.generator")


class DatasetGenerator:
    """Generate synthetic training datasets from a text corpus.

    Each text line is rendered to a clean canvas,
    then exactly one augmentation method is applied per output image (isolated augmentation).
    """

    def __init__(self, cfg: GenerationConfig) -> None:
        self._cfg = cfg
        self.font_manager = FontManager(language=cfg.language, fonts_dir=cfg.fonts_dir)
        self.renderer = ImageRenderer(self.font_manager, cfg)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_label_text(text: str) -> str:
        """Normalize embedded tabs in label text (labels.txt uses tab as delimiter)."""
        return text.replace("\t", " ")

    @staticmethod
    def _read_non_empty_lines(
        text_file: str | Path, image_dir: str | None = None
    ) -> list[str | tuple[str, str]]:
        """Read lines from *text_file*, optionally parsing (filename, text) pairs."""
        lines: list[str | tuple[str, str]] = []
        with open(text_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if image_dir:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        lines.append((parts[0], DatasetGenerator._sanitize_label_text(parts[1])))
                else:
                    lines.append(DatasetGenerator._sanitize_label_text(line))
        return lines

    @staticmethod
    def _split_lines_without_text_overlap(
        lines: list, val_ratio: float = 0.1, test_ratio: float = 0.1, seed: int = 42
    ) -> tuple[list, list, list]:
        """Split *lines* into train/val/test keeping each unique text in exactly one split.

        Returns ``(train_lines, val_lines, test_lines)`` where no text string appears in
        more than one partition.

        Resolution of effective ratios matches :meth:`GenerationConfig.resolve_split_ratios`:
        pass ``test_ratio=0.0`` to disable the test split (returns empty list for test).
        """
        if not lines:
            return [], [], []

        val_ratio = float(max(0.0, min(1.0, val_ratio)))
        test_ratio = float(max(0.0, min(1.0, test_ratio)))
        # Clamp so train can't go negative
        if val_ratio + test_ratio >= 1.0:
            excess = val_ratio + test_ratio
            val_ratio = val_ratio / excess
            test_ratio = test_ratio / excess

        if val_ratio <= 0.0 and test_ratio <= 0.0:
            return list(lines), [], []

        buckets: dict[str, list] = {}
        for item in lines:
            text = item[1] if isinstance(item, tuple) else item
            buckets.setdefault(text, []).append(item)

        unique_texts = list(buckets.keys())
        if len(unique_texts) <= 1:
            return list(lines), [], []

        rng = random.Random(seed)
        rng.shuffle(unique_texts)

        n = len(unique_texts)
        val_unique = round(n * val_ratio)
        test_unique = round(n * test_ratio)
        # Ensure at least one text stays in train
        val_unique = max(0, min(val_unique, n - 1))
        test_unique = max(0, min(test_unique, n - 1 - val_unique))

        val_texts = set(unique_texts[:val_unique])
        test_texts = set(unique_texts[val_unique : val_unique + test_unique])

        train_lines: list = []
        val_lines: list = []
        test_lines: list = []
        for text in unique_texts:
            if text in val_texts:
                val_lines.extend(buckets[text])
            elif text in test_texts:
                test_lines.extend(buckets[text])
            else:
                train_lines.extend(buckets[text])

        return train_lines, val_lines, test_lines

    @staticmethod
    def _copies_for_line(
        text: str,
        copies: int,
        rare_chars: set[str] | None,
        rare_char_multiplier: float,
    ) -> int:
        """Boost *copies* for lines containing a rare character.

        Lines with no rare character are unaffected. Multiplier is only
        applied (and only ever increases copies) when rendering random-font
        training samples; val/test always pass ``rare_chars=None``.
        """
        if not rare_chars or rare_char_multiplier <= 1.0:
            return copies
        if any(ch in rare_chars for ch in text):
            return max(copies, round(copies * rare_char_multiplier))
        return copies

    @staticmethod
    def _write_lines(path: Path, lines: list) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                if isinstance(line, tuple):
                    f.write(f"{line[0]}\t{line[1]}\n")
                else:
                    f.write(line + "\n")

    @staticmethod
    def _build_vocab(labels_files: list[str], output_path: str) -> None:
        """Scan labels files and write a vocab.json covering every character."""
        print("\nBuilding vocabulary from generated labels...")
        unique_chars: set[str] = set()

        for lf in labels_files:
            if not os.path.exists(lf):
                continue
            with open(lf, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.strip().split("\t", 1)
                    if len(parts) == 2:
                        unique_chars.update(parts[1])

        print(f"   Found {len(unique_chars)} unique characters.")

        if not unique_chars:
            print(
                "   WARNING: no characters found in any labels file. "
                "The written vocab.json will contain only {'<unk>': 0}."
            )

        vocab: dict[str, int] = {"<unk>": 0}
        for idx, ch in enumerate(sorted(unique_chars), start=1):
            if ch != "<unk>":
                vocab[ch] = idx

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(vocab, fh, indent=2, ensure_ascii=False)

        print(f"   Vocabulary saved -> {output_path}")

    # ── Worker config ──────────────────────────────────────────────────────

    def _render_worker_config(
        self,
        output_dir: Path,
        split_name: str,
        font_mode: str,
        retry_limit: int,
        image_dir: str | None = None,
    ) -> dict[str, Any]:
        """Build the dict passed to worker initializer."""
        worker_dict = self._cfg.to_dict()
        worker_dict.update(
            {
                "split_name": split_name,
                "output_images_dir": str(output_dir / "images"),
                "font_mode": font_mode,
                "retry_limit": retry_limit,
                "image_dir": image_dir,
            }
        )
        return worker_dict

    # ── Batch iteration ────────────────────────────────────────────────────

    @staticmethod
    def _iter_sample_batches(samples: list[tuple[str, Any]], start_idx: int, chunk_size: int):
        """Yield batches of (index, text, font_ref) tuples."""
        batch: list[tuple[int, str, Any]] = []
        for offset, (text, font_ref) in enumerate(samples):
            batch.append((start_idx + offset, text, font_ref))
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch

    # ── Split generation ───────────────────────────────────────────────────

    def _generate_split_serial(
        self,
        samples: list[tuple[str, Any]],
        output_dir: Path,
        split_name: str,
        font_mode: str,
        retry_limit: int,
        start_idx: int,
        file_mode: str,
        image_dir: str | None = None,
    ) -> tuple[int, list[int]]:
        """Generate one split using a single process.

        Returns `(success_count, heights)` where *heights* is the pixel height
        of every successfully rendered image (for the QA height-distribution
        summary).
        """
        enabled_methods = self._cfg.enabled_aug_methods()
        success_count = 0
        heights: list[int] = []
        record_metadata = bool(self._cfg.record_metadata)

        meta_file = (
            open(output_dir / "metadata.jsonl", file_mode, encoding="utf-8")  # noqa: SIM115
            if record_metadata
            else None
        )
        try:
            with open(output_dir / "labels.txt", file_mode, encoding="utf-8") as labels_file:
                for idx, (text, specific_font) in enumerate(
                    tqdm(samples, desc="    Generating", unit="img")
                ):
                    current_retry_limit = 1 if font_mode == "all" else retry_limit

                    try:
                        meta: dict[str, Any] = {}
                        if image_dir:
                            img_path = Path(image_dir) / specific_font
                            img_array = cv2.imread(str(img_path))
                            if img_array is None:
                                raise RuntimeError(f"Could not read image: {img_path}")
                            if img_array.ndim == 3 and img_array.shape[2] == 3:
                                img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

                            aug_results = self.renderer.augment_image(img_array, enabled_methods)
                            if not aug_results:
                                continue
                            _, img = aug_results[0]
                        else:
                            result = self.renderer.render_with_one_augmentation(
                                text,
                                enabled_methods,
                                specific_font=specific_font,
                                retry_limit=current_retry_limit,
                            )
                            if result is None:
                                continue
                            _, img, meta = result

                        if img is None:
                            continue

                        current_idx = start_idx + idx
                        img_filename = f"{split_name}_{current_idx:06d}.jpg"
                        img_path = output_dir / "images" / img_filename
                        write_ok = write_output_image(img_path, img)
                        if not write_ok:
                            raise RuntimeError(f"cv2.imwrite failed for output path: {img_path}")

                        labels_file.write(f"{img_filename}\t{text}\n")
                        heights.append(int(img.shape[0]))
                        if meta_file is not None:
                            record = {
                                "image": img_filename,
                                "text": text,
                                "width": int(img.shape[1]),
                                "height": int(img.shape[0]),
                                "font": meta.get("font"),
                                "font_size": meta.get("font_size"),
                            }
                            meta_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success_count += 1

                    except Exception as e:
                        print(f"    Failed for '{text[:30]}...': {e}")
                        continue
        finally:
            if meta_file is not None:
                meta_file.close()

        return success_count, heights

    def _generate_split_parallel(
        self,
        samples: list[tuple[str, Any]],
        output_dir: Path,
        split_name: str,
        font_mode: str,
        retry_limit: int,
        start_idx: int,
        file_mode: str,
        workers: int,
        image_dir: str | None = None,
    ) -> tuple[int, list[int]]:
        """Generate one split using multiple worker processes.

        Returns `(success_count, heights)`; see `_generate_split_serial`.
        """
        import json as _json
        from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, TimeoutError, wait

        resolved_workers = resolve_worker_count(workers, len(samples))
        if resolved_workers <= 1:
            return self._generate_split_serial(
                samples=samples,
                output_dir=output_dir,
                split_name=split_name,
                font_mode=font_mode,
                retry_limit=retry_limit,
                start_idx=start_idx,
                file_mode=file_mode,
                image_dir=image_dir,
            )

        chunk_size = resolve_chunk_size(len(samples), resolved_workers)
        worker_config = self._render_worker_config(
            output_dir=output_dir,
            split_name=split_name,
            font_mode=font_mode,
            retry_limit=retry_limit,
            image_dir=image_dir,
        )

        print(f"  Rendering with {resolved_workers} worker processes (chunk size: {chunk_size})")

        worker_timeout = self._cfg.worker_timeout if self._cfg.worker_timeout > 0 else None
        error_log_path = output_dir / "generation_errors.jsonl"
        record_metadata = bool(self._cfg.record_metadata)

        success_count = 0
        heights: list[int] = []
        error_records: list[dict] = []
        batch_iter = self._iter_sample_batches(samples, start_idx=start_idx, chunk_size=chunk_size)
        max_in_flight = max(2, resolved_workers * 2)

        mp_context, start_method = resolve_mp_context()

        with (
            open(output_dir / "labels.txt", file_mode, encoding="utf-8") as labels_file,
            contextlib.ExitStack() as stack,
            ProcessPoolExecutor(
                max_workers=resolved_workers,
                mp_context=mp_context,
                initializer=_init_render_worker,
                initargs=(worker_config,),
            ) as executor,
        ):
            meta_file = (
                stack.enter_context(
                    open(output_dir / "metadata.jsonl", file_mode, encoding="utf-8")
                )
                if record_metadata
                else None
            )
            print(f"  Multiprocessing start method: {start_method}")
            in_flight: set = set()
            for _ in range(max_in_flight):
                try:
                    batch = next(batch_iter)
                except StopIteration:
                    break
                in_flight.add(executor.submit(_render_sample_batch, batch))

            with tqdm(total=len(samples), desc="    Generating", unit="img") as pbar:
                while in_flight:
                    done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            (
                                labels,
                                attempted,
                                batch_success,
                                err_msgs,
                                meta_lines,
                                batch_heights,
                            ) = future.result(timeout=worker_timeout)
                        except TimeoutError:
                            raise RuntimeError(
                                f"A worker batch timed out after {worker_timeout}s. "
                                "Increase --worker-timeout or set it to 0 to disable."
                            ) from None
                        if labels:
                            labels_file.writelines(labels)
                        if meta_file is not None and meta_lines:
                            meta_file.writelines(meta_lines)
                        success_count += batch_success
                        heights.extend(batch_heights)
                        pbar.update(attempted)

                        for message in err_msgs:
                            print(message)
                            error_records.append({"message": message})

                        try:
                            batch = next(batch_iter)
                        except StopIteration:
                            continue
                        in_flight.add(executor.submit(_render_sample_batch, batch))

        if error_records:
            with open(error_log_path, "a", encoding="utf-8") as ef:
                for rec in error_records:
                    ef.write(_json.dumps(rec, ensure_ascii=False) + "\n")
            print(
                f"  {len(error_records)} error(s) written to "
                f"{error_log_path.relative_to(output_dir.parent)}"
            )

        return success_count, heights

    # ── Top-level entrypoints ──────────────────────────────────────────────

    def generate_split(
        self,
        text_file: str | Path,
        output_dir: str | Path,
        split_name: str,
        font_mode: str = "random",
        retry_limit: int = 10,
        append: bool = False,
        workers: int = 0,
        image_dir: str | None = None,
        copies: int = 3,
        rare_chars: set[str] | None = None,
        rare_char_multiplier: float = 1.0,
    ) -> int:
        """Generate one split (train or val) from *text_file*.

        *rare_chars*/*rare_char_multiplier* boost the per-line copy count for
        lines containing a rare character; pass ``rare_chars=None`` (the
        default) for splits that should stay at a uniform ``copies`` per line
        (e.g. val/test).
        """
        output_dir = Path(output_dir)

        lines = self._read_non_empty_lines(text_file, image_dir=image_dir)
        print(f"  Loaded {len(lines)} lines from {text_file}")

        # Build samples
        samples: list[tuple[str, Any]] = []

        if image_dir:
            print("  Using EXISTING IMAGES mode (retry limit ignored)")
            for item in lines:
                filename, text = item
                n = self._copies_for_line(text, copies, rare_chars, rare_char_multiplier)
                for _ in range(n):
                    samples.append((text, filename))
        elif font_mode == "all":
            print("  Using ALL fonts mode")
            fonts_list = self.font_manager.all_fonts
            print(f"  Iterating {len(fonts_list)} fonts per line...")
            # image_dir is falsy here, so _read_non_empty_lines only produced plain str lines.
            for line in cast("list[str]", lines):
                for font_tuple in fonts_list:
                    samples.append((line, (font_tuple[0], font_tuple[1])))
        else:
            print(f"  Using RANDOM fonts mode (retry limit: {retry_limit} attempts per sample)")
            for line in cast("list[str]", lines):
                n = self._copies_for_line(line, copies, rare_chars, rare_char_multiplier)
                for _ in range(n):
                    samples.append((line, None))

        if not samples:
            print("  Generating 0 images...")
            return 0

        random.shuffle(samples)
        file_mode = "a" if append else "w"

        print(f"  Generating {len(samples)} images...")

        success_count, heights = self._generate_split_parallel(
            samples=samples,
            output_dir=output_dir,
            split_name=split_name,
            font_mode=font_mode,
            retry_limit=retry_limit,
            start_idx=0,
            file_mode=file_mode,
            workers=workers,
            image_dir=image_dir,
        )

        print(f"  Generated {success_count} / {len(samples)} images")
        self._print_height_summary(heights)
        print()
        return success_count

    def _print_height_summary(self, heights: list[int]) -> None:
        """Print observed line-height distribution for QA (variable-height modes)."""
        mode = self._cfg.line_height_mode
        print(f"  Line height mode: {mode}")
        if mode != "fixed":
            print(
                f"  Height range: {self._cfg.min_line_height}..{self._cfg.max_line_height} "
                f"step {self._cfg.line_height_step}"
            )
        if heights:
            mean = sum(heights) / len(heights)
            print(f"  Observed heights: min={min(heights)} max={max(heights)} mean={mean:.1f}")

    def generate_dataset(
        self,
        corpus_path: str | Path,
        output_dir: str | Path = "data",
        val_file: str | Path | None = None,
        test_file: str | Path | None = None,
        copies: int = 3,
        font_mode: str = "random",
        retry_limit: int = 10,
        existing_mode: str = "error",
        workers: int = 0,
        split_seed: int = 42,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        image_dir: str | None = None,
        min_length: int = 5,
        max_length: int = 120,
        max_lines: int = 0,
        oversample_rare_chars: bool = False,
        rare_char_percentile: float = 5.0,
        rare_char_multiplier: float = 3.0,
    ) -> dict[str, int]:
        """Generate a complete dataset with train/val/test splits.

        When *oversample_rare_chars* is set, training lines containing one of
        the least-frequent *rare_char_percentile* percent of characters in
        the corpus get their copy count multiplied by *rare_char_multiplier*
        (val/test stay uniform, so evaluation reflects natural frequency).

        Returns a dict of split -> sample count.
        """
        valid_modes = {"error", "append", "overwrite"}
        if existing_mode not in valid_modes:
            raise ValueError(
                f"existing_mode must be one of {sorted(valid_modes)}, got: {existing_mode!r}"
            )
        if not 0.0 <= float(val_ratio) < 1.0:
            raise ValueError("val_ratio must be in [0.0, 1.0).")
        if not 0.0 <= float(test_ratio) < 1.0:
            raise ValueError("test_ratio must be in [0.0, 1.0).")

        val_ratio = float(val_ratio)
        test_ratio = float(test_ratio)

        # An explicit test_file is the sole source of the test split; don't also
        # carve a test set out of the disjoint ratio-based split (mirrors val_file).
        if test_file and Path(test_file).exists():
            test_ratio = 0.0

        print("\n" + "=" * 70)
        print("  Dataset Generation")
        print("=" * 70)

        output_dir = Path(output_dir)

        # Handle existing output
        append_mode = False
        if output_dir.exists() and any(output_dir.iterdir()):
            print(f"\n  Dataset directory '{output_dir}' already exists.")
            if existing_mode == "append":
                append_mode = True
                print("  Continuing generation (appending to existing)...")
            elif existing_mode == "overwrite":
                print("  Cleaning up existing directory...")
                shutil.rmtree(output_dir)
            else:
                raise FileExistsError(
                    "Dataset output already exists. Re-run with "
                    "existing_mode='append' or existing_mode='overwrite'."
                )

        # Create output dirs
        output_dir.mkdir(exist_ok=True)
        (output_dir / "train" / "images").mkdir(parents=True, exist_ok=True)

        will_have_val = bool((val_file and Path(val_file).exists()) or float(val_ratio) > 0.0)
        if will_have_val:
            (output_dir / "val" / "images").mkdir(parents=True, exist_ok=True)

        will_have_test = bool((test_file and Path(test_file).exists()) or float(test_ratio) > 0.0)
        if will_have_test:
            (output_dir / "test" / "images").mkdir(parents=True, exist_ok=True)

        counts: dict[str, int] = {}

        rare_chars: set[str] | None = None
        if oversample_rare_chars:
            freq = char_frequencies(
                corpus_path,
                min_length=min_length,
                max_length=max_length,
                max_lines=max_lines,
                normalizer=self._cfg.normalizer,
            )
            rare_chars = rare_chars_from_frequencies(freq, percentile=rare_char_percentile)
            print(
                f"  Rare-char oversampling: {len(rare_chars)} rare char(s) "
                f"(bottom {rare_char_percentile:g}% of {len(freq)} distinct chars), "
                f"{rare_char_multiplier:g}x copies for lines containing one (train only)"
            )

        if val_file and Path(val_file).exists():
            print("\nGenerating TRAINING set...")
            counts["train"] = self.generate_split(
                text_file=corpus_path,
                output_dir=output_dir / "train",
                split_name="train",
                font_mode=font_mode,
                retry_limit=retry_limit,
                append=append_mode,
                workers=workers,
                image_dir=image_dir,
                copies=copies,
                rare_chars=rare_chars,
                rare_char_multiplier=rare_char_multiplier,
            )

            print("\nGenerating VALIDATION set (from separate file)...")
            counts["val"] = self.generate_split(
                text_file=val_file,
                output_dir=output_dir / "val",
                split_name="val",
                font_mode=font_mode,
                retry_limit=retry_limit,
                append=append_mode,
                workers=workers,
                image_dir=image_dir,
                copies=1,
            )

            if test_file and Path(test_file).exists():
                print("\nGenerating TEST set (from separate file)...")
                counts["test"] = self.generate_split(
                    text_file=test_file,
                    output_dir=output_dir / "test",
                    split_name="test",
                    font_mode=font_mode,
                    retry_limit=retry_limit,
                    append=append_mode,
                    workers=workers,
                    image_dir=image_dir,
                    copies=1,
                )
        else:
            print("\nPreparing disjoint TRAIN/VAL/TEST split from corpus...")
            print(
                f"  Split config: train={(1.0 - val_ratio - test_ratio) * 100:.1f}%, "
                f"val={val_ratio * 100:.1f}%, "
                f"test={test_ratio * 100:.1f}%, seed={split_seed}"
            )

            # Stream corpus through filters into a temp file
            tmp_corpus = tempfile.NamedTemporaryFile(  # noqa: SIM115
                mode="w", suffix=".txt", encoding="utf-8", delete=False
            )
            try:
                filtered_lines = load_corpus(
                    corpus_path,
                    min_length=min_length,
                    max_length=max_length,
                    max_lines=max_lines,
                    normalizer=self._cfg.normalizer,
                )
                for line in tqdm(filtered_lines, desc="  Filtering corpus", unit="line"):
                    tmp_corpus.write(line + "\n")
                tmp_corpus.close()

                all_lines = self._read_non_empty_lines(tmp_corpus.name)
                train_lines, val_lines, test_lines = self._split_lines_without_text_overlap(
                    all_lines, val_ratio=val_ratio, test_ratio=test_ratio, seed=split_seed
                )

                train_unique = len({(t[1] if isinstance(t, tuple) else t) for t in train_lines})
                val_unique = len({(t[1] if isinstance(t, tuple) else t) for t in val_lines})
                test_unique = len({(t[1] if isinstance(t, tuple) else t) for t in test_lines})

                def _text_of(item):
                    return item[1] if isinstance(item, tuple) else item

                overlap_tv = len(
                    {_text_of(x) for x in train_lines} & {_text_of(x) for x in val_lines}
                )
                overlap_tt = len(
                    {_text_of(x) for x in train_lines} & {_text_of(x) for x in test_lines}
                )
                overlap_vt = len(
                    {_text_of(x) for x in val_lines} & {_text_of(x) for x in test_lines}
                )
                print(
                    f"  Split summary: train={len(train_lines)} lines ({train_unique} unique), "
                    f"val={len(val_lines)} lines ({val_unique} unique), "
                    f"test={len(test_lines)} lines ({test_unique} unique), "
                    f"overlaps: train∩val={overlap_tv} train∩test={overlap_tt} val∩test={overlap_vt}"
                )

                temp_train = output_dir / "temp_train.txt"
                temp_val = output_dir / "temp_val.txt"
                temp_test = output_dir / "temp_test.txt"
                self._write_lines(temp_train, train_lines)
                self._write_lines(temp_val, val_lines)
                self._write_lines(temp_test, test_lines)

                try:
                    print("\nGenerating TRAINING set...")
                    counts["train"] = self.generate_split(
                        text_file=temp_train,
                        output_dir=output_dir / "train",
                        split_name="train",
                        font_mode=font_mode,
                        retry_limit=retry_limit,
                        append=append_mode,
                        workers=workers,
                        image_dir=image_dir,
                        copies=copies,
                        rare_chars=rare_chars,
                        rare_char_multiplier=rare_char_multiplier,
                    )

                    if val_lines:
                        print("\nGenerating VALIDATION set (disjoint text split)...")
                        counts["val"] = self.generate_split(
                            text_file=temp_val,
                            output_dir=output_dir / "val",
                            split_name="val",
                            font_mode=font_mode,
                            retry_limit=retry_limit,
                            append=append_mode,
                            workers=workers,
                            image_dir=image_dir,
                            copies=1,
                        )

                    if test_lines:
                        print("\nGenerating TEST set (disjoint text split)...")
                        counts["test"] = self.generate_split(
                            text_file=temp_test,
                            output_dir=output_dir / "test",
                            split_name="test",
                            font_mode=font_mode,
                            retry_limit=retry_limit,
                            append=append_mode,
                            workers=workers,
                            image_dir=image_dir,
                            copies=1,
                        )

                    # Handle separate test_file when val_file path was NOT the primary path
                    if test_file and Path(test_file).exists():
                        print("\nGenerating TEST set (from separate file)...")
                        counts["test"] = self.generate_split(
                            text_file=test_file,
                            output_dir=output_dir / "test",
                            split_name="test",
                            font_mode=font_mode,
                            retry_limit=retry_limit,
                            append=append_mode,
                            workers=workers,
                            image_dir=image_dir,
                            copies=1,
                        )
                finally:
                    for tmp_path in (temp_train, temp_val, temp_test):
                        with contextlib.suppress(FileNotFoundError):
                            tmp_path.unlink()
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_corpus.name)

        print("\n" + "=" * 70)
        print("  Dataset Generation Complete!")
        print("=" * 70)
        for split, count in counts.items():
            print(f"  {split.capitalize()}: {count:,} samples")
        print(f"  Output: {output_dir}")
        print("=" * 70 + "\n")

        return counts
