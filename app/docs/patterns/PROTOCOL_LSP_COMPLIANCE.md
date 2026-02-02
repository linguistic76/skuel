---
title: Protocol LSP Compliance Pattern
updated: 2026-01-20
category: patterns
related_skills:
- python
related_docs: []
---

# Protocol LSP Compliance Pattern
**Date**: 2025-11-07
**Status**: ✅ Implemented

**NOTE (January 2026):** MOC is now KU-based. The MOC protocol examples below
are historical - they illustrate the LSP pattern but the actual MocOperations
protocol has been removed. See `/docs/domains/moc.md` for current MOC architecture.
## Related Skills

For implementation guidance, see:
- [@python](../../.claude/skills/python/SKILL.md)


## Core Principle

**"Domain protocols ADD type-safe methods, they don't OVERRIDE base contracts"**

## The Problem (Historical MOC Protocol Example)

### Before - LSP Violation ❌

```python
class BackendOperations(Protocol):
    async def update(self, uid: str, updates: dict[str, Any]) -> Any:
        """Generic dict-based update."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Any:
        """Generic delete with cascade option."""
        ...

class MOCOperations(BackendOperations, Protocol):
    # ❌ OVERRIDES with incompatible signature!
    async def update(self, uid: str, request: MOCUpdateRequest) -> Result[MapOfContent]:
        """Update MOC metadata."""
        ...

    # ❌ OVERRIDES with incompatible signature!
    async def delete(self, uid: str) -> Result[bool]:
        """Delete MOC."""
        ...
```

**MyPy Error:**
```
error: Argument 2 of "update" is incompatible with supertype "BackendOperations"
This violates the Liskov substitution principle
```

## The Solution (LSP Compliant) ✅

### After - ADD Domain Methods

```python
class MOCOperations(BackendOperations, Protocol):
    """
    Protocol for MOC backend operations.

    Inherits base CRUD operations from BackendOperations:
    - create(data: dict) -> Result[T]
    - get(uid: str) -> Result[T | None]
    - update(uid: str, updates: dict[str, Any]) -> Result[T]  ← INHERITED
    - delete(uid: str, cascade: bool = False) -> Result[bool]  ← INHERITED

    Adds MOC-specific type-safe operations below.
    """

    # Domain-specific type-safe methods (don't override!)
    async def create_moc(self, request: MOCCreateRequest) -> Result[MapOfContent]:
        """Type-safe MOC creation."""
        ...

    async def update_moc(self, uid: str, request: MOCUpdateRequest) -> Result[MapOfContent]:
        """Type-safe MOC update."""
        ...

    async def delete_moc(self, uid: str, cascade: bool = True) -> Result[bool]:
        """Type-safe MOC deletion with MOC-specific cascade default."""
        ...
```

## Service Layer Pattern

### Service Converts Pydantic → Dict

```python
class MocCoreService:
    def __init__(self, backend: MOCOperations):
        self.backend = backend

    async def update(self, uid: str, request: MOCUpdateRequest) -> Result[MapOfContent]:
        """
        Update MOC metadata.

        SERVICE LAYER RESPONSIBILITY:
        - Converts Pydantic MOCUpdateRequest → dict
        - Calls backend's generic update(uid, dict) method
        - This is the correct pattern - Pydantic at edges, dicts in backend
        """
        # SERVICE LAYER: Convert Pydantic → dict
        updates = {}
        if request.title is not None:
            updates["title"] = request.title
        if request.description is not None:
            updates["description"] = request.description
        # ... other fields

        updates["updated_at"] = datetime.now()

        # INFRASTRUCTURE LAYER: Generic dict-based update
        result = await self.backend.update(uid, updates)

        return result
```

## Why This Pattern?

### 1. **LSP Compliance** - Protocols are substitutable

```python
def generic_update(backend: BackendOperations, uid: str):
    # Works for ANY BackendOperations implementation
    await backend.update(uid, {"field": "value"})
```

If MOC overrides `update()` signature, this breaks!

### 2. **Layer Separation** - Backend knows nothing about Pydantic

| Layer | Responsibility | Types |
|-------|---------------|-------|
| **Web/API** | Validation | Pydantic (BaseModel) |
| **Service** | Conversion | dict (from `.model_dump()`) |
| **Backend** | Storage | dict (to Neo4j) |

Backend accepting `BaseModel` violates separation of concerns.

### 3. **100% Dynamic Backend Pattern**

`UniversalNeo4jBackend` uses dict-based introspection:

```python
async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
    updates["updated_at"] = datetime.now().isoformat()
    query = f"""
    MATCH (n:{self.label} {{uid: $uid}})
    SET n += $updates  # Dict-based update
    RETURN n
    """
```

This pattern REQUIRES dicts. Adding `BaseModel | dict` complicates it for no benefit.

### 4. **Type Safety Where It Matters**

Domain-specific methods provide type safety at the protocol level:

```python
# Protocol documents the domain contract
async def update_moc(self, uid: str, request: MOCUpdateRequest) -> Result[MapOfContent]:
    """Type-safe MOC update."""
    ...

# Service layer honors the contract
async def update(self, uid: str, request: MOCUpdateRequest) -> Result[MapOfContent]:
    # Pydantic → dict conversion
    updates = self._convert_request_to_dict(request)
    # Generic backend call
    return await self.backend.update(uid, updates)
```

## Pattern Application

### All Domain Protocols Should Follow This

```python
class TasksOperations(BackendOperations, Protocol):
    # ✅ Inherits: create(dict), get(uid), update(uid, dict), delete(uid)

    # ✅ ADDS domain-specific methods (doesn't override!)
    async def update_task(self, task_id: str, data: dict) -> Result[bool]:
        ...

class EventsOperations(BackendOperations, Protocol):
    # ✅ Inherits base methods

    # ✅ ADDS domain-specific methods
    async def link_event_to_goal(self, event_uid: str, goal_uid: str) -> Result[bool]:
        ...
```

### Anti-Pattern to Avoid

```python
# ❌ NEVER DO THIS
class SomeOperations(BackendOperations, Protocol):
    # ❌ Overriding with incompatible signature
    async def update(self, uid: str, request: SomeRequest) -> Result[SomeType]:
        ...
```

## MyPy Verification

**Before fix:**
```bash
$ poetry run mypy core/services/protocols/moc_protocols.py
error: Argument 2 of "update" is incompatible with supertype
error: Signature of "delete" incompatible with supertype
Found 2 errors
```

**After fix:**
```bash
$ poetry run mypy core/services/protocols/moc_protocols.py
✅ No override violations found!
```

## Benefits Achieved

| Aspect | Result |
|--------|--------|
| **LSP Compliance** | ✅ Protocols are fully substitutable |
| **Layer Separation** | ✅ Backend independent of Pydantic |
| **Type Safety** | ✅ Domain methods provide type guarantees |
| **Code Clarity** | ✅ Pattern is consistent across domains |
| **MyPy Validation** | ✅ Static analysis passes |

## Philosophy Alignment

From CLAUDE.md:
> "Design so the parts work together, the pieces move together"

The backend IS working correctly with dicts. The issue was MOC trying to change that contract. By fixing MOC's protocol (not the foundation), we maintain architectural consistency.

## Related Patterns

- **Three-Tier Type System** - Pydantic at edges, dicts in backend
- **100% Dynamic Backend** - Dict-based introspection requires dict inputs
- **Protocol-Based Architecture** - Zero port dependencies via structural typing

## References

- Liskov Substitution Principle: https://mypy.readthedocs.io/en/stable/common_issues.html#incompatible-overrides
- Protocol location: `/core/services/protocols/curriculum_protocols.py`
- MOC Architecture: `/docs/domains/moc.md` (KU-based since January 2026)
