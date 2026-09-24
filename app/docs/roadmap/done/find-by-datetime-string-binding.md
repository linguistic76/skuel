---
title: "find_by Datetime String-Binding — Three Habit Sites"
status: done
registered: 2026-08-24
ruled: "2026-09-23 (Mike): option (c). Extend the generic `find_by_date_range` (offset + a total, type-normalised order) rather than add a habit-completions domain backend; the 17 `event_date` `find_by` range reads stay out of scope"
updated: 2026-09-24
---

# `find_by` Datetime String-Binding — Three Habit Sites

*Case file for the former [deferred-work.md](../deferred-work.md) entry of the same name.*

#1140 established the bug class (Pattern 10b / Key Rule 18b in
`.claude/skills/neo4j-cypher-patterns/PATTERNS.md`): `find_by(field__gte/__lte=<datetime>)` is a
Cypher range predicate whose bound is stringified by `convert_value_for_neo4j`, so a
natively-typed stored value falls outside every range, silently. #1140 fixed only the
consistency score's own fetch. Three sites remained, all in
`core/services/habits/habits_completion_service.py`:

- `get_completions_for_habit(start_date/end_date)`, which feeds the streak backfill
  (`_completed_days_window`), the calendar day read, completion stats, and the per-habit
  history/calendar views;
- `get_today_completions` via `_all_completions` (`completed_at__gte/__lte`);
- `export_completion_history` (CSV/JSON export, same range).

**Named cost:** a natively-typed `completed_at` row vanishes from streak backfill, calendar day
reads, today view, and exports, which is a confident wrong answer rather than an error.

## What shipped

**The read.** The proposed "one backend method" already existed:
`find_by_date_range` on `_SearchMixin`, declared on `EntitySearchOperations` and so already inside
the `BackendOperations[HabitCompletion]` the service holds. It compares
`date(left(toString(n.f), 10))` on both sides. It gained two things:

- `offset`, so a whole window can be walked in pages;
- `ORDER BY datetime(toString(n.f)) DESC, n.uid` in place of `ORDER BY n.f DESC`. The raw field
  sorted by TYPE before value under a mixed column (a cap truncated a type band, not the oldest
  rows), and had no tiebreak, so `SKIP`/`LIMIT` pages could overlap and omit rows. The key is the
  parsed instant, not `toString` alone: `track_habit` stores offset-bearing ISO strings, and
  string order is wall-clock (`…T10:00+02:00` sorts after `…T09:00+00:00`, an hour later). A
  value with no zone parses in the server's default zone (Codex P2 on #1411).

**The three sites.** All go through it, and none keeps a `completed_at__gte/__lte` `find_by`.
`get_completions_for_habit` is one capped read, newest first. `_all_completions(scope, start,
end)` walks `find_by_date_range` pages in `QueryLimit.BULK` steps and backs
`get_today_completions`, `export_completion_history` and `get_all_completions_for_habit`.

**A second defect under the first.** The mapper returns a native zoned `completed_at` as an
**aware** `datetime` and an ISO string as a **naive** one, so every Python
`sorted(key=get_completed_at)` over both shapes raised `TypeError`. That was already live in
`get_all_completions_for_habit`, which carried no predicate and so returned both shapes. The
Python re-sorts are deleted, and the database order is the one authority (the export reverses
it for oldest-first).

**Census at ship time.** AuraDB (read-only, 2026-09-23): 1 `:HabitCompletion`, `completed_at`
STRING, so the hazard was latent. No index on `completed_at`, so the function over the property
costs nothing. Other `find_by` temporal range reads: 17, all `event_date` in 7 events services,
binding explicit `.isoformat()` strings (AuraDB `event_date`: 5 STRING + 1 NULL). Out of scope
by ruling.

**Timezone.** `toString` of a zoned native value gives its own zone's wall-clock date, which is
the same day `completed_at.date()` gives on the mapped value. The predicate and the Python-side
day logic (`_completion_days`) agree.

**Guards.** `tests/integration/test_habit_completion_range_reads.py` seeds one native row (raw
Cypher, since no production writer makes that shape), one string row through `record_completion`,
and one out-of-window row through `record_completions_bulk`. It asserts that all four reads
return exactly the in-window rows, in chronological order across the split. It failed on `main`
(3 reads dropped the native row; the unwindowed read raised `TypeError`), and reverting any one
site to `find_by`, or the order to `n.f DESC` or `toString(n.f) DESC`, fails it. Backend query shape:
`test_find_by_date_range_pages_under_a_total_order`.

**Not built here.** The habit-completion persistence bundle's defect 5 (a DISTINCT-day read for
the streak backfill) reuses this predicate but has its own trigger, duplicate volume, which has
not fired. See [habit-completion-persistence-bundle.md](../habit-completion-persistence-bundle.md).
