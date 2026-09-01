---
title: "ADR-065: Functional Inference Contract (typed `*InferenceResult`, no DTO mutation)"
updated: 2026-07-18
status: current
category: decisions
tags: [adr, decisions, architecture, intelligence, dto, immutability, hexagonal]
related: [ADR-035, ADR-043, ADR-044]
---

# ADR-065: Functional Inference Contract (typed `*InferenceResult`, no DTO mutation)

**Status:** Accepted

**Date:** 2026-05-28

**Decision Type:** ✅ Pattern/Practice

**Related ADRs:**
- Closes a deferred risk from: ADR-035 (Tier Selection Guidelines) — that ADR
  flagged "intelligence services would operate on mutable DTOs (risky)" while
  rejecting the always-two-tier alternative, but did not specify how Tasks
  (which keeps Tier 3) would avoid the same hazard inside its own intelligence
  layer. This ADR specifies it.
- Extends: ADR-044 (Neo4j as Committed Architectural Choice) — same
  "create-the-chokepoint" / "make-the-contract-visible-in-the-type" instinct,
  applied to intelligence rather than persistence.
- Scoped by: ADR-043 (Intelligence Tier Toggle) — the inference layer this ADR
  governs is part of `.intelligence` / advanced engine, which is FULL-tier only.

---

## Context

`EntityInferenceService` and `AdvancedInferenceEngine` enriched
`TaskDTO` instances **in place**. Both `enhance_task_dto_with_inference` and
`enhance_task_dto_with_advanced_inference` accepted a `TaskDTO`, set
`knowledge_confidence_scores`, `knowledge_inference_metadata`, and
`learning_opportunities_count` directly on it, and returned the same DTO
wrapped in `Result.ok(...)`. The contract was implicit: nothing in the type
told a reader what inference was allowed to touch.

The caller side compounded the implicitness. `TasksCoreService.create_task`
constructed a frozen `Task`, round-tripped through `Task.to_dto()` *only*
because inference required something mutable, let inference modify the
returned DTO, and serialised the result. A comment in the body even noted the
work was happening because "inference mutates the DTO in place" — a
documented workaround rather than a designed flow.

This is exactly the hazard ADR-035 named when rejecting the always-two-tier
alternative for complex domains: "Intelligence services would operate on
mutable DTOs (risky)". ADR-035 closed that door at the *tier* level by
keeping Tier 3 frozen domain models for Tasks/Goals/Habits/Events/Choices/
Principles, but did not close the corresponding door at the *intelligence*
level — Tasks' inference path still required a mutable intermediary anyway,
recreating the hazard one level down.

Five more Activity Domains (Goals, Habits, Events, Choices, Principles) are
slated to grow inference services as the pattern propagates. Replicating the
"return Result[DomainDTO], mutate in place" shape across six domains would
mean six implicit contracts and six identical workarounds — and at that scale
"intelligence is the exception to immutability" becomes an architectural
position by accumulation, not by decision.

A second debt surfaced alongside this: `AdvancedInferenceEngine` carried
dormant `_validation_feedback` instance state (`defaultdict[str, list[float]]`),
plus `add_validation_feedback()` and `validate_inference_batch()` methods.
The feedback loop fed a `validation_boost` term inside
`calculate_advanced_confidence_score`. Nothing in the codebase ever called
`add_validation_feedback` — no routes, no services, no jobs. There were no
TODOs naming when it would be wired, no roadmap commitment, no design notes
on where the feedback would come from. It was speculative infrastructure
that survived because removing it was no one's job.

## Decision

**Inference services return a typed, frozen `*InferenceResult` dataclass
carrying ONLY the enrichment fields. Callers apply via `dataclasses.replace`.
Intelligence services do not mutate their inputs.**

For Tasks specifically (lead domain — other 5 follow this template when
their inference services are built):

1. **New type:** `core/models/task/task_inference_result.py` defines
   `TaskInferenceResult` — a frozen dataclass with exactly the three
   enrichment fields (`knowledge_confidence_scores`,
   `knowledge_inference_metadata`, `learning_opportunities_count`) and an
   `as_kwargs()` helper for clean replace-call sites.

2. **Inference signatures change:**
   - `EntityInferenceService.enhance_task_dto_with_inference(task)`
   - `EntityInferenceService.enhance_task_with_knowledge_inference(task)`
   - `EntityInferenceService._enhance_with_advanced_inference(task)` (internal; was `AdvancedInferenceEngine.enhance_task_dto_with_advanced_inference` before the engine class was merged into `EntityInferenceService`)
   - `EntityInferenceService._basic_inference_fallback(task)` (internal)

   All now accept `Task | TaskDTO` (they read content, they don't write
   structure) and return `Result[TaskInferenceResult]` instead of
   `Result[TaskDTO]`. No method mutates its input.

3. **Caller pattern:** `TasksCoreService.create_task` becomes:

   ```python
   task_draft = Task.from_request(task_request, user_uid=user_uid)

   if self.ku_inference_service:
       inference_result = self._enhance_with_knowledge_inference(task_draft)
       if inference_result.is_error:
           return Result.fail(inference_result)
       enrichment = inference_result.value
       if enrichment is not None:
           task_draft = dataclasses.replace(task_draft, **enrichment.as_kwargs())

   payload = task_draft.to_dict()
   ```

   No DTO round-trip exists solely to give inference something mutable. The
   Task ↔ DTO conversion remains where it is genuinely needed (persistence
   serialisation), but it is no longer a smokescreen for in-place mutation.

4. **Dormant `_validation_feedback` machinery is deleted:** the instance
   state, `add_validation_feedback()`, `validate_inference_batch()`, the
   `enable_validation_feedback` config knob, the `validation_boost` branch
   inside `calculate_advanced_confidence_score`, and the
   `validation_feedback` block in `get_inference_statistics`. Per SKUEL's
   One Path Forward principle (CLAUDE.md), dead code is deleted, not
   archived. When validation feedback becomes a real feature, it will get
   its own ADR and a design anchored on real callers — not preserved
   instance state in search of a use case.

## Alternatives considered

### Alternative 1 — Keep mutable-DTO inference and live with the risk

Leave `enhance_*` returning `Result[TaskDTO]` after in-place mutation; add a
docstring noting the contract.

**Pros:** Zero refactor cost. Six future domains follow the same path
trivially.

**Cons:** Docstring contracts don't survive — they drift, get skimmed,
and don't show up in IDE / type-checker output. The risk ADR-035 named stays
open. Each new domain that adopts the pattern reaffirms by inertia that
intelligence is allowed to mutate DTOs, which is exactly the implicit
position One Path Forward asks us to avoid.

**Why rejected:** ADR-035 already named this risk as deferred. Six domains
of propagation is the wrong scale at which to keep deferring it.

### Alternative 2 (Variant B1) — Functional contract returning a fresh full DTO

Have inference return `Result[TaskDTO]` containing a freshly-constructed DTO
(no input mutation), and have the caller copy enrichment fields off it.

**Pros:** Reuses the existing DTO type; no new dataclass.

**Cons:** The contract stays implicit — the type says "a TaskDTO" but the
caller actually only consumes three fields off it. Callers would either
copy-pasta the field list at each site or write a helper that, in effect,
*becomes* `TaskInferenceResult` without the type discipline. Future inference
methods could quietly start "claiming" new fields without anyone noticing,
because the type didn't narrow.

**Why rejected:** the entire point of the refactor is to make what inference
produces visible at the boundary. B1 trades the in-place hazard for an
implicit-contract hazard. B2 (chosen) makes the contract the type.

### Alternative 3 — Build a `ValidationFeedbackStore` now

Keep the `add_validation_feedback` / `validate_inference_batch` surface and
wire it to a real persistence backend (e.g. a Neo4j edge or a
`feedback.jsonl` append log) so it stops being dead code.

**Pros:** Closes the dormancy by *using* the infrastructure rather than
removing it.

**Cons:** No caller has asked for this. There is no design for *where*
feedback would come from (UI? teacher review? user agreement on suggested
KU tags?), no design for how the boost would be evaluated (what counts as a
correct inference?), no roadmap commitment. Building a store would lock the
data shape (`list[float]` of feedback scores per knowledge_uid) before the
real callers exist, which is the wrong direction — feedback design should
follow the caller, not precede it.

**Why rejected:** speculative infrastructure for a feature with no current
callers. SKUEL deletes dead code (One Path Forward). When feedback becomes a
real feature, it will be designed against real callers with its own ADR.

## Consequences

### Positive

- ADR-035's deferred risk ("intelligence services would operate on mutable
  DTOs") is closed at the inference layer for Tasks. The same closure is
  available as a template for Goals/Habits/Events/Choices/Principles when
  those domains gain inference.
- Inference's output is visible in the type. A reader looking at
  `Result[TaskInferenceResult]` knows immediately that exactly three fields
  may be set; they don't have to read the body of `enhance_*` to find out
  what was mutated.
- Frozen `Task` no longer needs a DTO smokescreen at create time. The
  Task ↔ DTO round-trip in `create_task` exists where it pays for itself
  (persistence), not where it merely accommodates a mutable intermediary.
- Dormant `_validation_feedback` infrastructure is removed — one fewer dead
  code path, one fewer surface for confused future modifications.

### Negative / caveats

- `TaskDTO` is **not** deleted by this ADR. It remains the persistence
  translation layer (used by `Task.to_dict() / .from_dict()`, by
  `calendar_service.py`, by `goal_task_generator.py`, and by the generic
  Neo4j backend's read-path deserialisation). What changed is that
  intelligence no longer mutates it. A future ADR may revisit `TaskDTO`'s
  role; that's separate work.
- `dataclasses.replace()` returns a new `Task` — the caller must reassign
  (`task_draft = dataclasses.replace(task_draft, ...)`). Forgetting the
  assignment silently drops the enrichment. The frozen-Task pattern makes
  this hard to miss (no in-place mutation possible), but it is a different
  ergonomic shape than the old code.
- Removing `add_validation_feedback` / `validate_inference_batch` means a
  hypothetical *future* validation-feedback feature starts from scratch
  rather than from preserved infrastructure. This is intentional: the
  preserved infrastructure was preserving its own assumptions about a
  feature that didn't exist.

### Migration

None required for inference call sites outside Tasks — the only caller of
`enhance_*_inference` was `TasksCoreService.create_task`, updated in this
PR. Test mocks that returned `Result.ok(TaskDTO)` were updated to return
`Result.ok(TaskInferenceResult(...))`.

The other 5 Activity Domains have no inference services today. When they
gain inference, each should define a `{Domain}InferenceResult` following
the same shape — typed enrichment-only fields, frozen, with an `as_kwargs()`
helper.

## See Also

- [ADR-035](ADR-035-tier-selection-guidelines.md) — where the deferred risk
  this ADR closes was first named.
- [Activity Domain Inference Migration roadmap](../roadmap/activity-domain-inference-migration.md)
  — per-domain plan to bring Goals/Habits/Events/Choices/Principles to
  parity with the Tasks template.
- `/docs/patterns/three_tier_type_system.md` § "Intelligence is the
  exception" — the pattern-level note that points back here.
- `core/models/task/task_inference_result.py` — the type.
- `core/services/entity_inference_service.py` — the contract enforced (engine merged in; no separate `advanced_inference_engine.py`).
- `core/services/tasks/tasks_core_service.py::create_task` — the canonical
  caller pattern.
