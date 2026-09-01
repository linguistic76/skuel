---
title: Return Type Error Propagation Pattern
updated: 2026-06-11
category: patterns
related_skills:
- result-pattern
- ui-error-handling
related_docs: []
---
# Return Type Error Propagation Pattern
**Date**: 2025-12-05 (Updated)
**Status**: ✅ Implemented
## Related Skills

For implementation guidance, see:
- [@result-pattern](../../.claude/skills/result-pattern/SKILL.md)
- [@ui-error-handling](../../.claude/skills/ui-error-handling/SKILL.md)

## Core Principle

**"Use `Result.fail(result)` to propagate errors across Result[T] type boundaries"**

## The Problem

When a method returns `Result[A]` but needs to propagate an error to a caller expecting `Result[B]`, you cannot directly return the error result because of type mismatch.

### Example Scenarios

#### Scenario 1: Validation Hook Returns Wrong Type

```python
def _validate_create(self, entity: T) -> Result[None] | None:
    """Returns None if valid, Result[None] if invalid."""
    if entity.invalid:
        return Result.fail(Errors.validation("Invalid entity"))
    return None

async def create(self, entity: T) -> Result[T]:
    validation = self._validate_create(entity)
    if validation:
        return validation  # ❌ Returns Result[None], expects Result[T]
```

**MyPy Error:**
```
error: Incompatible return value type (got "Result[None]", expected "Result[T]")
```

#### Scenario 2: Error from Helper Method

```python
async def calculate_score(self, user_uid: UserUID, knowledge_uid: str) -> Result[float]:
    profile_result = await self.build_user_knowledge_profile(user_uid)
    if profile_result.is_error:
        return profile_result  # ❌ Returns Result[UserKnowledgeProfile], expects Result[float]
```

#### Scenario 3: Persistence Error Propagation

```python
async def create_path(...) -> Result[Lp]:
    path = Lp(...)

    persist_result = await self._persist_path(path, user_uid)
    if persist_result.is_error:
        return persist_result  # ❌ Returns Result[bool], expects Result[Lp]
```

## The Solution: `Result.fail(result)` Pattern

`Result.fail()` accepts another Result object directly for clean error propagation:

```python
# ✅ PREFERRED - Pass the Result directly
if result.is_error:
    return Result.fail(result)
```

`Result.fail()` internally calls `.expect_error()` to extract the `ErrorContext`, so you never need to call `.expect_error()` for propagation. Reserve `.expect_error()` for when you need to _read_ the error (e.g., logging, branching on category).

### Fixed Examples

#### Fix 1: BaseService Validation Hook

**File**: `core/services/base_service.py:373`

```python
# BEFORE
async def create(self, entity: T) -> Result[T]:
    validation = self._validate_create(entity)
    if validation:
        return validation  # ❌ Result[None] → Result[T] mismatch

# AFTER
async def create(self, entity: T) -> Result[T]:
    validation = self._validate_create(entity)
    if validation:
        return Result.fail(validation)  # Result[None] → Result[T]
```

#### Fix 2: Helper Error Across a Type Boundary

(Pattern example — the original `UserProgressService` site was deleted in the 2026-06 user dead-code campaign; `build_user_knowledge_profile` remains live.)

```python
# BEFORE
async def calculate_score(...) -> Result[float]:
    profile_result = await self.build_user_knowledge_profile(user_uid)
    if profile_result.is_error:
        return profile_result  # ❌ Result[UserKnowledgeProfile] → Result[float]

# AFTER
async def calculate_score(...) -> Result[float]:
    profile_result = await self.build_user_knowledge_profile(user_uid)
    if profile_result.is_error:
        return Result.fail(profile_result)  # Result[Profile] → Result[float]
```

#### Fix 3: LpCoreService Persistence Error

**File**: `core/services/lp/lp_core_service.py:204`

```python
# BEFORE
async def create_path(...) -> Result[Lp]:
    persist_result = await self._persist_path(path, user_uid)
    if persist_result.is_error:
        return persist_result  # ❌ Result[bool] → Result[Lp]

# AFTER
async def create_path(...) -> Result[Lp]:
    persist_result = await self._persist_path(path, user_uid)
    if persist_result.is_error:
        return Result.fail(persist_result)  # Result[bool] → Result[Lp]
```

## Why `Result.fail(result)` Works

`Result.fail()` accepts three argument types:
- `ErrorContext` — direct error
- `str` — creates a SYSTEM error
- `Result[Any]` — extracts the error via `.expect_error()` internally

This means `Result.fail(result)` does the `.expect_error()` extraction for you. The method is still available for cases where you need to _read_ the error:

```python
# Reading error details (logging, branching)
if result.is_error:
    error = result.expect_error()  # Type: ErrorContext (guaranteed)
    logger.error(f"Failed: {error.message}")
    match error.category:
        case ErrorCategory.NOT_FOUND: ...

# Propagating errors — just pass the Result directly
if result.is_error:
    return Result.fail(result)  # ✅ Preferred
```

## Pattern Recognition

Use `Result.fail(result)` when:

1. **Early return on error** - Propagating error from helper method
   ```python
   result = await helper_method()
   if result.is_error:
       return Result.fail(result)  # Clean propagation
   ```

2. **Validation hooks** - Converting validation errors to correct type
   ```python
   validation = self._validate_create(entity)
   if validation:
       return Result.fail(validation)
   ```

3. **Cross-boundary errors** - Passing errors across Result[A] → Result[B] boundaries
   ```python
   persist_result = await self._persist(entity)
   if persist_result.is_error:
       return Result.fail(persist_result)
   ```

## Tuple Unpacking for list() Methods

The `list()` method returns `tuple[list[T], int]` (items + total count). Always unpack:

```python
# ❌ WRONG - Treats tuple as list
list_result = await self.backend.list(filters={"user_uid": user_uid})
if list_result.is_error:
    return Result.fail(list_result)
entities = list_result.value  # This is tuple[list[T], int], not list[T]!

# ✅ CORRECT - Unpack the tuple
list_result = await self.backend.list(filters={"user_uid": user_uid})
if list_result.is_error:
    return Result.fail(list_result)
entities, total = list_result.value  # Properly unpacked
```

## Anti-Patterns to Avoid

```python
# ❌ WRONG - Using assert for type narrowing
if result.is_error:
    assert result.error is not None  # MyPy doesn't narrow types!
    return Result.fail(result.error)  # Still Optional[ErrorContext] to MyPy

# ❌ VERBOSE - Redundant .expect_error() for propagation (migrated 2026-03-25, 834 sites)
if result.is_error:
    return Result.fail(result.expect_error())  # Works but unnecessary

# ✅ CORRECT - Pass the Result directly
if result.is_error:
    return Result.fail(result)  # Clean, concise, type-safe

# ❌ WRONG - Redundant re-wrapping when no transformation needed
result = await self.backend.operation(uid)
if result.is_error:
    return result
return Result.ok(result.value)  # Just return result directly

# ❌ WRONG - Re-wrapping error as Errors.system() at route boundary (loses original category)
if result.is_error:
    error = result.error
    return Result.fail(Errors.system(message=error.message))  # NOT_FOUND becomes SYSTEM/500!

# ✅ CORRECT - Let @boundary_handler map error categories to HTTP status codes
if result.is_error:
    return Result.fail(result)  # Original category preserved (NOT_FOUND → 404, etc.)

# ✅ CORRECT - Use require_found() for get + null-check pattern
return require_found(await self.backend.get(uid), "Entity", uid)
```

## Benefits Achieved

| Aspect | Result |
|--------|--------|
| **Type Safety** | ✅ MyPy validates error propagation correctly |
| **No Assertions** | ✅ Explicit method eliminates type narrowing hacks |
| **Runtime Safety** | ✅ Raises clear error if misused (calling on Ok) |
| **Code Clarity** | ✅ Single line instead of assert + return |
| **Pattern Enforcement** | ✅ Linter (SKU005) detects unsafe assert pattern |

## Verification

**Files Fixed** (November 7, 2025):
- `core/services/base_service.py` (lines 373, 407)
- `core/services/user_progress_service.py` (line 273)
- `core/services/lp/lp_core_service.py` (line 204)

**MyPy Verification:**
```bash
$ uv run mypy core/services/base_service.py
# No errors on lines 373, 407 ✅

$ uv run mypy core/services/user_progress_service.py
# No error on line 273 ✅

$ uv run mypy core/services/lp/lp_core_service.py
# No error on line 204 ✅
```

## Related Patterns

- **Result[T] Pattern** - Type-safe error handling
- **@boundary_handler** - Converts Results to HTTP responses
- **Error Factories** - Structured error creation (`Errors.validation()`, etc.)
- **SKU005 Linter Rule** - Detects unsafe `assert result.error` pattern

## References

- Result implementation: `/core/utils/result_simplified.py:181-206`
- Error handling docs: `/home/mike/0bsidian/skuel/docs/patterns/error_handling.md`
- SKUEL linter: `/scripts/lint_skuel_patterns.py`
- CLAUDE.md section: "Error Handling"
