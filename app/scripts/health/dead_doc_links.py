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

Also confirms that all files referenced in docs/INDEX.md exist.

Usage:
    uv run python scripts/health/dead_doc_links.py
    uv run python scripts/health/dead_doc_links.py --verbose
"""

import re
import sys
from pathlib import Path

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

# A maximal run of path-plausible characters inside a fenced code block.
#
# Template markers (`{ } < > * $ ~`) are deliberately INSIDE the class so they stay
# attached to their token and `_looks_like_local_path` can reject the whole thing.
# Excluding them would split `core/services/{domain}/{domain}_service.py` into
# clean-looking fragments and hand the guard a false positive it cannot see.
FENCE_TOKEN_RE = re.compile(r"[A-Za-z0-9_./{}<>*$~-]+")

# Opening/closing fence: 3+ backticks or tildes, optionally indented (list items).
FENCE_DELIM_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")


def get_md_files() -> list[Path]:
    result: list[Path] = []
    for base in SCAN_DIRS:
        if base.exists():
            result.extend(sorted(base.rglob("*.md")))
    return result


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

    # Mirror _looks_like_local_path's `./` normalisation so the guard and the resolver
    # agree on what a token means.
    raw = raw.removeprefix("./")

    if raw.startswith("/"):
        # Absolute path relative to repo root — the ONE canonical citation
        # style for repo files. Machine-absolute citations
        # (`/home/<user>/skuel/app/…`) are deliberately NOT rescued via an
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


def extract_markdown_links(content: str) -> list[tuple[int, str, str]]:
    """
    Extract [text](path) patterns.
    Returns list of (line_no, display_text, raw_path).
    """
    results = []
    for i, line in enumerate(content.splitlines(), 1):
        for match in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", line):
            text = match.group(1)
            path = match.group(2).strip()
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
            if any(raw.endswith(ext) for ext in LOCAL_EXTENSIONS):
                results.append((i, raw))
    return results


def _strip_quote_prefix(line: str) -> str:
    """Strip Markdown blockquote markers (`>`, `> >`, …) from the head of a line."""
    stripped = line
    while True:
        candidate = stripped.lstrip()
        if not candidate.startswith(">"):
            return stripped
        stripped = candidate[1:].removeprefix(" ")


def iter_code_fence_lines(content: str) -> list[tuple[int, str, str]]:
    """
    Walk triple-backtick/tilde fenced blocks.

    Returns list of (line_no, language_tag, line) for lines INSIDE a fence — the
    delimiter lines themselves are excluded. A fence closes only on the same
    delimiter character, at least as long, and carrying no info string, so a
    ```` ```python ```` inside a ```` ````markdown ```` wrapper does not close it.

    Deliberately NOT ``stale_names.extract_code_segments``, which also walks fences
    in this directory. That one returns whole blocks keyed by their *opening* line,
    which would degrade this checker's per-line coordinates to "somewhere in the
    block starting at L400" — a link report is only actionable at a line. It also
    treats any ``` run as a closer, so it truncates the wrapper case above. Reuse
    needs the shared walker to yield per-line, and fixing that walker moves
    ``stale_names``' own totals — a separate change, not this one.

    Blockquoted fences count. `lstrip()` alone drops whitespace but not the `> `
    container marker, so a quoted example never opened the fence and its contents were
    silently skipped — a live one sits at
    ``docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md:318`` (Codex, PR #872). The quote
    prefix is stripped only for fences *opened* inside a quote, so a shell redirect at
    the start of an unquoted fence line keeps its `>`.
    """
    results: list[tuple[int, str, str]] = []
    delim: str | None = None
    delim_len = 0
    lang = ""
    quoted = False

    for i, raw_line in enumerate(content.splitlines(), 1):
        line = _strip_quote_prefix(raw_line) if delim is None or quoted else raw_line
        match = FENCE_DELIM_RE.match(line.lstrip())
        if delim is None:
            if match:
                delim = match.group(1)[0]
                delim_len = len(match.group(1))
                info = match.group(2).strip()
                lang = info.split()[0].lower() if info else ""
                quoted = line is not raw_line and raw_line.lstrip().startswith(">")
            continue
        if (
            match
            and match.group(1)[0] == delim
            and len(match.group(1)) >= delim_len
            and not match.group(2).strip()
        ):
            delim = None
            lang = ""
            quoted = False
            continue
        results.append((i, lang, line))
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
        for token in FENCE_TOKEN_RE.findall(line):
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


def _is_placeholder(text: str) -> bool:
    """Does this path use a documentation placeholder the reader is meant to replace?"""
    lowered = text.lower()
    if any(marker in lowered for marker in PLACEHOLDER_SUBSTRINGS):
        return True
    if PLACEHOLDER_METAVAR_RE.search(text):
        return True
    for segment in lowered.split("/"):
        if _matches_topic_marker(segment):
            return True
        # A test *for* a placeholder subject is itself a placeholder, and the marker
        # sits behind the `test_` prefix: `test_foo.py`, `test_your_service.py`.
        subject = segment.removeprefix("test_")
        if subject.startswith(PLACEHOLDER_SUBJECT_PREFIXES):
            return True
        if PLACEHOLDER_METASYNTACTIC_RE.match(subject):
            return True
    return False


def _looks_like_local_path(text: str) -> bool:
    """Heuristic: does this backtick span look like a checkable project file path?"""
    if _is_external(text):
        return False
    # `./core/services/foo.py` is a valid repo-relative citation and the natural form in
    # a copy-paste shell command, but it starts with neither `/` nor a known project
    # directory, so the checks below silently dropped it (Codex, PR #872). Normalise
    # here — the shared guard — so the inline-backtick pass gains it too; `resolve_path`
    # strips the same prefix.
    text = text.removeprefix("./")
    if len(text) < 5:
        return False
    if "{" in text or "<" in text or "*" in text:
        return False  # template / glob patterns
    if _is_placeholder(text):
        return False  # `your_service.py`, `alpine.X.Y.Z.min.js`, `adapters/.../foo.py`

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


def check_file(md_file: Path, verbose: bool) -> list[tuple[Path, int, str, str]]:
    """
    Check one Markdown file for broken links.
    Returns list of (relative_source, line_no, raw_link, kind).
    """
    try:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    rel_source = md_file.relative_to(ROOT)
    dead: list[tuple[Path, int, str, str]] = []
    # Deduplicate on (lineno, RESOLVED TARGET), not (lineno, raw). Two spellings of one
    # dead file on one line are one defect, and since `./core/x.py` became checkable the
    # backtick pass reports it while the bare pass independently matches its
    # `/core/x.py` tail — a raw-keyed set lets that same file through twice.
    seen: set[tuple[int, str]] = set()

    def record(lineno: int, raw: str, kind: str) -> None:
        target = resolve_path(raw, md_file)
        if target is None:
            return
        key = (lineno, str(target))
        if key in seen:
            return
        if not target.exists():
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

    return dead


def _sort_dead_link_records(record: tuple[Path, int, str, str]) -> tuple[str, int]:
    """Sort dead links by source file path then line number."""
    source, lineno, _, _ = record
    return str(source), lineno


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate documentation links")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each dead link as found")
    args = parser.parse_args()

    print(f"{Colors.BOLD}Dead Doc Link Validator{Colors.RESET}")
    print("=" * 60)

    md_files = get_md_files()
    print(f"Scanning {len(md_files)} Markdown files in docs/ and .claude/skills/...\n")

    all_dead: list[tuple[Path, int, str, str]] = []
    index_md = Path("docs/INDEX.md")

    for md_file in md_files:
        dead = check_file(md_file, args.verbose)
        all_dead.extend(dead)

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
            marker = ""
            if str(source) == str(index_md):
                index_issues = len(items)
                marker = f"  {Colors.RED}[INDEX.md]{Colors.RESET}"
            print(f"\n  {Colors.BOLD}{source}{Colors.RESET}{marker}")
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
        return 1
    else:
        print(f"{Colors.GREEN}✓ All links valid{Colors.RESET}")
        print(f"{Colors.GREEN}✓ docs/INDEX.md references verified{Colors.RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
