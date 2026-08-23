#!/usr/bin/env bash
#
# install-git-hooks.sh — install the repo's git hooks.
#
# Git hooks live in .git/hooks/, which is not version-controlled, so the
# hooks themselves are committed under scripts/git-hooks/ and copied here.
# Run this after cloning (and again after pulling updates to the hooks):
#
#     ./scripts/install-git-hooks.sh
#
# Installs:
#   pre-commit — ruff format --check on staged Python files
#   pre-push   — ruff format --check + ruff check on the whole tree (CI gate)
#
# Idempotent: re-running overwrites the installed copies with the current
# committed versions.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/git-hooks"
DEST="$ROOT/.git/hooks"

if [ ! -d "$DEST" ]; then
    echo "error: $DEST does not exist — run this from inside a git checkout." >&2
    exit 1
fi

for hook in pre-commit pre-push; do
    if [ ! -f "$SRC/$hook" ]; then
        echo "error: $SRC/$hook is missing." >&2
        exit 1
    fi
    cp "$SRC/$hook" "$DEST/$hook"
    chmod +x "$DEST/$hook"
    echo "installed $DEST/$hook"
done

echo
echo "Hooks installed. They run the ruff gates locally; skip with"
echo "  git commit --no-verify   /   git push --no-verify"
echo "Re-run this script after pulling updates to scripts/git-hooks/."
