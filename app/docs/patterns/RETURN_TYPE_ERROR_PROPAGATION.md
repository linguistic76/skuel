---
title: Return Type Error Propagation Pattern
updated: 2025-12-05
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

**"Use `.expect_error()` to propagate errors across Result[T] type boundaries"**

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
async def calculate_readiness_for_knowledge(
    self, user_uid: str, knowledge_uid: str
) -> Result[float]:
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
# ✅ PREFERRED - Pass the Result directly (cleanest)
if result.is_error:
    return Result.fail(result)

# ✅ ALSO CORRECT - Explicit extraction (equivalent)
if result.is_error:
    return Result.fail(result.expect_error())
```

The first form is preferred as it's more concise. Both produce identical behavior.

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
        # Validation failed: Result[None] → Result[T] with same error
        return Result.fail(validation.expect_error())
```

**Same pattern for `update()` at line 407:**
```python
async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
    validation = self._validate_update(current_result.value, updates)
    if validation:
        # Validation failed: Result[None] → Result[T] with same error
        return Result.fail(validation.expect_error())
```

#### Fix 2: UserProgressService Helper Error

**File**: `core/services/user_progress_service.py:273`

```python
# BEFORE
async def calculate_readiness_for_knowledge(...) -> Result[float]:
    profile_result = await self.build_user_knowledge_profile(user_uid)
    if profile_result.is_error:
        return profile_result  # ❌ Result[UserKnowledgeProfile] → Result[float]

# AFTER
async def calculate_readiness_for_knowledge(...) -> Result[float]:
    profile_result = await self.build_user_knowledge_profile(user_uid)
    if profile_result.is_error:
        # Error building profile: Result[UserKnowledgeProfile] → Result[float]
        return Result.fail(profile_result.expect_error())
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
        # Persistence failed: Result[bool] → Result[Lp] with same error
        return Result.fail(persist_result.expect_error())
```

## Why `.expect_error()` Works

The `.expect_error()` method:
1. **Returns `ErrorContext`** (not `ErrorContext | None`) - eliminates MyPy union errors
2. **Raises `ValueError`** if called on Ok result (defensive programming)
3. **Type-safe** - MyPy knows the return type is `ErrorContext`
4. **Semantic** - Explicitly states "I expect this to be an error"

**Implementation**: `/core/utils/result_simplified.py:181-206`

```python
class Result[T]:
    def expect_error(self) -> ErrorContext:
        """
        Extract error from failed Result - type-safe error propagation.

        Returns:
            ErrorContext (not Optional!) - guaranteed non-None

        Raises:
            ValueError: If result is Ok (misuse detection)
        """
        if self.is_ok:
            raise ValueError("Called expect_error() on Ok result")

        if self.error is None:
            raise ValueError("Result is error but error is None (corrupted state)")

        return self.error  # Type: ErrorContext (not Optional!)
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

## Anti-Pattern to Avoid

```python
# ❌ WRONG - Using assert for type narrowing
if result.is_error:
    assert result.error is not None  # MyPy doesn't narrow types!
    return Result.fail(result.error)  # Still Optional[ErrorContext] to MyPy

# ✅ CORRECT - Use .expect_error()
if result.is_error:
    return Result.fail(result.expect_error())  # Returns ErrorContext (not Optional!)
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
- CLAUDE.md section: "Type-Safe Error Access with .expect_error()"
