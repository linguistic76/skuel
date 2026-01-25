---
title: ADR-027: KnowledgeCarrier Protocol
updated: 2026-01-07
status: current
category: decisions
tags: [adr, decisions, protocol, knowledge, curriculum]
related: [ADR-017, ADR-023]
---

# ADR-027: KnowledgeCarrier Protocol

**Status:** Accepted

**Date:** 2026-01-07

**Decision Type:** ☑️ Pattern/Practice

**Related ADRs:**
- Related to: ADR-017 (Relationship Service Unification)
- Related to: ADR-023 (Curriculum BaseService Migration)

---

## Context

**What is the issue we're facing?**

SKUEL's philosophy is "everything is a KU" - Knowledge Units are the foundational building blocks that flow through all domains. However, this philosophy wasn't encoded in the type system, making it difficult for:

1. **MCF (AI content authoring)** to understand which entities carry knowledge
2. **Type-safe dispatch** for unified knowledge operations across domains
3. **SearchRouter** to implement unified knowledge search
4. **Intelligence services** to calculate knowledge relevance scores

The codebase had two relationship patterns:
- **Activity Domains** (6): UnifiedRelationshipService with semantic relationships
- **Curriculum Domains (3) + MOC**: Direct driver queries for read-heavy traversal (MOC is Content/Organization but uses same pattern)

Both patterns are architecturally correct for their purposes, but lacked a unifying abstraction that answers: "Does this entity carry knowledge?"

**Constraints:**
- Must work with frozen dataclasses (SKUEL's immutable domain model)
- Cannot add Neo4j fields (all data from existing graph relationships)
- Must be `@runtime_checkable` for dynamic dispatch
- Must not break existing architecture

---

## Decision

**What is the change we're proposing/making?**

Introduce a `KnowledgeCarrier` protocol that all 10 domains implement, enabling unified knowledge operations without breaking existing patterns.

**Protocol Hierarchy:**

```python
@runtime_checkable
class KnowledgeCarrier(Protocol):
    """Base protocol - all 10 domains implement this."""
    uid: str

    def knowledge_relevance(self) -> float:
        """How relevant is knowledge to this entity? (0.0-1.0)"""
        ...

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """Get all knowledge UIDs this entity carries/references."""
        ...

@runtime_checkable
class SubstantiatedKnowledge(KnowledgeCarrier, Protocol):
    """Extended protocol for entities with substance tracking."""
    def substance_score(self) -> float: ...

@runtime_checkable
class CurriculumCarrier(KnowledgeCarrier, Protocol):
    """Protocol for curriculum domains (KU, LS, LP, MOC)."""
    def get_all_knowledge_uids(self) -> set[str] | tuple[str, ...]: ...

@runtime_checkable
class ActivityCarrier(KnowledgeCarrier, Protocol):
    """Protocol for activity domains with learning impact."""
    def learning_impact_score(self) -> float: ...
```

**Implementation by Domain:**

| Domain | knowledge_relevance() | get_knowledge_uids() |
|--------|----------------------|---------------------|
| **KU** | Always 1.0 (IS knowledge) | `(self.uid,)` |
| **LS** | Always 1.0 (IS curriculum) | Via `get_all_knowledge_uids()` |
| **LP** | Always 1.0 (IS curriculum) | Via `get_all_knowledge_uids()` |
| **MOC** | Always 1.0 (IS curriculum) | Via `get_all_knowledge_units()` |
| **Task** | 0.0-1.0 based on learning alignment | `()` (graph-native) |
| **Event** | 0.0-1.0 based on learning impact | `()` (graph-native) |
| **Habit** | 0.0-1.0 based on learning category | `()` (graph-native) |
| **Goal** | 0.0-1.0 based on learning goal type | `()` (graph-native) |
| **Choice** | 0.0-1.0 based on strategic nature | `()` (graph-native) |
| **Principle** | 0.0-1.0 based on intellectual category | `()` (graph-native) |

**Key Design Decisions:**

1. **Graph-native for Activity domains**: `get_knowledge_uids()` returns `()` for activity domains because knowledge relationships are stored as Neo4j edges, not model properties. Services query the graph for actual data.

2. **Calculated relevance scores**: `knowledge_relevance()` uses existing model fields (category, type, status) to calculate how knowledge-relevant an entity is.

3. **Protocol, not inheritance**: Using Python protocols instead of base class inheritance because frozen dataclasses cannot inherit behavior cleanly.

---

## Alternatives Considered

### Alternative 1: Abstract Base Class

**Description:** Create `KnowledgeCarrierBase` class that all domain models inherit from.

**Pros:**
- Shared implementation code
- Enforced method signatures at compile time

**Cons:**
- Frozen dataclasses don't inherit well
- Would require major refactoring of all 10 domain models
- Violates "One Path Forward" (multiple inheritance paths)

**Why rejected:** Doesn't work with SKUEL's frozen dataclass pattern.

### Alternative 2: Mixin Classes

**Description:** Create `KnowledgeCarrierMixin` that provides default implementations.

**Pros:**
- Reusable code across domains
- Works with multiple inheritance

**Cons:**
- Mixins + frozen dataclasses = complex MRO issues
- Each domain has different knowledge semantics
- Default implementations would need overriding anyway

**Why rejected:** Each domain's knowledge relevance is calculated differently.

### Alternative 3: Service-Level Abstraction Only

**Description:** Keep knowledge logic in services, don't add to models.

**Pros:**
- No model changes
- Centralized logic

**Cons:**
- No type-safe dispatch (`isinstance(entity, KnowledgeCarrier)`)
- MCF can't introspect model capabilities
- Violates "knowledge is foundational" philosophy

**Why rejected:** Loses type-safety and discoverability benefits.

---

## Consequences

### Positive Consequences
- ✅ Type-safe dispatch: `isinstance(entity, KnowledgeCarrier)` works
- ✅ MCF can understand knowledge relationships via protocol introspection
- ✅ SearchRouter can implement `search_knowledge_carriers()` method
- ✅ Encodes "everything is a KU" philosophy in the type system
- ✅ No breaking changes to existing code
- ✅ No new Neo4j fields required

### Negative Consequences
- ⚠️ Activity domains return empty tuple from `get_knowledge_uids()` (requires service query)
- ⚠️ Slight model complexity increase (3 new methods per model)
- ⚠️ Knowledge relevance calculation is heuristic-based

### Neutral Consequences
- ℹ️ Two relationship patterns (Activity/Curriculum) remain unchanged
- ℹ️ Protocol is opt-in for runtime checks

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Relevance scores don't match user expectations | Medium | Low | Iterate on scoring heuristics based on feedback |
| Service layer forgets to query graph for knowledge UIDs | Low | Medium | Clear documentation, code review patterns |

---

## Implementation Details

### Code Location

**Primary files:**
- `/core/models/protocols/knowledge_carrier_protocol.py` (NEW)
- `/core/models/protocols/__init__.py` (MODIFIED - exports)

**Domain model modifications (3 methods each):**
- `/core/models/ku/ku.py`
- `/core/models/ls/ls.py`
- `/core/models/lp/lp.py`
- `/core/models/moc/moc.py`
- `/core/models/task/task.py`
- `/core/models/event/event.py`
- `/core/models/habit/habit.py`
- `/core/models/goal/goal.py`
- `/core/models/choice/choice.py`
- `/core/models/principle/principle.py`

### Testing Strategy

- [ ] Unit tests: Protocol conformance tests for all 10 domains
- [ ] Integration tests: SearchRouter knowledge search
- [ ] Manual testing: MCF content authoring with protocol introspection

---

## Documentation & Communication

### Pattern Documentation Checklist

- [ ] Create companion pattern guide in `/docs/patterns/KNOWLEDGE_CARRIER_PROTOCOL.md`
- [ ] Add pattern guide to `/docs/INDEX.md`
- [x] Cross-reference: ADR → CLAUDE.md (update Knowledge Substance section)

### Related Documentation
- CLAUDE.md: Knowledge Substance Philosophy section
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`

---

## Future Considerations

### When to Revisit
- If knowledge relevance scores prove inadequate for MCF
- If SearchRouter needs more sophisticated knowledge queries
- If new domains are added that carry knowledge

### Evolution Path

**Phase 2 (Future):** Add `search_knowledge_carriers()` to SearchRouter:
```python
async def search_knowledge_carriers(
    self,
    query: str,
    min_relevance: float = 0.0,
    entity_types: list[EntityType] | None = None,
) -> SearchResponse:
    """Search across all knowledge-carrying entities."""
```

**Phase 3 (Future):** Intelligence services use protocol for recommendations:
```python
def get_knowledge_recommendations(entity: KnowledgeCarrier) -> list[str]:
    if entity.knowledge_relevance() > 0.5:
        # High-relevance entity - recommend related knowledge
        ...
```

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-07 | Claude | Initial implementation | 1.0 |

---

## Appendix

### Code Snippets

**Protocol Definition:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class KnowledgeCarrier(Protocol):
    """Enables 'everything is a KU' philosophy across all 10 domains."""
    uid: str

    def knowledge_relevance(self) -> float:
        """How relevant is knowledge to this entity? (0.0-1.0)

        - Curriculum domains (KU, LS, LP) + MOC: Always 1.0
        - Activity domains: Based on learning alignment/category
        """
        ...

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """Get all knowledge UIDs this entity carries/references.

        - Curriculum domains: Return actual KU UIDs
        - Activity domains: Return () - query graph via service
        """
        ...
```

**Usage Example:**
```python
from core.models.protocols import KnowledgeCarrier

def process_entity(entity: KnowledgeCarrier) -> None:
    # Type-safe dispatch
    if isinstance(entity, KnowledgeCarrier):
        relevance = entity.knowledge_relevance()
        if relevance > 0.5:
            # High knowledge relevance - process accordingly
            knowledge_uids = entity.get_knowledge_uids()
            ...
```

**Activity Domain Implementation Pattern:**
```python
@dataclass(frozen=True)
class Task:
    # ... existing fields ...

    def knowledge_relevance(self) -> float:
        """Calculate knowledge relevance from existing fields."""
        score = 0.0
        if self.source_learning_step_uid:
            score += 0.4  # Derived from curriculum
        if self.fulfills_goal_uid:
            score += 0.2  # Goal-aligned
        if self.knowledge_mastery_check:
            score += 0.3  # Explicit mastery tracking
        return min(score, 1.0)

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """Graph-native - query service for actual relationships."""
        return ()

    def learning_impact_score(self) -> float:
        """How much does completing this task impact learning?"""
        return self.learning_alignment_score()
```
