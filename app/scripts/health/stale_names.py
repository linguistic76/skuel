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

Two exemption tiers — each audited so an exemption that hides nothing is itself a
finding (SKUEL026 discipline):

  * ``ALLOWED_OCCURRENCES`` — a counted set of hits for one identifier at one line in
    one otherwise-scanned doc. The surgical tier: an ADR before/after table, a
    searchable import string, a frozen snippet inside a maintained migration guide.
    Anchored on line AND count, so a new stale mention (new line, or extra hit on the
    same line) is still reported.
  * ``SKIP_FILES`` — one whole file, the scanner's own documentation. Stays narrow.

There is deliberately no directory-scope exclusion: no subtree here is uniformly frozen
(migration guides get maintained and rename-swept), so blinding one wholesale would hide
real drift. Frozen snippets get occurrence-level allowances instead (Codex, PR #988).

Usage:
    uv run python scripts/health/stale_names.py
    uv run python scripts/health/stale_names.py --verbose
    uv run python scripts/health/stale_names.py --list   # Print the full RENAMED/DELETED tables
"""

import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

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
    # build_rich() parameter rename (Mar 2026). Deliberately NOT a bare "time_period="
    # key: only UserContextBuilder.build_rich() renamed the parameter — time_period is
    # still live elsewhere (the {time_period} placeholder in
    # core/prompts/templates/activity_feedback.md and its render examples, and
    # ProgressReportGenerator.generate(time_period=...)).
    # LIMITATION (Codex, PR #986): this is a best-effort single-line literal — the
    # per-line substring matcher cannot relate `build_rich(` and `time_period` across
    # keyword spellings (`user_uid=...`) or multiline calls, so those slip through.
    # Context-aware matching needs the scanner redesign tracked on #983.
    "build_rich(user_uid, time_period": "build_rich(user_uid, window",
    # Method renames (Submissions rename, Feb 2026)
    "list_reports": "list_submissions",
    "get_recent_reports": "get_recent_submissions",
    # Old module-level class rename (Privacy refactor, Mar 2026)
    "class Feedback(": "class EntryReport(",
    # Old import paths (post ku/ monolith dissolution, Feb 2026)
    "from core.models.ku.ku_enums import": "from core.models.enums.entity_enums import (or domain-specific enums file)",
    "from core.models.ku import": "from core.models.ku.ku import Ku / from core.models.ku.ku_dto import KuDTO (package __init__ does not re-export)",
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
    # (core/models/ku/ is a LIVE package — ku.py, ku_dto.py. Only the old ku_enums
    #  module is gone; the RENAMED "from core.models.ku.ku_enums import" rule covers it.)
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
#
# SKIP_FILES is a WHOLE-FILE blind spot and must stay narrow: exactly the one
# doc whose subject is the scanner itself. Its blast radius is audited by
# tests/unit/scripts/test_stale_names_suppression.py — every hidden hit must sit
# under a heading that documents the scanner. Do NOT add maintained docs here to
# force the count down; that is the "no suppressions to hit a number" anti-pattern
# (reverted in PR #986). Use ALLOWED_OCCURRENCES (below) for an intentional
# identifier in an otherwise-scanned doc.
#
# No directory-scope exclusion. An earlier cut excluded docs/migrations/ wholesale
# as a "frozen archive", but that premise is false: several migration guides are
# maintained and current-facing (NEO4J_GENAI_MIGRATION.md updates its class names to
# current; DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md was refreshed by an Aug-2026
# census, and rename campaigns like #867 sweep the subtree). A whole-subtree exclusion
# would blind a genuine rename in those, and its audit — "some hit somewhere in the
# tree" — could not tell (Codex, PR #988). Frozen before/after snippets inside those
# guides get occurrence-level allowances instead, each individually audited.
SKIP_FILES = {
    ROOT / "docs" / "tools" / "HEALTH_CHECKS.md",
}


class Allow(NamedTuple):
    """One audited intentional-mention grant: a rationale and how many hits it covers.

    ``hits`` is how many raw hits the anchored (line, identifier) legitimately has —
    almost always 1, but >1 when a single physical line names the identifier more than
    once (e.g. two inline-code spans). The scanner suppresses only ``hits`` of them at the
    anchor and reports any surplus, and the audit pins ``hits`` to the real number — so a
    newly-added same-line occurrence is both reported by the scanner AND fails the audit,
    instead of riding along under the grant (Codex, PR #988). Not named ``count``: that
    field would shadow the inherited ``tuple.count`` method.
    """

    why: str
    hits: int = 1


# ── Occurrence-level allowlist (audited, line-anchored, count-pinned) ─────────
# {relative_path: {(line_number, old_identifier): Allow(why, hits=1)}} — exempts a
# fixed number of hits at ONE line in one maintained doc. Every other line, every other
# identifier, and any hit beyond ``hits`` on the same line stays scanned. This is the
# surgical alternative to SKIP_FILES: it does not blind the whole file, and — because it
# anchors on the LINE and pins the COUNT — a genuinely-stale mention of an already-allowed
# identifier is still reported whether it lands on a different line or as an extra hit on
# the same line (Codex, PR #988: a bare (file, identifier) key would suppress both
# silently and the audit would stay green). ``line_number`` is the 1-based file line as
# this scanner reports it (run with --verbose to read it off).
#
# Use it for a doc that is otherwise current but MUST name a retired identifier at a
# specific place — an ADR's before/after table, TROUBLESHOOTING's verbatim
# import-error strings users search for, a doc that demonstrates this scanner, or a
# frozen before/after snippet inside a still-maintained migration guide.
#
# Every entry is audited (tests/unit/scripts/test_stale_names_allowed_occurrences.py):
# the file must be a live scan target, each (line, identifier) must raw-match at that
# exact line EXACTLY ``hits`` times (a moved line, wrong count, or dead entry is a
# finding, SKUEL026-style — and forces the anchor to be re-verified), and each must
# carry a rationale.
#
# Per-file rationales (shared by every entry in that file — the reason a given doc names
# retired identifiers is uniform within it: a changelog, a before/after table, a frozen
# migration record). Each was verified per-example against the doc, 2026-08 (#983).
_adr040 = "decision Context + struck-through withdrawn processor_type clause + amendment naming the retired ProcessorType (self-notes the scanner flags it)"
_adr041 = (
    "ADR-041 before/after record of the KuType/KuStatus -> EntityType/EntityStatus unification"
)
_adr042 = "ADR-042 records sharing extracted from SubmissionsSharingService into UnifiedSharingService -- the before-state"
_adr043 = (
    "decision-time bootstrap gating snapshot -- all three named services have since been renamed"
)
_adr054 = "ADR-054 before/after record of the ProcessorType/EXERCISE_SUBMISSION/JE_* -> UserEntry collapse"
_askesis_arch = "change-history table recording the entities_rich unification / ActivityDataReader absorption / ActivityReviewService split"
_askesis_intel = "'the former ActivityReviewService was split' -- historical record of the split"
_entity_arch = "'Pipeline and ReportSource (supersede ProcessorType)' explainer -- names the retired enum to document its replacement"
_freshness = "demonstrates this scanner by naming tracked (renamed/deleted) identifiers as examples"
_intel_index = "'KnowledgePatternAnalyzer generalized from AnalyticsEngine' -- provenance of the generalization"
_m2a = "'Methods moved from' provenance table -- names the source file the methods migrated from"
_m_actui = "migration record -- test snippets using KuStatus as it stood pre-EntityStatus rename"
_m_assign = "migration record -- __all__ export snapshot naming ProcessorType"
_m_backends = "migration record -- 'Files Modified'/'Why it stays' tables naming the pre-migration service files"
_m_domcfg = "migration record -- Before/After config blocks with KuStatus.COMPLETED.value pre-EntityStatus rename"
_m_health = "migration record -- enum inventory/table naming KuStatus pre-EntityStatus rename"
_m_lifepath = "migration record -- module inventory naming sel_routes.py (since deleted)"
_m_profile = "migration record -- narrates migrating off the legacy ProfileLayout"
_m_routecfg = (
    "migration record -- as-built 'Key Patterns' naming create_drawer_layout (since deleted)"
)
_m_selroutes = "migration record -- sel_routes.py / create_drawer_layout name the modules being migrated/deleted"
_m_selux = "migration record -- sel_routes verification/procedure commands from the migration"
_ref_ll = "learning-loop service table note: 'the former JournalOutputService was deleted'"
_skill_ll = "learning-loop historical-references index -- names retired identifiers to map them to successors"
_three_tier = (
    "'Key enum renames' record -- naming KuType/KuStatus is the historical record of the rename"
)
_trouble = "verbatim ui.daisy_components ImportError strings users search for -- the retired name is the lookup key"
_ui_comp = "'Evolution (2026-02-01)' note recording migration off the legacy ProfileLayout"

ALLOWED_OCCURRENCES: dict[str, dict[tuple[int, str], Allow]] = {
    ".claude/skills/learning-loop/SKILL.md": {
        (32, "ProcessorType"): Allow(_skill_ll),
        (44, "ProcessorType"): Allow(_skill_ll),
    },
    ".claude/skills/learning-loop/reference.md": {
        (741, "JournalOutputService"): Allow(_ref_ll),
    },
    "docs/TROUBLESHOOTING.md": {
        (132, "daisy_components"): Allow(_trouble, hits=2),
        (134, "daisy_components"): Allow(_trouble),
        (139, "daisy_components"): Allow(_trouble),
        (139, "from ui.daisy_components import"): Allow(_trouble),
    },
    "docs/architecture/ASKESIS_ARCHITECTURE.md": {
        (444, "activity_rich"): Allow(_askesis_arch),
        (445, "ActivityDataReader"): Allow(_askesis_arch),
        (446, "ActivityReviewService"): Allow(_askesis_arch),
    },
    "docs/architecture/ENTITY_TYPE_ARCHITECTURE.md": {
        (407, "ProcessorType"): Allow(_entity_arch),
        (416, "ProcessorType"): Allow(_entity_arch),
    },
    "docs/decisions/ADR-040-teacher-exercise-workflow.md": {
        (21, "ProcessorType"): Allow(_adr040),
        (24, "SubmissionsSharingService"): Allow(_adr040),
        (51, "ProcessorType"): Allow(_adr040),
        (56, "ProcessorType"): Allow(_adr040),
    },
    "docs/decisions/ADR-041-unified-ku-model.md": {
        (22, "KuStatus"): Allow(_adr041),
        (22, "KuType"): Allow(_adr041),
        (39, "KuStatus"): Allow(_adr041),
        (40, "KuStatus"): Allow(_adr041),
        (42, "KuStatus"): Allow(_adr041),
        (43, "KuStatus"): Allow(_adr041),
        (44, "KuStatus"): Allow(_adr041),
        (54, "KuStatus"): Allow(_adr041),
        (54, "KuType"): Allow(_adr041),
        (55, "KuStatus"): Allow(_adr041),
        (82, "KuStatus"): Allow(_adr041),
        (82, "KuType"): Allow(_adr041),
    },
    "docs/decisions/ADR-042-privacy-as-first-class-citizen.md": {
        (168, "SubmissionsSharingService"): Allow(_adr042),
        (248, "SubmissionsSharingService"): Allow(_adr042),
        (271, "submissions_sharing_service"): Allow(_adr042),
    },
    "docs/decisions/ADR-043-intelligence-tier-toggle.md": {
        (40, "JournalOutputService"): Allow(_adr043),
    },
    "docs/decisions/ADR-054-user-entry-unified-submissions.md": {
        # Re-anchored -2 (PR #1045): the execution note above lost 2 net lines when
        # its citation of two vanished plans/ files was removed.
        (100, "EntityType.EXERCISE_SUBMISSION"): Allow(_adr054),
        (100, "EntityType.JE_INPUT"): Allow(_adr054),
        (101, "EntityType.JE_OUTPUT"): Allow(_adr054),
        (140, "ProcessorType"): Allow(_adr054),
        (145, "ProcessorType"): Allow(_adr054),
        (148, "ProcessorType"): Allow(_adr054),
        (150, "ProcessorType"): Allow(_adr054),
        (306, "ProcessorType"): Allow(_adr054),
        (362, "ProcessorType"): Allow(_adr054),
        (413, "ProcessorType"): Allow(_adr054),
        (491, "EntityType.EXERCISE_SUBMISSION"): Allow(_adr054),
        (505, "ProcessorType"): Allow(_adr054),
    },
    "docs/intelligence/ASKESIS_INTELLIGENCE.md": {
        (361, "ActivityReviewService"): Allow(_askesis_intel),
    },
    "docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md": {
        # 503 → 505: the "## Quick Start" stub above it became "## Related Skills"
        # in the repo's 3-line form (2026-08-25). Anchor re-derived from the
        # scanner's own report, never by adding the diff's line delta.
        (505, "AnalyticsEngine"): Allow(_intel_index),
    },
    "docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md": {
        (283, "KuStatus"): Allow(_m_actui),
        (284, "KuStatus"): Allow(_m_actui),
        (288, "KuStatus"): Allow(_m_actui),
    },
    "docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md": {
        (31, "KuStatus"): Allow(_m_domcfg),
        (44, "KuStatus"): Allow(_m_domcfg),
        (156, "KuStatus"): Allow(_m_domcfg),
        (164, "KuStatus"): Allow(_m_domcfg),
        (284, "KuStatus"): Allow(_m_domcfg),
        (312, "KuStatus"): Allow(_m_domcfg),
    },
    "docs/migrations/DOMAIN_BACKENDS_POSITION_2_COMPLETE_2026-03-01.md": {
        (34, "submissions_sharing_service"): Allow(_m_backends),
        (58, "submissions_sharing_service"): Allow(_m_backends),
        (147, "progress_feedback_generator"): Allow(_m_backends),
        (148, "activity_review_service.py"): Allow(_m_backends),
        (159, "submissions_sharing_service"): Allow(_m_backends),
    },
    "docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md": {
        (714, "create_drawer_layout"): Allow(_m_routecfg),
        (767, "create_drawer_layout"): Allow(_m_routecfg),
        (885, "create_drawer_layout"): Allow(_m_routecfg),
        (907, "create_drawer_layout"): Allow(_m_routecfg),
    },
    "docs/migrations/LIFEPATH_DOCUMENTATION_UPDATES_2026-02-03.md": {
        (99, "sel_routes"): Allow(_m_lifepath),
        (110, "sel_routes"): Allow(_m_lifepath),
    },
    "docs/migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md": {
        (17, "ProfileLayout"): Allow(_m_profile),
        (59, "ProfileLayout"): Allow(_m_profile),
        (122, "ProfileLayout"): Allow(_m_profile),
    },
    "docs/migrations/SEL_ROUTES_MIGRATION_2026-02-03.md": {
        (34, "sel_routes"): Allow(_m_selroutes),
        (44, "sel_routes"): Allow(_m_selroutes),
        (71, "sel_routes"): Allow(_m_selroutes),
        (94, "sel_routes"): Allow(_m_selroutes),
        (99, "sel_routes"): Allow(_m_selroutes),
        (182, "create_drawer_layout"): Allow(_m_selroutes),
        (382, "sel_routes"): Allow(_m_selroutes),
        (385, "sel_routes"): Allow(_m_selroutes),
        (395, "sel_routes"): Allow(_m_selroutes),
        (401, "sel_routes"): Allow(_m_selroutes, hits=2),
    },
    "docs/migrations/SEL_UX_MODERNIZATION_2026-02-03.md": {
        (159, "sel_routes"): Allow(_m_selux),
        (218, "sel_routes"): Allow(_m_selux),
        (381, "sel_routes"): Allow(_m_selux, hits=2),
        (390, "sel_routes"): Allow(_m_selux),
    },
    "docs/migrations/assignments-refactoring-2026-01-25.md": {
        (62, "ProcessorType"): Allow(_m_assign),
    },
    "docs/migrations/health-score-enum-improvement-2026-01-25.md": {
        (135, "KuStatus"): Allow(_m_health),
        (200, "KuStatus"): Allow(_m_health),
    },
    "docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md": {
        (186, "submissions_sharing_service"): Allow(_m2a),
    },
    "docs/patterns/UI_COMPONENT_PATTERNS.md": {
        (66, "ProfileLayout"): Allow(_ui_comp),
    },
    "docs/patterns/three_tier_type_system.md": {
        # 949/950 → 947/948: the Key Files table above them lost its row for a
        # migration script that has never existed in this repo, and the
        # finance/automated-fixing prose shortened (B7, 2026-09-02). Anchors
        # re-derived from the scanner's report, never by adding the diff delta.
        (947, "KuType"): Allow(_three_tier),
        (948, "KuStatus"): Allow(_three_tier),
    },
    "docs/user-guides/documentation-freshness.md": {
        # 127/128 → 128/129: the health-command list above them gained a
        # `health-headings` line (2026-08-25). Anchors re-derived from the
        # scanner's report, never by adding the diff's line delta.
        (128, "KuTaskCreateRequest"): Allow(_freshness),
        (129, "ProfileLayout"): Allow(_freshness),
    },
}


def _allowed_count(rel_path: str, lineno: int, identifier: str) -> int:
    """How many hits at (``lineno``, ``identifier``) in ``rel_path`` are audited-intentional.

    0 when the occurrence is not allowlisted. The scanner suppresses only this many hits
    at the anchor and reports the rest. ``rel_path`` is the forward-slash path relative to
    ROOT (matches the ALLOWED_OCCURRENCES keys and the display path used elsewhere).
    """
    entry = ALLOWED_OCCURRENCES.get(rel_path, {}).get((lineno, identifier))
    return entry.hits if entry else 0


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
    where kind is "renamed" or "deleted". One tuple is emitted per MATCH, not per line:
    a line naming an identifier twice (``KuType = KuType`` in a fenced block, or two inline
    ```KuType``` spans) yields two tuples. Counting every match — via ``finditer``,
    not ``search`` — is what lets ALLOWED_OCCURRENCES pin a truthful per-line hit count, so a
    newly-added repeat on an already-allowed line is not silently absorbed (Codex, PR #988).
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
                issues.extend(
                    (lineno, old, new, "renamed")
                    for _match in _RENAMED_PATTERNS[old].finditer(seg_line)
                )

            for deleted, reason in DELETED.items():
                issues.extend(
                    (lineno, deleted, reason, "deleted")
                    for _match in _DELETED_PATTERNS[deleted].finditer(seg_line)
                )

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
    # Per-anchor suppression tally: an allowlisted (file, line, identifier) absorbs only
    # its audited COUNT of hits; a surplus hit on the same line is still reported.
    suppressed: Counter[tuple[str, int, str]] = Counter()

    for md_file in md_files:
        issues = scan_file(md_file)
        rel = md_file.relative_to(ROOT)
        for lineno, old, new, kind in issues:
            anchor = (str(rel), lineno, old)
            if suppressed[anchor] < _allowed_count(*anchor):
                suppressed[anchor] += 1  # audited intentional mention — see ALLOWED_OCCURRENCES
                continue
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
