---
title: "HabitEventScheduler Stamps a Goal on a Field Event Does Not Have"
updated: 2026-09-05
status: "registered"
registered: 2026-09-04
trigger: "the next HabitEventScheduler touch, or a Habit→Event→Goal reader that comes up empty"
check: "git grep -n \"fulfills_goal_uid\" core/services/habit_event_scheduler.py — the type: ignore[attr-defined] line is the marker"
---

# `HabitEventScheduler` Stamps a Goal on a Field `Event` Does Not Have

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`core/services/habit_event_scheduler.py` (`_generate_events_for_habit`) sets
`event.fulfills_goal_uid = <first linked goal>` under a `# type: ignore[attr-defined]`. `EventDTO`
declares no such field, and the dict door it persists through (`event.to_dict()` → `dto_to_dict` →
`asdict`) serialises declared fields only — so the stamp never reaches the node. Verified 2026-09-04
against the live graph: 0 Event nodes carry `fulfills_goal_uid`. The goal list DOES land, as
`metadata.supports_goals`, which no reader consults either. The Event→Goal link SKUEL reads is the
`(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` edge (`core/services/events/_goal_links.py`).

**The real work:** write that edge post-persist in `schedule_events_for_habit` — one per goal in
`HabitRelationships.linked_goal_uids`, admitted through `keep_permitted_link_edges` like every other
create-door link — and delete the dead stamp with its `type: ignore`. Surfaced while building the
Task `FULFILLS_GOAL` dual-write; ruled *verify, report, don't build* in that contract.
**Trigger:** the next `HabitEventScheduler` touch, or a Habit→Event→Goal reader that comes up empty.
**Named cost:** habit-scheduled events never count toward the goals their habit supports; the
`type: ignore` hides the field mismatch from mypy.
