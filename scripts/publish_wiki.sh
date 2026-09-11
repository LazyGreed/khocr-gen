#!/usr/bin/env bash
#
# Publish wiki/*.md to the project's GitHub wiki.
#
# Usage:
#   ./scripts/publish_wiki.sh [remote-url]
#
# Defaults to the .wiki.git remote derived from `git remote get-url origin`.
#
# Note: GitHub does not create <repo>.wiki.git until the first wiki page has been
# saved through the web UI. On a brand-new repository, open
# https://github.com/<owner>/<repo>/wiki, click "Create the first page", save, and
# re-run this script.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wiki_src="$repo_root/wiki"

if [ ! -d "$wiki_src" ]; then
    echo "error: wiki source directory not found: $wiki_src" >&2
    exit 1
fi

if [ "$#" -ge 1 ]; then
    wiki_remote="$1"
else
    origin="$(git -C "$repo_root" remote get-url origin)"
    wiki_remote="${origin%.git}.wiki.git"
fi

wiki_clone="$(mktemp -d)"
trap 'rm -rf "$wiki_clone"' EXIT

echo "==> Cloning $wiki_remote"
if ! git clone --quiet "$wiki_remote" "$wiki_clone"; then
    echo "error: could not clone the wiki repository." >&2
    echo "If this is a fresh repository, create the first page via the web UI:" >&2
    echo "  https://github.com/<owner>/<repo>/wiki  ->  Create the first page" >&2
    exit 1
fi

echo "==> Copying pages from $wiki_src"
find "$wiki_clone" -maxdepth 1 -name '*.md' -delete
# README.md documents the wiki source itself and is not a wiki page.
find "$wiki_src" -maxdepth 1 -name '*.md' ! -name 'README.md' -exec cp {} "$wiki_clone/" \;

cd "$wiki_clone"
git add -A
if git diff --cached --quiet; then
    echo "==> Wiki already up to date; nothing to publish."
    exit 0
fi

git commit --quiet -m "docs: sync wiki from repository wiki/ directory"
git push --quiet origin HEAD

echo "==> Published $(find . -maxdepth 1 -name '*.md' | wc -l) pages to the wiki."
