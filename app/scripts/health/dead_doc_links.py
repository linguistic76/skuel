#!/usr/bin/env python3
"""
Dead Doc Link Validator
=======================

Validates all links and path references in Markdown documentation.

For every .md file in docs/ and .claude/skills/:
  - Extract [text](path) markdown links
  - Extract inline paths in backtick code (e.g. `/docs/patterns/foo.md`)
  - Extract bare /absolute/paths that look like file references
  - Check each exists relative to the repo root
  - Report: dead link, source file, line number

Also confirms that all files referenced in docs/INDEX.md exist.

Usage:
    poetry run python scripts/health/dead_doc_links.py
    poetry run python scripts/health/dead_doc_links.py --verbose
"""

import re
import sys
from pathlib import Path

# ANSI colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

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


def get_md_files() -> list[Path]:
    result: list[Path] = []
    for base in SCAN_DIRS:
        if base.exists():
            result.extend(sorted(base.rglob("*.md")))
    return result


def _is_external(link: str) -> bool:
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

    if raw.startswith("/"):
        # Absolute path relative to repo root
        return ROOT / raw.lstrip("/")
    else:
        # Relative path from source file's directory
        return (source_file.parent / raw).resolve()


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
    # Match /project-prefix/... paths ending with a file extension
    pattern = re.compile(
        r"(?<![`\[(])"  # not inside link or backtick (already handled above)
        r"((?:" + "|".join(re.escape(p) for p in PROJECT_PREFIXES) + r")[^\s\)\]`\"'<>,]+)"
    )
    for i, line in enumerate(content.splitlines(), 1):
        # Skip lines that are markdown link syntax (already covered)
        for match in pattern.finditer(line):
            raw = match.group(1).rstrip(".,;:")
            if any(raw.endswith(ext) for ext in LOCAL_EXTENSIONS):
                results.append((i, raw))
    return results


def _looks_like_local_path(text: str) -> bool:
    """Heuristic: does this backtick span look like a checkable project file path?"""
    if _is_external(text):
        return False
    if len(text) < 5:
        return False
    if "{" in text or "<" in text or "*" in text:
        return False  # template / glob patterns

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
    seen: set[tuple[int, str]] = set()  # deduplicate (lineno, raw) pairs

    def record(lineno: int, raw: str, kind: str) -> None:
        key = (lineno, raw)
        if key in seen:
            return
        target = resolve_path(raw, md_file)
        if target is None:
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

    print(f"{BOLD}Dead Doc Link Validator{RESET}")
    print("=" * 60)

    md_files = get_md_files()
    print(f"Scanning {len(md_files)} Markdown files in docs/ and .claude/skills/...\n")

    all_dead: list[tuple[Path, int, str, str]] = []
    index_md = Path("docs/INDEX.md")

    for md_file in md_files:
        dead = check_file(md_file, args.verbose)
        all_dead.extend(dead)

    if all_dead:
        print(f"{RED}{BOLD}Broken References — {len(all_dead)} dead links:{RESET}\n")

        # Group by source file
        by_file: dict[Path, list[tuple[int, str, str]]] = {}
        for source, lineno, raw, kind in sorted(all_dead, key=_sort_dead_link_records):
            by_file.setdefault(source, []).append((lineno, raw, kind))

        index_issues = 0
        for source, items in by_file.items():
            marker = ""
            if str(source) == str(index_md):
                index_issues = len(items)
                marker = f"  {RED}[INDEX.md]{RESET}"
            print(f"\n  {BOLD}{source}{RESET}{marker}")
            for lineno, raw, kind in items:
                tag = f"[{kind}]"
                print(f"    {YELLOW}L{lineno:4d}{RESET}  {tag:10s}  {RED}{raw}{RESET}")

        print(f"\n{YELLOW}Total: {len(all_dead)} broken references{RESET}")

        if index_issues:
            print(
                f"{RED}⚠  docs/INDEX.md has {index_issues} broken reference(s) — "
                f"update the index to match current files{RESET}"
            )
        return 1
    else:
        print(f"{GREEN}✓ All links valid{RESET}")
        print(f"{GREEN}✓ docs/INDEX.md references verified{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
