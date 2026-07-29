---
title: Domain-Specific Hooks Pattern
updated: 2026-03-24
category: patterns
related_skills: []
related_docs: []
---

# Domain-Specific Hooks Pattern
**Date**: 2026-01-17 (post-lifecycle hooks: 2026-03-24)
**Status**: ✅ Active Pattern

## Overview

Domain-specific hooks in `CrudOperationsMixin` implement the **Template Method Pattern** - a design pattern where a base class defines the algorithm structure while allowing subclasses to customize specific steps.

SKUEL provides **two hook categories**:
1. **Pre-operation hooks** (sync): `_validate_create`, `_validate_update` — run before the backend operation
2. **Post-lifecycle hooks** (async): `_post_create`, `_post_update`, `_post_delete` — run after the backend operation (e.g., event publishing)

**Location**: `core/services/mixins/crud_operations_mixin.py`

## The Pattern

### Core Concept

```python
class CrudOperationsMixin:
    # Generic CRUD operation (template method)
    async def create(self, entity: T) -> Result[T]:
        # Step 1: Call pre-operation validation hook (sync)
        validation = self._validate_create(entity)
        if validation:
            return Result.fail(validation)

        # Step 2: Proceed with creation
        result = await self.backend.create(entity)

        # Step 3: Call post-lifecycle hook (async)
        await self._post_create(entity, result)
        return result

    # Pre-operation hook (sync, default no-op)
    def _validate_create(self, entity: T) -> Result[None] | None:
        """Override to add domain-specific validation."""
        return None

    # Post-lifecycle hook (async, default no-op)
    async def _post_create(self, entity: T, result: Result[T]) -> None:
        """Override to publish events, etc."""
```

### Template Method Pattern

**Template Methods**: `create()`, `update()`, `delete()`
- Define the algorithm structure (validate → operate → post-hook)
- Call hook methods at specific points
- Handle result propagation and error conversion

**Pre-Operation Hooks** (sync): `_validate_create()` and `_validate_update()`
- Run BEFORE the backend operation
- Return `None` if valid, `Result.fail()` if invalid
- Use for business rule enforcement

**Post-Lifecycle Hooks** (async): `_post_create()`, `_post_update()`, `_post_delete()`
- Run AFTER the backend operation (regardless of success/failure)
- Receive the operation result — check `result.is_ok` before acting
- Use for event publishing, notifications, cache invalidation

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

Validation hooks run **before** the backend operation, preventing invalid data from reaching the database.

**Flow**:
```
User calls service.create(entity)
    ↓
CrudOperationsMixin.create() called
    ↓
_validate_create(entity) called (PRE-HOOK, sync)
    ↓ (if validation fails)
    Return Result.fail(error) immediately
    ↓ (if validation passes)
    backend.create(entity) called
    ↓
_post_create(entity, result) called (POST-HOOK, async)
    ↓
Return result
```

### 3. **State Transition Validation**

`_validate_update()` can enforce valid state transitions by inspecting both current state and proposed changes.

**Example**: Tasks service prevents modification of completed/archived tasks

The hook receives the typed update value `U` (ADR-066) — an Activity Domain `*UpdateIntent`
for the six activity domains, `RawChanges` otherwise. Read its materialized patch via
`updates.to_changes()` (a `dict` of only the set fields), then inspect keys:

```python
def _validate_update(self, current: Task, updates: TaskUpdateIntent) -> Result[None]:
    """Validate task updates with business rules."""
    changes = updates.to_changes()  # only the explicitly-set fields

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
    if "priority" in changes and current.is_overdue():
        new_priority = changes["priority"]
        if new_priority.to_numeric() < current.priority.to_numeric():
            return Result.fail(
                Errors.validation(
                    message="Cannot decrease priority of overdue task",
                    field="priority",
                    value=new_priority,
                )
            )

    return Result.ok(None)
```

> The live reference for this shape is `EventsCoreService._validate_update(current, updates: EventUpdateIntent)`.
> Tasks itself routes updates through `update_task` (backend-direct), so its `_validate_update`
> is illustrative — see `docs/roadmap/update-intents.md` for which domains run the hook live.

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

The hooks use the `Result.fail(result)` pattern for cross-type propagation:

```python
async def create(self, entity: T) -> Result[T]:
    validation = self._validate_create(entity)
    if validation:
        return Result.fail(validation)  # Result[None] → Result[T]

    return await self.backend.create(entity)
```

`Result.fail()` accepts another `Result` directly — it extracts the error internally.

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

### `_validate_update(current: T, updates: U) -> Result[None]`

**Purpose**: Validate updates before applying them

**Parameters**:
- `current`: Current entity state (type `T`)
- `updates`: The typed update value `U` (an Activity Domain `*UpdateIntent`, or `RawChanges`).
  Call `updates.to_changes()` to get the `dict` of set fields.

**Returns**:
- `Result.ok(None)`: Validation passed, proceed with update
- `Result.fail(error)`: Validation failed, return error to caller

**When Called**: Before `backend.update()` in `BaseService.update()`

**Common Validations**:
- State transition validation
- Immutable field protection (e.g., "cannot change created_at")
- Status-dependent validation (e.g., "cannot edit completed tasks")
- Update authorization (e.g., "only owner can modify")

## Post-Lifecycle Hooks (March 2026)

Post-lifecycle hooks run **after** the backend operation. They receive the operation result so implementations can check success before acting.

### `_post_create(entity: T, result: Result[T]) -> None`

**Purpose**: Post-creation behavior (event publishing, notifications)

**Parameters**:
- `entity`: The entity that was created
- `result`: The Result from `backend.create()` — check `result.is_ok` before acting

**When Called**: After `backend.create()` in `CrudOperationsMixin.create()`

### `_post_update(uid: str, old_entity: T, updates: U, result: Result[T]) -> None`

**Purpose**: Post-update behavior (event publishing with old/new state comparison)

**Parameters**:
- `uid`: Entity UID that was updated
- `old_entity`: Entity state BEFORE the update
- `updates`: The typed update value `U` (`*UpdateIntent` or `RawChanges`); use
  `updates.to_changes()` for the set-field `dict`
- `result`: The Result from `backend.update()`

**When Called**: After `backend.update()` in `CrudOperationsMixin.update()`

### `_post_delete(uid: str, old_entity: T, result: Result[bool]) -> None`

**Purpose**: Post-deletion behavior (event publishing with deleted entity data)

**Parameters**:
- `uid`: Entity UID that was deleted
- `old_entity`: Entity state BEFORE deletion (for event data)
- `result`: The Result from `backend.delete()`

**When Called**: After `backend.delete()` in `CrudOperationsMixin.delete()`

### Example: Event Publishing via Post-Hooks

```python
class FormTemplateService(BaseService[FormTemplateBackendOperations, FormTemplate]):
    """Uses post-hooks for event publishing instead of overriding CRUD methods."""

    async def _post_create(self, entity: FormTemplate, result: Result[FormTemplate]) -> None:
        if result.is_error:
            return
        await publish_event(
            self.event_bus,
            FormTemplateCreated(template_uid=entity.uid, ...),
            self.logger,
        )

    async def _post_update(
        self, uid: str, old_entity: FormTemplate, updates: dict, result: Result[FormTemplate]
    ) -> None:
        if result.is_error:
            return
        await publish_event(
            self.event_bus,
            FormTemplateUpdated(template_uid=uid, ...),
            self.logger,
        )
```

### When to Use Hooks vs. Overrides

| Approach | Use When |
|----------|----------|
| `_validate_*` hooks | Pre-operation validation (business rules) |
| `_post_*` hooks | Post-operation side effects (events, notifications) |
| Method override | Pre-operation guards (e.g., deletion guard that blocks the operation) |

**Example of method override (not a hook)**: FormTemplateService overrides `delete()` because it needs a submission guard that runs BEFORE the delete, not after.

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

**FormTemplateService** (`/core/services/forms/form_template_service.py`)
- `_post_create()`: Publishes `FormTemplateCreated` event
- `_post_update()`: Publishes `FormTemplateUpdated` event
- `delete()` override: Pre-delete submission guard + `FormTemplateDeleted` event

**Note**: Finance is a standalone bookkeeping domain and does NOT use BaseService hooks (January 2026 simplification). It implements validation directly in FinanceCoreService.

### Other Services

**Current State**: Most services use the default implementation (no custom validation or post-hooks)

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

    # ❌ WRONG - Don't perform side effects (use _post_create instead)
    await self.send_notification(entity)

    # ✅ CORRECT - Only validate
    if entity.amount <= 0:
        return Result.fail(Errors.validation("Amount must be positive"))
    return None
```

**Post-hook anti-pattern** (Don't do this):
```python
async def _post_create(self, entity: T, result: Result[T]) -> None:
    # ❌ WRONG - Don't override the CRUD method just to add events
    #    Use _post_create instead of overriding create()

    # ❌ WRONG - Don't use _post_delete for pre-delete guards
    #    Override delete() directly for guards that must block deletion

    # ✅ CORRECT - Check result before acting
    if result.is_ok:
        await publish_event(self.event_bus, MyEvent(...), self.logger)
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

    def _validate_update(self, current: Task, updates: TaskUpdateIntent) -> Result[None]:
        """Validate task updates."""
        changes = updates.to_changes()  # only the explicitly-set fields

        # Business rule: Cannot modify completed tasks
        if current.status == EntityStatus.COMPLETED:
            return Result.fail(
                Errors.validation(
                    message="Cannot modify completed tasks",
                    field="status"
                )
            )

        # Business rule: Cannot decrease priority of overdue tasks
        if "priority" in changes and current.is_overdue():
            new_priority = changes["priority"]
            if new_priority.to_numeric() < current.priority.to_numeric():
                return Result.fail(
                    Errors.validation(
                        message="Cannot decrease priority of overdue tasks",
                        field="priority"
                    )
                )

        return Result.ok(None)  # All validations passed
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
- **Result Error Propagation**: Uses `Result.fail(result)` for cross-type error propagation
- **Result[T] Pattern**: All validation returns Result[None] or None
- **Error Factories**: Uses `Errors.validation()` for structured errors
- **Event-Driven Architecture**: `/docs/patterns/event_driven_architecture.md`

## References

- CrudOperationsMixin: `/core/services/mixins/crud_operations_mixin.py`
- Base Service: `/core/services/base_service.py`
- Tasks Service Example: `/core/services/tasks/tasks_core_service.py`
- FormTemplate Post-Hook Example: `/core/services/forms/form_template_service.py`
- Error Handling: `/docs/patterns/error_handling.md` (SKUEL standard)

## Philosophy

**"Generic framework, domain-specific behavior"** - BaseService provides the infrastructure (CRUD, error handling, pagination), while domain services provide the intelligence (validation, business rules).

This separation keeps the architecture clean:
- **Framework code** in BaseService (stable, reusable)
- **Domain code** in subclasses (evolving, specific)

The hooks pattern makes it easy to add domain logic without modifying the framework.
