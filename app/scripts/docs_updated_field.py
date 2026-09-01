#!/usr/bin/env python3
"""
Shared mechanics for the docs ``updated:`` frontmatter stamp.

One module, three consumers — the pre-commit stamper (``stamp_docs_updated.py``),
the one-shot backfill (``backfill_docs_updated.py``) and the guard
(``scripts/health/docs_updated.py``). Splitting "which files are in scope", "where
is the ``updated:`` line" and "which commits are stamp-only" across three
implementations would make each one a catalog copy of the others, and the copies
would drift the first time scope changed. See ``docs/roadmap/deferred-work.md``
§ Catalog Copies in Code.

Design constraints, each paid for by a registered trap:

**Never ``yaml.safe_load`` the frontmatter to find this field.** 35 of 412 docs
(measured 2026-08-31 on ``dec83d3f6``) carry an unquoted ``title: ADR-013: KU UID
Flat Identity Design`` — a colon-space inside a plain scalar, which is a YAML
syntax error. A YAML-parsing guard reports all 35 as unparsable and sits red for a
``title:`` defect it does not own; a YAML-parsing backfill silently skips them.
Their ``updated:`` line is perfectly well-formed. So: take the leading block with
``split_frontmatter`` (the mandated parser), then match ``^updated:`` line-scoped
inside that block only. That is a strictly smaller claim than "this is valid YAML",
and it is the only claim this feature needs.

**Leading block only, never the whole file.** ``docs/README.md`` and
``patterns/CYPHER_VS_APOC_STRATEGY.md`` each carry a real ``updated:`` in
frontmatter and a documentation *example* of one in the body (measured: exactly
those two of 412). A whole-file ``^updated:`` count calls both duplicates, and the
guard would sit permanently red on correct documents.

**Column 0 only.** ``^updated:`` anchored at the start of a line inside the block
cannot match a nested ``  updated:`` under some other mapping. No in-scope doc has
one today; the anchor is what keeps that true.

**UTC everywhere.** Stamping and comparison both normalise to UTC. An author east
of UTC committing just after local midnight would otherwise stamp tomorrow's date
against a commit still carrying today's, and the upper bound would reject a correct
stamp as a future date. This machine is ``-0700``, where the bug is invisible — do
not conclude from local testing that it is absent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.utils.frontmatter import split_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # /home/mike/skuel
APP_DIR = REPO_ROOT / "app"

# Repo-root-relative, because `git log` speaks repo-root-relative and joining the
# two path bases on anything else silently matches nothing — the failure that made
# the first census of this corpus read a clean `0 stale`.
SCOPE_PREFIX = "app/docs/"

# How far `updated:` may lag the last substantive commit before the guard fails.
#
# The comparison is a ROT THRESHOLD rather than an equality check (ruled by Mike,
# 2026-09-01) because `gh pr merge --squash` builds the final commit server-side
# where no local hook runs, and rewrites the author date as well as the committer
# date — so a correctly stamped doc legitimately trails its own merge commit.
#
# 7 days is: >= the worst realistic squash-merge latency (a PR that sits over a
# weekend plus review), + 1 day of timezone-boundary skew, and still well under
# the rot it exists to catch — of the 162 docs measured stale on 2026-08-31, 149
# lag by more than 7 days and 125 by more than a month.
ROT_WINDOW_DAYS = 7

# One day of slack on the upper bound, for the same timezone boundary. Without it a
# stamp written on the author's local date can read as "later than every commit
# that touched the file" and fail as a future date.
FUTURE_SKEW_DAYS = 1

_UPDATED_LINE = re.compile(r"^updated\s*:(?P<value>.*)$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FENCE = re.compile(r"^---\s*$")


def in_scope(repo_relative_path: str) -> bool:
    """Is this repo-root-relative path a doc this feature stamps?

    ``app/docs/**/*.md`` and nothing else. Three neighbours were considered and
    deliberately excluded (decided in the shipping PR, recorded in deferred-work.md):

    - ``app/.claude/skills/**`` — SKILL.md already carries ``last_updated`` and the
      cross-reference validator reads a human-set ``last_reviewed``. A third date
      key would be a duplicated fact, and auto-stamping a *review* date would
      destroy the one thing it means. 0 of 30 carry ``updated:`` today.
    - root ``AGENTS.md`` / ``CLAUDE.md`` — always-loaded instruction files with no
      frontmatter at all. A stamp there would put a date in every context window
      and be read by nobody; these are read in full, not sampled for freshness.
    - ``docs/roadmap/done/`` and other pinned archives — NOT exempted. A frozen doc
      is not edited, so its stamp already equals its last substantive commit and
      the guard stays green on it for free; an exemption would only create a hole
      for the day someone does edit one.
    """
    return repo_relative_path.startswith(SCOPE_PREFIX) and repo_relative_path.endswith(
        ".md"
    )


@dataclass(frozen=True)
class UpdatedField:
    """Where the ``updated:`` key sits in a document, and what it says.

    ``line_index`` indexes into the FILE's lines, not the frontmatter block's, so a
    caller can rewrite exactly that one line and leave every other byte alone.
    """

    line_index: int
    raw_value: str
    occurrences: int

    @property
    def value(self) -> str:
        """The date text with surrounding whitespace and any quotes removed.

        25 of 219 docs write ``updated: '2026-04-20'``. A parser that does not strip
        quotes classifies every one of them as fieldless — which is how the first
        census of this corpus counted 194 present when the true figure was 219.
        """
        return self.raw_value.strip().strip("'\"")

    @property
    def parsed(self) -> date | None:
        """The value as a date, or None when it is not a bare ISO ``YYYY-MM-DD``."""
        text = self.value
        if not _ISO_DATE.match(text):
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None


def find_updated(content: str) -> UpdatedField | None:
    """Locate ``updated:`` in the leading YAML block. None when there is no key.

    ``occurrences`` counts every column-0 ``updated:`` **inside the block**, so a
    caller can fail on a genuine duplicate without a body example tripping it.
    """
    raw, _ = split_frontmatter(content)
    if raw is None:
        return None

    block_lines = raw.split("\n")
    hits = [
        (index, match)
        for index, line in enumerate(block_lines)
        if (match := _UPDATED_LINE.match(line))
    ]
    if not hits:
        return None

    first_index, first_match = hits[0]
    # +1 for the opening `---` fence, which split_frontmatter strips from `raw`.
    return UpdatedField(
        line_index=first_index + 1,
        raw_value=first_match.group("value"),
        occurrences=len(hits),
    )


def apply_stamp(content: str, stamp: date) -> str:
    """Return ``content`` with its ``updated:`` set to ``stamp``.

    Rewrites the existing key **in place** — never appends a second one — preserving
    the author's quoting style. When the document has no frontmatter at all, the
    block is CREATED rather than skipped: a new doc lands through a perfectly normal
    commit, and skipping it is the hook failing at its one job.

    Returns ``content`` unchanged when the stamp already reads ``stamp``, so callers
    can treat "no change" as "nothing to write" without a second comparison.
    """
    field = find_updated(content)
    stamp_text = stamp.isoformat()

    if field is not None:
        if field.value == stamp_text:
            return content
        lines = content.split("\n")
        quoted = field.raw_value.strip().startswith(("'", '"'))
        lines[field.line_index] = (
            f"updated: '{stamp_text}'" if quoted else f"updated: {stamp_text}"
        )
        return "\n".join(lines)

    raw, _body = split_frontmatter(content)
    if raw is not None:
        # A frontmatter block with no `updated:` key — insert it as the last key of
        # the block, ahead of the closing fence, rather than rebuilding the block.
        lines = content.split("\n")
        closing = next(
            index
            for index in range(1, len(lines))
            if _FENCE.match(lines[index]) and index > 0
        )
        lines.insert(closing, f"updated: {stamp_text}")
        return "\n".join(lines)

    # No frontmatter at all: create the block. The blank separator line is emitted
    # only when the document does not already start with one — stripping the
    # author's own leading blank would turn a pure insertion into an insertion PLUS
    # a deletion, and the guard's stamp-only shortlist (bounded at one deletion)
    # would then read the backfill commit as substantive and fail on that file.
    # Exactly one in-scope doc starts with a newline today; the bound is what keeps
    # a second one from being a silent regression.
    separator = "" if content.startswith("\n") else "\n"
    return f"---\nupdated: {stamp_text}\n---\n{separator}{content}"


# ---------------------------------------------------------------------------
# Commit history — "when did this file last change for a reason that is not the
# stamp itself?"
# ---------------------------------------------------------------------------


def _run_git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _utc_date(iso_with_offset: str) -> date:
    return datetime.fromisoformat(iso_with_offset).astimezone(UTC).date()


@dataclass(frozen=True)
class FileHistory:
    """Commit dates for one doc, in UTC."""

    newest: date
    last_substantive: date


# A stamp-only change is at most: one `updated:` line replaced (1 insertion, 1
# deletion), or a created block (`---`, `updated:`, `---`, blank = 4 insertions, 0
# deletions). Anything bigger cannot be stamp-only, so it never needs confirming.
# This shortlist only has to avoid MISSING a candidate; `_is_stamp_only` decides.
_MAX_STAMP_INSERTIONS = 4
_MAX_STAMP_DELETIONS = 1


def _is_stamp_only_line(line: str) -> bool:
    """Is this one added/removed diff line explicable as stamp bookkeeping?

    Fences and blank lines are allowed because *creating* a frontmatter block emits
    them; the substance of the change still has to be the ``updated:`` key.
    """
    payload = line[1:]
    return (
        _UPDATED_LINE.match(payload) is not None
        or _FENCE.match(payload) is not None
        or payload.strip() == ""
    )


def _stamp_only_files(commit: str) -> set[str]:
    """Paths in ``commit`` whose diff touches nothing but the ``updated:`` stamp.

    ``git log --name-only`` cannot answer this — it emits paths, not changed lines —
    which is why this is a second pass over a shortlist rather than one traversal.
    """
    diff = _run_git(
        "show",
        "-U0",
        "--format=",
        "--no-renames",
        commit,
        "--",
        SCOPE_PREFIX,
    )
    per_file: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("--- ") or line.startswith("diff --git"):
            continue
        elif current and line[:1] in "+-" and not line.startswith(("+++", "---")):
            per_file[current].append(line)

    return {
        path
        for path, changed in per_file.items()
        if changed and all(_is_stamp_only_line(line) for line in changed)
    }


def load_history(paths: set[str]) -> dict[str, FileHistory]:
    """Newest and last-substantive commit date per path, both UTC.

    Substantive means "not a stamp-only commit". Without that exclusion the backfill
    invalidates itself the instant it lands: it becomes the newest commit for every
    file it rewrote, so every historical date it just wrote predates it and the
    guard fails on nearly the whole corpus.

    Two stages, because the cheap traversal cannot see line content. ``--numstat``
    shortlists commits small enough to *possibly* be stamp-only; ``git show`` then
    confirms only those. In a healthy tree the shortlist is a handful of commits.
    """
    log = _run_git(
        "log",
        "--numstat",
        "--no-renames",
        "--format=%H %cI",
        "--",
        SCOPE_PREFIX,
    )

    # commit -> {path: (insertions, deletions)}, newest first
    commits: list[tuple[str, date, dict[str, tuple[int, int]]]] = []
    current_sha = ""
    current_date: date | None = None
    current_files: dict[str, tuple[int, int]] = {}
    for line in log.split("\n"):
        if not line.strip():
            continue
        header = re.match(r"^([0-9a-f]{40}) (\S+)$", line)
        if header:
            if current_sha:
                commits.append((current_sha, current_date, current_files))  # type: ignore[arg-type]
            current_sha = header.group(1)
            current_date = _utc_date(header.group(2))
            current_files = {}
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        if path not in paths:
            continue
        # "-" is git's marker for a binary file; not a stamp change either way.
        current_files[path] = (
            int(added) if added.isdigit() else 10**6,
            int(removed) if removed.isdigit() else 10**6,
        )
    if current_sha:
        commits.append((current_sha, current_date, current_files))  # type: ignore[arg-type]

    candidates = {
        sha
        for sha, _, files in commits
        if any(
            added <= _MAX_STAMP_INSERTIONS and removed <= _MAX_STAMP_DELETIONS
            for added, removed in files.values()
        )
    }
    stamp_only: dict[str, set[str]] = {sha: _stamp_only_files(sha) for sha in candidates}

    newest: dict[str, date] = {}
    substantive: dict[str, date] = {}
    for sha, when, files in commits:
        for path in files:
            newest.setdefault(path, when)
            if path in stamp_only.get(sha, set()):
                continue
            substantive.setdefault(path, when)

    return {
        path: FileHistory(
            newest=newest[path],
            # A file whose every commit is stamp-only cannot exist (its creation
            # commit adds a body), but fall back rather than raise if it ever does.
            last_substantive=substantive.get(path, newest[path]),
        )
        for path in newest
    }


def tracked_docs() -> list[str]:
    """Every in-scope doc, repo-root-relative, tracked at HEAD.

    ``-z`` because three docs under ``design-principles/`` have spaces in their
    filenames and a newline-split list quietly turns each into three phantom paths.
    """
    raw = _run_git("ls-files", "-z", "--", SCOPE_PREFIX)
    return [path for path in raw.split("\0") if path and in_scope(path)]


def today_utc() -> date:
    return datetime.now(UTC).date()
