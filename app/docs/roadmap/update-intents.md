---
title: "Roadmap: Typed Update Intents migration"
updated: 2026-06-04
status: not-started
category: roadmap
tags: [roadmap, activity-domains, typing, immutability, one-path-forward]
---

# Roadmap: Typed Update Intents migration

**Status:** Phase 1 (Tasks reference) complete — 2026-06-04. Phases 2–7 pending.
**Pattern owner:** [ADR-066 — Typed Update Intents](../decisions/ADR-066-typed-update-intents.md)
**Doctrine:** [functional-direction.md](functional-direction.md), [three_tier_type_system.md](../patterns/three_tier_type_system.md)

## Context

ADR-066 replaces the unsound, decorative `*UpdatePayload` TypedDicts with frozen `*UpdateIntent`
dataclasses and collapses the four-way write boundary into **one canonical update path** (service
contract, validated + event-firing) plus an explicit, documented raw-write bypass. This roadmap
propagates the pattern Tasks-first across all six Activity Domains and then deletes every alternative
from code, docs, and skills (One Path Forward).

A bridging change has already landed: the service `update` / `update_for_user` contract takes
`Mapping[str, Any]` (a TypedDict is assignable to it; a `dict` was not). That widening is the *bridge*
each domain removes when it adopts its intent — it lets the migration proceed one domain at a time
with a green tree throughout.

## The canonical update path (the rule every phase enforces)

- **Service contract** (`self.update` / `self.core.update` / `super().update` / `update_<x>` facades)
  consumes the domain `*UpdateIntent`, runs `_validate_update` + `_post_update` (events), and
  materializes `intent.to_changes()` → `dict` once at the `backend.update` seam. **Only** path for
  partial / user-facing updates.
- **`backend.update(dict)` directly** is allowed **only** for full-DTO persistence (`dto.to_dict()`)
  and system/timestamp bumps, each marked `# raw-write: <why>`. Any partial field update going
  straight to the backend is a defect to migrate.

## Status table (the cross-context source of truth — tick on each PR)

| Domain | `*UpdateIntent` | `*UpdateRequest.to_intent()` | Service contract on intent | #2 backend-direct partials resolved | `*UpdatePayload` deleted |
|--------|:---:|:---:|:---:|:---:|:---:|
| Tasks (reference) | ☑ | ☑ | ☑ | ☑ | ☐ (Phase 7) |
| Goals | ☐ | ☐ | ☐ | ☐ | ☐ (Phase 7) |
| Habits | ☐ | ☐ | ☐ | ☐ | ☐ (Phase 7) |
| Events | ☐ | ☐ | ☐ | ☐ | ☐ (Phase 7) |
| Choices | ☐ | ☐ | ☐ | ☐ | ☐ (Phase 7) |
| Principles | ☐ | ☐ | ☐ | ☐ | ☐ (Phase 7) |

Shared `UNSET` sentinel: ☑ (Phase 1, `core/models/sentinels.py`) · Docs/skills One-Path cleanup: ☐ (Phase 7)

> **Sequencing decision (2026-06-04): funnel now, parameterize the base at Phase 7.**
> The "service contract on intent" column is satisfied per-domain by typing the
> domain method (`update_<domain>`) on the intent and **funnelling** the inherited
> generic `update` / `update_for_user` (still `Mapping`, called by the shared
> `CRUDRouteFactory` + `calendar_service`) through it via a small, greppable
> `_intent_from_mapping` bridge. The shared `CrudOperationsMixin` / `CrudOperations`
> protocol — including `_validate_update` / `_post_update` — stays `Mapping`-typed
> until **Phase 7**, when, with all six domains on intents, it is parameterized over
> `U: SupportsToChanges` (PEP 695 *bound*, no default — valid on Python 3.12) and the
> generic methods + bridges collapse to a direct intent parameter. This is the ADR-066
> destination ("the service contract `update` / `update_for_user` accepts the domain
> `*UpdateIntent`"); the funnel is the 3.12-clean, low-blast-radius path to it.

## The pattern per domain (what each phase does)

1. **Define** `*UpdateIntent` (`core/models/<domain>/<domain>_update_intent.py`): frozen dataclass,
   one field per updatable column, `UNSET`-defaulted, with `to_changes()`. Re-export from the domain
   `__init__.py`.
2. **Add** `*UpdateRequest.to_intent()` (`core/models/<domain>/<domain>_request.py`): build the intent
   from `model_fields_set` so only explicitly-set fields are non-`UNSET`.
3. **Migrate the service contract**: change `update` / `update_for_user` / `update_<x>` parameter from
   `Mapping[str, Any]` (bridge) to the domain `*UpdateIntent`; materialize `intent.to_changes()` at the
   single `backend.update` call. Update `_validate_update` / `_post_update` to read the intent (or its
   `to_changes()` dict). Service-authored transitions construct the intent directly
   (`GoalUpdateIntent(status=EntityStatus.ACTIVE.value)`), not a dict.
4. **Migrate callers**: route handlers and facades pass `request.to_intent()` instead of a
   `model_dump()` dict.
5. **Resolve #2 stragglers**: every `self.backend.update({...})` partial in this domain either routes
   through the service contract (gaining validation + events) or, if the bypass is intentional, is
   converted to a plain `dict` literal and annotated `# raw-write:`.
6. **Verify** (below) and tick the table row.

## Phases (each = one context / one PR)

- **Phase 1 — Foundation + Tasks reference. ✅ DONE (2026-06-04).** Added
  `core/models/sentinels.py` (`UNSET` / `Unset`, PEP 661 single-member enum — narrowable, unlike the
  pre-existing `_UNSET = object()` in `core/services/exercises/`). Implemented the full pattern for
  Tasks: `TaskUpdateIntent` (`core/models/task/task_update_intent.py`, includes the two edge-typed
  fields the facade splits off), `TaskUpdateRequest.to_intent()` (from `model_fields_set`, enums lowered
  to `.value`), `update_task` (core + facade) typed on the intent with `to_changes()` materialized at
  the single `backend.update` seam. The inherited generic `update` / `update_for_user` keep their
  `Mapping` signature (shared `CRUDRouteFactory` + `calendar_service`) and **funnel** through
  `update_task` via `_intent_from_mapping` (one runtime path; generic JSON property updates now also
  fire `TaskUpdated`). #2 stragglers: the three `tasks_progress_service` partial writes route through
  `self.update`; `complete_tasks_bulk` stays a plain `dict` literal annotated `# raw-write:`.
  **Deliberately deferred to Phase 7** (LSP/3.12-bound to the un-parameterized base): typing
  `_validate_update` / `_post_update` on the intent. Verified live: `tests/integration/
  test_task_update_intent_pipeline.py` (partial-no-clobber, `TaskUpdated` fires, status transition,
  `to_intent()` semantics).
- **Phases 2–6 — Goals, Habits, Events, Choices, Principles** (independent; any order, parallel contexts
  fine). Each reads ADR-066 + this roadmap + the Tasks reference commit and replicates steps 1–6.
  Watch the activity mixins typed `core: Any` (e.g. `events/_orchestration_mixin.py`,
  `habits/_completion_mixin.py`) — passing an intent through an `Any` attribute is unchecked; tighten
  the attribute type to the core service (or its protocol) so the intent is actually verified.
- **Phase 7 — Teardown + One-Path cleanup + base parameterization.**
  - **Parameterize the base over the update type (the ADR-066 destination).** With all six domains on
    intents, add `U: SupportsToChanges` (a `to_changes() -> dict[str, Any]` protocol) as a third type
    param to `CrudOperationsMixin` / `BaseService` / `CrudOperations` — a PEP 695 *bound* (no default),
    valid on Python 3.12. `update` / `update_for_user` / `_validate_update` / `_post_update` then read
    the intent directly; materialization is uniform `updates.to_changes()` (no `isinstance`). Each
    domain declares its intent (`BaseService[TasksOperations, Task, TaskUpdateIntent]`), the generic
    `CRUDRouteFactory` builds the intent via `UpdateRequestBase.to_intent()`, and the per-domain
    `_intent_from_mapping` funnel bridges are deleted.
  - Delete all `*UpdatePayload` from `core/ports/query_types.py` (and `__init__` re-exports) and the
    advertising docstring in `core/services/mixins/crud_operations_mixin.py`. Remove the now-dead
    `Mapping[str, Any]` bridge signatures where every caller passes an intent.
  - **Docs** (rewrite to the intent pattern, delete TypedDict references):
    `docs/patterns/three_tier_type_system.md` (§ TypedDicts, lines ~622–719),
    `docs/patterns/query_architecture.md` (§ TypedDicts, lines ~508–559),
    `docs/guides/BASESERVICE_QUICK_START.md` (Update-an-entity example),
    `docs/patterns/ROUTE_FACTORIES.md` (`update_schema`),
    `docs/patterns/entity_timestamp_mixin.md`, `docs/patterns/DOMAIN_SPECIFIC_HOOKS.md`,
    `docs/tutorials/DATA_FLOW_WALKTHROUGH.md`, `docs/patterns/AUTH_PATTERNS.md`,
    `docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md`, `docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md`.
  - **Skills** (make the intended way the only documented way):
    `.claude/skills/activity-domains/SKILL.md` (+ `COMMON_PATTERNS.md`) — add the canonical
    "How to update an entity" section,
    `.claude/skills/python/SKILL.md` + `python/type-hints-reference.md` (drop `TaskUpdatePayload`),
    `.claude/skills/pydantic/SKILL.md` + `pydantic/request-response-reference.md` (show `.to_intent()`),
    `.claude/skills/neo4j-cypher-patterns/PATTERNS.md`, `.claude/skills/domain-route-config/SKILL.md`.
  - **Indexes:** `docs/INDEX.md`, `docs/CROSS_REFERENCE_INDEX.md`, and flip
    `docs/roadmap/functional-direction.md` extension #2 to ✅ with PR references.
  - **Optional guard (One Path Forward):** a *trivially sound, AST-structural* lint check that fails on
    any re-introduced `*UpdatePayload` import/name. Do **not** attempt flow-analysis to detect "#2
    partial backend calls" — that needs control-flow domination and is unsound (see
    `feedback_lint_rules_refuse_flow_analysis`). The `# raw-write:` convention + review is the guard
    for #2.

## Verification (per phase)

- `./dev quality` → MyPy **0 errors**. MyPy is the migration teacher: widening/narrowing a service
  `update` parameter surfaces every override (`_validate_update`/`_post_update`) and protocol mirror
  that must move together (`core/ports/base_service_interface.py`, the 6 `*_core_service.py`).
- `uv run pytest` for the domain's service tests + status-transition / edge-sync tests.
- Confirm `_post_update` events still fire on the intent path for status transitions — verify against
  local Docker Neo4j or the `neo4j-cypher` MCP (CI runs no pytest).
- Codex clean. Tick the table row so the next context starts from accurate state.

## Out of scope

- **Curriculum (PS/LP) and Finance** `update_*` methods — not Activity Domains; keep `dict[str, Any]`
  unless a later roadmap pulls them in.
- **Full-DTO writes (#3)** — `dto.to_dict()` → `backend.update` is entity *replace*, not a partial
  patch; `*UpdateIntent` does not model it. Leave as raw writes (annotated).
- **The `core: Any` mixin typing** beyond tightening it enough to type-check the intent — a full
  Protocol-ization of the activity mixins is its own change.

## References
- [ADR-066 — Typed Update Intents](../decisions/ADR-066-typed-update-intents.md) (pattern owner)
- [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md)
- [functional-direction.md](functional-direction.md) — doctrine + extension tracker
- [activity-domain-inference-migration.md](activity-domain-inference-migration.md) — sibling Tasks-first
  propagation roadmap (same structure)
- Reference implementation (after Phase 1): `core/models/task/task_update_intent.py`,
  `core/services/tasks/tasks_core_service.py`, `core/models/task/task_request.py::TaskUpdateRequest.to_intent`
