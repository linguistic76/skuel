---
title: "Priority Scoring — the Ranking No Route Asks For"
updated: 2026-10-10
status: "staged"
registered: "2026-09-30 (skills review batch 6 — skuel-search-architecture)"
ruled: "2026-10-10 — the founder: the priority-scoring machinery is staged (PLANNED), not deleted"
trigger: "a page or route wants a user's activities ranked for them — the /search results, the daily plan, or an Askesis answer"
check: "git grep -n -E '\\.get_prioritized\\(|\\.get_standalone_steps\\(|(intelligent|advanced)_search\\([^)]*user_context' -- adapters ui core/services/user"
---

# Priority Scoring — the Ranking No Route Asks For

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What exists

- **The scorers.** `score_task`, `score_goal`, `score_habit`, `score_event`, `score_choice` and
  `score_principle` (`core/models/search/scoring.py`) each weigh a domain's components —
  deadline proximity, priority level, goal alignment, progress momentum, streak protection —
  against a `UserContext` and return a `PriorityScore` in 0.0–1.0.
- **Door 1: search results.** `SearchRouter._score_results` (`core/orchestrator/search_router.py`)
  sets `SearchResultItem.priority_score`, which `combined_score` weighs at 40%.
  `intelligent_search` and `advanced_search` run it **only when handed a `user_context`**.
  Neither route passes one (`GET /api/search/intelligent`, `POST /api/search/unified` in
  `adapters/inbound/search_routes.py`), so `priority_score` is 0.0 on every result a user sees.
  (The vector rungs copy a `priority_score` node property, which no entity model stores.)
- **Door 2: `get_prioritized`.** Each Activity search service has
  `get_prioritized(user_context, limit=10)`: Tasks, Goals, Habits, Events, Choices and
  Principles. Each reads the user's candidate set, hydrates any edge-derived field its scorer
  reads, scores, and cuts to `limit`. `TasksService.get_prioritized` is the one facade
  delegation. The curriculum pair is `PsSearchService.get_prioritized` and
  `LpSearchService.get_prioritized`, both `(user_uid, context, limit=20)` and ranked in their
  backends. Nothing calls any of the eight.
- **`PsSearchService.get_standalone_steps`** lists PathSteps in no learning path. Nothing outside
  its service calls it, and the `PsService` facade does not delegate it.
- **The candidate reads are whole-set reads.** The Choices, Events, Goals and Principles reads go
  through `find_all_by`, and the Tasks read asks `get_user_entities` for `QueryLimit.MAXIMUM` and
  calls `warn_if_capped`. A ranking cut to `limit` must see every candidate first; a 100-row page
  would rank an arbitrary hundred.

`./dev bloat` cannot see any of this: each method's name collides with a live one elsewhere
(vulture matches by name), and the scorers are called — by the staged methods. The subjects are
registered by hand in `PLANNED_METHODS`
(`scripts/detect_bloat.py`, `_PRIORITY_SCORING`).

## Staged, not retired

The founder ruled the machinery staged on 2026-10-10. The capability is ranking a user's
activities by what matters to them now, across domains. It stays, with its tests, until a surface
asks for it.

## What wiring it takes

1. **Choose the surface.** The `/search` page orders results today by relevance alone. The daily
   plan has its own ranking (`UserContextIntelligence`). An Askesis answer is the third
   candidate.
2. **Hand it a context.** A search route that builds the caller's `UserContext` and passes it to
   `intelligent_search` / `advanced_search` lights door 1 on that route. Check which context depth
   the scorers read before choosing `build()` or `build_rich()`.
3. **Retire the entries** for whatever is wired. Delete the `_PRIORITY_SCORING` keys the wiring
   reaches, and move this file to `done/` when none remain.
