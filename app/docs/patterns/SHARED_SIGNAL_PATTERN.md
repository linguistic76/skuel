---
title: Shared Signal Pattern
updated: 2026-04-21
status: proposed
category: patterns
tags: [patterns, activity-domains, intelligence, protocols, cross-cutting, design]
related:
  - ADR-057-activity-domain-sibling-signals
  - patterns/SIBLING_SIGNAL_PATTERN
  - patterns/protocol_architecture
  - patterns/BACKEND_OPERATIONS_ISP
---

# Shared Signal Pattern

> **Status:** Proposed shape. The one realization that already exists — [`ActivityKnowledgeIntelligenceService`](../../core/services/knowledge/activity_knowledge_intelligence_service.py) + [`KnowledgeIntelligenceDelegationMixin`](../../core/services/mixins/knowledge_intelligence_mixin.py) — is in production. This doc names that shape so future cross-cutting consultations (Calendar, user capacity) follow it. The "why" lives in [ADR-057](../decisions/ADR-057-activity-domain-sibling-signals.md).

**Core Principle:** *Infrastructure sees what no single domain owns; domains consult it.*

Some corrective signals are not peer-to-peer. They come from **infrastructure that serves all 6 Activity Domains** (Tasks, Goals, Habits, Events, Choices, Principles) and is typically *user-scoped* rather than *entity-scoped* — knowledge mastery across all a user's Kus, calendar pressure across all their scheduled commitments, task throughput across their whole workload. A Shared Signal is a narrow, ISP-shaped protocol produced by such infrastructure and consumed by each Activity Domain's intelligence method at the point of judgment.

The [Sibling Signal pattern](SIBLING_SIGNAL_PATTERN.md) is this pattern's peer-to-peer counterpart. Same consumption machinery (narrow protocol, delegation mixin, constructor injection); different producer location.

## The Cross-Cutting Systems

SKUEL's CLAUDE.md names **5 cross-cutting systems** — infrastructure orthogonal to the 7 subsystems and the Entity Types:

| System | Purpose |
|--------|---------|
| UserContext | ~250 fields of cross-domain state |
| Search | Unified search across all domains |
| Calendar | Aggregates Tasks, Events, Habits, Goals |
| Askesis | Pedagogical guide — ZPD-aware Socratic companion |
| Messaging | Notifications (planned) |

**Knowledge** is a sixth implicit cross-cutting concern. It already has a production realization — `ActivityKnowledgeIntelligenceService` — but has never appeared in the cross-cutting roster. It is the **first realization of the Shared Signal pattern**, and this doc is the place where that identity is made explicit.

Future Shared Signals will typically be produced by one of these systems. Calendar → every Activity Domain (collision pressure), UserContext → every Activity Domain (capacity, load balance), Askesis → every Activity Domain (pedagogical readiness) all fit the shape.

## Shape

```
┌────────────────────────────────────────────┐
│  Producer: shared infrastructure service   │
│  (singleton or factory-wired)              │
│                                            │
│  ActivityKnowledgeIntelligenceService       │
│  CalendarIntelligenceService (future)       │
│  UserCapacityService (future)               │
└──────────────────┬─────────────────────────┘
                   │ implements
                   ▼
┌────────────────────────────────────────────┐
│  Protocol: narrow ISP surface              │
│  core/ports/intelligence_protocols.py      │
│                                            │
│  KnowledgeIntelligenceOperations           │
│  CalendarCollisionOperations (future)      │
│  UserCapacityOperations (future)           │
└──────────────────┬─────────────────────────┘
                   │ consumed via
                   ▼
┌────────────────────────────────────────────┐
│  Delegation mixin                          │
│  core/services/mixins/                     │
│                                            │
│  KnowledgeIntelligenceDelegationMixin      │
│  CalendarCollisionDelegationMixin (future) │
└──────────────────┬─────────────────────────┘
                   │ inherited by
                   ▼
┌────────────────────────────────────────────┐
│  Every Activity Domain facade              │
│  (TasksService, GoalsService, HabitsService,│
│   EventsService, ChoicesService,            │
│   PrinciplesService)                        │
└────────────────────────────────────────────┘
```

- **Producer** is one service, wired as a singleton (or factory-wired, one instance per user session) in `services_bootstrap/compose.py`.
- **Protocol** is a narrow `Protocol` in `core/ports/intelligence_protocols.py`, scoped to just the consultation surface — not the producer's whole intelligence surface.
- **Delegation mixin** lives in `core/services/mixins/`. It holds the 2-to-5 delegation methods every facade inherits so the call site is `self.knowledge_intelligence.get_knowledge_suggestions(...)` rather than a hand-wired lookup.
- **Consumers** are the 6 Activity Domain facades. Each inherits the delegation mixin and assigns the injected producer to `self.{concern}` in `__init__`.

## Protocol Shape

```python
# core/ports/intelligence_protocols.py
from typing import Protocol, runtime_checkable

from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import Result


@runtime_checkable
class KnowledgeIntelligenceOperations(Protocol):
    """Knowledge intelligence shared across all 6 activity domains.

    Implemented by ActivityKnowledgeIntelligenceService — one instance wired
    into every activity facade via self.knowledge_intelligence.
    """

    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> "Result[KnowledgeSuggestionsResult]": ...

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> "Result[KnowledgePrerequisitesResult]": ...

    # ... narrow, shared surface only
```

**Naming rule:** `{Concern}IntelligenceOperations` or `{Concern}Operations` — `KnowledgeIntelligenceOperations`, `CalendarCollisionOperations`. The name identifies the *shared concern*, not any single producing service.

Shared Signal protocols do **not** live in `core/ports/sibling_signals.py` — that file is reserved for peer-to-peer protocols. Shared Signal protocols live in `core/ports/intelligence_protocols.py` alongside the existing `KnowledgeIntelligenceOperations`.

## Consumption Shape

Every Activity Domain facade inherits the delegation mixin. The mixin provides one method per protocol surface. The facade's `__init__` wires the producer onto `self`.

```python
# ILLUSTRATIVE (consumer side — follows the knowledge pattern exactly)

class TasksService(KnowledgeIntelligenceDelegationMixin, ...):
    def __init__(
        self,
        ...,
        knowledge_intelligence: KnowledgeIntelligenceOperations,  # protocol, not concrete
    ) -> None:
        ...
        self.knowledge_intelligence = knowledge_intelligence
```

```python
# ILLUSTRATIVE (delegation mixin — core/services/mixins/)

class KnowledgeIntelligenceDelegationMixin:
    knowledge_intelligence: KnowledgeIntelligenceOperations

    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[KnowledgeSuggestionsResult]:
        return await self.knowledge_intelligence.get_knowledge_suggestions(
            user_uid, entity_uid
        )
```

**Consumption rules:**

1. **Every facade mounts every Shared Signal.** The shape is uniform — no facade opts out. This is what distinguishes Shared Signals from Sibling Signals (which are selective, consumed only where a specific peer's insight sharpens a specific judgment).
2. **Delegation methods, not reach-across.** The facade calls `self.knowledge_intelligence.method(...)`, not `self.backend` or another facade.
3. **Idempotent queries.** Signal methods are read-only. No event publishes, no counters incremented, no cached writes.
4. **Narrow result types.** Signal methods return specific TypedDicts or frozen dataclasses (`KnowledgeSuggestionsResult`, `CalendarCollisionResult`, `UserCapacityResult`), never `Result[Any]`. See `/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md`.

## The 3 Cross-Cutting Gaps

From the ADR-057 Phase 1 audit, reclassified in this pattern. Each is a place where implementation of a new Shared Signal would begin:

| # | Producer (infrastructure) | Target method | Signal |
|---|---------------------------|---------------|--------|
| 4 | User-capacity / throughput service (new) | `HabitsIntelligenceService.analyze_habit_performance()` | throughput / capacity |
| 5 | Calendar (cross-cutting system) | `HabitsIntelligenceService.analyze_habit_performance()` | calendar collision |
| 8 | Knowledge mastery (existing `ActivityKnowledgeIntelligenceService`) | `ChoicesIntelligenceService.get_decision_intelligence()` | mastery score |

Gap #8 extends the *existing* knowledge singleton with a new method; gaps #4 and #5 require introducing new producer services (a user-capacity service, and lifting calendar-collision reasoning out of wherever it sits today into a shared consultation surface).

## Edge ↔ Signal Mapping

Shared Signals frequently aggregate across many edges rather than riding on a single one — that is the trait that distinguishes them from sibling signals.

| Signal (future/existing) | Data source | Scope |
|--------------------------|-------------|-------|
| `KnowledgeIntelligenceOperations.get_knowledge_suggestions` | `(User)-[:MASTERED_AT]->(Ku)` + entity→Ku edges | User-wide, entity-contextual |
| `KnowledgeIntelligenceOperations.get_knowledge_prerequisites` | `(Entity)-[:REQUIRES_KNOWLEDGE]->(Ku)` | Per-entity, user-scoped mastery |
| `TaskThroughputSignal` (future) | `(User)<-[:OWNED_BY]-(Task)` aggregated over a window | User-wide throughput |
| `CalendarCollisionSignal` (future) | `(Event)-[:OCCURS_AT]->(TimeSlot)` + direct `event_date` / `scheduled_at` properties | User-wide calendar window |
| `KnowledgeMasterySignal` (future, gap #8) | `(User)-[:MASTERED_AT]->(Ku)` with recency/decay | User-wide mastery aggregate |

## Precedent to Imitate

The shape above is not theoretical — it is the **exact** shape of `ActivityKnowledgeIntelligenceService`, which has been in production since the April 2026 extraction. Concretely:

- **Producer:** [`core/services/knowledge/activity_knowledge_intelligence_service.py`](../../core/services/knowledge/activity_knowledge_intelligence_service.py) — one shared instance, backend is `UniversalNeo4jBackend[Entity]` with `NeoLabel.ENTITY` so it queries across all domains.
- **Protocol:** `KnowledgeIntelligenceOperations` in [`core/ports/intelligence_protocols.py`](../../core/ports/intelligence_protocols.py) — narrow, 4 methods, runtime-checkable.
- **Delegation mixin:** [`core/services/mixins/knowledge_intelligence_mixin.py`](../../core/services/mixins/knowledge_intelligence_mixin.py) — 4 one-line delegations to `self.knowledge_intelligence`.
- **Consumers:** all 6 Activity Domain facades inherit the mixin; none overrides it.
- **Composition:** wired once in `services_bootstrap/compose.py`; each facade receives the same instance.

When adding a new Shared Signal (Calendar, user capacity, future cross-cutting concerns), match this topology file-for-file. Do not invent a new placement.

## What This Pattern Is *Not*

- **Not a sibling-to-sibling call.** If the producer is one of the 6 Activity Domains, it is a [Sibling Signal](SIBLING_SIGNAL_PATTERN.md), not a Shared Signal. Cue: does the signal make sense without naming a specific peer entity? (Shared) or does it require pointing at a peer entity to interpret? (Sibling.)
- **Not a replacement for `UserContextIntelligence`.** Aggregate life-path scoring, synergy detection, and daily-planning synthesis stay in `synergy_intelligence.py` / `life_path_intelligence.py` / `daily_planning.py`. Shared Signals are for *per-entity* judgment that needs a cross-cutting aggregate as *one input among several*, not for whole-user aggregation.
- **Not a synchronous event bus.** Signals are consulted at query time. If you need to *react* to a state change (e.g. knowledge gained → recompute goal feasibility), use the existing event bus (`core/events/`).
- **Not an opt-in capability.** Every Shared Signal is mounted on every facade. The shape is the contract. If a new cross-cutting concern only benefits one domain, it is not a Shared Signal — it is a domain-specific sub-service.

## Testing Shape

Each protocol gets a focused unit test with a fake implementation. For each facade that inherits the delegation mixin, one smoke test confirms the delegation fires (the delegation itself is a one-liner; the integration value comes from the producer-side tests).

```python
# ILLUSTRATIVE
async def test_tasks_facade_delegates_knowledge_suggestions_to_injected_service():
    fake_knowledge = FakeKnowledgeIntelligence()
    tasks_service = TasksService(..., knowledge_intelligence=fake_knowledge)

    await tasks_service.get_knowledge_suggestions(user_uid="user_1")

    assert fake_knowledge.calls == [("get_knowledge_suggestions", "user_1", None)]
```

## Implementation Checklist (When Proceeding)

1. **Producer service:** new (or existing) service in `core/services/{concern}/` implementing the shared-concern surface.
2. **Protocol:** add `{Concern}IntelligenceOperations` to `core/ports/intelligence_protocols.py`, marked `@runtime_checkable`.
3. **Delegation mixin:** new file `core/services/mixins/{concern}_intelligence_mixin.py`, shaped exactly like `knowledge_intelligence_mixin.py`.
4. **Facade wiring:** every one of the 6 Activity Domain facades inherits the mixin, accepts the producer as an `__init__` parameter typed as the Protocol, assigns it to `self.{concern}` (or `self.{concern}_intelligence`).
5. **Composition:** one instance in `services_bootstrap/compose.py`, passed into every facade's constructor.
6. **Integration test per consumer:** smoke-test that each facade's delegation method calls into the injected producer.

## Related Documentation

- **Architecture:** [ADR-057](../decisions/ADR-057-activity-domain-sibling-signals.md) — the decision record (names Sibling Signal; this doc covers its cross-cutting counterpart)
- **Companion pattern:** [Sibling Signal Pattern](SIBLING_SIGNAL_PATTERN.md) — peer-to-peer consultation between the 6 Activity Domains
- **Philosophy:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md) — shared-shape-with-unique-verbs
- **Topology:** [SERVICE_TOPOLOGY.md](../architecture/SERVICE_TOPOLOGY.md) — where the knowledge singleton lives today (first realization of this pattern)
- **Intelligence index:** [INTELLIGENCE_SERVICES_INDEX.md](../intelligence/INTELLIGENCE_SERVICES_INDEX.md) — catalog of intelligence services including the shared knowledge instance
- **Consolidation:** [SERVICE_CONSOLIDATION_PATTERNS.md](SERVICE_CONSOLIDATION_PATTERNS.md) — the structural contract (7 shared sub-services); Shared Signal is the orthogonal *consultation* contract
- **Protocol shape:** [Protocol Architecture](protocol_architecture.md) — how protocols are defined and consumed in SKUEL
- **ISP pattern:** [BackendOperations ISP](BACKEND_OPERATIONS_ISP.md) — precedent for narrow Protocol slices
- **Return types:** [Return Type Error Propagation](RETURN_TYPE_ERROR_PROPAGATION.md) — why signals return typed results, not `Result[Any]`
