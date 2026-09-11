# Output and Storage

## Dataset layout

`khocr-gen generate --output data` produces:

```text
data/
├── train/
│   ├── images/                  <- raw image files (unless --storage lmdb)
│   │   ├── 000001.png
│   │   └── ...
│   ├── labels.txt               <- path<TAB>label, one row per image
│   ├── metadata.jsonl           <- only with --record-metadata
│   ├── generation_errors.jsonl  <- written when samples fail to render
│   └── lmdb/                    <- only with --storage lmdb|both
│       ├── data.mdb
│       └── lock.mdb
├── val/
│   └── ... (same structure)
├── test/
│   └── ... (same structure)
└── vocab.json
```

`val/` and `test/` are omitted when their split ratio is 0.

## Image files

| Flag | Default | Meaning |
|------|---------|---------|
| `--output-format {png,jpg,tiff}` | `jpg` | Container format for the raw images |
| `--jpeg-quality N` | 90 | JPEG quality (0–100), used for `jpg` output |
| `--width PX` | *auto* | Fixed width; omit for width-following-content |
| `--random-align-when-padded` | off | Random left/center/right alignment within a fixed width |
| `--color-mode {1,3}` | 1 | 1 = grayscale, 3 = RGB |

Variable heights (from `--line-height-mode`) mean image dimensions are **not** fixed across a
dataset. Any downstream loader must handle that — see **[Variable Line Height](Variable-Line-Height)**.

## `labels.txt`

The label file is intentionally boring: one row per image, tab-separated.

```text
images/000001.png	សួស្តី
images/000002.png	Hello World
images/000003.png	ស្វាគមន៍ Welcome
```

- Path is **relative to the split directory**.
- Delimiter is a single **tab**; any tab inside a label is replaced before writing.
- The format does not change with variable line height or decorations — image dimensions carry that
  information, not the label file.

## `vocab.json`

A character → index map covering every character in the generated labels of all splits.

```json
{
  "<unk>": 0,
  " ": 1,
  "H": 2,
  "e": 3
}
```

| Flag | Meaning |
|------|---------|
| `--vocab FILE` | Write the vocabulary to a specific path |
| `--skip-vocab` | Do not build a vocabulary at all |

The vocabulary is built by scanning the labels files, so it only contains characters that were
actually generated.

## `metadata.jsonl`

Written when `--record-metadata` is set — one JSON object per image, in generation order:

```json
{"image": "000001.png", "text": "សួស្តី", "width": 384, "height": 64, "font": "KhmerOS.ttf", "font_size": 42, "decorations": ["bold"]}
```

| Key | Meaning |
|-----|---------|
| `image` | Image filename |
| `text` | Ground-truth label |
| `width`, `height` | Actual image dimensions in pixels |
| `font` | Font file used |
| `font_size` | Font size used for rendering |
| `decorations` | Active decoration names, or null |

This is the sidecar to use for QA renders, diagnosing clipping, measuring the height distribution,
and reproducing individual samples.

## `generation_errors.jsonl`

Written when one or more samples fail to render (for example, no font in the pool covers a line
within `--retry-limit`). Check it after a run if your expected image count does not match the actual
count — a silent shortfall usually means fonts, not the corpus.

## Storage modes

`--storage {raw,lmdb,both}` selects what is kept on disk:

| Mode | Behaviour |
|------|-----------|
| `raw` *(default)* | Write image files; nothing else |
| `lmdb` | Pack into LMDB, then **delete** the raw image files |
| `both` | Write image files **and** pack LMDB, keeping both |

```bash
khocr-gen generate --corpus corpus/corpus.txt --fonts fonts --storage both
```

### LMDB options

| Flag | Default | Meaning |
|------|---------|---------|
| `--lmdb-jpeg-quality N` | 90 | JPEG quality for images stored in LMDB (independent of `--jpeg-quality`) |
| `--lmdb-map-size-gb N` | 256 | LMDB map size in GiB — **raise this for large datasets** |
| `--lmdb-verbose` | off | Print skipped/corrupt image warnings during packing |

### LMDB key layout

Keys are plain strings, so any LMDB client can read the database without this package:

| Key | Value |
|-----|-------|
| `image-000000001`, `image-000000002`, … | JPEG-encoded image bytes |
| `label-000000001`, `label-000000002`, … | UTF-8 label bytes |
| `num-samples` | Sample count as an ASCII integer |

Image and label keys share the same zero-padded index, so `image-N` pairs with `label-N`.

Packing is batched: writes are committed every N samples or once a byte threshold of encoded image
data accumulates, so very large datasets do not build up unbounded pending state.

### Legacy flags

`--pack-lmdb` and `--keep-raw` predate `--storage` and still work:

| Legacy | Equivalent |
|--------|-----------|
| `--pack-lmdb` | `--storage lmdb` |
| `--pack-lmdb --keep-raw` | `--storage both` |

Prefer `--storage`.

## Appending and overwriting

| Flag | Behaviour |
|------|-----------|
| *(neither)* | Create the output directory; error if it already exists |
| `--append` | Add new samples to an existing output |
| `--overwrite` | Delete and recreate the output directory |

`--append` and `--overwrite` are mutually exclusive.

## Reading data back

```bash
# Summary: sample count and key stats
khocr-gen view --lmdb data/train/lmdb --summary

# Extract images and labels
khocr-gen view --lmdb data/train/lmdb --output-dir extracted

# Print labels only
khocr-gen view --lmdb data/train/lmdb --labels-only

# Limit how much is read
khocr-gen view --lmdb data/train/lmdb --count 50
```

`--count 0` (the default) reads everything, capped by `--max-count` (default 100) when `--count` is
not given explicitly.

## Merging datasets

```bash
khocr-gen combine data_run1 data_run2 data_run3 --output data_merged
```

Each input may have `train/` and/or `val/` subdirectories, and each split may be raw
(`labels.txt` + `images/`) or LMDB (`lmdb/`) — they can be mixed freely. **The merged output is
always LMDB.** A merged `vocab.json` covering every character across all merged splits is written to
the output directory.

| Flag | Default | Meaning |
|------|---------|---------|
| `-o, --output DIR` | `data_combined` | Output directory |
| `--overwrite` | off | Overwrite the output directory without prompting |
| `--keep-raw` | off | Keep raw images after LMDB packing |
| `--jpeg-quality N` | 90 | JPEG quality |
| `--map-size-gb N` | 256 | LMDB map size in GiB |
| `--vocab FILE` | `OUTPUT/vocab.json` | Where to write the merged vocabulary |
| `--skip-vocab` | off | Do not write a merged vocabulary |
| `--verbose` | off | Print merge and packing progress |

`combine` accepts `--config` and auto-detects `configs/combine.yml` — see
**[Configuration](Configuration)**.

## Workers and timeouts

| Flag | Default | Meaning |
|------|---------|---------|
| `--workers N` | 0 | Worker processes; 0 = auto-sized, 1 = serial |
| `--worker-timeout SEC` | 300 | Seconds before a worker batch is considered timed out |

Worker count and chunk size are resolved automatically from the dataset size, so small runs stay
serial and large runs scale out. Set `KHOCR_GEN_MP_START_METHOD` to `fork` or `spawn` to override
the multiprocessing start method (see **[Troubleshooting](Troubleshooting)**).

## See also

- **[CLI Reference](CLI-Reference)** — every flag
- **[Architecture](Architecture)** — the pipeline that produces these files
- **[Corpus and Normalization](Corpus-and-Normalization)** — what goes in
