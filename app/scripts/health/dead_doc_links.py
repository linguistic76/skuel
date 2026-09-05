#!/usr/bin/env python3
"""
Dead Doc Link Validator
=======================

Validates all links and path references in Markdown documentation.

For every .md file in docs/ and .claude/skills/:
  - Extract [text](path) markdown links
  - Extract inline paths in backtick code (e.g. `/docs/patterns/foo.md`)
  - Extract bare /absolute/paths that look like file references
  - Extract path-looking tokens inside ```fenced code blocks``` (see below)
  - Check each exists relative to the repo root
  - Report: dead link, source file, line number

Why the fenced-block pass exists
--------------------------------
The first three passes are prose-shaped, and how-to guides are mostly *fence*.
That left a structural blind spot: `docs/patterns/DOMAIN_LATERAL_SERVICE_QUICK_START.md`
told readers to `cp core/services/goals/goals_lateral_service.py …` for ~6 months
after that file was deleted (`e8818dc26`), and this checker reported ZERO broken
references for it across 13 maintenance sweeps (PR #870).

Note the gap was narrower than "fences are never scanned": ``extract_bare_paths``
is already fence-blind, so a *project-rooted absolute* path inside a fence
(``cp /core/services/foo.py``) has always been reported. The uncaught class was
**relative** tokens — ``cp core/services/foo.py`` — which is precisely the shape a
copy-paste shell instruction uses. ``tests/unit/scripts/test_dead_doc_links.py``
pins all four cells of that matrix.

Fenced blocks hold shell and Python, so they carry placeholder shapes prose does
not (``core/services/your_service.py``, ``alpine.X.Y.Z.min.js``, ``/etc/prometheus/…``).
Those are rejected by ``_looks_like_local_path`` — one shared shape guard, not a
second filter — plus one fence-local rule: an absolute path inside a fence must be
project-rooted, mirroring what ``extract_bare_paths`` already requires of prose.

Fence *boundaries* come from ``scripts/health/markdown_fences``, the CommonMark-backed
walker shared with ``stale_names.py`` — not a hand-written scanner. A scanner was tried
and accrued five container-handling bugs in one review; see that module for the list,
for why a tree-wide differential showing "zero disagreements" was not the evidence of
correctness it looked like, and for why one walker now serves both scanners.

Also confirms that all files referenced in docs/INDEX.md exist.

What is deliberately NOT reported
---------------------------------
Four exclusions, every one **visible**: the run prints a count per class on every
run, zero included. A check that reports 871 findings is one nobody reads, but a
check that goes quiet without saying so is worse — so nothing here suppresses
silently.

  - ``FREEFORM_FILES`` / ``TEMPLATE_FILES`` / ``TEMPLATE_DIRS`` — files whose links
    are unvalidatable by construction (working notes citing an Obsidian vault
    outside this repo; templates whose paths are fictional by design). Scoped to
    measured FILES for ``design-principles/``, never the directory: it also holds
    maintained specs whose dead links are genuine rot.
  - ``HISTORY_DIRS`` — dated records of a past state, where a dead link is the
    history being faithful rather than rot. Directory membership IS the
    classification, so this one is a *directory* carve-out (Mike, 2026-09-01).
  - Registered application routes — docs cite app URLs (``/journals``,
    ``/manifest.json``) with the same leading-slash spelling as a repo path. The
    class is defined by MATCHING a live registration read from ``adapters/inbound/``,
    never by shape and never by a hand-kept URL list.
  - ``<!-- historical -->`` markers in ``docs/decisions/`` — a per-citation opt-out
    that skips a dead target and nothing else. A marker that skipped nothing is
    itself reported (the SKUEL026 inversion), so it stays falsifiable; a blanket
    carve-out for ADRs would not, which is why it was refused.

Usage:
    uv run python scripts/health/dead_doc_links.py
    uv run python scripts/health/dead_doc_links.py --verbose
"""

import ast
import re
import sys
import urllib.parse
from functools import cache
from pathlib import Path
from typing import Literal, NamedTuple

# scripts/health/ is not a package — see the note in stale_names.py.
from markdown_fences import (  # type: ignore[import-not-found]
    iter_code_fence_blocks,
    iter_code_fence_lines,
)

from core.utils.terminal_colors import Colors

ROOT = Path(__file__).parent.parent.parent  # /home/mike/skuel/app

SCAN_DIRS = [
    ROOT / "docs",
    ROOT / ".claude" / "skills",
]

# Link prefixes that should never be validated as local paths
EXTERNAL_PREFIXES = ("http://", "https://", "ftp://", "mailto:", "#")

# Recognised local file extensions for inline path detection
LOCAL_EXTENSIONS = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".cypher",
    ".sh",
    ".js",
    ".ts",
    ".txt",
    ".html",
    ".css",
}

# Recognised project-root prefixes for bare path detection in prose
PROJECT_PREFIXES = (
    "/docs/",
    "/core/",
    "/adapters/",
    "/ui/",
    "/scripts/",
    "/static/",
    "/.claude/",
    "/tests/",
    "/monitoring/",
)

# Documentation-convention placeholders. Docs name a file the reader is meant to
# substitute, and the convention is lexical rather than syntactic — `{domain}` and
# `<name>` are already rejected by the `{`/`<`/`*` guard, but `your_service.py` and
# `alpine.X.Y.Z.min.js` are not. Each entry below is measured against the live tree
# (PR #871), and every one is pinned by a case in test_dead_doc_links.py.
#
# This vocabulary only ever SUBTRACTS reports from an advisory report, so a gap here
# costs one noisy line — never a false failure. That is the fail-safe direction; do
# not invert it by using this list to decide that something *is* broken.
#
# Every entry is boundary-aware, because loose matching here creates exactly the
# blind spot this pass exists to close. Measured against the live tree: a substring
# `new_domain` swallows the real `tests/integration/test_new_domain_relationships.py`,
# and a bare `foo` prefix swallows any `footer.html` / `footnotes.py`.

# The subject the reader substitutes: `your_service.py`, `my_service.py`. A test *for*
# a placeholder subject is itself one, so `test_` is stripped before this check.
PLACEHOLDER_SUBJECT_PREFIXES = (
    "your_",
    "your-",
    "my_",
    "our_",
    "example_",
)
# The topic a scaffolding doc walks you through creating: `new_domain/`,
# `new_domain_service.py`, `NEW_PATTERN.md`, `test_new_feature.py`. See
# `_matches_topic_marker` for why this cannot be a plain prefix test.
PLACEHOLDER_TOPIC_MARKERS = (
    "new_domain",
    "new_feature",
    "new_pattern",
    "old_pattern",
)
# Metasyntactic stand-in. The trailing guard keeps `foo`/`foo.py`/`foo_bar` in and
# `footer`/`footnotes` out. Only `foo` is listed — bar/baz/qux never appeared in the
# measured surface, and an unmeasured entry is pure shadow risk.
PLACEHOLDER_METASYNTACTIC_RE = re.compile(r"^foo(?![a-z])")
PLACEHOLDER_SUBSTRINGS = (
    "path/to/",
    "...",  # elided path segment, e.g. adapters/.../fragments.py
)
# Uppercase metavariables standing in for a version or a date. `\b` is wrong here:
# there is no word boundary in `nodes_YYYY.cypher` between `_` and `Y`, so a
# `\bYYYY\b` pattern misses the one shape this rule exists for.
PLACEHOLDER_METAVAR_RE = re.compile(r"(?<![A-Za-z])(?:X\.Y\.Z|YYYY|MM-DD)(?![A-Za-z])")

# Uppercase metavariables a *naming-convention* doc uses for its own examples:
# `FEATURE_NAME.md`, `ADR-XXX.md`, `FEATURE_X.md`, `skill-name/SKILL.md`. Distinct from
# the version/date metavariables above — those stand in for a value, these stand in for
# the subject the reader is naming — and the vocabulary had no entry for them, so eight
# docs teaching a naming convention reported their own examples as rot.
#
# ⚠️ The obvious WIDER rule is wrong, and was measured: SHOUTING_SNAKE_CASE is how this
# corpus names ~200 real docs, so "reject any uppercase stem" shadows the whole tier —
# `ANY_USAGE_POLICY.md`, `AUTH_PATTERNS.md`, on down. These four discriminators are
# narrow because the wide one failed, the same lesson as the comma
# `_is_checkable_link_target` deliberately does not reject. Each was scored against the
# full tracked tree and matches no real file; `test_placeholder_vocabulary_shadows_no_
# file_in_the_tree` re-derives that from the tree on every run rather than trusting this
# comment.
#
# ⚠️ `RELATED_ARCHITECTURE.md` is deliberately NOT covered. It fits no discriminator
# here, and a one-off `RELATED_` entry is precisely the shadow risk this vocabulary
# refuses (the reason only `foo` is listed). One instance earns no rule; fix the citing
# doc or leave it reported.
PLACEHOLDER_METAVAR_STEM_SUFFIXES = ("_NAME", "_X", "-name")
# An all-`X` token: `ADR-XXX`, `ADR-0XX-example`. The boundaries reject `X` inside a
# word so a real `.../XXth_...` style name could never be swallowed; a digit on either
# side is fine, which is what `0XX` needs.
PLACEHOLDER_ALL_X_RE = re.compile(r"(?<![A-Za-z])XX+(?![A-Za-z])")

# Template markers the tokenizer deliberately keeps attached to a token so the shape
# guard can reject the whole thing. Excluding them would split
# `core/services/{domain}/{domain}_service.py` into clean-looking fragments and hand the
# guard a false positive it cannot see.
#
# ONE constant feeds both the tokenizer and `_looks_like_local_path`, deliberately: they
# had drifted, the tokenizer retaining `$ ~ >` while the guard rejected only `{ < *`, so
# `core/services/$DOMAIN/service.py` was reported as a dead repo file — and the comment
# here asserted they agreed (Codex, PR #872). A contract stated in prose but not enforced
# by the code is worse than no contract; keep them structurally tied.
TEMPLATE_MARKERS = "{}<>*$~"

# A maximal run of path-plausible characters inside a fenced code block.
FENCE_TOKEN_RE = re.compile(r"[A-Za-z0-9_./" + re.escape(TEMPLATE_MARKERS) + r"-]+")

# Quoted shell arguments, so a path containing spaces survives tokenization — e.g. the
# live `docs/design-principles/direction w structuring.md`.
FENCE_QUOTED_RE = re.compile(r"\"([^\"\n]+)\"|'([^'\n]+)'")

# Two-path prose joins. A backtick span like
# `core/services/submissions/ + core/services/feedback/x.py` names TWO paths, so it
# resolves to neither and reports as one dead file that was never cited (9 findings,
# measured 2026-09-01). Rejecting the join is not the same as rejecting spaces, and
# the difference is load-bearing — see `_looks_like_local_path`.
PATH_JOIN_MARKER = " + "

# ── Scope carve-outs ─────────────────────────────────────────────────────────
# Excluded by SCOPE, not suppressed: the run prints a file count per class, so each
# carve-out stays visible (the shape `duplicate_headings.py` uses). Entries are
# repo-relative POSIX strings, resolved against ROOT at call time so tests can
# substitute a throwaway root.
#
# ⚠️ FILE-scoped for `design-principles/`, never the directory. That directory also
# holds maintained specs whose dead links are genuine rot — `HUB_PAGES.md` cites the
# deleted `ui/teaching/hub.py` — and a directory carve-out would hide it (Codex, PR
# #1214). Measured 2026-09-01: 20 + 16 of the directory's 37 findings are the two
# freeform files below; the 37th is that HUB_PAGES.md rot, which stays reported.
#
# (`duplicate_headings.py` excluding the whole directory remains right for ITS check:
# freeform notes legitimately repeat headings, while dead links in a maintained spec
# are a different property. Not an inconsistency to "fix" the other way.)
FREEFORM_FILES = frozenset(
    {
        # Working notes; the links point at files in the author's Obsidian vault,
        # which is not in this repo — unvalidatable by construction (20 findings).
        "docs/design-principles/direction w structuring.md",
        # Same, exported from the vault with `%20`-encoded destinations (16).
        "docs/design-principles/dp - emergence, patience, non-attachment.md",
    }
)

# Whole directories where every file is a template by construction: the paths in them
# are the shapes a reader substitutes, not citations (14 findings).
TEMPLATE_DIRS = (".claude/skills/_templates",)

# Single files of the same species, where the directory around them is NOT a template
# tree. Kept file-scoped for the same reason `design-principles/` is: `docs/decisions/`
# is the authority tier, and carving out the directory to reach one template would hide
# the rot this instrument exists to surface.
TEMPLATE_FILES = frozenset(
    {
        # The ADR template's `**Example:**` block illustrates what a Decision section
        # looks like; its `File: /core/services/user/graph_sourced_context_builder.py`
        # names a module that was never tracked in this repo (`git log --all` is empty),
        # which is what "fictional by design" means here. 1 finding, measured 2026-09-01.
        "docs/decisions/ADR-TEMPLATE.md",
    }
)

# ── History directories: dated records of a past state ───────────────────────
# A dead link inside a dated record is the history being FAITHFUL — the file it names
# really was there when the record was written. Directory membership IS the
# classification, so unlike `design-principles/` there is no mixed-content risk to scope
# around: these directories hold nothing but records (Mike's ruling, 2026-09-01, option
# (a) on the C class — 226 findings measured that day).
#
# Silence is sanctioned here in a way it is NOT for `docs/decisions/`: these directories
# carry no tripwire. An ADR carve-out would have un-observed its own reopening condition
# (Codex, PR #1215), which is why ADRs got the per-citation marker below instead.
#
# ⚠️ "Silent" names the absence of a tripwire, not the absence of a count — the file
# count prints on every run, and it prints SEPARATELY from the unvalidatable-by-
# construction count. Measured 2026-09-01: 73 files here against 6 there, so one merged
# number would be a number whose growth nobody can read (this set grows with every
# completed roadmap doc; that one is meant to stay fixed).
#
# ⚠️ `docs/roadmap/done/` and not `docs/roadmap/` — the live half of that folder is
# "what might still happen" and its dead links are rot. The trailing separator added at
# match time is what keeps `docs/migrations` from also swallowing a `docs/migrations-v2/`.
HISTORY_DIRS = (
    # Dated migration logs: each records a cutover as it stood (198 findings).
    "docs/migrations",
    # Completed roadmap docs — the citable archive of executed work (12).
    "docs/roadmap/done",
    # One-off investigations, written against the tree as it was on the day (12).
    "docs/investigations",
    # Point-in-time review write-ups (4).
    "docs/Reviews",
)

# ── Registered application routes ────────────────────────────────────────────
# Docs cite application URLs (`/journals`, `/submissions/sync`, the root-served PWA
# assets `/manifest.json` `/service-worker.js` `/offline.html`) with the same
# leading-slash spelling a repo path uses, and this checker reads them as files.
#
# The class is defined by MATCHING a live route registration — never by shape, and
# never by a hand-maintained URL list, which is a catalog copy that rots (Codex, PR
# #1214). Extraction is AST-based over `adapters/inbound/`, the one tree that
# registers routes: measured 2026-09-01, 514 `@rt("…")` calls there and none anywhere
# else in production code. AST rather than grep because the other `@rt(` occurrences
# in the repo are docstring examples and test fixtures, which a walk never sees.
#
# `ROUTE_DECORATORS` mirrors `scripts/audit_route_security.py`'s definition of a route
# decorator rather than inventing a second one — the same reason `TEMPLATE_MARKERS` is
# one constant feeding two consumers.
#
# ⚠️ Only *string-literal* paths are extracted. The activity/domain UI factories
# register `@rt(f"/{domain}")`, which no static pass can resolve, so `/tasks` stays
# reported even though it is live. That is the deliberate direction: an unmatched
# route costs one advisory line, a wrongly-matched one hides real rot. Fail toward
# reporting.
ROUTE_DECORATORS = frozenset({"rt", "route"})


# ── The historical-citation marker ───────────────────────────────────────────
# ADRs mix two kinds of citation in one Accepted file: faithful narrative ("we deleted
# X", "the former Y") and standing contract ("the chokepoint lives at X"). Measured
# 2026-09-01 across all 154 `docs/decisions/` findings: 81 standing / 70 narrative / 3
# ambiguous. A whole-tier carve-out would have hidden the 81 — so the narrative citations
# opt out one at a time, and the marker itself stays falsifiable:
#
#   - it skips a marked citation ONLY when the target is dead, and
#   - a marker that skipped nothing is REPORTED (`stale_markers`), the same inversion
#     SKUEL026 applies to lint suppressions that suppress nothing.
#
# **Line-scoped**, which in this corpus is per-citation: 153 of the 154 findings are
# alone on their line, and the single two-finding line (ADR-070:255, naming two deleted
# scripts) is homogeneous. A line mixing a narrative citation with a standing-contract
# one must be SPLIT before marking — one marker would silence both.
#
# ⚠️ The grammar is the WHOLE comment, matched exactly. The comment delimiters are the
# anchors, so `<!-- historical: replaced by X -->` and `<!-- historically ... -->` are
# not markers and their citations stay red. That direction is deliberate: B2's one
# review finding was a pattern anchored at only one end reading `ADR-050-typo` as
# `ADR-050`, and a marker predicate that accepts a superset of its grammar would quietly
# swallow ADR prose that was never a marker. Fail toward reporting.
#
# The marker is inert as a citation: it carries no path, no extension and no project
# prefix, so no pass extracts it (and `<`/`>` are TEMPLATE_MARKERS besides).
# ── The planned-file marker ──────────────────────────────────────────────────
# A LIVE roadmap doc cites the files it plans to CREATE, and the scanner sees exactly
# what it sees for a deleted one: `not exists()`. Measured 2026-09-02 on `21491cd4e`:
# 8 of the 14 live-`docs/roadmap/` findings are this shape, four of them annotated
# "(new)" in the doc's own code-touch inventory and one "(when implemented)".
#
# It is the historical marker's mirror image — that one says "this WAS there", this one
# says "this is not there YET" — so it is the same mechanism with a different scope,
# not a second one. Two near-identical marker implementations would drift, which is the
# failure `TEMPLATE_MARKERS` already exists to prevent.
#
# ⭐ The property that earned it over "just leave them reported" (Mike, 2026-09-02):
# **it self-retires.** When the planned file is finally built the marker suppresses
# nothing, so the SKUEL026 inversion REPORTS it — turning a permanent dead link into a
# build-completion signal. A silent carve-out could never do that.
#
# ⚠️ Scoped to `docs/roadmap` and NOT `docs/decisions`. An ADR proposing a file is
# writing a contract, not a schedule; if that ever needs an opt-out it gets its own
# measured entry, never a widened scope here.

# ── Marker mechanism (both markers) ──────────────────────────────────────────
# ONE implementation, a registry of two specs — deliberately. The two markers share
# every rule below and differ only in name and scope, so a parallel implementation
# would be two copies of the same contract free to drift apart.
#
# Every marker, whatever its name:
#
#   - skips a marked citation ONLY when the target is dead, and
#   - is REPORTED when it skipped nothing (`stale_markers`), the same inversion
#     SKUEL026 applies to lint suppressions that suppress nothing.
#
# **Line-scoped**, which in this corpus is per-citation. A line mixing a markable
# citation with an unmarkable one must be SPLIT before marking — one marker would
# silence both.
#
# ⚠️ The grammar is the WHOLE comment, matched exactly. The comment delimiters are the
# anchors, so `<!-- historical: replaced by X -->` and `<!-- historically ... -->` are
# not markers and their citations stay red. That direction is deliberate: B2's one
# review finding was a pattern anchored at only one end reading `ADR-050-typo` as
# `ADR-050`, and a marker predicate that accepts a superset of its grammar would quietly
# swallow prose that was never a marker. Fail toward reporting.
#
# A marker is inert as a citation: it carries no path, no extension and no project
# prefix, so no pass extracts it (and `<`/`>` are TEMPLATE_MARKERS besides).


class MarkerSpec(NamedTuple):
    """One per-citation opt-out: its name, where it is honored, and what it asserts.

    ``scope_dirs`` is what keeps a marker from silencing the sweep queue wholesale —
    one rule evaluated corpus-wide, so a marker copied outside its tier suppresses
    nothing and is reported as such.
    """

    name: str
    scope_dirs: tuple[str, ...]
    # Completes "…because the citation is ", for the reason a stale marker carries.
    asserts: str

    @property
    def spelling(self) -> str:
        return f"<!-- {self.name} -->"

    @property
    def pattern(self) -> re.Pattern[str]:
        return re.compile(rf"<!--\s*{self.name}\s*-->")


MARKERS = (
    # ADRs mix two kinds of citation in one Accepted file: faithful narrative ("we
    # deleted X", "the former Y") and standing contract ("the chokepoint lives at X").
    # Measured 2026-09-01 across all 154 `docs/decisions/` findings: 81 standing / 70
    # narrative / 3 ambiguous. A whole-tier carve-out would have hidden the 81.
    MarkerSpec("historical", ("docs/decisions",), "a faithful record of a past state"),
    # See the planned-file block above.
    MarkerSpec("planned", ("docs/roadmap",), "a file this plan intends to create"),
)

MARKERS_BY_NAME = {m.name: m for m in MARKERS}

# An inline code span, removed before marker detection — see `_marker_lines`. The same
# shape `extract_backtick_paths` reads, since it is the same convention: what is inside
# backticks is a quoted token, not the surrounding prose's own voice.
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# One link grammar for every consumer. `scripts/docs_relative_links.py` rewrites exactly
# the matches this pass checks, so the two can never disagree about what a link is.
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Any marker's opening, used to skip the fence walk on a file carrying none.
ANY_MARKER_RE = re.compile(r"<!--\s*(?:" + "|".join(m.name for m in MARKERS) + r")\s*-->")

CarveOutClass = Literal["unvalidatable", "history"]


def _carve_out_class(path: Path) -> CarveOutClass | None:
    """Which scope carve-out excludes this doc from the scan, if any?

    The two classes are counted and printed separately because their reasons differ:
    one set of links can never be checked, the other should not be.
    """
    if not path.is_relative_to(ROOT):
        return None
    rel = path.relative_to(ROOT).as_posix()
    if rel in FREEFORM_FILES or rel in TEMPLATE_FILES:
        return "unvalidatable"
    if rel.startswith(tuple(f"{d}/" for d in TEMPLATE_DIRS)):
        return "unvalidatable"
    if rel.startswith(tuple(f"{d}/" for d in HISTORY_DIRS)):
        return "history"
    return None


class ScopeSkips(NamedTuple):
    """Files a scope carve-out kept out of the scan, counted per class.

    Two numbers rather than one: a merged count moves for two unrelated reasons, and
    the 73-file history set would swamp the 6-file unvalidatable set it was merged with.
    """

    unvalidatable: int
    history: int


def get_md_files() -> tuple[list[Path], ScopeSkips]:
    """Markdown to scan, plus the counts skipped by each scope carve-out."""
    scanned: list[Path] = []
    skipped = {"unvalidatable": 0, "history": 0}
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            carve_out = _carve_out_class(path)
            if carve_out is None:
                scanned.append(path)
            else:
                skipped[carve_out] += 1
    return scanned, ScopeSkips(skipped["unvalidatable"], skipped["history"])


def _honors_marker(path: Path, marker: MarkerSpec) -> bool:
    """Is this doc inside the tier where `marker` is honored?

    ⚠️ Per marker, not per file: a doc is in scope for at most one of them today, and a
    marker written outside its own tier suppresses nothing and is reported. That is what
    stops a `planned` marker copied into an ADR — or a `historical` one copied into the
    live roadmap — from quietly silencing the sweep queue.
    """
    if not path.is_relative_to(ROOT):
        return False
    rel = path.relative_to(ROOT).as_posix()
    return rel.startswith(tuple(f"{d}/" for d in marker.scope_dirs))


def _marker_lines(content: str, marker: MarkerSpec) -> frozenset[int]:
    """Line numbers carrying a well-formed marker of this kind.

    A marker inside a code span or a fenced block is prose ABOUT the marker, not an
    annotation — documenting this checker requires writing the shape it hunts, and the
    four occurrences in `HEALTH_CHECKS.md` and `deferred-work.md` each reported as a
    marker-that-suppresses-nothing until this rule existed. `stale_names.py` meets the
    same problem and answers it with a `SKIP_FILES` list; a code-span rule needs no
    registry, generalises to the next doc that names the marker, and fails toward
    reporting — a marker accidentally backticked inside an ADR is simply not honored,
    so its citation stays red.

    Scoped to the two contexts that fence off code by construction. A marker in an
    indented (4-space) code block would still count; measured zero today, and the cost
    would be one advisory line telling its author to backtick it.

    ⚠️ The exclusion takes each fence's whole ``span``, delimiter lines included — not
    the content-line projection ``iter_code_fence_lines`` gives. A marker in an INFO
    STRING (```` ```markdown <!-- historical --> ````) sits on the opener, which is not
    a content line, so the projection left it counting as a real annotation (Codex, PR
    #1219). That was not merely noise: the prose passes DO read the opener line, so a
    citation in the same info string would have been suppressed by it. ``FenceBlock``
    carries ``span`` for precisely this reason — "a delimiter line is neither content
    nor prose".
    """
    pattern = marker.pattern
    if not pattern.search(content):
        # Nothing to walk fences for. Sound because the whole-content match is a strict
        # superset of the per-line ones, and it keeps the fence parse (which
        # `extract_fenced_paths` already pays once) off every unmarked file.
        return frozenset()
    fenced = {
        lineno
        for block in iter_code_fence_blocks(content)
        for lineno in range(block.span[0], block.span[1] + 1)
    }
    return frozenset(
        lineno
        for lineno, line in enumerate(content.splitlines(), 1)
        if lineno not in fenced and pattern.search(INLINE_CODE_RE.sub("", line))
    )


def _decorator_callee(func: ast.expr) -> str:
    """Name of the thing being called — `rt` in `@rt(...)`, `route` in `@app.route(...)`."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


@cache
def _route_paths_under(inbound_dir: Path) -> frozenset[str]:
    """Literal route paths registered under a routes tree. Cached per directory."""
    paths: set[str] = set()
    if not inbound_dir.exists():
        return frozenset()
    for py_file in sorted(inbound_dir.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _decorator_callee(node.func) not in ROUTE_DECORATORS:
                continue
            first = node.args[0] if node.args else None
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.startswith("/")
            ):
                paths.add(first.value)
    return frozenset(paths)


def registered_route_paths() -> frozenset[str]:
    """The live route catalog, read from `adapters/inbound/` source."""
    return _route_paths_under(ROOT / "adapters" / "inbound")


def _is_registered_route(raw: str) -> bool:
    """Does this link target name an application URL rather than a repo file?"""
    if not raw.startswith("/") or raw.startswith(PROJECT_PREFIXES):
        # A repo-rooted citation is a file path by convention, never a route.
        # Measured 2026-09-01: no registered route lives under a PROJECT_PREFIX, so
        # this costs nothing today and blocks a whole class of accidental suppression
        # if one ever does.
        return False
    return raw.split("#")[0].strip() in registered_route_paths()


def _is_external(link: str) -> bool:
    # `//cdn.example.com/lib.js` is a protocol-relative URL, not a repo path — it
    # otherwise passes the leading-slash test and resolves under ROOT.
    if link.startswith("//"):
        return True
    return any(link.startswith(p) for p in EXTERNAL_PREFIXES)


def resolve_path(raw: str, source_file: Path) -> Path | None:
    """
    Resolve a raw link/path string to an absolute Path.

    Returns None if the link should not be checked (external URL, anchor-only).
    """
    if _is_external(raw):
        return None
    if raw.startswith("#"):
        return None

    # Strip inline anchor
    raw = raw.split("#")[0].strip()
    if not raw:
        return None

    # A link destination is a URL, so `%20` is a space. Without decoding, the REAL
    # `docs/design-principles/dp - emergence, patience, non-attachment.md` reported dead
    # purely because its citation was correctly encoded. Decoded AFTER the anchor strip,
    # so an encoded `%23` cannot manufacture an anchor.
    #
    # Corner: a literal `%20` inside a real filename would now false-negative. Measured
    # 2026-09-01 — zero tracked filenames contain `%` at all (`git ls-files | grep %`).
    raw = urllib.parse.unquote(raw)

    # Mirror _looks_like_local_path's `./` normalisation so the guard and the resolver
    # agree on what a token means.
    raw = raw.removeprefix("./")

    if raw.startswith("/"):
        # Repo-root-absolute — the citation form for everything that is not a
        # docs→docs link (those are written relative to the citing file; the rule
        # and its sweep live in `scripts/docs_relative_links.py`). Machine-absolute
        # citations (`/home/<user>/skuel/app/…`) are deliberately NOT rescued via an
        # `/app/` landmark: that would legitimize a second, non-portable link
        # style (Codex, PR #796). They resolve under ROOT and report broken
        # identically in every checkout — fix the doc, not the resolver.
        return ROOT / raw.lstrip("/")
    else:
        # Relative path from source file's directory
        candidate = (source_file.parent / raw).resolve()
        if candidate.exists():
            return candidate
        # Docs routinely cite paths root-relative without a leading slash
        # (`docs/patterns/foo.md`, `core/services/bar.py`) — try the repo
        # root before declaring the reference broken.
        return ROOT / raw


def _is_checkable_link_target(target: str) -> bool:
    """Is this `[text](target)` destination something this checker can resolve?

    The link pass was the only one of the four with no shape guard at all, and Python
    generic subscripts collide with link syntax:
    ``UniversalNeo4jBackend[T](driver, "Task", Task)`` parses as link text ``T`` and
    destination ``driver, "Task", Task``. ADR-019/023 and the pytest skill are dense
    with them — 24 findings measured 2026-09-01, every one a subscript, none a link.

    **A raw space is the discriminator**, and it is CommonMark-grounded rather than
    heuristic: an unescaped space cannot appear in a link destination at all (the
    spelling for a path with spaces is ``<…>``-wrapped, of which the corpus has none).
    The one thing this gives up is the ``(dest "title")`` form, whose title the regex
    above swallows into the destination — measured zero in the corpus, and skipping is
    the fail-safe direction.

    **A comma is NOT a rejection signal**, deliberately: the corpus's six comma-bearing
    destinations are all properly ``%20``-encoded vault links, one of which
    (``dp%20-%20emergence,…md``) names a REAL file that ``resolve_path`` now resolves.
    That is why the guard runs BEFORE URL-decoding but tests only for a RAW space.

    ``TEMPLATE_MARKERS`` rejection measures zero today. It pins a *latent* gap rather
    than a live one: ``core/services/{domain}/x.py`` in backticks is rejected by
    ``_looks_like_local_path`` while the same token as a link destination was reported,
    and closing a measured-zero inconsistency with a test is the same move
    ``test_blockquoted_fence_is_walked`` made.

    The placeholder half of ``_is_documentation_stand_in`` is NOT latent here — it
    measures 4. Python generics whose argument list is elided (``[T](…)``) parse as link
    text plus a destination that is only an elision marker, and the raw-space
    discriminator above cannot see them because an elision marker has no space. They
    need no rule of their own: the elided-segment substring already in
    ``PLACEHOLDER_SUBSTRINGS`` covers all four, including the ``http``-prefixed one that
    an exact-match rule would have missed (Codex, PR #1222).
    """
    if " " in target:
        return False
    return not _is_documentation_stand_in(target)


def extract_markdown_links(content: str) -> list[tuple[int, str, str]]:
    """
    Extract [text](path) patterns whose destination is a checkable path.
    Returns list of (line_no, display_text, raw_path).
    """
    results = []
    for i, line in enumerate(content.splitlines(), 1):
        for match in MARKDOWN_LINK_RE.finditer(line):
            text = match.group(1)
            path = match.group(2).strip()
            if _is_checkable_link_target(path):
                results.append((i, text, path))
    return results


def extract_backtick_paths(content: str) -> list[tuple[int, str]]:
    """
    Extract inline `backtick` spans that look like file paths.
    Returns list of (line_no, path_string).
    """
    results = []
    for i, line in enumerate(content.splitlines(), 1):
        for match in re.finditer(r"`([^`\n]+)`", line):
            text = match.group(1)
            if _looks_like_local_path(text):
                results.append((i, text))
    return results


def extract_bare_paths(content: str) -> list[tuple[int, str]]:
    """
    Extract bare /absolute/paths in prose that look like project-internal file references.
    Only matches paths with a recognised project prefix and file extension.
    Returns list of (line_no, path_string).
    """
    results = []
    # Match /project-prefix/... paths ending with a file extension. The
    # lookbehind also rejects word chars and slashes: without that, the
    # `/monitoring/foo.py` TAIL of a longer citation like
    # `core/infrastructure/monitoring/foo.py` matches as its own bare path and
    # resolves to a nonexistent ROOT/monitoring/... — a false positive on every
    # such citation (the full span is already handled by the backtick pass).
    pattern = re.compile(
        r"(?<![\w/`\[(])"  # not inside link/backtick, not mid-path
        r"((?:" + "|".join(re.escape(p) for p in PROJECT_PREFIXES) + r")[^\s\)\]`\"'<>,]+)"
    )
    for i, line in enumerate(content.splitlines(), 1):
        # Skip lines that are markdown link syntax (already covered)
        for match in pattern.finditer(line):
            raw = match.group(1).rstrip(".,;:")
            # This pass never consulted the shared shape guard, so glob and template
            # patterns sailed through it — ADR-071's Tailwind content globs
            # (`/ui/**/*.py`) and the skuel-ui skill's `/ui/{domain}/layout.py`, 7
            # findings measured 2026-09-01. The ONE predicate, not a fresh literal: the
            # tokenizer/guard drift in PR #872 is the cautionary tale, and reaching for
            # only HALF of it here was the same drift again — `/docs/patterns/NEW_FEATURE.md`
            # was already in the placeholder vocabulary and this pass reported it anyway.
            if _is_documentation_stand_in(raw):
                continue
            if any(raw.endswith(ext) for ext in LOCAL_EXTENSIONS):
                results.append((i, raw))
    return results


def extract_fenced_paths(content: str) -> list[tuple[int, str]]:
    """
    Extract path-looking tokens from inside fenced code blocks.

    Every fence language is scanned. That is measured, not assumed: across the live
    tree the dead tokens land in bash (88), python (35), yaml (8), untagged (5),
    cypher (3), javascript (3), markdown (2) and html (1), and no language is a
    pure-noise source once the shape guard runs — so restricting to ```bash/```python
    would drop genuine findings and buy nothing (PR #871).

    Returns list of (line_no, path_string).
    """
    results = []
    for lineno, _lang, line in iter_code_fence_lines(content):
        # Quoted arguments first: FENCE_TOKEN_RE has no space in its class, so a path
        # with spaces would shatter into fragments that each fail the guard, leaving the
        # exact dead-path blind spot this pass exists to close for filenames like the
        # live `docs/design-principles/direction w structuring.md` (Codex, PR #872).
        quoted_spans = [g for match in FENCE_QUOTED_RE.finditer(line) for g in match.groups() if g]
        for token in [*quoted_spans, *FENCE_TOKEN_RE.findall(line)]:
            token = token.rstrip(".,;:")
            if not _looks_like_local_path(token):
                continue
            # Fence-local rule: absolute paths here are usually filesystem- or
            # URL-absolute (`/etc/prometheus/prometheus.yml`, a service-worker
            # cache list's `/offline.html`), not repo-relative. Require the same
            # project rooting extract_bare_paths already requires of prose —
            # measured on the live tree, this rejects 20 tokens and every one is
            # a false positive.
            if token.startswith("/") and not token.startswith(PROJECT_PREFIXES):
                continue
            results.append((lineno, token))
    return results


def _matches_topic_marker(segment: str) -> bool:
    """
    Is this path segment named after a scaffolding doc's stand-in topic?

    A plain `startswith(marker)` is wrong in one direction and a plain `== marker` is
    wrong in the other, and both were measured against the live tree:

      new_domain/                            placeholder — the marker IS the segment
      new_domain_service.py                  placeholder — scaffolded from the marker
      NEW_DOMAIN_INTELLIGENCE.md             placeholder — likewise
      test_new_feature.py                    placeholder — a test for the stand-in
      test_new_domain_relationships.py       REAL FILE — a test *about* new domains

    So: the marker must be the whole stem, or extend it under a non-`test_` segment,
    or be the whole stem behind a `test_` prefix. The last two rules are what keep the
    real file visible — a shadowed real file is a permanent blind spot, which is the
    failure this whole pass exists to fix.
    """
    stem = segment.rsplit(".", 1)[0] if "." in segment else segment
    for marker in PLACEHOLDER_TOPIC_MARKERS:
        if stem == marker or stem == f"test_{marker}":
            return True
        if stem.startswith(f"{marker}_") and not stem.startswith("test_"):
            return True
    return False


def _is_metavariable_segment(segment: str) -> bool:
    """Is this segment a documentation metavariable standing in for a name?

    Case-SENSITIVE on the two uppercase suffixes, deliberately: `_NAME` is a
    metavariable while a real `..._name.py` is an ordinary module, and folding case
    here would widen the rule past what was measured. See
    ``PLACEHOLDER_METAVAR_STEM_SUFFIXES`` for why narrow is the only safe direction.

    Applied to the STEM, so an extension cannot defeat the suffix test — `FEATURE_NAME`
    and `FEATURE_NAME.md` are the same stand-in, and `skill-name` is the same whether it
    names a directory or a file.
    """
    stem = segment.rsplit(".", 1)[0] if "." in segment else segment
    if stem.endswith(PLACEHOLDER_METAVAR_STEM_SUFFIXES):
        return True
    return bool(PLACEHOLDER_ALL_X_RE.search(stem))


def _is_placeholder(text: str) -> bool:
    """Does this path use a documentation placeholder the reader is meant to replace?"""
    if any(marker in text.lower() for marker in PLACEHOLDER_SUBSTRINGS):
        return True
    if PLACEHOLDER_METAVAR_RE.search(text):
        return True
    for segment in text.split("/"):
        # Case-sensitive rules read the segment as written; the vocabulary below is
        # lowercase, so it reads a lowered copy. One split serves both.
        if _is_metavariable_segment(segment):
            return True
        lowered = segment.lower()
        if _matches_topic_marker(lowered):
            return True
        # A test *for* a placeholder subject is itself a placeholder, and the marker
        # sits behind the `test_` prefix: `test_foo.py`, `test_your_service.py`.
        subject = lowered.removeprefix("test_")
        if subject.startswith(PLACEHOLDER_SUBJECT_PREFIXES):
            return True
        if PLACEHOLDER_METASYNTACTIC_RE.match(subject):
            return True
    return False


def _has_template_marker(text: str) -> bool:
    """Does this token carry a template / glob / shell-variable marker?

    One predicate for every pass, so a marker added to ``TEMPLATE_MARKERS`` reaches all
    of them at once — the drift this constant already exists to prevent.
    """
    return any(marker in text for marker in TEMPLATE_MARKERS)


def _is_documentation_stand_in(text: str) -> bool:
    """Is this token a shape the reader substitutes rather than a citation to check?

    ONE predicate over BOTH vocabularies, and every pass calls it — because the two had
    drifted apart exactly the way ``TEMPLATE_MARKERS`` once drifted from its tokenizer.
    The backtick and fence passes reached ``_is_placeholder`` through
    ``_looks_like_local_path``; ``extract_bare_paths`` and ``_is_checkable_link_target``
    called only ``_has_template_marker``, so a placeholder already IN the vocabulary was
    still reported by those two — `NEW_FEATURE.md` matches the `new_feature` topic
    marker and the bare pass reported it regardless (5 findings, measured 2026-09-01).

    B1 closed this shape for the template markers without closing it for the
    placeholders. Pairing them in one predicate is what makes the next entry to either
    vocabulary reach all four passes at once, rather than the two that happened to be
    wired.
    """
    return _has_template_marker(text) or _is_placeholder(text)


def _looks_like_local_path(text: str) -> bool:
    """Heuristic: does this backtick span look like a checkable project file path?"""
    if _is_external(text):
        return False
    # Two-path prose join — see PATH_JOIN_MARKER. Reject the JOIN, never spaces in
    # general: this guard is shared with the fence pass, whose quoted spans exist
    # precisely to keep space-bearing filenames whole (Codex, PR #872), and a blanket
    # space rejection would also lose the live dead `/docs/FastHTML Best Practices –
    # fasthtml.html` — a real finding with spaces in it, measured 2026-09-01.
    if PATH_JOIN_MARKER in text:
        return False
    # `./core/services/foo.py` is a valid repo-relative citation and the natural form in
    # a copy-paste shell command, but it starts with neither `/` nor a known project
    # directory, so the checks below silently dropped it (Codex, PR #872). Normalise
    # here — the shared guard — so the inline-backtick pass gains it too; `resolve_path`
    # strips the same prefix.
    text = text.removeprefix("./")
    if len(text) < 5:
        return False
    if _is_documentation_stand_in(text):
        # template / glob / shell-variable patterns (see TEMPLATE_MARKERS), and
        # `your_service.py` / `alpine.X.Y.Z.min.js` / `adapters/.../foo.py`.
        return False

    # Must start with / or a known project directory
    starts_ok = text.startswith("/") or any(
        text.startswith(d)
        for d in (
            "docs/",
            "core/",
            "adapters/",
            "ui/",
            "scripts/",
            "static/",
            ".claude/",
            "tests/",
            "monitoring/",
        )
    )
    if not starts_ok:
        return False

    # Must have a recognisable extension
    return any(text.endswith(ext) for ext in LOCAL_EXTENSIONS)


class FileScan(NamedTuple):
    """One file's audit: the dead references, plus what was skipped and why.

    The skip counts are carried out of the scan rather than dropped so ``main`` can
    print them. A skip nobody can see is a suppression, and this checker's exclusions
    are supposed to be countable — the same reason the carve-outs print a file count.

    ``stale_markers`` is the other half of every marker's contract: a marker that
    skipped nothing is rot in the marker, so it is a FINDING (rows of
    ``(source, line_no, marker_name, reason)``), not a silent no-op.

    ``marker_skips`` is keyed BY MARKER NAME rather than summed, for the reason the two
    carve-out classes print separately: one number that moves for two unrelated reasons
    is a number nobody can read. It also makes the planned marker's self-retirement
    visible — that count falling is a file getting built.
    """

    dead: list[tuple[Path, int, str, str]]
    route_skips: int
    marker_skips: dict[str, int]
    stale_markers: list[tuple[Path, int, str, str]]


def check_file(md_file: Path, verbose: bool) -> FileScan:
    """
    Check one Markdown file for broken links.
    Returns the dead (relative_source, line_no, raw_link, kind) rows, the counts of
    targets skipped as a registered application route and as a marked historical
    citation, and any marker that skipped nothing.
    """
    try:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return FileScan([], 0, {m.name: 0 for m in MARKERS}, [])

    rel_source = md_file.relative_to(ROOT)
    dead: list[tuple[Path, int, str, str]] = []
    route_skips = 0
    marker_skips: dict[str, int] = {m.name: 0 for m in MARKERS}
    # Every marker's lines are collected, in scope or not — an out-of-scope marker must
    # still be REPORTED as suppressing nothing, which is what stops one from being
    # copied into a tier where it would look effective and be inert.
    marker_lines = {m.name: _marker_lines(content, m) for m in MARKERS}
    honored = {m.name: _honors_marker(md_file, m) for m in MARKERS}
    used_marker_lines: dict[str, set[int]] = {m.name: set() for m in MARKERS}
    # Deduplicate on (lineno, RESOLVED TARGET), not (lineno, raw). Two spellings of one
    # dead file on one line are one defect, and since `./core/x.py` became checkable the
    # backtick pass reports it while the bare pass independently matches its
    # `/core/x.py` tail — a raw-keyed set lets that same file through twice.
    seen: set[tuple[int, str]] = set()

    def record(lineno: int, raw: str, kind: str) -> None:
        nonlocal route_skips, marker_skips
        target = resolve_path(raw, md_file)
        if target is None:
            return
        key = (lineno, str(target))
        if key in seen:
            return
        if target.exists():
            return
        # A live application URL is not a missing file. Checked only once the path has
        # failed to resolve, so a real repo file at a route-shaped path still wins.
        if _is_registered_route(raw):
            seen.add(key)
            route_skips += 1
            if verbose:
                print(f"  ROUTE [{kind}] {rel_source}:{lineno} → {raw}")
            return
        # An author has marked this line's citations — as history, or as a file the
        # plan intends to create. Reached only once the target has failed to resolve
        # AND failed to match a live route, which is the contract: a marker skips a
        # DEAD reference and nothing else, so it can never cover a live one — the
        # property that keeps every marker falsifiable, and the planned one
        # self-retiring.
        for marker in MARKERS:
            if honored[marker.name] and lineno in marker_lines[marker.name]:
                seen.add(key)
                marker_skips[marker.name] += 1
                used_marker_lines[marker.name].add(lineno)
                if verbose:
                    print(f"  {marker.name.upper()} [{kind}] {rel_source}:{lineno} → {raw}")
                return
        seen.add(key)
        dead.append((rel_source, lineno, raw, kind))
        if verbose:
            print(f"  DEAD [{kind}] {rel_source}:{lineno} → {raw}")

    for lineno, _text, path in extract_markdown_links(content):
        record(lineno, path, "link")

    for lineno, path in extract_backtick_paths(content):
        record(lineno, path, "backtick")

    for lineno, path in extract_bare_paths(content):
        record(lineno, path, "bare")

    # Last, so a fenced absolute path keeps its long-standing "bare" label rather
    # than being relabelled by the newer pass (the `seen` dedup is per line+token).
    for lineno, path in extract_fenced_paths(content):
        record(lineno, path, "code")

    # The SKUEL026 inversion: a marker that suppressed nothing is rot in the marker.
    # Out of scope it can never suppress anything, which is a different authoring
    # mistake from a marker whose target came back to life — so the reason is carried.
    #
    # ⭐ For `planned`, the in-scope reason is not a complaint but a SIGNAL: the file
    # got built. That is the property this marker was chosen for, so the message says
    # so rather than telling the reader to delete something they should celebrate.
    stale_markers: list[tuple[Path, int, str, str]] = []
    for marker in MARKERS:
        if honored[marker.name]:
            reason = (
                f"no dead reference on this line — the target now exists, so it is no "
                f"longer {marker.asserts}"
            )
        else:
            reason = f"honored only in {'/, '.join(marker.scope_dirs)}/"
        stale_markers.extend(
            (rel_source, lineno, marker.name, reason)
            for lineno in sorted(marker_lines[marker.name] - used_marker_lines[marker.name])
        )

    return FileScan(dead, route_skips, marker_skips, stale_markers)


def _sort_dead_link_records(record: tuple[Path, int, str, str]) -> tuple[str, int]:
    """Sort dead links by source file path then line number."""
    source, lineno, _, _ = record
    return str(source), lineno


def _sort_stale_marker_records(record: tuple[Path, int, str, str]) -> tuple[str, int]:
    """Sort stale markers by source file path then line number."""
    source, lineno, _, _ = record
    return str(source), lineno


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate documentation links")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each dead link as found")
    args = parser.parse_args()

    print(f"{Colors.BOLD}Dead Doc Link Validator{Colors.RESET}")
    print("=" * 60)

    md_files, carved_out = get_md_files()
    print(f"Scanning {len(md_files)} Markdown files in docs/ and .claude/skills/...")

    all_dead: list[tuple[Path, int, str, str]] = []
    all_stale_markers: list[tuple[Path, int, str, str]] = []
    route_skips = 0
    marker_skips: dict[str, int] = {m.name: 0 for m in MARKERS}
    index_md = Path("docs/INDEX.md")

    for md_file in md_files:
        scan = check_file(md_file, args.verbose)
        all_dead.extend(scan.dead)
        all_stale_markers.extend(scan.stale_markers)
        route_skips += scan.route_skips
        for name, count in scan.marker_skips.items():
            marker_skips[name] += count

    # Printed unconditionally, zero included: each count is the visible half of an
    # exclusion, and a silent zero is how a carve-out that has rotted (or a route
    # matcher that has broken) looks exactly like a clean run.
    print(
        f"{carved_out.unvalidatable} file(s) carved out: freeform notes + templates "
        f"(links unvalidatable by construction)"
    )
    print(
        f"{carved_out.history} file(s) carved out: history directories "
        f"(dated records, where a dead link is the record being faithful)"
    )
    print(f"{route_skips} target(s) skipped: registered application routes (adapters/inbound/)")
    # One line per marker, never summed: they exclude for opposite reasons (was there /
    # is not there yet), so a merged number would move for two unrelated causes.
    for marker in MARKERS:
        print(f"{marker_skips[marker.name]} target(s) skipped: {marker.spelling} markers")
    print()

    if all_dead:
        print(
            f"{Colors.RED}{Colors.BOLD}Broken References — {len(all_dead)} dead links:{Colors.RESET}\n"
        )

        # Group by source file
        by_file: dict[Path, list[tuple[int, str, str]]] = {}
        for source, lineno, raw, kind in sorted(all_dead, key=_sort_dead_link_records):
            by_file.setdefault(source, []).append((lineno, raw, kind))

        index_issues = 0
        for source, items in by_file.items():
            # `index_label`, not `marker`: this function now also iterates `MARKERS`,
            # and one name for two unrelated things is how the two get confused.
            index_label = ""
            if str(source) == str(index_md):
                index_issues = len(items)
                index_label = f"  {Colors.RED}[INDEX.md]{Colors.RESET}"
            print(f"\n  {Colors.BOLD}{source}{Colors.RESET}{index_label}")
            for lineno, raw, kind in items:
                tag = f"[{kind}]"
                print(
                    f"    {Colors.YELLOW}L{lineno:4d}{Colors.RESET}  {tag:10s}  {Colors.RED}{raw}{Colors.RESET}"
                )

        print(f"\n{Colors.YELLOW}Total: {len(all_dead)} broken references{Colors.RESET}")

        if index_issues:
            print(
                f"{Colors.RED}⚠  docs/INDEX.md has {index_issues} broken reference(s) — "
                f"update the index to match current files{Colors.RESET}"
            )

    if all_stale_markers:
        print(
            f"\n{Colors.RED}{Colors.BOLD}Markers that suppress nothing — "
            f"{len(all_stale_markers)}:{Colors.RESET}\n"
        )
        for source, lineno, name, reason in sorted(
            all_stale_markers, key=_sort_stale_marker_records
        ):
            print(
                f"    {Colors.YELLOW}{source}:{lineno}{Colors.RESET}  "
                f"<!-- {name} -->  {Colors.RED}({reason}){Colors.RESET}"
            )
        print(
            f"\n{Colors.YELLOW}Delete the marker — the citation it covered is no longer "
            f"dead, or was never in scope. For a {Colors.BOLD}planned{Colors.RESET}"
            f"{Colors.YELLOW} marker in scope this is the good outcome: the file "
            f"exists now.{Colors.RESET}"
        )

    if all_dead or all_stale_markers:
        return 1

    print(f"{Colors.GREEN}✓ All links valid{Colors.RESET}")
    print(f"{Colors.GREEN}✓ docs/INDEX.md references verified{Colors.RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
