---
title: "DSL-Bridge Grounding — Principles/Recent-Topics"
updated: 2026-09-05
status: "registered"
registered: 2026-08-28
ruled: 2026-09-02
trigger: "the keyed A/B on the next bridge touch, or Mike schedules it"
check: "each argument in BOTH callers or NEITHER (git grep -c per file); git grep -n \"@link\" -- core/prompts/templates/ stays empty"
---

# DSL-Bridge Grounding — Principles/Recent-Topics

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

#474 (2026-07-04) grounded BOTH `LLMDSLBridgeService.transform_with_context` callers in the
user's active goals through one builder (`core/services/dsl/grounding.py`: `active_goal_titles`,
`goals_as_context`), riding a non-extractable `{user_context}` prompt slot. Two follow-ups were
deferred in that PR's thread and lived only in memory; one is now retired by ruling, one stays
registered.

1. **Goal-LINK persistence — RETIRED 2026-09-02 (Mike): goal links stay user-authored only.**
   On the extraction path a `FULFILLS_GOAL` edge comes from one source only: an explicit
   `@link(goal:<uid>)` the user wrote (`ActivityDSLParser.get_linked_goals`,
   `core/services/dsl/activity_dsl_parser.py`); `@goal(...)` stays a dropped attribute and the
   bridge never infers a link. (Goal links written elsewhere — the task form, goal→task
   generation from an explicit parent goal — are outside this ruling; none of them is an LLM
   inference over prose.)
   Grounding is title-only and recognition-only — it disambiguates what the model recognises
   and never resolves a title to a UID — and the bridge output carries no `@link`
   (`LLMDSLBridgeService._parse_llm_output` drops any the model emits, and the templates in
   `core/prompts/templates/dsl_*` teach none), so the model has no channel to a goal link. The
   2026-08-28 measurement (56 extracted tasks, 0 with any edge
   to a Goal; the 2 live `FULFILLS_GOAL` edges hand-authored) is the accepted design, not a
   parked cost: an edge the user did not author is a different kind of write. Do not build
   UID-aware grounding, a model-emitted `@link(goal:…)`, or a title→UID resolver on either
   bridge path. The ruling is also recorded at the code site (`grounding.py` module docstring),
   in ADR-069 § Decision 1.1 (amendment 2026-09-03, with the #473/#474 history) and in
   `DSL_SPECIFICATION.md` § `@link()`.
2. **`user_principles` / `recent_topics` grounding.** `transform_with_context` accepts both
   (`core/services/dsl/llm_dsl_bridge.py:301`); neither caller passes them
   (`core/services/journal/journal_service.py:286`,
   `core/services/user_entry/user_entry_processing_service.py:478`). Deliberately symmetric:
   adding either to ONE path re-introduces the asymmetry #474 closed — **add to BOTH together**.

**The prerequisite:** the keyed LLM A/B that #474 could not run (no key then; the Anthropic key
has been in dev since 2026-07-23) — does goal grounding actually lift recognition? Until that is
measured, extending grounding is adding inputs to an unverified effect.

**Named work:** (0) run the A/B on the two prompt-capture fixtures with a real key and record the
recognition delta here; (2) if it lifts, thread `user_principles` / `recent_topics` through BOTH
callers in one PR (principle titles via `UserContext.core_principle_uids`; recent topics from
the entry's own recent tags).
**Trigger:** (0) next touch of the bridge, or Mike schedules it; (2) the A/B.
**Check:** per argument — each must appear in BOTH callers or in NEITHER (neither today; a single
grep for either name would pass with one argument in each file):
`git grep -c "user_principles=" -- core/services/journal/journal_service.py core/services/user_entry/user_entry_processing_service.py`
`git grep -c "recent_topics=" -- core/services/journal/journal_service.py core/services/user_entry/user_entry_processing_service.py`.
Ruling guard for (1): `tests/unit/test_llm_dsl_bridge.py::test_bridge_output_carries_no_link_tag`
pins the drop, and `git grep -n "@link" -- core/prompts/templates/` stays empty — a `@link`
appearing in a bridge template is the retired path being rebuilt, not a feature.
**Named cost while parked:** the recognition-quality claim behind #474 stays unmeasured.
