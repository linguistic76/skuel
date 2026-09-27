---
title: "Naive-Local Timestamps Read as UTC"
updated: 2026-09-27
status: "deferred — registered at the Submit & Share arc close (Mike's ruling, 2026-09-26)"
registered: 2026-09-27
ruled: 2026-09-26
trigger: "the next change to a time-window read (a cooldown, a retention or 'recent' window), OR a production host that does not run in UTC, OR a user-facing relative time that matters"
check: "on the host: date +%z (non-zero = affected); live: MATCH (ar:ActivityReport) RETURN toString(ar.created_at), toString(datetime()) — a stamp minutes old reading hours old is the defect"
---

# Naive-Local Timestamps Read as UTC

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The defect

Writers stamp naive local wall-clock time, and Neo4j reads an offset-less stamp as UTC:

- `Entity.created_at` defaults to `datetime.now()` (`core/models/entity.py`), which the mapper
  stores as an `isoformat()` string with no offset.
- The notification writer and every sharing writer build `now = datetime.now().isoformat()` and
  store `datetime($now)` / `datetime($shared_at)` — a native DateTime carrying the local wall clock
  under a `Z` zone.
- A read that compares either against `datetime()` (the server's UTC now) is off by the host's UTC
  offset. On the development laptop (America/Vancouver, UTC−7) every stamp reads seven hours old.

## What it breaks (observed)

- **The activity-report generation cooldown never fires on a host west of UTC.**
  `ActivityReportGeneratorBackend.check_cooldown` counts reports with
  `datetime(ar.created_at) >= datetime() - duration({minutes: 60})`; a report written a minute ago
  reads as seven hours old, so `recent_count` is always 0. Probed read-only on AuraDB
  (2026-09-26): an activity report's stored `created_at` of `2026-09-25T07:24:38.717603` (local
  wall clock) parses as `2026-09-25T07:24:38.717603Z`. The arc-close step 5 verified the
  human-report exclusion with a timezone-corrected read-only mirror instead (`localdatetime(...)`),
  because the live check is vacuous here.
- **Relative times on shares read hours off** (a share made minutes ago shows "7h ago") — the
  residual recorded at Submit & Share PR 6b and PR 6c.
- **Notification and membership stamps** (`created_at`, `joined_at`) hold the local wall clock under
  a UTC zone, so any future window read over them inherits the same skew.

## Why it waits

It is cross-cutting — every writer that stamps `datetime.now()`, and every stored stamp (a data-shape
migration) — and no arc has owned time handling. A host running in UTC shows no skew, so the defect
is dormant wherever the server clock is UTC.

## Shape of the fix (not ruled)

Stamp aware UTC at the writers (`datetime.now(UTC)`), migrate stored offset-less stamps by the
host's historical offset, and pin one window read (the cooldown) with an integration test that
seeds a stamp from the writer's own clock rather than a UTC-aware literal — the existing
`test_created_at_window_coercion.py` seeds UTC-aware strings, which is why it passes on any host.
