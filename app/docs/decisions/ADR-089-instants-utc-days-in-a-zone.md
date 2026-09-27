---
title: "ADR-089: Instants Are UTC; Days Belong to a Zone"
updated: 2026-09-27
status: accepted
category: decisions
tags: [adr, decisions, timestamps, timezone, utc, calendar, migration, neo4j]
related: [ADR-070, ADR-080, ADR-087]
related_skills: [neo4j-cypher-patterns]
---

# ADR-089: Instants Are UTC; Days Belong to a Zone

**Status:** Accepted — founder-ratified 2026-09-27. **Implementation pending:** the UTC Instants
arc builds it; its [PR contract table](../roadmap/utc-instants-arc.md#pr-plan-contract) is the ledger.
**Date:** 2026-09-27
**Deciders:** MCF
**Decision Type:** ☑ Graph Schema  ☑ Pattern/Practice
**Arc:** [UTC Instants — rulings & contract](../roadmap/utc-instants-arc.md) (rulings R1–R8).
**Related ADRs:**
- [ADR-087](ADR-087-status-guarded-conditional-writes.md) — completion stamps are written through
  its guard; this ADR decides the clock the stamp carries, not how the write is guarded.
- [ADR-070](ADR-070-bidirectional-vault-bridge.md) — the vault's `✅ date` is a calendar value in the
  vault owner's zone.
- [ADR-080](ADR-080-auradb-three-horizon-strategy.md) — the graph is one AuraDB instance that the
  laptop and the parked production droplet (a UTC host) both write.

## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md) — Pattern 10
  (temporal property coercion); Key Rules #17/#18 are rewritten when the arc closes.

---

## Context

SKUEL records two kinds of time and has treated them as one:

- **Instants** — when something happened: created, updated, shared, submitted, completed, joined,
  viewed. A moment is the same moment everywhere.
- **Calendar values** — which day it is for a person (due today, overdue, a habit's day, a daily
  note's date, a report's week) and how a moment reads to them ("3:40 PM", "2h ago"). These depend
  on where the person is.

Most writers stamp instants with the host's naive wall clock (`datetime.now()`), stored either as
an offset-less ISO string (the mapper's `isoformat()`) or as a native DateTime built from that
string (`datetime($now)`), which labels the local wall clock `Z`. Neo4j reads an offset-less
stamp as UTC, so on the development laptop (America/Vancouver, UTC−7) every such stamp reads seven
hours old: the activity-report generation cooldown never fires, and a share made a minute ago reads
"7h ago". Two other clocks — Cypher `datetime()` and aware `datetime.now(UTC)` — write true UTC,
some of them into the same columns, and the laptop sat at UTC+7 before 2026-03-27. The stored
corpus therefore holds four cohorts of one idea (census: the arc's § Verified ground truth).

Calendar concepts, meanwhile, use the host's local day (`date.today()`) in Python and the server's
UTC day (`date()`) in Cypher, so from 17:00 local the two disagree. The per-user
`UserPreferences.timezone` field is read by nothing.

The founder moves to UTC+7 for about eight months from late November 2026, and the parked
production droplet would write the same graph from a UTC host: a naive stamp's meaning cannot
depend on the host that wrote it.

## Decision

### 1. An instant is UTC

- In Python an instant is an aware UTC `datetime`; `now_utc()` in `core/utils/timestamp_helpers.py`
  is the one clock. A naive datetime read from storage means UTC and is made aware at the parse
  boundary.
- In the graph an instant is UTC in whichever shape its writer produces — an ISO string (the
  mapper) or a native DateTime (Cypher). The shapes are not converged by this decision; every
  comparison or ordering of a stamp coerces with `datetime()` (Pattern 10).
- A stored instant is never a local wall clock, and a stored instant is never shifted to "fix" a
  display.

### 2. A calendar value belongs to a zone

- Due dates, event dates and times, daily-note dates and report-period tokens are local calendar
  values; they are never converted to UTC. A stored field's type says which it is: a `datetime` is
  an instant; a calendar value is a `date` or a LOCAL TIME. A field that holds a day is retyped, not
  exempted.
- "Today" is today in the current zone. A stored instant's day is its date in the current zone. A
  local period over instants is queried by the UTC bounds of that period in the zone. Cypher never
  computes "today" with `date()`; the day is passed in.
- Display renders an instant in the current zone, absolute and relative.

### 3. Whose zone

- Each user may choose a zone (Settings: a validated IANA list and "Use this device's time zone").
  A user who has not chosen follows `SKUEL_TIMEZONE` (`.env`, validated at boot, default
  `America/Vancouver`), which also serves system work that acts for no user.
- The current zone is resolved once per request from the signed-in user; work done for a named user
  outside a request (vault sync for the vault's owner, a report for a user) resolves that user's
  zone explicitly.
- No prompt is shown when the device's zone differs from the chosen one.

### 4. The migration and the bridge

- Stored instants are migrated to UTC row by row, classified by writer, shape, sub-second
  precision and date against the laptop's zone history (UTC+7 until 2026-03-27, America/Vancouver
  since). A row the rules cannot classify stops the run. The migration moves digits, never shapes,
  so its state lives outside the values: it applies an immutable manifest, built once while the app
  is stopped, in one transaction with a durable applied record. From the cutover on, the code
  refuses to open a graph that holds data but no such record (a graph opened empty is stamped with
  it at once); this data-version guard stays after the pin is removed. Calendar values, authored
  days and diagnostic stamps nested in JSON metadata are not touched; a JSON-nested stamp that code
  compares as an instant is migrated.
- The cutover pins the process clock to UTC at every entry point, asserted by every graph driver
  factory (a temporary bridge), so every naive writer writes UTC
  at once; the code is then swept to aware datetimes behaviour-neutrally, and the pin is removed.
  The standing guards are ruff `DTZ` and integration tests run under forced non-UTC zones.

## Alternatives Considered

### Alternative 1: Aware writers and the migration in one cutover
**Description:** switch every naive writer and every comparison to aware UTC in the same
stop-the-app window as the migration.
**Pros:** no temporary pin.
**Cons:** stamp-to-stamp reads cross labels and writers (supersede rule, review badges, exchange
order), so several hundred sites must flip in one PR; any one missed raises `TypeError` or
misorders across the cohort boundary.
**Why rejected:** the risk sits in one oversized change; the pin buys the same data correctness
with no writer edits.

### Alternative 2: Pin the process to UTC permanently
**Description:** the bridge as the end state — naive datetimes mean UTC by process configuration.
**Pros:** the smallest change.
**Cons:** correctness lives in process configuration: a test, script or notebook without the pin
writes local time again, invisibly. Naive and aware values still meet in Python.
**Why rejected:** accepted as the bridge only (R1, R8).

### Alternative 3: Leave storage; fix only the window reads
**Description:** interpret stored stamps as host-local at every read that compares them with now.
**Pros:** no migration.
**Cons:** columns already hold two clocks, and a local-as-UTC native cannot be told from a true-UTC
one at read time; every read carries the zone history forever; a second host (the droplet) makes
naive stamps ambiguous the day it writes.
**Why rejected:** it cannot be made correct.

### Alternative 4: One app-wide zone only
**Description:** `SKUEL_TIMEZONE` for everyone; no per-user choice.
**Pros:** no preference plumbing.
**Cons:** a traveller edits `.env` and restarts; any second user in another zone is wrong.
**Why rejected:** R2 — the founder's own travel is the first use case.

## Consequences

- **Positive:** moving between zones changes what "today" is and how times read, and nothing
  stored changes. Windows against the server clock (the cooldown, retention, drift checks) are
  correct on any host. The disagreeing "what does naive mean" helpers collapse into one rule.
- **Negative:** a one-time migration of about 1,230 stored values, with a stop-the-app window; a
  temporary process pin while the sweep runs; every calendar read needs a zone.
- **Neutral:** instant storage keeps two shapes (strings and natives), handled as today by
  `datetime()` coercion.

## Implementation Details

The arc document carries the rulings, the verified census, the migration contract and the per-PR
scope and acceptance. This ADR is marked implemented when the arc closes.

## Changelog

- 2026-09-27 — Accepted (UTC Instants arc PR 0).
