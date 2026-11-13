---
title: Goals Domain
created: 2025-12-04
updated: 2026-11-13
status: current
category: domains
tags:
- goals
- activity-domain
- domain
related_skills:
- activity-domains
---

# Goals Domain

**Type:** Activity Domain (2 of 6)
**UID Prefix:** `goal:`
**Entity Label:** `Goal`
**Config:** `GOALS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

**Skill:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

Goals represent desired outcomes that guide learning and habit formation. They provide direction for tasks, habits, and knowledge acquisition.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/goal/goal.py` |
| DTO | `/core/models/goal/goal_dto.py` |
| Request Models | `/core/models/goal/goal_request.py` |
| Relationships | `/core/services/goals/goal_relationships.py` |
| **Backend** | `/adapters/persistence/neo4j/backends/activity_backends.py` (`GoalsBackend`) |
| Core Service | `/core/services/goals/goals_core_service.py` |
| Search Service | `/core/services/goals/goals_search_service.py` |
| Progress Service | `/core/services/goals/goals_progress_service.py` |
| Learning Service | `/core/services/goals/goals_learning_service.py` |
| Planning Service | `/core/services/goals/goals_planning_service.py` |
| Scheduling Service | `/core/services/goals/goals_scheduling_service.py` |
| Intelligence Service | `/core/services/goals/goals_intelligence_service.py` |
| Event Handler Service | `/core/services/goals/goal_event_handler_service.py` |
| Facade | `/core/services/goals_service.py` |
| Config | `GOALS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/goal_events.py` |
| UI Routes | `/adapters/inbound/goals_ui.py` |
| View Components | `/ui/activities/goals_views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `GoalType` | `core.models.enums` | OUTCOME, PROCESS, LEARNING, PROJECT, MILESTONE, MASTERY | `goal_type` |
| `GoalTimeframe` | `core.models.enums` | DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY, MULTI_YEAR | `timeframe` |
| `MeasurementType` | `core.models.enums` | BINARY, PERCENTAGE, NUMERIC, MILESTONE, HABIT_BASED, KNOWLEDGE_BASED, TASK_BASED, MIXED | `measurement_type` |
| `HabitEssentiality` | `core.models.enums` | ESSENTIAL, CRITICAL, SUPPORTING, OPTIONAL | `get_weight()` (1 / .75 / .5 / .25, `HabitEssentialityWeight`) — the `SUPPORTS_GOAL` edge's tier, weighing the dashboard's `habit_contribution`; `from_stored()` reads an untagged edge as SUPPORTING |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH | `priority` |

**See:** [Enum Architecture](../architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026, mixins April 2026)

`GoalsService` delegates to sub-services + 1 focused facade mixin for orchestration:

```python
class GoalsService(
    _OrchestrationMixin,    # cross-domain orchestration (create_goal_with_context, etc.)
    KnowledgeIntelligenceDelegationMixin,
    BaseService[GoalsOperations, Goal],
):
    # Delegation methods delegate to the sub-services below
    async def get_goal(self, uid: str) -> Result[Goal]:
        return await self.core.get_goal(uid)
```

**Facade Mixin** (`core/services/goals/`):

| Mixin | File | Methods |
|-------|------|---------|
| `_OrchestrationMixin` | `_orchestration_mixin.py` | `create_goal_with_context`, `assess_goal_feasibility` |

Graph relationship methods (`link_goal_to_habit/knowledge/principle/life_path`, `unlink_goal_from_habit`, `unlink_goal_from_principle`, `create_semantic_goal_relationship`) are inline on `GoalsService` directly — inlined June 2026 per the decomposition floor rule.

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, status transitions (takes `cross_domain_query` for goal-abandonment guard) |
| `search` | Text search, filtering, graph-aware queries |
| `progress` | Progress tracking and milestones |
| `learning` | Learning path integration |
| `planning` | Context-first planning methods |
| `scheduling` | Capacity management, timeline optimization (January 2026) |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Analytics, predictions, dual-track assessment (decomposed into 4 mixins — see below) |
| `event_handler` | Event-driven reactive handlers (achievements, abandonment, progress) |

`core`, `search`, `relationships`, `learning`, `event_handler` and `knowledge_intelligence` come from `create_common_sub_services()`; `intelligence`, `progress`, `planning` and `scheduling` are built in the facade `__init__` with sibling sub-services as dependencies (`progress`, `core`, `relationships`).

## Event Handler — Insight Persistence (March 2026)

`GoalEventHandlerService` handles fire-and-forget reactive logic and persists structured insights to `InsightStore`:

| Handler | Trigger | InsightType | Impact |
|---------|---------|------------|--------|
| `handle_goal_abandoned` | All abandonments | `COMPLETION_PATTERN` | HIGH (near-miss) / MEDIUM |
| `handle_goal_progress_updated` | `progress_delta < 0.01` | `IMBALANCE_DETECTED` | MEDIUM |
| `handle_goal_progress_updated` | Within 5% of 25/50/75/100% | `COMPLETION_PATTERN` | LOW |

Also handles: recommendation generation (via `backend.get_achievement_context()` — a `GoalsOperations` protocol method that fetches goal properties + related Kus/habits/principles), duration calibration, principle alignment, cross-domain trigger logging.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Goal title |
| `description` | `str?` | Goal description |
| `goal_type` | `GoalType` | Outcome, Process, Learning, Project, Milestone, Mastery |
| `timeframe` | `GoalTimeframe` | Daily, Weekly, Monthly, Quarterly, Yearly, Multi-year |
| `status` | `GoalStatus` | Not Started, In Progress, Completed, etc. |
| `priority` | `Priority` | Low, Medium, High |
| `target_date` | `date?` | Target completion date |
| `progress_percentage` | `float` | Progress percentage (0-100) — the goal's one progress field |
| `last_progress_update` | `datetime?` | Stamp of the last progress EVENT (a figure that moved); overwritten by every later one |
| `progress_history` | `tuple[ProgressHistoryEntry, ...]` | Every progress event, `{date, progress_percentage}`, appended by each writer that moves the figure (manual door, milestone door, task/habit propagation, an intent carrying a figure, the reopen reset of a goal whose percentage is the measure, the reopen recompute of one whose is not), plus the learner's `note` where they wrote one on the progress form. A note written without moving the figure is an entry of its own, marked `note_only` (the figure as it stood). The activity report's `goals_progressed` counts the progress events (not a `note_only` entry), never the stamp; the goal page lists every entry |
| `measurement_type` | `MeasurementType` | Binary, Percentage, Numeric, Milestone, etc. |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |

## Relationships

### Outgoing (Goal → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `REQUIRES_KNOWLEDGE` | Ku | Knowledge required for goal |
| `aligned_paths` | `ALIGNED_WITH_PATH` | Lp | Aligned learning paths |
| `required_paths` | `REQUIRES_PATH_COMPLETION` | Lp | Required learning paths |
| `parent_goal` | `SUBGOAL_OF` | Goal | Parent goal |
| `inspired_by_choice` | `INSPIRED_BY_CHOICE` | Choice | The choice that inspired this goal |

### Incoming (Other → Goal)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `subgoals` | `SUBGOAL_OF` | Goal | Child goals |
| `supporting_habits` | `SUPPORTS_GOAL` | Habit | Habits that support this goal |
| `supporting_principles` | `SUPPORTS_GOAL` | Principle | Principles that support this goal (YAML: `connections.supporting_principles`) |
| `contributing_tasks` | `CONTRIBUTES_TO_GOAL` | Task | Tasks that contribute to this goal |
| `contributing_events` | `CONTRIBUTES_TO_GOAL` | Event | Events that contribute to this goal |
| `celebrating_events` | `CELEBRATES_GOAL` | Event | Events that celebrate this goal |
| `affecting_choices` | `AFFECTS_GOAL` | Choice | Choices that affect this goal |
| `essential_habits` | `SUPPORTS_GOAL` (essentiality=essential) | Habit | Essential habits |
| `critical_habits` | `SUPPORTS_GOAL` (essentiality=critical) | Habit | Critical habits |
| `optional_habits` | `SUPPORTS_GOAL` (essentiality=optional) | Habit | Optional habits |

`SUPPORTS_GOAL` has three kinds of source — habits, principles and PathSteps (`goal_uids`) — so each
goal view names its kind: a keyed read of `supporting_habits` returns habits only, and
`supporting_principles` principles only. The three tier views are habit-only; a principle's edge
stores `essentiality` but has no tier view. A PathStep that supports the goal is on no goal view.

`CONTRIBUTES_TO_GOAL` has two kinds of source, tasks and events, so the goal reads each as its own
view: `contributing_tasks` names `Task`, `contributing_events` names `Event`. A cancelled
contribution is still listed (its status shown) and is left out of the progress tally.

An event that celebrates the goal (`CELEBRATES_GOAL`, the event form's "Milestone for goal"
picker) is listed under `celebrating_events`, apart from the events that contribute, and never
counts toward progress: a celebration marks the goal, a contribution moves it. A choice is linked
two ways: the goal names the choice that inspired it (`INSPIRED_BY_CHOICE`, written at the goal),
and lists the choices that affect it (`AFFECTS_GOAL`, written at the choice —
`POST /api/choices/link-goal` or the choice's `connections.affects_goal`).

### Bidirectional

- `SUBGOAL_OF` - Goal hierarchy

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `tasks` | Task | `CONTRIBUTES_TO_GOAL` (incoming) |
| `habits` | Habit | `SUPPORTS_GOAL` |
| `knowledge` | Ku | `REQUIRES_KNOWLEDGE` |
| `subgoals` | Goal | `SUBGOAL_OF` |
| `supporting_principles` | Principle | `SUPPORTS_GOAL` (incoming) |

## Query Intent

**Default:** `QueryIntent.GOAL_ACHIEVEMENT`

| Context | Intent |
|---------|--------|
| `context` | `GOAL_ACHIEVEMENT` |
| `achievement` | `GOAL_ACHIEVEMENT` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `active_goal_uids` - Active goal UIDs
- `completed_goal_uids` - Completed goal UIDs
- `goal_progress` - Progress per goal `{uid, progress}`
- `entities_rich["goals"]` - Full goal data with graph context

## Goal Types

| Type | Description |
|------|-------------|
| `OUTCOME` | Result-focused (achieve X) |
| `PROCESS` | Activity-focused (do Y consistently) |
| `LEARNING` | Knowledge/skill acquisition |
| `PROJECT` | Complete a specific project |
| `MILESTONE` | Reach a specific milestone |
| `MASTERY` | Master a domain/skill |

## Habit Essentiality

Goals track which habits are essential for achievement:

| Essentiality | Meaning |
|--------------|---------|
| `ESSENTIAL` | Goal is impossible without this habit |
| `CRITICAL` | Goal is very difficult without this habit |
| `SUPPORTING` | Goal is easier with this habit |
| `OPTIONAL` | Habit is tangentially helpful |

The tier is the `essentiality` property of `(Habit)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)`;
`HabitEssentiality.from_stored` reads an absent or unknown value as `supporting`. It weighs the
habit's adherence in the dashboard's habit-support figure (`dashboard_figures`) and sorts the
habit into the tier buckets; it does not enter a habit-based goal's percentage, which is the
plain average streak. Nothing reads `weight`; every door writes it 1.0.

**The habit system's doors** (owner verified; JSON or the goal page's habit section). Every habit
must be the goal owner's own (`HABIT_FAR_END`): another user's habit, a principle or a uid that
names nothing is not found and nothing is written. A principle's `SUPPORTS_GOAL` on the same goal
is never touched by any of them.

| Door | Model | Service |
|---|---|---|
| `POST /api/goals/{uid}/habits` | `GoalHabitLinkRequest` (`habit_uid`, `essentiality`, default supporting) | `link_goal_to_habit`. A habit already linked keeps its one edge and takes the tier given |
| `POST /api/goals/{uid}/habits/essentiality` | `HabitEssentialityChangeRequest` | `change_habit_essentiality`: sets the tier alone; a habit not linked is not found and no link is made |
| `POST /api/goals/{uid}/habits/unlink` | `GoalHabitUidRequest` | `unlink_goal_from_habit`; a habit not linked changes nothing |
| `POST /api/goals/{uid}/habits/system` | `HabitSystemUpdateRequest` | `replace_habit_system`: a full replace. The four lists are every habit the goal keeps; a habit not named is unlinked, a habit linked by another door after the caller read the system included. One transaction under the goal's lock |

A habit-based goal's figure follows its habits. The recompute
(`GoalsProgressService.recompute_habit_figure`, the locked recompute a habit completion runs) has
one membership trigger, `GoalHabitsChanged` (`goal_uids`, `habit_uids`), and
`GoalsProgressService.handle_goal_habits_changed` is its one subscriber. Every door that writes or
removes a habit's `SUPPORTS_GOAL` edge publishes it: the link, unlink and replace doors above; goal
create with `supporting_habit_uids` and habit create with `linked_goal_uids` (each announcing only
the links its batch wrote; a new habit's streak is 0, so it lowers the average); habit delete (the
goals read before the edge goes); the vault (`connections.supports_goal` on a habit file or
`connections.supporting_habits` on a goal file, added or retracted, a re-synced habit or goal, a
deleted habit file, a `SUPPORTS_GOAL` Edge YAML written or deleted); and a PathStep engagement's
discard or abandon of a habit the learner had linked. A goal whose last habit leaves is written 0,
as a task-based goal whose last contribution leaves is. A habit's status change does not change
membership: the recompute counts every linked habit whatever its status. A habit-based goal's
figure on a vault goal file is overwritten by the recompute, since its habits are that figure's
one writer. The trigger is best-effort, so `./dev reconcile-goal-tallies` recomputes every
HABIT_BASED goal whose stored figure disagrees with its habits, as it does a task-based tally.

A link a vault file creates carries the create doors' `weight` 1.0 and `supporting` tier
(`SUPPORTS_GOAL_LINK_PROPERTIES`); a re-sync leaves an existing link's tier alone.

## Search Methods

**Service:** `GoalsSearchService` (`/core/services/goals/goals_search_service.py`)

Its methods with their real signatures, its search fields, and which of its methods are staged: [Search Service Methods § GoalsSearchService](../reference/SEARCH_SERVICE_METHODS.md#goalssearchservice). That catalog is generated from the class, so it lists only what the class has.

## Scheduling Service (January 2026)

`GoalsSchedulingService` provides capacity management and timeline optimization:

| Method | Description |
|--------|-------------|
| `check_goal_capacity(user_uid)` | Can user handle another active goal? |
| `create_goal_with_context(data, context)` | Context-validated goal creation |
| `suggest_goal_timeline(user_uid, type, timeframe)` | Recommend target date based on history |
| `assess_goal_achievability(goal_uid, context)` | Can goal be achieved by target date? |
| `get_schedule_aware_next_goal(context)` | Best goal to focus on now |
| `optimize_goal_sequencing(user_uid, goal_uids)` | Optimal order for multiple goals |
| `get_goal_load_by_timeframe(user_uid)` | Goal distribution across timeframes |

**Capacity Criteria:**
- Maximum active goals (default: 5)
- Priority distribution (advisory: at most 2 HIGH)
- Complexity scoring (type × timeframe)

**Result Types:**
- `GoalCapacityResult` - Capacity check with recommendations
- `TimelineSuggestion` - Timeline suggestions with confidence
- `AchievabilityResult` - Achievability assessment with velocity metrics
- `GoalSequenceItem` - Goal sequencing with reasoning

## Intelligence Service (decomposed April 2026)

`GoalsIntelligenceService` provides goal analysis and insights. Inherits `get_with_context`
(mechanism B) from the shared `core/services/intelligence/_CoreIntelligenceMixin` and is
decomposed into focused mixins:

| Mixin | File | Methods |
|-------|------|---------|
| `_AnalyticsMixin` | `_analytics_mixin.py` | `get_performance_analytics`, `get_domain_insights`, `get_goal_progress_dashboard`, `_generate_progress_recommendations`, `get_goal_completion_forecast`, `get_goal_learning_requirements` |
| `_PredictiveMixin` | `_predictive_mixin.py` | `predict_goal_success`, `analyze_habit_impact`, `assess_goal_risk`, `run_scenario_analysis` + private helpers |
| `_DualTrackMixin` | `_dual_track_mixin.py` | `assess_progress_dual_track`, `_calculate_system_progress`, `_progress_level_to_score`, `_generate_progress_gap_*` |

**See:** [Intelligence Services Index](../intelligence/INTELLIGENCE_SERVICES_INDEX.md), [Goals Intelligence](../intelligence/GOALS_INTELLIGENCE.md)

## Events/Publishing

The Goals domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `GoalCreated` | Goal created | `goal_uid`, `user_uid`, `title` |
| `GoalAchieved` | Goal marked complete | `goal_uid`, `user_uid`, `actual_duration_days`, `completed_ahead_of_schedule` |
| `GoalReopened` | Goal moved out of completed to a working status (`update_goal` or the vault door) | `goal_uid`, `user_uid` |
| `GoalProgressUpdated` | Progress changed | `goal_uid`, `user_uid`, `old_progress`, `new_progress` |
| `GoalAbandoned` | Goal abandoned | `goal_uid`, `user_uid`, `reason` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, task updates).

**`GoalAchieved` fires on the transition, never on the state — and since ADR-087 the transition
is decided BY the write.** Publishing on the state alone would both move the recorded achievement
date to today on any later write (a mutable completion stamp) and duplicate the
PRINCIPLE_ALIGNMENT insight `GoalEventHandlerService` appends per event. No event carries a
repeat flag: the transition gate is the whole mechanism.

Where that gate lives differs by door, and the split is the point:

- The **chokepoint** (`GoalsCoreService.update_goal`) is handed a status target, so
  `status_transition_guard` packages the stamp as a `patch_if_prior_not_in` and the verdict comes
  from `is_completion_transition(outcome.prior_status, changes)`.
- The **progress writers** are handed no target — they derive one from the figure:
  `new_progress >= 100 and old_progress < 100`, a statement about the NEW state. Only the
  *"…and it was not already achieved"* half rides the guard, as a `patch_if_prior_not_in`
  carrying the status/stamp **pair**. So an already-completed goal is written no `status` key
  either — the recompute still lands, the completion pair does not. Every one of them plans under
  the goal's lock.
- The **milestone writers and the entered figure** (`create_goal_milestone`, `complete_milestone`,
  `update_goal_progress`) plan from the goal read under its lock (`rewrite_under_lock`): the
  milestone list is appended to or changed as it stands, so two writes of one goal keep both, and
  status follows the figure by the rule below.
- The **two tally recomputes** (`recompute_goal_tally`, `recompute_habit_figure`) go
  further: they read the goal AND its tally under the goal's write-lock, in the same transaction as
  the write (`GoalsBackend.recompute_progress_from_contributions` / `…_from_linked_habits`, over
  `_CrudMixin._recompute_with_status_guard`). Two recomputes of one goal therefore serialize, and
  the later one counts what the earlier one wrote over — a count taken before the lock could land
  after a change it never saw. Their progress is a measurement, so status follows it **both ways**
  (ruled 2026-09-23): a drop from 100% to below it on a COMPLETED goal un-achieves it — status back
  to `active`, `achieved_date` removed — via a `patch_if_prior_in`, the mirror of the achievement
  pair. A goal its owner settled (CANCELLED, ARCHIVED, FAILED) has its figure written and its status
  left alone: a recompute never achieves or un-achieves it.

**The contribution tally.** A TASK_BASED goal's progress is its owner's tasks and events that
`CONTRIBUTES_TO_GOAL` the goal, each counted once: COMPLETED is done, CANCELLED is left out, every
other status (FAILED included) is not done, and a task with `completion_updates_goal` false is left
out (`core/models/goal/goal_contribution.py`; the statement is
`goal_tally_queries.build_contribution_tally_query`). A goal whose last contribution leaves is
written 0 / 0 and 0%. A MIXED goal is not recomputed from it
([Mixed Goals Get No Event-Driven Progress](../roadmap/mixed-goal-event-progress.md)).

The recompute has one trigger, `GoalContributionsChanged` (`goal_uids`, `contributor_uids`), and
`GoalsProgressService.handle_goal_contributions_changed` is its one subscriber. Every door that can
change a tally publishes it: a task or event status write that moves the contribution between done,
not done and out; task and event create with goals; the task update's goal list (a full replace)
and a `completion_updates_goal` change; the task and event link doors and the unlink service
methods; task and event delete (the goals captured before the edge goes); the vault field
(`connections.contributes_to_goal`) added or retracted, a vault file deleted, a content-vault Edge
file; and a PathStep engagement's spawn, discard and abandon. The trigger is best-effort, so
`./dev reconcile-goal-tallies` (`GoalsProgressService.reconcile_goal_tallies`) recomputes every
TASK_BASED goal whose stored tally disagrees with its contributions, and every HABIT_BASED goal
whose figure disagrees with its habits ([Habit Essentiality](#habit-essentiality)).

A goal cannot be cancelled through `GoalsService.cancel_goal` while a contributing task is open
(not COMPLETED, CANCELLED or FAILED); a contributing event does not block it.

**Whose figure it is.** A goal's measurement type names the one writer of
`progress_percentage` (`MeasurementType.takes_entered_figure` / `follows_milestones` /
`entered_in_units`):

| Measurement type | The figure's writer |
|---|---|
| `task_based` | the contribution tally |
| `habit_based` | the supporting habits' streaks |
| `milestone` | the goal's milestones: completed over total, the two counts as `current_value` / `target_value` |
| `numeric` | the learner, in the goal's own unit: `current_value` against `target_value`, the percentage derived and capped at 100 |
| `percentage`, `binary`, `knowledge_based`, `mixed` | the learner, as the percentage 0-100 |

A figure entered on one of the three derived types is refused (422). Milestones on a goal they do
not measure are a checklist: adding or completing one writes the list alone. Status follows every
figure by the recompute rule above: a rise to 100 achieves the goal unless its owner settled it,
and a fall from 100 un-achieves it. So adding a milestone to an achieved milestone-measured goal
un-achieves it, and so does lowering an entered figure.

Doors: `POST /api/goals/{uid}/progress`, `POST /api/goals/{uid}/milestones`,
`POST /api/goals/{uid}/milestones/complete`, `POST /api/goals/{uid}/milestones/reopen` (owner
verified; JSON or the goal page's forms). A milestone is named by its own uid
(`milestone_{16 hex}`), a key inside the goal's list, not a node uid. Reopening a milestone is the
mirror of completing it: on a milestone-measured goal the figure falls, and a fall from 100
un-achieves the goal.

**A progress note and the history the page shows** (ruled 2026-11-13). The progress form takes
an optional note (`GoalProgressUpdateRequest.note`, stripped, 500 characters at most, blank is no
note). It rides the `progress_history` entry the entered figure appends, under the goal's lock, so
notes racing on one goal are all kept. A note entered with the figure unmoved still writes an
entry, marked `note_only`: it moves no `last_progress_update`, publishes no
`GoalProgressUpdated`, and the report does not count it as progress. The goal page lists the
history below the progress control on every goal (derived and set-aside ones too, read-only),
newest first by the day each entry names, in the user's zone: the day, the figure ("unchanged" on a
note-only entry) and the note. The five latest show, the rest fold under "Show all N entries".
Derived goals (task-based, habit-based, milestone) have no progress form, so no place for a note.

**A reopened goal keeps the figure its measure gives** (ruled 2026-11-12). Reopening a goal
(COMPLETED → a working status, `update_goal` or the vault door) resets the percentage to 0 only
where the percentage is the whole measurement (`MeasurementType.percentage_is_the_measure`:
`percentage`, `binary`, `knowledge_based`, `mixed`). On the other four the reset would be a second
writer standing beside a measure that says otherwise, so the reopen publishes `GoalReopened` and
`GoalsProgressService.handle_goal_reopened` rewrites the figure from the measure, under the goal's
lock, through the planner that type's writer uses, **with its status half taken off**: the learner
has just said the goal is not done, so the recompute neither achieves nor un-achieves it. That
covers a goal completed by hand (`complete_goal` writes 100 on every type): one completed at 2 of 5
tasks reopens at 40%. A goal whose measure still says 100 reopens at "100%, active", and the way
on is to change the measure: add a task or milestone, or reopen a milestone. A numeric goal keeps
its `current_value`; one with no target has no figure to give and is left alone. A move from
completed to a terminal status is not a reopen: the goal keeps its figure as the record.

⚠ A milestone-measured goal's "already achieved" input is the goal's **status**, not "every
milestone is flagged done": reopening the goal clears `achieved_date` and leaves the milestone
flags set, so a flag-based gate would make a reopened goal unachievable. The status is read under
the node's write-lock, at the moment it is acted on.

**The same rule applies one level down, to each milestone's own `achieved_date`.** It is
documented as "when actually achieved", so it records the milestone's *first* completion and
never moves; re-completing an already-completed milestone leaves it alone, and so does reopening
the milestone and completing it again. `is_completed` needs
no gate — it is already idempotent. The goal-level gate above does not cover this: re-completing
a milestone of a still-unachieved goal writes no goal stamp at all, yet would move the
milestone's. A completed milestone whose date is already null stays null — a repeat is not a
transition, so there is no moment to record, matching the task stamp gate (#1125).

## UI Routes

Goals has a list at `/goals` with filtering and progress display, and a detail page that
carries the progress and milestone controls.

| Route | Method | Description |
|-------|--------|-------------|
| `/goals` | GET | Goal list with filtering |
| `/goals/list-fragment` | GET | HTMX filtered list fragment |
| `/goals/detail?uid=` | GET | One goal: its figure, the progress form where the learner enters it (with an optional note), its progress history, its milestones with a Complete button on each open one, a Reopen button on each reached one, and the "Add milestone" form; the habit section below them. A goal set aside (cancelled, archived, failed) shows no control |
| `/goals/habits?uid=` | GET | HTMX fragment the detail page loads: the habits that support the goal, each with its tier select and Unlink button, and the "Link a habit" form (a habit picker and a tier). A goal set aside shows each habit's tier and no control |

## Code Examples

### Create a Goal

```python
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal import GoalType, GoalTimeframe
from core.models.enums import Priority
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

result = await goals_service.create_goal(
    GoalCreateRequest(
        title="Master FastHTML Framework",
        description="Become proficient in building web apps with FastHTML",
        goal_type=GoalType.MASTERY,
        timeframe=GoalTimeframe.QUARTERLY,
        priority=Priority.HIGH,
        target_date=today_in(current_zone()) + timedelta(days=90),
    ),
    user_uid=user_uid,
)
goal = result.value
```

### Update Goal Progress

```python
result = await goals_service.update_goal_progress(
    goal.uid,
    progress_value=60.0,  # a percentage; on a numeric goal, a value in the goal's unit
    note="Finished chapter three",  # optional; kept on the history entry
)
goal = result.value  # the goal as written
```

### Link Goal to Principle

```python
result = await goals_service.link_goal_to_principle(
    goal_uid=goal.uid,
    principle_uid="principle.continuous-learning",
)
```

Writes `(Principle)-[:SUPPORTS_GOAL {weight: 1.0, essentiality: "supporting"}]->(Goal)` — the one
principle ↔ goal edge. The principle's own door (`POST /api/principles/link`, `link_type=goal`),
`POST /api/goals/link-principle`, goal create's `supporting_principle_uids` and the DSL's
`@context(goal) @link(principle:…)` all write it, so the link shows on both pages whichever door
made it. `weight` and `essentiality` are optional arguments with those defaults.
`unlink_goal_from_principle(uid, principle_uid)` removes it and leaves a habit's support of the
same goal alone; no HTTP route calls it.

### Link Goal to the Life Path

```python
result = await goals_service.link_goal_to_life_path(
    goal_uid=goal.uid,
    life_path_uid="lp.mindfulness-101",
)
```

Writes `(Goal)-[:SERVES_LIFE_PATH]->(LearningPath)`; `POST /api/goals/link-life-path` is its door.
The far end is admitted only when it is the life path the goal's owner has designated
(`(User)-[:ULTIMATE_PATH]->`); any other path is refused as not found. A goal serves one life path:
writing the link removes the goal's links to any other path. The goal page lists it under
"The life path this goal serves", and the rich context reads it into `life_path_goal_uids` — the
goals method 7 and the schedule recommendations count as serving the life path.

## See Also

- [Tasks Domain](tasks.md) - Tasks fulfill goals
- [Habits Domain](habits.md) - Habits support goals
- [Principles Domain](principles.md) - Principles support goals
- [LifePath Domain](lifepath.md) - Goals serve life path
