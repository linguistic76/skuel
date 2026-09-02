---
title: Domain Documentation
created: 2025-12-04
updated: 2026-09-02
status: current
category: domains
tags: [domains, reference, architecture]
---

# Domain Documentation

This folder contains documentation for each of SKUEL's entity types.

## Entity Types

Each entity type is a peer — behavioral traits (not category membership) determine infrastructure behavior. See [ADR-047](../decisions/ADR-047-entity-types-replace-domain-categories.md).

| Entity Type | Key Purpose |
|-------------|-------------|
| [Tasks](tasks.md) | Work items with dependencies and deadlines |
| [Goals](goals.md) | Objectives with milestones and progress |
| [Habits](habits.md) | Recurring behaviors with streak tracking |
| [Events](events.md) | Calendar items with scheduling |
| [Choices](choices.md) | Decisions with outcome tracking |
| [Principles](principles.md) | Values that guide goals and choices |
| [Finance](finance.md) | Expense and budget tracking (admin-only) |
| [KU](ku.md) | Atomic knowledge unit (point topology) |
| [PS](ps.md) | Sequential path steps (edge topology) |
| [LP](lp.md) | Complete learning sequences (path topology) |
| [UserEntry](user_entry.md) | All user-authored content — exercise turn-ins, journal entries, uploads, periodic notes (ADR-054) |
| [MOC](moc.md) | Non-linear navigation (graph topology via ORGANIZES) |
| [LifePath](lifepath.md) | "Am I living my life path?" |

**UID formats are NOT listed here.** [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md) carries the authoritative per-type table; a second copy here rotted into colon-spelled prefixes that no generator has ever minted, with two entity types claiming the same one. The rule that outlives any copy: a colon is reserved for internal machine identifiers and is **never an authored** entity UID — the machine-minted periodic UserEntry uids (`ue:daily:…` and their weekly/monthly siblings) are real graph identities and the sanctioned exception, which `is_sanctioned_machine_uid()` enumerates. And entity kind is read from the label / `entity_type` / an edge — never sniffed from the UID's spelling (ADR-013, SKUEL034).

**MOC Architecture:** MOC is NOT a separate entity — it IS a KU with ORGANIZES relationships. A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity).

**Journals are not an entity type.** The AI companion is ephemeral by default (ADR-073's
understanding wall + ADR-078's opt-in persistence) — a saved chat becomes an owner-private
`:ConversationSession`, never a `UserEntry`. Which stored notes exist, and what pipeline
each carries, is a live contract with more than one answer — `Pipeline.JOURNAL` is authored
rather than assigned, and the notes around journaling carry other pipelines — so this
catalog does not restate it.

**See:** [Journals Domain Architecture](../architecture/JOURNALS_DOMAIN_ARCHITECTURE.md) — the successor to the deleted per-domain doc, and the authority on journal persistence — plus the UserEntry row above and the `@journals` skill.

## Quick Reference

### Domain → Config Mapping

```python
from core.models.relationship_registry import DOMAIN_CONFIGS, TASKS_CONFIG
from core.models.enums import Domain

# Get config for a domain
config = DOMAIN_CONFIGS[Domain.TASKS]  # or use TASKS_CONFIG directly
```

### Service Location Pattern

```
core/services/{domain}/
├── {domain}_core_service.py      # Core CRUD operations
├── {domain}_search_service.py    # Search operations
└── {domain}_service.py           # Facade (combines core + search)
```

### Facade Delegation Pattern (February 2026)

Activity Domain facades use explicit `async def` delegation methods — MyPy-native, no mixin needed:

```python
from typing import Any

class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService

    # Explicit delegation — each method is a real async def
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def search_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)
```

**Key features:**
- **MyPy-native**: All methods are real `async def` — no workaround needed
- **Underscore prefix convention**: `_filters` means "placeholder for future implementation" (not "unused")
- **One file**: The service class is the single source of truth

**Note:** `FacadeDelegationMixin` and `facade_protocols.py` are deleted (February 2026).

### Intelligence Service Pattern (January 2026 - ADR-031)

Domain intelligence services follow the **unified internal creation pattern**:

| Domain Type | Domains | Intelligence Pattern |
|-------------|---------|---------------------|
| **Activity (6)** | Tasks, Goals, Habits, Events, Choices, Principles | Created internally by facade |
| **Curriculum (3)** | KU, PS, LP | Created internally by facade |
| **Organizational (1)** | MOC | No intelligence (KU-based, uses KU intelligence) |

**Unified Pattern:**
- All facades create their intelligence service internally (not passed in from bootstrap)
- All extend `BaseAnalyticsService[BackendOperations[T], T]`
- No external intelligence creation in `services_bootstrap.py`

```python
# Example: LpService creates intelligence internally
class LpService(BaseService[LpOperations, LearningPath]):
    def __init__(self, driver, ps_service, graph_intel, ...):
        # Step 5: Create intelligence INTERNALLY (January 2026 - Unified Pattern)
        self.intelligence = LpIntelligenceService(
            backend=lp_backend,
            graph_intel=graph_intel,
            ...
        )
```

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`

## Domain Enum Quick Reference

Each activity domain has domain-specific enums beyond the shared `Priority` and `EntityStatus`. All enums import from `core.models.enums`.

| Domain | Key Enums |
|--------|-----------|
| **Tasks** | Priority, EntityStatus, RecurrencePattern, EnergyLevel |
| **Goals** | GoalType, GoalTimeframe, MeasurementType, HabitEssentiality |
| **Habits** | HabitPolarity, HabitCategory, HabitDifficulty, CompletionStatus, RecurrencePattern, TimeOfDay |
| **Events** | RecurrencePattern, EnergyLevel, ActivityType |
| **Choices** | ChoiceType |
| **Principles** | PrincipleCategory, PrincipleSource, PrincipleStrength, AlignmentLevel, TriggerType |
| **Curriculum** | LpType, StepDifficulty, LearningLevel, KuComplexity, SELCategory |
| **KU** | SELCategory |

**See:** [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md) for the complete catalog with values and dynamic patterns.

## See Also

- [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [UnifiedRelationshipService](../patterns/UNIFIED_RELATIONSHIP_SERVICE.md)
- [Relationship Registry](../../core/models/relationship_registry.py)
