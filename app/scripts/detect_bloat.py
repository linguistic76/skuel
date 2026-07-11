#!/usr/bin/env python3
"""
Bloat Detection — AST-sound dead-code analysis for SKUEL semantics.
===================================================================

Finds dead code that generic tools cannot express:

- Event lifecycle: events defined but never published, subscribed but never
  published, published but never subscribed (the publish/subscribe semantics
  live in SKUEL's event bus, not in Python's import graph).
- Service-method liveness (PR 2, pending): Vulture as the liveness engine,
  post-filtered through SKUEL dynamic-dispatch knowledge (route-factory
  templates, relationship-registry method names, dispatch tables).

Design rules (mirrors the SKUEL linter's structural-soundness discipline):

- AST only — no regex over source. Docstring examples are inert for free.
- No cross-file dataflow. An event constructed in one file and published from
  another is reported as UNVERIFIED ("constructed but publication not
  structurally traceable"), never as dead. A tool that lies is worse than none.
- Over-approximation is only allowed in the safe direction: it may suppress a
  dead-code accusation, never create one.
- No silent caps: everything the analysis could not resolve is counted and
  printed in the Limitations section.
- Unwired by intent is not bloat: staged work registered in PLANNED_EVENTS /
  PLANNED_METHODS reports in its own PLANNED tier — a visible completion
  to-do list that never fails --check. Stale markings (subject became live)
  are themselves reported.

Advisory by default (exit 0). ``--check`` exits 1 on surviving WARNING
findings — not wired into quality gates until the manual false-positive audit
passes (see the rewrite plan).

Usage:
    uv run python scripts/detect_bloat.py
    uv run python scripts/detect_bloat.py --events-only
    uv run python scripts/detect_bloat.py --methods-only
    uv run python scripts/detect_bloat.py --verbose --json
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Production code that confers liveness. tests/ is parsed separately and only
# ever contributes annotations ("published in tests"), never liveness.
FIRST_PARTY_ROOTS = ["core", "adapters", "api", "ui", "services_bootstrap", "main.py"]
EXCLUDED_PARTS = {"__pycache__", "archive"}

EVENTS_PACKAGE = ROOT / "core" / "events"
EVENT_ROOT_BASE = "BaseEvent"

# Exemptions require a documented reason (audit_route_security.py convention).
# Exempted findings are still printed, collapsed — never hidden.
EXEMPTED_EVENTS: dict[str, str] = {}
# Keyed "relative/path.py::method_name".
EXEMPTED_METHODS: dict[str, str] = {}

# Planned code: structurally dead TODAY, by intent — staged work awaiting its
# wiring, not abandonment. One Path Forward demands deleting abandoned code;
# staged work instead gets its own PLANNED tier here: still printed (it is a
# completion to-do list), never counted as dead, never fails --check. The
# reason must name what completes it. Entries whose subject becomes live are
# reported as stale and must be removed.
PLANNED_EVENTS: dict[str, str] = {
    # ADR-074 wired the curriculum embedding events through the
    # embedding_publisher chokepoint (Ku/PathStep/LearningPath via the
    # ingestion post-persist step + in-app creates; Exercise via
    # ExerciseService). ResourceEmbeddingRequested is structurally live via
    # the same chokepoint but has no producer that passes RESOURCE yet —
    # see the note on EMBEDDING_EVENT_TYPES in embedding_publisher.py.
    "HabitMissed": (
        "publish-side missed-habit detection never built; subscriber wiring in "
        "services_bootstrap/_event_wiring.py is intentional staging — wire a "
        "scheduler/cron detector that publishes it, or delete the chain"
    ),
    # Exercises dead-code campaign (2026-06): ADR-040 teacher-assignment
    # notification hook. Neither published nor subscribed — its sibling
    # ExerciseSubmitted was deleted (superseded by the live UserEntryCreated
    # after the ADR-054 UserEntry collapse), but the assignment-notification
    # moment ExerciseCreated marks has no live equivalent.
    "ExerciseCreated": (
        "teacher-assignment notification + calendar-integration hook staged "
        "(ADR-040) — publish side (notify group members + calendar due-date on "
        "exercise assignment) never built and no subscriber wired; same staged "
        "assignment-notification family as report.get_unsubmitted_exercises / "
        "review_queue.request_review — wire when the assignment-notification / "
        "Messaging surface lands, or delete the chain"
    ),
    # Campaign 18 (2026-06): events with subscribers but no publisher — staging
    "KnowledgeCreated": (
        "publish-side never built; subscribers wired in metrics_event_handler + "
        "_event_wiring — fire when a Ku or PS is created/ingested and downstream "
        "knowledge-tracking consumers need it, or delete the chain"
    ),
}
# Habits dead-code campaign (2026-06): staged habit capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_HABITS_DUE_TODAY = (
    "sole home of frequency-based due-ness — staged daily-planning capability; "
    "wire into daily planning/dashboard or delete the frequency lens"
)
_HABITS_SCHED_CREATE = (
    "scheduling-aware habit creation staged; wire a route/UI entry point that "
    "creates habits with capacity checks"
)
_HABITS_LIFECYCLE = (
    "habit lifecycle + reminder surface staged; wire routes/UI for pause/resume/"
    "archive/untrack, streak/progress/history, completion calendar, reminders"
)
_HABITS_BADGES = "completion bulk/badge/export surface staged; wire gamification and export routes"
_HABITS_ORCHESTRATION = (
    "goal/Ku/principle orchestration surface staged; wire link + skill routes "
    "or fold into relationship routes"
)
_HABITS_INSIGHTS = (
    "habit analytics/AI insight surface staged; wire an insights UI or Askesis consumer"
)
# Principles dead-code campaign (2026-06): staged principle capabilities kept
# by deliberate decision — each reason names the wiring that completes it.
_PRINCIPLES_EMBODIMENT = (
    "embodiment surface staged (post-create expression append, portfolio, integrity); "
    "wire an add-expression UI on the detail page — create-time expressions and the "
    "detail-page render are already live"
)
_PRINCIPLES_ASSESS = (
    "single-track self-assessment staged — the ONLY post-create writer of "
    "alignment_history, which the detail page already renders; wire an assess "
    "route/UI (dual-track check-ins live separately in dual_track_checkins)"
)
_PRINCIPLES_GRAVITY = (
    "goal/habit/Ku/choice link surface staged; wire link routes/UI or fold into relationship routes"
)
_PRINCIPLES_INSIGHTS = (
    "principle analytics/AI insight surface staged; wire an insights UI or Askesis consumer"
)
# Events dead-code campaign (2026-06): staged event capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_EVENTS_ATTENDEES = (
    "attendee surface staged (uid-based add/remove/list over (User)-[:HAS_EVENT]->(Event)); "
    "wire attendee routes/UI on the event detail page"
)
_EVENTS_ORCHESTRATION = (
    "goal/Ku/user link + context-aware create surface staged; create_event_with_context is "
    "the ONLY knowledge-practice-at-create writer (KnowledgePracticedInEvent); wire link "
    "routes/UI or fold into relationship routes"
)
_EVENTS_SCHEDULING = (
    "conflict-detection + recurring-instance-expansion surface staged; wire a conflict-check "
    "UI and a recurrence expansion route, or fold conflicts into "
    "CalendarOptimizationOrchestrator (cross-domain slot view)"
)
_HABIT_EVENT_AUTOMATION = (
    "bulk habit→event automation staged on the LIVE HabitEventScheduler (single-habit "
    "schedule_events_for_habit is routed via orchestration_routes.py); wire bulk-scheduling/"
    "routine/template routes or a scheduler cron"
)
# User dead-code campaign (2026-06): staged user-context capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_USER_PERCEPTION = (
    "ADR-030 cross-domain perception aggregator built (#262–#265) but never wired; "
    "wire a perception-insights panel (profile or Self Check-In page) consuming it"
)
_USER_PRINCIPLE_INTEGRATION = (
    "staged rich-context principle-integration read surface — the populator fills "
    "principle_guided_choice_counts/recent_principle_aligned_choices and SKUEL018 "
    "mandates these accessors as the read path; wire a profile/insights consumer"
)
# Choices dead-code campaign (2026-06): staged choice capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_CHOICES_GRAVITY = (
    "goal/habit/principle link surface staged; wire link routes/UI or fold into relationship routes"
)
_CHOICES_QUICK_METRICS = (
    "fast-path decision screening staged (ChoiceRelationships.fetch-based quick metrics, "
    "the LIVE get_decision_intelligence is the full typed-reader lens); wire a dashboard "
    "quick-view or batch complexity filter consuming it"
)
_CHOICES_OUTCOME = (
    "outcome-evaluation write path staged — ADR-066 designates it THE writer of "
    "satisfaction_score/actual_outcome/lessons_learned (rendered on the detail page; "
    "ChoiceOutcomeRecorded handler is live-subscribed); wire an evaluate route/form"
)
# Goals dead-code campaign (2026-06): staged goal capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_GOALS_GRAVITY = (
    "user/Ku/principle link surface staged (link_goal_to_habit is the LIVE essentiality "
    "write path); wire link routes/UI or fold into relationship routes"
)
_GOALS_SCHED_CREATE = (
    "scheduling-aware goal creation staged; wire a route/UI entry point that "
    "creates goals with capacity checks"
)
_GOALS_INSIGHTS = (
    "goal analytics/AI insight surface staged (feasibility, what-if scenarios, "
    "LLM strategy); wire an insights UI or Askesis consumer"
)
_GOAL_TASK_AUTOMATION = (
    "bulk goal→task automation staged on the LIVE GoalTaskGenerator (single-goal "
    "generate_tasks_for_goal is routed via orchestration_routes.py); wire bulk/"
    "critical-task/template routes or a planner cron"
)
# Tasks dead-code campaign (2026-06): staged task capabilities kept by
# deliberate decision — each reason names the wiring that completes it.
_TASKS_ASSIGNMENT = (
    "task-assignment surface staged — reads (Task)-[:ASSIGNED_TO]->(User); the writer "
    "assign_task_to_user (progress service + facade) is its staged dependency with no "
    "route/UI; wire assign/queue routes (teacher→student shape) or delete the surface"
)
_TASKS_BULK = (
    "bulk completion staged — sole publisher of TasksBulkCompleted, whose subscribers "
    "(metrics + task event handler) are live; wire a multi-select complete route/UI"
)
_TASKS_INSIGHTS = (
    "task analytics/AI insight surface staged; wire an insights UI or Askesis consumer"
)
_TASKS_KU_ORCHESTRATION = (
    "manual knowledge-generation trigger staged — the automatic TaskCompleted "
    "event-handler path is live; this variant returns curated results for review "
    "instead of auto-creating; wire an admin/review route"
)
_TASKS_DEPENDENCY_WRITE = (
    "task-dependency write path staged — the ONLY writer of (Task)-[:DEPENDS_ON]->(Task), "
    "which MEGA-QUERY task_dependencies and the gantt timeline read live (lateral routes "
    "write PREREQUISITE_FOR, not DEPENDS_ON); integration-tested with cache-invalidation "
    "events; wire a dependency UI on the task detail page"
)
_TASKS_GRAVITY = (
    "goal/Ku link surface staged (link_task_to_knowledge is the LIVE knowledge-edge "
    "write path); wire link routes/UI or fold into relationship routes"
)
_PS_SEMANTIC_DELETE = (
    "semantic-edge delete counterpart staged — the ADD path is LIVE (create_step_relationship "
    "route in path_steps_api.py + hierarchy_routes string-dispatch → add_semantic_relationship); "
    "wire a delete-step-relationship route for write-path symmetry"
)
_PS_SEMANTIC_INFER = (
    "transitive-inference lens staged (confidence-filtered reasoning chains over semantic "
    "edges); wire an explore/intelligence inference surface"
)
_PS_GUIDANCE = (
    "guidance-strength lens staged (principles 40% + choices 60% weighted score; backend "
    "fetch_guidance_counts stays); compose into get_domain_insights like the live "
    "practice_completeness lens, or a PS detail-page guidance indicator"
)
_LP_REVERSE_LOOKUP = (
    "LP reverse-lookup lens staged (full chain: service wrapper + protocol member + backend "
    "query, no live equivalent at LP grain); wire a goal-detail 'aligned learning paths' / "
    "ku-detail 'paths teaching this' consumer"
)
_DSL_EXTRACTION_PREVIEW = (
    "extraction preview lens staged — extract_and_create went live as the "
    "Pipeline.EXTRACT_ACTIVITIES branch (ADR-069 PR-1) but the no-create preview has no UI "
    "consumer yet; wire a 'preview what this entry would create' panel on the entry submit/"
    "detail page calling preview_extraction before the user commits to processing"
)
_LIFEPATH_WORD_ACTION = (
    "words-vs-actions integrity lens staged — the concept-defining LifePath check "
    "('Are you LIVING what you SAID?'): vision themes vs UserContext action themes, "
    "no live equivalent (the live 5-dimension alignment measures graph edges, not "
    "theme overlap); wire as the words-vs-actions panel on the /lifepath alignment "
    "dashboard next to the live dimension breakdown"
)
_REPORT_DAILY_PLANNING = (
    "assigned-work nag staged — 'exercises assigned via group with no submission yet, by due "
    "date' is a daily-planning signal in the same family as the daily-plan phantom-dispatch "
    "repair thread; wire when that cross-domain repair lands (Mike ruled PLANNED 2026-06-12)"
)
_REPORT_COMPLETION_STATS = (
    "learning-loop completion-rate read surface staged — submissions with/without reports + "
    "total reports received over REPORT_FOR edges; wire a progress/dashboard consumer "
    "(Mike ruled PLANNED 2026-06-12)"
)
_REPORT_EXERCISE_CHAIN = (
    "exercise-rooted loop traversal staged — teacher/admin 'everything chained to this "
    "Exercise' (submissions, reports, revised exercises); the entry-rooted twin "
    "get_submission_chain is now wired live (ADR-069 PR-3), this one awaits a teaching-UI "
    "exercise detail view (Mike ruled PLANNED 2026-06-12)"
)
_REPORT_SCHEDULE_PRODUCER = (
    "missing producer of a LIVE consumer — ProgressReportWorker starts at bootstrap "
    "(scripts/dev/bootstrap.py) and polls get_due_schedules, but no route creates/manages "
    "ReportSchedule nodes, so the loop polls an eternally-empty table; wire a report-schedule "
    "settings route/UI to complete the periodic ActivityReport feature (ADR-069 §3)"
)
_REPORT_PRIVACY_AUDIT = (
    "privacy-transparency surface staged — per-user audit of admin snapshots, shares granted, "
    "and report schedule; the producer side (ActivitySnapshotAccessed audit events) already "
    "publishes; wire a /privacy route + UI per the security posture "
    "(Mike ruled PLANNED 2026-06-12)"
)
_REVIEW_REQUEST_PRODUCER = (
    "missing producer of a LIVE consumer — the admin activity-review queue page "
    "(activity_review_ui.py → get_pending_reviews) ships and reads an eternally-empty queue "
    "because no user-facing route calls request_review; wire a 'request a review' "
    "button/route to complete the loop (ADR-069 §3)"
)
_SHARING_MANAGEMENT = (
    "sharing-management surface staged — the unwired half of UnifiedSharingService (ADR-038): "
    "the create/check half is LIVE and wired (share, check_access, get_shared_with_me, "
    "share_with_group, get_user_entries_shared_with_group all have routes/UI), but the "
    "revoke / visibility-ladder / 'who is this shared with' management half was never wired. "
    "No superseded loser — each is the unwired inverse or owner-view twin of a live op. "
    "Wire a sharing-management panel on entity detail pages (revoke button, "
    "PRIVATE→SHARED→TEAM→PUBLIC visibility selector, 'shared with' list) "
    "(Mike ruled PLANNED 2026-06-13)"
)
# Relationships dead-code campaign (2026-06-13): staged relationship capabilities
# kept by deliberate decision — each reason names the wiring that completes it.
_RELATIONSHIPS_DAILY_PLANNING = (
    "generic UserContext planning surface on UnifiedRelationshipService — "
    "get_blocked_for_user has no live caller after the phantom-dispatch repair "
    "(the facade services now supply domain-specific planning methods directly); "
    "wire a cross-domain blocked-item surface or delete (Mike ruled PLANNED 2026-06-13)"
)
_RELATIONSHIPS_HIERARCHY = (
    "curriculum multi-hop hierarchy traversal staged (universal hierarchical "
    "pattern) — OrderedRelationshipsMixin is mixed into UnifiedRelationshipService "
    "and the backend impls (get_hierarchical_children_single/two_level/deep) are "
    "live, but no caller invokes the service entry point; wire a curriculum "
    "tree/hierarchy explorer consumer (Mike ruled PLANNED 2026-06-13)"
)
_RELATIONSHIPS_EXISTS = (
    "generic relationship existence-check staged — config-keyed has-any-related "
    "boolean (sibling of the live count_related / get_related_uids); integration-"
    "tested on live Neo4j (LP relationships) but no production caller; wire where "
    "a cheap exists check beats loading UIDs, or fold into the domain relationship "
    "containers (Mike ruled PLANNED 2026-06-13)"
)
# Askesis dead-code campaign (2026-06-13): Askesis is a LIVE subsystem (the
# answer_user_question conversation pipeline is wired to /api/askesis/ask and
# /askesis/api/submit), but its instance-persistence/management layer and several
# AI/citation/context lenses were never wired. Flagship-maintained direction
# (feedback: Askesis = ZPD-aware companion) — staged, not deleted.
_ASKESIS_INSTANCE_MANAGEMENT = (
    "askesis instance persistence/management surface staged — the live conversation "
    "flow only uses get_or_create_for_user (auto-create) + in-memory ConversationContext; "
    "the explicit-create (configured AskesisCreateRequest), settings-update, delete, "
    "multi-instance listing, and conversation-metrics-persist half was never wired. "
    "No superseded loser — these back the placeholder /askesis/settings form (no persist), "
    "/askesis/history, and /askesis/analytics ('coming soon') UIs. Wire settings "
    "persistence + conversation-history/analytics consumers (Mike ruled PLANNED 2026-06-13)"
)
_ASKESIS_CITATION_QUALITY = (
    "askesis citation-quality lens staged — the live citation path is "
    "format_citations_for_askesis → get_citations_for_knowledge_unit (query_processor); "
    "the evidence-count-filtered 'well-supported' selector and the citation-quality "
    "analyzer are unwired lenses over that live bundle with no caller; wire a "
    "citation-quality display / 'well-supported sources' filter (Mike ruled PLANNED 2026-06-13)"
)
_ASKESIS_CONTEXT_ORCHESTRATION = (
    "askesis context-orchestration surface staged — load_askesis_context centralises the "
    "get_askesis → get_rich_unified_context bundle (AskesisContext) for instance-aware "
    "intelligence API routes that were never wired (the live pipeline loads UserContext "
    "inline, instance-free), and find_relevant_from_user_context is the unwired "
    "UserContext→relevant-KU discovery entry point; wire instance-aware intelligence "
    "routes + a 'relevant knowledge for you' recommendation (Mike ruled PLANNED 2026-06-13)"
)
# Shared BaseService-mixin dead-code campaign (2026-06-13, campaign 16): the 6
# common mixins (ConversionHelpers, CRUD, Search, Relationships, TimeQuery,
# Context) are inherited by all domains, so a flagged base-mixin method is
# genuinely uncalled across every inheritor (Vulture name-collision would have
# masked any same-named call). Two pure-plumbing helpers were DELETED (live
# winners exist: inline None-guard / standalone from_domain_model fn); these
# three are feature-shaped surfaces with no superseded loser.
# Chain builders on phantom edges (Mike ruled PLANNED, not delete, 2026-07-10).
_PHANTOM_EDGE_CHAIN_BUILDERS = (
    "caller-less dependency-chain query builder (export lists only) built on "
    "phantom edge vocabulary: REQUIRES between Principles/Habits plus the "
    "user-scoped filter edges ADHERES_TO (User→Principle) and PRACTICES "
    "(User→Habit) — none of these are in RelationshipName and none has a "
    "writer anywhere (2026-07 writer audits; PRACTICES Event→Ku remapped in "
    "#586, these User-scoped reads are the separate shape). Completing this "
    "requires real edge vocabulary FIRST (register the edges + build write "
    "paths), then wire a dependency-chain surface on the detail pages"
)

_MIXIN_PREREQUISITE_WRITE = (
    "config-driven prerequisite-write half staged — the write twin of the LIVE "
    "get_prerequisites/get_enables read pair (PsService + GraphQL curriculum "
    "traversal, both read via the domain's _prerequisite_relationships config). "
    "No superseded loser: add_relationship is the primitive it composes, and the "
    "lateral create_lateral_relationship writes a route-chosen RelationshipName, "
    "not via the domain prereq config; live prereq edges currently come only from "
    "ingestion (Edge YAML). Wire a prerequisite-edit control on entity detail "
    "pages (Mike ruled PLANNED 2026-06-13)"
)
_MIXIN_GENERIC_HIERARCHY = (
    "generic parents/children hierarchy read staged — the base-mixin entry point "
    "over backend.hierarchy_query_raw (whose only caller is this method); the "
    "per-domain get_*_hierarchy methods use the richer get_hierarchy_raw and are "
    "themselves PLANNED, and campaign-14's get_hierarchical_children is the "
    "curriculum multi-hop twin. No live consumer of either; wire a hierarchy "
    "explorer/breadcrumb consuming the unified surface (Mike ruled PLANNED 2026-06-13)"
)
_MIXIN_ARRAY_SEARCH = (
    "generic array-field search staged — the 'any array field contains value' "
    "generalization of the live search_by_tags (which covers the tags case); no "
    "production caller, in the same unwired-search-surface family as the PLANNED "
    "intelligent_search NL entry point. Wire a faceted array-field filter or fold "
    "into the search box (Mike ruled PLANNED 2026-06-13)"
)
# Exercises dead-code campaign (2026-06, campaign 17): teacher-management half
# of the exercise lifecycle. delete_exercise was DELETED (superseded by the
# generic CRUDRouteFactory delete route → ownership-verified service.delete_for_user),
# but these two have no live winner — the live exercise-listing family
# (get_student_exercises*) is a STUDENT view, and no route archives an exercise.
_EXERCISES_GROUP_LISTING = (
    "teacher group-roster listing staged — 'all ASSIGNED exercises for a group' "
    "(find_by group_uid, scope='assigned'); the live get_student_exercises / "
    "get_student_exercises_with_status family is the STUDENT view (a learner's "
    "exercises across their groups, via MEMBER_OF + SHARED_WITH_GROUP), a "
    "different job with no superseded loser. Wire a teacher group-detail "
    "exercises panel consuming it (Mike ruled PLANNED 2026-06-13)"
)
_EXERCISES_ARCHIVE = (
    "exercise archive soft-delete staged — writes status='archived'; the live "
    "delete path is the generic ownership-verified hard delete (CRUDRouteFactory "
    "→ service.delete_for_user) and ExerciseUpdateRequest carries no status field "
    "(only is_active), so no live route reaches archiving. Wire an archive/restore "
    "control on the exercise detail page (Mike ruled PLANNED 2026-06-13)"
)
# Keyed "relative/path.py::method_name".
# NOTE (ADR-075): AgentSession.call / AgentChannelRegistry.get were PLANNED here
# between B2 and B3; the detector stopped flagging them (test coverage + name
# collisions), so the markings went stale and were removed per its convention.
# Their production consumer is still B4's LocalAgentVaultAdapter.
PLANNED_METHODS: dict[str, str] = {
    # --- Shared BaseService mixins (campaign 16) ---
    "core/services/mixins/relationship_operations_mixin.py::add_prerequisite": (
        _MIXIN_PREREQUISITE_WRITE
    ),
    "core/services/mixins/relationship_operations_mixin.py::get_hierarchy": (
        _MIXIN_GENERIC_HIERARCHY
    ),
    "core/services/mixins/search_operations_mixin.py::search_array_field": _MIXIN_ARRAY_SEARCH,
    # --- Exercises: teacher-management half (campaign 17) ---
    "core/services/exercises/exercise_service.py::list_group_exercises": (_EXERCISES_GROUP_LISTING),
    "core/services/exercises/exercise_service.py::deactivate_exercise": _EXERCISES_ARCHIVE,
    # --- Habits: due-today machinery (get_all_habits_due_today + by_frequency remain unwired
    # — admin/scheduler scope, not per-user API) ---
    "core/services/habits_service.py::get_all_habits_due_today": _HABITS_DUE_TODAY,
    "core/services/habits_service.py::get_habits_by_frequency": _HABITS_DUE_TODAY,
    # --- Habits: scheduling-aware creation ---
    "core/services/habits_service.py::create_habit_with_scheduling_context": (_HABITS_SCHED_CREATE),
    "core/services/habits_service.py::create_habit_with_learning_scheduling_context": (
        _HABITS_SCHED_CREATE
    ),
    # --- Habits: goal/Ku orchestration ---
    "core/services/habits/_orchestration_mixin.py::complete_with_goal_impacts": (
        _HABITS_ORCHESTRATION
    ),
    "core/services/habits/_orchestration_mixin.py::create_with_goal_links": (_HABITS_ORCHESTRATION),
    "core/services/habits/_orchestration_mixin.py::create_user_habit_relationship": (
        _HABITS_ORCHESTRATION
    ),
    "core/services/habits/_orchestration_mixin.py::get_skills_developed_by_habits": (
        _HABITS_ORCHESTRATION
    ),
    "core/services/habits/_orchestration_mixin.py::create_semantic_skill_relationship": (
        _HABITS_ORCHESTRATION
    ),
    "core/services/habits/_orchestration_mixin.py::find_habits_developing_knowledge": (
        _HABITS_ORCHESTRATION
    ),
    # --- Habits: analytics / AI insights ---
    "core/services/habits/_enrichment_mixin.py::get_habits_summary_analytics": (_HABITS_INSIGHTS),
    "core/services/habits/_enrichment_mixin.py::get_habit_trends": _HABITS_INSIGHTS,
    "core/services/habits/_enrichment_mixin.py::get_enriched_learning_summary": (_HABITS_INSIGHTS),
    "core/services/habits/_enrichment_mixin.py::get_enriched_curriculum_metadata": (
        _HABITS_INSIGHTS
    ),
    "core/services/habits/_enrichment_mixin.py::get_enriched_prerequisite_metadata": (
        _HABITS_INSIGHTS
    ),
    # analyze_patterns went LIVE 2026-06-10: /habits/insights-fragment on the habit detail page
    "core/services/habits/habits_search_service.py::get_needing_attention": _HABITS_INSIGHTS,
    "core/services/habits/habits_search_service.py::get_at_risk": _HABITS_INSIGHTS,
    # --- Principles: single-track alignment self-assessment ---
    "core/services/principles/principles_alignment_service.py::assess_with_user_input": (
        _PRINCIPLES_ASSESS
    ),
    # --- Principles: gravity / cross-domain link surface ---
    "core/services/principles/_gravity_mixin.py::create_user_principle_relationship": (
        _PRINCIPLES_GRAVITY
    ),
    # --- Principles: analytics / AI insights ---
    "core/services/principles/_enrichment_mixin.py::get_analytics_summary": (_PRINCIPLES_INSIGHTS),
    # --- Events: attendee surface ---
    "core/services/events/_orchestration_mixin.py::get_event_attendees": _EVENTS_ATTENDEES,
    "core/services/events/_orchestration_mixin.py::add_attendee": _EVENTS_ATTENDEES,
    "core/services/events/_orchestration_mixin.py::remove_attendee": _EVENTS_ATTENDEES,
    # --- Events: cross-domain link / context-aware create ---
    "core/services/events/_orchestration_mixin.py::create_user_event_relationship": (
        _EVENTS_ORCHESTRATION
    ),
    "core/services/events/_orchestration_mixin.py::link_event_to_knowledge": (
        _EVENTS_ORCHESTRATION
    ),
    "core/services/events/_orchestration_mixin.py::create_event_with_context": (
        _EVENTS_ORCHESTRATION
    ),
    # --- Events: conflict detection + recurring instances ---
    "core/services/events/_scheduling_mixin.py::check_conflicts": _EVENTS_SCHEDULING,
    "core/services/events/_scheduling_mixin.py::create_recurring_instances": (_EVENTS_SCHEDULING),
    "core/services/events/events_search_service.py::get_conflicting": _EVENTS_SCHEDULING,
    # --- Events: bulk habit→event automation ---
    "core/services/habit_event_scheduler.py::schedule_events_for_all_habits": (
        _HABIT_EVENT_AUTOMATION
    ),
    "core/services/habit_event_scheduler.py::schedule_streak_maintenance": (
        _HABIT_EVENT_AUTOMATION
    ),
    "core/services/habit_event_scheduler.py::create_habit_routine": _HABIT_EVENT_AUTOMATION,
    "core/services/habit_event_scheduler.py::get_event_templates": _HABIT_EVENT_AUTOMATION,
    # --- User: cross-domain perception aggregator (ADR-030) ---
    "core/services/user/intelligence/perception_intelligence.py::get_cross_domain_perception_analysis": (  # noqa: E501
        _USER_PERCEPTION
    ),
    # --- User: rich-context principle-integration read surface ---
    "core/services/user/unified_user_context.py::principle_guided_choice_counts_or_empty": (
        _USER_PRINCIPLE_INTEGRATION
    ),
    "core/services/user/unified_user_context.py::recent_principle_aligned_choices_or_empty": (
        _USER_PRINCIPLE_INTEGRATION
    ),
    # --- Choices: gravity links (inlined from _relationship_mixin into facade) ---
    "core/services/choices_service.py::link_choice_to_habit": _CHOICES_GRAVITY,
    "core/services/choices_service.py::create_semantic_choice_relationship": _CHOICES_GRAVITY,
    # --- Choices: fast-path decision screening ---
    "core/services/choices/_analytics_mixin.py::get_quick_decision_metrics": (
        _CHOICES_QUICK_METRICS
    ),
    "core/services/choices/_analytics_mixin.py::batch_analyze_decision_complexity": (
        _CHOICES_QUICK_METRICS
    ),
    # --- Choices: outcome evaluation write path ---
    "core/services/choices/choices_core_service.py::evaluate_choice_outcome": _CHOICES_OUTCOME,
    # --- Goals: gravity links (inlined from _relationship_mixin into facade) ---
    "core/services/goals_service.py::create_user_goal_relationship": _GOALS_GRAVITY,
    "core/services/goals_service.py::create_semantic_goal_relationship": _GOALS_GRAVITY,
    "core/services/goals_service.py::unlink_goal_from_habit": _GOALS_GRAVITY,
    # --- Goals: analytics/AI insight surface ---
    "core/services/goals/_orchestration_mixin.py::assess_goal_feasibility": _GOALS_INSIGHTS,
    "core/services/goals/_predictive_mixin.py::run_scenario_analysis": _GOALS_INSIGHTS,
    # suggest_achievement_strategy wired: GET /api/goals/ai/strategy (Theme F)
    # --- Goals: bulk goal→task automation (LIVE GoalTaskGenerator) ---
    "core/services/goal_task_generator.py::get_task_templates": _GOAL_TASK_AUTOMATION,
    # --- Tasks: assignment surface ---
    "core/services/tasks/tasks_search_service.py::get_user_assigned_tasks": _TASKS_ASSIGNMENT,
    # --- Tasks: bulk completion ---
    "core/services/tasks/tasks_core_service.py::complete_tasks_bulk": _TASKS_BULK,
    # --- Tasks: analytics/AI insight surface ---
    "core/services/tasks/_analytics_mixin.py::get_behavioral_insights": _TASKS_INSIGHTS,
    # generate_task_breakdown wired: GET /api/tasks/ai/breakdown (Theme F)
    # suggest_priority wired: GET /api/tasks/ai/priority-suggestion (Theme F)
    "core/services/tasks/_orchestration_mixin.py::analyze_task_knowledge_impact": (_TASKS_INSIGHTS),
    # --- Tasks: manual knowledge-generation trigger ---
    "core/services/tasks/_orchestration_mixin.py::trigger_manual_knowledge_generation": (
        _TASKS_KU_ORCHESTRATION
    ),
    # --- Tasks: dependency write path + gravity links (inlined into facade) ---
    "core/services/tasks_service.py::create_task_dependency": _TASKS_DEPENDENCY_WRITE,
    "core/services/tasks_service.py::create_semantic_knowledge_relationship": _TASKS_GRAVITY,
    # --- PS: semantic write-path symmetry + inference lens ---
    "core/services/ps/ps_semantic_service.py::remove_semantic_relationship": (_PS_SEMANTIC_DELETE),
    "core/services/ps/ps_semantic_service.py::infer_relationships": _PS_SEMANTIC_INFER,
    # --- PS: guidance-strength intelligence lens ---
    "core/services/ps/ps_intelligence_service.py::calculate_guidance_strength": _PS_GUIDANCE,
    # --- LP: reverse-lookup search lenses ---
    "core/services/lp/lp_search_service.py::get_aligned_with_goal": _LP_REVERSE_LOOKUP,
    "core/services/lp/lp_search_service.py::get_by_knowledge": _LP_REVERSE_LOOKUP,
    # --- DSL: extraction preview lens (pipeline itself went live in ADR-069 PR-1) ---
    "core/services/dsl/activity_extractor.py::preview_extraction": _DSL_EXTRACTION_PREVIEW,
    # --- LifePath: word-action alignment lens ---
    "core/services/lifepath/lifepath_service.py::check_word_action_alignment": (
        _LIFEPATH_WORD_ACTION
    ),
    "core/services/lifepath/lifepath_types.py::biggest_gap": _LIFEPATH_WORD_ACTION,
    "core/services/lifepath/lifepath_types.py::get_gap_summary": _LIFEPATH_WORD_ACTION,
    # NOTE: get_pending_submissions + get_submission_chain were wired live in
    # ADR-069 PR-3 (journal responses) — removed from PLANNED_METHODS.
    # --- Reports: staged intelligence lenses ---
    "core/services/report/report_relationship_service.py::get_unsubmitted_exercises": (
        _REPORT_DAILY_PLANNING
    ),
    "core/services/report/report_relationship_service.py::get_report_summary": (
        _REPORT_COMPLETION_STATS
    ),
    "core/services/report/report_relationship_service.py::get_learning_loop_chain": (
        _REPORT_EXERCISE_CHAIN
    ),
    # --- Reports: missing producers of live consumers ---
    "core/services/report/progress_schedule_service.py::create_schedule": (
        _REPORT_SCHEDULE_PRODUCER
    ),
    "core/services/report/progress_schedule_service.py::get_user_schedule": (
        _REPORT_SCHEDULE_PRODUCER
    ),
    "core/services/report/progress_schedule_service.py::deactivate_schedule": (
        _REPORT_SCHEDULE_PRODUCER
    ),
    "core/services/report/review_queue_service.py::request_review": _REVIEW_REQUEST_PRODUCER,
    # --- Sharing: revoke / visibility-ladder / management-view surface (ADR-038) ---
    "core/services/sharing/unified_sharing_service.py::unshare": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::set_visibility": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::verify_shareable": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::get_shared_with": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::unshare_from_group": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::get_groups_shared_with": _SHARING_MANAGEMENT,
    "core/services/sharing/unified_sharing_service.py::get_shared_with_me_via_groups": (
        _SHARING_MANAGEMENT
    ),
    # --- Reports: privacy-transparency surface ---
    "core/services/report/activity_report_service.py::get_privacy_summary": (_REPORT_PRIVACY_AUDIT),
    # --- Relationships: generic UserContext planning surface ---
    # get_blocked_for_user: no live caller after phantom-dispatch repair (keep PLANNED)
    "core/services/relationships/unified_relationship_service.py::get_blocked_for_user": (
        _RELATIONSHIPS_DAILY_PLANNING
    ),
    # --- Relationships: curriculum multi-hop hierarchy traversal ---
    "core/services/relationships/_ordered_relationships_mixin.py::get_hierarchical_children": (
        _RELATIONSHIPS_HIERARCHY
    ),
    # --- Relationships: generic relationship existence-check ---
    "core/services/relationships/unified_relationship_service.py::has_relationship": (
        _RELATIONSHIPS_EXISTS
    ),
    # --- Askesis: instance persistence/management surface ---
    "core/services/askesis/askesis_core_service.py::create_askesis": (_ASKESIS_INSTANCE_MANAGEMENT),
    "core/services/askesis/askesis_core_service.py::update_askesis": (_ASKESIS_INSTANCE_MANAGEMENT),
    "core/services/askesis/askesis_core_service.py::delete_askesis": (_ASKESIS_INSTANCE_MANAGEMENT),
    "core/services/askesis/askesis_core_service.py::list_user_instances": (
        _ASKESIS_INSTANCE_MANAGEMENT
    ),
    "core/services/askesis/askesis_core_service.py::record_conversation": (
        _ASKESIS_INSTANCE_MANAGEMENT
    ),
    # --- Askesis: citation-quality lenses ---
    "core/services/askesis_citation_service.py::get_well_supported_citations": (
        _ASKESIS_CITATION_QUALITY
    ),
    "core/services/askesis_citation_service.py::analyze_citation_quality": (
        _ASKESIS_CITATION_QUALITY
    ),
    # --- Askesis: context-orchestration surface ---
    "core/services/askesis_service.py::load_askesis_context": _ASKESIS_CONTEXT_ORCHESTRATION,
    "core/services/askesis_service.py::find_relevant_from_user_context": (
        _ASKESIS_CONTEXT_ORCHESTRATION
    ),
    # --- Campaign 18 (2026-06): standalone service staged capabilities ---
    "core/services/content_enrichment_service.py::process_audio": (
        "audio transcription pipeline staged — wire a /upload-audio route that "
        "accepts an audio file, calls process_audio, then routes the transcript "
        "through the UserEntry pipeline (ADR-054)"
    ),
    "core/services/content_enrichment_service.py::create_instruction_set": (
        "instruction-set management write path — pair with list_instruction_sets "
        "and wire an admin UI/API once the instruction-set editing surface lands"
    ),
    "core/services/content_enrichment_service.py::list_instruction_sets": (
        "instruction-set management read path — see create_instruction_set"
    ),
    "core/services/embeddings_service.py::calculate_similarity": (
        "cosine similarity utility with test coverage; no production caller yet — "
        "wire into a similarity-comparison route or search re-ranking when needed"
    ),
    "core/services/embeddings_service.py::check_version_compatibility": (
        "per-node embedding-version diagnostic; lost its one production caller when "
        "get_or_create_embedding folded onto verify_fresh_embeddings (ADR-074 §8) — "
        "test-covered; wire into an admin embedding-health surface, or delete if "
        "check_embedding_versions.py-style batch queries stay the only diagnostic path"
    ),
    "core/services/embeddings_service.py::get_or_create_embedding": (
        "embedding with idempotent caching on THE hash-based skip decision "
        "(verify_fresh_embeddings — version current + text-hash match, ADR-074 §8); "
        "test-covered but not wired in production — wire into bulk-embed or "
        "on-demand embed routes"
    ),
    "core/services/embeddings_service.py::stamp_embedding_hashes": (
        "NOT staged — LIVE, but its only caller is scripts/generate_embeddings_batch.py "
        "--stamp-hashes (ADR-074 §8 one-shot hash rollout), and scripts/ sits outside the "
        "scanner's production roots by design; registry entry keeps the gate honest instead "
        "of widening the roots for one method"
    ),
    "core/services/ingestion/reference_ingestion.py::ingest_book": (
        "NOT staged — LIVE, but its only caller is scripts/ingest_canon_book.py "
        "(the canon Phase-2 admin ingest door), and scripts/ sits outside the scanner's "
        "production roots by design; registry entry keeps the gate honest instead of "
        "widening the roots for one method. Becomes an in-app caller when a canon "
        "management route/UI is built (Phase 3+)"
    ),
    "core/services/entity_inference_service.py::_infer_from_content": (
        "private helper for the inference pipeline — becomes live when "
        "get_inference_statistics / analyze_inference_confidence are wired"
    ),
    "core/services/entity_inference_service.py::get_inference_statistics": (
        "inference stats surface — wire into an admin/debug route to expose "
        "inference accuracy and throughput metrics"
    ),
    "core/services/entity_inference_service.py::analyze_inference_confidence": (
        "confidence analysis surface — wire into the inference result detail "
        "view or a teacher-facing confidence dashboard"
    ),
    "core/services/zpd/zpd_service.py::get_proximal_ku_uids": (
        "lightweight ranked-proximal-Kus wrapper over assess_zone — the "
        "/explore/next-step/related fragment (its once-destined consumer) ended "
        "up on assess_zone directly because it also needs current_zone to filter "
        "engaged Kus out of the hint chips; this wrapper stays staged for a "
        "consumer that needs ONLY the ranked list"
    ),
    "core/services/zpd/zpd_service.py::get_readiness_score": (
        "ZPD readiness score for a specific Ku — wire into the PS detail page "
        "or the prerequisite-checker surface when per-Ku readiness is needed"
    ),
    # NOT registrable: core/services/askesis_service.py::analyze_user_state has
    # zero external callers (hand-verified 2026-07-10, PR 5 discovery-analytics
    # arc) but shares its name with the LIVE UserStateAnalyzer.analyze_user_state
    # it delegates to, so the name-based reference scan sees it as live — a
    # registry entry here would only fire planned-marking-stale. Staged, not
    # superseded (deletion-campaign protocol): it's the Askesis pre-answer
    # state-snapshot facade awaiting its pipeline consumer.
    # Restored from campaign-18 deletion — test-covered, no production caller
    # (find_similar_to_node graduated 2026-07-10: consumed by find_related_concepts
    # → the /explore/{ku,ps}/{uid}/related "Related concepts" fragments)
    "core/services/neo4j_vector_search_service.py::find_cross_domain_similar": (
        "cross-domain vector similarity across multiple labels in one call; "
        "integration test coverage in test_vector_search.py + test_embedding_fixtures_usage.py; "
        "wire into a cross-domain search route when the multi-domain surface lands"
    ),
    "core/services/neo4j_vector_search_service.py::find_similar_by_text_with_metrics": (
        "find_similar_by_text wrapper that captures SearchMetrics; full integration "
        "test coverage in test_search_metrics_tracking.py; wire when metrics "
        "collection is needed on the vector search path"
    ),
    "core/services/neo4j_vector_search_service.py::hybrid_search_with_metrics": (
        "hybrid_search wrapper that captures SearchMetrics; full integration test "
        "coverage in test_search_metrics_tracking.py; wire alongside hybrid_search "
        "when metrics collection is needed"
    ),
    # Restored — test-covered, no production caller (same pattern as vector search above)
    "core/services/base_service.py::ensure_backend_available": (
        "backend health-check method; unit test coverage in "
        "tests/unit/test_base_service.py::TestInfrastructure; no production "
        "call site yet — wire into a /health route or startup check"
    ),
    "core/services/ingestion/ingestion_history.py::get_total_count": (
        "count query for ingestion history entries; unit test coverage in "
        "tests/unit/test_ingestion_history.py; no production caller yet — "
        "wire into the ingestion admin dashboard or a /status route"
    ),
    # --- Query builders: dependency chains on phantom edge vocabulary ---
    # (outside METHOD_SCOPE — reported via the existence-checked out-of-scope
    # path, not the vulture pipeline)
    "adapters/persistence/neo4j/query/cypher/domain_queries.py::build_principle_dependencies": (
        _PHANTOM_EDGE_CHAIN_BUILDERS
    ),
    "adapters/persistence/neo4j/query/cypher/domain_queries.py::build_habit_dependencies": (
        _PHANTOM_EDGE_CHAIN_BUILDERS
    ),
}

# Method findings are scoped to the service layer; the rest of the tree is
# covered by the standalone vulture run at --min-confidence 90.
METHOD_SCOPE = "core/services/"


class Colors:
    """Terminal colors for better output readability."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


class BloatSeverity(Enum):
    """Finding tiers. Only WARNING can ever fail a --check run."""

    WARNING = "warning"  # structurally dead — verified absence of liveness
    UNVERIFIED = "unverified"  # constructed somewhere; publication untraceable
    INFO = "info"  # live but noteworthy (e.g. published, never subscribed)
    PLANNED = "planned"  # unwired by intent — a completion to-do, not bloat


@dataclass
class Finding:
    """One bloat finding."""

    kind: str  # e.g. "event-never-published"
    severity: BloatSeverity
    subject: str  # e.g. event class name
    file: str
    line: int
    detail: str
    annotations: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "subject": self.subject,
            "file": self.file,
            "line": self.line,
            "detail": self.detail,
            "annotations": self.annotations,
        }


@dataclass
class Site:
    """A source location."""

    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


# ============================================================================
# Parsed codebase — every file parsed exactly once, shared by all analyses
# ============================================================================


class ParsedCodebase:
    """File discovery + one-shot ast.parse cache.

    Syntax errors are collected and REPORTED — never silently skipped. A file
    the analysis cannot see is a hole in every liveness claim.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.production: dict[Path, ast.Module] = {}
        self.tests: dict[Path, ast.Module] = {}
        self.syntax_errors: list[str] = []

    def load(self) -> None:
        for path in self._discover(FIRST_PARTY_ROOTS):
            self._parse_into(path, self.production)
        for path in self._discover(["tests"]):
            self._parse_into(path, self.tests)

    def _discover(self, roots: list[str]) -> list[Path]:
        files: list[Path] = []
        for root_name in roots:
            target = self.root / root_name
            if target.is_file() and target.suffix == ".py":
                files.append(target)
            elif target.is_dir():
                for path in sorted(target.rglob("*.py")):
                    if not EXCLUDED_PARTS.intersection(path.parts):
                        files.append(path)
        return files

    def _parse_into(self, path: Path, cache: dict[Path, ast.Module]) -> None:
        try:
            cache[path] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            self.syntax_errors.append(f"{self.rel(path)}: {exc.msg} (line {exc.lineno})")
        except (OSError, UnicodeDecodeError) as exc:
            self.syntax_errors.append(f"{self.rel(path)}: unreadable ({exc})")

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))


# ============================================================================
# Event universe — transitive inheritance closure from BaseEvent
# ============================================================================


def _base_name(node: ast.expr) -> str | None:
    """Resolve a class base expression to its terminal name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class EventUniverse:
    """All event classes in core/events/, closed transitively over BaseEvent.

    Catches indirect subclasses (e.g. TaskEmbeddingRequested(EmbeddingRequested))
    that a direct-base check misses. Builds a descendants map so an intermediate
    base counts as publish-live when any descendant is published.
    """

    def __init__(self, codebase: ParsedCodebase) -> None:
        self.codebase = codebase
        self.classes: dict[str, Site] = {}  # event class -> definition site
        self.descendants: dict[str, set[str]] = defaultdict(set)

    def build(self) -> None:
        bases: dict[str, list[str]] = {}
        sites: dict[str, Site] = {}
        for path, tree in self.codebase.production.items():
            if EVENTS_PACKAGE not in path.parents:
                continue
            rel = self.codebase.rel(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    names = [b for b in map(_base_name, node.bases) if b]
                    bases[node.name] = names
                    sites[node.name] = Site(rel, node.lineno)

        # Fixpoint closure from BaseEvent.
        universe = {EVENT_ROOT_BASE}
        changed = True
        while changed:
            changed = False
            for cls, cls_bases in bases.items():
                if cls not in universe and universe.intersection(cls_bases):
                    universe.add(cls)
                    changed = True

        for cls in universe - {EVENT_ROOT_BASE}:
            self.classes[cls] = sites[cls]

        # Direct-child edges -> transitive descendants.
        children: dict[str, set[str]] = defaultdict(set)
        for cls in self.classes:
            for base in bases.get(cls, []):
                if base in self.classes:
                    children[base].add(cls)
        for cls in self.classes:
            stack = list(children[cls])
            while stack:
                child = stack.pop()
                if child not in self.descendants[cls]:
                    self.descendants[cls].add(child)
                    stack.extend(children[child])

    def __contains__(self, name: str) -> bool:
        return name in self.classes

    def registry_size(self) -> int | None:
        """Entry count of EVENT_REGISTRY in core/events/__init__.py (AST, no import).

        Used as a self-diagnostic cross-check; None if the dict moved.
        """
        init_path = EVENTS_PACKAGE / "__init__.py"
        tree = self.codebase.production.get(init_path)
        if tree is None:
            return None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "EVENT_REGISTRY"
                and isinstance(node.value, ast.Dict)
            ):
                return len(node.value.keys)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "EVENT_REGISTRY" in targets:
                    return len(node.value.keys)
        return None


# ============================================================================
# Publication / construction / subscription collectors (pure AST)
# ============================================================================


@dataclass
class EventUsage:
    """Aggregated event usage across the production tree (tests kept apart)."""

    published: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    constructed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    subscribed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    test_published: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    test_constructed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    unresolved_publishes: list[Site] = field(default_factory=list)
    unresolved_subscribes: list[Site] = field(default_factory=list)


@dataclass(frozen=True)
class PublishWrapper:
    """A function/method that publishes one of its own parameters.

    ``caller_index`` is the event argument's position as seen by callers
    (``self``/``cls`` already stripped); ``param_name`` resolves keyword calls.
    """

    caller_index: int
    param_name: str


class PublishWrapperInference:
    """Infers publish-wrapper functions structurally, to a fixpoint.

    A def whose body publishes one of its OWN parameters (via a primitive
    ``publish_async``/``publish`` or an already-known wrapper) is itself a
    wrapper — e.g. ``publish_event`` (core/events/__init__.py),
    ``group_service._publish_event``, ``BaseAIService._publish_event``.
    Applied globally by name: marking events live is the safe direction.
    Interior publish sites of recognized wrappers (the parameter pass-through)
    are accounted for at call sites and excluded from the unresolved count.
    """

    # Bus methods (Attribute calls only — bare publish()/publish_async() names
    # would be ambiguous) and the canonical helper (Name or Attribute; its
    # signature publish_event(event_bus, event, logger) is the documented
    # contract at core/events/__init__.py).
    PRIMITIVES = {"publish_async": 0, "publish": 0}
    CANONICAL_HELPERS = {"publish_event": 1}

    def __init__(self, codebase: ParsedCodebase) -> None:
        self.codebase = codebase
        self.wrappers: dict[str, set[PublishWrapper]] = defaultdict(set)
        self.interior_sites: set[tuple[str, int]] = set()  # (file, line) to skip

    def infer(self) -> None:
        defs: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
        for path, tree in self.codebase.production.items():
            rel = self.codebase.rel(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defs.append((rel, node))

        changed = True
        while changed:
            changed = False
            for rel, fn in defs:
                if self._try_promote(rel, fn):
                    changed = True

    def event_arg_candidates(self, call: ast.Call) -> tuple[list[ast.expr], bool]:
        """(candidate event arguments, is publish-shaped) for a call node.

        A wrapper name can carry several inferred signatures (two different
        ``_publish_event`` defs exist); every signature's argument is a
        candidate and the caller records whichever resolves to an event class.
        """
        name = _base_name(call.func)
        if name in self.PRIMITIVES and isinstance(call.func, ast.Attribute):
            arg = _call_arg(call, self.PRIMITIVES[name], "event")
            return ([arg] if arg is not None else []), True
        if name in self.CANONICAL_HELPERS:
            arg = _call_arg(call, self.CANONICAL_HELPERS[name], "event")
            return ([arg] if arg is not None else []), True
        if name in self.wrappers:
            candidates = []
            for wrapper in sorted(self.wrappers[name], key=lambda w: w.caller_index):
                arg = _call_arg(call, wrapper.caller_index, wrapper.param_name)
                if arg is not None:
                    candidates.append(arg)
            return candidates, True
        return [], False

    def _try_promote(self, rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        params = [a.arg for a in fn.args.args]
        promoted = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            candidates, is_publish = self.event_arg_candidates(node)
            if not is_publish:
                continue
            for arg in candidates:
                if not isinstance(arg, ast.Name) or arg.id not in params:
                    continue
                self.interior_sites.add((rel, node.lineno))
                index = params.index(arg.id)
                if params and params[0] in ("self", "cls"):
                    index -= 1
                if index < 0:
                    continue
                wrapper = PublishWrapper(index, arg.id)
                # Dedup on the full (index, param) signature — two defs sharing
                # a name may put the event at different positions.
                if wrapper not in self.wrappers[fn.name]:
                    self.wrappers[fn.name].add(wrapper)
                    promoted = True
        return promoted


def _call_arg(node: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    if len(node.args) > position:
        return node.args[position]
    return None


class EventUsageCollector:
    """Collects publish / construct / subscribe sites for the event universe.

    Resolution rules (all structural, all file-scoped):
    - Import aliases: ``from core.events.x import TaskCompleted as TC`` makes
      ``TC`` resolve to ``TaskCompleted`` within that file.
    - Variables: ``x = EventClass(...)`` anywhere in a file lets a later
      ``publish_*(x)`` in the same file resolve — over-approximation in the
      safe direction (it can only suppress a dead-event accusation).
    - Class registries: ``REG = {...: EventClass, ...}`` (dict literal whose
      values are event classes) followed by ``cls = REG.get(...)`` /
      ``cls = REG[...]`` and a published ``cls(...)`` resolves to EVERY class
      in the registry — the embedding_publisher chokepoint pattern; same safe
      over-approximation direction as the variable rule.
    - Publish wrappers: see PublishWrapperInference.
    Cross-FILE event flow is never traced — it surfaces as an unresolved
    publish site plus the UNVERIFIED construction tier.
    """

    def __init__(self, universe: EventUniverse, codebase: ParsedCodebase) -> None:
        self.universe = universe
        self.codebase = codebase
        self.usage = EventUsage()
        self.wrappers = PublishWrapperInference(codebase)

    def collect(self) -> EventUsage:
        self.wrappers.infer()
        for path, tree in self.codebase.production.items():
            self._collect_file(self.codebase.rel(path), tree, is_test=False)
        for path, tree in self.codebase.tests.items():
            self._collect_file(self.codebase.rel(path), tree, is_test=True)
        return self.usage

    # -- per-file ------------------------------------------------------------

    def _collect_file(self, rel: str, tree: ast.Module, is_test: bool) -> None:
        aliases = self._file_alias_map(tree)
        var_events = self._file_event_var_index(tree, aliases)
        var_lists = self._file_event_list_index(tree, aliases)
        in_events_pkg = rel.startswith("core/events/")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            site = Site(rel, node.lineno)

            # Constructions: EventClass(...) anywhere. Definitions inside
            # core/events/ are the class statements, not constructions, so the
            # package itself still counts (it rarely constructs its own events).
            ctor = self._ctor_class(node, aliases)
            if ctor is not None and not in_events_pkg:
                target = self.usage.test_constructed if is_test else self.usage.constructed
                target[ctor].append(site)

            candidates, is_publish = self.wrappers.event_arg_candidates(node)
            if is_publish:
                if (rel, node.lineno) in self.wrappers.interior_sites:
                    continue  # parameter pass-through, accounted at call sites
                self._record_publish(node, candidates, var_events, aliases, site, is_test)
            elif (
                _base_name(node.func) == "subscribe"
                and isinstance(node.func, ast.Attribute)
                and not is_test
            ):
                self._record_subscribe(node, var_lists, aliases, site)

    # -- name resolution -------------------------------------------------------

    def _file_alias_map(self, tree: ast.Module) -> dict[str, str]:
        """Import-alias -> canonical event class name, for one file."""
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.asname and alias.name in self.universe:
                        aliases[alias.asname] = alias.name
        return aliases

    def _resolve(self, name: str | None, aliases: dict[str, str]) -> str | None:
        if name is None:
            return None
        if name in self.universe:
            return name
        return aliases.get(name)

    def _ctor_class(self, node: ast.expr, aliases: dict[str, str]) -> str | None:
        if isinstance(node, ast.Call):
            return self._resolve(_base_name(node.func), aliases)
        return None

    # -- variable indices (file-scoped, safe over-approximation) --------------

    def _file_event_var_index(
        self, tree: ast.Module, aliases: dict[str, str]
    ) -> dict[str, set[str]]:
        """var name -> event classes assigned to it.

        Covers ``x = EventClass(...)`` and the class-registry pattern:
        ``REG = {...: EventClass, ...}`` then ``cls = REG.get(...)`` /
        ``cls = REG[...]`` maps ``cls`` to every class in the registry
        (embedding_publisher chokepoint — safe over-approximation, it can
        only suppress a dead-event accusation).
        """
        index: dict[str, set[str]] = defaultdict(set)
        registries: dict[str, set[str]] = defaultdict(set)

        for node in ast.walk(tree):
            value = None
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value, targets = node.value, [node.target]
            if value is None:
                continue

            if isinstance(value, ast.Dict):
                classes = {
                    resolved
                    for v in value.values
                    if isinstance(v, ast.Name)
                    and (resolved := self._resolve(v.id, aliases)) is not None
                }
                if classes:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            registries[target.id].update(classes)
                continue

            cls = self._ctor_class(value, aliases)
            if cls is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    index[target.id].add(cls)

        # Second pass so lookups resolve regardless of statement order.
        for node in ast.walk(tree):
            value = None
            targets = []
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value, targets = node.value, [node.target]
            if value is None:
                continue
            reg_classes = self._registry_lookup_classes(value, registries)
            if not reg_classes:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    index[target.id].update(reg_classes)

        return index

    @staticmethod
    def _registry_lookup_classes(value: ast.expr, registries: dict[str, set[str]]) -> set[str]:
        """Classes for ``REG.get(...)`` / ``REG[...]`` lookups on a known registry."""
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get"
            and isinstance(value.func.value, ast.Name)
        ):
            return registries.get(value.func.value.id, set())
        if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
            return registries.get(value.value.id, set())
        return set()

    def _file_event_list_index(
        self, tree: ast.Module, aliases: dict[str, str]
    ) -> dict[str, set[str]]:
        """var name -> event classes, for subscribe-loop resolution.

        Covers ``events = [TaskCreated, ...]`` and ``for ev in events:`` /
        ``for ev in [TaskCreated, ...]:`` (services_bootstrap/_event_wiring.py).
        """
        index: dict[str, set[str]] = defaultdict(set)
        list_vars: dict[str, set[str]] = defaultdict(set)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
                classes = self._event_names_in_list(node.value, aliases)
                if classes:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            list_vars[target.id].update(classes)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.AsyncFor)):
                continue
            if not isinstance(node.target, ast.Name):
                continue
            loop_classes: set[str] = set()
            if isinstance(node.iter, ast.List):
                loop_classes = self._event_names_in_list(node.iter, aliases)
            elif isinstance(node.iter, ast.Name):
                loop_classes = list_vars.get(node.iter.id, set())
            if loop_classes:
                index[node.target.id].update(loop_classes)

        return index

    def _event_names_in_list(self, node: ast.List, aliases: dict[str, str]) -> set[str]:
        resolved = (
            self._resolve(elt.id, aliases) for elt in node.elts if isinstance(elt, ast.Name)
        )
        return {name for name in resolved if name is not None}

    # -- recording -----------------------------------------------------------

    def _record_publish(
        self,
        call: ast.Call,
        candidates: list[ast.expr],
        var_events: dict[str, set[str]],
        aliases: dict[str, str],
        site: Site,
        is_test: bool,
    ) -> None:
        published = self.usage.test_published if is_test else self.usage.published
        # Bare .publish() exists on non-event objects; only its resolvable
        # calls count, and it never lands in the unresolved tally (noise).
        is_bare_publish = _base_name(call.func) == "publish"
        for arg in candidates:
            ctor = self._ctor_class(arg, aliases)
            if ctor is not None:
                published[ctor].append(site)
                return
            # Registry-variable construction: ``cls = REG.get(...)`` then a
            # published ``cls(...)`` — resolves to every class in the registry.
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                registry_classes = var_events.get(arg.func.id, set())
                if registry_classes:
                    for cls in registry_classes:
                        published[cls].append(site)
                    return
            if isinstance(arg, ast.Name):
                classes = set(var_events.get(arg.id, set()))
                direct = self._resolve(arg.id, aliases)
                if direct is not None:
                    classes.add(direct)
                if classes:
                    for cls in classes:
                        published[cls].append(site)
                    return
        if not is_test and not is_bare_publish:
            self.usage.unresolved_publishes.append(site)

    def _record_subscribe(
        self,
        node: ast.Call,
        var_lists: dict[str, set[str]],
        aliases: dict[str, str],
        site: Site,
    ) -> None:
        arg = _call_arg(node, position=0, keyword="event_type")
        if isinstance(arg, ast.Name):
            resolved = self._resolve(arg.id, aliases)
            if resolved is not None:
                self.usage.subscribed[resolved].append(site)
                return
            if arg.id in var_lists:
                for cls in var_lists[arg.id]:
                    self.usage.subscribed[cls].append(site)
                return
        self.usage.unresolved_subscribes.append(site)


# ============================================================================
# Event findings assembly
# ============================================================================


def analyze_events(
    universe: EventUniverse, usage: EventUsage
) -> tuple[list[Finding], list[Finding]]:
    """Build (findings, exempted) for the event universe.

    Liveness rule: an event is publish-live iff it OR any descendant has a
    resolved publish site (an intermediate base is not dead while its children
    fly). Tier order: live -> UNVERIFIED (constructed in production, flow not
    traceable) -> WARNING (structurally dead).
    """
    findings: list[Finding] = []
    exempted: list[Finding] = []

    for cls, site in sorted(universe.classes.items()):
        family = {cls} | universe.descendants[cls]
        publish_live = any(usage.published.get(member) for member in family)
        subscribed = usage.subscribed.get(cls, [])

        if publish_live:
            if cls in PLANNED_EVENTS:
                findings.append(
                    Finding(
                        kind="planned-marking-stale",
                        severity=BloatSeverity.INFO,
                        subject=cls,
                        file=site.file,
                        line=site.line,
                        detail=(
                            "marked planned but now published — wiring complete; "
                            "remove from PLANNED_EVENTS"
                        ),
                    )
                )
            if not subscribed and not universe.descendants[cls]:
                findings.append(
                    Finding(
                        kind="event-never-subscribed",
                        severity=BloatSeverity.INFO,
                        subject=cls,
                        file=site.file,
                        line=site.line,
                        detail="published but no subscriber — fine if fire-and-forget",
                    )
                )
            continue

        constructed = [s for member in family for s in usage.constructed.get(member, [])]
        annotations = []
        if subscribed:
            annotations.append(
                f"has subscribers ({', '.join(str(s) for s in subscribed[:3])}) — dead wiring chain"
            )
        test_sites = [
            s
            for member in family
            for s in usage.test_published.get(member, []) + usage.test_constructed.get(member, [])
        ]
        if test_sites:
            annotations.append(f"referenced in tests ({len(test_sites)} sites)")

        if cls in PLANNED_EVENTS:
            # Subscriber wiring is intentional staging here, not a dead chain.
            planned_notes = []
            if subscribed:
                planned_notes.append(
                    f"subscribers staged at {', '.join(str(s) for s in subscribed[:3])}"
                )
            planned_notes.extend(a for a in annotations if "dead wiring chain" not in a)
            finding = Finding(
                kind="event-awaiting-wiring",
                severity=BloatSeverity.PLANNED,
                subject=cls,
                file=site.file,
                line=site.line,
                detail=f"unwired by intent — {PLANNED_EVENTS[cls]}",
                annotations=planned_notes,
            )
        elif constructed:
            finding = Finding(
                kind="event-publication-untraced",
                severity=BloatSeverity.UNVERIFIED,
                subject=cls,
                file=site.file,
                line=site.line,
                detail=(
                    f"constructed at {constructed[0]} but publication not "
                    "structurally traceable — verify manually"
                ),
                annotations=annotations,
            )
        else:
            finding = Finding(
                kind="event-never-published",
                severity=BloatSeverity.WARNING,
                subject=cls,
                file=site.file,
                line=site.line,
                detail="defined but never published nor constructed in production code",
                annotations=annotations,
            )

        if cls in EXEMPTED_EVENTS:
            finding.annotations.append(f"exempted: {EXEMPTED_EVENTS[cls]}")
            exempted.append(finding)
        else:
            findings.append(finding)

    # Stale planned markings for vanished subjects: a PLANNED_EVENTS key
    # absent from the event universe was deleted, renamed, or mistyped —
    # without this pass the registry would silently keep dead keys.
    for cls in sorted(PLANNED_EVENTS):
        if cls not in universe:
            findings.append(
                Finding(
                    kind="planned-marking-stale",
                    severity=BloatSeverity.INFO,
                    subject=cls,
                    file="core/events/",
                    line=0,
                    detail=(
                        "marked planned but no such event class exists — deleted, "
                        "renamed, or mistyped; remove from PLANNED_EVENTS"
                    ),
                )
            )

    return findings, exempted


# ============================================================================
# Method analysis — Vulture liveness engine + SKUEL dispatch-knowledge filter
# ============================================================================


# Names constructed by query_route_factory.py at route registration
# (get_user_{d} / find_{d} / get_{d}_for_goal / get_{d}_for_habit).
QUERY_ROUTE_TEMPLATES = (
    "get_user_{d}",
    "find_{d}",
    "get_{d}_for_goal",
    "get_{d}_for_habit",
)


class DispatchKnowledge:
    """SKUEL's dynamic-dispatch vocabulary, collected structurally.

    Vulture cannot see ``getattr(service, name)`` when ``name`` is computed.
    Every collector here reads only literal configuration (kwargs, dict keys)
    and expands the runtime templates those literals feed. Expansion
    over-approximates in the safe direction: it may suppress a dead-method
    accusation, never create one. Anything string-shaped but unexplained is
    DEMOTED to needs-verification, not suppressed; getattr with a computed
    name is counted, not hidden (no silent caps).
    """

    METHOD_KWARG = "method_name"
    METHOD_KWARG_SUFFIX = "_method"

    # Constructors whose POSITIONAL argument at the given index is a service
    # method name. AIRouteSpec.method_name is field index 4 and the route
    # table in ai_routes.py passes it positionally, so the kwarg collector
    # alone misses every AI route's dispatch target.
    POSITIONAL_METHOD_ARGS = {"AIRouteSpec": 4}

    # Operation-label constructs: their string argument names an operation for
    # error messages / Prometheus metrics and can never make a method
    # reachable, so it is NOT dispatch evidence and must not demote a vulture
    # finding. Known SKUEL constructs only (core/utils/decorators.py,
    # core/utils/metrics.py, the Errors factory's ``operation=`` kwarg) — any
    # other identifier-shaped string still demotes.
    LABEL_CALL_FIRST_ARG = {"with_error_handling", "track_query_metrics"}
    LABEL_KWARGS = {"operation"}

    def __init__(self, codebase: ParsedCodebase) -> None:
        self.codebase = codebase
        self.live: dict[str, str] = {}  # method name -> reason
        self.string_literals: dict[str, Site] = {}  # identifier-shaped constants
        self.unanalyzable_getattr: list[Site] = []
        self._domains: dict[str, Site] = {}
        self._entity_labels: set[str] = set()
        self._relationship_suffixes: set[str] = set()

    def collect(self) -> None:
        for path, tree in self.codebase.production.items():
            rel = self.codebase.rel(path)
            self._collect_calls(rel, tree)
            self._collect_identifier_strings(rel, tree)
        self._expand_templates()

    # -- call-site configuration ----------------------------------------------

    def _collect_calls(self, rel: str, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            site = Site(rel, node.lineno)
            callee = _base_name(node.func)

            if callee == "getattr":
                name_arg = node.args[1] if len(node.args) > 1 else None
                is_literal = isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)
                if not is_literal:
                    self.unanalyzable_getattr.append(site)
                continue

            positional_index = self.POSITIONAL_METHOD_ARGS.get(callee or "")
            if positional_index is not None and len(node.args) > positional_index:
                arg = node.args[positional_index]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.live.setdefault(arg.value, f"positional method arg ({callee}) at {site}")

            for kw in node.keywords:
                if kw.arg is None:
                    continue
                value = kw.value
                literal = (
                    value.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    else None
                )
                if literal is not None and (
                    kw.arg == self.METHOD_KWARG or kw.arg.endswith(self.METHOD_KWARG_SUFFIX)
                ):
                    self.live.setdefault(literal, f"literal method kwarg at {site}")
                elif literal is not None and kw.arg == "domain_name":
                    self._domains.setdefault(literal, site)
                elif literal is not None and kw.arg == "entity_label":
                    self._entity_labels.add(literal)
                elif kw.arg in ("outgoing_relationships", "incoming_relationships"):
                    # Dict KEYS are relationship method suffixes
                    # (relationship_registry.py -> get_{label}_{suffix}).
                    if isinstance(value, ast.Dict):
                        for key in value.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                self._relationship_suffixes.add(key.value)
                elif kw.arg == "transitions" and callee == "StatusRouteFactory":
                    # transitions={action: StatusTransition(...)} ->
                    # f"{action}_{domain_singular}" (status_route_factory.py).
                    singular = self._literal_kwarg(node, "domain_singular")
                    if singular is not None and isinstance(value, ast.Dict):
                        for key in value.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                self.live.setdefault(
                                    f"{key.value}_{singular}",
                                    f"status route template at {site}",
                                )

    @staticmethod
    def _literal_kwarg(node: ast.Call, name: str) -> str | None:
        for kw in node.keywords:
            if (
                kw.arg == name
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
        return None

    def _expand_templates(self) -> None:
        # Query-route templates per registered domain. Hyphenated domain names
        # also expand underscored (route slugs vs method identifiers).
        for domain, site in self._domains.items():
            variants = {domain, domain.replace("-", "_")}
            for template in QUERY_ROUTE_TEMPLATES:
                for variant in variants:
                    self.live.setdefault(
                        template.format(d=variant),
                        f"query route template for domain_name='{domain}' ({site})",
                    )
        # Relationship registry: get_{entity_label}_{suffix}, full cross
        # product of literal labels x literal suffixes (safe direction).
        for label in self._entity_labels:
            for suffix in self._relationship_suffixes:
                self.live.setdefault(
                    f"get_{label.lower()}_{suffix}",
                    f"relationship registry expansion ({label} x {suffix})",
                )

    # -- string-literal demotion tier ------------------------------------------

    def _collect_identifier_strings(self, rel: str, tree: ast.Module) -> None:
        """Identifier-shaped string constants in USED positions.

        A vulture finding matching one of these is demoted to
        needs-verification (likely dynamic dispatch), never suppressed.
        Bare-string statements (docstrings, prose) are inert, and so are
        operation-label strings (LABEL_CALL_FIRST_ARG / LABEL_KWARGS) — a
        method's own ``@with_error_handling("name")`` label must not shield
        it from a dead-method finding.
        """
        inert: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = _base_name(node.func)
                if callee in self.LABEL_CALL_FIRST_ARG and node.args:
                    inert.add(id(node.args[0]))
                for kw in node.keywords:
                    if kw.arg in self.LABEL_KWARGS:
                        inert.add(id(kw.value))
            body = getattr(node, "body", None)
            if not isinstance(body, list):
                continue
            for stmt in body:
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    inert.add(id(stmt.value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.isidentifier()
                and id(node) not in inert
            ):
                self.string_literals.setdefault(node.value, Site(rel, node.lineno))


@dataclass
class MethodAnalysis:
    """Outcome of the vulture + dispatch-knowledge pipeline."""

    findings: list[Finding]
    exempted: list[Finding]
    suppressed: dict[str, str]  # method name -> dispatch reason
    total_candidates: int
    dispatch: DispatchKnowledge


def _test_reference_index(codebase: ParsedCodebase) -> dict[str, int]:
    """name -> reference count across tests/ (attribute reads + imports)."""
    counts: dict[str, int] = defaultdict(int)
    for tree in codebase.tests.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                counts[node.attr] += 1
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    counts[alias.name] += 1
    return counts


def run_vulture(root: Path) -> list:
    """Vulture over the full first-party tree (whitelist included).

    min_confidence=60 is mechanics, not tuning: vulture assigns exactly 60 to
    unused functions/methods/properties, so 60 is the floor required to see
    them at all. The standalone --min-confidence 90 CLI run is unaffected.
    """
    import vulture

    v = vulture.Vulture()
    paths = [str(root / name) for name in FIRST_PARTY_ROOTS]
    paths.append(str(root / "vulture_whitelist.py"))
    v.scavenge(paths)
    return [
        item
        for item in v.get_unused_code(min_confidence=60)
        if item.typ in ("function", "method", "property")
    ]


def analyze_methods(codebase: ParsedCodebase, vulture_items: list) -> MethodAnalysis:
    """Filter vulture's service-layer candidates through dispatch knowledge.

    Pipeline: scope to core/services -> drop names in the dispatch-live
    vocabulary (printed with reasons) -> demote names that appear as string
    literals (likely dynamic dispatch) -> annotate test references -> apply
    EXEMPTED_METHODS -> report the remainder.
    """
    dispatch = DispatchKnowledge(codebase)
    dispatch.collect()
    test_refs = _test_reference_index(codebase)

    findings: list[Finding] = []
    exempted: list[Finding] = []
    suppressed: dict[str, str] = {}
    total = 0

    for item in vulture_items:
        rel = str(Path(item.filename).relative_to(codebase.root))
        if not rel.startswith(METHOD_SCOPE):
            continue
        total += 1
        name = item.name

        if name in dispatch.live:
            suppressed[name] = dispatch.live[name]
            continue

        annotations: list[str] = []
        if test_refs.get(name):
            annotations.append(f"referenced in tests ({test_refs[name]} sites)")

        planned_key = f"{rel}::{name}"
        if planned_key in PLANNED_METHODS:
            findings.append(
                Finding(
                    kind="method-awaiting-wiring",
                    severity=BloatSeverity.PLANNED,
                    subject=name,
                    file=rel,
                    line=item.first_lineno,
                    detail=f"unwired by intent — {PLANNED_METHODS[planned_key]}",
                    annotations=annotations,
                )
            )
            continue

        if name in dispatch.string_literals:
            finding = Finding(
                kind="method-needs-verification",
                severity=BloatSeverity.UNVERIFIED,
                subject=name,
                file=rel,
                line=item.first_lineno,
                detail=(
                    "unused per vulture, but the name appears as a string "
                    f"literal at {dispatch.string_literals[name]} — likely "
                    "dynamic dispatch, verify manually"
                ),
                annotations=annotations,
            )
        else:
            finding = Finding(
                kind="method-unused",
                severity=BloatSeverity.WARNING,
                subject=name,
                file=rel,
                line=item.first_lineno,
                detail=f"unused {item.typ} (vulture confidence {item.confidence})",
                annotations=annotations,
            )

        key = f"{rel}::{name}"
        if key in EXEMPTED_METHODS:
            finding.annotations.append(f"exempted: {EXEMPTED_METHODS[key]}")
            exempted.append(finding)
        else:
            findings.append(finding)

    # Stale planned markings: a planned method that stopped being a vulture
    # candidate is now live (wiring complete) or deleted — either way the
    # entry must go. Only METHOD_SCOPE keys ride this check — out-of-scope
    # entries are never vulture candidates here, so they get the
    # existence-checked path below instead.
    flagged_keys = {f"{f.file}::{f.subject}" for f in findings + exempted}
    for planned_key in PLANNED_METHODS:
        rel, _, name = planned_key.rpartition("::")
        if not rel.startswith(METHOD_SCOPE):
            continue
        if planned_key not in flagged_keys:
            findings.append(
                Finding(
                    kind="planned-marking-stale",
                    severity=BloatSeverity.INFO,
                    subject=name,
                    file=rel,
                    line=0,
                    detail=(
                        "marked planned but no longer flagged unused — wiring "
                        "complete or method deleted; remove from PLANNED_METHODS"
                    ),
                )
            )

    findings.extend(_out_of_scope_planned_findings(codebase))

    findings.sort(key=lambda f: (f.file, f.line))
    return MethodAnalysis(findings, exempted, suppressed, total, dispatch)


def _out_of_scope_planned_findings(codebase: ParsedCodebase) -> list[Finding]:
    """Report PLANNED entries living outside METHOD_SCOPE (e.g. adapters/ query
    builders).

    The vulture pipeline never scopes to these files, so such entries can't
    ride the normal candidate→PLANNED demotion or its stale check. They are
    emitted directly as backlog items; the one verification possible without
    call analysis is existence — a deleted or renamed function turns the
    entry into a stale marking.
    """
    results: list[Finding] = []
    for planned_key, note in PLANNED_METHODS.items():
        rel, _, name = planned_key.rpartition("::")
        if rel.startswith(METHOD_SCOPE):
            continue
        module = codebase.production.get(codebase.root / rel)
        def_line = 0
        if module is not None:
            for node in ast.walk(module):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
                    def_line = node.lineno
                    break
        if def_line == 0:
            results.append(
                Finding(
                    kind="planned-marking-stale",
                    severity=BloatSeverity.INFO,
                    subject=name,
                    file=rel,
                    line=0,
                    detail=(
                        "marked planned but the function no longer exists at this "
                        "path — deleted or renamed; remove from PLANNED_METHODS"
                    ),
                )
            )
        else:
            results.append(
                Finding(
                    kind="method-awaiting-wiring",
                    severity=BloatSeverity.PLANNED,
                    subject=name,
                    file=rel,
                    line=def_line,
                    detail=f"unwired by intent — {note}",
                    annotations=["outside METHOD_SCOPE — liveness not vulture-verified"],
                )
            )
    return results


# ============================================================================
# Reporting
# ============================================================================


def _print_finding(finding: Finding) -> None:
    mark = {
        BloatSeverity.WARNING: f"{Colors.RED}✗{Colors.RESET}",
        BloatSeverity.UNVERIFIED: f"{Colors.YELLOW}?{Colors.RESET}",
        BloatSeverity.INFO: f"{Colors.CYAN}i{Colors.RESET}",
        BloatSeverity.PLANNED: f"{Colors.BLUE}◷{Colors.RESET}",
    }[finding.severity]
    print(f"  {mark} {Colors.BOLD}{finding.subject}{Colors.RESET}  ({finding.file}:{finding.line})")
    print(f"      {finding.detail}")
    for note in finding.annotations:
        print(f"      {Colors.YELLOW}⚠ {note}{Colors.RESET}")


def print_event_report(
    universe: EventUniverse,
    usage: EventUsage,
    findings: list[Finding],
    exempted: list[Finding],
    verbose: bool,
) -> None:
    print(f"\n{Colors.BOLD}🔔 Events Analysis{Colors.RESET}")
    registry = universe.registry_size()
    registry_note = f" (EVENT_REGISTRY lists {registry})" if registry is not None else ""
    print(
        f"  Event universe (transitive BaseEvent subclasses): {len(universe.classes)}{registry_note}"
    )
    resolved_pubs = sum(len(v) for v in usage.published.values())
    resolved_subs = sum(len(v) for v in usage.subscribed.values())
    print(
        f"  Resolved publish sites: {resolved_pubs}  (unresolved: {len(usage.unresolved_publishes)})"
    )
    print(
        f"  Resolved subscriptions: {resolved_subs}  (unresolved: {len(usage.unresolved_subscribes)})"
    )

    # Self-diagnostic: a scanner finding nothing is more likely broken than
    # the codebase being silent (fail-fast applied to the tool itself).
    if resolved_pubs == 0 or resolved_subs == 0:
        print(
            f"\n{Colors.RED}{Colors.BOLD}🚨 SELF-DIAGNOSTIC: zero resolved "
            f"{'publish sites' if resolved_pubs == 0 else 'subscriptions'} — "
            f"the collector is almost certainly broken. Do not trust this report.{Colors.RESET}"
        )

    by_severity: dict[BloatSeverity, list[Finding]] = defaultdict(list)
    stale_planned: list[Finding] = []
    for finding in findings:
        if finding.kind == "planned-marking-stale":
            stale_planned.append(finding)
        else:
            by_severity[finding.severity].append(finding)

    for severity, title in [
        (BloatSeverity.WARNING, "Structurally dead events"),
        (BloatSeverity.UNVERIFIED, "Constructed but publication untraced — verify manually"),
        (BloatSeverity.PLANNED, "Planned — unwired by intent, awaiting completion"),
        (BloatSeverity.INFO, "Published but never subscribed (may be intentional)"),
    ]:
        items = by_severity.get(severity, [])
        if not items:
            continue
        print(f"\n{Colors.YELLOW}{title} ({len(items)}):{Colors.RESET}\n")
        for finding in items:
            _print_finding(finding)

    if stale_planned:
        print(
            f"\n{Colors.RED}Stale planned markings — remove from PLANNED_EVENTS "
            f"({len(stale_planned)}):{Colors.RESET}\n"
        )
        for finding in stale_planned:
            _print_finding(finding)

    if not findings:
        print(f"\n  {Colors.GREEN}✓ No event findings.{Colors.RESET}")

    if exempted:
        print(
            f"\n  {Colors.DIM}exempted ({len(exempted)}): "
            f"{', '.join(f.subject for f in exempted)}{Colors.RESET}"
        )

    if verbose and usage.unresolved_publishes:
        print(f"\n{Colors.DIM}Unresolved publish sites:{Colors.RESET}")
        for site in usage.unresolved_publishes:
            print(f"  {Colors.DIM}{site}{Colors.RESET}")
    if verbose and usage.unresolved_subscribes:
        print(f"\n{Colors.DIM}Unresolved subscription sites:{Colors.RESET}")
        for site in usage.unresolved_subscribes:
            print(f"  {Colors.DIM}{site}{Colors.RESET}")


def print_method_report(analysis: MethodAnalysis, verbose: bool) -> None:
    print(
        f"\n{Colors.BOLD}🔧 Service Methods Analysis (vulture + dispatch knowledge){Colors.RESET}"
    )
    print(f"  Vulture candidates in {METHOD_SCOPE}: {analysis.total_candidates}")
    print(
        f"  Suppressed by dispatch knowledge: {len(analysis.suppressed)}  "
        f"(dynamic-dispatch vocabulary: {len(analysis.dispatch.live)} names)"
    )

    by_severity: dict[BloatSeverity, list[Finding]] = defaultdict(list)
    stale_planned: list[Finding] = []
    for finding in analysis.findings:
        if finding.kind == "planned-marking-stale":
            stale_planned.append(finding)
        else:
            by_severity[finding.severity].append(finding)

    dead = by_severity.get(BloatSeverity.WARNING, [])
    demoted = by_severity.get(BloatSeverity.UNVERIFIED, [])
    planned = by_severity.get(BloatSeverity.PLANNED, [])

    if dead:
        print(
            f"\n{Colors.YELLOW}Unused service methods "
            f"({len(dead)}) — verify before deleting:{Colors.RESET}\n"
        )
        by_file: dict[str, list[Finding]] = defaultdict(list)
        for finding in dead:
            by_file[finding.file].append(finding)
        for file in sorted(by_file):
            print(f"  {Colors.BOLD}{file}{Colors.RESET}")
            for finding in by_file[file]:
                print(f"    {Colors.RED}✗{Colors.RESET} {finding.subject}  (line {finding.line})")
                for note in finding.annotations:
                    print(f"        {Colors.YELLOW}⚠ {note}{Colors.RESET}")
            print()
    else:
        print(f"\n  {Colors.GREEN}✓ No unused service methods.{Colors.RESET}")

    if demoted:
        print(
            f"{Colors.YELLOW}Needs verification — name appears as a string "
            f"literal, likely dynamic dispatch ({len(demoted)}):{Colors.RESET}\n"
        )
        for finding in demoted:
            _print_finding(finding)

    if planned:
        print(
            f"\n{Colors.YELLOW}Planned — unwired by intent, awaiting completion "
            f"({len(planned)}):{Colors.RESET}\n"
        )
        for finding in planned:
            _print_finding(finding)

    if stale_planned:
        print(
            f"\n{Colors.RED}Stale planned markings — remove from PLANNED_METHODS "
            f"({len(stale_planned)}):{Colors.RESET}\n"
        )
        for finding in stale_planned:
            _print_finding(finding)

    if analysis.exempted:
        print(
            f"\n  {Colors.DIM}exempted ({len(analysis.exempted)}): "
            f"{', '.join(f.subject for f in analysis.exempted)}{Colors.RESET}"
        )

    if verbose and analysis.suppressed:
        print(f"\n{Colors.DIM}Suppressed by dispatch knowledge:{Colors.RESET}")
        for name, reason in sorted(analysis.suppressed.items()):
            print(f"  {Colors.DIM}{name}: {reason}{Colors.RESET}")
    if verbose and analysis.dispatch.unanalyzable_getattr:
        print(f"\n{Colors.DIM}Unanalyzable getattr sites:{Colors.RESET}")
        for site in analysis.dispatch.unanalyzable_getattr:
            print(f"  {Colors.DIM}{site}{Colors.RESET}")


def print_limitations(
    codebase: ParsedCodebase,
    usage: EventUsage | None,
    methods: MethodAnalysis | None,
) -> None:
    print(f"\n{Colors.BOLD}📏 Limitations (read before acting on findings){Colors.RESET}")
    if usage is not None:
        print(
            f"  - {len(usage.unresolved_publishes)} publish and "
            f"{len(usage.unresolved_subscribes)} subscribe sites could not be "
            "resolved to an event class (run --verbose for locations)."
        )
        print(
            "  - No cross-file dataflow by design: events that travel between "
            "files before publication land in the UNVERIFIED tier, not WARNING."
        )
    if methods is not None:
        print(
            f"  - {len(methods.dispatch.unanalyzable_getattr)} getattr sites use a "
            "computed name — methods reachable only through them may be falsely "
            "flagged (run --verbose for locations)."
        )
        print(
            "  - Vulture name-collision: any same-named attribute access anywhere "
            "marks ALL same-named methods used, so common-named dead methods stay "
            "invisible (inherent under-reporting)."
        )
    if codebase.syntax_errors:
        print(
            f"  - {Colors.RED}{len(codebase.syntax_errors)} files failed to parse "
            f"— their usage is INVISIBLE to this report:{Colors.RESET}"
        )
        for err in codebase.syntax_errors:
            print(f"      {err}")


# ============================================================================
# CLI
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect unused code in SKUEL (AST-sound)")
    parser.add_argument("--events-only", action="store_true", help="Check events only")
    parser.add_argument("--methods-only", action="store_true", help="Check methods only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if WARNING findings survive (advisory otherwise)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit findings as JSON")
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    check_events = not args.methods_only
    check_methods = not args.events_only

    # With --json, stdout carries ONLY the findings document.
    progress_out = sys.stderr if args.as_json else sys.stdout

    print(f"{Colors.CYAN}🔍 Parsing codebase...{Colors.RESET}", file=progress_out)
    codebase = ParsedCodebase(ROOT)
    codebase.load()
    print(
        f"  {len(codebase.production)} production files, "
        f"{len(codebase.tests)} test files parsed"
        + (
            f", {Colors.RED}{len(codebase.syntax_errors)} unparseable{Colors.RESET}"
            if codebase.syntax_errors
            else ""
        ),
        file=progress_out,
    )

    findings: list[Finding] = []
    usage: EventUsage | None = None
    methods: MethodAnalysis | None = None

    if check_events:
        universe = EventUniverse(codebase)
        universe.build()
        usage = EventUsageCollector(universe, codebase).collect()
        event_findings, exempted = analyze_events(universe, usage)
        findings.extend(event_findings)
        if not args.as_json:
            print_event_report(universe, usage, event_findings, exempted, args.verbose)

    if check_methods:
        print(
            f"{Colors.CYAN}🔍 Running vulture (liveness engine)...{Colors.RESET}",
            file=progress_out,
        )
        methods = analyze_methods(codebase, run_vulture(ROOT))
        findings.extend(methods.findings)
        if not args.as_json:
            print_method_report(methods, args.verbose)

    if args.as_json:
        print(json.dumps([f.to_json() for f in findings], indent=2))

    if not args.as_json:
        print_limitations(codebase, usage, methods)
        warnings = [f for f in findings if f.severity is BloatSeverity.WARNING]
        planned = [f for f in findings if f.severity is BloatSeverity.PLANNED]
        other = len(findings) - len(warnings) - len(planned)
        print(f"\n{Colors.BOLD}{'=' * 78}{Colors.RESET}")
        if warnings:
            print(
                f"{Colors.YELLOW}{len(warnings)} structurally-dead findings "
                f"(+{other} unverified/info, {len(planned)} planned). "
                f"Verify before deleting.{Colors.RESET}"
            )
        else:
            print(
                f"{Colors.GREEN}✅ No structurally-dead findings"
                f"{f' ({len(planned)} planned)' if planned else ''}.{Colors.RESET}"
            )

    if args.check:
        return 1 if any(f.severity is BloatSeverity.WARNING for f in findings) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
