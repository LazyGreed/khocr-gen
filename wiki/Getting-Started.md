# Getting Started

This page takes you from nothing to a training-ready dataset and shows you how to inspect what
came out. Every command below is copy-pasteable.

## 0. Before you start

You need:

- Python **3.12 or newer**
- A Khmer font and an English font (`.ttf` / `.otf`)
- A UTF-8 text corpus — one string per line

## 1. Install

```bash
pip install khocr-gen
```

For development installs, Rust acceleration, or offline/`uv` setups see **[Installation](Installation)**.

Confirm the CLI is on your `PATH`:

```bash
khocr-gen --version
khocr-gen --help
```

## 2. Lay out fonts

Create two subdirectories — the names matter:

```text
fonts/
├── khmer/     <- .ttf / .otf Khmer fonts
└── english/   <- .ttf / .otf English fonts
```

Font files dropped *directly* in `fonts/` (not in a subdirectory) are added to **both** pools as
fallbacks. See **[Fonts](Fonts)** for variant (bold/italic) handling and coverage checks.

## 3. Prepare a corpus

A plain UTF-8 text file with one string per line:

```text
សួស្តី
Hello World
ស្វាគមន៍ Welcome
```

Mixed Khmer/English on one line is the point of the tool. See
**[Corpus and Normalization](Corpus-and-Normalization)** for filtering, split control, and
rare-character oversampling.

## 4. Generate a dataset

```bash
khocr-gen generate \
  --corpus corpus/corpus.txt \
  --fonts fonts \
  --output data \
  --copies 3 \
  --storage lmdb
```

What this does:

- splits the corpus into `train` / `val` / `test` (default 80/10/10),
- renders `--copies` augmented variants of every training line,
- writes images + `labels.txt` + `vocab.json`,
- packs everything into LMDB and deletes the raw images (`--storage lmdb`).

Resulting layout:

```text
data/
├── train/
│   ├── lmdb/          <- data.mdb, lock.mdb
│   └── labels.txt
├── val/
│   └── ...
├── test/
│   └── ...
└── vocab.json
```

Use `--storage both` to keep the raw image files as well. Full layout details are in
**[Output and Storage](Output-and-Storage)**.

### One-liner with a config file

Instead of long flag lists, put the recipe in YAML:

```bash
khocr-gen generate --config configs/generate.yml
```

`khocr-gen generate` with no `--config` auto-detects `configs/generate.yml` when it exists. See
**[Configuration](Configuration)**.

## 5. Verify the augmentations look right

Render every augmentation method at fixed MIN and MAX intensity on clean canvases:

```bash
khocr-gen verify --fonts fonts --output verify_output
```

Output is one PNG per method with the MIN column on the left and the MAX column on the right.
You can also verify individual text decorations and effects:

```bash
khocr-gen verify --fonts fonts --method text_deco_bold text_effect_glow
```

## 6. Inspect a generated dataset

```bash
# Summary of an LMDB database
khocr-gen view --lmdb data/train/lmdb --summary

# Extract images (and labels) to a directory
khocr-gen view --lmdb data/train/lmdb --output-dir extracted

# Print labels only
khocr-gen view --lmdb data/train/lmdb --labels-only
```

## 7. Merge datasets

Multiple generation runs can be merged into one LMDB dataset:

```bash
khocr-gen combine data_run1 data_run2 data_run3 --output data_merged
```

A merged `vocab.json` covering every character across all merged splits is written too.

## Where to go next

| I want to… | Read |
|------------|------|
| Understand every flag | [CLI Reference](CLI-Reference) |
| Write a reproducible recipe | [Configuration](Configuration) |
| Tune augmentations for my domain | [Augmentation](Augmentation) |
| Vary image heights | [Variable Line Height](Variable-Line-Height) |
| Add color, underlines, glow, shadows | [Text Decorations and Effects](Text-Decorations-and-Effects) |
| Speed up generation | [Rust Acceleration](Rust-Acceleration) |
| Something broke | [Troubleshooting](Troubleshooting) |

## Minimal end-to-end script

```bash
set -euo pipefail

pip install khocr-gen

mkdir -p fonts/khmer fonts/english corpus
# ... copy your .ttf fonts and write corpus/corpus.txt ...

khocr-gen generate \
  --corpus corpus/corpus.txt \
  --fonts fonts \
  --output data \
  --copies 3 \
  --storage both \
  --line-height-mode variable --min-line-height 32 --max-line-height 96 --line-height-step 8 \
  --font-size-mode proportional \
  --blur-prob 0.4 --rotation-prob 0.2 --jpeg-compression-prob 0.4

khocr-gen view --lmdb data/train/lmdb --summary
khocr-gen verify --fonts fonts --output verify_output
```
