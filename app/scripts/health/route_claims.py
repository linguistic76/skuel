#!/usr/bin/env python3
"""
Route-claim scanner — does every route a live doc names exist?

A doc or skill that describes ``/ku`` when no handler serves it is fiction the link
checker cannot see: ``dead_doc_links.py`` tests link *targets* and repo *files*, and a
route is neither. This scanner reads the inline code spans of the same corpus
(``dead_doc_links.get_md_files()`` — its carve-outs inherited) and matches each
URL-shaped span against the runtime route catalog (``route_catalog.py``).

What it reads — and only this
-----------------------------
Inline code spans outside fenced blocks whose content is ``[METHOD ]/path``:
```` `/api/tasks/create` ````, ```` `POST /api/user-entries/upload` ````. Fence contents
are never counted — a route-shaped string literal inside a fence is an example, and
whether an example is a claim about SKUEL or a lesson about the framework is a read,
not a rule. ``--fences`` lists those literals as an advisory VIEW for a sweep PR
opening the file; nothing counts them. Markdown link destinations, bare prose paths and
frontmatter are not read either — the link checker owns the first, and the other two
carry no route claims in this corpus.

Not every leading-slash span is a claim. ``is_url_shape`` rejects, before matching:
spaces and backticks; regex / glob / shell characters; an Uppercase segment anywhere
(another vendor's API — ``/api/services/Platform/…``); filesystem prefixes and bare
mount names (``/home/…``, ``/opt/…``, ``/conf``, ``/swapfile``, ``/etc``); repo
top-level directories cited as paths (``/services_bootstrap``, ``/services_bootstrap/x``); a
``PROJECT_PREFIXES`` span that is file-shaped or exists in the tree (``/static/css/x.css``,
``/core/services/ps`` — the link checker's; ``/ui/analytics/view`` is neither and is a
claim, because five ``/ui/analytics/*`` routes share the ``/ui/`` prefix); any span
``dead_doc_links._looks_like_local_path`` accepts (``/services_bootstrap.py`` — the
backtick pass resolves it as a file, then as a route, then reports it; the same
predicate, so a leading-slash span is one reader's or the other's, never both); a
trailing-slash ``docs/`` subdirectory (``/patterns/``); a metavariable first segment
(``/{domain}/…``, ``/domain/…``, ``/section/…``); an all-numeric span (``/100``, a
column header); and anything ``dead_doc_links._is_placeholder`` rejects. NOT ``_is_documentation_stand_in``: its
template-marker half rejects ``{uid}``, which every parameterised route carries, and
would drop hundreds of real claims.

Classes — every one printed with a count on every run, zero included
--------------------------------------------------------------------
A class that prints zero for a whole run is what a rotted narrowing looks like from
the outside; a class that is silently skipped looks like a clean scan. So there are no
silent skips — every claim lands in exactly one of:

- ``matched``          registered — exact, or wildcard-segment in one direction (the
                       catalog module says which), and for the claimed verb if one is
                       written (``PUT /x`` is not matched by a ``POST``-only ``/x``)
- ``fiction``          unmatched, not negated, no history signal on the line — the sweep
- ``history``          unmatched, and the line carries a ``history_in_code`` signal
                       (its ``classify`` — ONE vocabulary, imported): the line narrates,
                       and ``history_in_code --docs`` is the census that reads it
- ``family-prefix``    unmatched, strict prefix of ≥1 registered route (``/api/context``
                       naming the door to ``/api/context/*``). A CLASS, never a skip:
                       ``POST /api/knowledge`` is a prefix of ``/api/knowledge/ai/*``
                       and does not exist
- ``relative-suffix``  unmatched single segment that ends ≥1 deeper route (``/create``
                       cited relative to a base named earlier). A CLASS, never a skip:
                       ``/ku`` lands here through ``/library/ku`` and has no handler
- ``negated``          the SPAN is the object of a present-tense negation: ``no `/x```,
                       ``not `/x```, ```/x` → 404``, ```/x` is a 404``, ```/x` returns
                       404``, ```/x` does not exist``. Span-adjacent only — a negation
                       token elsewhere on the line says nothing about this span (a line
                       asserting a dead route "requires ``@require_admin``" is fiction
                       however many "no"s the rest of the sentence carries)
- ``marker-skipped``   the line carries ``<!-- historical -->`` inside ``docs/decisions/``
                       or ``<!-- planned -->`` inside live ``docs/roadmap/`` —
                       ``dead_doc_links``'s ``MarkerSpec`` registry and ``_marker_lines``,
                       not a second marker grammar. Counted per marker, never summed

A marker that skips nothing is rot in the marker. That verdict is computed ONCE, in
``dead_doc_links.check_file`` — its ledger consults this module's ``scan_content`` so a
marker is stale only when it covers neither a dead link nor a dead route claim — and
``./dev health-links`` reports it. This scanner prints the skip counts and points there.

Advisory
--------
Exit 0 whatever it finds. The ``fiction`` class is the only one that could ever gate;
promotion to ``./dev health`` red is a separate ruling that waits on two sweep PRs each
re-measuring ≥95% precision on a fresh draw. ``family-prefix``, ``relative-suffix`` and
``history`` are printed-only by design.

Usage:
    ./dev health-claims                      # per-file fiction counts + class totals
    ./dev health-claims --all                # every fiction site: file:line  METHOD /path
    ./dev health-claims --class history      # a different class through --all / the table
    ./dev health-claims --file docs/x.md …   # a sweep PR's ride-along: only these files
    ./dev health-claims --fences             # the advisory view of fenced string literals
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

# scripts/health/ is not a package — sibling imports resolve at runtime via sys.path[0]
# but not for MyPy (the same ignore stale_names.py carries).
import dead_doc_links as ddl  # type: ignore[import-not-found]
from markdown_fences import (  # type: ignore[import-not-found]
    frontmatter_lines,
    iter_code_fence_blocks,
)
from route_catalog import (  # type: ignore[import-not-found]
    RouteCatalog,
    normalize,
    runtime_catalog,
)

from core.utils.terminal_colors import Colors
from scripts.history_in_code import classify as history_signals

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT = ddl.ROOT

CLASSES: tuple[str, ...] = (
    "matched",
    "fiction",
    "history",
    "family-prefix",
    "relative-suffix",
    "negated",
)
GATE_CANDIDATE = "fiction"
LISTABLE_CLASSES = ("fiction", "history", "family-prefix", "relative-suffix", "negated")


def marker_class(marker_name: str) -> str:
    return f"marker-skipped:{marker_name}"


ALL_CLASSES: tuple[str, ...] = (*CLASSES, *(marker_class(m.name) for m in ddl.MARKERS))

# Every standard verb is admitted as a claim; the verb-aware catalog decides whether the
# route serves it (`OPTIONS /x` on a GET-only route is fiction, not a non-claim).
METHOD_RE = re.compile(r"^(?:(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|TRACE|CONNECT)\s+)?(/\S*)$")
# A string literal inside a fence that starts with "/" — the advisory view only.
FENCE_STR_RE = re.compile(r"""["'](/[A-Za-z0-9_\-{}./:?=&]*)["']""")
# Regex, glob and shell characters: a span carrying one is a pattern, not a path.
NOT_A_PATH_CHARS = frozenset("*$~<>|()\\")
# An Uppercase-then-lowercase segment is another vendor's API or prose, never a SKUEL
# route (every registered segment is lowercase, a `{param}` or a dotted asset name).
UPPERCASE_SEGMENT_RE = re.compile(r"/[A-Z][a-z]")

# Filesystem prefixes a deployment doc cites with a leading slash — matched WITH a
# subpath. The bare names are listed separately below, because one of them is not a
# mount in this corpus: bare `/home` is the application's landing route (a dead one —
# the claim this scanner exists to report), while `/home/<user>/…` is a filesystem path.
# Every entry ends in `/` so it matches on a segment boundary: `/data/x` is a mount
# path, `/database` is not.
FS_PREFIXES = (
    "/home/",
    "/opt/",
    "/etc/",
    "/var/",
    "/tmp/",
    "/usr/",
    "/app/",
    "/root/",
    "/dev/",
    "/proc/",
    "/mnt/",
    "/data/",
    "/srv/",
    "/bin/",
    "/run/",
    "/conf/",
    "/logs/",
    "/plugins/",
    "/import/",
    "/vault/",
    "/bundles/",
)
BARE_MOUNTS = frozenset(
    {p.rstrip("/") for p in FS_PREFIXES if p != "/home/"} | {"/swapfile", "/sys", "/boot"}
)
# A first segment a pattern doc uses to mean "any domain" — the claim is a shape,
# not a route. `{}` is what `normalize` turns any `{…}` first segment into.
METAVAR_FIRST_SEGMENTS = frozenset(
    {
        "domain",
        "{domain}",
        "entity",
        "{entity}",
        "section",
        "resource",
        "path",
        "route",
        "endpoint",
        "example",
        "custom",
    }
)

# ── The negation grammar ─────────────────────────────────────────────────────
# Span-ADJACENT, in both directions: only the text touching the span is read, so a
# "no" or "404" elsewhere on the line says nothing about this span. The corpus lines
# that separate the two grammars are `test_route_claims.py`'s `NEGATION_CORPUS`.
BEFORE_NEG_RE = re.compile(r"\b(?:no|not|never|nor)\s*$", re.IGNORECASE)
# Present tense only: "`/x` was deleted" narrates, and the history class owns it.
AFTER_NEG_RE = re.compile(
    r"^\s*(?:→|->|is a|returns?|gives|yields)?\s*404\b"
    r"|^\s*(?:does not|doesn't|no longer) exist"
    r"|^\s*is (?:deleted|removed|retired|gone)\b",
    re.IGNORECASE,
)


def span_negated(line: str, start: int, end: int) -> bool:
    """Is THIS code span the object of a present-tense negative-existence statement?

    ``start``/``end`` are the span's column range (backticks included). Only the text
    immediately before and immediately after the span is read.
    """
    return bool(BEFORE_NEG_RE.search(line[:start])) or bool(AFTER_NEG_RE.match(line[end:]))


def _repo_top_level_dirs() -> tuple[str, ...]:
    return tuple(
        f"/{p.name}" for p in sorted(ROOT.iterdir()) if p.is_dir() and not p.name.startswith(".")
    )


def looks_like_file(path: str, verb_written: bool = False) -> bool:
    """Is this leading-slash span a file or directory citation rather than a URL?

    Project-prefixed paths belong to the link checker (``/static/`` included — it is a
    mount as well as a directory, and the link checker already resolves it as files).
    A written verb is a route signal: ``GET /manifest.json`` is a claim about a served
    asset, and the link checker never reads a span with a verb in it.
    """
    if path.startswith(ddl.PROJECT_PREFIXES):
        # A repo-rooted span is a file citation — the link checker's — unless nothing
        # about it says "file": no extension (unless a verb is written — `GET
        # /ui/report.json` is a claim the link checker never reads), no line number,
        # no template or elision marker, and nothing in the tree at that path. Read
        # as a route would be (query, anchor and trailing slash dropped) so
        # `/ui/analytics/view/` and `/ui/analytics/view#chart` are the same claim as
        # `/ui/analytics/view`. Five `/ui/analytics/*` routes share the `/ui/` prefix
        # with the `ui/` package and carry no file signal — they stay claims. So does
        # a citation of a directory absent from the tree: no route serves it and no
        # other pass reads an extensionless directory citation, so it reports here
        # as fiction — a name for something that does not exist.
        stem = normalize(path) or path
        return (
            "…" in stem
            or ddl._is_documentation_stand_in(stem)
            or (not verb_written and ddl._looks_like_local_path(stem))
            or ddl.LINE_CITATION_RE.search(stem) is not None
            or (ROOT / stem.lstrip("/")).exists()
        )
    if path.startswith(FS_PREFIXES) or path.rstrip("/") in BARE_MOUNTS:
        return True
    # `/patterns/`, `/guides/` — a docs/ subdirectory cited with a trailing slash.
    if path.endswith("/") and (ROOT / "docs" / path.strip("/")).is_dir():
        return True
    top_level = _repo_top_level_dirs()
    if path in top_level or path.startswith(tuple(f"{d}/" for d in top_level)):
        return True
    # Whatever the link checker's backtick pass would read as a file citation is that
    # pass's to verify — it already resolves such a span as a file, then as a route
    # (`/manifest.json`), then reports it dead. The SAME predicate, so the two readers
    # partition leading-slash spans instead of both reporting `/services_bootstrap.py`.
    # With a verb in the span the link checker reads nothing, so the claim stays here.
    return not verb_written and ddl._looks_like_local_path(path.split("?")[0])


def is_url_shape(text: str) -> tuple[str, str] | None:
    """``(method, path)`` if this span content is a route claim, else ``None``."""
    match = METHOD_RE.match(text.strip())
    if not match:
        return None
    path = match.group(2)
    if len(path) < 2 or path.startswith("//"):
        return None
    if " " in path or "`" in path:
        return None
    if any(ch in path for ch in NOT_A_PATH_CHARS):
        return None
    if looks_like_file(path, verb_written=bool(match.group(1))):
        return None
    if UPPERCASE_SEGMENT_RE.search(path):
        return None
    segments = path.split("?")[0].strip("/").split("/")
    # A span of nothing but digits is a number with a slash in front of it (`/100`,
    # the hits-per-hundred column), not a path; no route has an all-numeric segment.
    if all(seg.isdigit() for seg in segments):
        return None
    first = segments[0]
    # No registered route opens with a parameter, so a `{…}` first segment is a shape.
    if first in METAVAR_FIRST_SEGMENTS or first.startswith("{"):
        return None
    if ddl._is_placeholder(path):
        return None
    return (match.group(1) or "", path)


class Claim(NamedTuple):
    """One route claim, classified."""

    lineno: int
    method: str
    path: str
    cls: str
    line: str

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}".strip()


class FileClaims(NamedTuple):
    """One file's claims plus the marker lines its dead claims used.

    ``marker_used`` is keyed by marker name and feeds ``dead_doc_links.check_file``'s
    ledger — the one place a stale marker is decided.
    """

    claims: list[Claim]
    marker_used: dict[str, set[int]]


def _inline_claims(content: str) -> list[tuple[int, str, str, int, int]]:
    """``(lineno, method, path, span_start, span_end)`` for every inline route claim."""
    lines = content.splitlines()
    # Fences (delimiters included) and the YAML frontmatter are not the doc's voice.
    masked: set[int] = set(frontmatter_lines(content))
    for block in iter_code_fence_blocks(content):
        first, last = block.span
        masked.update(range(first, last + 1))
    out: list[tuple[int, str, str, int, int]] = []
    for lineno, spans in sorted(ddl._inline_code_spans_by_line(content).items()):
        if lineno in masked:
            continue
        line = lines[lineno - 1]
        for start, end in spans:
            text = line[start:end]
            # A span that crosses a soft line break arrives as one slice per line,
            # and a slice missing its opening or closing backtick string is a
            # fragment; a route claim never spans lines.
            if len(text) < 2 or not (text.startswith("`") and text.endswith("`")):
                continue
            shape = is_url_shape(text.strip("`").strip())
            if shape:
                out.append((lineno, shape[0], shape[1], start, end))
    return out


def fence_claims(content: str) -> list[tuple[int, str]]:
    """Route-shaped string literals inside fenced blocks — the advisory view."""
    out: list[tuple[int, str]] = []
    for block in iter_code_fence_blocks(content):
        for lineno, text in block.lines:
            for match in FENCE_STR_RE.finditer(text):
                shape = is_url_shape(match.group(1))
                if shape:
                    out.append((lineno, shape[1]))
    return out


def scan_content(content: str, md_file: Path, catalog: RouteCatalog) -> FileClaims:
    """Classify every inline route claim in one document."""
    lines = content.splitlines()
    marker_lines = {m.name: ddl._marker_lines(content, m) for m in ddl.MARKERS}
    honored = {m.name: ddl._honors_marker(md_file, m) for m in ddl.MARKERS}
    marker_used: dict[str, set[int]] = {m.name: set() for m in ddl.MARKERS}
    claims: list[Claim] = []
    for lineno, method, path, start, end in _inline_claims(content):
        line = lines[lineno - 1]
        norm = normalize(path)
        claims.append(
            Claim(
                lineno,
                method,
                path,
                _classify(
                    catalog,
                    norm,
                    method,
                    line,
                    start,
                    end,
                    lineno,
                    marker_lines,
                    honored,
                    marker_used,
                ),
                line.strip(),
            )
        )
    return FileClaims(claims, marker_used)


def _classify(
    catalog: RouteCatalog,
    norm: str | None,
    method: str,
    line: str,
    start: int,
    end: int,
    lineno: int,
    marker_lines: dict[str, frozenset[int]],
    honored: dict[str, bool],
    marker_used: dict[str, set[int]],
) -> str:
    """The one class this claim lands in — the order IS the precedence."""
    if norm is not None and catalog.is_registered(norm, method):
        return "matched"
    # A marker skips a DEAD claim and nothing else — checked only once the claim has
    # failed to match, so it can never cover a live route (the property that keeps it
    # falsifiable, and the planned one self-retiring).
    for marker in ddl.MARKERS:
        if honored[marker.name] and lineno in marker_lines[marker.name]:
            marker_used[marker.name].add(lineno)
            return marker_class(marker.name)
    if span_negated(line, start, end):
        return "negated"
    if norm is not None and catalog.is_family_prefix(norm):
        return "family-prefix"
    if norm is not None and catalog.is_relative_suffix(norm):
        return "relative-suffix"
    return "history" if history_signals(line) else "fiction"


def scan_file(md_file: Path, catalog: RouteCatalog) -> FileClaims | None:
    """``scan_content`` over a file on disk; ``None`` when it cannot be read."""
    try:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return scan_content(content, md_file, catalog)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def _resolve_files(given: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for raw in given:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        files.append(path)
    return files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Route claims in docs/ + .claude/skills/ vs the runtime route table (exit 0 always)."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="list every site of the chosen class: file:line  METHOD /path",
    )
    parser.add_argument(
        "--class",
        dest="cls",
        choices=LISTABLE_CLASSES,
        default=GATE_CANDIDATE,
        help=f"which class the table and --all report (default: {GATE_CANDIDATE})",
    )
    parser.add_argument(
        "--file",
        nargs="+",
        metavar="PATH",
        help="scan only these Markdown files (a sweep PR's ride-along)",
    )
    parser.add_argument(
        "--fences",
        action="store_true",
        help="also list unmatched route-shaped string literals inside fences (advisory view; never counted)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    print(f"{Colors.BOLD}Route Claim Scanner{Colors.RESET}")
    print("=" * 60)
    catalog = runtime_catalog()
    if args.file:
        files = _resolve_files(args.file)
        missing = [f for f in files if not f.is_file()]
        if missing:
            parser.error(f"no such file: {', '.join(_rel(f) for f in missing)}")
        # The corpus is Markdown; a source file's backticked comments are not claims.
        not_markdown = [f for f in files if f.suffix != ".md"]
        if not_markdown:
            parser.error(f"--file takes Markdown: {', '.join(_rel(f) for f in not_markdown)}")
        carved = ddl.ScopeSkips(0, 0)
        print(f"Scanning {len(files)} file(s) given on the command line...")
    else:
        files, carved = ddl.get_md_files()
        print(f"Scanning {len(files)} Markdown files in docs/ and .claude/skills/...")
    print(f"Catalog: {len(catalog)} registered paths (runtime route table, union over tiers)")
    print(
        f"{carved.unvalidatable} file(s) carved out: freeform notes + templates; "
        f"{carved.history} file(s) carved out: history directories (as dead_doc_links)"
    )

    totals: Counter[str] = Counter()
    listed: list[tuple[str, Claim]] = []
    per_file: Counter[str] = Counter()
    fenced_unmatched: list[tuple[str, int, str]] = []
    for md_file in files:
        scan = scan_file(md_file, catalog)
        if scan is None:
            continue
        rel = _rel(md_file)
        for claim in scan.claims:
            totals[claim.cls] += 1
            if claim.cls == args.cls:
                per_file[rel] += 1
                listed.append((rel, claim))
        if args.fences:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            for lineno, path in fence_claims(content):
                norm = normalize(path)
                if norm is None or not catalog.is_registered(norm):
                    fenced_unmatched.append((rel, lineno, path))

    # Printed unconditionally, zero included: a class that goes quiet without saying
    # so is indistinguishable from a clean scan.
    print(
        f"\n{Colors.BOLD}Claims by class{Colors.RESET} ({sum(totals.values())} inline route claims):"
    )
    for cls in ALL_CLASSES:
        note = ""
        if cls == GATE_CANDIDATE:
            note = "  ← the sweep queue (advisory; promotion to health-red is a separate ruling)"
        elif cls in ("family-prefix", "relative-suffix"):
            note = "  (printed, never a skip — each hides real fiction when treated as a match)"
        elif cls == "history":
            note = "  (the line narrates — read by history_in_code --docs)"
        elif cls == "negated":
            note = "  (span-adjacent present-tense negation)"
        elif cls.startswith("marker-skipped:"):
            spec = ddl.MARKERS_BY_NAME[cls.split(":", 1)[1]]
            note = f"  ({spec.spelling}, honored in {'/, '.join(spec.scope_dirs)}/)"
        print(f"  {totals[cls]:5d}  {cls:<24s}{note}")
    print("  stale markers: reported by ./dev health-links (one ledger for links and route claims)")

    if per_file:
        print(f"\n{Colors.BOLD}{args.cls} by file{Colors.RESET} (most first):")
        for rel, count in sorted(per_file.items(), key=_count_desc_then_path):
            print(f"  {count:5d}  {rel}")
    else:
        print(f"\n{Colors.GREEN}No {args.cls} claims.{Colors.RESET}")

    if args.all and listed:
        print(f"\n{Colors.BOLD}Every {args.cls} site{Colors.RESET}:")
        for rel, claim in sorted(listed, key=_site_key):
            print(f"  {rel}:{claim.lineno}  {Colors.RED}{claim.label}{Colors.RESET}")

    if args.fences:
        print(
            f"\n{Colors.BOLD}Fenced string literals not in the catalog{Colors.RESET} "
            f"— {len(fenced_unmatched)} (advisory view; a read decides whether each is a "
            f"claim about SKUEL or a lesson about the framework; never counted above):"
        )
        for rel, lineno, path in fenced_unmatched:
            print(f"  {rel}:{lineno}  {path}")

    print(f"\n{Colors.YELLOW}Advisory — exit 0 always.{Colors.RESET}")
    return 0


def _count_desc_then_path(item: tuple[str, int]) -> tuple[int, str]:
    rel, count = item
    return (-count, rel)


def _site_key(item: tuple[str, Claim]) -> tuple[str, int]:
    rel, claim = item
    return (rel, claim.lineno)


if __name__ == "__main__":
    sys.exit(main())
