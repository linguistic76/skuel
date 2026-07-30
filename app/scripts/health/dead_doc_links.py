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

Fence *boundaries* come from a CommonMark parser (``markdown-it-py``), not a
hand-written scanner. A scanner was tried and accrued five container-handling bugs in
one review — see ``iter_code_fence_lines`` for the list and for why a tree-wide
differential showing "zero disagreements" was not the evidence of correctness it
looked like.

Also confirms that all files referenced in docs/INDEX.md exist.

Usage:
    uv run python scripts/health/dead_doc_links.py
    uv run python scripts/health/dead_doc_links.py --verbose
"""

import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt

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


def _strip_quote_prefix(line: str, depth: int | None = None) -> str:
    """
    Remove Markdown blockquote container markers from the head of a line.

    ``depth`` bounds how many are removed; pass the parser's quote depth so that a
    literal ``>`` in *fence content* survives. Stripping greedily conflates the two: in
    a quoted fence holding a no-space shell redirect, ``> >core/generated.txt`` has one
    container marker and one content character, and eating both hands the guard a bare
    path that gets reported — while the identical unquoted redirect is correctly rejected
    by the ``>`` template marker. Quoting a fence must not change what it reports
    (Codex, PR #872).

    ``None`` means strip every marker, which is only right when the caller has no depth
    to work from.
    """
    remaining = depth
    stripped = line
    while remaining is None or remaining > 0:
        candidate = stripped.lstrip()
        if not candidate.startswith(">"):
            break
        stripped = candidate[1:].removeprefix(" ")
        if remaining is not None:
            remaining -= 1
    return stripped


def _closes_fence(line: str, opener: str, quote_depth: int) -> bool:
    """
    Is this line a valid CommonMark closing delimiter for a fence opened with ``opener``?

    Exact rather than heuristic, and measured against the parser's own ``token.markup``:
    a closer uses the same character, is at least as long as the opener, and carries
    nothing but whitespace afterwards. A "starts with ``` or ~~~" test admits three
    non-closers — a shorter run, the other delimiter character, and a run followed by
    text — and each one makes an *unclosed* fence look closed, dropping its last line
    from the audit. `` ```core/dead.py `` at the end of a file is the shape that bites
    (Codex, PR #872).

    The quote prefix comes off first: a blockquoted fence closes on ``> ``` ``, whose
    ``lstrip()`` starts with ``>``, so testing the raw line calls a closed fence unclosed
    and emits its own closing delimiter as content.
    """
    candidate = _strip_quote_prefix(line, quote_depth).lstrip()
    char = opener[0]
    run = len(candidate) - len(candidate.lstrip(char))
    return run >= len(opener) and not candidate[run:].strip()


def iter_code_fence_lines(content: str) -> list[tuple[int, str, str]]:
    """
    Return (line_no, language_tag, line) for every line INSIDE a fenced code block.

    Fence boundaries come from a real CommonMark parser, not a hand-written scanner.
    The scanner this replaced accrued **five** container-handling bugs in one review
    (PR #872): blockquoted fences never opened; an unclosed quoted fence then leaked
    into following prose; a fence opened in a nested quote (``> > ```) did not close
    when the inner quote ended; a list-item fence without a closer swallowed the rest
    of the document; and a four-space-indented delimiter — an *indented code block*
    under CommonMark, not a fence — was opened as a real fence. Each one falsely
    reported ordinary prose as ``[code]``.

    The lesson is why this is a parser call and not a longer regex: a tree-wide
    differential found ZERO disagreements with CommonMark, which read as "the scanner
    is equivalent" but only ever meant "the corpus contains none of these shapes."
    Corpus-relative agreement is not correctness. Every construction above is absent
    from ``docs/`` today and would have started silently misreporting the moment
    someone wrote one.

    Swapping the parser in left the report byte-identical (908 broken refs, before and
    after), so this buys correctness on unseen input at zero behavioural cost.

    Note this is deliberately NOT ``stale_names.extract_code_segments``, the other
    fence walker in this directory: that one keys whole blocks by their *opening* line,
    and a link report is only actionable at a line. It carries the same class of bug
    (see the chip filed from PR #872) and should move to this parser too.
    """
    lines = content.splitlines()
    results: list[tuple[int, str, str]] = []
    quote_depth = 0

    # Fences are block tokens, so they sit in the flat stream; only `inline` tokens carry
    # children. Blockquote depth comes from the parser rather than being sniffed off the
    # line, which is what lets the strip below stay narrow.
    for token in MarkdownIt("commonmark").parse(content):
        if token.type == "blockquote_open":
            quote_depth += 1
        elif token.type == "blockquote_close":
            quote_depth -= 1
        elif token.type == "fence" and token.map:
            start, end = token.map  # 0-based, [start, end)
            # An unclosed fence has no closing delimiter line to skip, so whether the
            # last line is a real closer decides if it is content. Assuming it always
            # is once made this module's own CommonMark differential report a false
            # disagreement — the harness was wrong, not the code under test.
            closed = end - 1 < len(lines) and _closes_fence(
                lines[end - 1], token.markup, quote_depth
            )
            info = token.info.strip()
            lang = info.split()[0].lower() if info else ""
            for lineno in range(start + 2, (end - 1 if closed else end) + 1):
                line = lines[lineno - 1]
                # Strip `> ` only inside a real blockquote, so a shell redirect at the
                # start of an unquoted fence line keeps its `>`.
                results.append(
                    (lineno, lang, _strip_quote_prefix(line, quote_depth) if quote_depth else line)
                )

    return sorted(results)


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
    if any(marker in text for marker in TEMPLATE_MARKERS):
        return False  # template / glob / shell-variable patterns — see TEMPLATE_MARKERS
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
