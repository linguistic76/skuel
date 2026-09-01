---
title: "ADR-059: Engagement-Aware Daily Plan in Askesis"
updated: 2026-09-01
status: current
category: decisions
tags: [adr, decisions, askesis, engagement, daily-plan]
related: [ADR-043, ADR-048, ADR-055]
---

# ADR-059: Engagement-Aware Daily Plan in Askesis

**Status:** Implemented (2026-05-13) — landed with one deliberate deviation from the original Decision; see "As Shipped" below.

**Date:** 2026-05-10

**Decision Type:** Pattern/Practice

**Related ADRs:**
- ADR-043 — Intelligence Tier Toggle (Askesis is FULL-tier)
- ADR-048 — Adaptive Learning Loop (the lifecycle this ADR rides on)
- ADR-055 — Architectural Lenses (Askesis is a cross-cutting subsystem)

---

## Context

The PS+Activity lifecycle (Template → Engaged → Completed/Abandoned) shipped
between May 1 and May 9, 2026. The Askesis ↔ engagement wiring at the
**bundle layer** shipped alongside it. What is already in place:

- `PsEngagementService` (`core/services/ps_engagement/`) provides
  `publish_pathstep`, `engage_pathstep`, `complete_pathstep`, `abandon_pathstep`.
- `Engagement` (`core/services/ps_engagement/engagement.py:17-34`) is the
  frozen projection of the `(User)-[:ENGAGED_WITH {state, since, ...}]->(PS)`
  edge: `state`, `since`, `completed_at`, `abandoned_at`, `spawned_instance_uids`.
- `PsBundle.engagement: Engagement | None`
  (`core/models/askesis/ps_bundle.py:54`) carries the lifecycle snapshot
  per Socratic turn.
- `ContextRetriever._find_active_ps`
  (`core/services/askesis/context_retriever.py:505-571`) prefers engaged
  candidates over published-but-not-engaged ones and populates the bundle's
  `engagement` field.
- `create_askesis_service` (`core/services/askesis_factory.py:20`) takes
  `ps_engagement_service` and `_intelligence_hub.py:208` wires it.
- `_spawn_orchestrator` (`core/services/ps_engagement/_spawn_orchestrator.py:278`)
  resolves every Activity Template's `RelativeOffset` to absolute date/datetime
  fields **on the spawned instance** at engagement time. Spawned tasks and
  events carry concrete `due_at` / `scheduled_at` — there is no separate
  "PS engagement deadline" to compute.
- `adapters/inbound/askesis_api.py` was pruned to a single route
  (`/api/askesis/ask`); 16 unreferenced endpoints were deleted under
  "One Path Forward."

What is **not** yet in place: `AskesisService.get_daily_work_plan`
(`core/services/askesis_service.py:417-467`) delegates straight to
`UserContextIntelligence.get_ready_to_work_on_today()`. That method
synthesizes a daily plan from UserContext (at-risk habits, today's events,
overdue tasks, advancing goals, etc.) but is engagement-blind: it does
not separate "items spawned from a PS the user is currently engaged with"
from "items that exist independent of any PS engagement," and it cannot
surface "PS X — engaged May 3, three of its spawned tasks are pending"
as a coherent unit.

The bundle knows about engagement; the plan does not. That is the gap.

---

## Decision

**Make `get_daily_work_plan` engagement-aware by bucketing its output, not
by adding new fields or recomputing dates.** Specifically:

1. **`DailyWorkPlan` gains two grouping affordances** (additive — existing
   per-domain lists stay):
   - `engaged_ps_groups: tuple[EngagedPsGroup, ...]` — one entry per PS the
     user is currently engaged with, holding the PS, the engagement snapshot
     (state + since), and the spawned activities still pending. Built by
     joining `bundle.engagement.spawned_instance_uids` against the existing
     domain lists.
   - `available_to_start: tuple[PathStep, ...]` — published PSes the user
     has touched but not engaged with. Surfaced only when the engaged set
     is empty or when the caller explicitly asks "what's next."

2. **`AskesisService.get_daily_work_plan` reads engagement from the bundle
   it already has access to**, and queries `PsEngagementService.list_engaged`
   for the user's full engaged-PS set (a single edge scan keyed on `user_uid`,
   already indexed). It does not recompute deadlines — spawned activities
   already carry absolute date fields.

3. **Activities not associated with any engaged PS keep their existing
   ranking.** This ADR does not re-rank the rest of the daily plan — habits,
   independent tasks, calendar events, and goal progress flow through the
   same `UserContextIntelligence` path as today.

This is the minimum change that lets Askesis answer "what's pending from
the things you're actively engaged with" without changing data shapes or
duplicating deadline resolution.

---

## Alternatives Considered

### Alternative 1: Push engagement-awareness into `UserContextIntelligence`

**Why rejected:** `UserContextIntelligence.get_ready_to_work_on_today()` is
consumed by surfaces beyond Askesis (the home dashboard, the schedule
recommender). Forcing PS-engagement grouping on every consumer pays a cost
they don't all need. Askesis is the surface that frames work as
"what's pending from your current learning engagements"; other surfaces
correctly frame work as "what's due today across all domains."

### Alternative 2: Add `engagement_deadline` to `PsBundle` and resolve `RelativeOffset` in the bundle builder

**Why rejected:** `RelativeOffset` lives on Activity Templates, not on
`PathStep`. There is no PS-level offset to resolve, and spawned instances
already carry the absolute dates the ADR would otherwise recompute. Adding
a derived field would duplicate `_spawn_orchestrator`'s output and create
a second source of truth for "when is this due."

### Alternative 3: Wait for a fuller pedagogical-prompt rewrite

**Why rejected:** The bundle is engagement-aware today; the daily plan
isn't. The plan rewrite is independently valuable and cheap. Sequencing
it behind a larger redesign blocks a small, correct fix.

---

## Consequences

### Positive

- Askesis's "what should I work on" surface can name the engagement:
  "From *PS Algebra-Linear-Maps* (engaged May 3): two pending tasks, one
  scheduled event tomorrow."
- Published-but-not-engaged PSes become a clearly separated affordance
  — students see the engage/start step explicitly rather than mixed into
  a flat list.
- No new fields on `PsBundle`, no new helper, no second deadline-resolution
  path. The change is scoped to the daily-plan synthesis.

### Negative

- `DailyWorkPlan` gains two optional fields; downstream destructuring by
  position (none currently) would need updates.
- One additional `PsEngagementService.list_engaged` call per daily-plan
  build. Single edge scan, indexed; expected p95 impact <5 ms.

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `list_engaged` adds latency | Low | Low | Single indexed edge scan; measure before/after; cache per UserContext build if regression > 20 ms. |
| Bucketing surfaces a confusing empty state when nothing is engaged | Medium | Low | Empty `engaged_ps_groups` falls back to `available_to_start`; UI copy explains the distinction. |
| Spawned activities listed twice (in their domain bucket and in the engaged group) | High | Low | Engaged groups *reference* activity UIDs; UI renders one bucket or the other based on caller intent. Confirm via integration test. |

---

## Implementation Details

### Original Proposed Files (superseded — see "As Shipped" below)

**Modified:**
- `core/models/askesis/daily_work_plan.py` — add `engaged_ps_groups`, <!-- historical -->
  `available_to_start` (both default-empty tuples).
- `core/services/askesis_service.py` — `get_daily_work_plan` post-processes
  the existing `UserContextIntelligence` output: fetch engaged PSes, group
  spawned activity UIDs against the per-domain lists, populate the buckets.
- `tests/integration/test_askesis_rag_wiring.py` — extend to cover (a) a
  user with one engaged PS and two spawned pending tasks, (b) a user with
  one available-to-start PS and no engagements, (c) an abandoned engagement
  that should not appear.

**New:** none. The bundle already carries the engagement; `_spawn_orchestrator`
already resolves dates; routes are already pruned.

### Original Wiring Sketch (superseded)

```python
# core/services/askesis_service.py — get_daily_work_plan
plan = await intelligence.get_ready_to_work_on_today(...)
engaged = await self._ps_engagement.list_engaged(user_uid)
groups = self._group_by_engagement(plan, engaged)
available = await self._published_but_not_engaged(user_uid, engaged)
return Result.ok(plan.with_buckets(engaged_ps_groups=groups, available_to_start=available))
```

### As Shipped (2026-05-13)

The bucketing landed in `UserContextIntelligence` (`DailyPlanningMixin`),
not in `AskesisService` — the path "Future Considerations § When to Revisit"
predicted. A second consumer (`SynergyIntelligenceMixin`) needed the same
engagement state during implementation, so lifting one level upstream
avoided the duplication the original Decision would have introduced.

The dataflow as shipped:

1. `UserContextBuilder.build_rich` calls `PsEngagementService.list_engaged`
   and writes the result into `RichUserContext.active_ps_engagements`
   (`core/services/user/user_context_builder.py:418`).
2. `DailyPlanningMixin.get_ready_to_work_on_today` reads
   `self.context.active_ps_engagements`, builds `EngagedPsGroup` entries
   via `_build_engaged_groups`, and computes `available_to_start` via
   `_compute_available_to_start`
   (`core/services/user/intelligence/daily_planning.py:362-371`).
3. `AskesisService.get_daily_work_plan` is now a pass-through —
   `engaged_ps_groups` and `available_to_start` are already populated on
   the `DailyWorkPlan` returned from
   `intelligence.get_ready_to_work_on_today()`
   (`core/services/askesis_service.py:446-477`).

**Files as actually modified:**

- `core/models/context_types.py:1511` — `EngagedPsGroup` dataclass.
- `core/models/context_types.py:1573-1574` — `DailyWorkPlan.engaged_ps_groups`,
  `DailyWorkPlan.available_to_start`.
- `core/services/user/unified_user_context.py:259-269` —
  `RichUserContext.active_ps_engagements` + spawned-instance reverse index.
- `core/services/user/user_context_builder.py:418` — builder populates the
  field via `list_engaged`; logs and leaves `None` on failure.
- `core/services/user/intelligence/daily_planning.py:362-371` — bucketing
  logic and `replace(plan, engaged_ps_groups=..., available_to_start=...)`.
- `core/services/askesis_service.py:446-450` — docstring updated to point
  consumers at the upstream populating site.

### Testing Strategy

- [x] **Unit:** bucketing logic groups spawned activity UIDs correctly when
  some are completed, some pending, some abandoned —
  `tests/unit/test_daily_planning_bucketing.py`.
- [x] **Unit:** `available_to_start` excludes any PS in the engaged set —
  `tests/unit/test_daily_planning_bucketing.py`.
- [x] **Unit:** rendered "engaged PS" UI section gates on empty buckets — was
  `tests/unit/test_engaged_ps_section.py`, deleted in #519 along with the dead overview <!-- historical -->
  constellation it covered. No successor: that UI section is gone.
- [~] **Integration:** intentionally **not** added to
  `tests/integration/test_askesis_rag_wiring.py` (and a note at line 140-143
  of that file documents the move). Because bucketing happens in
  `DailyPlanningMixin`, the unit tests above exercise the same code path
  the Askesis surface ultimately hits — adding a Neo4j-backed integration
  test would re-verify the same logic at a higher cost. If a future
  end-to-end smoke test for Askesis daily-plan rendering is desired, it
  belongs alongside other Askesis surface tests, not in `test_askesis_rag_wiring.py`.
- [ ] **Manual:** exercise `/askesis/api/submit` with a fixture user
  holding one engaged PS and one published-but-not-engaged PS; confirm the
  two surfaces render differently.

---

## Future Considerations

### When to Revisit

- If a second consumer (home dashboard, schedule recommender) needs
  engagement grouping, lift the bucketing into `UserContextIntelligence`
  rather than duplicating it.
- When ZPD gating arrives (don't engage a new PS until current one reaches
  mastery threshold), the gate sits on top of `available_to_start` —
  separate ADR.

### Out of Scope

- Engagement-aware Socratic prompt rewriting (the bundle already carries
  `engagement.state` and `engagement.since`; prompt builders can read them
  whenever a follow-up effort prioritizes that work).
- Recovery dialogues for abandoned engagements.
- Teacher-side surfaces showing per-student engagement state (ADR-040
  teacher-review track owns those).

---

## References

- ADR-043 — Intelligence Tier Toggle
- ADR-048 — Adaptive Learning Loop
- `core/services/ps_engagement/` — engagement service, gateway, spawn orchestrator
- `core/models/templates/relative_offset.py` — value type already consumed by `_spawn_orchestrator`
- `core/services/askesis/context_retriever.py:396-571` — engagement-aware bundle building (already shipped)
- `core/services/askesis_service.py:417-477` — daily-plan entry point (pass-through after 2026-05-13; bucketing happens upstream in `DailyPlanningMixin`)
- `core/services/user/intelligence/daily_planning.py:362-371` — actual bucketing site
- `tests/unit/test_daily_planning_bucketing.py` — coverage for the shipped path (its
  `test_engaged_ps_section.py` sibling went with the UI it tested, #519)
