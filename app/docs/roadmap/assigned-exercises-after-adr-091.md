---
title: "Assigned Exercises After ADR-091"
updated: 2026-11-15
status: "deferred — the read matches nothing on any graph a door can write; what it should mean is a design decision"
registered: "2026-11-15 (bootstrap typing residuals, row 2h-iii)"
ruled: "2026-11-15 — keep it, staged: its test marks the retired shape it seeds, and the meaning is decided on its own"
trigger: "a ruling on what an exercise waiting for a learner is, now that every exercise is curriculum (ADR-091)"
check: "grep -n \"scope: 'assigned'\" adapters/persistence/neo4j/user_context_queries.py — a hit means the section still reads the retired scope"
---

# Assigned Exercises After ADR-091

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What it reads

`SUBMISSION_STATS_QUERY` (`adapters/persistence/neo4j/user_context_queries.py`) counts a learner's
**assigned exercises**: exercises with `scope: 'assigned'` shared with a group the learner is a
member of (`(user)-[:MEMBER_OF]->(:Group)<-[:SHARED_WITH_GROUP]-(ex)`). From them it derives three
`UserContext` fields — `assigned_exercise_count`, `completed_exercise_count` (the assigned ones the
learner has turned in) and `unsubmitted_exercises` (up to five not yet turned in, with title and due
date).

## Why it reads nothing

ADR-091 made curriculum the one scope: every exercise is authored in the content vault and its
`scope` is `curriculum` (`ExerciseScope` has no other member), and group assignment (ADR-040) went
with the retired doors. On the live graph when this was registered, all 14 exercises held
`curriculum` and no exercise was shared with a group. So the section matches nothing, and the three
fields are always `0`, `0` and `[]`.

Their one reader is the daily plan: `ExerciseService.get_actionable_exercises_for_user` builds the
plan's exercise suggestions from `unsubmitted_exercises`
(`core/services/user/intelligence/daily_planning.py`), so the daily plan has suggested no exercise
since ADR-091.

## The test that keeps it seeded

`tests/integration/test_user_context_lifted_statements.py` seeds two exercises in the retired scope
so the section has something to count. The graph census refuses the seed — no exercise read can
read `scope: 'assigned'` — so its tests carry `stores_unreadable_value`, naming this file. When the
section is redefined, the seed changes with it and the marker goes.

## What a redefinition decides

What "an exercise waiting for this learner" means when exercises are curriculum. One candidate:
the exercises of the path steps the learner is in progress on that they have not turned in yet
(`HAS_EXERCISE` from an engaged step, no `FULFILLS_EXERCISE` from their entry), due dates read from
the engagement rather than the exercise. Retiring the three fields and the daily plan's reader is
the other way out; it was not taken, under the keep-future-capabilities stance.
