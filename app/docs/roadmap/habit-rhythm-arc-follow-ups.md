---
title: "Habit-Rhythm Arc Follow-ups"
updated: 2026-09-18
status: "deferred"
registered: 2026-08-07
trigger: "next touch of habits_scheduling_service for the duration follow-up"
check: "ride-along, not standalone"
---

# Habit-Rhythm Arc Follow-ups

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted 2026-08-07 from the completed arc when it moved to
[`done/habit-rhythm-arc.md`](done/habit-rhythm-arc.md) (M1–M7 all shipped, #927/#933/#934):
the arc is finished, these follow-ups are not. Each was left open by design, gated on lived
use rather than on work — the archive is the record, this register is the tracker.

## Habit rows in the weekly-note panel

**Closed 2026-09-18 — moot.** A5's backward-review half asked for habit rows in the
weekly-note planning panel; that panel was removed from the periodic-note page (the page now
carries the Tasks+ sidebar and the period navigator; the panel module and the
`get_planning_items` calendar read behind it are deleted). There is no panel to add rows to —
the backward look over a week's habits is the calendar week view's.

## Non-positive-duration follow-ups (arc PR 2)

The same habit rendered `0m` on `/today` while `habits_scheduling_service` proposes `15` —
two surfaces disagreeing about a non-positive `duration_minutes`. The `/today` half closed
with the day view (calendar-priority-lens arc D.1, 2026-09-12): the day renders habits as
the calendar's chips, whose block label reads a non-positive stored duration as unstated
(`CalendarService._habit_block_minutes`). What remains is the scheduling service's `15`.

**Enable when**: next touch of `habits_scheduling_service`; small enough to ride along.
