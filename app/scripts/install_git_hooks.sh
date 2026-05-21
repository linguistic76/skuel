#!/usr/bin/env bash
#
# Install SKUEL Git hooks (pre-commit + pre-push).
#
# Installs symlinks (NOT copies) to the canonical scripts at
# app/scripts/git-hooks/, so edits to those scripts take effect immediately
# without re-running this installer.
#
# Honors core.hooksPath when set (the outer repo here uses it to point at
# app/.git/hooks/). Falls back to .git/hooks/ otherwise. Idempotent — running
# it twice is safe; existing symlinks are refreshed.
#
# Usage:   app/scripts/install_git_hooks.sh
#
# See:     app/scripts/git-hooks/README.md  (what each hook does, how to bypass,
#                                            and the path to stronger hardening)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_DIR="$SCRIPT_DIR/git-hooks"

# Resolve the hooks directory git is actually using.
# - If core.hooksPath is set, git uses that path (absolute).
# - Otherwise it uses $GIT_DIR/hooks.
HOOKS_DIR=$(git config --get core.hooksPath || true)
if [[ -z "$HOOKS_DIR" ]]; then
  HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
fi

mkdir -p "$HOOKS_DIR"

install_hook() {
  local name="$1"
  local source="$CANONICAL_DIR/$name"
  local target="$HOOKS_DIR/$name"

  if [[ ! -f "$source" ]]; then
    echo "✗ Missing canonical hook: $source" >&2
    exit 1
  fi

  # -f overwrites an existing symlink or file; -n treats $target as a regular
  # file even if it's an existing symlink to a directory (defensive).
  ln -snf "$source" "$target"
  chmod +x "$source"

  echo "✓ Installed $name → $source"
}

echo "Installing SKUEL Git hooks…"
echo "  active hooks dir: $HOOKS_DIR"
install_hook pre-commit
install_hook pre-push
echo
echo "Done. Hooks symlink to the canonical scripts — edit those files directly."
echo "Bypass mechanisms and hardening notes: $CANONICAL_DIR/README.md"
