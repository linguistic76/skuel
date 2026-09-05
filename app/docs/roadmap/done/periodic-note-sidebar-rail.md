---
status: done
ruled: 2026-09-05
registered: 2026-09-05
updated: 2026-09-05
---

# Periodic-note sidebar: week rail + period rail

*Shipped 2026-09-05. Supersedes the period ladder from `quarterly-yearly-periodic-notes.md`
and completes the makeover that `period-notes-toolbar-picker.md` started at the navbar.*

## Why

Periodic Notes became a first-class domain — its own navbar door, five period kinds — but
its own page could still only be *entered*, not *moved through*. The sidebar had:

- a **ladder** of "up" links (`↑ 2026`, `↑ Q3 2026`, `↑ September 2026`, `↑ Week 36`) that
  showed only the periods *wider* than the note, changed shape on every kind, and could not
  step sideways at all
- a **mini month** whose day cells opened daily notes and whose weeks opened nothing
- a **bottom bar** that stepped one period — whichever the note happened to be

So there was no way to reach the previous month's note from a monthly note without going
through the calendar, no way at all to step quarters or years, and three different-shaped
navigation affordances to read before you knew which one moved you.

Mike's ruling (2026-09-05): the ladder goes; week numbers move into the calendar the way the
full month view already does them; monthly, quarterly and yearly each get an icon and
prev/next arrows.

## What shipped

**One rail, all five periods** (the layout Mike chose over keeping the bottom bar). The
sidebar is now two pickers with no overlap:

| Surface | Opens | Steps |
|---|---|---|
| Mini month — day cells | the daily note | — (the grid *is* the picker) |
| Mini month — leading ISO-week rail | the weekly note | — |
| Period rail — one row per kind | that period's note | ‹ › to its neighbours |

- The **week rail** is the mini form of `create_month_grid`'s (`ui/calendar/components.py`),
  down to the Monday-first columns the ISO week numbers depend on — the sidebar now teaches
  the same gesture as the calendar it shrinks. A weekly note marks its own number.
- The **period rail** shows all five rows on every note, with the note's own row marked
  (`aria-current="page"`). A rail that changed shape per note is a rail you re-read every
  time; five fixed rows are one mechanism to learn. The bottom bar is deleted — it was the
  duplicate.
- Icons name the kind so the text is free to name the period: `sun` / `calendar-range` /
  `calendar-days` / `layers` / `orbit`, widening zoom. (`orbit` is new to `ICON_PATHS`;
  `scripts/gen_icons.py` regenerated.)
- The sidebar widened 220px → 240px and day cells shrank 28px → 24px to seat the week column.

**`period_step(kind, ref_date, steps)`** joins `period_link` in `ui/journals/period_links.py`
— the neighbour arithmetic behind every arrow, derived once for the same reason the URL is.
Month and quarter steps go through a flat period index, so December→January and Q4→Q1 carry
the year instead of overflowing a month number, and a step from the 31st anchors on the 1st
rather than raising `day is out of range`. The daily `label` was compacted to
`"Sat, Sep 5, 2026"` — the rail renders it in a ~150px column, and its only other consumer
is the picker's accessible name.

## What was deliberately NOT changed

**The cross-boundary anchor.** A weekly note still anchors on its Monday, so week 36 of 2026
(Aug 31 – Sep 6) shows *August* in the mini month with one day of the week visible at the
bottom. That is the documented anchor `period_link` and `CalendarService.get_planning_items`
already share; moving the calendar to the week's Thursday-month alone would make the rail say
"August 2026" over a September grid, which is worse than the near-empty row. Changing it
everywhere is a separate ruling.

## Files

| File | Change |
|---|---|
| `ui/journals/period_links.py` | `+ PERIOD_ICONS`, `+ period_step()`, compact daily label |
| `ui/journals/chat_page.py` | `_period_rail` replaces `_period_ladder`; `_note_anchor` extracted; `_mini_month_calendar` gains the week rail |
| `ui/components/_icon_data.py` | `+ orbit` (regenerated) |
| `tests/unit/ui/test_periodic_note_sidebar.py` | new — both pickers, the five rows, the year-boundary steps |
| `tests/unit/ui/test_period_links.py` | `+ period_step` boundaries and reversibility |
