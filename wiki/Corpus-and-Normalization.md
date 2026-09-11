# Corpus and Normalization

The corpus is the source of every label in your dataset. It is a plain UTF-8 text file with **one
string per line**.

```text
សួស្តី
Hello World
ស្វាគមន៍ Welcome
```

Mixed Khmer/English lines are the point of the tool — include them liberally.

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --output data
```

`--corpus` defaults to `corpus/corpus.txt`.

## Filtering

| Flag | Default | Meaning |
|------|---------|---------|
| `--min-length N` | 1 | Drop lines shorter than N characters |
| `--max-length N` | 260 | Drop lines longer than N characters |
| `--lines N` | 0 | Use at most N lines (0 = all) |

### Preview before you commit

`--count-only` prints filter statistics and the estimated image count, then exits without
generating anything:

```bash
khocr-gen generate --corpus corpus/corpus.txt --count-only
```

This is the cheapest way to sanity-check length filters and `--copies` before a long run.

## Train / val / test splits

The corpus is split into three **disjoint** sets of *text strings* — no line of text ever appears in
two splits. Splitting is deterministic given `--seed` (default 42).

| Situation | Result |
|-----------|--------|
| Neither `--val-percent` nor `--test-percent` given | 80% train / 10% val / 10% test |
| Only `--val-percent 15` | 85% train / 15% val / **0% test** |
| Only `--test-percent 15` | 85% train / **0% val** / 15% test |
| `--split-ratios 70 15 15` | explicit ratios, normalised to sum to 1.0 |
| `--split-ratios 100 0 0` or both percents 0 | no val/test split |
| `--test-file FILE` | FILE is the **sole** source of the test split |

`--split-ratios` overrides `--val-percent`/`--test-percent` when both are supplied.

```bash
# 80/10/10 (default)
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts

# 85/15/0 — no test split
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --val-percent 15

# Explicit ratios
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --split-ratios 70 15 15

# Fixed held-out test corpus, carved from a file rather than by ratio
khocr-gen generate --corpus corpus/train.txt --test-file corpus/test.txt --fonts fonts
```

`--seed` also controls the shuffle that decides *which* texts land in which split, so the same
corpus + seed reproduces the same split exactly.

> `--seed` does **not** seed rendering or augmentation randomness. See
> **[Variable Line Height](Variable-Line-Height)** for the details.

## Rare-character oversampling

Khmer (and mixed) corpora often have a long tail: a handful of characters appear a few times while
others dominate. Undersampling the tail hurts recognition of exactly the characters that are
hardest to learn.

`--oversample-rare-chars` renders **extra copies** of training lines that contain rare characters:

| Flag | Default | Meaning |
|------|---------|---------|
| `--oversample-rare-chars` | off | Enable tail oversampling |
| `--rare-char-percentile PCT` | 5.0 | Least-frequent PCT% of distinct characters count as "rare" |
| `--rare-char-multiplier F` | 3.0 | Copy multiplier applied to training lines containing a rare character |

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts \
  --oversample-rare-chars --rare-char-percentile 20 --rare-char-multiplier 3.0
```

**val and test are never oversampled** — they stay at one copy per line, so your evaluation split
continues to reflect the natural corpus distribution. Oversampling affects `train` only.

## Text normalization

Khmer text needs canonical character ordering to render and label consistently, and real-world
corpora carry encoding detritus (curly quotes, stray emoji, URLs, zero-width spaces). Normalization
runs on the corpus before rendering.

| Flag | Default | Effect |
|------|---------|--------|
| `--norm-unicode-norm` | `NFKC` | Unicode normalization form |
| `--norm-emoji-replacement STR` | `""` | Replacement string for emoji |
| `--norm-url-replacement STR` | `""` | Replacement string for URLs |
| `--norm-no-remove-zwsp` | off | **Keep** zero-width spaces |
| `--norm-no-fix-encoding` | off | Disable ftfy encoding fixes |
| `--norm-no-uncurl-quotes` | off | Disable quote uncurling |
| `--norm-no-fix-line-breaks` | off | Disable line-break normalization |
| `--norm-passthrough` | off | Skip **all** normalization |

Notes:

- Normalization is provided by [khmernormalizer](https://github.com/seanghay/khmernormalizer) (MIT),
  which normalizes Khmer internally.
- `--norm-passthrough` is the nuclear option: nothing is normalized. Use it only when your corpus
  is already canonical and you want byte-exact labels.
- The `norm_no_*` flags are negative switches — they *disable* an individual fix. Spelling matters.

## Using pre-existing images (`--image-dir`)

`--image-dir DIR` bypasses text rendering entirely and uses images you already have. In this mode
the "corpus" must be a **`labels.txt`** file (the same `path<TAB>label` format the generator
writes), since labels are read from it rather than rendered.

This is how you fold an existing dataset into the same pipeline, LMDB packing and `combine` flow.
See **[Output and Storage](Output-and-Storage)** for the label format.

## Practical advice

- **Keep lines realistic.** Line lengths in the corpus should match what your OCR model will see at
  inference; the default `--max-length 260` is a guard rail, not a target.
- **Check the tail.** Run `--count-only` and look at the statistics before a long run.
- **Use `--test-file` for benchmarks.** A frozen, hand-curated test corpus makes model comparisons
  meaningful across runs, unlike a ratio-split that moves as the corpus grows.
- **Split before you augment.** Splits are disjoint at the *text* level, so an augmented variant of a
  training line can never leak into val/test.

## See also

- **[CLI Reference](CLI-Reference)** — the Corpus flag tables
- **[Output and Storage](Output-and-Storage)** — `labels.txt`, `vocab.json`, `metadata.jsonl`
- **[Configuration](Configuration)** — the same settings as YAML keys
