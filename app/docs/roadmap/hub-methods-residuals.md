---
title: "Hub Methods Build — Registered Residuals"
updated: 2026-10-10
status: "registered"
registered: "2026-10-08 to 2026-10-09 (the F8 rows — the hub methods, realized)"
trigger: "the next touch of the subsystem an item names (each item carries its file and line), or the quarterly review walk"
check: "re-read each item at its cited line; an item whose code no longer matches its description moves to done/ or is struck"
---

# Hub Methods Build — Registered Residuals

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The defects the F8 rows (the hub methods, realized — PRs #1510–#1520) found beside the hub and
registered rather than fixed. Every one was re-verified live on `main` `7be40f00d` at the docs
close (2026-10-09). The file and line are where the defect is, not where the fix goes; the hub
methods themselves and their doors are described in
[USER_CONTEXT_INTELLIGENCE.md](../intelligence/USER_CONTEXT_INTELLIGENCE.md) and the staged
second door in [askesis-intelligence-doors.md](askesis-intelligence-doors.md).

## Readers that mean something other than what they read

1. **`get_ready_to_learn_for_user` treats the KEYS of `knowledge_mastery` as mastered.**
   `core/services/ps/ps_context_service.py:77` (and the same line again at `:148`, in
   `get_learning_gaps_for_user`) — `mastered_uids = list(context.knowledge_mastery.keys())`, then
   `find_ready_to_learn(mastered_uids, …)`. The map holds every Ku with a mastery level,
   IN_PROGRESS ones included, so a Ku the user is studying is never offered as ready to learn,
   and a Ku whose only prerequisite is in progress is offered as if it were met. The populated
   analogue is `context.mastered_knowledge_uids`. Third source of the daily plan's learning slot
   and of hub method 1; found by F8-6 part 1.

## Reads that swallow their own failure

2. **`get_learning_tasks_for_user` turns a failed read into an empty answer.**
   `core/services/tasks/tasks_planning_service.py:400` — inside the per-Ku loop,
   `if tasks_result.is_error: continue`, so a backend failure on every Ku returns `Result.ok([])`
   and the caller (hub method 1's application reads) cannot tell "no tasks" from "the read
   failed". A derived list is only as honest as its failure branch. Found by F8-6 part 2.

## Hydration that cannot succeed

3. **`get_model_from_rich_context(…, EventDTO, Event)` cannot hydrate a rich event.**
   `core/services/user/rich_context.py:77` — the rich `entities_rich["events"]` item carries
   Neo4j `Time` values that reach `datetime.combine` in the DTO conversion and raise. No caller
   asks for an Event today (the three callers hydrate habits and goals), so the defect is latent;
   the first event-hydrating caller will hit it. Found by F8-6 part 2.

## Link writers outside the one invalidating chokepoint

4. **The lateral-relationship doors and the backend-direct link writers publish no
   `EntityLinksChanged`.** The one publisher is
   `core/services/relationships/unified_relationship_service.py:350` (`create_relationship` /
   `delete_relationship`, F8-6 part 2b), which drops the owner's cached context on any link made
   through it. `LateralRelationshipService.create_relationship`
   (`core/services/lateral_relationships/lateral_relationship_service.py:154`) writes through its
   own backend and holds no event bus; the Task dependency writer (`DEPENDS_ON`) is
   backend-direct too. A link made through either leaves every link-derived context field
   (`habits_by_goal`, `goal_knowledge_required`, …) stale for up to the 5-minute TTL, which the
   Insights cards make visible. Fix at those writers, publishing the same event. Found by F8-6
   part 2b (Codex P2 there, declined as out of that PR's scope).

## Projections that hard-code a figure

5. **`get_next_action` reports `blocked_items_count: 0` for every user.**
   `core/services/user/user_context_service.py:324` — the `ContextInsights` row is a constant
   because the projection holds only the `DailyWorkPlan`, which carries no blocked list. The
   rich context the plan was built from is in the cache (`UserService.peek_cached_context`),
   and its `blocked_task_uids_or_empty()` is the figure; or the plan grows the field. Noted in
   the skills review (`plans/skills-review-2026-09.md`), left standing by F8-7 (a docs PR).

## Resolution

Strike an item when its cited code no longer matches its description — fixed, deleted, or
re-registered in a nearer case file — and move this file to `done/` when every item is struck.
