#!/usr/bin/env python3
"""
Pre-commit stamper: set ``updated:`` on every staged doc to the commit date.

Invoked by ``scripts/git-hooks/pre-commit`` (check 0). Makes the field true by
construction so nobody has to remember it — qualified, not exact: ``gh pr merge
--squash`` builds the final commit server-side where no hook runs, so the stamp is
accurate within a merge-latency window, which is what the guard's rot threshold
measures against.

**Index AND worktree, both.** The staged blob is rewritten through
``git hash-object -w`` + ``git update-index --cacheinfo``, and the single
``updated:`` line in the working-tree file is rewritten separately.

Why not the obvious ``git add <path>``: that replaces the index entry with the whole
working-tree file, silently staging every hunk the author deliberately left out of a
``git add -p`` — including content the hook's own secret scan already ran past. This
script never calls ``git add``.

Why the worktree half is not optional: an index-only write leaves the old value on
disk, so ``git status`` shows an unstaged reversal of the stamp after every docs
commit, and the next ``git add`` re-propagates the stale date. Rewriting only that
one line — rather than copying the stamped blob out — preserves the author's other
unstaged hunks.

Bypass: ``SKUEL_SKIP_DOC_STAMP=1``. Its one required use is the backfill commit,
which writes each file's *historical* date and must not be re-stamped to today.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# scripts/ is not a package — these modules are run as scripts, so the sibling
# import resolves at runtime via sys.path[0] but not for MyPy (matches the same
# ignore in scripts/health/stale_names.py).
from docs_updated_field import (  # type: ignore[import-not-found]
    REPO_ROOT,
    apply_stamp,
    find_updated,
    in_scope,
    is_generated,
    today_utc,
)


def _git(*args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        input=stdin,
        capture_output=True,
        check=True,
    ).stdout


def staged_docs() -> list[str]:
    """In-scope docs staged for this commit, repo-root-relative.

    ``-z`` because three docs carry spaces in their filenames; a newline-split list
    turns each into several phantom paths that then fail to stat.
    """
    raw = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode()
    return [path for path in raw.split("\0") if path and in_scope(path)]


def _staged_mode(path: str) -> str:
    """The file mode git already records for this path (usually 100644)."""
    entry = _git("ls-files", "--stage", "--", path).decode().strip()
    return entry.split()[0] if entry else "100644"


def stamp_index(path: str, stamp: date) -> bool:
    """Rewrite the STAGED blob's stamp. True when the index changed.

    Reads the generated-artifact banner from the STAGED content, not the worktree's:
    the staged blob is what will land, and it is what the drift test a generated doc
    carries will be compared against.
    """
    original = _git("show", f":{path}").decode("utf-8")
    if is_generated(original):
        return False
    stamped = apply_stamp(original, stamp)
    if stamped == original:
        return False
    blob = _git("hash-object", "-w", "--stdin", stdin=stamped.encode("utf-8"))
    sha = blob.decode().strip()
    _git("update-index", "--cacheinfo", f"{_staged_mode(path)},{sha},{path}")
    return True


def stamp_worktree(path: str, stamp: date) -> bool:
    """Rewrite the working-tree file's stamp. True when the file changed.

    Operates on the worktree's OWN content, not on the staged blob — the two differ
    under partial staging and copying the blob out would destroy the difference.
    """
    target = REPO_ROOT / path
    if not target.exists():
        # Staged, then deleted from the worktree. The index half still stands.
        return False
    original = target.read_text(encoding="utf-8")
    if is_generated(original):
        return False
    field = find_updated(original)
    stamped = apply_stamp(original, stamp)
    if stamped == original:
        return False
    if field is None:
        # Creating a block in the worktree rewrites the head of the file, which is
        # by construction not inside any hunk the author left unstaged (there is no
        # frontmatter for a hunk to overlap).
        target.write_text(stamped, encoding="utf-8")
        return True
    lines = original.split("\n")
    stamped_lines = stamped.split("\n")
    lines[field.line_index] = stamped_lines[field.line_index]
    target.write_text("\n".join(lines), encoding="utf-8")
    return True


def main() -> int:
    paths = staged_docs()
    if not paths:
        return 0

    stamp = today_utc()
    touched: list[str] = []
    for path in paths:
        index_changed = stamp_index(path, stamp)
        worktree_changed = stamp_worktree(path, stamp)
        if index_changed or worktree_changed:
            touched.append(path)

    if touched:
        noun = "doc" if len(touched) == 1 else "docs"
        print(f"🕒 Stamped updated: {stamp.isoformat()} on {len(touched)} {noun}")
        for path in touched:
            print(f"    {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
