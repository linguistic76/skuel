---
title: Clean Patterns Reference
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# Clean Patterns Reference
*Last updated: 2026-01-19*

This document contains established patterns for SKUEL service development, moved from CLAUDE.md during consolidation.

## The Standard Pattern

```python
from core.services.protocols import get_enum_value, EnumLike

# For any enum value extraction:
value = get_enum_value(some_enum)  # Returns enum.value or object itself

# For type checking:
if isinstance(obj, EnumLike):
    # Object has .value attribute
```

**Rules:**
- Do not use lambda expressions (SKUEL012)

## Composition Root Pattern

```python
# Single point of service wiring in services_bootstrap.py
async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    # All service creation happens here - no factory pattern
    tasks_service = TasksService(tasks_backend)
    events_service = EventsService(events_backend)
    return Result.ok(Services(tasks=tasks_service, events=events_service, ...))
```

## Protocol-Based Dependency Injection

```python
# Services depend on protocols, not implementations
class KnowledgeService:
    def __init__(self, backend: KnowledgeOperations):  # Protocol interface
        self.backend = backend

# Backends implement protocols
class KnowledgeUniversalBackend(UniversalNeo4jBackend, KnowledgeOperations):
    async def get_knowledge_unit(self, uid: str) -> Result[Optional[KnowledgeUnit]]:
        # Implementation details
```

## Universal Backend Pattern

```python
# Consistent pattern across ALL domains
learning_backend = LearningUniversalBackend(driver)
learning_intelligence = LearningIntelligenceService(
    learning_backend=learning_backend,  # Direct injection
    progress_backend=None,
    embeddings_service=None
)
```

## Result[T] Error Handling

```python
# Services return Result[T] internally
async def get_knowledge_unit(self, uid: str) -> Result[KnowledgeUnit]:
    result = await self.backend.get_knowledge_unit(uid)
    if result.is_error:
        return result
    return Result.ok(result.value)

# Routes use @boundary_handler for HTTP conversion
@rt("/api/ku/get")
@boundary_handler()
async def get_knowledge_route(request, uid: str):
    return await service.get_knowledge_unit(uid)  # Auto-converts Result[T] to HTTP
```

## Three-Tier Type System

```python
# Clean separation: External -> Transfer -> Core

# Tier 1: Pydantic (External validation)
class KnowledgeCreateRequest(BaseModel):
    title: str
    content: str

# Tier 2: DTO (Mutable transfer)
@dataclass
class KnowledgeDTO:
    uid: str
    title: str
    content: str

# Tier 3: Domain Model (Immutable business logic)
@dataclass(frozen=True)
class KnowledgeUnit:
    uid: str
    title: str
    content: str

    def calculate_complexity(self) -> float:
        """Business logic in domain model"""
        return len(self.content.split()) / 100.0
```

## Fail-Fast Architecture

```python
# No graceful degradation - require components to work
if not backend:
    raise ValueError("Knowledge backend is required")  # Fail immediately

# No alternative paths
knowledge_service = services.learning_intelligence  # One way only
if not knowledge_service:
    return Result.fail("Knowledge intelligence not available")  # Clear error
```

## Related Documentation

- `/docs/patterns/three_tier_type_system.md` - Full type system documentation
- `/docs/patterns/ERROR_HANDLING.md` - Error handling patterns
- `/docs/patterns/protocol_architecture.md` - Protocol architecture
- `/core/utils/services_bootstrap.py` - Composition root implementation
