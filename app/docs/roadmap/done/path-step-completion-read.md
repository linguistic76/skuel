---
title: "Path Step Completion Read"
updated: 2026-11-24
status: "done — a learner's completion of a step is their MASTERED edge to it, at every reader"
registered: "2026-11-23 (bootstrap typing residuals, row 2i-b-v)"
ruled: "2026-11-23 — a learner has completed a step when they have mastered it: their MASTERED edge to it. 2026-11-24 — mastered only, the PathStep page too; a prerequisite step is one the learner masters before the step that requires it may be undertaken"
---

# Path Step Completion Read

*Closed case file. It was the [deferred-work.md](../deferred-work.md) entry of the same name.*

## What it read

The user-context statement for a learner's curriculum (`adapters/persistence/neo4j/user_context_queries.py`)
read a `completed` property off `PathStep` nodes in three places:

- each enrolled path's `graph_context.steps[].completed`, from the path's `HAS_STEP` targets;
- the path's `completed_steps` and `progress_percentage`, counted from those steps;
- each active step's `prerequisite_steps[].completed`, from its `REQUIRES_STEP` targets.

No writer stored the key, and none should: a step is shared curriculum, so a property on it would
mark it completed for every learner at once. Every enrolled path read `completed_steps: 0` and
`progress_percentage: 0.0`. Askesis's grounding projection (`_path_entry`) told the LLM
"(0/N steps)", and the learner's activity report printed "0/N steps (0%)".

## The rule

A learner has completed a step when they hold a `MASTERED` edge to it: the edge `PsMasteryService`
derives once every Ku the step teaches is mastered, and announces with `PathStepCompleted`. Marking a
step as read is a state of its own, short of completion.

A prerequisite is what the learner masters before the step that requires it may be undertaken, so a
prerequisite is met by the same edge. One edge answers every reader:

- the curriculum statement's three sites;
- the PathStep page's hero card, whose Completed state is `mastered` (a step marked as read shows
  as Read);
- the page's Blocking dependencies accordion (`PsIntelligenceBackend.fetch_prerequisite_statuses`),
  which agrees with the chain door's `prerequisites_mastered` and `unmet_count`;
- the LP pages and Insights, which already counted mastered steps.

A path's progress is its mastered steps over its steps. The enrollment edge's `progress` is a
different measure (the path's mastered Kus), and no page shows it.

## Held by

- `tests/integration/test_path_step_completion_reads_mastered.py`: two learners on one path, each
  reading only their own masteries, and the Askesis line naming each one's count.
- `tests/integration/test_rich_context_statement_equivalence.py`: its seed expresses a completed
  step as a `MASTERED` edge and stores no `completed` key.
- `tests/integration/routes/test_ps_blocking_dependencies.py`,
  `tests/unit/ui/test_ps_hero_states.py` and `tests/js/ps-hero-states.test.js`: the step page.
- `tests/integration/test_user_context_plan_cache.py`: the statement's size.

## Not here

- A gate on the doors that undertake a step whose prerequisites are not mastered:
  [path-step-prerequisite-gate.md](../path-step-prerequisite-gate.md).
- The enrollment's completion counting the path's prerequisite Kus:
  [enrollment-progress-counts-prerequisite-kus.md](../enrollment-progress-counts-prerequisite-kus.md).
- Draft steps in a path's step total, here and on the LP pages: parked with the publication work on
  what a learner who already holds a draft reads.
