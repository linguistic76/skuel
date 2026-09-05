---
title: "Periodic-Note Doors — one \"Notes\" picker on the calendar and Today toolbars"
updated: 2026-09-05
status: "done"
registered: 2026-09-05
ruled: 2026-09-05
trigger: "Mike: a top-level entry for the quarterly and yearly notes"
check: "shipped 2026-09-05 — chosen from four rendered options"
---

# Periodic-Note Doors — one "Notes" picker

*Shipped 2026-09-05. Additive to `quarterly-yearly-periodic-notes.md`; the period ladder
inside a note is unchanged.*

> **Where the picker lives now:** the navbar, not the calendar toolbar — Mike moved it the
> same day. The component is `ui/layouts/period_notes.py`, and the viewed period it follows
> is read off the request path instead of being passed in by the surface. Everything below
> about the choice (why one disclosure, why the mixed row rule, why not four icons) still
> holds; only the host changed.

## The ask

Mike, after #1277 shipped the quarterly and yearly notes: *"I want a top-level entry — I am
not sure how this is to work to have it look good, I want a simple icon to click on for
quarterly note + an icon for yearly note."*

The notes' only door was the **period ladder** in a periodic note's own sidebar, so reaching
the quarterly note meant being inside a periodic note first — two clicks from `/cal`.

## What was actually wrong

Not the missing button — the **crowding**. The Week and Month toolbars already carried two
note pills ("Monthly note" + "Daily note"); two more would make four in one row, and the
cluster already wraps on a phone because it is wider than a 375px viewport. Adding two icons
would have made a live mobile constraint worse.

And there is no icon to add. Of the 159 marks in `ui/components/_icon_data.py` none says
QUARTER or YEAR; the nearest candidates (`calendar-range`, `globe`) read as generic calendar
furniture, and two near-identical glyphs side by side communicate nothing.

## The ruling (Mike, 2026-09-05)

Four options were rendered with the real components against the real Tailwind — icon-only
squares, text marks (`Q3` / `2026`), one picker, and two new sidebar rungs — and shown as
desktop plus 390px-phone screenshots. Mike chose the **picker**.

**The whole note family collapses into one control.** Four pills become one; all five periods
(daily → yearly) are one click from `/cal/week/*`, `/cal/month/*` and `/today`. It is the only
one of the four that does not add a wrapped row on a phone.

**Which period each row opens** (the fork most easily missed): the row for the surface's OWN
period follows the VIEWED period — the month view's Monthly row opens the month on screen,
preserving exactly what the replaced "Monthly note" pill did. Every other row opens the
CURRENT period. Mike ruled "always the current one" for quarterly and yearly specifically;
extending that to the view's own row would have been a silent regression, so it was not.

The trailing short label on each row (`Sep 5`, `W36`, `March`, `Q3`, `2026`) is what makes the
mixed rule legible rather than surprising: the row heading names the KIND, the label names the
PERIOD, so a row that does not follow the view says so on its face.

## Shape

- `ui/journals/period_links.py` — `period_link(kind, ref_date) -> PeriodLink(href, label,
  short_label)`, the ONE derivation of a periodic note's URL. Both doors read it: the ladder
  (`_period_rung` now delegates) and the picker. Deriving a quarter boundary twice is how the
  two would drift apart, invisibly on either page alone.
- `ui/calendar/components.py` — `_period_note_picker`; `calendar_nav_cluster` /
  `create_calendar_toolbar` now take `own_kind` + `own_date` instead of
  `note_href`/`note_label`/`daily_note_href`.
- `ui/primitives.py` — `dropdown_menu(align=…)`: the shared shell pinned BOTH edges, which is
  wrong for a menu wider than its small trigger. `"right"`/`"left"` anchor one edge. The
  activities priority dropdown's `cls="w-36 right-auto"` override was the same need,
  hand-patched; it now passes `align="left"`.

**A disclosure, not an ARIA menu.** Every row is a plain navigation link, so Tab walks them
and no arrow-key roving has to be hand-rolled (Alpine's focus plugin is not vendored). The
trigger carries `aria-expanded` + `aria-controls`; Escape closes and returns focus to it.

## Verified live

Driven through CDP against the running app (not asserted from markup): closed at load
(`display: none`, `aria-expanded="false"`), click opens (5 rows, right edge inside the
viewport), Escape closes and restores focus to the trigger, click-outside closes. On
`/cal/month/2026/3` the Monthly row resolves to `/journals/monthly/2026/3` while the quarterly
and yearly rows resolve to the current Q3 and 2026.
