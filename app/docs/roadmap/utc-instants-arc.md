---
title: "UTC Instants Arc — Rulings & Contract"
updated: 2026-09-27
status: "active — ruled 2026-09-27; PR 0 merged, PR 1 next"
registered: 2026-09-27
ruled: 2026-09-27
---

# UTC Instants Arc — Rulings & Contract

**Status:** ACTIVE — ruled 2026-09-27 (founder rulings R1–R8). Eleven PRs, **one per fresh
context**. This document is the single source of truth for the arc, and the **Status** column of
the [PR contract table](#pr-plan-contract) is its progress ledger.
**Decision record:** [ADR-089 — Instants Are UTC; Days Belong to a Zone](../decisions/ADR-089-instants-utc-days-in-a-zone.md).
**Closes:** [Naive-Local Timestamps Read as UTC](naive-local-timestamps-read-as-utc.md) (the case
file that registered the defect; it moves to `done/` with this document).
**Related:** the neo4j-cypher-patterns skill's Pattern 10 and Key Rules #17/#18
(`.claude/skills/neo4j-cypher-patterns/PATTERNS.md`, rewritten at the close);
[ADR-087](../decisions/ADR-087-status-guarded-conditional-writes.md) (completion stamps go through
its guard); [ADR-070](../decisions/ADR-070-bidirectional-vault-bridge.md) (the vault's `✅ date`
is a calendar value); [ADR-080](../decisions/ADR-080-auradb-three-horizon-strategy.md) (one AuraDB
graph, written by the laptop and — once unparked — a UTC droplet).

---

## Intent

SKUEL records two kinds of time and has treated them as one:

- **Instants** — when something happened: created, updated, shared, submitted, completed, joined,
  viewed. A moment is the same everywhere; it should be stored once, in UTC, and never change when
  a person moves.
- **Calendar values** — which day it is for a person (due today, overdue, a habit's day, a daily
  note's date, a report's week) and how a moment reads to them ("3:40 PM", "2h ago"). These depend
  on where the person is.

Most writers stamp instants with the host's naive wall clock. Neo4j reads an offset-less stamp as
UTC, so on the development laptop (America/Vancouver, UTC−7) every such stamp reads seven hours
old: the activity-report cooldown never fires and a share made a minute ago reads "7h ago". Two
other clocks write true UTC — some into the same columns — and the laptop was at UTC+7 before
2026-03-27, so the stored corpus holds four cohorts. The arc makes every instant UTC, migrates the
stored cohorts, and makes every calendar concept ask one zone: the user's own, with an app default.

Mike moves to Thailand (UTC+7) for about eight months from late November 2026. After this arc,
switching zone in Settings changes what "today" is and how times read; nothing stored changes.

## Founder rulings (2026-09-27 — do not re-litigate)

| # | Ruling |
|---|---|
| R1 | **Route: aware-UTC Python is the destination, reached through a UTC process pin as a temporary bridge.** The pin makes every naive writer write UTC at once with no writer edits, so the cutover is small; the sweep to aware datetimes then runs behaviour-neutral under the pin. |
| R2 | **A per-user zone with an app default.** `SKUEL_TIMEZONE` (`.env`, an IANA name, default `America/Vancouver`, validated at boot) is the zone of anyone who has not chosen one and of system work acting for no user. Each user sets their own in Settings: a validated list plus **"Use this device's time zone"** (the browser's zone, one click). The six stored `"UTC"` values were never chosen (the field's old default) and are cleared to follow the default. **No mismatch banner** ("Your device is in Bangkok time — switch?"): left out. |
| R3 | **Provenance: the laptop was at UTC+7 until 2026-03-27 and America/Vancouver since, with nothing in between** (Mike). The migration classifies each row by writer, shape, sub-second precision and date; an unclassified row stops the run and is listed for Mike. **Accepted residual:** naive rows written by the Docker app (`./dev up`, a UTC process) in the sandbox era, where no server-clock stamp sits beside them to reveal it. |
| R4 | **Timing: the cutover (PR 4) lands before 2026-11-01 and before the laptop's zone changes for travel.** A stamp written at UTC+7 before the cutover would be a fifth cohort. No fall-back hour exists: tzdata 2026.3 (host, the venv's `tzdata`, AuraDB) puts America/Vancouver on permanent UTC−7 from 2026-11-01 02:00 — the script still reads any repeated hour as its first occurrence. |
| R5 | **Each writer keeps its storage shape.** The migration moves digits, never shapes: an offset-less string stays offset-less (its digits become UTC), a native stays native. A string gains an offset only when its writer turns aware in the sweep. Every comparison or ordering of a stamp coerces with `datetime()` (Pattern 10). One shape for instants is not this arc. |
| R6 | **Left alone:** stamps nested inside JSON metadata properties; authored days relabelled as UTC midnight (`…T00:00:00Z`); calendar days stored as naive midnights (`Habit.last_completed`, `HabitCompletion.completed_at`); the authored `+07:00` edge stamp. |
| R7 | **The stopped local Docker sandbox is disposable** — not migrated. |
| R8 | **The pin is removed at the close**, not kept as a boot assertion. Ruff `DTZ` and forced-zone tests are the standing guards. |

## Architecture (target, at the close)

1. **An instant in Python is an aware UTC `datetime`.** `now_utc()` in
   `core/utils/timestamp_helpers.py` is the one clock; default factories use it; a naive datetime
   from storage means UTC and is made aware at the parse boundary (`from_neo4j_node`,
   `dto_helpers`, `convert_neo4j_datetime`).
2. **An instant in the graph is UTC**, in whichever shape its writer produces (R5); every Cypher
   comparison or ordering of a stamp coerces with `datetime()`.
3. **A calendar value is local to a zone and never converted**: due and event dates, LOCAL TIMEs,
   habit days, daily-note dates, report-period tokens. "Today" is today in the current zone. A
   stored instant's day is its date in the current zone (Python `astimezone(zone).date()`; Cypher
   `date(datetime({datetime: datetime(x), timezone: $zone}))`). A local period over instants is
   queried by its UTC bounds. Cypher never computes "today" with `date()` — the day comes in as a
   parameter.
4. **The current zone** is the signed-in user's choice, else `SKUEL_TIMEZONE`, resolved once per
   request into a request-scoped context variable (the pattern of `auth_state_var` in
   `core/utils/auth_context.py`). Work done for a named user outside a request (a vault sync for
   the vault's owner, a report generated for a user) resolves that user's zone explicitly.
5. **Display** renders an instant in the current zone, absolute and relative.
6. **Guards:** ruff `DTZ` over `core/`, `adapters/` and `ui/`, plus a check for uncalled
   `datetime.now` references (`default_factory=datetime.now`, which `DTZ005` does not see); forced-
   zone integration tests under `America/Vancouver` and `Asia/Bangkok`.

## The bridge (from PR 4 to PR 9)

The process clock is pinned to UTC at the one import chokepoint every entry point shares (the app,
scripts, tests), so naive `datetime.now()` is the UTC wall clock and every naive writer writes UTC.
The stored corpus has been migrated to UTC. One constant, `STORED_INSTANT_CLOCK` (PR 3), tells the
edge helpers what a stored stamp's digits mean; from PR 4 it says UTC. Every PR after the cutover
is behaviour-neutral hygiene, so **the arc can pause at the bridge with no live defect** (R1).

---

## Verified ground truth (2026-09-27 — main `628c9c526`, AuraDB read-only)

A census workflow — 18 file slices and 5 tree-wide lenses, each followed by an adversarial
verifier, then a synthesis against a live AuraDB shape census — plus direct probes. Line numbers
drift: re-verify by symbol.

### Stored instants

128 stored properties hold an instant — 6,684 values:

| Cohort | Values | What it is | Migration |
|---|---|---|---|
| `L-str` — offset-less string holding the laptop's PDT wall clock | 1,098 | The mapper's `isoformat()` of a naive `datetime.now()` or default factory, across 57 properties: `created_at`/`updated_at` on Task, UserEntry, Choice, Event, Goal, Habit, Principle, Ku, PathStep, Exercise, Resource, Interaction, User, FormSubmission, ActivityReport, HabitCompletion, the `*Template.updated_at`, OWNS and the lateral edges; `ActivityReport.period_*`/`data_cutoff`, `Choice.completed_at`, `UserEntry.processing_completed_at`, `OWNS.last_accessed`, `ENROLLED_IN.target_completion`, `User.feedback_updated_at` | shift: America/Vancouver → UTC |
| `+07` — offset-less string written at UTC+7 | 6 | `User.created_at` ×3 and `User.updated_at` ×3, 2026-02-01..06 | shift: +07:00 → UTC |
| `L-nat` — native `Z` holding the laptop's wall clock | 125 | Cypher `datetime($now)` with `now = datetime.now().isoformat()`: EntryReport 3, Insight 20, Ku/PathStep `last_applied_date`/`last_reflected_date` 48, Notification 4, ProductivityAnalytics 2, RevisedExercise 2, SearchEvent 41, SHARES_WITH 1, SUBMITTED_TO_GROUP 2, UserEntry.updated_at 2 | shift: America/Vancouver → UTC |
| `UTC-naive` — offset-less string holding UTC | 20 | 10 OWNS edges × `created_at`/`last_accessed`, from a 2026-07 backfill's `toString(localdatetime())` (millisecond precision) | leave |
| True UTC, native | 5,410 | Cypher `datetime()` (millisecond precision: bulk upsert's `updated_at`, content and chunk stamps, embedding stamps, IngestionMetadata…) and aware Python params (microseconds: AuthEvent, Session, ConversationSession/Turn, VIEWED, IN_PROGRESS, Group and MEMBER_OF from the enrollment handler); 990 chunk `embedding_updated_at` carry zone id `UTC` (driver carry-forward) | leave |
| True UTC, string | 11 | Server `toString(datetime())` `…Z` (ingest `created_at` on Ku, PathStep and the six templates) and aware `+00:00` (`User.last_active_at`) | leave |
| Authored or calendar | 14 | Authored days `2026-03-29T00:00:00Z` (11), the authored `+07:00` `EXACERBATED_BY.observed_at` (1), naive-midnight calendar days (2) | leave (R6) |

- **Precision identifies native writers where shape cannot.** Cypher `datetime()` has millisecond
  precision; a Python parameter carries microseconds. A microsecond native is local-as-UTC only if
  its writer was naive *when it wrote*: every aware writer adopted `datetime.now(UTC)` before its
  oldest stored row (VIEWED and IN_PROGRESS since `94d63c3cd`, 2026-03-30; the oldest VIEWED row is
  2026-04-03).
- **Paired stamps confirm the offset.** 31 of 31 nodes with a naive `created_at` and a server
  `embedding_updated_at` written in the same moment read exactly +7.00 h apart.
  `Notification.created_at` 07:24:39.03Z sits 0.3 s after `ActivityReport.created_at` 07:24:38.72
  (one generation); `Ku.last_reflected_date` 13:53:14.83Z pairs with
  `APPLIES_KNOWLEDGE.grounded_at` 20:53:14.81Z.
- **Zone history.** Git author offsets are `+0700` through `eed1fd5fd` (2026-03-27 17:49 +0700)
  and `-0700` from `d65f4a529` (2026-03-27 05:43 −0700); `/etc/localtime` was relinked to
  America/Vancouver on 2026-03-27 at 05:34 −0700. No naive stamp is dated between 2026-03-08 and
  2026-03-28.
- **DST.** No stored stamp falls in PST or the 2026-03-08 gap; America/Vancouver is permanent
  UTC−7 from 2026-11-01 (tzdata 2026.3, confirmed in Python, `zdump` and AuraDB).
- AuraDB holds a dump/load of the sandbox graph (cutover 2026-08-15), so pre-cutover stamps keep
  the laptop's digits.

### Columns that already mix clocks

`updated_at` on Task, Goal, Habit, Choice, Event, Principle, Ku, Interaction and User mixes `L-str`
with true-UTC natives (bulk upsert's `updated_at = datetime()` on re-ingest; `datetime()` on
password changes and on interaction status); Ku and PathStep `created_at` mix `L-str` with `…Z`
strings (ingest's server stamp, and on PathStep also authored days); `EntryReport.updated_at` holds one `L-nat` and one server value. A stamp-to-stamp read
over these compares values 7 h apart today — which is why the migration classifies rows, not
properties (R3). `UserEntry.updated_at` mixes two shapes on one clock (`L-str`, `L-nat`).

### Live defects

**Wrong on any host** (CI included — CI runs UTC):

- `GET /api/insights/active` raises `TypeError` on every active insight: `PersistedInsight.from_dict`
  keeps a neo4j `DateTime`, and `priority_score` subtracts it from naive `datetime.now()`
  (reproduced on the three live rows).
- Principle embodiment rates are always 0: `CrossDomainQueryService.get_embodiment_rates_7d` binds
  a naive `datetime` raw, the driver sends a LOCAL DATETIME, and `datetime(hc.completed_at) >=
  $cutoff` is null (reproduced: zoned ≥ local is null).
- "Upcoming events applying knowledge" is always empty:
  `PsApplicationDiscoveryService.find_events_applying_knowledge` filters `n.start_time >=
  datetime()`, and `start_time` is a LOCAL TIME.
- `EventsBackend.get_stats_for_user`'s "today" is always 0: it matches a date against the LOCAL
  TIME `start_time`, not `event_date`.
- `EventsBackend.count_recent_reschedules` reads `rescheduled_at`, which nothing writes.
- Completing or deleting `goal.self-reflection-beginner` (an authored `…Z` `created_at`) raises
  after the write in `GoalsCoreService` (`datetime.now() - goal.created_at`), losing
  `GoalAchieved` / `GoalAbandoned`.

**Wrong on a host west of UTC:**

- The activity-report generation cooldown never fires
  (`ActivityReportGeneratorBackend.check_cooldown`).
- Relative times: a naive stamp takes `format_relative_time`'s `TypeError` fallback (an absolute
  date); an `L-nat` share reads "7h ago".
- Cypher `date()` is the UTC day, so from 17:00 local `TasksBackend.get_stats_for_user` counts a task
  due today as overdue, `HabitsBackend.get_active_habits_prioritized` sorts a habit done today as
  streak-at-risk, and `LifePathBackend.record_alignment_snapshot` files the evening's snapshot under
  tomorrow.
- Windows against `datetime()` drop `L` stamps 7 h early: the Choice and Task analytics windows, and
  the SearchEvent and Interaction retention prunes.
- Substance decay ages every stamp 7 h (`curriculum._naive_local` runs `astimezone()` on `L-nat`
  values).
- Embedding drift checks miss an edit made within 7 h of an embed (`embedding_updated_at` is server
  UTC, `datetime(n.updated_at)` reads an `L-str` as UTC) — in `generate_embeddings_batch.py --stale`
  and in the hash-stamping backfill, which stamped current hashes onto such vectors, so `--audit`
  cannot see them.
- The forms default-audience backfill (`forms_backends.py`) compares true-UTC `MEMBER_OF.joined_at`
  with `datetime(fs.created_at)` on an `L-str`.

### Python

- The parse boundary returns naive for an offset-less string and aware for an offset string or a
  native, so a mixed column yields both, and naive-versus-aware arithmetic raises. Most such sites
  are latent (no live caller, or no mixed data yet); the live ones are listed above.
- Six helpers, in two camps, disagree on what naive means: `parse_iso_utc` and `as_naive_utc` treat
  it as UTC; `curriculum._naive_local`, `goals_progress_service._parse_progress_date`,
  `_spawn_orchestrator._model_clock` and `ingestion/status_transitions._as_datetime` convert aware
  values to local time or strip them. Each is consistent only with the cohort it was written against.

### Calendar

- About 480 calendar sites use the host's local day (`date.today()`, `datetime.now().date()`) —
  right on this laptop, wrong on any UTC host — and about a dozen Cypher sites use `date()`, the UTC
  day.
- `UserPreferences.timezone` is dead: free text written by `settings_routes.py`, read only for
  display, `"UTC"` for all six users.
- Day-of-an-instant reads (`[:10]`, `.date()`, `split("T")`, Cypher `left(toString(x), 10)`,
  `find_by_date_range` on an instant field) yield the local day today **only because** stamps hold
  the local wall clock; after migration they would yield the UTC day unless routed through the zone
  (PR 3). The same holds for every display of an instant.
- A 24-hour `.days` used as a calendar-day count (habit due and streak logic, the habits planning
  service) is wrong whatever the clock.

### Instruments

- `uv run ruff check --select DTZ core adapters ui` on 2026-09-27: 258 `DTZ005` (naive `now()`),
  208 `DTZ011` (`date.today()`), 5 `DTZ001`, 4 `DTZ901`, 3 `DTZ007`. `DTZ005` does not see an
  uncalled `datetime.now` — 50 `default_factory=datetime.now` references need a grep or AST check.
- CI runners and the Neo4j testcontainer run UTC, and nothing sets `TZ`: a test of this defect must
  force a non-UTC zone (`monkeypatch.setenv("TZ", "America/Vancouver")` + `time.tzset()`, both
  restored after) or it passes with and without the fix.
  `tests/integration/test_created_at_window_coercion.py` seeds `+00:00` strings that no writer
  produces for those properties, which is why it passes while the live cooldown never fires.

---

## Migration contract (PR 4)

`scripts/migrations/utc_instants_2026_10.py` <!-- planned --> — a census by default; `--confirm` writes;
`--verify` checks.

**Shape alone cannot tell a migrated stamp from an unmigrated one.** R5 keeps each value's shape, so
an `L-str` whose digits have moved to UTC is still an offset-less microsecond string, and every stamp
the pinned code writes after the cutover looks the same. A classifier re-run after the migration
would shift those values again, and a census by shape can never read 0. The migration's state is
therefore held outside the values: an immutable manifest and a durable applied record.

1. **Classify every stored stamp** — every node and relationship property holding a temporal or an
   ISO-datetime string — by a named rule, from (label or edge type, property, shape, sub-second
   precision, date) and the writer table re-verified at PR 4. As measured on 2026-09-27:
   - `L-str`: offset-less, microsecond precision, dated from 2026-03-28 → a wall clock in
     America/Vancouver → UTC, written back offset-less (R5).
   - `+07`: offset-less, dated before 2026-03-27 → a wall clock at +07:00 → UTC, offset-less.
   - `L-nat`: a native whose (property, writer) was naive when it wrote → its digits read in
     America/Vancouver → UTC, native.
   - **leave:** millisecond natives and `…Z` strings from Cypher; natives and strings from aware
     writers; the `UTC-naive` OWNS rows; authored days and offsets; naive-midnight calendar days;
     stamps inside JSON properties; zone-id `UTC` natives.
2. **An unclassified row stops the run** (exit 2, before and regardless of `--confirm`) and is
   listed: a property missing from the table, an offset-less stamp dated 2026-03-27, a microsecond
   native whose writer is mixed, and any shift candidate (`L-str` or `L-nat`) whose digits are later
   than the laptop's wall clock at the census — a UTC-clock process (the PR 4 code, or a container)
   wrote it, and shifting it would be wrong. The script computes that wall clock explicitly
   (`datetime.now(ZoneInfo("America/Vancouver"))`): it runs pinned itself.
3. **The census writes an immutable manifest** — one row per value to shift: node or relationship
   id, property, old value, new value, rule — and prints per-rule counts with samples (old → new) for
   Mike's OK. The census runs with the app stopped, so the manifest is the whole of the work.
4. **`--confirm` applies that manifest and nothing else**, compare-and-set per row
   (`SET x.p = $new WHERE x.p = $old`): a row whose value is no longer `$old` is reported as a
   conflict, never re-derived. In the same run it writes a **durable applied record** in the graph
   (the migration's name, the manifest's hash, per-rule counts; its label is a new `NeoLabel` member,
   chosen in PR 4). A census or `--confirm` that finds the applied record refuses to run, so no second
   manifest can shift a value twice. One write per script; never re-run the script that wrote.
5. **`--verify`** reads every manifest row back: 0 still at the old value, 0 conflicts, and the applied
   record present.
6. **Deploy order, in one sitting:** stop the running app and any vault-sync or backfill script →
   pull the PR 4 code → census (manifest) → Mike's OK with the counts → `--confirm` → `--verify` →
   start the app. **No process runs the PR 4 code against AuraDB before `--confirm`:** its stamps are
   UTC digits in the offset-less shape, which the census cannot tell from the laptop's (step 2 catches
   only those written in the last seven hours).

---

## Choices — per PR

Each section stands alone for a fresh context: census before the first edit, re-verify every
symbol, and update the ledger row as the PR's last commit.

### PR 0 — Arc record (docs only)

This document; ADR-089 (and its skill back-link); the case file's status and trigger; the
deferred-work MOC line; INDEX rows.

**Acceptance:** merged; `./dev docs-links` and the skills validator are clean.

### PR 1 — Pre-flight: the defects that don't depend on the host zone

Scope — each of these is wrong on every host today:

- **Insights.** `PersistedInsight.from_dict` converts native temporals (`convert_neo4j_datetime`)
  for every stamp field, and `priority_score` measures an age between two aware values, so it
  cannot raise. The same writer stores `expires_at` as the literal string `"datetime('…')"`
  (`insight_store`; latent — no row has one): fix it.
- **Raw temporal parameters.** The embodiment cutoff crosses the driver as an ISO string compared
  through `datetime($cutoff)`. Sweep every backend and service for a `datetime` or `date` passed
  raw as a query parameter (the executor passes parameters unconverted); the census also found
  the prerequisite-chain filter in `domain_queries.py` comparing string `valid_from`/`valid_until`
  with a raw parameter (latent).
- **Event days.** "Upcoming" and the "today" stat read `event_date` (a calendar value) against a
  `$today` parameter; a LOCAL TIME `start_time` is never compared with a DateTime.
- **`count_recent_reschedules`.** `rescheduled_at` has no writer: delete the read with its protocol
  member and consumers, or register the intended writer — decided from a census of consumers.
- **Goal events.** `actual_duration_days` and `days_active` are computed without raising on an aware
  `created_at`. This PR introduces `as_utc()` in `timestamp_helpers` — an instant as aware UTC: an
  aware value converted, a naive one read in the process's zone (the laptop's until the cutover,
  UTC under the pin; PR 9 fixes it to UTC when the pin comes out) — which PRs 5–6 adopt everywhere.

**Acceptance:** `GET /api/insights/active` returns 200 with the live insights; an integration test
seeds a habit completion inside the window and reads a non-zero embodiment rate (red before the
fix); an event dated today counts in the "today" stat; a unit test completes a goal whose
`created_at` is aware.

### PR 2a — Whose zone: `SKUEL_TIMEZONE`, the user's choice, the request's zone

Scope:

- `SKUEL_TIMEZONE` in config, validated with `zoneinfo.ZoneInfo` at boot (an unknown name refuses
  to boot), default `America/Vancouver`; documented with the other `.env` settings.
- `UserPreferences.timezone` becomes `str | None` (None follows the default), validated against
  `zoneinfo.available_timezones()` at the settings door and at DTO parse. The Settings field becomes
  a list with a "SKUEL default (America/Vancouver)" entry, plus a **"Use this device's time zone"**
  button that selects the browser's `Intl.DateTimeFormat().resolvedOptions().timeZone`; the server
  validates what is posted.
- The six stored `"UTC"` values are cleared (one write, Mike's OK with the count), keyed by the six
  users' uids from the census — never by value, since after this PR `"UTC"` can be a real choice.
- Zone resolution: middleware sets a request-scoped current zone from the signed-in user's choice,
  else the default (`auth_state_var`'s pattern); a function resolves a named user's zone for work
  outside a request.
- Zone helpers in `timestamp_helpers`: `today(zone)`, `now_in(zone)`, `local_day_bounds(day, zone)`
  (UTC instants), `instant_day(value, zone)`. No calendar site moves yet (PR 2b).

**Acceptance:** Settings lists zones; in a browser emulating Asia/Bangkok, "Use this device's time
zone" selects Asia/Bangkok and saves; an invalid name is refused; the six users follow the default;
an integration test resolves a Bangkok user's request to Asia/Bangkok; boot refuses
`SKUEL_TIMEZONE=Mars/Olympus`.

### PR 2b — Calendar sites ask the zone

Scope: every `date.today()`, `datetime.now().date()` and local-wall-time `datetime.now()` used as a
calendar value moves to the zone helpers — the current zone in a request, the named user's zone
outside one (the vault reconciler's and line reconciliation's `✅` dates, `completion_date`
stamps, daily-note uids, report-period tokens). Every Cypher "today" `date()` becomes a `$today`
parameter. A 24-hour `.days` used as a calendar-day count becomes a difference of days in the zone.
`DTZ011` is enabled over `core/`, `adapters/`, `ui/` with `timestamp_helpers` exempt. **Every
`datetime.now()` is classified here** — an instant (left for PRs 5–8) or a local wall time compared
with calendar values (event start and end times, "next free slot", `Event.start_datetime`), which
moves to `now_in(zone)`: under the pin a missed wall-time site reads seven hours off. Neutral on
the laptop for users on the default; fixes the evening `date()` defects. If the census shows it too
large for one PR, split by tree (models and services / adapters and ui).

**Acceptance:** `DTZ011` reads 0 outside `timestamp_helpers`; the PR lists each remaining `DTZ005`
site as an instant. A forced-zone integration test: the
process at TZ=UTC and the clock at 02:00Z (19:00 the previous day in Vancouver) — for a user on the
default, `today()` is the Vancouver day, a task due that day is not overdue in
`TasksBackend.get_stats_for_user`, and a habit done that day is not streak-at-risk; for a user on
Asia/Bangkok at 18:00Z, `today()` is the next day. Live, after 17:00 local, the task stats' overdue
count agrees with the Today page.

### PR 3 — The edges read the stored clock through one constant (neutral)

Scope: `STORED_INSTANT_CLOCK` in `timestamp_helpers` names what a stored stamp's digits mean — the
laptop's wall clock until PR 4. Every display of an instant (absolute and relative:
`format_relative_time`, `format_date` callers, `strftime` / `[:10]` of stamps in `ui/` and `core/`),
every day-of-an-instant read (Python `.date()`, `[:10]`, `split("T")`; Cypher `left(toString(x), 10)`,
`date(datetime(x))`, and `find_by_date_range` on an instant field — the field's kind decides), and
every local-period bound compared with stamps (report periods, the MEGA-QUERY window, journal
ranges, life-path momentum, habit completion counts) goes through a helper or fragment builder that
reads the constant. A form's `datetime-local` value is produced and parsed by the same helper.
Output is identical to today for users on the default zone. (A user who picks another zone
before PR 4 gets calendar days in that zone but instants still read as the laptop's wall clock.)

**Acceptance:** unit tests pin each helper under both values of the constant; rendered pages
(GradeBook, Shared, notifications, an activity report) are the same before and after for
linguistic76, apart from relative times advancing between the two renders; the PR records the grep
that finds no display or day-slice site bypassing the helpers.

### PR 4 — Cutover: pin, flip, migrate

Scope:

- **The pin:** `os.environ["TZ"] = "UTC"` + `time.tzset()` at the one import chokepoint every entry
  point shares. Census the entry points (`main.py`, the `./dev` targets, `scripts/`,
  `tests/conftest.py`, the in-process embedding worker) and prove each reaches it before any clock
  read; a subprocess test imports the app under `TZ=America/Vancouver` and sees `datetime.now()`
  equal the UTC wall clock.
- `STORED_INSTANT_CLOCK` flips to UTC; `format_relative_time` reads a naive value as UTC.
- **The cooldown pin:** an integration test writes an activity report through the real writer in a
  process started under `TZ=America/Vancouver` and asserts `check_cooldown` counts it (red on the
  PR 3 code).
- The migration script (§ Migration contract) with unit tests for every rule, the stop cases, a
  conflict (a value changed after the census), a second `--confirm` of the same manifest (a no-op)
  and a census after the applied record exists (refused); and an integration test against the
  testcontainer seeded with one row per rule.
- After the migration: re-run the embedding staleness backstop. The vectors the hash-stamping
  backfill marked current within 7 h of an edit cannot be told apart; a one-time re-embed of the
  affected labels is the only certain remedy (OpenAI calls — Mike's OK, or leave it).

**Deploy:** § Migration contract step 6, before 2026-11-01 and before the laptop's zone changes (R4).

**Acceptance (live, AuraDB):** `--verify` finds every manifest row at its new value, 0 conflicts, and
the applied record present; a fresh census is refused;
generating an activity report twice within the hour — the second is refused by the cooldown; a
share made now reads "just now" and its notification shows the wall-clock time; the GradeBook
exchange order and the review badges are unchanged for the live exchanges (snapshot before and
after).

### PR 5 — Readers compare aware values (`core/`)

Scope: every Python comparison, subtraction, sort, `min`/`max` over instants in `core/` — model
methods such as `Entity.is_recent`, services, event handlers, report periods, curriculum substance —
compares `as_utc()` values against `now_utc()`, tolerant of naive (UTC under the pin) and aware
values alike. The disagreeing normalizers (`parse_iso_utc`, `as_naive_utc`, `_naive_local`,
`_parse_progress_date`, `_model_clock`, `status_transitions._as_datetime`) collapse onto `as_utc`.
Behaviour-neutral under the pin; it removes the remaining latent `TypeError`s.

**Acceptance:** no comparison site in `core/` reads a naive `datetime.now()` (the remaining `DTZ005`
hits are writers, PRs 7–8); unit tests put naive and aware values in one list, sort and window;
forced `TZ=America/Vancouver` unit tests on the touched domains pass.

### PR 6 — Readers compare aware values (`adapters/`, `ui/`, `scripts/`)

Scope and acceptance as PR 5, for the Python side of `adapters/`, `ui/` and `scripts/`.

### PR 7 — Writers stamp aware UTC: models and the parse boundary

Scope: entity, DTO and model default factories use `now_utc`; the parse boundary
(`from_neo4j_node`, `dto_helpers`, `convert_neo4j_datetime`, `to_native_datetime`) returns aware
UTC always; the mapper writes an aware stamp as a `+00:00` string (R5: still a string).

**Acceptance:** the uncalled-`datetime.now` check reads 0 in `core/models`; a model written and read
back carries aware UTC stamps; an integration test reads a mixed column (offset-less UTC string,
`+00:00` string, native) back all aware and sorts it.

### PR 8 — Writers stamp aware UTC: services, backends, events, scripts

Scope: every remaining `datetime.now()` — instants, `BaseEvent.occurred_at`, hand-built
`datetime.now().isoformat()` Cypher parameters, duration timers (`time.monotonic()` where only
elapsed time matters); `datetime.combine` and `datetime.min`/`max` without a zone; `strptime` without
one. A client-supplied datetime without an offset is read in the user's zone at the door.

**Acceptance:** `uv run ruff check --select DTZ core adapters ui` reads 0 (with `timestamp_helpers`
exempt where it reads the zone); the forced-zone integration suite passes.

### PR 9 — Close: the pin comes out, the guards go in

Scope: remove the pin and `STORED_INSTANT_CLOCK` (the helpers keep the UTC reading), and `as_utc`
reads a naive value as UTC rather than in the process's zone — in the same change, or the unpinned
laptop would read one as Vancouver time; enable ruff
`DTZ` for `core/`, `adapters/`, `ui/` in `pyproject.toml`, with the uncalled-`datetime.now` check in
the lint; a forced-zone guard (America/Vancouver and Asia/Bangkok) over the cooldown, a share's
relative time, today and overdue, and a day-of-instant read. Rewrite Pattern 10 and Key Rules
#17/#18 (the naive-local invariant is gone) and the CLAUDE.md lines that state it; mark ADR-089
implemented; move this document and the case file to `done/`; run the arc-close walk-through.

**Acceptance:** § Verification.

---

## Non-goals (this arc)

- One storage shape for instants (R5).
- A prompt when the device's zone differs from the chosen one (R2).
- Logs — already UTC.
- The local Docker sandbox (R7).
- Stamps nested inside JSON metadata, authored days, naive-midnight calendar days (R6).

## Standing conventions that bind every PR here

- **A forced zone, or the test proves nothing.** CI and the testcontainer run UTC. Force `TZ` with
  `monkeypatch.setenv` and `time.tzset()`, and restore both; from PR 4, a test that needs the
  unpinned behaviour forces the zone after import.
- **A calendar value is never converted to UTC; an instant is never stored as a wall clock.**
- **A new stamp.** Before PR 4, a new stored stamp property joins the migration's rule table (the
  script stops on an unclassified property). From PR 4, a new instant writer uses `now_utc()` and a
  new reader compares through `as_utc()`.
- **Every AuraDB write** needs Mike's explicit OK in that session with counts first; one write per
  script; never re-run a script that wrote.
- Review and merge per `docs/development/PR_WORKFLOW.md`; the PR that lands a row updates it.

## Running the arc: one PR per fresh context

Kickoff for each PR: *"Read `docs/roadmap/utc-instants-arc.md`. Take the first PR whose Status is
not merged. Census before the first edit; re-verify every symbol it names; update its ledger row as
the PR's last commit."*

## PR plan (contract)

Rows are in execution order. PR 1 depends on nothing. PR 2b requires PR 2a. PR 3 requires PR 2a
(its helpers take a zone). PR 4 requires PR 2b and PR 3 — the pin turns every host-local day it
finds into the UTC day — and lands before 2026-11-01 (R4). PRs 5 and 6 require PR 4. PR 7 requires
PRs 5 and 6 (readers accept aware values before writers produce them). PR 8 requires PR 7; PR 9
requires PR 8.

| PR | Scope | Acceptance (live case) | Status |
|----|-------|------------------------|--------|
| 0 | This document + ADR-089 + the case file, MOC and INDEX rows (docs only; summon Codex explicitly) | Merged; `./dev docs-links` and the skills validator clean | merged #1431, 2026-09-27 |
| 1 | Pre-flight: insights crash, raw temporal parameters (embodiment), event days, the unwritten `rescheduled_at`, goal-event arithmetic; `as_utc()` | `/api/insights/active` 200; a non-zero embodiment rate (red before); today's event counts | — |
| 2a | `SKUEL_TIMEZONE`; the user's zone in Settings (list + "Use this device's time zone"); the six `"UTC"` cleared; the request's zone; zone helpers | A Bangkok-emulating browser saves Asia/Bangkok in one click; a bad name refused; boot refuses a bad default | — |
| 2b | Every calendar site asks the zone; Cypher `$today`; calendar-day counts; `DTZ011` on | After 17:00 local the overdue count agrees with the Today page; forced-zone test (UTC process, Vancouver and Bangkok users) | — |
| 3 | `STORED_INSTANT_CLOCK`; displays, day-of-instant reads and period bounds through helpers (neutral) | Rendered pages unchanged for linguistic76 (relative times aside) | — |
| 4 | The UTC pin; the constant flipped; the migration (stop the app → census and manifest → OK → `--confirm` → `--verify` → start) | The cooldown refuses a second generation within the hour; a new share reads "just now"; exchange order and badges unchanged | — |
| 5 | Readers compare aware values in `core/`; the normalizers collapse onto `as_utc` | Mixed naive/aware sorts and windows; forced-Vancouver unit tests | — |
| 6 | Readers compare aware values in `adapters/`, `ui/`, `scripts/` | As PR 5 | — |
| 7 | Writers aware: default factories, the parse boundary, the mapper's `+00:00` | A mixed column reads back all aware | — |
| 8 | Writers aware: services, backends, `occurred_at`, Cypher parameters, timers, client datetimes | `ruff --select DTZ` reads 0 | — |
| 9 | Pin removed; `DTZ` in the lint; forced-zone guards; Pattern 10 / Key Rules #17–18 / CLAUDE.md; ADR-089 implemented; this document and the case file to `done/` | § Verification | — |

## Verification (arc close)

A live walk-through as linguistic76, plus a second account set to Asia/Bangkok:

1. Generate an activity report, then generate again within the hour — the second is refused.
2. Share an entry — the recipient's Shared page reads "just now", and the notification shows the
   wall-clock time.
3. Set the account to Asia/Bangkok with "Use this device's time zone" (a browser emulating Bangkok):
   Today, overdue and habit streaks follow the Bangkok day, and the entry's time reads in Bangkok
   time; switch back and they follow Vancouver.
4. After 17:00 local, a task due today is not overdue in any count.
5. The migration's `--verify` reads every manifest row at its new value, and the applied record is
   present.
6. `uv run ruff check --select DTZ core adapters ui` reads 0, and the forced-zone suite passes under
   `TZ=America/Vancouver` and `TZ=Asia/Bangkok`.
