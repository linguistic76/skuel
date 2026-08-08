---
title: "ADR-066: Typed Update Intents (frozen `*UpdateIntent`, one update path)"
updated: 2026-06-04
status: current
category: decisions
tags: [adr, decisions, architecture, dto, immutability, typing, hexagonal, activity-domains]
related: [ADR-065, ADR-044, ADR-043, ADR-035]
---

# ADR-066: Typed Update Intents (frozen `*UpdateIntent`, one update path)

**Status:** Accepted

**Date:** 2026-06-04

**Decision Type:** ✅ Pattern/Practice

**Related ADRs:**
- Extends: ADR-065 (Functional Inference Contract) — same instinct ("make the contract visible in
  the type; compute and return immutable values; let the caller apply via `dataclasses.replace`"),
  applied to the *write/update* path instead of the *inference* path. ADR-065 typed what inference
  is allowed to set; this ADR types what an update is allowed to change.
- Realizes: the "update intents" extension named as the natural next step in
  `docs/roadmap/functional-direction.md`.
- Scoped by: ADR-044 (Neo4j as Committed Architectural Choice) — the materialize-to-dict point sits
  exactly at the `UniversalNeo4jBackend` hexagonal seam.
- Sibling to: ADR-035 (three-tier type selection) — Pydantic at the edge, frozen dataclasses at the
  core; the `*UpdateIntent` is a core type, the `*UpdateRequest` stays the edge type.

---

## Context

Partial entity updates moved through SKUEL as **untyped `dict[str, Any]`**. Three layered problems:

**1. The `*UpdatePayload` TypedDicts were structurally unsound and decorative.**
`core/ports/query_types.py` defined `TaskUpdatePayload`, `GoalUpdatePayload`, … as `TypedDict`s and
the CRUD mixin docstring told callers to write `updates: TaskUpdatePayload = {...}; service.update(uid,
updates)`. That pattern does not type-check: a TypedDict is **not assignable to `dict[str, Any]`**
(`dict` is invariant and mutable). A bridging change widened the service `update` parameter to
`Mapping[str, Any]` (which a TypedDict *is* assignable to), but that only made the TypedDicts
*passable*, never *load-bearing*: real route updates flow Pydantic `*UpdateRequest` → `.model_dump()`
→ plain `dict[str, Any]`, and you cannot attach a TypedDict to `model_dump()` output. The few internal
sites that named a payload either `dict()`-wrapped it (erasing the type at the call site) or passed it
through an `Any`-typed attribute (unchecked). Net: **three competing contracts for one payload** —
Pydantic request model (the real validator), TypedDict (decorative), `dict[str, Any]` (what moves).

**2. The write boundary was semantically ambiguous.** `backend.update` performed three unrelated
jobs, and the service contract was a fourth path — with the *same partial payload shape* split across
two paths that have *different side effects*, chosen inconsistently across sibling methods:

| # | Path | Payload | `_validate_update`? | `_post_update` events? |
|---|------|---------|---------------------|------------------------|
| 1 | Service contract (`self.update` / `self.core.update` / `super().update`) | partial map | yes | yes |
| 2 | Backend-direct, partial (`self.backend.update({...})`) | partial map (same as #1) | no | no |
| 3 | Backend-direct, full-DTO (`self.backend.update(dto.to_dict())`) | whole entity | no | no |
| 4 | Backend-direct, metadata (`self.backend.update(self.update_properties())`) | system bump | no | no |

`tasks_progress_service`, `events_progress_service`, `habits_completion_service`,
`principles_core_service`, `choices_core_service` all issued partial updates straight to the backend
(#2), silently skipping validation and event publishing, while sibling methods used `self.update` and
got both. Upstream compounded it: the CRUD route factory writes `model_dump(exclude_unset=True)` while
`tasks_ui` writes "non-`None` values" — two different "which fields count" conventions.

The real axis was never "where does the `dict()` go." It is: **"is this a meaningful update that
should validate and announce itself, or a raw state write that deliberately should not?"** That axis
was implicit and decided by accident.

Six Activity Domains share this shape. Leaving it untyped and ambiguous means six implicit contracts,
two silently-diverging write paths per domain, and a docstring that lies about a feature that does not
type-check.

## Decision

**1. Replace the `*UpdatePayload` TypedDicts with a frozen `*UpdateIntent` dataclass per Activity
Domain** (Task, Goal, Habit, Event, Choice, Principle), carrying exactly the updatable fields and
nothing else. The contract becomes visible in the type: the only things an update may change are the
fields on the intent.

Update is *partial*, and `None` can be a meaningful value, so fields default to a shared `UNSET`
sentinel (PEP-661 style, type-checker-narrowable). The intent exposes `to_changes() -> dict[str, Any]`
returning only the set fields — the patch to apply.

```python
@dataclass(frozen=True)
class TaskUpdateIntent:
    title:    str   | Unset = UNSET
    status:   str   | Unset = UNSET
    priority: str   | Unset = UNSET
    progress: float | Unset = UNSET
    def to_changes(self) -> dict[str, Any]:
        return {f.name: v for f in fields(self)
                if (v := getattr(self, f.name)) is not UNSET}
```

**2. Establish ONE update path.** The service contract (`update` / `update_for_user`, and the domain
`update_<x>` facades) accepts the domain `*UpdateIntent`, runs `_validate_update` + `_post_update`
(events), and materializes `intent.to_changes()` → `dict` exactly once at the `backend.update` seam.
This is the only path permitted for partial / user-facing updates.

**3. Reserve `backend.update(dict)` for deliberate raw writes** — #3 full-DTO persistence and #4
system field bumps — each annotated `# raw-write: <why the lifecycle is bypassed>`. Partial updates
calling the backend directly (#2) are migrated onto the service contract.

**4. One flow, Pydantic at the edge.** `*UpdateRequest` (Pydantic, adapter boundary) gains
`.to_intent() -> *UpdateIntent`, built from `model_fields_set`. End to end:
**HTTP → Pydantic validate → `.to_intent()` → service contract → `to_changes()` → dict → backend.**

**5. Delete the alternatives.** Remove every `*UpdatePayload` TypedDict and the CRUD-mixin docstring
that advertises them; collapse the bridging `Mapping[str, Any]` signatures to the intent types; and
purge/rewrite all documentation and skills that teach the old `update(uid, dict)` / TypedDict patterns,
so the One Path is the only path a reader (human or agent) can find.

This propagates Tasks-first (the ADR-065 lead domain) to all six Activity Domains. See
`docs/roadmap/done/update-intents.md` for the phased, context-reset-friendly migration.

## Consequences

**Positive**
- The update contract is **load-bearing and visible in the type** — a reader sees exactly what an
  update may touch, and the type cannot be silently widened to `dict` and back.
- **One write path** for meaningful updates; validation and events can no longer be skipped by accident.
  The rare intentional bypass is explicit and greppable (`# raw-write:`).
- **Immutability + no input mutation** (the functional-direction principle): the
  `updates["status"] = ...` mutate-after-construct pattern becomes `replace(intent, status=...)`.
- **One contract per payload** instead of three half-connected ones; the `*UpdateRequest` → `*UpdateIntent`
  hand-off is the single seam.

**Negative / costs**
- Six domains × (intent dataclass + `to_intent()` + service-signature migration + route migration +
  #2 straggler cleanup). Mechanical but broad; mitigated by the Tasks reference template and per-domain
  context resets.
- A new shared `UNSET` sentinel primitive (or reuse of an existing one).
- Service-authored transitions become slightly more verbose (`EventUpdateIntent(status=...)` vs a dict
  literal) — an acceptable trade for the typed, single path.

**Neutral**
- The backend port (`Neo4jProperties = dict[str, Neo4jValue]`) is unchanged; the materialization seam
  stays at the service↔backend boundary (one `to_changes()` per call).

## Alternatives considered

- **Keep TypedDicts, pass directly to the `Mapping[str, Any]` contract.** The local optimum that the
  bridging change already enables. Rejected: structural typing remains silently widenable to `dict`,
  the three-contract split persists, and nothing forces the single write path. Not load-bearing.
- **Reuse the Pydantic `*UpdateRequest` as the service-contract type (`frozen=True`).** Fewer types.
  Rejected: pushes an edge/validation type into core service signatures, violating the three-tier
  "Pydantic at the edges, frozen dataclasses at the core" boundary (ADR-035).
- **Do nothing.** Rejected: the docstring advertises a pattern that does not type-check, and the
  #1/#2 split keeps letting updates skip validation and events by accident.

## References
- ADR-065 — Functional Inference Contract (`*InferenceResult` + `dataclasses.replace`)
- `docs/roadmap/functional-direction.md` — doctrine owner; "update intents" extension
- `docs/roadmap/done/update-intents.md` — phased migration
- `docs/patterns/three_tier_type_system.md` — Pydantic-edge / frozen-core boundary
- Reference implementation (after Phase 1): `core/models/task/task_update_intent.py`,
  `core/services/tasks/tasks_core_service.py`
