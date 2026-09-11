# Wiki source

This directory is the **source of truth** for the [khocr-gen GitHub wiki](https://github.com/LazyGreed/khocr-gen/wiki).

Each `.md` file here maps 1:1 to a wiki page (the filename, minus `.md`, is the page title — dashes
become spaces). `_Sidebar.md` and `_Footer.md` are GitHub's special navigation pages.

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

The script clones the wiki git repository, copies every `.md` from this directory, commits and
pushes. Wiki content is **not** part of the main repository history — the main repo only holds this
source copy.

Editing a page: change the file here, run the publish script, and keep the change in the same
commit as any code change it documents (see
[Development](https://github.com/LazyGreed/khocr-gen/wiki/Development)).

## Relationship to `docs/`

The two documentation sets are independent and neither is generated from the other:

| | `docs/*.md` | `wiki/*.md` |
|---|---|---|
| Audience | contributors reading the repo | users reading the published wiki |
| Shipped in | the repository and the source distribution | nothing — the wiki is a separate git repository |
| Authoritative for | long-form design notes (e.g. `VARIABLE_LENGTH_DESIGN.md`) | the published wiki pages |

When a change alters behaviour, setup, configuration or usage, update the affected file in **both**
sets in the same commit if both cover the topic. Don't fix one and leave the other stale.

## Note on wiki bootstrap

GitHub does not create the `<repo>.wiki.git` repository until the first page is created through the
web UI. If `publish_wiki.sh` fails with `Repository not found` on a brand-new repository, open
`https://github.com/<owner>/<repo>/wiki`, click **Create the first page**, save, and re-run the
script.
