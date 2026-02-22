---
title: Service Creation Template
updated: 2025-11-27
status: current
category: reference
tags: [creation, reference, service]
related: []
---

# Service Creation Template

**Created:** 2025-10-17
**Updated:** 2025-10-17
**Status:** active
**Audience:** developers

## Quick Reference

Template for creating new services in SKUEL following the Protocol-Based Architecture pattern.

## Template

```python
from typing import Optional
from core.ports.domain_protocols import SomeOperations
from core.utils.result import Result
from core.utils.errors import Errors
from core.utils.logging_utils import get_logger

class NewService:
    """
    Service for [domain] operations.

    Follows SKUEL patterns:
    - Protocol-based dependencies
    - Result[T] error handling
    - Fail-fast philosophy (required dependencies)
    """

    def __init__(self, backend: SomeOperations):
        """
        Initialize service with required backend.

        Args:
            backend: Backend implementing SomeOperations protocol

        Raises:
            ValueError: If backend is None (fail-fast)
        """
        if not backend:
            raise ValueError("Backend is required")

        self.backend = backend
        self.logger = get_logger(__name__)

    async def do_something(self, uid: str) -> Result[SomeThing]:
        """
        Perform domain operation.

        Args:
            uid: Entity UID

        Returns:
            Result[SomeThing]: Success with entity or failure with error
        """
        try:
            result = await self.backend.operation(uid)

            if result.is_error:
                return result

            return Result.ok(result.value)

        except Exception as e:
            self.logger.error(f"Operation failed: {e}")
            return Result.fail(
                Errors.system(
                    message="Operation failed",
                    exception=e,
                    operation="do_something"
                )
            )
```

## Key Patterns

### 1. Protocol-Based Dependency
```python
def __init__(self, backend: SomeOperations):
    # backend is a Protocol interface, not concrete class
```

**Benefits:**
- No circular dependencies
- Type safety (MyPy checks protocol compliance)
- Easy testing (mock protocol)

### 2. Fail-Fast Validation
```python
if not backend:
    raise ValueError("Backend is required")
```

**Philosophy:** Services require all dependencies - no graceful degradation.

### 3. Result[T] Error Handling
```python
async def do_something(self) -> Result[SomeThing]:
    try:
        result = await self.backend.operation()
        if result.is_error:
            return result  # Propagate backend error
        return Result.ok(result.value)
    except Exception as e:
        return Result.fail(Errors.system(message="...", exception=e))
```

**Benefits:**
- Type-safe error propagation
- Errors captured, not thrown
- Boundary handler converts to HTTP at routes

### 4. Errors Factory
```python
return Result.fail(
    Errors.system(
        message="Operation failed",
        exception=e,
        operation="do_something"
    )
)
```

**Never use string-based failures:**
```python
# ❌ WRONG
return Result.fail("Operation failed")

# ✅ CORRECT
return Result.fail(Errors.system(message="Operation failed", exception=e))
```

## Related Documentation

- [Protocol-Based Architecture](/home/mike/0bsidian/skuel/docs/architecture/protocol_based_architecture.md)
- [ADR-001: Why Protocols?](/home/mike/0bsidian/skuel/docs/archive/decisions/ADR-001_why_protocols.md)
- [Protocol Definition Template](/home/mike/0bsidian/skuel/docs/reference/templates/protocol_definition.md)
- [Error Handling Standard](/home/mike/0bsidian/skuel/docs/patterns/error_handling.md)

## Examples

**Real implementations:**
- `/core/services/tasks_service.py`
- `/core/services/ku_service.py`
- `/core/services/events_service.py`
