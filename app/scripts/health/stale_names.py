#!/usr/bin/env python3
"""
Stale Name Scanner
==================

Scans documentation code blocks for deprecated identifiers that have been
renamed or deleted as SKUEL evolves.

Only checks fenced ``` code blocks and inline `backtick` spans — not prose —
to avoid flagging legitimate historical descriptions.

Fence boundaries come from ``scripts/health/markdown_fences``, the CommonMark-backed
walker shared with ``dead_doc_links.py``. See ``extract_code_segments`` for the two
coordinate rules it fixed.

Usage:
    uv run python scripts/health/stale_names.py
    uv run python scripts/health/stale_names.py --verbose
    uv run python scripts/health/stale_names.py --list   # Print the full RENAMED/DELETED tables
"""

import re
import sys
from pathlib import Path

# scripts/health/ is not a package — these modules are run as scripts, so the sibling
# import resolves at runtime via sys.path[0] but not for MyPy (matches the same ignore
# in tests/unit/scripts/test_dead_doc_links.py).
from markdown_fences import iter_code_fence_blocks  # type: ignore[import-not-found]

from core.utils.terminal_colors import Colors

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
    "EntityType.CURRICULUM": "EntityType.PATH_STEP",
    "EntityType.ARTICLE": "EntityType.PATH_STEP",
    "EntityType.AI_FEEDBACK": "EntityType.ACTIVITY_REPORT",
    "EntityType.FEEDBACK_REPORT": "EntityType.ENTRY_REPORT",
    # Submission/Report hierarchy refactoring (Mar 2026) → UserEntry collapse (Apr 2026)
    "EntityType.SUBMISSION": "EntityType.USER_ENTRY",
    "EntityType.JOURNAL": "EntityType.USER_ENTRY",
    "EntityType.SUBMISSION_REPORT": "EntityType.ENTRY_REPORT",
    # Journal domain extraction (Mar 2026) → UserEntry collapse (Apr 2026)
    "EntityType.JOURNAL_SUBMISSION": "EntityType.USER_ENTRY",
    "EntityType.JOURNAL_REPORT": "EntityType.USER_ENTRY",
    "JournalSubmission": "UserEntry (pipeline=transcribe_and_structure)",
    "JournalReport": "UserEntry (TRANSFORMS output)",
    "JournalSubmissionDTO": "UserEntryDTO",
    "JournalReportDTO": "UserEntryDTO",
    # Class renames (Feb–Mar 2026)
    "AiFeedback": "ActivityReport",
    "KuTaskCreateRequest": "TaskCreateRequest",
    "KuAnalyticsEngine": "TaskKnowledgeAnalyzer",
    "AnalyticsEngine": "TaskKnowledgeAnalyzer — core/services/tasks/task_knowledge_analyzer.py",
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
    "class Feedback(": "class EntryReport(",
    # Old import paths (post ku/ monolith dissolution, Feb 2026)
    "from core.models.ku.ku_enums import": "from core.models.enums.entity_enums import (or domain-specific enums file)",
    "from core.models.ku import": "from core.models.<domain> import  (ku/ monolith deleted)",
    # Old report domain imports (Reports→Submissions, Feb 2026)
    "from core.services.reports": "from core.services.report or core.services.user_entry",
    "from core.models.reports": "from core.models.report or core.models.user_entry",
    # Old ActivityDataReader (absorbed into UserContext, Mar 2026)
    "ActivityDataReader": "UserContextBuilder.build_rich() — ActivityDataReader absorbed",
    "ActivityData(": "ActivityData frozen dataclass deleted — data now in UserContext",
    # daisy_components (decomposed Feb 2026)
    "from ui.daisy_components import": "from ui.<module> import  (daisy_components decomposed)",
    "daisy_components": "focused ui/ modules (decomposed Feb 2026)",
    # Old component imports (components/ deleted Feb 2026)
    "from components.": "from ui.<domain>.views import  (components/ deleted)",
    # Feedback→Report rename (Mar 2026)
    "from core.services.feedback": "from core.services.report",
    "FeedbackService": "EntryReportService",
    # SubmissionReport→ExerciseReport→EntryReport rename (Mar 2026 → ADR-069 Jun 2026)
    "SubmissionReportService": "EntryReportService",
    "SubmissionReportOperations": "EntryReportOperations",
    "FeedbackRelationshipService": "ReportRelationshipService",
    "ProgressFeedbackGenerator": "ProgressReportGenerator",
    "ProgressFeedbackWorker": "ProgressReportWorker",
    "progress_feedback_worker": "progress_report_worker",
    "progress_feedback_generator": "progress_report_generator",
    # UserEntry collapse (ADR-054, April 2026) — SKUEL018
    "EntityType.EXERCISE_SUBMISSION": "EntityType.USER_ENTRY (pipeline=teacher_review)",
    "EntityType.JE_INPUT": "EntityType.USER_ENTRY (pipeline=transcribe_and_structure)",
    "EntityType.JE_OUTPUT": "EntityType.USER_ENTRY (produced via TRANSFORMS edge)",
    "NeoLabel.EXERCISE_SUBMISSION": "NeoLabel.USER_ENTRY",
    "NeoLabel.JE_INPUT": "NeoLabel.USER_ENTRY",
    "NeoLabel.JE_OUTPUT": "NeoLabel.USER_ENTRY",
    "ProcessorType": "Pipeline (core/models/enums/pipeline.py)",
    "JournalOutputService": "UserEntryProcessingService",
    "SubmissionsProcessingService": "UserEntryProcessingService",
    "from core.services.submissions": "from core.services.user_entry",
    "from core.services.journal": "from core.services.user_entry",
    "from core.models.submissions": "from core.models.user_entry",
    "from core.models.journal": "from core.models.user_entry",
    "from core.events.submission_events": "from core.events.learning_loop_events",
    "from core.events.journal_events": "from core.events.learning_loop_events",
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
    # Deleted public attributes
    "TasksService.analytics_engine": "removed — TaskKnowledgeAnalyzer now private in TasksIntelligenceService as self._knowledge_analyzer",
    "TasksService.ku_generation_service": "removed — now private as self._ku_generation_service",
    # Deleted classes / concepts
    "ProfileLayout": "deleted — use BasePage(page_type=PageType.CUSTOM)",
    "PageType.HUB": "deleted — sidebar pages use PageType.CUSTOM + SidebarPage",
    "PageHead": "deleted — use build_head() from ui.layouts.base_page",
    "PageLayout": "deleted — use BasePage",
    "SimplePageLayout": "deleted — use BasePage",
    "DrawerLayout": "deleted — use SidebarPage from ui.patterns.sidebar",
    "create_drawer_layout": "deleted — use SidebarPage from ui.patterns.sidebar",
    # Deleted directories referenced as import paths
    "core.models.ku.": "core/models/ku/ monolith deleted — use domain-specific paths",
    "components.tasks": "components/ deleted — use ui.tasks.views",
    "components.goals": "components/ deleted — use ui.goals.views",
    "components.habits": "components/ deleted — use ui.habits.views",
    "components.events": "components/ deleted — use ui.events.views",
    "components.choices": "components/ deleted — use ui.choices.views",
    "components.principles": "components/ deleted — use ui.principles.views",
}


def _boundary_pattern(key: str) -> re.Pattern[str]:
    """Compile a key with boundaries that block alphanumeric neighbors only.

    Prevents `PageHead` matching inside `PageHeader`, while underscore
    adjacency still matches so deleted snake_case names are caught inside
    derived symbols (`sel_routes` in `create_sel_routes`). Keys ending in a
    non-word character (`core.models.ku.`) keep prefix-matching.
    """
    prefix = r"(?<![A-Za-z0-9])" if key[0].isalnum() or key[0] == "_" else ""
    suffix = r"(?![A-Za-z0-9])" if key[-1].isalnum() or key[-1] == "_" else ""
    return re.compile(prefix + re.escape(key) + suffix)


_RENAMED_PATTERNS = {old: _boundary_pattern(old) for old in RENAMED}
_DELETED_PATTERNS = {old: _boundary_pattern(old) for old in DELETED}


# The scanner's own documentation necessarily names tracked identifiers as
# examples (sample output, the "What's tracked" table) — skip it to avoid
# permanent self-flagging noise.
SKIP_FILES = {ROOT / "docs" / "tools" / "HEALTH_CHECKS.md"}


def get_scan_targets() -> list[Path]:
    """Collect all .md files from SCAN_DIRS, minus SKIP_FILES."""
    result: list[Path] = []
    for target in SCAN_DIRS:
        if target.is_file() and target.suffix == ".md":
            result.append(target)
        elif target.is_dir():
            result.extend(sorted(target.rglob("*.md")))
    return [p for p in result if p not in SKIP_FILES]


def extract_code_segments(content: str) -> list[tuple[int, str]]:
    """
    Extract fenced code blocks and inline backtick spans.

    Returns list of (first_line_no, segment_text), ordered by position. ``segment_text``
    for a fenced block is its content lines joined by newlines, so a caller walking those
    lines gets true file coordinates from ``first_line_no + index``.

    Fence boundaries come from ``markdown_fences``, the CommonMark-backed walker shared
    with ``dead_doc_links.py``. The hand-written scanner this replaced closed a block on
    any line starting with the opener's first three characters, so ANY inner fence ended
    the outer one.

    The live shape is not the 4-backtick wrapper it is easiest to picture — there are
    none in this tree — but an equal-length inner fence carrying an info string: six
    lines across four documents, e.g. a ```` ```markwhen ```` sample inside a
    ```` ```markdown ```` block at ``docs/guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md:199``.
    Closing there did not merely truncate one block, it INVERTED the fence state for the
    rest of the document: code read as prose and prose read as code, 153 lines of prose
    scanned as code across three files.

    Two coordinate rules, both load-bearing and both previously wrong for fences:

      * A block is keyed by its first CONTENT line, not its opening delimiter. Keying by
        the delimiter reported every fenced hit one line early — 47 of 121 findings on the
        live tree at the time of the fix.
      * Delimiter lines belong to neither pass. They are not block content, and scanning
        them as prose would read an info string (```` ```KuType ````) as an inline span.

    Empty fences yield no segment — there is nothing to scan — but still suppress the
    inline pass across their span.
    """
    results: list[tuple[int, str]] = []
    fenced_lines: set[int] = set()

    for block in iter_code_fence_blocks(content):
        first, last = block.span
        fenced_lines.update(range(first, last + 1))
        if block.lines:
            results.append((block.lines[0][0], "\n".join(text for _n, text in block.lines)))

    # Inline backtick spans, only on lines no fence has claimed.
    for i, line in enumerate(content.splitlines(), 1):
        if i in fenced_lines:
            continue
        results.extend((i, match.group(1)) for match in re.finditer(r"`([^`\n]+)`", line))

    return sorted(results)


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

    for first_line, segment in segments:
        seg_lines = segment.splitlines() if "\n" in segment else [segment]

        # A block's content lines are contiguous, so the offset within the segment is
        # the offset within the file. This is only true because `extract_code_segments`
        # keys blocks by their first content line rather than their opening delimiter.
        for j, seg_line in enumerate(seg_lines):
            lineno = first_line + j

            for old, new in RENAMED.items():
                if _RENAMED_PATTERNS[old].search(seg_line):
                    issues.append((lineno, old, new, "renamed"))

            for deleted, reason in DELETED.items():
                if _DELETED_PATTERNS[deleted].search(seg_line):
                    issues.append((lineno, deleted, reason, "deleted"))

    return issues


def _sort_stale_name_issues(record: tuple[Path, int, str, str, str]) -> tuple[str, int]:
    """Sort stale name issues by source path then line number."""
    source, lineno, _, _, _ = record
    return str(source), lineno


def print_tables() -> None:
    """Print the full RENAMED and DELETED tables."""
    print(f"\n{Colors.BOLD}RENAMED identifiers ({len(RENAMED)}):{Colors.RESET}")
    for old, new in sorted(RENAMED.items()):
        print(f"  {Colors.RED}{old}{Colors.RESET} → {Colors.GREEN}{new}{Colors.RESET}")

    print(f"\n{Colors.BOLD}DELETED identifiers ({len(DELETED)}):{Colors.RESET}")
    for ident, reason in sorted(DELETED.items()):
        print(f"  {Colors.RED}{ident}{Colors.RESET}")
        print(f"      {Colors.CYAN}{reason}{Colors.RESET}")


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

    print(f"{Colors.BOLD}Stale Name Scanner{Colors.RESET}")
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
        print(
            f"{Colors.RED}{Colors.BOLD}Stale Names — {len(all_issues)} violations:{Colors.RESET}\n"
        )

        current_file = None
        for source, lineno, old, new, kind in sorted(all_issues, key=_sort_stale_name_issues):
            if source != current_file:
                print(f"\n  {Colors.BOLD}{source}{Colors.RESET}")
                current_file = source

            if kind == "renamed":
                print(
                    f"    {Colors.YELLOW}L{lineno:4d}{Colors.RESET}  {Colors.RED}{old}{Colors.RESET} → {Colors.GREEN}{new}{Colors.RESET}"
                )
            else:  # deleted
                print(
                    f"    {Colors.YELLOW}L{lineno:4d}{Colors.RESET}  {Colors.RED}[DELETED]{Colors.RESET} {Colors.RED}{old}{Colors.RESET}"
                )
                print(f"               {Colors.CYAN}reason: {new}{Colors.RESET}")

        print(f"\n{Colors.YELLOW}Total: {len(all_issues)} stale references{Colors.RESET}")
        print(
            f"\n{Colors.CYAN}Tip: Run with --list to see all tracked renamed/deleted identifiers{Colors.RESET}"
        )
        return 1
    else:
        print(f"{Colors.GREEN}✓ No stale names found{Colors.RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

# ── Archive of resolved renames ───────────────────────────────────────────────
# Once a rename has been fully applied to ALL code and docs and verified by this
# script reporting zero violations, move it here so it doesn't clutter the active
# RENAMED dict but is preserved for historical reference.
#
# (none yet — script introduced 2026-03-03)
