# Functional Direction Roadmap

**Status:** Doctrine established (ADR-035 + ADR-065); targeted extensions identified, none in flight beyond the existing inference migration.
**Doctrine owners:** [ADR-035 — Tier Selection Guidelines](../decisions/ADR-035-tier-selection-guidelines.md) (frozen domain models), [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md) (typed return values, no input mutation).
**Pattern pointer:** [Three-Tier Type System § Intelligence is the Exception](../patterns/three_tier_type_system.md).

## Purpose

Name the architectural direction SKUEL has been moving toward, catalog where it already lives, and point at the next concrete extensions — without inviting speculative work. This is a bias-setting doc, not a campaign plan.

## What "functional" means here

In SKUEL specifically, functional means:

- **Frozen, value-typed inputs and outputs.** `@dataclass(frozen=True)` at the core; immutable by construction.
- **Functions do not mutate their arguments.** Compute, return; the caller applies.
- **Operations return new values.** Application uses `dataclasses.replace()` or comparable; the input is left untouched.
- **Errors are values.** `Result[T]`, not raised exceptions, for anything inside `core/`.

Bias: **frozen at the core, functional at the boundary, mutable only at the persistence translation step.** The translation step (DTOs ↔ Neo4j properties) is explicitly carved out per ADR-035; everything above it is functional.

## Where the direction already lives

| Surface | Functional? | Reference |
|---------|-------------|-----------|
| 25 domain models | ✅ All `@dataclass(frozen=True)` | ADR-035 |
| Error handling | ✅ `Result[T]` throughout `core/` | `/docs/patterns/ERROR_HANDLING.md` |
| Events | ✅ Frozen records on the event bus | `/core/events/` |
| Inference (Tasks) | ✅ `TaskInferenceResult` + `dataclasses.replace` | ADR-065 |
| Pydantic request models | ✅ Value-typed post-validation | ADR-035 Tier 1 |
| DTOs (CRUD translation) | ❌ Mutable by design — named exception | ADR-035 Tier 2 |
| Neo4j session/tx | ❌ Mutable by necessity — below the boundary | ADR-044 |
| Enforcement | ✅ mypy `arg-type` on `core/` (2026-05-29) + `services_bootstrap/` (2026-05-30) | `pyproject.toml` § per-module overrides |

The direction is well-established. What follows is where it has *not* yet been extended.

**What makes the direction *mechanical* rather than doctrinal:** mypy's `arg-type` error code is the enforcement layer for the frozen-models / typed-payloads / typed-intents disciplines on `core/`. Without it, a `TaskDTO` passed where a frozen `Task` is expected, a raw `str` passed where a `UserUID` is expected, or a `dict[str, Any]` passed where a typed payload is expected all pass silently — the roadmap stays aspirational. With `arg-type` live on `core/`, those crossings become type errors at the call site, so the frozen-value contract is checked by the toolchain, not just reviewed by humans. It was re-enabled by a 12-PR sweep (`mypy --enable-error-code arg-type core`: 194 → 0; ~80% real signal) and is enforced via a per-module override. A follow-on campaign (PRs #121–128) then drove `services_bootstrap/` — the composition root, where service↔protocol conformance gaps aggregate — to 0 honestly and flipped enforcement on there too (2026-05-30). It stays globally disabled for the not-yet-enforced `adapters`/`ui`/`tests`/`scripts` trees. The `adapters/` sweep is in progress (micro-PRs AD-1..AD-8, `arg-type` count 81 → 5 as of 2026-05-30; the per-module enforcement flip lands once the count reaches 0); `ui`/`tests`/`scripts` remain a future sweep. When item #2 below (typed update intents) lands, `arg-type` is what will keep a stray `dict` from sneaking back into an `update_X` signature.

## Where the direction wants to be extended

Three candidates, ordered by ratio of (clarity gained) to (work required). None of these is urgent; #1 is the only one with active roadmap commitment.

### 1. Inference parity across the 5 remaining Activity Domains (already in flight)

Goals, Habits, Events, Choices, Principles each gain a `{Domain}InferenceResult` mirroring `TaskInferenceResult`. Engine generalization (`AdvancedInferenceEngine`, `EntityInferenceService`) is the single cross-cutting prerequisite.

This is a direct, mechanical extension of ADR-065. The pattern is specified; the work is paced by when each domain grows an inference service.

**Already a separate roadmap doc:** [`activity-domain-inference-migration.md`](activity-domain-inference-migration.md). Listed here only so the broader functional direction picture is complete.

### 2. Typed update intents — replace `dict[str, Any]` update payloads with frozen `*UpdateIntent` dataclasses

**Current shape:** every `*CoreService` exposes `update_X(uid: str, updates: dict[str, Any]) -> Result[X]`. The `dict[str, Any]` is the same opaque "any field, any value" contract that ADR-065 closed for inference — implicit at the boundary, drift-prone over time.

**Functional shape:** `update_X(uid: str, intent: TaskUpdateIntent) -> Result[Task]` where `TaskUpdateIntent` is a frozen dataclass of `field: T | None` (only specified fields apply). The Pydantic `*UpdateRequest` models already exist and become the natural source — convert at the route boundary.

**Why this is the natural next extension:** same hazard ADR-065 named ("contract becomes implicit at the boundary"), applied to a different surface. Inference computed enrichment; updates accept user intent. Both are "compute structured changes, apply to a frozen value, return new value."

**Adjacent gesture already in the codebase:** `core/ports/query_types.py::TaskUpdatePayload` is a `TypedDict` for the update shape — a half-step toward typing the dict. The full functional shape promotes it from `TypedDict` to frozen dataclass with `dataclasses.replace`-style application.

**Why this is NOT urgent:** the `dict` shape works correctly today; the hazard is implicit-contract drift, not runtime bugs. Worth doing opportunistically when a service is touched anyway; not worth a dedicated campaign.

**Touches:** `update_X` signatures across all 6 Activity Domains + inbound route handlers that construct the dict today. Estimate: 1 PR per domain (6 total), or a single bundled PR if engine-style generalization fits.

### 3. Collapse the `Result[None] | None` wart on validation hooks

**Current shape:** `_validate_create / _validate_update` hooks return `Result[None] | None` (None = "no error"; `Result.fail(...)` = error).

**Functional shape:** `Result[None]` always — `Result.ok(None)` is already the canonical "no error" value. Two states for success is a wart.

**Cost:** ~6 hook implementations + their callers in `BaseService`. Trivial.

**Bundle, don't campaign.** Fold into any service touched for #2.

## What is explicitly NOT in scope

Naming these so the doc does not become a magnet for speculative work:

- **DTOs stay mutable.** ADR-035's three-tier structure stands. PR #102 (2026-05-29) reverted the speculative two-tier write spike that hid inside ADR-065's PR; the question is closed pending a new ADR with concrete motivation, which has not been established.
- **Neo4j adapter session/tx state stays mutable.** Below the hexagonal boundary (ADR-044), outside `core/`'s concern.
- **In-memory caches stay mutable.** Controlled mutation is the entire point of caching.
- **Pydantic request models are functional enough.** They are value-typed after validation; no further refactor needed.
- **Domain helper methods stay where they are.** `task.is_overdue()`, `task.urgency_score()`, etc. are already pure functions on frozen values.

## Contributor heuristic

When writing new service-layer code, default to:

1. **Frozen inputs.** Accept `Task`, not `TaskDTO`, when possible. The DTO is the persistence translation layer, not the working contract.
2. **Frozen outputs.** Return `Task`, `Result[Task]`, or a typed `*Result` dataclass. Never return a mutable dict for the caller to interpret.
3. **Returned errors.** `Result[T]` always within `core/`; `raise` only at adapter or boundary code.
4. **No input mutation.** Compute, return; let the caller apply via `dataclasses.replace`.

If you find yourself reaching for a `dict[str, Any]` parameter on a service method or an `obj.field = x` assignment inside one, that is the friction point this direction names. Flag it as TODO even if you don't fix it in the same PR.

## References

- [ADR-035 — Tier Selection Guidelines](../decisions/ADR-035-tier-selection-guidelines.md) — frozen domain models, three-tier structure, the always-two-tier alternative explicitly rejected for complex domains.
- [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md) — the doctrine extension this roadmap generalizes; closes ADR-035's "intelligence services would operate on mutable DTOs (risky)" risk flag.
- [Three-Tier Type System § Intelligence is the Exception](../patterns/three_tier_type_system.md) — pattern-level statement of the DTO carve-out.
- [Activity Domain Inference Migration](activity-domain-inference-migration.md) — the in-flight per-domain work item #1.
- [Error Handling — `Result[T]`](../patterns/ERROR_HANDLING.md) — error-as-value doctrine.
