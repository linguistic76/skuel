# Result Chaining Patterns

**Created**: September 24, 2025

## Overview

SKUEL uses a monadic Result[T] pattern with chaining methods to eliminate if/else error checking and create cleaner, more functional code.

## Available Chaining Methods

### Synchronous Methods

#### `map(func: Callable[[T], U]) -> Result[U]`
Transform the value inside a Result if successful.

```python
result = Result.ok(5)
doubled = result.map(lambda x: x * 2)  # Result.ok(10)
```

#### `flat_map(func: Callable[[T], Result[U]]) -> Result[U]`
Chain operations that return Results, preventing double-wrapping.

```python
def validate(x: int) -> Result[int]:
    return Result.ok(x) if x > 0 else Result.fail(Errors.validation("Must be positive", field="x"))

result = Result.ok(5)
validated = result.flat_map(validate)  # Result.ok(5)
```

### Asynchronous Methods

#### `async amap(func: Callable[[T], Awaitable[U]]) -> Result[U]`
Transform the value with an async function.

```python
async def fetch_data(id: str) -> dict:
    # Async operation
    return {"id": id, "name": "Example"}

result = Result.ok("123")
data = await result.amap(fetch_data)  # Result.ok({"id": "123", ...})
```

#### `async aflat_map(func: Callable[[T], Awaitable[Result[U]]]) -> Result[U]`
Chain async operations that return Results.

```python
async def fetch_user(id: str) -> Result[User]:
    user = await db.get_user(id)
    return Result.ok(user) if user else Result.fail(not_found_error())

result = Result.ok("user123")
user = await result.aflat_map(fetch_user)
```

## Service Layer Patterns

### Pattern 1: Simple Transformation

**Before (if/else)**:
```python
async def get_journal_for_date(self, target_date: date) -> Result[Optional[Report]]:
    journals_result = await self.backend.find_by_date(target_date)
    if journals_result.is_error:
        return journals_result

    journals = journals_result.value
    if journals:
        return Result.ok(journals[0])
    return Result.ok(None)
```

**After (chaining)**:
```python
async def get_journal_for_date(self, target_date: date) -> Result[Optional[Report]]:
    result = await self.backend.find_by_date(target_date)
    return result.map(lambda journals: journals[0] if journals else None)
```

### Pattern 2: Conditional Processing

**Before (if/else)**:
```python
async def get_events_by_day(self, target_date: date, include_all_day: bool = True) -> Result[list[EventPure]]:
    result = await self.get_events_by_date_range(target_date, target_date + timedelta(days=1))

    if result.is_ok and not include_all_day:
        events = [e for e in result.value if not e.all_day]
        return Result.ok(events)

    return result
```

**After (chaining)**:
```python
async def get_events_by_day(self, target_date: date, include_all_day: bool = True) -> Result[list[EventPure]]:
    result = await self.get_events_by_date_range(target_date, target_date + timedelta(days=1))

    return result.map(
        lambda events: events if include_all_day
        else [e for e in events if not e.all_day]
    )
```

### Pattern 3: Multi-Step Operations

**Before (if/else)**:
```python
async def get_journal(self, uid: str) -> Result[Report]:
    get_result = await self.backend.get(uid)
    if get_result.is_error:
        return get_result

    journal = get_result.value
    if not journal:
        return Result.fail(not_found_error(f"Journal {uid} not found"))

    return Result.ok(journal)
```

**After (chaining)**:
```python
async def get_journal(self, uid: str) -> Result[Report]:
    result = await self.backend.get(uid)
    return await result.aflat_map(
        lambda journal: Result.ok(journal) if journal
        else Result.fail(not_found_error(f"Journal {uid} not found"))
    )
```

### Pattern 4: Complex Validation and Processing

**Before (if/else)**:
```python
async def create_journal(self, journal: Report) -> Result[Report]:
    # Check for duplicates
    if journal.occurred_at:
        existing_result = await self.backend.find_by_date(journal.occurred_at)
        if existing_result.is_error:
            return existing_result

        existing = existing_result.value
        if existing:
            for j in existing:
                if j.title == journal.title:
                    return Result.fail(validation_error("Duplicate"))

    # Create
    create_result = await self.backend.create(journal)
    if create_result.is_error:
        return create_result

    # Publish event
    created = create_result.value
    if self.event_bus:
        await self.event_bus.publish("journal.created", {...})

    return Result.ok(created)
```

**After (chaining)**:
```python
async def create_journal(self, journal: Report) -> Result[Report]:
    # Define validation as a function
    async def check_duplicates(j: Report) -> Result[Report]:
        if not j.occurred_at:
            return Result.ok(j)

        existing_result = await self.backend.find_by_date(j.occurred_at)
        if existing_result.is_error:
            return existing_result

        existing = existing_result.value
        if existing:
            for existing_journal in existing:
                if existing_journal.title == j.title:
                    return Result.fail(validation_error("Duplicate"))
        return Result.ok(j)

    # Chain operations
    result = await check_duplicates(journal)
    if result.is_error:
        return result

    result = await result.aflat_map(self.backend.create)

    # Side effects on success
    if result.is_ok and self.event_bus:
        created = result.value
        await self.event_bus.publish("journal.created", {...})

    return result
```

### Pattern 5: Cascading Operations

**After (chaining)**:
```python
async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
    # Define cascading delete
    async def delete_with_cascade(_) -> Result[bool]:
        if cascade:
            subtasks_result = await self.backend.get_subtasks(uid)
            if subtasks_result.is_ok:
                for subtask in subtasks_result.value:
                    await self.backend.delete_task(subtask.uid)

        return await self.backend.delete_task(uid)

    # Start with success then chain
    return await Result.ok(None).aflat_map(delete_with_cascade)
```

## Best Practices

### DO ✅

1. **Use `map()` for simple transformations**
   ```python
   result.map(lambda x: x * 2)
   ```

2. **Use `flat_map()`/`aflat_map()` when chaining Results**
   ```python
   result.aflat_map(lambda x: backend.fetch(x))
   ```

3. **Define complex logic as named functions**
   ```python
   async def validate_and_process(data):
       # Complex logic here
       return Result.ok(processed)

   result.aflat_map(validate_and_process)
   ```

4. **Handle side effects after chaining**
   ```python
   result = await chain_of_operations()
   if result.is_ok:
       await publish_event(result.value)
   return result
   ```

### DON'T ❌

1. **Don't mix if/else with chaining**
   ```python
   # Bad
   if result.is_error:
       return result
   return result.map(transform)

   # Good
   return result.map(transform)
   ```

2. **Don't nest lambdas deeply**
   ```python
   # Bad
   result.map(lambda x: process(transform(validate(x))))

   # Good - use separate functions or chain
   result.map(validate).map(transform).map(process)
   ```

3. **Don't forget async in aflat_map**
   ```python
   # Bad
   result.aflat_map(backend.fetch)  # Missing await

   # Good
   await result.aflat_map(backend.fetch)
   ```

## Migration Guide

To migrate existing if/else patterns:

1. **Identify error checking patterns**
   - Look for: `if result.is_error: return result`

2. **Replace with appropriate chaining**
   - Simple transform: Use `map()`
   - Async transform: Use `amap()`
   - Result-returning: Use `flat_map()` or `aflat_map()`

3. **Extract complex logic**
   - Move multi-line if/else blocks into named functions
   - Chain the named functions

4. **Handle side effects last**
   - Perform all transformations first
   - Apply side effects after checking `result.is_ok`

## Examples from SKUEL Services

### journal_core_service.py
- Uses `aflat_map()` for backend operations
- Validates duplicates with custom async functions
- Handles events after successful operations

### tasks_service.py
- Chains update operations with validation
- Cascading deletes using `aflat_map()`

### events_service.py
- Simple filtering with `map()`
- Conditional transformations in lambdas

### habits_service.py
- Complex streak calculations in named functions
- Goal updates as side effects after success

## Summary

Result chaining in SKUEL provides:
- **Cleaner code**: No nested if/else blocks
- **Better composition**: Operations chain naturally
- **Type safety**: Compiler ensures Result handling
- **Functional style**: Immutable transformations
- **One path forward**: Consistent error handling pattern

This aligns with SKUEL's philosophy of clean, maintainable code with a single clear path forward.