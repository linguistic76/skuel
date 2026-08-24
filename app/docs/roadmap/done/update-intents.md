---
title: "Roadmap: Typed Update Intents migration"
updated: 2026-06-05
status: complete
category: roadmap
tags: [roadmap, activity-domains, typing, immutability, one-path-forward]
---

# Roadmap: Typed Update Intents migration

**Status:** ✅ **COMPLETE — 2026-06-05.** All phases shipped: Phases 1–6 (the six Activity
Domains on frozen `*UpdateIntent`), Phase 7a (base parameterized over the update type `U` —
`SupportsToChanges`, default `RawChanges`; the six `_intent_from_mapping` funnels, facade
`Mapping` overrides, and six activity `*UpdatePayload` TypedDicts deleted), and Phase 7b
(docs/skills One-Path cleanup — every doc/skill now describes the single typed-intent path).
ADR-066 is fully implemented.
**Pattern owner:** [ADR-066 — Typed Update Intents](../../decisions/ADR-066-typed-update-intents.md)
**Doctrine:** [functional-direction.md](../functional-direction.md), [three_tier_type_system.md](../../patterns/three_tier_type_system.md)

> ⚠ **The write SEAM moved after this arc closed; the intent contract did not.**
> [ADR-087](../../decisions/ADR-087-status-guarded-conditional-writes.md) (2026-08-24) routes
> every Activity update chokepoint through `backend.update_with_status_guard` instead of
> `super().update` / `backend.update`, so the per-phase notes below describing which domains
> "keep `super().update()`" are a record of what June 2026 landed, not of today's shape. What
> is unchanged: the intent is still the contract, `to_changes()` is still materialized exactly
> once, and the domain rules still run — but `_validate_update` is now called explicitly by
> each chokepoint, because leaving `CrudOperationsMixin.update` took the hook off the path.
> (Each call is gated on what that domain's rules actually read: unconditional for Events and
> Choices, on the date fields for Goals, whose one rule is a no-op without them.)

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
| Tasks (reference) | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |
| Goals | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |
| Habits | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |
| Events | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |
| Choices | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |
| Principles | ☑ | ☑ | ☑ | ☑ | ☑ (Phase 7a) |

Shared `UNSET` sentinel: ☑ (Phase 1, `core/models/sentinels.py`) · Base parameterized over `U`: ☑ (Phase 7a) · Docs/skills One-Path cleanup: ☑ (Phase 7b)

> **Sequencing decision (2026-06-04): funnel now, parameterize the base at Phase 7.**
> The "service contract on intent" column is satisfied per-domain by typing the
> domain method (`update_<domain>`) on the intent and **funnelling** the inherited
> generic `update` / `update_for_user` (still `Mapping`, called by the shared
> `CRUDRouteFactory` + `calendar_service`) through it via a small, greppable
> `_intent_from_mapping` bridge. The shared `CrudOperationsMixin` / `CrudOperations`
> protocol — including `_validate_update` / `_post_update` — stays `Mapping`-typed
> until **Phase 7**, when, with all six domains on intents, it is parameterized over a third
> type param `U: SupportsToChanges` and the generic methods + bridges collapse to a direct
> intent parameter. This is the ADR-066 destination ("the service contract `update` /
> `update_for_user` accepts the domain `*UpdateIntent`"); the funnel is the low-blast-radius
> path to it.
>
> **Correction (2026-06-05, traced for Phase 7):** the original note said "PEP 695 *bound*,
> no default — valid on Python 3.12." That assumed only the six activity domains touch the
> base. They don't: `BaseService` / `CrudOperationsMixin` is the **universal** base — ~59
> `BaseService[Op, T]` instantiations, ~53 of them non-activity (Ku/Ps/Lp/UserEntry/forms/
> templates/…) with **no** intent. A no-default `U` would force all 59 to declare one. So
> `U` needs a **PEP 696 type-param *default*** (available now — the repo is on **Python
> 3.14**, ADR-067) so only the six activity domains override `U` and the rest are untouched.
> The default must itself satisfy `SupportsToChanges` (a plain `Mapping` does **not** — has no
> `to_changes()`); resolve in Phase 7 (likely a tiny `RawChanges` wrapper as the default, or a
> looser bound).

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
- **Phase 2 — Goals. ✅ DONE (2026-06-04).** Shape B (core overrode the generic `update(Mapping)` with
  event logic). `GoalUpdateIntent` (node-property fields only — the three cross-domain edge UIDs on
  `GoalUpdateRequest` are graph edges, synced on the create-with-context path, so `to_intent()` does not
  carry them), `GoalUpdateRequest.to_intent()`, and `GoalsCoreService.update_goal(intent)` typed on the
  intent. Unlike Tasks (whose `update_task` always wrote `backend.update` directly), `update_goal` keeps
  the `super().update` call so `_validate_update` (achieved-goal immutability, target>start) still runs.
  Added a `GoalUpdated` event (mirroring `TaskUpdated`) — wired to context invalidation — so plain
  property edits now invalidate caches; `GoalAchieved` still fires on the COMPLETED transition. The dead
  `"progress"`-keyed `GoalProgressUpdated` branch (Goal has no `progress` column — only
  `progress_percentage`) was removed; progress events stay owned by `GoalsProgressService`. The single
  `_intent_from_mapping` funnel lives on the core (in-service status methods + the facade-routed CRUD
  route both flow through it); facade `update` / `update_for_user` / `update_goal` route through it. #2
  stragglers: the two `goals_progress_service` partial writes stay `# raw-write:` (they publish their own
  provenance-bearing `GoalProgressUpdated`). Verified live:
  `tests/integration/test_goal_update_intent_pipeline.py`.
- **Phase 3 — Events. ✅ DONE (2026-06-04).** Shape B (core overrode the generic `update(Mapping)`)
  AND edge-splitting (like Tasks). `EventUpdateIntent` carries node-property columns + the two
  cross-domain edge UIDs (`milestone_celebration_for_goal` → `CELEBRATES_GOAL`, `reinforces_habit_uid`
  → `REINFORCES_HABIT`); `EventsService.update_event(intent)` splits the edges off (resetting them to
  `UNSET` on the property sub-intent), writes node props via `EventsCoreService.update_event(intent)`
  (keeps `super().update()` → `_validate_update`: past-event immutability, duration 5–720), and replaces
  the edges via the existing `_replace_edge`. No new event — Events already had `CalendarEventUpdated`
  wired to context invalidation (fires on plain edits; `CalendarEventCompleted` on COMPLETED,
  `CalendarEventRescheduled` on `event_date` change). `to_intent()` drops `practices_knowledge_uids` /
  `executes_tasks` (neither columns nor handled edges — honest junk-write fix; the create path drops
  them too); the dead `quality_score` read in the old override is replaced by an honest `None` (quality
  flows through progress/habit services). `_intent_from_mapping` funnel lives on BOTH core (in-service
  status methods) and facade (CRUD route + `calendar_service`). The mixin `core: Any` attributes
  (`events/_orchestration_mixin.py`, `events/_scheduling_mixin.py`) were tightened to `EventsCoreService`.
  #2 stragglers: `events_progress_service` (complete-with-cascade) + `events_habit_integration_service`
  (complete-with-quality, miss-habit) stay `# raw-write:` (each publishes its own provenance-bearing
  CalendarEvent*). Verified live: `tests/integration/test_event_update_intent_pipeline.py`.
- **Phase 4 — Choices. ✅ DONE (2026-06-04).** Shape A in structure (a separately-named
  `update_choice` that wrote `backend.update` directly, no generic `update(Mapping)` override) but —
  unlike Tasks — with a **live `_validate_update`** (decision immutability for DECIDED/EVALUATED
  choices, option-count floor). Pre-change, exactly one caller reached it: `choices_api` calls
  `choices_service.core.update(...)`, drilling into the core so `self._validate_update` resolves to the
  real implementation. (The pre-change UI-edit and generic-CRUD-factory paths went through the facade's
  inherited *no-op* `_validate_update` — identical to Tasks, whose same-named `TasksCoreService.
  _validate_update` was, at the time, dead: every live caller hit the facade no-op or `update_task`'s
  direct backend write. *(Wired 2026-08-23 — `update_task` now calls it explicitly, and its
  terminal-state rule was deleted rather than wired; see the cascade-idempotency arc.)*) Routing the
  facade's `update` / `update_for_user` through the core funnel now means
  **all three paths validate** — a behavior gain, not just preservation.
  `ChoiceUpdateIntent` (node-property columns only; `ChoiceUpdateRequest` carries no
  edge fields, so nothing to drop — the create-only `informed_by_knowledge_uids` edge lives on
  `ChoiceCreateRequest`), `ChoiceUpdateRequest.to_intent()` (generic `when_set[T]`, enums lowered),
  and `ChoicesCoreService.update_choice(intent)` typed on the intent. **Like Goals (not Tasks),
  `update_choice` now keeps `super().update()`** so `_validate_update` runs on every property
  update — this *adds* validation to the UI edit path (previously backend-direct, unvalidated), the
  intended One-Path convergence. **Reused the existing `ChoiceUpdated`** event (already wired to
  context invalidation; `updated_fields: dict`) — no new event. The status route (`core.update`,
  `{"status": ...}`) now fires `ChoiceUpdated` too (previously the base no-op `_post_update` fired
  nothing). One `_intent_from_mapping` funnel on the core; facade `update` / `update_for_user` /
  `update_choice` route through it; the UI edit route passes `to_intent()` (dropped the ad-hoc "drop
  None"). #2/#3 stragglers annotated `# raw-write:`: `make_decision` (partial, fires its own
  `ChoiceMade`) + `evaluate_choice_outcome` / `add_option` / `update_option` / `remove_option`
  (full-DTO `dto.to_dict()` replaces, each with option/outcome provenance). The backend-level
  `ChoicesOperations.update_choice` protocol method (`Result[bool]`) is vestigial/uncalled — left for
  Phase 7. The choices facade mixins' `core: Any` were left untouched (the intent flows only through
  the facade's own methods, where `core: ChoicesCoreService` is concretely typed). Verified live:
  `tests/integration/test_choice_update_intent_pipeline.py`.
- **Phase 5 — Principles. ✅ DONE (2026-06-04).** Shape A in structure (a separately-named
  `update_principle` that wrote `backend.update` directly, no generic `update(Mapping)` override) and —
  **unlike Choices, like Tasks** — `update_principle` stays **backend-direct** (no `super().update()`).
  Principles' `_validate_update` *is* reachable (via `principles_api` → `core.update({"status": ...})`)
  but **stale/broken**: Rule 1 keys on `label` (not a column — field is `title`); Rule 3's `strength_order`
  compares UPPERCASE keys against the lowercase enum `.value`, so both sides default to `3` and it never
  fires; Rule 4 demands a `modification_reason` field that exists **nowhere** (unsatisfiable). The only
  live caller sends `{"status": ...}`, which triggers no rule. Routing through `super().update()` would
  *activate* the unsatisfiable Rule 4 and **block CORE/STRONG description edits** — a regression. Since
  reforming `_validate_update` onto the intent is **Phase-7** work, the hook is left untouched and
  documented; backend-direct preserves exact behavior (the "stated-fact-contradicts-code" exception to
  "keep `super().update()` when live"). Landed: `PrincipleUpdateIntent` (node columns only + `status` for
  the funnel/status route), `PrincipleUpdateRequest.to_intent()` (generic `when_set[T]`, enums lowered),
  `PrinciplesCoreService.update_principle(intent)` (backend-direct; `updated_fields` snapshotted BEFORE
  `backend.update` since the backend stamps `updated_at` in place), `_intent_from_mapping` funnel on the
  core, facade `update`/`update_for_user`/`update_principle` route through it. **Reused the existing
  `PrincipleUpdated`** event (+ `PrincipleStrengthChanged` on strength change) — no new event. `to_intent()`
  **drops two non-column request fields** (honest junk-write fix, locked by a test): `why_important` (folded
  into `description` via `merge_why_important` — `principles_ui` re-folds it into the intent's `description`
  using the existing principle as the base) and `decision_criteria` (absent from `Principle`/`PrincipleDTO`).
  **Superseded for `why_important` (2026-08):** it became a real `Principle` column, both splice helpers were
  deleted, and the intent now carries it like any other node property — only `decision_criteria` is still
  dropped. The rest of this entry stands as written.
  #3 stragglers annotated `# raw-write:`: the three full-DTO `dto.to_dict()` replaces in
  `_embodiment_mixin` (expression append) + `_alignment_intelligence_mixin` / `principles_alignment_service`
  (alignment-history append). The backend-level `PrinciplesOperations.update_principle` protocol method
  (`Result[bool]`) is vestigial/uncalled — left for Phase 7. The Principles facade mixins' `core: Any` were
  left untouched (the intent flows only through the facade's own concretely-typed `core` methods). Verified
  live: `tests/integration/test_principle_update_intent_pipeline.py` (6 cases).
- **Phase 6 — Habits. ✅ DONE (2026-06-05).** Last Activity Domain. Shape B in structure (core overrode
  the generic `update(Mapping)`) but — **unlike Goals/Choices, like Tasks/Principles** — `update_habit`
  does **not** route through `super().update()`. Habits' `_validate_update` IS live and real (streak
  preservation on archive; DAILY-frequency consistency) but reads a transient `force_archive` directive
  that bypasses the streak rule. The shared base passes the *same* mapping to `_validate_update` AND
  `backend.update` (`SET n += $updates`, no key filtering), so carrying `force_archive` through
  `super().update()` would persist it as a junk node column. So `update_habit` validates **explicitly**
  (force flag visible to validation only) then writes the clean patch backend-direct — validation still
  runs on every path (all callers funnel through `update_habit`), force_archive works without leaking a
  column. (Trace-and-deviate from the "keep super().update() when live" rule, mirroring Principles'
  documented case — the stated-fact-vs-code exception.) **Also fixed a latent bug while here:** the
  `force_archive` bypass its own error message advertises was **dead code** — Rule 1 returned `Result.fail`
  *before* the trailing `if updates.get("force_archive")` check could ever run. Gated Rule 1 on
  `not updates.get("force_archive")` and deleted the unreachable trailing block; Rule 2 (data-integrity,
  DAILY target ≤ 7) stays non-bypassable. Landed: `HabitUpdateIntent` (15 request-settable columns +
  `reminder_time`/`reminder_days`/`reminder_enabled` so the `set/delete_habit_reminder` funnel carries
  real columns), `HabitUpdateRequest.to_intent()` (generic `when_set[T]`, 6 enums lowered, **drops the
  four edge UIDs** `linked_knowledge_uids`/`linked_goal_uids`/`linked_principle_uids`/
  `prerequisite_habit_uids` — graph edges, not columns, locked by a test), `HabitsCoreService.update_habit(intent, *, force_archive)`
  + `_intent_from_mapping` funnel on the core (extracts `force_archive` from the Mapping; also naturally
  drops the legacy junk writes `notes`/`paused_until` — non-columns nothing reads). **Added a new
  `HabitUpdated` event** (Habits had none — the core docstring even said "Habit updates don't have
  specific events"; mirrors `GoalUpdated`) wired to context invalidation in `services_bootstrap/_event_wiring.py`,
  so plain property edits now invalidate caches. Facade `update_habit`/`update`/`update_for_user` route
  through the funnel; the UI edit route passes `to_intent()` (dropped the ad-hoc "drop None").
  #2 stragglers annotated `# raw-write:`: `habits_progress_service` (streak/stat propagation, converted
  `HabitUpdatePayload` → plain `dict`) + the two `habits_completion_service` streak-stat writes — each owns
  its provenance-bearing HabitCompleted/HabitStreakBroken/HabitStreakMilestone. The Habits facade mixins'
  `core: Any` were left untouched (the intent flows only through the facade's own concretely-typed `core`;
  `_completion_mixin` still passes a `Mapping` through `core.update`, not an intent). Verified live:
  `tests/integration/test_habit_update_intent_pipeline.py` (7 cases).
  **Caller-convergence (step 4) — COMPLETE for all six domains:** `habits_api.py:32` converged from
  `service.core.update(uid, {"status": ...})` to `habits_service.update_habit(uid, HabitUpdateIntent(status=new_status))`.
  **End-state invariant achieved: no activity `*_api.py` calls `.core.update(dict)`** — Tasks/Events/Choices/Principles/Habits
  use the typed-intent status route and Goals uses `set_status`.
- **Phase 7 — Teardown + One-Path cleanup + base parameterization.** Split into two PRs.
  The edge-clear UX gap (Tasks/Events
  picker `""`→None) is **out of Phase 7** — a deferred UX bug, not One-Path teardown; track separately
  (now tracked live in `../deferred-work.md` § Tasks/Events Edge-Clear on Edit).

  **Phase 7a — base parameterization (atomic code, one PR). ✅ DONE (2026-06-05).** *Forced-atomic*:
  parameterizing the base over the update type mechanically forced the funnel/factory/hook changes
  together — once `update` takes `U`, the facade `update(uid, Mapping)` funnel overrides became
  **incompatible overrides** (the intent dataclass is not a `Mapping`) → red MyPy. Landed in one change:
  - Added `SupportsToChanges` (`to_changes() -> dict[str, Any]`) + `SupportsToIntent`
    (`to_intent() -> SupportsToChanges`) protocols and the `RawChanges` default wrapper in
    `core/models/update_contracts.py`. Added `U` as a third type param to `CrudOperationsMixin` /
    `BaseService` / `CrudOperations` with a **PEP 696 bounded *default* (`RawChanges`)** so only the six
    activity domains override `U`; the ~53 non-activity `BaseService[Op, T]` sites stay untouched.
    🔑 **Implementation note:** the default is declared via old-style `TypeVar(..., default=RawChanges)`
    + `Generic[B, T, U]`, *not* PEP 695 inline `[U: Bound = Default]` — the latter is py313+ syntax the
    Ruff lint target (py312, ADR-067) rejects as invalid. `RawChanges(dict)` subclasses `dict` so
    dict-shaped callers (curriculum `ps_service`, the base `update_progress`/`update_status`/
    `update_content` helpers, `tasks_progress`) wrap once; the three curriculum route-facing protocols
    (`FormTemplateOperations`/`GroupOperations`/`RevisedExerciseOperations`) take `RawChanges`.
  - `update` / `update_for_user` take `U`, materialize uniformly via `updates.to_changes()` at the
    single backend seam (no `isinstance`, no `dict()`-wrap). Retype `_validate_update` / `_post_update`
    from `Mapping` to `U` across the base + the six domain overrides + forms (MyPy is the teacher —
    move them together).
  - Each activity domain declares its intent (`BaseService[TasksOperations, Task, TaskUpdateIntent]`).
    The generic `CRUDRouteFactory` builds the intent via the request's `to_intent()` — type it against
    `SupportsToIntent` (the six `*UpdateRequest` bases are inconsistent: Tasks + Choices extend
    `UpdateRequestBase`, the rest `BaseModel`; all six have `to_intent()`). Migrate `calendar_service`
    (the other `Mapping` caller) to build the intent. Delete the six `_intent_from_mapping` funnels +
    facade `update`/`update_for_user` `Mapping` overrides.
  - Delete the **six activity** `*UpdatePayload` (Task/Goal/Habit/Event/Choice/Principle) from
    `core/ports/query_types.py` (+ `__init__` re-exports), the advertising docstring in
    `core/services/mixins/crud_operations_mixin.py`, and the `query_types` usage-example blocks. **Leave
    the three curriculum payloads (Ku/Ps/Lp)** — out of scope; verify usages, leave if load-bearing;
    delete `BaseUpdatePayload` only if unused after.
  - **`force_archive` reconciliation:** keep Habits' `update_habit(uid, intent, *, force_archive)` as
    the documented bespoke explicit-validate path — `force_archive` cannot ride the intent (backend
    does `SET n += $updates`, no key filter → it would persist as a junk column). Do **not** silently
    wire on Tasks'/Principles' dead/stale `_validate_update` hooks (Principles' Rule 4 is unsatisfiable).
    *(Tasks' hook was later wired deliberately, 2026-08-23, under a ruling that first deleted its
    terminal-state rule — the Habits-style explicit call from `update_task`. Principles' stays stale;
    its reform is still tracked in `docs/roadmap/deferred-work.md`.)*
  - Verify: `./dev quality` (MyPy 0, Pyright 0) + the **six live pipeline tests** on Docker Neo4j
    (behavior must not change; Habits' force_archive cases are the canary). Tick col 5 for the six
    activity rows.

  **Phase 7b — docs/skills One-Path cleanup (gated prose, one PR). ✅ DONE (2026-06-05).** Rewrote
  every doc/skill to describe the *final* code — the single typed-intent path — verifying each
  behavioral claim against the code (mechanical rename is unsound). With this the **whole ADR-066
  migration is COMPLETE.** The items below record what was swept:
  - **Docs** (rewrote to the intent pattern, deleted TypedDict references):
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
    partial backend calls" — that needs control-flow domination and is unsound.
    The `# raw-write:` convention + review is the guard
    for #2.

## Verification (per phase)

- `./dev quality` → MyPy **0 errors**. MyPy is the migration teacher: widening/narrowing a service
  `update` parameter surfaces every override (`_validate_update`/`_post_update`) and protocol mirror
  that must move together (`core/ports/base_service_interface.py`, the 6 `*_core_service.py`).
- `uv run pytest` for the domain's service tests + status-transition / edge-sync tests.
- Confirm `_post_update` events still fire on the intent path for status transitions — verify against
  local Docker Neo4j or the `neo4j-cypher` MCP.
- Codex clean. Tick the table row so the next context starts from accurate state.

## Out of scope

- **Curriculum (PS/LP) and Finance** `update_*` methods — not Activity Domains; keep `dict[str, Any]`
  unless a later roadmap pulls them in.
- **Full-DTO writes (#3)** — `dto.to_dict()` → `backend.update` is entity *replace*, not a partial
  patch; `*UpdateIntent` does not model it. Leave as raw writes (annotated).
- **The `core: Any` mixin typing** beyond tightening it enough to type-check the intent — a full
  Protocol-ization of the activity mixins is its own change.

## References
- [ADR-066 — Typed Update Intents](../../decisions/ADR-066-typed-update-intents.md) (pattern owner)
- [ADR-065 — Functional Inference Contract](../../decisions/ADR-065-functional-inference-contract.md)
- [functional-direction.md](../functional-direction.md) — doctrine + extension tracker
- [activity-domain-inference-migration.md](../activity-domain-inference-migration.md) — sibling Tasks-first
  propagation roadmap (same structure)
- Reference implementation (after Phase 1): `core/models/task/task_update_intent.py`,
  `core/services/tasks/tasks_core_service.py`, `core/models/task/task_request.py::TaskUpdateRequest.to_intent`
