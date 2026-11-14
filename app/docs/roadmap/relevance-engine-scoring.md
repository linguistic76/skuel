---
title: "Relevance Engine Scoring"
updated: 2026-11-14
status: "deferred — the scoring is provisional; the engine has no caller"
registered: "2026-11-14 (bootstrap typing residuals, row 2c)"
ruled: "2026-11-14 — keep the formula and the 0.5 threshold for now, marked as planned to evolve"
trigger: "a route or surface calls ContextRelevanceEngine.find_relevant_from_user_context (or find_relevant_for_context)"
check: "grep -rn 'find_relevant_from_user_context\\|find_relevant_for_context' adapters ui core --include=*.py — a caller outside askesis_service.py's delegators means the trigger has fired"
---

# Relevance Engine Scoring

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`ContextRelevanceEngine` (`core/services/askesis/context_relevance_engine.py`) finds the published
knowledge around a learner's activities. What it reads is settled; how it ranks what it reads is not.

## What it reads (settled)

Two depth-1 rings per activity, through `GraphIntelligenceService.get_entity_context`:

- **`DIRECT`** — the knowledge the activity links itself, by any edge.
- **`ADJACENT`** — the knowledge one edge from a `DIRECT` unit: its prerequisite, a PathStep that
  uses it. The second ring grows out of knowledge only. A single depth-2 read would also reach a
  goal's Ku through the task that contributes to the goal, and credit it to the task.

Only published curriculum is returned. Every reason names its activity, its ring, the knowledge it
came through (`via_uid`) and the edge. Each unit carries the `domain` (a subject area) and
`complexity` its curriculum file authored, or `None`.

## What is provisional

The score is `min(1.0, 0.2 × reasons) + 0.15 × activity kinds reaching the unit`, capped at 1.0,
kept from the engine as it was first written. With the default `min_relevance_score` of 0.5 a unit
needs two reasons to appear: one activity linking one Ku scores 0.35. On the live graph when this
was registered, open activities linked 3 published knowledge units directly, and only 1 of them was
linked by two activities.

## The planned evolution

- **Weight by ring** — a `DIRECT` reason counts the same as an `ADJACENT` one today. The ring is
  on every reason so the weighting can be added without another read.
- **Complexity** — `KuComplexity.sort_order()` could break ties in `recommended_order` among units
  equally ready, foundations first. No Ku authors a complexity yet, and the `Ku` model has no
  `complexity` field (an authored `complexity:` is stored on the node, and only raw-property reads
  such as this engine's see it).
- **Calibrate the threshold** against what the first surface shows a learner.

None of this is worth deciding before a caller exists: there is nothing to tune it against.
