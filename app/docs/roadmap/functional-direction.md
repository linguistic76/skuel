# Functional Direction Roadmap

**Status:** Doctrine established (ADR-035 + ADR-065); **enforcement infrastructure complete (2026-05-31)** — mypy `arg-type` is the toolchain default on all first-party trees, the global disable deleted. Of the three targeted *extensions* below: **#2 (typed update intents, ADR-066) is ✅ done (2026-06-05)** — all six Activity Domains on frozen `*UpdateIntent` dataclasses, the shared CRUD base parameterized over the update type `U`, every `dict`/`*UpdatePayload` alternative deleted (PRs #228, #230–233, #236, #238); **#3 (the `Result[None] | None` collapse) is done (2026-05-31)**; #1 inference parity is 1/6 (Task only) and **blocked** on the 5 remaining domains growing an inference service. See the [implementation status snapshot](#implementation-status-snapshot-2026-05-31).
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
| Enforcement | ✅ mypy `arg-type` enforced on **all first-party trees** (`core/`, `services_bootstrap/`, `adapters/`, `ui/`) — global disable deleted 2026-05-31 | `pyproject.toml` (global default; `tests`/`scripts` scope-disabled) |

The direction is well-established. What follows is where it has *not* yet been extended.

## Implementation status snapshot (2026-05-31)

The question "is the functional direction implemented?" has two halves — the *enforcement layer* and the *extension items* — and they are at very different stages.

**Enforcement layer — ✅ COMPLETE.** The ~30-PR arg-type campaign (PRs #104–150) is finished. `core/` (sweep PRs F–L), `services_bootstrap/` (#121–129), `adapters/` (AD-1..AD-8, #131–145), and `ui/` (UI-1..UI-5, #146–150) were each driven to 0 honestly — zero unjustified suppressions — and the global `disable_error_code=["arg-type"]` was deleted in #150. The frozen-value / typed-payload / NewType-UID contracts on `core/` are now checked by the toolchain everywhere except `tests`/`scripts`. This is what the recent PRs delivered: the *mechanism* that keeps the direction true, not the remaining *extensions*.

**Extension items — two of three done.** Snapshot as of 2026-05-31 (item #2 below has since been completed — see its updated row):

| Extension | Target | Status (2026-05-31) | Evidence |
|-----------|--------|---------------------|----------|
| #1 Inference parity | `{Domain}InferenceResult` for all 6 Activity Domains | **PARTIAL — 1/6** | Only `TaskInferenceResult` exists (`core/models/task/task_inference_result.py`). Goals/Habits/Events/Choices/Principles have none. |
| #2 Typed update intents | `update_X(uid, intent: {Domain}UpdateIntent)` | **✅ DONE (2026-06-05)** | ADR-066 complete: all six Activity Domains expose `update_X(uid, intent: {Domain}UpdateIntent)`; the shared `CrudOperationsMixin[B, T, U]` is parameterized over the update type `U` (bound `SupportsToChanges`, default `RawChanges`); the six `*UpdatePayload` TypedDicts, the `_intent_from_mapping` funnels, and the facade `Mapping` overrides are deleted. PRs #228 (Tasks), #230 (Goals), #231 (Events), #232 (Choices), #233 (Principles), #236 (Habits), #238 (base parameterization + teardown). |
| #3 Collapse `Result[None] \| None` | hooks return `Result[None]` | **✅ DONE (2026-05-31)** | All 5 validation hooks (`_validate_create`, `_validate_update`, `_validate_content`, `_validate_prerequisites`, `_validate_required_user_uid`) now return `Result[None]`; success is `Result.ok(None)`. Call sites use `.is_error`, not truthiness. |

The enforcement layer being live is precisely what makes the remaining extensions *mechanical* when they land — a stray `dict` sneaking back into an `update_X` signature (#2) or a `TaskDTO` passed where a frozen `Task` is expected is now an arg-type error at the call site, not a silent regression.

**#3 note (closed wider than originally scoped):** the collapse covered *all five* `Result[None] | None` validation hooks, not just `_validate_create` / `_validate_update` — the two siblings (`_validate_prerequisites`, `_validate_required_user_uid`) carried the identical wart, so a partial collapse would have left it half-present. The correctness-critical part was the call-site rewrite from `if validation:` to `if validation.is_error:`: `Result` has no `__bool__`, so once success became the (truthy) `Result.ok(None)`, the old truthiness check would have treated every passing validation as a failure. mypy cannot catch that flip — it is guarded by `tests/unit/test_base_service.py::TestValidationHookContract`.

**#1 blockage (why it is deferred, not in progress):** the roadmap frames #1 as "add `{Domain}InferenceResult` to 5 domains," but those domains have *no inference service at all* — an `*InferenceResult` is the return type of a computation that does not exist. Per [`activity-domain-inference-migration.md`](activity-domain-inference-migration.md), the dataclasses arrive *when a domain grows an inference service*, which is paced by product demand. Even the named engine-generalization prerequisite (make `EntityInferenceService` `EntityType`-aware) is to be done "before the second domain migrates" — generalizing a one-implementation dispatch with no second caller now would be premature abstraction. #1 stays deferred until a domain actually needs inference.

**What makes the direction *mechanical* rather than doctrinal:** mypy's `arg-type` error code is the enforcement layer for the frozen-models / typed-payloads / typed-intents disciplines on `core/`. Without it, a `TaskDTO` passed where a frozen `Task` is expected, a raw `str` passed where a `UserUID` is expected, or a `dict[str, Any]` passed where a typed payload is expected all pass silently — the roadmap stays aspirational. With `arg-type` live on `core/`, those crossings become type errors at the call site, so the frozen-value contract is checked by the toolchain, not just reviewed by humans. It was re-enabled by a 12-PR sweep (`mypy --enable-error-code arg-type core`: 194 → 0; ~80% real signal). A follow-on campaign (PRs #121–128) then drove `services_bootstrap/` — the composition root, where service↔protocol conformance gaps aggregate — to 0 honestly and flipped enforcement on there too (2026-05-30). The `adapters/` sweep followed as micro-PRs AD-1..AD-8 (81 → 0; AD-9 finance was dissolved by the finance demolition, #144), and the `ui/` sweep as UI-1..UI-4 (76 → 0; the FastHTML/MonsterUI boundary, where the genuinely-irreducible Alpine colon/`@`/dot attribute splats carry a `# fasthtml dynamic-attr splat` ignore). With all four first-party trees at 0, the **global `disable_error_code` was deleted (2026-05-31)** — arg-type is now the toolchain default everywhere, with only `tests`/`scripts` scope-disabled (framework-mock noise, thousands of sites, never swept — the suppression audit reports the current count weekly). Throughout, the discipline was zero unjustified suppressions: a tree that needed `# type: ignore` to pass meant the wrong sequencing, not a reason to suppress. When item #2 below (typed update intents) lands, `arg-type` is what will keep a stray `dict` from sneaking back into an `update_X` signature.

## Where the direction wants to be extended

Three candidates, ordered by ratio of (clarity gained) to (work required). None of these is urgent; #1 is the only one with active roadmap commitment.

### 1. Inference parity across the 5 remaining Activity Domains (already in flight) — *1/6 done*

Goals, Habits, Events, Choices, Principles each gain a `{Domain}InferenceResult` mirroring `TaskInferenceResult`. Generalizing `EntityInferenceService` to be `EntityType`-aware is the single cross-cutting prerequisite (the engine was merged into the service; no separate `AdvancedInferenceEngine` class remains).

This is a direct, mechanical extension of ADR-065. The pattern is specified; the work is paced by when each domain grows an inference service.

**Already a separate roadmap doc:** [`activity-domain-inference-migration.md`](activity-domain-inference-migration.md). Listed here only so the broader functional direction picture is complete.

### 2. Typed update intents — replace `dict[str, Any]` update payloads with frozen `*UpdateIntent` dataclasses — *✅ done (2026-06-05)*

> **Owned and completed by [ADR-066 — Typed Update Intents](../decisions/ADR-066-typed-update-intents.md)**; the phased
> migration is recorded in [docs/roadmap/done/update-intents.md](done/update-intents.md). The text below is now a record of what shipped.

**Shipped shape:** every `*CoreService` exposes `update_X(uid: str, intent: {Domain}UpdateIntent) -> Result[X]`, where `{Domain}UpdateIntent` is a frozen dataclass with one `UNSET`-defaulted field per updatable column and a `to_changes()` that emits only the set fields. The shared `CrudOperationsMixin[B, T, U]` is parameterized over the update type `U` (bound `SupportsToChanges`, default `RawChanges`), so the base's `update` / `update_for_user` / `_validate_update` / `_post_update` are all typed on the intent and materialize the patch once at `backend.update(uid, updates.to_changes())`. The Pydantic `*UpdateRequest` models build the intent via `to_intent()`; the generic `CRUDRouteFactory` calls it for any `SupportsToIntent` schema.

**Why it was the natural extension of ADR-065:** same hazard ADR-065 named ("contract becomes implicit at the boundary"), applied to the write surface. Inference computed enrichment; updates accept user intent. Both are "compute structured changes, apply to a frozen value, return new value."

**What was removed (One Path Forward):** the six activity `*UpdatePayload` TypedDicts in `core/ports/query_types.py`, the per-domain `_intent_from_mapping` funnels, and the facade `Mapping`-typed `update` overrides — every alternative to the one typed path is deleted. The non-activity domains (curriculum Ku/Ps/Lp, finance, reports) keep their `*UpdatePayload` TypedDicts, flowing as `RawChanges` through the same base `U`.

**Per-domain deviations preserved:** Habits keeps `update_habit(uid, intent, *, force_archive)` (the transient `force_archive` directive can't ride the intent — it would persist as a junk column); Tasks/Events split edge-typed fields off the intent before the property write.

**Delivered in:** PRs #228 (Tasks reference), #230 (Goals), #231 (Events), #232 (Choices), #233 (Principles), #236 (Habits), #238 (base parameterization + teardown), and the Phase 7b docs/skills cleanup.

### 3. Collapse the `Result[None] | None` wart on validation hooks — *✅ done (2026-05-31)*

**Current shape:** `_validate_create / _validate_update` hooks return `Result[None] | None` (None = "no error"; `Result.fail(...)` = error).

**Functional shape:** `Result[None]` always — `Result.ok(None)` is already the canonical "no error" value. Two states for success is a wart.

**Cost:** ~6 hook implementations + their callers in `BaseService`. Trivial.

**Bundle, don't campaign.** Fold into any service touched for #2.

**✅ Done (2026-05-31).** Completed as a standalone change since #2 (its intended bundle partner) stayed deferred. Final surface was wider than the "~6" estimate: 5 hook types (the two named here + `_validate_content`, `_validate_prerequisites`, `_validate_required_user_uid`), their default stubs in `crud_operations_mixin` / `relationship_operations_mixin` / `conversion_helpers_mixin`, the `base_service_interface` protocol, 6 Activity-Domain `_validate_create` / `_validate_update` overrides, and the finance invoice override — plus the call-site truthiness→`.is_error` rewrites. See the [snapshot](#implementation-status-snapshot-2026-05-31) for the correctness rationale and the guarding test.

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
