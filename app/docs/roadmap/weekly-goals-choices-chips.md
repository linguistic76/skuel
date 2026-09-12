---
title: "Goals and Choices as Weekly-Calendar Chips"
updated: 2026-09-11
status: "deferred — founder wish recorded; contradicts three standing rulings"
registered: 2026-09-11
trigger: "lived use of the priority-lens weekly view (calendar-priority-lens-arc C1) wants high-priority goals and choices on the grid"
check: "product need, not a data threshold — re-elicit after living with the week view; a ruling must name M4, R2 and S1 by letter"
---

# Goals and Choices as Weekly-Calendar Chips

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when
nothing in it remains open.*

## The wish

Recorded 2026-09-11 while ruling the
[calendar priority-lens arc](calendar-priority-lens-arc.md): after the weekly view shows high+medium
events, high+medium habits and high tasks, the founder would "ultimately" like **high-priority goals
and choices** on it too. Ruled **deferred** the same day (ruling 3): it is recorded here rather than
built, because building it silently would override three standing rulings.

## What it contradicts

| Ruling | Text | Where |
|---|---|---|
| **M4** (habit-rhythm arc) | "Goals, Choices, Principles do not apply as weekly-calendar filters — a Goal or Choice reaches the grid only by being marked as an Event or Task." | [`done/habit-rhythm-arc.md`](done/habit-rhythm-arc.md) |
| **R2** (periodic-notes arc) | "Choices+Principles live in the periodic note, not as chips — the compass travels with the writing, not the grid." | [`done/calendar-periodic-notes-arc.md`](done/calendar-periodic-notes-arc.md) |
| **S1** (periodic-notes arc) | The legend vocabulary is four kinds (Event, Task, Habit, Milestone); "Choices+Principles get no swatch." | same |

## What already exists

- **Goals already reach the grid as Milestones** (act-from C5): a goal with a `target_date` renders an
  all-day Milestone chip on that day. The priority-lens arc keeps Milestones on the WEEK view at
  priority ≥ medium. A goal *without* a target date has no day to sit on — "high-priority goals on the
  week" therefore means either the existing Milestones (already there) or a new dateless rail, which is
  a different design.
- **Choices carry `decision_deadline` / `decided_at`** (`core/models/choice/choice.py:80-81`), so a
  Choice chip has a candidate placement date. Nothing renders it today.

## What a ruling must decide

1. Goals: is the existing Milestone (target-date) chip the answer, or is a dateless "goals in play this
   week" rail wanted? The former is done; the latter is not a calendar chip.
2. Choices: which date places a Choice (deadline vs decided)? Does a Choice chip amend R2's "compass
   lives in the note" or sit beside it?
3. Legend: a fifth kind (Choice) amends S1 and the per-view legend of the priority-lens arc.

## Enable when

Lived use of the priority-lens week view (arc C1 shipped) misses goals/choices on the grid — a product
need, elicited explicitly, with M4/R2/S1 amended by letter in the ruling.
