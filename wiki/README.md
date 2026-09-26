# Wiki source

This directory is the **source of truth** for the [khocr-gen GitHub wiki](https://github.com/LazyGreed/khocr-gen/wiki).

Every `.md` file except `README.md` maps to a wiki page (the filename, minus `.md`, is the page
title; dashes become spaces). `_Sidebar.md` and `_Footer.md` are GitHub's special navigation pages.
`README.md` documents this source directory and is not published.

## Pages

| File | Wiki page |
|------|-----------|
| `Home.md` | Home |
| `Getting-Started.md` | Getting Started |
| `Installation.md` | Installation |
| `CLI-Reference.md` | CLI Reference |
| `Configuration.md` | Configuration |
| `Corpus-and-Normalization.md` | Corpus and Normalization |
| `Fonts.md` | Fonts |
| `Variable-Line-Height.md` | Variable Line Height |
| `Text-Decorations-and-Effects.md` | Text Decorations and Effects |
| `Augmentation.md` | Augmentation |
| `Output-and-Storage.md` | Output and Storage |
| `Architecture.md` | Architecture |
| `Rust-Acceleration.md` | Rust Acceleration |
| `Development.md` | Development |
| `FAQ.md` | FAQ |
| `Troubleshooting.md` | Troubleshooting |
| `_Sidebar.md` | sidebar navigation |
| `_Footer.md` | footer |

## Publishing

```bash
./scripts/publish_wiki.sh
```

The script clones the wiki git repository, copies every publishable `.md` from this directory,
commits and pushes. Wiki content is **not** part of the main repository history. The main repo only
holds this source copy.

Editing a page: change the file here, run the publish script, and keep the change in the same
commit as any code change it documents (see
[Development](https://github.com/LazyGreed/khocr-gen/wiki/Development)).

## Relationship to `docs/`

The sets are maintained separately and neither is generated from the other:

| | `docs/*.md` | `wiki/*.md` |
|---|---|---|
| Audience | contributors using in-repository references | users following the published guides |
| Shipped in | the repository and source distribution | a separate GitHub wiki repository |
| Main content | CLI, configuration, augmentation and Rust references; archived proposals | installation, walkthroughs, and topic guides |

Code and tests define current behavior. When both sets describe a changed behavior, setup, or
option, update both. Keep archived proposals as historical records.

## Note on wiki bootstrap

GitHub does not create the `<repo>.wiki.git` repository until the first page is created through the
web UI. If `publish_wiki.sh` fails with `Repository not found` on a brand-new repository, open
`https://github.com/<owner>/<repo>/wiki`, click **Create the first page**, save, and re-run the
script.
