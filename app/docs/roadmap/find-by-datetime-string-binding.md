---
title: "find_by Datetime String-Binding — Three Habit Sites"
updated: 2026-09-05
status: "registered"
registered: 2026-08-24
trigger: "next touch of any of the three reads, or a second completed_at writer shape appears"
check: "one PR: a normalized range predicate on a backend method replaces all three find_by reads"
---

# `find_by` Datetime String-Binding — Three Habit Sites

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

#1140 established the bug class (Pattern 10b / Key Rule 18b in
`.claude/skills/neo4j-cypher-patterns/PATTERNS.md`): `find_by(field__gte/__lte=<datetime>)` is a
Cypher range predicate whose bound is stringified by `convert_value_for_neo4j`, so a
natively-typed stored value falls outside every range — silently. #1140 fixed only the
consistency score's own fetch; three pre-existing sites remain, all in
`core/services/habits/habits_completion_service.py` and each ⚠-marked in the
`get_completions_for_habit` docstring:

- `get_completions_for_habit(start_date/end_date)` — feeds the streak backfill
  (`_completed_days_window`) and the calendar day read;
- `get_today_completions` via `_all_completions` (`completed_at__gte/__lte`);
- `export_completion_history` (CSV/JSON export, same range).

**Fix as ONE PR:** a normalized range query on a backend method —
`date(left(toString(x), 10)) >= date($iso)` on both sides (Codex's original suggestion on
#1140), replacing all three `find_by` reads.
**Trigger:** next touch of any of the three reads, or a second `completed_at` writer shape
appears (today's single writer persists ISO strings, so the hazard is latent, not live).
**Named cost:** a natively-typed `completed_at` row vanishes from streak backfill, calendar day
reads, today view, and exports — a confident wrong answer, not an error.
