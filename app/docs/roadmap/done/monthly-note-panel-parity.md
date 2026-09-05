---
title: "Calendar Periodic-Notes Arc Follow-up — Monthly-Note Panel Parity"
updated: 2026-09-05
status: "done"
registered: 2026-08-07
ruled: 2026-09-05
trigger: "lived monthly-note use wants the panel the weekly note has"
check: "product need, not a data threshold"
---

# Calendar Periodic-Notes Arc Follow-up — Monthly-Note Panel Parity

*Former case file for the [deferred-work.md](../deferred-work.md) entry of the same name —
ruled and shipped 2026-09-05; nothing in it remains open.*

Extracted 2026-08-07 from [`calendar-periodic-notes-arc.md`](calendar-periodic-notes-arc.md)
(all four PRs shipped 2026-08-03): the weekly note got its read-only planning panel; the
monthly note deliberately did not — "monthly-note panel parity is a follow-up, not in-scope,"
gated on lived use.

## Ruling 2026-09-05 (Mike): build it

The trigger was re-derived before the ruling, and had **not** fired: the founder vault's
`periodic_notes/Monthly/` held zero files (the `t_monthly.md` template had never been
instantiated), and the live graph held two `ue:monthly:` notes — June and August 2026, both
minted by the calendar's month-header door, both with empty content — against six weekly
notes, four of them written and edited within the day. Mike ruled to build the panel
regardless of measured use, the parity being cheap: the weekly panel's producer
(`CalendarService.get_planning_items`) is range-agnostic and the monthly UID contract
(`YYYY-MM`) already agreed across the app door, vault ingestion (`month_of`) and the sidebar.

## What shipped

- `ui/journals/week_panel.py` → `ui/journals/period_panel.py` (One Path Forward — no
  weekly-only module survives). `planning_period(entry_kind, period_key)` is the one
  place that knows which note kinds plan and how their keys parse: weekly → the ISO week,
  monthly → the calendar month (`monthly_period_start`, which also replaces the sidebar's
  hand-rolled `split("-")` parse), daily → `None` (the day lens IS its panel). `PlanningPanel`
  renders either period with the same pair vocabulary, day-lens doors, read-only contract
  and v1 habit exclusion; the panel `id` is `planning-panel`.
- `/journals/{entry_uid}` passes the panel for weekly AND monthly notes through one branch;
  `PeriodicNotePage(planning_panel=…)`.
- The quarterly/yearly notes ([`quarterly-yearly-periodic-notes.md`](quarterly-yearly-periodic-notes.md))
  took that inherited answer the next day: one `planning_period` branch each, plus a
  `groups_by_month` flag those two long periods set and the weekly/monthly panels do not.
