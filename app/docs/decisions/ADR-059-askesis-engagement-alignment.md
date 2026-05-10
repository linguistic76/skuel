---
title: "ADR-059: Aligning Askesis with the Template -> Engaged Lifecycle"
updated: 2026-05-10
status: current
category: decisions
tags: [adr, decisions, askesis, engagement, lifecycle, ps-engagement]
related: [ADR-043, ADR-048, ADR-055]
---

# ADR-059: Aligning Askesis with the Template -> Engaged Lifecycle

**Status:** Proposed

**Date:** 2026-05-10

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-043 (Intelligence Tier Toggle) — Askesis is the FULL-tier conversational surface
- Related to: ADR-048 (Adaptive Learning Loop) — engagement is the lifecycle the loop runs inside
- Related to: ADR-055 (Architectural Lenses) — Askesis is a cross-cutting subsystem

---

## Context

The PS+Activity lifecycle (Template -> Engaged -> Completed/Abandoned) shipped
between May 1 and May 9, 2026:

- `core/services/ps_engagement/ps_engagement_service.py` provides
  `publish_pathstep`, `engage_pathstep`, `complete_pathstep`, `abandon_pathstep`.
- `(User)-[:ENGAGED_WITH {since, state, ...}]->(PS)` carries the lifecycle
  (`EngagementState = Literal["engaged", "completed", "abandoned"]`,
  `core/services/ps_engagement/engagement.py:17`).
- `core/models/templates/relative_offset.py` defines the `RelativeOffset`
  value type used by Activity Templates to express timing as
  "N days/weeks after engagement."
- The 6 Activity Templates (Task / Goal / Habit / Event / Choice / Principle)
  attach to a published PS, and `_spawn_orchestrator` materializes instances
  on engagement using a 4-layer topological order.

Askesis (`core/services/askesis/`, `core/services/askesis_service.py`,
`core/models/askesis/`) was not touched in that window and still operates as
if PathSteps are statically authored content rather than a Template that a
student engages with. The bundle loader, daily-plan ranker, and recommendation
surface are all timeline-unaware:

- `PsBundle` (`core/models/askesis/ps_bundle.py:33-65`) carries the PathStep,
  KUs, Resources, and Activity entities — but no `engaged_at`,
  `engagement_state`, `template_uid`, or computed deadlines.
- `ContextRetriever._find_active_ps()` reads `active_path_steps_rich` from
  UserContext, which knows the user touched the PS but not whether the
  ENGAGED_WITH edge exists or when it was created.
- `RelativeOffset` is never resolved to an absolute datetime anywhere in
  the Askesis pipeline.

The functional consequence is not aesthetic. Recommendations rank
published-but-not-engaged PathSteps alongside actively engaged ones, deadlines
are absent from prompt context, and the "what should I do today" surface
cannot distinguish "available to start" from "in flight, due Friday."
Askesis is wired (`services_bootstrap/_intelligence_hub.py:172`) and
callable (`/askesis/api/submit`), but its model of the world predates the
lifecycle that now governs every PS-derived recommendation.

---

## Decision

**Adopt the engagement lifecycle as a first-class input to the Askesis
context bundle and ranker.** Specifically:

1. **`PsEngagementService` is a required dependency of `ContextRetriever`.**
   Wire it through `create_askesis_service()` in
   `core/services/askesis_factory.py`. No `None` default — Askesis already
   gates on `INTELLIGENCE_TIER=full`, and engagement is a core-tier service,
   so it is always available wherever Askesis runs.

2. **`PsBundle` gains four engagement fields** (frozen, optional only because
   a freshly published PS has no engagement until the student engages):
   - `engagement_state: EngagementState | None`
   - `engaged_at: datetime | None`
   - `engagement_deadline: datetime | None` (computed from PS-level
     `RelativeOffset` if present, else `None`)
   - `template_uid: str | None` (the Activity Template the spawned instance
     was rendered from, for the activities already in the bundle)

3. **A new `engagement_time_resolver` helper** lives at
   `core/services/askesis/engagement_time_resolver.py`. Single function:
   `resolve_deadline(engaged_at: datetime, offset: RelativeOffset) -> datetime`.
   Called from `_build_path_step` once per bundle build.

4. **`get_daily_work_plan()` ranks by engagement, not publication.** The
   query becomes "PathSteps the user is currently `engaged` with, ordered
   by deadline ascending (overdue first), then by ZPD readiness." Published-
   but-not-engaged PathSteps move to a separate "available to start" bucket
   that is surfaced only when the engaged set is empty or when the user
   explicitly asks "what's next."

5. **The 17 routes in `askesis_api.py` are audited and the dead set
   removed in the same change.** A route that has no caller in
   `ui/askesis/`, `static/js/`, or another service is deleted, not preserved.
   This is consistent with "One Path Forward" — Askesis does not maintain
   aspirational endpoints.

This is the minimum change that lets Askesis answer "what is due, and when"
truthfully. Deeper integrations (engagement-aware Socratic prompts, ZPD
gating of new engagements, abandoned-PS recovery dialogues) are deferred
until this baseline is in place.

---

## Alternatives Considered

### Alternative 1: Leave `PsBundle` alone; compute deadlines at render time in the daily-plan endpoint

**Why rejected:** The bundle is the contract every downstream Askesis
consumer reads — IntentClassifier, EntityExtractor, ResponseGenerator, and
the prompt builders. Putting deadline awareness only in the daily-plan
endpoint means the Socratic prompt builder still tells the LLM "the user
is studying X" with no timing context, and recommendations rendered through
other endpoints stay timeline-blind. The bundle is the right seam.

### Alternative 2: Fold engagement state into UserContext and let Askesis read it from `active_path_steps_rich`

**Why rejected:** UserContext is already wide (~250 fields under
`build_rich()`). Adding per-PS engagement metadata to every UserContext
build pays the cost on every page load, including pages that have nothing
to do with curriculum. Askesis is the only consumer that needs the full
lifecycle shape; `PsEngagementService` is cheap to call directly when
building the bundle. ZPD followed the same reasoning (computed at the end
of `build_rich()`, not denormalized everywhere).

### Alternative 3: Wait for a fuller pedagogical-prompt rewrite

**Why rejected:** The lifecycle is shipping recommendations today.
Postponing alignment means daily-plan output is wrong now, not later.
The prompt rewrite and the data-shape alignment are independently valuable;
sequencing them serially blocks a fix on a larger redesign.

---

## Consequences

### Positive
- Daily plan and recommendation surfaces are timeline-correct: overdue
  engagements lead, available-to-start templates are clearly separated.
- Socratic prompt context can include "you engaged with this PS on
  May 3; the practice task is due tomorrow" — concrete grounding the
  current bundle cannot supply.
- `RelativeOffset` finally has a consumer in Askesis, closing the loop
  between Template authoring (teacher) and student-facing reminders.
- Dead routes in `askesis_api.py` are pruned in the same change, reducing
  the surface area future contributors have to reason about.

### Negative
- `PsBundle` gains four optional fields; downstream consumers that
  destructure the bundle by position (none currently — all use named
  fields) would need updates if any appear.
- `ContextRetriever` now depends on `PsEngagementService`, adding a
  per-bundle Cypher round-trip. Mitigation: a single `MATCH (u)-[r:
  ENGAGED_WITH]->(ps)` keyed on the active PS UID, indexed.
- The "available to start" bucket is a new UI affordance and may surface
  the publish/engage gap to users who previously saw a single flat list.
  This is a feature, not a regression, but it is a visible behavioral change.

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Engagement query adds noticeable latency to every Askesis turn | Low | Medium | Single edge lookup keyed on user_uid + ps_uid; both indexed. Measure p95 before/after; fold into UserContext if regression > 50ms. |
| `RelativeOffset` resolution drifts when a PS is republished after engagement | Medium | Low | `engaged_at` is frozen at engagement time. Republishing the PS does not reset deadlines for already-engaged students. Test in `test_engagement_time_resolver`. |
| Pruning routes in `askesis_api.py` removes one a hidden caller depends on | Low | Medium | Audit all of `ui/`, `static/js/`, `core/services/` for `/api/askesis/` strings before deletion; keep deletions in their own commit so they can be reverted independently. |

---

## Implementation Details

### Files

**New:**
- `core/services/askesis/engagement_time_resolver.py` — `resolve_deadline(engaged_at, offset) -> datetime`. Pure function, no I/O.
- `tests/unit/services/askesis/test_engagement_time_resolver.py`

**Modified:**
- `core/models/askesis/ps_bundle.py` — add `engagement_state`, `engaged_at`, `engagement_deadline`, `template_uid` (all `| None`).
- `core/services/askesis_factory.py` — accept `ps_engagement_service: PsEngagementService` (required), pass to `ContextRetriever`.
- `core/services/askesis/context_retriever.py` — `_find_active_ps()` and `_build_path_step()` query the engagement edge; populate the four new bundle fields.
- `core/services/askesis_service.py` — `get_daily_work_plan()` queries engaged instances first, ranks by `engagement_deadline` ascending, falls back to "available to start" bucket only when engaged set is empty.
- `services_bootstrap/_intelligence_hub.py` — pass `ps_engagement` into `create_askesis_service()`.
- `adapters/inbound/askesis_api.py` — audit and prune unreferenced routes (separate commit).

**Tests:**
- Unit: `test_engagement_time_resolver`, `test_ps_bundle_engagement_fields`, `test_context_retriever_engagement_wiring`.
- Integration: extend `tests/integration/test_askesis_rag_wiring.py` to cover an engaged PS with a future deadline and an abandoned PS (which should not appear in the daily plan).

### Wiring

```python
# core/services/askesis_factory.py
def create_askesis_service(
    *,
    backend,
    askesis_core_service,
    askesis_ai,
    askesis_citation,
    user_context_intelligence,
    zpd_service,
    ps_engagement_service: PsEngagementService,  # new, required
) -> AskesisService:
    ...
```

```python
# core/services/askesis/context_retriever.py — _build_path_step()
engagement = await self._ps_engagement.get_engagement(user_uid, ps.uid)
deadline = (
    resolve_deadline(engagement.since, ps.engagement_offset)
    if engagement and ps.engagement_offset
    else None
)
return PsBundle(
    path_step=ps,
    engagement_state=engagement.state if engagement else None,
    engaged_at=engagement.since if engagement else None,
    engagement_deadline=deadline,
    template_uid=engagement.template_uid if engagement else None,
    # ...existing fields
)
```

### Testing Strategy

- [ ] Unit: deadline resolution for `RelativeOffset` in days, weeks, months
- [ ] Unit: `PsBundle` accepts `None` engagement fields without breaking existing consumers
- [ ] Unit: `get_daily_work_plan` returns engaged-then-available ordering
- [ ] Integration: skipped tests in `test_askesis_ask_endpoint.py` re-enabled with engagement fixtures
- [ ] Manual: hit `/askesis/api/submit` against a test user with one engaged PS due tomorrow and one published-but-not-engaged PS; verify the response distinguishes them

---

## Future Considerations

### When to Revisit

- If `PsEngagementService.get_engagement` becomes a hot path (>20% of
  Askesis turn latency), denormalize engagement state into UserContext.
- If a second consumer outside Askesis needs `resolve_deadline`,
  promote the helper to `core/services/templates/`.
- When ZPD gating arrives (don't engage a new PS until current one
  reaches mastery threshold), the gate sits on top of this bundle, not
  inside it — separate ADR.

### Out of Scope

- Engagement-aware Socratic prompt rewriting (separate effort, depends
  on this).
- Recovery dialogues for abandoned engagements.
- Teacher-side surfaces showing per-student engagement state (the
  ADR-040 teacher-review track owns those).

---

## References

- ADR-043 — Intelligence Tier Toggle (Askesis is FULL-tier)
- ADR-048 — Adaptive Learning Loop (lifecycle context)
- `core/services/ps_engagement/` — engagement service and gateway
- `core/models/templates/relative_offset.py` — value type being consumed
- `docs/architecture/ASKESIS_ARCHITECTURE.md` — current Askesis design (to be updated alongside this change)
