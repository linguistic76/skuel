---
title: "HabitEventScheduler Stamps a Goal on a Field Event Does Not Have"
status: done
registered: 2026-09-04
ruled: "2026-09-23 (Mike): (a) a plural create-only input `Event.contributes_to_goal_uids`, written by the Events create primitive; accepted on POST /api/events/create; the streak-maintenance door carries it too; the scheduler's unread metadata keys are deleted"
updated: 2026-09-23
---

# `HabitEventScheduler` Stamps a Goal on a Field `Event` Does Not Have

*Fixed 2026-09-23 in the goal-link arc's PR 2. Registered as a
[deferred-work.md](../deferred-work.md) entry; the defect as found is kept below, followed by
what shipped.*

## The defect as registered

`core/services/habit_event_scheduler.py` (`_generate_events_for_frequency`) set
`event.fulfills_goal_uid = <first linked goal>` under a `# type: ignore[attr-defined]`. `EventDTO`
declares no such field, and the dict door it persists through serialises declared fields only —
so the stamp never reached the node. The goal list did land, as `metadata.supports_goals`, which
no reader consulted. The Event→Goal link SKUEL reads is the
`(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` edge, and nothing on the create path wrote it.

The registered plan — write the edge post-persist in `schedule_events_for_habit` — went stale
before it was built: by then the Events create path was one primitive
(`EventsCoreService._create_with_links`) whose ordering contract writes every edge BEFORE
`CalendarEventCreated` is published, because that event triggers a context rebuild that reads
the edges back and caches what it finds. A post-persist write from the scheduler would have
reintroduced that race.

**Found while fixing it:** bootstrap built the scheduler with no relationship service
(`relationship_service=None`, untyped), so `HabitRelationships` was always empty and the
goal branch — dead stamp included — never ran in production at all.

## What shipped

- **`Event.contributes_to_goal_uids: tuple[str, ...]`** — the edge's create-only, plural input,
  in `RELATIONSHIP_SKIP_FIELDS` so it never lands as a property, read off the INPUT entity (it
  does not survive the round-trip, like `reinforces_habit_uid`). The singular
  `contributes_to_goal_uid` stays the read-side projection.
- **`EventsCoreService._write_link_edges`** turns each uid into one `CONTRIBUTES_TO_GOAL`
  candidate (`allowed_labels={Goal}`, a repeated uid is one edge) in the same guarded batch as
  `REINFORCES_HABIT` / `CELEBRATES_GOAL` — admitted by `keep_permitted_link_edges` on existence,
  owner and kind, and written before the announcement.
- **`EventCreateRequest.contributes_to_goal_uids`** — the request door (`POST
  /api/events/create`) accepts it and sets it on the entity. Request-supplied UIDs, so the
  admission is what makes this safe: a cross-user or non-Goal uid is refused and logged, the
  event is created anyway.
- **`HabitEventScheduler`** takes the Habits relationship service as a REQUIRED, typed
  (`BaseRelationshipOperations`) dependency, reads `supported_goals` once per habit, and sets
  the goals on the entity at both doors — `schedule_events_for_habit` and
  `schedule_streak_maintenance`. An unreadable goal read schedules the events without goal
  links. The dead stamp, its `type: ignore`, and the unread `supports_goals` /
  `practices_knowledge_uids` / `contributes_to_mastery` metadata keys are deleted.
- **Backfill:** none needed — AuraDB (read-only count, 2026-09-23) held 6 Event nodes, 0 with
  goal metadata and 0 Event `CONTRIBUTES_TO_GOAL` edges.

**Readers switched on** (census 2026-09-23): none miscount once fed — the MEGA-QUERY's
`event_goal`, `cross_domain_backend`, the `get_goal_links_for_events` batch behind
`enrich_events_with_goal_links`, and the metrics calculator all de-duplicate. Goal progress does
not count Event edges (`GOALS_CONFIG` tallies Task `FULFILLS_GOAL` and Habit `SUPPORTS_GOAL`
only). Known lossy-but-correct readers: `/api/events/insights` reports one goal of several, and
the incoming `GOAL_CONNECTION_CONFIG` lists every scheduled occurrence on the goal's card.

Tests: `tests/unit/test_event_create_edges.py` (`TestEventContributedGoalEdges`),
`tests/unit/test_habit_event_scheduler_create_door.py`, and
`tests/integration/test_habit_event_goal_edges.py` — the ordering proof queries the graph from
inside a `CalendarEventCreated` subscriber.
