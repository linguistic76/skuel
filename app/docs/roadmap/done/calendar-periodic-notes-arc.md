# Calendar × Periodic Notes Arc — Rulings & Contract

**Status:** ✅ COMPLETE 2026-08-03 — all four PRs shipped the same day the arc went
active: #921 (PR 0, this contract), #922 (PR 1, legend), #923 (PR 2, weekly panel),
#924 (PR 3, parse contract + FULL-tier bridge bypass). Every PR carried a real Codex
verdict, considered and resolved; acceptance verified against live cases per the
table below. History: the staging gate cleared when the calendar act-from arc
completed (PRs 1–7 as #913–#917, #919, #920) and the pickup elicitations ran
2026-08-03 (rulings E1–E4 below). The rulings remain binding on future work.
**Related:** `docs/roadmap/calendar-act-from-arc.md`, ADR-070 (VaultBridge), ADR-073
(journals / periodic-note storage), `core/services/user_entry/user_entry_service.py`
(`ensure_periodic_note`), `core/services/ingestion/user_entry_ingestion.py` (periodic
UID derivation), `core/services/dsl/activity_extractor.py`, `ui/calendar/components.py`
(`create_calendar_legend`), `core/models/event/calendar_models.py` (`CalendarItemType`),
`adapters/inbound/journals_routes.py` (periodic-note page), `static/js/skuel.js`
(`calendarLegend`).

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
  always nearby. *(Label resolved at pickup: act-from C6 shipped the "Daily note" /
  "Weekly note" / "Monthly note" button family — that vocabulary is adopted; the
  tentative "Details" is retired.)*

## Pickup rulings (settled 2026-08-03 elicitation — do not re-litigate)

- **E1 — The legend speaks one word per kind; "Deadline" dies as a kind.** Founder:
  resolve Task's double entry "in the simplest most harmonious way possible that
  results in the double entry not occurring." Kind = Task; due = state. A due-but-
  unscheduled task keeps a visible urgency cue on its CHIP (a state marker, the way
  completed is a state) — ruled explicitly: the at-a-glance distinction survives, but
  as chip styling, never as a legend word.
- **E2 — Weekly planning is template-led.** Planning flows through checkbox/DSL lines
  in the vault weekly template (EXTRACT_ACTIVITIES parse — already live); SKUEL's
  weekly-note surface adds a READ panel of the week's existing entities. Forward
  planning happens in Obsidian; the app shows, for planning-against and
  accountability (R4). No app-side quick-add on the weekly note.
- **E3 — Parse contract = checkbox lines + explicit DSL markers, nothing else.**
  No section-heading→domain mapping, ever — a heading is prose, not a parse
  instruction. Choices/Principles become entities ONLY via explicit markers
  (a deliberate act; per R2 the compass is writing first).
- **E4 — Markwhen is DEFERRED.** The door stays open; reading/rendering the daily
  template's timeline is out of this arc and resumes as its own conversation (where
  the act-from arc's hourly-time-grid non-goal anticipated it).
  *(Resolved 2026-08-03: the S5 exploration ran and ruled RETIREMENT — no markwhen
  parsing/rendering ever; habitual time becomes Habit entity data instead. See
  `docs/roadmap/done/habit-rhythm-arc.md`, rulings M1–M7.)*

## Verified ground truth (2026-08-02 code read + live graph + vault specimens)

- **Note↔calendar unification is real.** Day cell date-number → `/journals/daily/{date}`,
  ISO-week rail → `/journals/weekly/{y}/{w}`, month header → `/journals/monthly/{y}/{m}`;
  each find-or-creates a periodic UserEntry (`ensure_periodic_note`). A vault note with
  `entry_kind` + date frontmatter derives the SAME `ue:daily:{user}:{date}` UID at
  ingestion — one node from either door. Derived periodic UIDs keep their colon form
  deliberately (the calendar-routes join contract; never normalize).
- **EXTRACT_ACTIVITIES already covers all six Activity domains** (plus Ku/PS/LP/
  LifePath): `activity_extractor.py` + `activity_domain_converters.py`. A periodic
  note can spawn entities in every bucket today.
- **The legend is interactive but looks static.** Swatches click-to-filter and
  hover-to-spotlight (`create_calendar_legend`, Alpine `calendarLegend`), with zero
  visual affordance. Its vocabulary is five RENDER types (Event, Task, Deadline,
  Habit, Milestone) — Task occupies two entries; Goal renders as Milestone (producer
  shipped in act-from PR 5); Choices/Principles absent (now sanctioned by R2).
- **Affordance invisibility was the calendar's recurring disease** — the act-from arc
  cured the day cells (click → day lens, C6) and the habit chips (per-day completion,
  C3); the static-looking legend is the last known instance (S1's target).
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

## Verified ground truth (2026-08-03 pickup code read)

- **S2 is resolved by act-from C6 — audit run, no code PR needed.** Day-cell empty
  space → `/today/{date}` and per-cell date numbers → `/journals/daily/{date}` in both
  views (`ui/calendar/components.py:495-547` month, `:577-606` week); both toolbars
  carry the Daily-note button beside the period-note button (`components.py:157-212`);
  the Today day-lens header carries the same door (`ui/today/page.py:161-162`).
- **Task's double entry, mechanically:** one task → ONE chip; `_task_to_calendar_item`
  types it `TASK_DEADLINE` only when `scheduled_date is None and due_date is not None`,
  else `TASK_WORK` (`calendar_service.py:689-692`). Labels/colors/icons live on
  `CalendarItemType` (`calendar_models.py:28-73`); legend filtering is pure CSS keyed
  off `data-item-type`, so collapsing the kind unifies filtering for free;
  `visualization_service.py:163-164` buckets tasks vs deadlines; `components.py:957`
  does a task-family membership check.
- **The extractor already speaks E3's shape.** The two parsed line shapes are checkbox
  lines (🆔 join key, ADR-070) and explicit `@context()` DSL prose lines; `@ku()`
  references resolve on any parsed line; all six domains have creators including
  `_create_choice`/`_create_principle` (`activity_extractor.py`). PR 3 is
  verify-against-specimens + close gaps + document — not green-field.
- **⚠️ The FULL-tier bridge pre-pass violated E3 for periodic notes** (Codex
  finding on this PR, code-verified — **CLOSED by PR 3**). When `dsl_bridge` was
  wired (FULL tier), `UserEntryProcessingService.process()` sent all non-checkbox
  prose to the LLM and appended the generated `@context()` lines before parsing;
  vault sync triggered this for every EXTRACT_ACTIVITIES entry. Unmarked
  periodic-note prose could therefore create entities — "inferred from writing",
  which E3 rules out. PR 3 closed this: periodic entries bypass the bridge
  pre-pass (gated on the shared `UserEntry.is_periodic_note()` model predicate);
  non-periodic entries keep it unchanged (the bridge is a sanctioned Digital
  enhancement elsewhere). Contract documented in `docs/dsl/DSL_USAGE_GUIDE.md`
  § Periodic Notes — The Parse Contract (cross-linked with the ingestion guide).
- **The weekly-note page is a bare editor today.** `/journals/{entry_uid}` renders
  `PeriodicNotePage` with an editable `PeriodicNoteFragment` (title + content) and
  nothing else (`journals_routes.py:1054-1105`) — PR 2's panel has a clean canvas.

## Scope (settled)

- **S1 — Legend redesign (PR 1).** Pair-grouped legend + one Task kind + visible
  interactivity. Chosen: swatches group under **Tasks+Events** and **Goals+Habits**
  (R1/R2; Choices+Principles get no swatch — the compass lives in the note);
  vocabulary = four kinds (Event, Task, Habit, Milestone); due-ness renders as a chip
  STATE cue (⏰/accent), not a kind (E1); filter/spotlight gains a discoverable
  affordance (control styling, hint, or tooltip — the PR picks the form).
  Implementation lean (the PR's fresh read settles the exact carrier): collapse
  `CalendarItemType.TASK_DEADLINE` per One Path Forward — due-ness travels on the item
  as state (flag/metadata → `data-` attribute + `calendar.css`), the item-details type
  pill says "Task", and `visualization_service`'s deadline bucket re-derives from the
  state flag.
- **S2 — Visible note-doors: RESOLVED** (see 2026-08-03 ground truth). No PR.
- **S3 — Weekly note as planning surface (PR 2).** Template-led (E2): the app's
  weekly-note page gains a read panel of the week's existing entities — the vault
  plans, the app shows. Panel v1 contract: the ISO week's **Tasks+Events** (due OR
  scheduled in-week, mirroring calendar C2 semantics) + **Milestones** (goal
  `target_date` in-week), grouped in pair vocabulary; each row links to its day's
  lens (`/today/{date}`) — acting happens there; the panel is read-only. Habits are
  deliberately excluded from v1 (daily recurrence is calendar texture, not weekly
  planning matter) — revisit only if lived use misses them. Monthly-note parity is a
  follow-up, not in-scope.
- **S4 — Parse contract (PR 3).** Per E3: recognized shapes = checkbox lines +
  explicit `@context()` DSL markers; nothing else, ever. Deliverables: verify the
  live contract against the real specimens (daily + weekly), close gaps (especially
  explicit-marker Choices/Principles in periodic-note prose), **gate the FULL-tier
  bridge pre-pass off for periodic entries** (see ground truth — unmarked prose must
  create nothing on EITHER tier; non-periodic entries keep the bridge), and DOCUMENT
  the recognized-shape contract where the docs architecture homes it (DSL usage guide
  or ingestion guide § periodic notes — cross-linked both ways).
- **S5 — Markwhen: DEFERRED** (E4). Recorded; out of arc. *(Since resolved —
  see `docs/roadmap/done/habit-rhythm-arc.md`.)*

## Non-goals

- Finance as a seventh Activity domain — recorded founder wish ("I'd like that";
  budget as part of sustaining the work). The seed exists (Firefly sidecar ADR-052;
  `activity_extractor.py` names Finance for 7-domain completeness) but it is OUT of
  this arc.
- Rendering note contents on the grid (R5 forbids).
- Markwhen timeline reading/rendering (E4 — deferred, its own future conversation).
- Section-heading→domain parse mapping (E3 rules it out permanently, not merely
  deferred).
- App-side quick-add on the weekly note (E2 — the vault plans; the day lens already
  owns task quick-add per act-from C6).
- Habits in the weekly panel v1; monthly-note panel parity (follow-ups gated on
  lived use).
- Re-litigating Monday-start / ISO-week rail (PERMANENT) or any act-from arc choice.
- Background/watcher-based ingestion (ADR-070 Decision 9 stands — sync is
  human-initiated).

## Standing conventions that bind every PR here

Fresh context per PR; branch from **updated** main (`git pull --ff-only` first);
`./dev format` + `./dev quality` + targeted tests; runtime verification with headless
Chrome against the live dev app (real Alpine, screenshot; assert after 2 rAFs with
`--run-all-compositor-stages-before-draw`) plus a live-graph spot check where data
changes; commit → PR → Codex review → consideration note → merge (standing
authorization). Monday-start + ISO-week rail PERMANENT. All chips render — legend
filters are the only hiding mechanism (#623). Derived periodic UIDs keep their colon
form (never normalize). Vault sync stays human-initiated (ADR-070 D9). No personal
vault content in this public repo — specimen shapes only.

## PR plan (contract)

All shipped 2026-08-03: PR 0 = #921 · PR 1 = #922 · PR 2 = #923 · PR 3 = #924.

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 0 | This doc (docs-only; summon Codex explicitly — the gate auto-passes docs PRs without a verdict) | Doc reflects E1–E4 + S2 resolution; PR table matches the rulings |
| 1 | S1 — pair-grouped legend; one Task kind (due = chip state); visible filter affordance | Legend shows Tasks+Events / Goals+Habits groups with four kind-swatches; a live due-only task renders as a Task chip WITH the due-state cue; clicking the Task swatch hides scheduled AND due-only task chips; hover spotlight unchanged; swatches read as controls (discoverable affordance); the item-details pill for a due-only task says "Task"; no legend entry for Choices/Principles; month + week views verified in headless Chrome |
| 2 | S3 — weekly-note page read panel (week's Tasks+Events + Milestones, day-lens links) | A live week's note shows that ISO week's tasks (due OR scheduled) + events + any milestone dated in-week, in pair vocabulary; rows link to `/today/{date}`; the panel is read-only; a checkbox task line with an in-week `📅` due date added to the vault weekly note appears in the panel after "Sync from Obsidian" (plan → entity → visible loop closed); daily/monthly note pages unchanged |
| 3 | S4 — verify + close gaps + document the periodic-note parse contract; periodic entries bypass the FULL-tier bridge pre-pass | A specimen-shaped note ingests: checkbox task line → Task; explicit `@context(choice)` line → Choice (and `@context(principle)` → Principle); unmarked prose creates NOTHING — including bare lines under a "## Goals" heading (negative control for the ruled-out section magic) — **with the FULL-tier bridge path active** (`dsl_bridge` wired), not just parser-only CORE; a non-periodic EXTRACT_ACTIVITIES entry still gets the bridge pre-pass (no regression); the recognized-shape contract is documented and matches behavior |

PR 1 is independent; PRs 2 and 3 are independent of each other (suggested order
1 → 2 → 3). Any PR that discovers a contract-breaking surprise updates THIS doc in
the same PR.
