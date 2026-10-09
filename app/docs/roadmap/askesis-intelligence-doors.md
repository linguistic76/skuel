---
title: "Askesis Intelligence Doors — the Hub Methods' Second Door"
updated: 2026-10-09
status: "staged"
registered: "2026-10-08 (F8 — the hub methods, realized)"
ruled: "2026-10-08 — the founder: the Insights cards are the first door; the Askesis catalog entries are the staged second door"
trigger: "the Insights cards (F8-6) are live and a hub method is worth asking in conversation"
check: "grep -n 'get_cross_domain_synergies\\|calculate_life_path_alignment' core/services/askesis/query_tools.py"
---

# Askesis Intelligence Doors — the Hub Methods' Second Door

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The names

**The hub methods** are the nine questions `UserContextIntelligence`
(`core/services/user/intelligence/`) answers for one user from a `RichUserContext` plus the
domain services. **Askesis** is the pedagogical companion that asks them: each of its eight
wrappers (`core/services/askesis_service.py`, members of `AskesisOperations`) builds the hub
from a context and calls the hub method of the same name. A wrapper is Askesis' *door* onto a
hub method, not a separate capability.

Ruled by the founder, 2026-10-08: *"I like the DSL of 'the hub methods,' and a distinction +
relationship with 'Askesis.'"*

| # | Hub method | Askesis wrapper |
|---|---|---|
| 1 | `get_optimal_next_path_steps` — what should I learn next | `get_optimal_next_path_steps` |
| 2 | `get_learning_path_critical_path` — the fastest route to the life path | `get_learning_path_critical_path` |
| 3 | `get_knowledge_application_opportunities` — where can I apply this | `get_knowledge_application_opportunities` |
| 4 | `get_unblocking_priority_order` — what unlocks the most | `get_unblocking_priority_order` |
| 5 | `get_ready_to_work_on_today` — the daily plan (live: `/api/context/next-action`) | `get_daily_work_plan` |
| 6 | `get_cross_domain_synergies` — one thing that helps many | `get_cross_domain_synergies` |
| 7 | `calculate_life_path_alignment` — am I living toward my life path | `calculate_life_path_alignment` |
| 8 | `get_schedule_aware_recommendations` — what fits right now | `get_schedule_aware_recommendations` |
| 9 | `get_cross_domain_perception_analysis` — self-rating against the tracked record | — |

## The two doors

1. **The Insights cards — the first door, being built.** Each hub method answers on an
   Insights card; the HTMX fragments that load the cards are the methods' routes. Method 3
   answers on the Ku detail page. Ruled 2026-10-08 (Q5): *"Let's go with your recommendation:
   build the Insights cards in the F8 rows (including the perception card you already said yes
   to for Q9), register the Askesis catalog entries as the staged second door, and skip the bare
   /api/context/{question} routes unless the cards need them as HTMX fragments."*
2. **The Askesis conversation — the second door, staged.** Askesis reaches a hub method by
   tool-selection ([askesis-tool-selection-queries.md](askesis-tool-selection-queries.md)): a
   catalog entry in `core/services/askesis/query_tools.py` that calls the wrapper with the
   authenticated user's context. The catalog holds one tool today (`count_goals_achieved`);
   the `check:` above fires when a hub method joins it. Until then the eight wrappers are
   registered `PLANNED` / `DELAYED` in `scripts/detect_bloat.py` (`_ASKESIS_HUB_DOOR`), where the
   detector reports them *masked* — a protocol member is loaded by name, so its liveness cannot
   be attributed — which is the documented reading, not a failure.

## The zoom lens's place in it

`get_filtered_context` on the nine facades (over `build_filtered_context`,
`core/services/filtered_context.py`) is the per-domain filtered view with stats — the zoom lens
beside the context's map. Its one caller, the daily plan, passes `status_filter="all"`, never
`sort_by`, and reads `stats` only; `metadata` has no reader. The filter / sort / metadata half
was built for the Activity list pages, which moved to the CRUD factory within a week, so an
improved means replaced that half — and it stays, by ruling, as the typed, vetted per-domain
read a tool-selection entry would call ("my overdue tasks by due date"). Ruled 2026-10-08 (Q7):
*"keep"*. Registered `_ZOOM_LENS_FILTER_HALF`, blocked by this heading. The PS stats read
beside it (`_compute_ps_stats`) counts `publication_state`, the authoring gate, not `status`.

## Method 2 waits on something else

The critical path (method 2) reads the context only; the walk through the LP structure it was
imagined for waits on the two LP backend methods ruled *build, not now*
([lp-backend-recommendation-methods.md](lp-backend-recommendation-methods.md)). It is
registered separately (`_HUB_CRITICAL_PATH`), blocked by that heading, not this one. Ruled
2026-10-08 (Q1): keep `lp` as the dependency it will read; make it honest on the populated
prerequisite map meanwhile.

## What this does NOT stage

The hub methods' *correctness* is not staged: method 1 raised on every source until its
application reads took a Ku uid; the schedule-aware fit was one constant until the clock
fallback was reachable; the per-candidate prerequisite boost was loop-invariant. Those are
fixed, and the hub answers truthfully behind whichever door opens.

## Resolution

Close this file when a hub method is callable from the Askesis conversation through the
catalog: delete `_ASKESIS_HUB_DOOR` and `_ZOOM_LENS_FILTER_HALF`, retarget any wrapper whose
protocol member changed, and move the file to `done/`.
