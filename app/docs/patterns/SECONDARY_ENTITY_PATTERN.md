---
title: Secondary Entity Pattern
updated: 2026-01-19
status: current
category: patterns
tags: [patterns, secondary-entity, tracking, completion, reflection]
related: [STANDALONE_SERVICE_PATTERN.md, SERVICE_CONSOLIDATION_PATTERNS.md]
---

# Secondary Entity Pattern

When to use a standalone service for entities that track engagement with a primary entity.

---

## Overview

Secondary entities are graph-connected nodes that capture user engagement with a primary entity. They don't need the full `BaseService` machinery because they:

1. Are always queried via their parent entity
2. Don't need CRUD route factories
3. Handle ownership via User relationship, not `verify_ownership()`
4. Have simpler lifecycle (create, query, delete - rarely update)

---

## Examples in SKUEL

| Secondary Entity | Primary Entity | Service | Relationship Pattern |
|------------------|----------------|---------|---------------------|
| `HabitCompletion` | `Habit` | `HabitsCompletionService` | `(User)-[:COMPLETED]->(HabitCompletion)-[:COMPLETION_OF]->(Habit)` |
| `PrincipleReflection` | `Principle` | `PrinciplesReflectionService` | `(User)-[:MADE_REFLECTION]->(PrincipleReflection)-[:REFLECTS_ON]->(Principle)` |

---

## When to Use This Pattern

Use a secondary entity when:

1. **Tracking engagement over time** - Multiple records per primary entity
2. **Rich metadata per occurrence** - Quality scores, notes, timestamps
3. **Analytics required** - Trends, streaks, patterns
4. **Cross-domain triggers** - Links to what caused the engagement

### Contrast with Primary Entities

| Aspect | Primary Entity | Secondary Entity |
|--------|----------------|------------------|
| **Base Class** | `BaseService[Operations, Model]` | Standalone (no inheritance) |
| **Queried via** | Direct UID lookup | Parent entity |
| **CRUD routes** | Factory-generated | Custom minimal |
| **Ownership** | `verify_ownership()` | User relationship |
| **Updates** | Frequent | Rare (usually immutable) |
| **Examples** | Task, Goal, Habit, Principle | HabitCompletion, PrincipleReflection |

---

## Graph Schema

Secondary entities form a chain: **User → Secondary → Primary**

```
(User)-[:MADE_REFLECTION]->(PrincipleReflection)-[:REFLECTS_ON]->(Principle)
                                   |
                                   +-[:TRIGGERED_BY]->(Goal|Habit|Event|Choice)
                                   |
                                   +-[:REVEALS_CONFLICT]->(Principle)
```

```
(User)-[:COMPLETED]->(HabitCompletion)-[:COMPLETION_OF]->(Habit)
```

---

## Service Structure

### Constructor Pattern

Secondary entity services take the secondary backend directly:

```python
class PrinciplesReflectionService:
    """
    Service for principle reflection operations.

    Architecture Note:
        This service intentionally does NOT extend BaseService.
        PrincipleReflection is a "secondary entity" - it tracks engagement
        with a primary entity (Principle). This follows the HabitCompletion
        pattern established in HabitsCompletionService.
    """

    def __init__(
        self,
        backend: BackendOperations[PrincipleReflection],
        event_bus: Any | None = None,
    ) -> None:
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("principles.reflection")
```

For services that need both primary and secondary access:

```python
class HabitsCompletionService:
    def __init__(
        self,
        habits_backend: BackendOperations[Habit],          # Primary (for validation)
        completions_backend: BackendOperations[HabitCompletion],  # Secondary
        event_bus: Any | None = None,
    ) -> None:
        self.habits_backend = habits_backend
        self.completions_backend = completions_backend
        self.event_bus = event_bus
```

---

## Core Methods

Secondary entity services typically have 4-6 focused methods:

| Method | Purpose |
|--------|---------|
| `save_*()` / `record_*()` | Create secondary record with relationships |
| `get_*_for_{primary}()` | Query by parent entity |
| `get_*_history()` | Time-range queries |
| `calculate_*_trend()` | Analytics over time |
| `get_cross_domain_*()` | Analyze triggers/sources |

### Example: PrinciplesReflectionService

```python
# Core operations
async def save_reflection(self, principle_uid, user_uid, alignment_level, evidence, ...) -> Result[PrincipleReflection]
async def get_reflections_for_principle(self, principle_uid, user_uid, limit) -> Result[list[PrincipleReflection]]

# Analytics
async def get_alignment_trend(self, principle_uid, user_uid, days) -> Result[AlignmentTrend]
async def get_cross_domain_insights(self, principle_uid, user_uid) -> Result[list[CrossDomainInsight]]

# Conflict detection
async def detect_conflicts(self, principle_uid, user_uid) -> Result[list[str]]
```

---

## Event Publishing

Secondary entity services publish domain events for cross-domain reactions:

```python
# PrinciplesReflectionService events
PrincipleReflectionRecorded  # New reflection saved
PrincipleConflictRevealed    # Conflict detected between principles

# HabitsCompletionService events
HabitCompleted               # Single completion
HabitCompletionBulk          # Batch completion
```

---

## Bootstrap Wiring

Secondary entity backends are created alongside primary backends:

```python
# services_bootstrap.py

# Primary backend
principle_backend = UniversalNeo4jBackend[Principle](
    driver, NeoLabel.PRINCIPLE, Principle
)

# Secondary backend
principle_reflection_backend = UniversalNeo4jBackend[PrincipleReflection](
    driver, NeoLabel.PRINCIPLE_REFLECTION, PrincipleReflection
)

# Service receives secondary backend
principles_reflection_service = PrinciplesReflectionService(
    backend=principle_reflection_backend,
    event_bus=event_bus,
)
```

---

## Facade Integration

Secondary entity services are sub-services of the primary domain facade:

```python
class PrinciplesService(FacadeDelegationMixin, BaseService[PrinciplesOperations, Principle]):
    def __init__(self, ...):
        # Primary sub-services (extend BaseService)
        self.core = PrinciplesCoreService(...)
        self.search = PrinciplesSearchService(...)
        self.intelligence = PrinciplesIntelligenceService(...)

        # Secondary entity service (standalone)
        self.reflection = PrinciplesReflectionService(
            backend=principle_reflection_backend,
            event_bus=event_bus,
        )
```

Access via facade: `principles_service.reflection.save_reflection(...)`

---

## When NOT to Use This Pattern

Don't use secondary entities for:

1. **Entities with their own identity** - If users reference it directly, it's primary
2. **Simple status changes** - Use enum fields on primary entity
3. **Single occurrence per primary** - Use a field, not a separate node
4. **No analytics needed** - Simpler to store on primary entity

---

## See Also

- **Standalone services:** `/docs/patterns/STANDALONE_SERVICE_PATTERN.md`
- **Service consolidation:** `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`
- **Event-driven architecture:** `/docs/patterns/event_driven_architecture.md`
