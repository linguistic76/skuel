---
title: Domain-Specific Hooks Pattern
updated: 2026-01-17
status: current
category: patterns
tags: [domain, hooks, patterns, specific]
related: []
---

# Domain-Specific Hooks Pattern
**Date**: 2026-01-17
**Status**: ✅ Active Pattern

## Overview

Domain-specific hooks in `BaseService` implement the **Template Method Pattern** - a design pattern where a base class defines the algorithm structure while allowing subclasses to customize specific steps.

**Location**: `core/services/base_service.py` (lines 268-322)

## The Pattern

### Core Concept

```python
class BaseService:
    # Generic CRUD operation (template method)
    async def create(self, entity: T) -> Result[T]:
        # Step 1: Call domain-specific validation hook
        validation = self._validate_create(entity)
        if validation:
            return Result.fail(validation.expect_error())

        # Step 2: Proceed with creation
        return await self.backend.create(entity)

    # Hook method (default implementation)
    def _validate_create(self, entity: T) -> Result[None] | None:
        """Override in subclasses to add domain-specific validation."""
        return None  # No validation = valid
```

### Template Method Pattern

**Template Method**: `BaseService.create()` and `BaseService.update()`
- Define the algorithm structure (validation → operation)
- Call hook methods at specific points
- Handle result propagation and error conversion

**Hook Methods**: `_validate_create()` and `_validate_update()`
- Provide default implementation (no-op, everything valid)
- Subclasses override to add domain-specific business rules
- Return `None` if valid, `Result.fail()` if invalid

## Role and Responsibilities

### 1. **Business Rule Enforcement**

Domain-specific hooks allow each service to enforce its own business rules without modifying the base CRUD logic.

**Example**: Tasks service validates high-priority tasks must have due dates

```python
class TasksCoreService(BaseService[TasksOperations, Task]):
    def _validate_create(self, task: Task) -> Result[None] | None:
        """Validate task creation with business rules."""
        # Business Rule: High-priority tasks must have due dates
        if task.priority.to_numeric() >= 3 and not task.due_date:  # HIGH=3, CRITICAL=4
            return Result.fail(
                Errors.validation(
                    message="High-priority tasks must have a due date",
                    field="due_date",
                    value=None,
                )
            )
        return None
```

### 2. **Pre-Operation Validation**

Hooks run **before** the backend operation, preventing invalid data from reaching the database.

**Flow**:
```
User calls service.create(entity)
    ↓
BaseService.create() called
    ↓
_validate_create(entity) called (HOOK)
    ↓ (if validation fails)
    Return Result.fail(error) immediately
    ↓ (if validation passes)
    backend.create(entity) called
```

### 3. **State Transition Validation**

`_validate_update()` can enforce valid state transitions by inspecting both current state and proposed changes.

**Example**: Tasks service prevents modification of completed/archived tasks

```python
def _validate_update(self, current: Task, updates: dict) -> Result[None] | None:
    """Validate task updates with business rules."""
    # Business Rule 1: Terminal state protection
    # Prevent modification of tasks in terminal states (preserves historical accuracy)
    if current.status.is_terminal():
        return Result.fail(
            Errors.validation(
                message="Cannot modify task in terminal state",
                field="status",
                value=current.status.value,
            )
        )

    # Business Rule 2: Overdue task protection
    # Cannot decrease priority of overdue tasks
    if "priority" in updates and current.is_overdue():
        new_priority = updates["priority"]
        if new_priority.to_numeric() < current.priority.to_numeric():
            return Result.fail(
                Errors.validation(
                    message="Cannot decrease priority of overdue task",
                    field="priority",
                    value=new_priority,
                )
            )

    return None
```

### 4. **Clean Separation of Concerns**

**BaseService Responsibilities**:
- Generic CRUD operations
- Error handling (via `@with_error_handling`)
- Result type conversion
- Pagination and filtering

**Domain Service Responsibilities** (via hooks):
- Domain-specific business rules
- Entity-specific validations
- State transition logic
- Field-level constraints

### 5. **Type-Safe Error Propagation**

The hooks use the `.expect_error()` pattern we implemented in Fix #3:

```python
async def create(self, entity: T) -> Result[T]:
    validation = self._validate_create(entity)
    if validation:
        # Type-safe: Result[None] → Result[T] with same error
        return Result.fail(validation.expect_error())

    return await self.backend.create(entity)
```

This ensures type safety while allowing validation errors to propagate correctly.

## Hook Method Signatures

### `_validate_create(entity: T) -> Result[None] | None`

**Purpose**: Validate entity before creation

**Parameters**:
- `entity`: The domain model being created (type `T` bound to `DomainModelProtocol`)

**Returns**:
- `None`: Validation passed, proceed with creation
- `Result.fail(error)`: Validation failed, return error to caller

**When Called**: Before `backend.create()` in `BaseService.create()`

**Common Validations**:
- Required field checks
- Field value constraints (positive numbers, valid dates, etc.)
- Business rule enforcement (e.g., "expense category must be active")
- Cross-field validations (e.g., "end date must be after start date")

### `_validate_update(current: T, updates: dict) -> Result[None] | None`

**Purpose**: Validate updates before applying them

**Parameters**:
- `current`: Current entity state (type `T`)
- `updates`: Dictionary of fields being updated

**Returns**:
- `None`: Validation passed, proceed with update
- `Result.fail(error)`: Validation failed, return error to caller

**When Called**: Before `backend.update()` in `BaseService.update()`

**Common Validations**:
- State transition validation
- Immutable field protection (e.g., "cannot change created_at")
- Status-dependent validation (e.g., "cannot edit completed tasks")
- Update authorization (e.g., "only owner can modify")

## Current Usage in SKUEL

### Active Implementation

**Activity Domain Services** (all 6 use BaseService hooks):

**TasksCoreService** (`/core/services/tasks/tasks_core_service.py`)
- `_validate_create()`: High-priority tasks must have due dates
- `_validate_update()`: Terminal state protection, overdue task priority protection

**GoalsCoreService** (`/core/services/goals/goals_core_service.py`)
- `_validate_create()`: Goal timeframe validation
- `_validate_update()`: Progress bounds checking

**HabitsCoreService** (`/core/services/habits/habits_core_service.py`)
- `_validate_create()`: Frequency validation
- `_validate_update()`: Streak protection rules

**ChoicesCoreService** (`/core/services/choices/choices_core_service.py`)
- `_validate_create()`: Options and criteria validation
- `_validate_update()`: Decision state transitions

**EventsCoreService** (`/core/services/events/events_core_service.py`)
- `_validate_create()`: Date/time validation
- `_validate_update()`: Recurrence rule validation

**PrinciplesCoreService** (`/core/services/principles/principles_core_service.py`)
- `_validate_create()`: Category validation
- `_validate_update()`: Strength bounds checking

**Note**: Finance is a standalone bookkeeping domain and does NOT use BaseService hooks (January 2026 simplification). It implements validation directly in FinanceCoreService.

### Other Services

**Current State**: Most services use the default implementation (no custom validation)

**Why**: Generic validations are handled by:
1. **Pydantic models** at the API boundary (type/format validation)
2. **Backend constraints** in Neo4j (uniqueness, required fields)
3. **Domain model construction** (frozen dataclasses ensure immutability)

**When to Override**: Only when domain-specific business rules need enforcement that can't be expressed in Pydantic or database constraints.

## Design Principles

### 1. **Optional, Not Required**

Services are **not required** to override hooks. Default implementation returns `None` (everything valid).

**Philosophy**: "Only add validation when business rules require it"

### 2. **Fail-Fast Validation**

Validation happens **before** database operations, preventing invalid state from being persisted.

**Benefits**:
- Database integrity maintained
- Clear error messages
- No rollback needed

### 3. **Single Responsibility**

Each hook method has one job: validate and return error or None.

**Anti-pattern** (Don't do this):
```python
def _validate_create(self, entity: T) -> Result[None] | None:
    # ❌ WRONG - Don't modify entity in validation
    entity.status = "pending"

    # ❌ WRONG - Don't perform side effects
    await self.send_notification(entity)

    # ✅ CORRECT - Only validate
    if entity.amount <= 0:
        return Result.fail(Errors.validation("Amount must be positive"))
    return None
```

### 4. **Template Method Pattern Benefits**

- **Open/Closed Principle**: BaseService is closed for modification, open for extension
- **Code Reuse**: Generic CRUD logic written once in BaseService
- **Consistency**: All services follow same validation flow
- **Type Safety**: Hook methods are type-checked by generic constraints

## Example: Adding Validation to a New Service

Let's say we want to add validation to `TasksCoreService`:

```python
from core.services.base_service import BaseService
from core.models.task.task import Task
from datetime import date

class TasksCoreService(BaseService[TasksOperations, Task]):

    def _validate_create(self, task: Task) -> Result[None] | None:
        """Validate task creation."""
        # Business rule: Due date cannot be in the past
        if task.due_date and task.due_date < date.today():
            return Result.fail(
                Errors.validation(
                    message="Due date cannot be in the past",
                    field="due_date",
                    value=task.due_date
                )
            )

        # Business rule: High-priority tasks must have a due date
        if task.priority == Priority.HIGH and not task.due_date:
            return Result.fail(
                Errors.validation(
                    message="High-priority tasks must have a due date",
                    field="due_date"
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Task, updates: dict) -> Result[None] | None:
        """Validate task updates."""
        # Business rule: Cannot modify completed tasks
        if current.status == ActivityStatus.COMPLETED:
            return Result.fail(
                Errors.validation(
                    message="Cannot modify completed tasks",
                    field="status"
                )
            )

        # Business rule: Cannot decrease priority of overdue tasks
        if "priority" in updates and current.is_overdue():
            new_priority = updates["priority"]
            if new_priority.to_numeric() < current.priority.to_numeric():
                return Result.fail(
                    Errors.validation(
                        message="Cannot decrease priority of overdue tasks",
                        field="priority"
                    )
                )

        return None  # All validations passed
```

## Comparison with Other Validation Layers

| Layer | Location | Purpose | Type |
|-------|----------|---------|------|
| **Pydantic** | API boundary | Type/format validation | Static (declarative) |
| **Domain-Specific Hooks** | Service layer | Business rule enforcement | Dynamic (programmatic) |
| **Database Constraints** | Neo4j | Data integrity | Static (declarative) |

**Example**: Validating an expense amount

```python
# Layer 1: Pydantic (API boundary)
class ExpenseCreateRequest(BaseModel):
    amount: float  # Type validation: must be float

# Layer 2: Domain Hook (Service layer)
def _validate_create(self, expense: ExpensePure) -> Result[None] | None:
    if expense.amount <= 0:  # Business rule: must be positive
        return Result.fail(Errors.validation("Amount must be positive"))
    return None

# Layer 3: Database (Neo4j constraint)
# CREATE CONSTRAINT FOR (e:Expense) REQUIRE e.amount IS NOT NULL
```

**Each layer has its role**:
- **Pydantic**: Validates request shape and types
- **Hooks**: Enforces domain business rules
- **Database**: Ensures data integrity

## Benefits of This Pattern

### 1. **Centralized Business Logic**

All domain-specific validation lives in the domain service, not scattered across routes or utilities.

### 2. **DRY (Don't Repeat Yourself)**

Generic CRUD logic written once in `BaseService`, reused by all domains.

### 3. **Easy to Test**

Hook methods are simple, focused functions that are easy to unit test:

```python
def test_validate_create_rejects_high_priority_without_due_date():
    service = TasksCoreService(backend)
    task = Task(priority=Priority.CRITICAL, due_date=None, ...)

    result = service._validate_create(task)

    assert result is not None
    assert result.is_error
    assert "High-priority tasks must have a due date" in result.error.message
```

### 4. **Clear Error Messages**

Validation failures return structured errors with field names, making debugging easy:

```python
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "High-priority tasks must have a due date",
        "field": "due_date",
        "value": null
    }
}
```

### 5. **No Breaking Changes**

Adding validation to an existing service doesn't require changes to routes or other services.

## Implementation Notes

### ARG002 Suppression

Base implementation has `# noqa: ARG002` comment:

```python
def _validate_create(self, entity: T) -> Result[None] | None:  # noqa: ARG002
    """Default implementation - no validation."""
    return None
```

**Why**: Parameters are intentionally unused in base class (template method pattern). Subclasses use them when they override.

**Linter**: `ARG002` = "Unused method argument" - suppressed because this is intentional design.

## Related Patterns

- **Template Method Pattern**: Design pattern where algorithm structure is defined in base class
- **Return Type Error Propagation**: Uses `.expect_error()` for type-safe error handling
- **Result[T] Pattern**: All validation returns Result[None] or None
- **Error Factories**: Uses `Errors.validation()` for structured errors

## References

- Base Service Implementation: `/core/services/base_service.py:268-322`
- Tasks Service Example: `/core/services/tasks/tasks_core_service.py:99-158`
- Goals Service Example: `/core/services/goals/goals_core_service.py:123-175`
- Return Type Pattern: `/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md`
- Error Handling: `/docs/patterns/error_handling.md` (SKUEL standard)

## Philosophy

**"Generic framework, domain-specific behavior"** - BaseService provides the infrastructure (CRUD, error handling, pagination), while domain services provide the intelligence (validation, business rules).

This separation keeps the architecture clean:
- **Framework code** in BaseService (stable, reusable)
- **Domain code** in subclasses (evolving, specific)

The hooks pattern makes it easy to add domain logic without modifying the framework.
