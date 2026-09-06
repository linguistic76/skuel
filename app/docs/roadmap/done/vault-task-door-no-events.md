---
title: "The Completion Cascade Does Not Reach Every Door"
updated: 2026-09-06
status: done
registered: 2026-08-24
ruled: 2026-09-06
---

# The Completion Cascade Does Not Reach Every Door

*Shipped 2026-09-06 (#1287 shape, #1288, #1289, #1290, and this docs close-out). Registered
2026-08-24 as "Vault Task Door Publishes No Task Events"; left the live folder when the last of
the three defects closed. Kept as the record of why the cascade is shaped the way it is — and of
the two alternatives that were rejected on the way.*

The trigger fired 2026-09-06 and the door was read; the gap the registration named was real but
**narrower in one direction and wider in two others** than it said. This file records what the
code did, what it does now, and why.

## What shipped

| Defect | Closed by | Where the contract now lives |
|---|---|---|
| 1 — born-completed creates publish no completion event | #1288 | `TasksCoreService._publish_born_completed` and its Goal/Event siblings |
| 3 — `last_completion_at` is not monotone | #1288 | `CrossDomainBackend.stamp_productivity_completion` (a `CASE` max, no APOC) |
| 2c — the validator admits an illegal status target | #1289 | `IngestionValidator.validate_entity_data`, against `EntityType.<T>.valid_statuses()` |
| 2a/2b — the vault door skips the completion event and the reopen-clear | #1290 | `core/services/ingestion/status_transitions.py` + `UnifiedIngestionService._apply_status_transitions` |

Two obligations were found while building it and are **still open**, each with its own case file:
[the goal-progress edge nothing writes](../goal-progress-reads-an-unwritten-edge.md) and
[ingest transition-obligation durability](../ingest-transition-obligation-durability.md) — the vault
door's post-persist announcement has no outbox, so a read-back failure loses the announcement
rather than the ingest.

## What the registration got wrong

It said checkbox/DSL **extraction**-created tasks "go through the activity services and DO
cascade — only the frontmatter bulk-upsert door is silent." They cascade `TaskCreated` only.

A `- [x]` line converts to `TaskCreateRequest(status=COMPLETED, completion_date=✅date)`
(`core/services/dsl/activity_domain_converters.py:127`) and reaches
`TasksCoreService.create_task`, whose announcement step `_publish_created`
(`core/services/tasks/tasks_core_service.py:619`) publishes `TaskCreated` and the ADR-074
embedding request — **and no `TaskCompleted`**. `GoalsCoreService._publish_created` and
`EventsCoreService`' sibling have the identical shape.

So an entity **born completed** is silent at the *service* door too, and that is the door
carrying the live traffic: the vault holds **zero** real `type: task` frontmatter files (four
matches, all code examples and templates). `get_productivity_analytics`' own docstring already
named "a task created already completed" as a drift source; this is that sentence's cause.

## The three defects, as they were

**1 — Born-completed creates published no completion event.** `create_task` / `create_goal` /
`create_event` published only `*Created`. Every `TaskCompleted` subscriber therefore skipped a
task that arrived already done: goal-progress recompute, PS-engagement auto-complete, context
invalidation, the Prometheus `entities_completed{task}` counter, and the `ProductivityAnalytics`
stamps. Reached by the DSL/checkbox extractor and by any API create carrying
`status: completed`.

**2 — The vault bulk door skipped the whole status guard, not just the events.**
`UnifiedIngestionService` → `BulkUpsertBackend.upsert_with_relationships`
(`adapters/persistence/neo4j/bulk_upsert_backend.py`) MERGEd and returned `count(n)`. It never
called `update_with_status_guard`, so **all three** of that primitive's jobs were skipped at this
door (ADR-087):

- *no completion event* — nothing knows a prior status, and without one an honest publish is
  impossible: a `--force` re-ingest of N completed files must publish **zero**;
- *no reopen-clear* — a file edited from `status: completed` to `status: in_progress` strands
  `completion_date` / `achieved_date` / `completed_at` on a non-completed entity, breaking the
  invariant that the stamp is non-null exactly when the entity is completed;
- *no status-target legality* — the ingestion validator's vocabulary gate
  (`core/services/ingestion/validator.py:216`) checks enum **membership** only, so
  `type: principle, status: completed` passes it although COMPLETED is not in
  `EntityType.PRINCIPLE.valid_statuses()`.

**3 — `stamp_productivity_completion` was not monotone.**
`SET analytics.last_completion_at = datetime($occurred_at)`
(`adapters/persistence/neo4j/cross_domain_backend.py`) was unconditional. That is correct only
while every publisher's `occurred_at` is *now*. The moment an authored `✅` date publishes, an
out-of-order batch moves "when did this user most recently complete something" **backward**, so
the fix rode with the change that first backdated `occurred_at`.

## Why "all 5 stamping domains" splits into 3 and 5

The scope was ruled 2026-09-06 as all five stamping domains. Only three of them have an
entity-completion event to publish, and the other two must not be given one:

| Domain | update-chokepoint publish on transition INTO completed | entity-completion event exists? |
|---|---|---|
| Task | `TaskCompleted` | yes |
| Goal | `GoalAchieved` | yes |
| Event | `CalendarEventCompleted` | yes |
| Habit | none | **no** — `HabitCompleted` is a logged daily *occurrence* (it feeds the `total_completions` tally and the streak services), not the habit entity retiring |
| Choice | none | **no** — `ChoiceMade` is the DRAFT→ACTIVE *decide* moment published by `make_choice`, a different moment from COMPLETED |

A new `HabitFinished` / `ChoiceCompleted` would have zero subscribers — staged bloat, not a fix.
So **defect 1 and the event half of defect 2 are Task/Goal/Event**, while **the status-contract
half of defect 2 is all five plus Principle's legality gate**.

## The shape that was built

Four changes, in this order.

1. **Born-completed creates cascade** (Task/Goal/Event). The domain's completion event is
   published after `*Created` when the created entity's status is COMPLETED. A create has no
   prior, so it is unambiguously a transition into completed — `is_repeat=False` for Task, no
   prior-status machinery needed. `occurred_at` is the entity's authored stamp, falling back to
   now. Carries defect 3, because this is what first backdates `occurred_at`.
2. **The validator refuses a status the entity type does not allow** — `valid_statuses()`
   membership, pre-persist, no Cypher.
3. **The bulk door learns its prior status.** The node-upsert template splits the MERGE from the
   property write so the prior status is read *under the node's write-lock* (the ADR-087 shape,
   not a pre-read) and returns it per row. Post-persist then applies the reopen-clear for all
   five stamping domains and publishes the three completion events on genuine transitions only.
4. **Docs** — several docstrings stated this gap as permanent and stopped
   (`core/events/task_events.py`, `core/services/cross_domain_analytics_service.py`,
   `adapters/persistence/neo4j/cross_domain_backend.py`, `adapters/inbound/analytics_api.py`,
   `docs/domains/tasks.md`, and the premise of
   `scripts/backfill_productivity_completion_stamps.py`, whose reason for existing is narrowed to
   pre-fix history rather than removed).

## Rejected

**Deriving the stamps at read.** `get_productivity_analytics`' existing traversal already
computes `completed_on` per completed task, so `min()` / `max()` would derive both stamps in the
same read — exactly what `scripts/backfill_productivity_completion_stamps.py` reconstructs
offline — and the stored stamps, their writer, the `:ProductivityAnalytics` node and the backfill
script could all go. It is the cheapest option and it is what #1142 chose for the *count*. It was
rejected because it fixes **only** the stamps: goal progress, PS-engagement auto-complete and
context invalidation stay silent for every born-completed entity, which is the larger half of the
bug. Revisit only if the event half is abandoned.

**The cost this carried while open:** completion stamps drifted stale, and the goal-progress /
PS-engagement / context-invalidation cascade did not run, for every entity that arrived already
completed through the DSL, API-create or vault-frontmatter doors. `./dev
backfill-productivity-stamps` fills that history — and stays useful afterwards, because the vault
door's announcement still has no outbox
([ingest transition-obligation durability](../ingest-transition-obligation-durability.md)).
