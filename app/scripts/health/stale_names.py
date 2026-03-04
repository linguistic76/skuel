#!/usr/bin/env python3
"""
Stale Name Scanner
==================

Scans documentation code blocks for deprecated identifiers that have been
renamed or deleted as SKUEL evolves.

Only checks fenced ``` code blocks and inline `backtick` spans — not prose —
to avoid flagging legitimate historical descriptions.

Usage:
    poetry run python scripts/health/stale_names.py
    poetry run python scripts/health/stale_names.py --verbose
    poetry run python scripts/health/stale_names.py --list   # Print the full RENAMED/DELETED tables
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
    ROOT / "CLAUDE.md",  # also check the main instructions file
]

# ── Renamed identifiers ──────────────────────────────────────────────────────
# "old_identifier": "replacement"
#
# Keep this up-to-date as SKUEL evolves.  When a rename is confirmed and all
# code + docs are updated, move the entry to the archive comment at the bottom.
#
RENAMED: dict[str, str] = {
    # EntityType enum values (Feb–Mar 2026)
    "EntityType.CURRICULUM": "EntityType.KU",
    "EntityType.AI_FEEDBACK": "EntityType.ACTIVITY_REPORT",
    "EntityType.FEEDBACK_REPORT": "EntityType.SUBMISSION_FEEDBACK",
    # Class renames (Feb–Mar 2026)
    "AiFeedback": "ActivityReport",
    "KuTaskCreateRequest": "TaskCreateRequest",
    "KuAnalyticsEngine": "AnalyticsEngine",
    "ActivityReviewService": "ActivityReportService",
    "ActivityReviewOperations": "ActivityReportOperations",
    "SubmissionsSharingService": "UnifiedSharingService",
    # Old enum type names (pre entity_enums split, Feb 2026)
    "KuStatus": "EntityStatus",
    "KuType": "EntityType",
    # UserContext field renames (Mar 2026 — entities_rich unification)
    "active_tasks_rich": 'entities_rich["tasks"]',
    "active_goals_rich": 'entities_rich["goals"]',
    "active_habits_rich": 'entities_rich["habits"]',
    "active_events_rich": 'entities_rich["events"]',
    "active_choices_rich": 'entities_rich["choices"]',
    "active_principles_rich": 'entities_rich["principles"]',
    "activity_rich": "entities_rich",
    "populate_rich_fields": "populate_entities_rich",
    # build_rich() parameter rename (Mar 2026)
    "time_period=": "window=",
    # Method renames (Submissions rename, Feb 2026)
    "list_reports": "list_submissions",
    "get_recent_reports": "get_recent_submissions",
    # Old module-level class rename (Privacy refactor, Mar 2026)
    "class Feedback(": "class SubmissionFeedback(",
    # Old import paths (post ku/ monolith dissolution, Feb 2026)
    "from core.models.ku.ku_enums import": "from core.models.enums.entity_enums import (or domain-specific enums file)",
    "from core.models.ku import": "from core.models.<domain> import  (ku/ monolith deleted)",
    # Old report domain imports (Reports→Submissions, Feb 2026)
    "from core.services.reports": "from core.services.submissions or core.services.feedback",
    "from core.models.reports": "from core.models.submissions or core.models.feedback",
    # Old ActivityDataReader (absorbed into UserContext, Mar 2026)
    "ActivityDataReader": "UserContextBuilder.build_rich() — ActivityDataReader absorbed",
    "ActivityData(": "ActivityData frozen dataclass deleted — data now in UserContext",
    # daisy_components (decomposed Feb 2026)
    "from ui.daisy_components import": "from ui.<module> import  (daisy_components decomposed)",
    "daisy_components": "focused ui/ modules (decomposed Feb 2026)",
    # Old component imports (components/ deleted Feb 2026)
    "from components.": "from ui.<domain>.views import  (components/ deleted)",
}

# ── Deleted identifiers ──────────────────────────────────────────────────────
# "deleted_identifier": "explanation / what replaced it"
DELETED: dict[str, str] = {
    # Deleted modules
    "htmx_a11y": "module deleted — accessibility patterns moved inline",
    "sel_routes": "module deleted — SEL domain removed",
    "relationship_decorator": "deleted — use explicit delegation methods",
    "submissions_sharing_service": "replaced by UnifiedSharingService",
    "activity_review_service.py": "replaced by activity_report_service.py + review_queue_service.py",
    "planning_mixin.ActivityDataReader": "absorbed into UserContextBuilder",
    # Deleted classes / concepts
    "ProfileLayout": "deleted — use BasePage(page_type=PageType.CUSTOM)",
    # Deleted directories referenced as import paths
    "core.models.ku.": "core/models/ku/ monolith deleted — use domain-specific paths",
    "components.tasks": "components/ deleted — use ui.tasks.views",
    "components.goals": "components/ deleted — use ui.goals.views",
    "components.habits": "components/ deleted — use ui.habits.views",
    "components.events": "components/ deleted — use ui.events.views",
    "components.choices": "components/ deleted — use ui.choices.views",
    "components.principles": "components/ deleted — use ui.principles.views",
}


def get_scan_targets() -> list[Path]:
    """Collect all .md files from SCAN_DIRS."""
    result: list[Path] = []
    for target in SCAN_DIRS:
        if target.is_file() and target.suffix == ".md":
            result.append(target)
        elif target.is_dir():
            result.extend(sorted(target.rglob("*.md")))
    return result


def extract_code_segments(content: str) -> list[tuple[int, str]]:
    """
    Extract fenced code blocks and inline backtick spans.

    Returns list of (start_line_no, segment_text).
    For multi-line fenced blocks, start_line_no is the opening fence line.
    """
    results: list[tuple[int, str]] = []
    lines = content.splitlines()

    in_block = False
    block_start = 0
    block_lines: list[str] = []
    fence_char = ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect fenced block open/close
        if not in_block and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_block = True
            fence_char = stripped[:3]
            block_start = i
            block_lines = []
            continue

        if in_block and stripped.startswith(fence_char):
            in_block = False
            results.append((block_start, "\n".join(block_lines)))
            block_lines = []
            fence_char = ""
            continue

        if in_block:
            block_lines.append(line)
            continue

        # Inline backtick spans (not inside a fenced block)
        for match in re.finditer(r"`([^`\n]+)`", line):
            results.append((i, match.group(1)))

    return results


def scan_file(md_file: Path) -> list[tuple[int, str, str, str]]:
    """
    Scan one .md file for stale names inside code blocks.

    Returns list of (line_no, old_identifier, replacement, kind)
    where kind is "renamed" or "deleted".
    """
    try:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    issues: list[tuple[int, str, str, str]] = []
    segments = extract_code_segments(content)

    for block_start, segment in segments:
        seg_lines = segment.splitlines() if "\n" in segment else [segment]

        for j, seg_line in enumerate(seg_lines):
            lineno = block_start + j

            for old, new in RENAMED.items():
                if old in seg_line:
                    issues.append((lineno, old, new, "renamed"))

            for deleted, reason in DELETED.items():
                if deleted in seg_line:
                    issues.append((lineno, deleted, reason, "deleted"))

    return issues


def _sort_stale_name_issues(record: tuple[Path, int, str, str, str]) -> tuple[str, int]:
    """Sort stale name issues by source path then line number."""
    source, lineno, _, _, _ = record
    return str(source), lineno


def print_tables() -> None:
    """Print the full RENAMED and DELETED tables."""
    print(f"\n{BOLD}RENAMED identifiers ({len(RENAMED)}):{RESET}")
    for old, new in sorted(RENAMED.items()):
        print(f"  {RED}{old}{RESET} → {GREEN}{new}{RESET}")

    print(f"\n{BOLD}DELETED identifiers ({len(DELETED)}):{RESET}")
    for ident, reason in sorted(DELETED.items()):
        print(f"  {RED}{ident}{RESET}")
        print(f"      {CYAN}{reason}{RESET}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan docs for deprecated/renamed/deleted identifiers in code blocks"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each hit as found")
    parser.add_argument(
        "--list", "-l", action="store_true", help="Print the full RENAMED/DELETED tables and exit"
    )
    args = parser.parse_args()

    if args.list:
        print_tables()
        return 0

    print(f"{BOLD}Stale Name Scanner{RESET}")
    print("=" * 60)
    print(f"Rules: {len(RENAMED)} renamed identifiers, {len(DELETED)} deleted identifiers\n")

    md_files = get_scan_targets()
    print(f"Scanning {len(md_files)} Markdown files (code blocks only)...\n")

    all_issues: list[tuple[Path, int, str, str, str]] = []

    for md_file in md_files:
        issues = scan_file(md_file)
        for lineno, old, new, kind in issues:
            rel = md_file.relative_to(ROOT)
            all_issues.append((rel, lineno, old, new, kind))
            if args.verbose:
                print(f"  [{kind}] {rel}:{lineno}  {old}")

    if all_issues:
        print(f"{RED}{BOLD}Stale Names — {len(all_issues)} violations:{RESET}\n")

        current_file = None
        for source, lineno, old, new, kind in sorted(all_issues, key=_sort_stale_name_issues):
            if source != current_file:
                print(f"\n  {BOLD}{source}{RESET}")
                current_file = source

            if kind == "renamed":
                print(f"    {YELLOW}L{lineno:4d}{RESET}  {RED}{old}{RESET} → {GREEN}{new}{RESET}")
            else:  # deleted
                print(f"    {YELLOW}L{lineno:4d}{RESET}  {RED}[DELETED]{RESET} {RED}{old}{RESET}")
                print(f"               {CYAN}reason: {new}{RESET}")

        print(f"\n{YELLOW}Total: {len(all_issues)} stale references{RESET}")
        print(f"\n{CYAN}Tip: Run with --list to see all tracked renamed/deleted identifiers{RESET}")
        return 1
    else:
        print(f"{GREEN}✓ No stale names found{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

# ── Archive of resolved renames ───────────────────────────────────────────────
# Once a rename has been fully applied to ALL code and docs and verified by this
# script reporting zero violations, move it here so it doesn't clutter the active
# RENAMED dict but is preserved for historical reference.
#
# (none yet — script introduced 2026-03-03)
