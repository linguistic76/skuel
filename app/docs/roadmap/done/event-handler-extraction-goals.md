# Plan 2 of 5: GoalEventHandlerService

## Context

Goals is the second domain to receive a dedicated event handler service, following the Tasks proof of concept (`TaskEventHandlerService`). Goals has 9 sub-services and already has event handlers scattered across two sub-services: `GoalsRecommendationService` and `GoalsProgressService`.

**Template files:**
- `core/services/tasks/task_event_handler_service.py` (Tasks proof of concept)
- `core/services/principles/principle_event_handler_service.py` (original template)

---

## Current State: Event Subscription Audit

### Bootstrap subscriptions (from `services_bootstrap.py`)

| Event | Current Handler | Location | Classification |
|-------|----------------|----------|----------------|
| `GoalAchieved` | `goals_service.recommendations.handle_goal_achieved` | `GoalsRecommendationService` | **MOVE** — reactive handler on own domain |
| `GoalAchieved` | `analytics_service.handle_goal_achieved` | `AnalyticsService` | STAYS — cross-domain infrastructure |
| `GoalCreated` | `cross_domain_analytics_service.handle_goal_created` | `CrossDomainAnalyticsService` | STAYS — cross-domain infrastructure |
| `TaskCompleted` | `goals_service.progress.handle_task_completed` | `GoalsProgressService` | STAYS — cross-domain progress tracking |
| `HabitCompleted` | `goals_service.progress.handle_habit_completed` | `GoalsProgressService` | STAYS — cross-domain progress tracking |
| `GoalCreated` | `invalidate_context` | bootstrap closure | STAYS — infrastructure |
| `GoalAchieved` | `invalidate_context` | bootstrap closure | STAYS — infrastructure |
| `GoalAbandoned` | `invalidate_context` | bootstrap closure | STAYS — infrastructure |
| `GoalMilestoneReached` | `invalidate_context` | bootstrap closure | STAYS — infrastructure |
| `GoalProgressUpdated` | `invalidate_context` | bootstrap closure | STAYS — infrastructure |

### What to MOVE

1. **`handle_goal_achieved`** from `GoalsRecommendationService` — this is the primary MOVE candidate. It generates recommendations when a goal is achieved. Currently lives in its own dedicated sub-service, which means after extraction, `GoalsRecommendationService` may become empty and deletable (reducing 9 sub-services to 9, net neutral, but cleaner separation).

### What has NO handler (gaps)

| Event | Current Reaction | New Handler Opportunity |
|-------|-----------------|----------------------|
| `GoalAbandoned` | Context invalidation only | Abandonment pattern analysis, principle alignment check |
| `GoalProgressUpdated` | Context invalidation only | Progress stall detection, milestone proximity alerts |
| `GoalMilestoneReached` | Context invalidation + auto-report | Celebration logging, principle alignment check |

---

## Proposed Handlers

### Handler 1: `handle_goal_achieved(event: GoalAchieved)`

**Migrated from:** `GoalsRecommendationService.handle_goal_achieved()` (~60 lines)

Contains:
1. **Recommendation generation** (migrated) — analyze goal context, generate next-goal suggestions, publish `GoalRecommendationsGenerated` event
2. **Duration calibration** (new) — compare `actual_duration_days` vs `planned_duration_days`, log accuracy insight
3. **Principle alignment** (new) — query `ALIGNED_WITH_PRINCIPLE` relationships, log cross-domain insight on achievement

### Handler 2: `handle_goal_abandoned(event: GoalAbandoned)`

**Currently:** No domain-specific handler (only context invalidation).

Contains:
1. **Abandonment pattern classification** — categorize by `reason`, `progress_at_abandonment`, `days_active`
2. **Early vs late abandonment** — <25% progress = "early pivot", >75% = "near-miss"
3. **Structured logging** with `extra` dict

### Handler 3: `handle_goal_progress_updated(event: GoalProgressUpdated)`

**Currently:** No domain-specific handler.

Contains:
1. **Progress stall detection** — if progress hasn't changed significantly in recent updates, log warning
2. **Milestone proximity alert** — if within 5% of 25/50/75/100%, log encouragement
3. **Cross-domain trigger logging** — log which domain triggered the update (`triggered_by_task_completion`, etc.)

---

## Decision: What happens to GoalsRecommendationService?

After migrating `handle_goal_achieved`, check if `GoalsRecommendationService` has remaining methods:
- If it only has `handle_goal_achieved` + private helpers → **delete it**, move helpers to event handler
- If it has other public methods → keep it, just remove the handler

**Check:** `grep -n "async def " core/services/goals/goals_recommendation_service.py`

---

## Integration Steps

1. Create `core/services/goals/goal_event_handler_service.py`
2. Integrate as sub-service on `GoalsService` facade (9 → 10 sub-services, or 9 if RecommendationService deleted)
3. Update `core/services/goals/__init__.py`
4. Migrate handler + rewire bootstrap
5. Tests in `tests/unit/services/activity/test_goal_event_handler.py`
6. Update event docstrings + SUB_SERVICE_CATALOG.md

---

## Status: ✅ COMPLETE (2026-03-20)

**Implementation:**
- Created `GoalEventHandlerService` with 3 handlers (GoalAchieved, GoalAbandoned, GoalProgressUpdated)
- Deleted `GoalsRecommendationService` (all logic migrated to event handler)
- Sub-service count stays at 9 (recommendations → event_handler)
- Fixed bug: `GoalAchieved.actual_duration_days` default was `(None,)` tuple instead of `None`
- 3 new bootstrap subscriptions replacing 1 old one
- Tests: `tests/unit/services/activity/test_goal_event_handler.py`
