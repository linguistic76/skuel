---
title: "Request Models No Door Reads"
updated: 2026-11-08
status: "open — 23 staged (8 wait on a door for a service that exists, 3 on a design, 12 on a re-evaluation) and 1 parked; 23 retired 2026-11-08; 1 bound by its door 2026-11-08"
registered: 2026-11-05
ruled: "2026-11-05 (Mike) — 23 retire; UserFilterSchema and HabitCompletionFilterRequest move from retire to staged; the rest stay staged or parked, each for the reason in its row"
trigger: "a door is being built that would bind one of these shapes, or a session takes a staged model's re-evaluation"
check: "uv run pytest tests/unit/models/test_unread_model_register.py — every model no production file reads is in the register, and every model the register names exists"
---

# Request Models No Door Reads

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

These Pydantic models under `core/models` had no reader: no production file but their own named
them. Each has its verdict. A model is retired on evidence: a record that it was tried and failed,
or a named, populated means that does the same job. "Nothing reads it yet" is neither, so the rest
stay registered here, each with what it waits on.

The `./dev bloat` PLANNED tier covers events, methods, templates and embedding maps, not models, so
this file is their register.

## How the list was read

Import every module under `core/models`, walk `BaseModel.__subclasses__()`, and hold each name
against every tracked `.py` file outside `tests/`. Three things are not a reader: the model's own
class line, a package `__init__.py` re-export, and an `__all__` entry. A model its own module names
anywhere else counts as read, and so does a docstring that names it, so the set is a floor.

The first reading (2026-11-05) found 48:

- 40 that no other file named, re-exports aside;
- 5 named only by a docstring (`ChoiceDecisionRequest`, in a `validation_rules.py` usage example)
  or by a test table (the four user views, in `test_client_datetime_fields.py`'s `RESPONSE_FIELDS`);
- 3 named only by something else unread: `FacetSetRequest` by `SearchQueryRequest`,
  `UserPreferencesSchema` by `UserView` and `UserUpdateSchema`, `InvoiceUpdateRequest` by
  `invoice_update_request_to_dto`.

The check holds the register to the code both ways: a model the floor finds and the register does
not name fails it, and so does a name the register holds that is no model.

## Retired 2026-11-08

Each row names the live means that does the model's job.

| Model | What does its job |
|---|---|
| `PauseHabitRequest` | `POST /api/habits/{uid}/status` with `paused` (`update_habit`, status-guarded). Its `reason` and `until_date` (auto-resume) had no reader |
| `ResumeHabitRequest` | the same door with `active` |
| `ArchiveHabitRequest` | the same door with `archived`, under the streak-preservation rule. Its `reason` had no reader |
| `HabitCompletionRequest` | `POST /api/habits/track` (`TrackHabitRequest`: date, a 1–5 value, notes) |
| `HabitCompletionCreateRequest` | the same door |
| `GetHabitProgressRequest` | `GET /api/habits/progress?uid&period`, the same two fields |
| `HabitStatsRequest` | `GET /api/habits/history`, `/streak`, `/progress`. No habit prediction exists |
| `GoalAnalyticsRequest` | `GET /api/goals/analytics`, `/goals/predict-success`, `/goals/habit-impact`; a goal's JSON carries `progress_history`. Milestone analysis waits on the milestone door below |
| `EventsInRangeRequest` | `/cal/week`, `/cal/month`, `/today/{date}` (`get_events_in_range`). The staged `EventFilterRequest` carries `date_from` / `date_to` |
| `CalendarQuickCreateRequest` | each item's own create door, `POST /api/{domain}/create`; the calendar reads what they write |
| `AlignmentAssessmentRequest` | `POST /api/principles/reflection` (`PrincipleReflectionRequest`: alignment level, evidence) |
| `WeeklyReviewRequest` | `POST /api/reports/progress/generate` with a calendar week (`time_period=2026-W45`) |
| `SearchQueryRequest` | `POST /api/search/unified` (`SearchRequest`) |
| `FacetSetRequest` | `SearchRequest`'s facet fields; read only by `SearchQueryRequest` |
| `CategorizeEntityRequest` | nothing to categorize into: its vocabulary is `ReportCategory`, which no module defines |
| `BulkCategorizeRequest` | each domain's update door sets its own typed category (`habit_category`, `principle_category`, a goal's `domain`); its one free-text category has no field to land in. No door categorizes several at once |
| `BulkTagRequest` | each domain's update door sets `tags`. No door tags several at once |
| `BulkDeleteRequest` | `POST /api/{domain}/bulk-delete` (`uids`, ownership checked per uid) on goals, habits, events, choices and principles; each domain's delete door |
| `UserView` | `GET /api/admin/users/get`, `/admin/users/{uid}`. 14 of its 29 fields are not `User` fields |
| `UserSummaryView` | the `/admin/users` table, `GET /api/admin/users` |
| `UserStatisticsSchema` | `/admin/users/{uid}`, `GET /api/analytics/productivity`, `/habit-consistency`, `/learning-velocity`. No door returns most active time, most productive day or average task duration |
| `UserServiceContextSchema` | `UserContext`, `GET /api/context/dashboard` |
| `UserPreferencesSchema` | `POST /settings/save` (`UserPreferencesFormRequest`). No door edits `preferred_subjects` or `energy_pattern`; read only by `UserView` and `UserUpdateSchema`'s `preferences` field, which went with it (the ruled narrowing of `UserUpdateSchema` drops it) |

## Bound by a door

| Model | Door |
|---|---|
| `ChoiceDecisionRequest` | `POST /api/choices/{uid}/decide`, the choice page's decide form (2026-11-08) |

## Register

A wiring door binds its model and takes its row out.

| Model | File | Verdict | Why |
|---|---|---|---|
| `ActivityReviewRequest` | `core/models/entity_requests.py` | staged: door | `request_review` exists, registered READY; bind the feedback form |
| `ActivityFeedbackSubmitRequest` | `core/models/entity_requests.py` | staged: door | the same door, passing `snapshot_context` |
| `GoalProgressUpdateRequest` | `core/models/goal/goal_request.py` | staged: door | one door with the two milestone models |
| `MilestoneCreateRequest` | `core/models/goal/goal_request.py` | staged: door | it has fields the service does not take |
| `MilestoneCompleteRequest` | `core/models/goal/goal_request.py` | staged: door | it sends a uid; the service wants an index |
| `GoalHabitLinkRequest` | `core/models/goal/goal_request.py` | staged: door | one door with the two habit-system models |
| `HabitEssentialityChangeRequest` | `core/models/goal/goal_request.py` | staged: door | the same door |
| `HabitSystemUpdateRequest` | `core/models/goal/goal_request.py` | staged: door | the same door |
| `UserUpdateSchema` | `core/models/user/user_request.py` | staged: design | wanted (Mike 2026-11-05): narrow to display name. `update_user` exists; `/settings` has no account section; `display_name` is set only at registration |
| `UserAnalyticsView` | `core/models/user/user_request.py` | staged: design | wanted: growth and retention on `/admin/analytics`. Growth reads `User.created_at`; `AuthEvent` is pruned at 90 days, so retention needs the ruled monthly login count per user, which has no home yet. Several fields read nothing that exists |
| `WeeklyPlanningRequest` | `core/models/analytics/analytics_report_request.py` | staged: design | wanted: the daily plan stretched over seven days, checked against available minutes. No service; read the daily plan first. Its `user_uid` field goes: the user comes from the session |
| `GoalFilterRequest` | `core/models/goal/goal_request.py` | staged: re-evaluate | list filters are fundamental (Mike). A GET door reads its fields through the strict readers, so a filter class is a specification until a POST door binds it |
| `HabitFilterRequest` | `core/models/habit/habit_request.py` | staged: re-evaluate | the same |
| `EventFilterRequest` | `core/models/event/event_request.py` | staged: re-evaluate | the same |
| `PrincipleFilterRequest` | `core/models/principle/principle_request.py` | staged: re-evaluate | the same |
| `UserFilterSchema` | `core/models/user/user_request.py` | staged: re-evaluate | of its 13 filters `GET /api/admin/users` serves active status alone (beside a role filter the schema lacks) and ignores `?search=`; the `/admin/users` page has no search, limit or pagination |
| `HabitCompletionFilterRequest` | `core/models/habit/habit_completion_request.py` | staged: re-evaluate | no door filters completions by quality or pages them; the filter family |
| `HabitCompletionUpdateRequest` | `core/models/habit/habit_completion_request.py` | staged: re-evaluate | no door edits a completion |
| `HabitSkipRequest` | `core/models/habit/habit_request.py` | staged: re-evaluate | no door records a skip |
| `UserCapacityCheckSchema` | `core/models/user/user_request.py` | staged: re-evaluate | held for review (Mike 2026-11-05) |
| `UserCapacityView` | `core/models/user/user_request.py` | staged: re-evaluate | the same |
| `IdentityBasedGoalRequest` | `core/models/goal/goal_request.py` | staged: re-evaluate | no door creates an identity goal |
| `SystemHealthCheckRequest` | `core/models/goal/goal_request.py` | staged: re-evaluate | no door checks a goal's habit system |
| `InvoiceUpdateRequest` | `core/models/finance/invoice.py` | parked | ChargeKeep ruling (no invoice-module fixes). Read only by `invoice_update_request_to_dto`, which nothing calls |
