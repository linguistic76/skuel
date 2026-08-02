# Calendar × Periodic Notes Arc — Rulings & Staged Contract

**Status:** STAGED 2026-08-02 — deliberately parked until the calendar act-from arc
(`docs/roadmap/calendar-act-from-arc.md`, PRs 1–5) completes. The rulings below are
SETTLED (founder elicitation, 2026-08-02); the scope items are CANDIDATES — the marked
ones get their own elicitation at pickup. This doc exists so the return path survives
context loss.
**Related:** `docs/roadmap/calendar-act-from-arc.md`, ADR-070 (VaultBridge), ADR-073
(journals / periodic-note storage), `core/services/user_entry/user_entry_service.py`
(`ensure_periodic_note`), `core/services/ingestion/user_entry_ingestion.py` (periodic
UID derivation), `core/services/dsl/activity_extractor.py`, `ui/calendar/components.py`
(`create_calendar_legend`), `static/js/skuel.js` (`calendarLegend`).

---

## Why this arc exists

Stepping back from the act-from arc, the founder examined the calendar's *function*:
it is the hinge between two views of daily life —

1. **Entity view (simplified):** domain pages (`/tasks`, `/habits`, …) → entities →
   calendar chips.
2. **Periodic-note view (organic):** capture starts unorganized ("a Muse being
   expressed"); random notes aggregate into Daily/Weekly/Monthly notes; those notes
   parse into Activity-domain entities; the entities render on the calendar; the
   calendar doors back to the notes.

Code-read verification showed the two views are ALREADY one designed loop — what is
missing is a settled display vocabulary, visible affordances, and a designed function
for the weekly/monthly notes. That is this arc.

## Founder rulings (settled 2026-08-02 — do not re-litigate)

- **R1 — The six Activity domains pair.** Tasks+Events (the day's commitments) /
  Goals+Habits (sustained direction) / Choices+Principles (the compass). Confirmed
  explicitly. Linear order remains Tasks, Events, Goals, Habits, Choices, Principles.
- **R2 — Display vocabulary organizes by pair.** Tasks+Events dominate the grid as
  chips; Goals+Habits appear as recurrence (habit chips) + milestones (goal target
  dates); **Choices+Principles live in the periodic note, not as chips** — the compass
  travels with the writing, not the grid.
- **R3 — Periodic notes are upstream of the calendar.** The note is the parse source;
  the calendar is the parse result plus the door back. Neither replaces the other.
- **R4 — Weekly and Monthly notes are planning-ahead surfaces** (goal setting;
  "planning helps me be more calm when the moment comes"). Review exists but serves
  forward thinking + accountability — it is not the primary act.
- **R5 — Note contents never render on the grid.** A link to the period's note is
  always nearby (tentative label "Details"; final label chosen at pickup).

## Verified ground truth (2026-08-02 code read + live graph + vault specimens)

- **Note↔calendar unification is real.** Day cell → `/journals/daily/{date}`, ISO-week
  rail → `/journals/weekly/{y}/{w}`, month header → `/journals/monthly/{y}/{m}`; each
  find-or-creates a periodic UserEntry (`ensure_periodic_note`). A vault note with
  `entry_kind` + date frontmatter derives the SAME `ue:daily:{user}:{date}` UID at
  ingestion — one node from either door. Derived periodic UIDs keep their colon form
  deliberately (the calendar-routes join contract; never normalize).
- **EXTRACT_ACTIVITIES already covers all six Activity domains** (plus Ku/PS/LP/
  LifePath): `activity_extractor.py` + `activity_domain_converters.py`. A periodic
  note can spawn entities in every bucket today.
- **The legend is interactive but looks static.** Swatches click-to-filter and
  hover-to-spotlight (`create_calendar_legend`, Alpine `calendarLegend`), with zero
  visual affordance. Its vocabulary is five RENDER types (Event, Task, Deadline,
  Habit, Milestone) — Task occupies two entries, Goal hides behind Milestone (emitted
  by nothing until act-from PR 5), Choices/Principles absent.
- **Affordance invisibility is the calendar's recurring disease:** static-looking
  legend, inert-looking day cells (which actually navigate to the daily note),
  display-only habit chips (act-from PR 3 fixes the chips).
- **Real specimens exist and already ingest.** The founder's personal vault holds
  daily + weekly periodic notes (plus Monthly/Quarterly/Yearly folders), unified in
  the graph. His templates already carry the required frontmatter (`type: user_entry`,
  `pipeline: extract_activities`, `entry_kind`, date/`week_of`) — the
  "Obsidian-native filename detection" seam is solved by template, not code.
  Structure observed (no personal content belongs in this public repo):
  - *Daily template:* Tasks section (obsidian-tasks checkbox lines with `📅` due,
    `🆔 sk_*` join key, `✅` done); a **Markwhen timeline code block** (recurring habit
    anchors + tagged time blocks, e.g. `#work`/`#finance`) with a Templater step that
    exports `.mw` toward `static/mw/daily` for a viewer; obsidian-tasks query blocks
    (due today / overdue / upcoming); Notes; End-of-Day Review prompts.
  - *Weekly template:* Weekly Focus (intention prose), Goals & Tasks (checkboxes),
    Notes, Weekly Review prompts. Matches R4 exactly.

## Candidate scope (shape at pickup; one PR each unless merged naturally)

- **S1 — Legend redesign in domain-pair language + visible interactivity.** Group or
  color the display vocabulary by R1 pairs; make filter/spotlight behavior
  discoverable (button affordance, hint, or tooltip). Resolve the Task/Deadline
  double-entry presentation within the Tasks+Events pair.
- **S2 — Visible note-doors.** Make the day-cell → daily-note navigation discoverable
  (R5's nearby "Details"-style link or equivalent affordance); keep the existing
  Weekly/Monthly note buttons; audit Today view for the same door.
- **S3 — Weekly note as planning surface** *(elicit mechanics at pickup)*. Designed
  function per R4: the place where next week's intentions become scheduled entities.
  Open: does planning flow through EXTRACT_ACTIVITIES lines, a guided section, or
  both? What does the weekly note show of the week's existing entities?
- **S4 — Parse contract from the real specimens** *(elicit at pickup)*. Decide what
  EXTRACT_ACTIVITIES should recognize beyond checkbox lines in periodic notes:
  section headings? which sections map to which domains? What stays
  prose-only (per R2, Choices/Principles may live as writing, or use explicit DSL
  markers only)?
- **S5 — Markwhen timeline** *(discovered, unruled — elicit first)*. The daily
  template already authors a structured day plan (time blocks, habit anchors) and
  exports it toward SKUEL's static dir. Whether SKUEL should read/render it (e.g. a
  future week-view time grid) is an open door, NOT a commitment. Note the act-from
  arc lists an hourly time grid as a non-goal; this is where that conversation would
  resume.

## Non-goals

- Finance as a seventh Activity domain — recorded founder wish ("I'd like that";
  budget as part of sustaining the work). The seed exists (Firefly sidecar ADR-052;
  `activity_extractor.py` names Finance for 7-domain completeness) but it is OUT of
  this arc.
- Rendering note contents on the grid (R5 forbids).
- Re-litigating Monday-start / ISO-week rail (PERMANENT) or any act-from arc choice.
- Background/watcher-based ingestion (ADR-070 Decision 9 stands — sync is
  human-initiated).

## Sequencing

1. Calendar act-from arc PRs 1–5 land first (this doc waits; its S1 depends on
   act-from PR 5 making Milestone truthful, and S2's day-cell work should not collide
   with act-from PRs 3–4 touching the same components).
2. At pickup: run the S3/S4/S5 elicitations, then promote candidates to a PR table in
   this doc (act-from arc format: per-PR acceptance against live cases).
