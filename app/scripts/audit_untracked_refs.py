#!/usr/bin/env python3
"""Untracked-reference guard — nothing tracked may cite the scratch tier.

SKUEL's thinking surface is ``app/plans/`` (plus ``~/.claude/plans/``): gitignored,
zero-ceremony, free to be wrong and free to delete. Its counterpart rule is that
**nothing tracked may cite it** — that prohibition IS the graduation trigger. The
moment a docstring, test, ADR, or CLAUDE.md needs to point at a document, that
document must be tracked, so it graduates to ``docs/roadmap/`` (open work) or
``docs/roadmap/done/`` (already executed). See CLAUDE.md § Documentation Architecture.

Why this is enforced rather than trusted: a citation of a gitignored path is
invisible to CI, absent from every worktree, and gone for anyone who clones. It
also rots silently — an audit in August 2026 found **35 such citations across 21
files, 23 of them pointing at documents that no longer existed anywhere**, including
absolute ``/home/mike/...`` paths committed to a public repo. Nothing detected them:
``scripts/health/dead_doc_links.py`` validates links inside ``.md`` files only, so a
dead path inside a Python docstring was never checked.

Two violation classes:

1. **A tracked file cites a scratch document** — any path of the shape
   ``plans/<name>.<ext>`` (with or without a leading ``/``, ``.claude/``, or an
   absolute home prefix). A bare ``plans/`` with no filename is NOT a violation:
   that is the ``.gitignore`` pattern and the prose in CLAUDE.md that defines this
   very rule.
2. **A tracked file LIVES under a scratch directory** — ``plans/`` is gitignored,
   but gitignore does not apply to already-tracked files, so files committed before
   the ignore stay tracked and make the tier incoherent. Four such files were found
   and untracked in August 2026.
3. **A tracked file cites a MEMORY document** — memory lives outside the repo
   (``~/.claude/projects/<slug>/memory/``), so the same three costs apply.

**Known limit, stated rather than hidden.** Class 3 matches only MARKED citations —
the slug carries ``memory``, a ``memory/`` path, a ``(memory)`` tag, or a ``.md``
suffix. A bare backticked slug cannot be matched, because it is indistinguishable
from a legitimate identifier: ``user_service``, ``user_context``,
``feedback_points`` and ``user_ownership_relationship`` are all real symbols of the
same shape. A regex broad enough to catch ``project_foo`` unmarked flags hundreds of
them, which would make the guard useless. That form is left to review.

Three forms are deliberately NOT gated, each for a stated reason:

1. **A bare backticked slug** — indistinguishable from a code identifier.
2. **A bare wiki-link** ``[[slug]]`` — first-class product syntax here
   (``core/services/ingestion/moc_links.py`` parses it for MOC ingestion), and a
   dangling target is *ruled legitimate* in a personal vault.
3. **A prefixless slug under a bare ``Memory:``** — backticks would be the
   distinguishing evidence, but ``_probe`` blanks them before matching.

Eight citation spellings surfaced during the August 2026 cleanup; five are gated.
Enumerating the limits beats implying coverage that does not exist — an
always-on gate that cries wolf is worse than one with a documented boundary.

Run: ``uv run python scripts/audit_untracked_refs.py``. Also ``./dev quality`` check
6c, a step in CI's gate-required **``content_boundary``** job, and asserted by
``tests/unit/test_untracked_refs.py``.

``content_boundary`` and not ``lint`` because that job is always-on: this guard reads
every tracked file, and ``app/.envrc`` and ``app/CLAUDE.md`` are matched by no path
filter at all, so under ``lint``'s ``py`` filter a docs-only PR would skip it. The CI
step is not optional belt-and-braces — ``tests/unit/scripts/test_quality_ci_parity.py``
fails any ``./dev quality`` check lacking a gate-required home, and its
``ALWAYS_ON_ONLY`` set pins this one to an unconditional job specifically.
Exit 0 = clean, 1 = violations.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# A citation of a document inside a scratch directory. The filename (with an
# extension) is required — that is what separates a POINTER AT a scratch doc from
# prose about the tier itself ("an untracked `plans/` file", the `plans/` ignore
# pattern, "moves to app/plans/done/"). Those must stay legal or this guard would
# flag the rule that defines it.
SCRATCH_CITATION = re.compile(
    r"""
    (?:^|[\s`'"(\[<])          # start, or a delimiter — never mid-identifier
    (?:[\w./~-]*?)             # optional leading path ( /home/mike/.claude/ , ./ , … )
    (?<!docs/)                 # NOT docs/plans/ — that would be TRACKED content, not scratch
    plans/                     # the scratch directory
    (?:[\w.-]+/)*              # optional subdirectories
    [\w.-]+\.[A-Za-z0-9]+      # a FILENAME WITH AN EXTENSION — the pointer itself
    """,
    re.VERBOSE,
)

# A citation of a MEMORY document. Memory lives outside the repo entirely
# (~/.claude/projects/<slug>/memory/), so the same reasoning applies: invisible to
# CI, absent from every worktree, gone for anyone who clones.
#
# Only MARKED forms are matched — the slug must be accompanied by `memory`, a
# `memory/` path, a `(memory)` tag, or a `.md` suffix. That is a deliberate limit,
# not an oversight: a BARE backticked slug is indistinguishable from a legitimate
# identifier. `user_service`, `user_context`, `feedback_points` and
# `user_ownership_relationship` are all real code symbols matching the same shape,
# and a regex that caught `project_foo` unmarked would flag hundreds of them. The
# unmarked form is left to review; see the module docstring.
# NOT case-insensitive, and \b-anchored: memory slugs are lowercase by convention,
# while tracked docs SHOUT (UNIFIED_USER_ARCHITECTURE.md, CROSS_REFERENCE_INDEX.md).
# An IGNORECASE version of this pattern matched 81 such filenames — the boundary and
# the case are what separate a memory slug from a document name.
MEMORY_CITATION = re.compile(
    r"""
    (?:
        # 1. Explicit citation CUE + any slug — "see memory entity-label-overload",
        #    "Memory: project_foo", "memory/feedback_bar". The cue (a `see`, a colon,
        #    or a path slash) is what separates a citation from ordinary prose about
        #    RAM: "in-memory filtering", "memory usage", "Memory exhaustion" carry no
        #    cue and must never fire. `(?<!in-)` kills the in-memory compound, whose
        #    hyphen would otherwise satisfy \b.
        # "see memory X" is an unmistakable citation verb, so X may be any slug.
        \b(?i:see\s+memory)[:\s]\s*`?\b[a-z][a-z0-9]*[_-][a-z0-9_-]{2,}
        # A bare "Memory:" is NOT unmistakable — it is also an ordinary field or
        # metric label ("Peak Memory: per_worker_buffer", "Memory: page_cache",
        # Codex #1047 r7). So the colon/slash form requires the slug to look like a
        # memory doc: prefix-named, or a .md filename.
        #
        # KNOWN LIMIT (Codex #1047 r8, accepted deliberately): a PREFIXLESS slug
        # under a bare colon — "Memory: `entity-label-overload`" — is NOT gated.
        # Backticks would be the evidence that distinguishes it from a metric label,
        # but `_probe` blanks them before matching, so a backtick alternative here
        # would be unreachable; one was written in r7 and has been deleted rather
        # than left to imply coverage it cannot deliver. Recovering that evidence
        # means threading raw and flattened text through every branch, and no
        # instance of the form exists in the tree. `see memory <anything>` still
        # catches prefixless slugs, so the gap is only bare-colon + prefixless.
      | (?<!in-)\b(?i:memory)\s*[:/]\s*
        (?:
            (?:project|feedback|user|reference|archive)_[a-z0-9_]+
          | [a-z][a-z0-9]*[_-][a-z0-9_-]{2,}\.md\b
        )
        # 2. TRAILING tag — "entity-label-overload (memory)". The cue follows the
        #    slug instead of preceding it, so alternative 1 cannot see it. PR #1046
        #    removed citations in this exact shape, but they matched only because
        #    those slugs ended in `.md`; a hyphenated one would have slipped past.
      | \b[a-z][a-z0-9]*[_-][a-z0-9_-]{2,}(?:\.md)?\s*\(memory\)
        # 3. A memory slug written as a BARE filename, cue or not. `(?<![/\w])`
        #    keeps it off path-qualified links: `docs/user_guide.md` is a tracked
        #    document, not a memory citation, and flagging it would red the
        #    always-on gate on a legitimate link — a false positive here is worse
        #    than a miss, because it breaks every PR rather than letting one slip.
        #    `find_violations` additionally clears any name that IS a tracked file.
      | (?P<unmarked>(?<![/\w])(?:project|feedback|user|reference|archive)_[a-z0-9_]+\.md\b)
        # 4. The prefixed slug directly after the word, no punctuation cue.
      | \b[Mm]emory\s+`?\b(?:project|feedback|user|reference|archive)_[a-z0-9_]+
    )
    """,
    re.VERBOSE,
)

# NOTE: there is deliberately NO bare-wiki-link rule. An earlier version gated
# ``[[slug]]`` on the reasoning that brackets are unambiguous — which is exactly
# backwards HERE (Codex, PR #1047 round 5). ``[[target]]`` is first-class product
# syntax: ``core/services/ingestion/moc_links.py`` parses wiki-links for MOC
# ingestion, and a tracked fixture in ``tests/unit/test_content_boundary.py``
# already embeds them. Resolving the target against tracked files does not rescue
# it either — a dangling MOC link is RULED legitimate in a personal vault
# (docs/roadmap/done/moc-knowledge-channel-design-notes.md § MOC). So the bare
# wiki-link joins the bare backticked slug on the "cannot gate" list; a MARKED one
# (``**Memory:** [[slug]]``) is still caught, because ``_probe`` flattens the
# brackets and the cue alternative sees it.

# Files allowed to contain the pattern: this guard and its test necessarily spell
# out what they forbid.
EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "scripts/audit_untracked_refs.py",
        "tests/unit/test_untracked_refs.py",
    }
)

# Any tracked file under one of these directories is itself a violation.
SCRATCH_DIRS: tuple[str, ...] = ("plans/",)

_SKIP_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".pdf", ".woff2"})

# Delimiters that sit BETWEEN a marker and its slug without changing the meaning:
# markdown emphasis and wiki-links (``**Memory:** [[project_foo]]``), backticks, and
# comment leaders (a citation continued onto the next ``#`` line). Blanked to spaces
# before matching so formatting cannot smuggle a citation past the gate.
_DELIMITER_NOISE = re.compile(r"[*\[\]`>#~]+")


def _probe(*lines: str) -> str:
    """Delimiter-flattened text to match against, joined across the given lines."""
    return _DELIMITER_NOISE.sub(" ", " ".join(lines))


def tracked_files() -> list[str]:
    """Repo-relative paths of every file git tracks under ``app/``."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def _memory_citation(probe: str, tracked_basenames: set[str]) -> re.Match[str] | None:
    """A memory citation in ``probe``, or None once tracked-document names are excused.

    Suppresses ONLY the unmarked-filename alternative: a bare `project_x.md` that names
    a real tracked document is a link, not a citation. A match carrying an explicit cue
    (`Memory: project_x.md`) or tag (`project_x.md (memory)`) says outright that it means
    memory, and must survive even when a tracked file happens to share the basename —
    otherwise the marker is overridden by a coincidence (Codex #1047 r6).

    ONE helper for both probes, deliberately. The wrapped-line probe used the raw regex
    while the single-line probe applied this rule, so a tracked lowercase-underscore doc
    (`docs/domains/user_entry.md`) was excused on its own line and then re-reported as
    half of a two-line citation — the suppression was there, and the second caller simply
    did not run it.
    """
    hit = MEMORY_CITATION.search(probe)
    if (
        hit
        and hit.group("unmarked")
        and hit.group("unmarked").rsplit("/", 1)[-1] in tracked_basenames
    ):
        return None
    return hit


def find_violations() -> tuple[list[tuple[str, int, str]], list[str]]:
    """Return (citations, tracked-under-scratch) violations."""
    citations: list[tuple[str, int, str]] = []
    under_scratch: list[str] = []
    tracked = tracked_files()
    # A name that IS a tracked file cannot be an external-memory citation, whatever
    # its spelling. Belt to the regex's braces: the cost of a false positive in an
    # always-on gate is every PR going red, so this clears the whole class rather
    # than trusting one lookbehind.
    tracked_basenames = {rel.rsplit("/", 1)[-1] for rel in tracked}

    for rel in tracked:
        if rel in EXEMPT_PATHS:
            continue
        if any(rel.startswith(d) or f"/{d}" in f"/{rel}" for d in SCRATCH_DIRS):
            under_scratch.append(rel)
            continue

        path = REPO_ROOT / rel
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            # errors="replace" rather than catching UnicodeDecodeError: binary
            # content decodes to noise that cannot match a citation, and a single
            # except clause keeps this runnable on any interpreter. (Ruff's py314
            # target rewrites `except (A, B):` into PEP 758's unparenthesized
            # form, which older interpreters reject — CI pins 3.14, a developer's
            # `python3` may not.)
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable — nothing to cite

        lines = text.splitlines()
        for index, line in enumerate(lines):
            probe = _probe(line)
            memory_hit = _memory_citation(probe, tracked_basenames)
            if SCRATCH_CITATION.search(probe) or memory_hit:
                citations.append((rel, index + 1, line.strip()))
                continue
            # A marker can end a line with its slug on the next ("See memory:\n
            # # project_foo."). Reported only when NEITHER line matches alone —
            # otherwise the same citation is counted twice, once wrapped and once
            # on the line that already carries it.
            if index + 1 >= len(lines):
                continue
            following = lines[index + 1]
            if _memory_citation(_probe(following), tracked_basenames):
                continue  # it will be reported on its own iteration
            if _memory_citation(_probe(line, following), tracked_basenames):
                citations.append((rel, index + 1, f"{line.strip()} ⏎ {following.strip()}"))

    return citations, under_scratch


def main() -> int:
    citations, under_scratch = find_violations()

    if not citations and not under_scratch:
        print("✅ Untracked-reference guard: no tracked file cites the scratch tier")
        return 0

    if citations:
        print(f"\n❌ {len(citations)} tracked reference(s) to a gitignored scratch document:\n")
        for rel, lineno, line in citations:
            print(f"  {rel}:{lineno}")
            print(f"      {line[:120]}")
        print(
            "\n  Fix: graduate the document (docs/roadmap/ if open, docs/roadmap/done/ if\n"
            "  already executed), or delete the pointer when it is provenance the citing\n"
            "  text already carries. Never leave a tracked file pointing at plans/."
        )

    if under_scratch:
        print(f"\n❌ {len(under_scratch)} tracked file(s) living under a scratch directory:\n")
        for rel in under_scratch:
            print(f"  {rel}")
        print(
            "\n  plans/ is gitignored, but gitignore does not apply to already-tracked\n"
            "  files. Fix: `git rm --cached <path>` (the file stays on disk), or graduate\n"
            "  it into docs/ if something tracked needs to cite it."
        )

    print("\nSee CLAUDE.md § Documentation Architecture for the graduation rule.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
