---
title: "ADR-060: UserContext as Single Source of Truth — Awareness Slice Protocols Retired"
updated: 2026-09-01
status: current
category: decisions
tags: [adr, decisions, type-safety, user-context, isp, protocols]
related:
  - ADR-031-baseservice-mixin-decomposition
---

# ADR-060: UserContext as Single Source of Truth — Awareness Slice Protocols Retired

**Status:** Accepted
**Date:** 2026-05-11
**Related:**
[ADR-031 BaseService Mixin Decomposition](ADR-031-baseservice-mixin-decomposition.md)

## Context

`core/ports/context_awareness_protocols.py` defined 11 `Protocol` classes — <!-- historical -->
`CoreIdentity`, `TaskAwareness`, `KnowledgeAwareness`, `HabitAwareness`,
`GoalAwareness`, `EventAwareness`, `PrincipleAwareness`, `ChoiceAwareness`,
`LearningPathAwareness`, `CrossDomainAwareness`, `FullAwareness` — each an
ISP-compliant slice of `UserContext`. The intent was that a service taking
`TaskAwareness` instead of `UserContext` declared a narrower dependency
contract; MyPy would then prevent it from reaching into knowledge or habit
state.

In practice the slices re-declared ~25 fields that already lived on
`UserContext`. Two artifacts named the same fields:

| Field | Slice protocol | `UserContext` |
|---|---|---|
| `active_task_uids: list[str]` | `TaskAwareness` L106 | L164 |
| `knowledge_mastery: dict[str, float]` | `KnowledgeAwareness` L152 | L249 |
| `active_habit_uids` | `HabitAwareness` L188 | L221 |
| `active_goal_uids` | `GoalAwareness` L226 | L203 |

Adding a field to `UserContext` did **not** widen the slice protocols.
Keeping them in sync was a manual convention. The MyPy-enforced
"this service only reads task state" guarantee was theoretical — any
service needing a new field could just widen its slice annotation.
Drift had no detector. The two-file maintenance burden was real and
recurring; the type-level minimization benefit was hypothetical.

Real consumer surface was small: 8 method signatures in
`UnifiedRelationshipService` and 2 in `service_protocols.py`. The
protocol layer (480 lines of definitions + 271 lines of tests) supported
~10 narrow-typed call sites — and the narrowing didn't even prevent the
shape it claimed to prevent.

## Decision

Delete the slice protocols. `UserContext` is the single contract for
user-state parameters.

**Changes:**

1. `core/ports/context_awareness_protocols.py` deleted (480 lines, 11 <!-- historical -->
   protocols).
2. `tests/unit/test_context_awareness_protocols.py` deleted (271 lines). <!-- historical -->
3. `core/ports/__init__.py` no longer exports `TaskAwareness`,
   `KnowledgeAwareness`, `HabitAwareness`, `GoalAwareness`,
   `EventAwareness`, `PrincipleAwareness`, `ChoiceAwareness`,
   `LearningPathAwareness`, `CrossDomainAwareness`, `FullAwareness`,
   `CoreIdentity`.
4. Consumer signatures take `UserContext` directly. The 10 affected
   signatures (`UnifiedRelationshipService.get_actionable_for_user`,
   `_get_blocked_for_user`, `_calculate_readiness_score`,
   `_calculate_relevance_score`, `_is_completed`, `_is_urgent`,
   `_identify_blocking_reasons`, `get_goal_aligned_for_user`,
   `GoalTaskGeneratorOperations.generate_tasks_for_goal`,
   `HabitEventSchedulerOperations.schedule_events_for_habit`) now take
   `UserContext` under `TYPE_CHECKING`.
5. `core/ports/service_protocols.py` and
   `core/services/relationships/unified_relationship_service.py` import
   `UserContext` from `core/services/user/unified_user_context.py`
   under `TYPE_CHECKING`. This is a deliberate dependency direction
   (`core/ports/` → `core/services/`), accepted because `UserContext`
   *is* the user-state contract; there is no smaller stable surface
   to bottle.

Implemented in commit `a82faaba` (-797 / +12 lines).

## Alternatives Considered

1. **Generate slice protocols from `UserContext` annotations.** Tag
   each `UserContext` field with metadata declaring which slices it
   belongs to, then generate the protocols at module load. Rejected —
   collapses the two artifacts into one source of truth, but
   subordinates the protocols to the model. The slice surface stops
   being "what the consumer minimally needs" (ISP intent) and becomes
   "a labeled partition of what the provider exposes." Also introduces
   a meta-programming layer that IDEs and MyPy navigate poorly.
2. **Keep slice protocols + add a drift-detection test.** Write a unit
   test that asserts every field declared on a slice protocol exists
   on `UserContext` with the same type. Rejected — preserves the
   two-peer design and catches drift, but does not address the deeper
   issue: the slice surface was already not strictly minimal (each
   slice was hand-curated to include "likely-needed" fields, not "only
   the fields this service reads"). Even with drift detection, the
   protocols would have been documentation of intent, not enforcement.
3. **Status quo — two sources of truth, manual sync.** Rejected for
   the reasons in Context. Drift had no detector and the type-level
   guarantee was theoretical.

## Consequences

**Positive**

- One place to declare context fields:
  `core/services/user/unified_user_context.py`. Adding a context field
  is a one-file change, not a one-file change plus updates to N slice
  protocols.
- Tests construct a minimal `UserContext` via dataclass defaults
  instead of bespoke protocol-conforming stubs:
  `UserContext(user_uid="u", username="u")` works, override only what
  the test cares about.
- 751 lines of protocols + tests deleted. No drift to monitor.
- Mocks for service tests do not need to know which slice a service
  uses — they construct `UserContext` once and reuse it across
  service-under-test cases.

**Negative / accepted trade-offs**

- The type-level "minimum context dependency" guarantee is gone. A
  service taking `UserContext` can in principle reach into any of ~250
  fields. Trust the function docstring (or its body) for what it
  actually reads — not the parameter type. This was already the
  effective state of the codebase; the protocols documented intent,
  not enforcement.
- `core/ports/` now imports from `core/services/user/` under
  `TYPE_CHECKING`. The protocol layer accepts `UserContext` as the
  user-state contract, rather than maintaining a parallel ISP slice
  surface.

**Neutral**

- The "Broader Protocol Adoption" backlog in
  `docs/architecture/INTELLIGENCE_BACKLOG.md` is closed by deletion,
  not completion. The intelligence gaps listed in that file are
  unrelated to the protocol-narrowing effort and survive.

## When to Revisit

Reintroduce slice protocols only if **both** of these hold:

1. A specific class of bug attributable to over-broad `UserContext`
   access shows up in practice — a service reaches into a field it
   shouldn't, and the type system would have caught it.
2. A drift-detection mechanism exists so the slice declarations stay
   synchronized with `UserContext` automatically.

Absent (1), the type-level minimum is theoretical. Absent (2), the
drift returns. Until both, prefer primitive parameters for narrow
needs over wrapping protocols.

## Related

- See `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` →
  "UserContext as Single Source of Truth" for the current usage
  pattern and testing examples.
- Extends [ADR-031 BaseService Mixin Decomposition](ADR-031-baseservice-mixin-decomposition.md).
  ADR-031 established the mixin layer that previously consumed slice
  protocols; ADR-060 simplifies those mixin signatures to a single
  `UserContext` parameter.
