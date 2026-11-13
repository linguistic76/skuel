---
title: "Request Models No Door Reads"
updated: 2026-11-13
status: "open — 16 staged (3 wait on a door for a service that exists, 1 on a design, 12 on a re-evaluation) and 1 parked; 23 retired 2026-11-08 and 1 on 2026-11-13; 7 bound by their doors 2026-11-08 to 2026-11-12; one staged field (a user's interests) waits on its representation"
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
| `UserPreferencesSchema` | `POST /settings/save` (`UserPreferencesFormRequest`). No door edits `preferred_subjects` or `energy_pattern`; read only by `UserView` and `UserUpdateSchema`'s `preferences` field, which went with it (`UserUpdateSchema` is now `DisplayNameUpdateRequest`, one field) |

## Retired 2026-11-13: `UserAnalyticsView`

Growth and retention on `/admin/analytics` do its job (design ruled by Mike 2026-11-13), as frozen
typed rows in `core/ports/query_types.py`: `GrowthReport`, `RetentionReport`, and the page's whole
payload, `AdminAnalyticsData`. The Pydantic model is deleted. Its fields:

| Field | Verdict |
|---|---|
| `total_users` | kept: `GrowthReport.total_accounts` |
| `active_users` | kept, renamed: `GrowthReport.accounts_not_deactivated`. It never meant "active recently"; the page shows deactivated accounts as their own figure |
| `new_users_this_month` | kept: `GrowthReport.new_this_month` |
| `user_growth_rate` | kept, as a count: `GrowthMonth.change`, a month's new accounts less the month before's |
| `user_growth_trend` | kept: `GrowthReport.months`, the trailing twelve months |
| `retention_rate` | kept: `RetentionMonth.rate`, shown beside its count ("2 of 3 (67%)") |
| `monthly_active_users` | kept: `RetentionMonth.present`, users present in the month. Present means signed in during it, or a live session seen in it |
| `activity_trend` | kept: `RetentionReport.months`, presence over the trailing twelve months |
| `verified_users` | retired, always constant: registration sets `is_verified` true for everyone |
| `premium_users` | retired, no source: nothing writes `is_premium`, in either tier |
| `daily_active_users`, `weekly_active_users` | retired, no source: presence is recorded by month. Each user-month counts its days active (`PRESENT_IN.days`), which `/admin/analytics` shows as a mean per present user; which users were active on a given day or week is not stored |
| `average_session_duration_minutes` | retired, no source: a session has no end stamp |
| `average_learning_level`, `users_by_level` | retired, no source: no door sets a learning level |
| `average_completion_rate`, `average_active_items`, `average_daily_minutes`, `completion_trend` | retired, no source: no per-user figure of these is stored, and none is derived across users |

`User.is_verified` and `User.is_premium` are still on the model; they wait for the later
User-model-fields row, with the fields `UserUpdateSchema` lost.

## Bound by a door

| Model | Door |
|---|---|
| `ChoiceDecisionRequest` | `POST /api/choices/{uid}/decide`, the choice page's decide form (2026-11-08) |
| `ActivityReviewRequest` | `POST /api/activity-reviews/request`, the "Ask for a personal review" card on `/submit-activity-report` (2026-11-09) |
| `ActivityFeedbackSubmitRequest` | `POST /activity-review/submit-feedback`, the admin review form; its snapshot is stored with the report and its request closed (2026-11-09) |
| `DisplayNameUpdateRequest` (was `UserUpdateSchema`) | `POST /api/user/display-name`, the Account card on `/settings` (2026-11-12). Narrowed to `display_name` alone; the fields it lost are below |
| `GoalProgressUpdateRequest` | `POST /api/goals/{uid}/progress`, the goal page's "Save progress" form (2026-11-12): the figure, its date, and the optional `note` (2026-11-13), stored on the history entry the write appends |
| `MilestoneCreateRequest` | `POST /api/goals/{uid}/milestones`, the goal page's "Add milestone" form (2026-11-12). `target_date` became optional; the fields it lost are below |
| `MilestoneUidRequest` | `POST /api/goals/{uid}/milestones/complete` and `/milestones/reopen`, the Complete button on each open milestone and the Reopen button on each reached one (2026-11-12). Narrowed to `milestone_uid`: the service finds the milestone by uid under the goal's lock |
| `GoalHabitLinkRequest` | `POST /api/goals/{uid}/habits`, the goal page's "Link a habit" form (2026-11-13). Gained `essentiality` (the tier it links at, default supporting); the field it lost is below |
| `HabitEssentialityChangeRequest` | `POST /api/goals/{uid}/habits/essentiality`, the tier select on each linked habit (2026-11-13); the field it lost is below |
| `HabitSystemUpdateRequest` | `POST /api/goals/{uid}/habits/system` (2026-11-13), JSON only: no page control replaces the whole system. A full replace: the four lists are every habit the goal keeps, a tier left out is empty (the lists default to empty, not `None`) |

### The fields the goal models lost (2026-11-12)

| Field | Verdict |
|---|---|
| `GoalProgressUpdateRequest.notes` | **bound again as `note` (2026-11-13, ruled by Mike: "A note should get a place on the goal page, as a field on the progress form, shown beside a progress history the page would start displaying").** The note now rides the `progress_history` entry the write appends, and the goal page lists that history. `metadata.progress_notes` and its one reader, `get_goal_progress`, are retired |
| `MilestoneCreateRequest.target_value` | retired: no code reads `Milestone.target_value`. The field is still on `Milestone` |
| `MilestoneCreateRequest.required_knowledge_uids` | **staged.** `Milestone.required_knowledge_uids` has one reader (`GoalTaskGenerator` copies it into a generated task's metadata), and no door writes it. A door needs the Ku admitted as the link doors admit one, and a picker on the page |
| `MilestoneUidRequest.achieved_date` | retired: a milestone's date is stamped by the write, today in the user's zone, on its first completion only |
| `MilestoneUidRequest.notes` | retired: `Milestone` has no field to hold one |

### The fields the habit-system models lost (2026-11-13)

| Field | Verdict |
|---|---|
| `GoalHabitLinkRequest.weight` | retired: nothing reads a `SUPPORTS_GOAL` edge's `weight`. Every door still writes it 1.0 |
| `HabitEssentialityChangeRequest.reason` | retired: there was nowhere to store it. `ui/ui_types.py`'s `HabitMigration` (a tier change's from, to, when, why) had no producer and no reader, and went with it |

### The fields `UserUpdateSchema` lost (ruled 2026-11-12)

Six retired, each with the live means that does its job; one is staged.

| Field | Verdict |
|---|---|
| `active_entity_uids`, `archived_entity_uids` | retired: each activity's own status says whether it is active or archived |
| `pinned_entity_uids` | retired: `PINNED` edges, written by the Ku page's Pin button through `/api/user/pins` |
| `current_goals` | retired: the learner's owned goals, each with its status |
| `achievements` | retired: a goal's own achieved status, and the habit streak badges |
| `settings` | retired: the typed `UserPreferences`, saved by `POST /settings/save` |
| `interests` | **staged: design.** Three representations exist and no door writes any: `User.interests`, `UserPreferences.preferred_subjects`, and `INTERESTED_IN` edges (`UserBackend.express_interest_in_knowledge`). It waits on choosing one; the edge is recommended, since family lives in edges. The staged `UserFilterSchema` filters on `interests` too |

The `User` and `UserDTO` fields behind these verdicts are still on the models; deleting them is a
later row. So is an admin's edit of another user's name from `/admin/users/{uid}`.

## Register

A wiring door binds its model and takes its row out.

| Model | File | Verdict | Why |
|---|---|---|---|
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
