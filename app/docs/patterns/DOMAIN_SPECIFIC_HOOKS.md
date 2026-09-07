---
title: Domain-Specific Hooks Pattern
updated: 2026-09-07
category: patterns
related_skills: []
related_docs: []
---

# Domain-Specific Hooks Pattern
**Date**: 2026-01-17 (post-lifecycle hooks: 2026-03-24; hook reachability: 2026-08-06)
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
        if validation.is_error:
            return Result.fail(validation)

        # Step 2: Proceed with creation
        result = await self.backend.create(entity)

        # Step 3: Call post-lifecycle hook (async)
        await self._post_create(entity, result)
        return result

    # Pre-operation hook (sync, default no-op)
    def _validate_create(self, entity: T) -> Result[None]:
        """Override to add domain-specific validation."""
        return Result.ok(None)

    # Post-lifecycle hook (async, default no-op)
    async def _post_create(self, entity: T, result: Result[T]) -> None:
        """Override to publish events, etc."""
```

The hooks return `Result[None]`, always — never a bare `None`. The caller branches on
`.is_error`, so a hook that returned `None` would raise on the next line, and one that
returned a truthy-but-ok `Result` would be read correctly only because `.is_error` is
what is checked. `CrudOperationsMixin` is the sole owner of both declarations: it
declares them and it invokes them. `BaseService` used to re-declare identical no-ops,
which meant a domain reading either copy could not tell which one `create()` would call;
those were removed in #960.

## ⚠ A hook only binds the class that declares it

**`create()` is the only caller of `_validate_create` — so an override is dead unless
the object the caller holds has that override in its MRO.** Two ways to lose it, both of
which happened in SKUEL and both of which are silent:

**1. The facade doesn't inherit its sub-service.** The entity door is
`service.create(entity)` on the `{Domain}Service` FACADE (until it was bound to the
request door, the generated CRUD route entered there too), but the rules live on
`{Domain}CoreService`, which the facade holds as the delegated ATTRIBUTE `self.core`.
Delegation is not inheritance: the override was never in the facade's MRO, so `create()`
resolved `_validate_create` to the mixin's no-op and the door persisted whatever it was
handed.

Fix — route the facade's `create` into the core's, exactly as the update path already
does:

```python
class GoalsService(...):
    async def create(self, entity: Goal) -> Result[Goal]:
        """Route the entity door into the one validated create path."""
        return await self.core.create(entity)
```

**2. The domain door bypasses `create()` entirely.** `create_goal` / `create_habit` /
`create_choice` / `create_task` persisted through `_create_and_convert` (which called
`backend.create` directly — the helper was deleted once its last caller left), and
`create_principle` called `backend.create` itself. None of them entered the template
method, so no hook ran on the app's *primary* create path.

Fix — make the core's `create()` THE create primitive and have the domain method build
its entity and hand it over:

```python
async def create_goal(self, request: GoalCreateRequest, user_uid: UserUID) -> Result[Goal]:
    goal = ConversionServiceV2.goal_create_to_pure(request, uid, user_uid=user_uid, ...)
    return await self.create(goal)   # validates, persists, publishes
```

Building the entity with the **same converter** is the other half: one conversion site
means the doors cannot drift on which request fields they carry. (Since the generated
route was bound to the request door, the domain method IS the only conversion site.)

**Before trusting any hook, check both.** "The rule is written" is not "the rule runs" —
every Activity Domain hook in this codebase was unreachable until #960 and its follow-ups.
Pinned by `tests/unit/test_choice_create_path_parity.py`,
`tests/unit/test_activity_create_validation_reach.py`, and — for Tasks and Principles,
which have no hook left to reach but shared the same broken routing —
`tests/unit/test_task_principle_create_event_reach.py`.

The same MRO hole costs something even where no rule survives: the facade's inherited
`create()` published no `*Created` event and no ADR-074 embedding request either, so an
entity created through the generated route invalidated no user context and was never
embedded. All six domains now route both doors through the core's `create()` — and the
generated route no longer walks the entity door at all: it is bound to the request-door
primitive via `CRUDRouteConfig.request_create_method`, so the request's edge-only link
fields ride too (`tests/unit/test_route_create_via_primitive.py`).

### Reachability is not correctness

A dormant rule has never been executed, so nothing has ever tested whether it agrees with
the layers around it. Wiring one up is therefore two changes, not one — and the second is
where the damage is. Census who creates the entity *before* switching a rule on:

- **Goals** said `target_date <= start_date` → reject, while `GoalCreateRequest` validates
  the same pair with `allow_equal=True` and defaults `start_date` to today. Enabling it
  as written would have made the service refuse a same-day goal the API accepts.
- **Tasks** required a due date on HIGH/CRITICAL tasks, but the Activity DSL emits exactly
  that shape (`@priority(1|2)` with no `@when()`), as does `GoalTaskGenerator`. Deleted.
- **Principles** required `statement` ≥ 10 chars against a request model that declares
  `min_length=1`, and the DSL passes prose straight through. Deleted.

Three of five dormant rules were wrong about their own domain. That is the base rate to
expect, not an unlucky sample.

### Template Method Pattern

**Template Methods**: `create()`, `update()`, `delete()`
- Define the algorithm structure (validate → operate → post-hook)
- Call hook methods at specific points
- Handle result propagation and error conversion

**Pre-Operation Hooks** (sync): `_validate_create()` and `_validate_update()`
- Run BEFORE the backend operation
- Return `Result.ok(None)` if valid, `Result.fail()` if invalid
- Use for business rule enforcement

**Post-Lifecycle Hooks** (async): `_post_create()`, `_post_update()`, `_post_delete()`
- Run AFTER the backend operation (regardless of success/failure)
- Receive the operation result — check `result.is_ok` before acting
- Use for event publishing, notifications, cache invalidation

## Role and Responsibilities

### 1. **Business Rule Enforcement**

Domain-specific hooks allow each service to enforce its own business rules without modifying the base CRUD logic.

**Example**: Goals service validates that a goal's timeline is coherent

```python
class GoalsCoreService(BaseService[GoalsOperations, Goal]):
    def _validate_create(self, goal: Goal) -> Result[None]:
        """Validate goal creation with business rules."""
        # Business Rule: target date must not PRECEDE start date.
        # Equal is legal — GoalCreateRequest validates the same pair with
        # allow_equal=True, and the two layers must not disagree.
        if goal.target_date and goal.start_date and goal.target_date < goal.start_date:
            return Result.fail(
                Errors.validation(
                    message="Target date cannot be before start date",
                    field="target_date",
                    value=goal.target_date.isoformat(),
                )
            )
        return Result.ok(None)
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

**Example**: Tasks service refuses to lower the priority of an overdue task

The hook receives the typed update value `U` (ADR-066) — an Activity Domain `*UpdateIntent`
for the six activity domains, `RawChanges` otherwise. Read its materialized patch via
`updates.to_changes()` (a `dict` of only the set fields), then inspect keys:

```python
def _validate_update(self, current: Task, updates: TaskUpdateIntent) -> Result[None]:
    """Validate task updates with the domain's one business rule."""
    changes = updates.to_changes()  # only the explicitly-set fields

    # Overdue-priority protection: lowering the priority of an overdue task
    # sweeps a missed deadline under the rug instead of facing it.
    if "priority" not in changes or not current.is_overdue():
        return Result.ok(None)

    new_priority = Priority.from_value(changes["priority"])  # None/unknown → MEDIUM
    if new_priority.to_numeric() < Priority.from_value(current.priority).to_numeric():
        return Result.fail(
            Errors.validation(
                message="Cannot decrease priority of overdue tasks",
                field="priority",
                value=changes["priority"],
            )
        )

    return Result.ok(None)
```

> The live reference for this shape is `EventsCoreService._validate_update(current, updates: EventUpdateIntent)`,
> which the inherited CRUD invokes. Tasks reaches the same hook a different way: its facade
> routes `update` / `update_for_user` to `update_task`, so `update_task` calls
> `_validate_update` explicitly (the Habits precedent). See
> `docs/roadmap/done/update-intents.md` for which domains run the hook through the base.
>
> **A terminal-state rule used to sit above this one** — "cannot modify a
> completed/cancelled/archived task" — and was deleted, not wired, when the hook was made
> live (2026-08). It had never had a caller, and wiring it would have refused the repeat
> completion the cascade treats as a repair path, refused the status re-post that reopens a
> task, and resurrected for Tasks the achievement immutability deliberately removed for
> Goals. *Terminal ≠ frozen* in SKUEL: a finished activity stays editable.

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

### `_validate_create(entity: T) -> Result[None]`

**Purpose**: Validate entity before creation

**Parameters**:
- `entity`: The domain model being created (type `T` bound to `DomainModelProtocol`)

**Returns**:
- `Result.ok(None)`: Validation passed, proceed with creation
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

**Activity Domain Services** — four of six declare a creation hook; two deliberately do not:

| Service | `_validate_create()` | `_validate_update()` |
|---------|----------------------|----------------------|
| **ChoicesCoreService** | A supplied option set holds ≥ 2; BINARY carries exactly 2; STRATEGIC needs a 50+ char description. Options are OPTIONAL at creation — see `docs/domains/choices.md` | Decision immutability in ACTIVE/COMPLETED; option-count floor |
| **GoalsCoreService** | `target_date` must not PRECEDE `start_date` (equal is legal — matches the request model's `allow_equal=True`) | Date ordering *(achievement-state immutability deleted 2026-08 by ruling — completed goals are editable like completed tasks; reopen clears `achieved_date` via the completion-stamp helper)* |
| **HabitsCoreService** | DAILY habits cannot target > 7 days/week | Streak preservation on archive (bypassable via the transient `force_archive`); frequency consistency |
| **EventsCoreService** | Duration sanity, 5–720 minutes | Past-event immutability (notes/tags/quality_score exempt); duration sanity |
| **TasksCoreService** | *(none — deleted; the rule contradicted the DSL and GoalTaskGenerator)* | Overdue-priority protection, invoked explicitly by `update_task` (the facade routes the generic CRUD there) *(terminal-state protection deleted 2026-08 by ruling — it had no caller, and refusing every change to a finished task would refuse the repair-path repeat complete and the reopen)* |
| **PrinciplesCoreService** | *(none — deleted; the length floors were stricter than the request model)* | Declared, but `update_principle` is backend-direct and does not invoke it |

**Scope note on the three surviving creation rules.** Each guards the ENTITY and each sits
behind a stricter request edge (`GoalCreateRequest` rejects a past target date and enforces
the same ordering; `HabitCreateRequest` bounds its field at `ge=1, le=7`;
`EventCreateRequest` has no `duration_minutes` field at all). None of them fires for an HTTP
caller — Pydantic rejects the request first, at whichever door it came in by. What they backstop is every caller that hands
`create(entity)` an entity it assembled itself. That is a real surface, but do not describe
these as API-level validation.

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

Services are **not required** to override hooks. Default implementation returns `Result.ok(None)` (everything valid).

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
def _validate_create(self, entity: T) -> Result[None]:
    # ❌ WRONG - Don't modify entity in validation
    entity.status = "pending"

    # ❌ WRONG - Don't perform side effects (use _post_create instead)
    await self.send_notification(entity)

    # ✅ CORRECT - Only validate
    if entity.amount <= 0:
        return Result.fail(Errors.validation("Amount must be positive"))
    return Result.ok(None)
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

Illustrative only — `TasksCoreService` deliberately declares **no** creation hook
(see the inventory above). This shows the shape you would write, not code that exists:

```python
from core.services.base_service import BaseService
from core.models.enums import Priority
from core.models.task.task import Task
from datetime import date

class TasksCoreService(BaseService[TasksOperations, Task]):

    def _validate_create(self, task: Task) -> Result[None]:
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

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Task, updates: TaskUpdateIntent) -> Result[None]:
        """Validate task updates."""
        changes = updates.to_changes()  # only the explicitly-set fields

        # Business rule: Cannot decrease priority of overdue tasks
        if "priority" in changes and current.is_overdue():
            new_priority = Priority.from_value(changes["priority"])
            if new_priority.to_numeric() < Priority.from_value(current.priority).to_numeric():
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
def _validate_create(self, expense: ExpensePure) -> Result[None]:
    if expense.amount <= 0:  # Business rule: must be positive
        return Result.fail(Errors.validation("Amount must be positive"))
    return Result.ok(None)

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
def test_validate_create_rejects_inverted_timeline():
    service = GoalsCoreService(backend)
    goal = Goal(start_date=date.today(), target_date=date.today() - timedelta(days=1), ...)

    result = service._validate_create(goal)

    assert result.is_error
    assert result.expect_error().details["field"] == "target_date"


def test_validate_create_allows_a_same_day_goal():
    """The bound, not just the rejection — this is what disagreed with the API edge."""
    service = GoalsCoreService(backend)
    goal = Goal(start_date=date.today(), target_date=date.today(), ...)

    assert service._validate_create(goal).is_ok
```

### 4. **Clear Error Messages**

Validation failures return structured errors with field names, making debugging easy:

```python
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Target date cannot be before start date",
        "field": "target_date",
        "value": "2026-08-04"
    }
}
```

### 5. **No Breaking Changes**

Adding validation to an existing service doesn't require changes to routes or other services.

## Implementation Notes

### ARG002 Suppression

Base implementation has `# noqa: ARG002` comment:

```python
def _validate_create(self, entity: T) -> Result[None]:  # noqa: ARG002
    """Default implementation - no validation."""
    return Result.ok(None)
```

**Why**: Parameters are intentionally unused in base class (template method pattern). Subclasses use them when they override.

**Linter**: `ARG002` = "Unused method argument" - suppressed because this is intentional design.

## Related Patterns

- **Template Method Pattern**: Design pattern where algorithm structure is defined in base class
- **Result Error Propagation**: Uses `Result.fail(result)` for cross-type error propagation
- **Result[T] Pattern**: All validation returns `Result[None]`
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
