---
title: "Request Models No Door Reads"
updated: 2026-11-05
status: "open — registered, no model has a verdict yet"
registered: 2026-11-05
ruled: "2026-11-05 — register here, delete nothing until each model has its verdict"
trigger: "a door is being built that would bind one of these shapes, or a session takes the per-model verdicts"
check: "for each model below: git grep -w <Name> -- '*.py' names only its own file (a package __init__.py re-export is not a reader)"
---

# Request Models No Door Reads

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

These Pydantic models under `core/models` have no reader: no other Python file holds the name.
Each needs its own verdict, because the names do not say which kind each one is. One may name a
capability still wanted, so it gets wired or stays registered here. Another may have a live twin
doing its job, so it goes. A model is retired on evidence: a record that it was tried and failed, or
a named, populated means that does the same job. "Nothing reads it yet" is neither.

The `./dev bloat` PLANNED tier covers events, methods, templates and embedding maps, not models, so
this file is their register.

## Today

| File | Models |
|---|---|
| `core/models/analytics/analytics_report_request.py` | `WeeklyPlanningRequest`, `WeeklyReviewRequest` |
| `core/models/entity_requests.py` | `ActivityFeedbackSubmitRequest`, `ActivityReviewRequest`, `BulkCategorizeRequest`, `BulkDeleteRequest`, `BulkTagRequest`, `CalendarQuickCreateRequest`, `CategorizeEntityRequest` |
| `core/models/event/event_request.py` | `EventFilterRequest`, `EventsInRangeRequest` |
| `core/models/goal/goal_request.py` | `GoalAnalyticsRequest`, `GoalFilterRequest`, `GoalHabitLinkRequest`, `GoalProgressUpdateRequest`, `HabitEssentialityChangeRequest`, `HabitSystemUpdateRequest`, `IdentityBasedGoalRequest`, `MilestoneCompleteRequest`, `MilestoneCreateRequest`, `SystemHealthCheckRequest` |
| `core/models/habit/habit_completion_request.py` | `HabitCompletionCreateRequest`, `HabitCompletionFilterRequest`, `HabitCompletionUpdateRequest` |
| `core/models/habit/habit_request.py` | `ArchiveHabitRequest`, `GetHabitProgressRequest`, `HabitCompletionRequest`, `HabitFilterRequest`, `HabitSkipRequest`, `HabitStatsRequest`, `PauseHabitRequest`, `ResumeHabitRequest` |
| `core/models/principle/principle_request.py` | `AlignmentAssessmentRequest`, `PrincipleFilterRequest` |
| `core/models/search_models.py` | `SearchQueryRequest` |
| `core/models/user/user_request.py` | `UserAnalyticsView`, `UserCapacityCheckSchema`, `UserCapacityView`, `UserFilterSchema`, `UserUpdateSchema` |

## How the list was read

Import every module under `core/models`, walk `BaseModel.__subclasses__()`, and hold each name
against every tracked `.py` file. A docstring that names a model counts as a reader, so the list is
a floor.
