---
title: Return Value Type Errors Analysis
updated: 2025-12-02
status: resolved
category: technical-debt
tags: [analysis, errors, return, technical-debt, value]
related: []
---

# Return Value Type Errors Analysis

**Status**: ✅ RESOLVED
**Error Count**: 0 [return-value] errors (down from 111)
**Last Updated**: 2025-12-02

## Resolution Summary (December 2, 2025)

All 111 return-value errors have been resolved through progressive fixes:

1. **Phase A Quick Wins** (Result[int] → Result[bool]): Already fixed prior to analysis
2. **Final 4 errors fixed** (December 2, 2025):
   - `curriculum_base_service.py:397` - Fixed fallback to unwrap Result before returning
   - `ku_service.py:225` - Fixed return type annotation to `Result[list[Any]]`
   - `ku_service.py:288` - Fixed error propagation with `Result.fail(result.expect_error())`
   - `ku_service.py:661` - Fixed return type annotation to `Result[list[Any]]`

---

## Historical Analysis (for reference)

## Overview

Return-value errors occur when a function's return statement doesn't match its declared return type. Unlike the backend infrastructure errors (MyPy limitations), these represent **genuine type mismatches** that should be fixed.

**Impact**: Low to Medium
- Tests pass (runtime types are compatible)
- Type safety reduced (callers can't trust return type annotations)
- Code clarity reduced (declared types don't match implementation)

## Error Categories

### Category 1: Result[int] vs Result[bool] ⚠️ HIGH PRIORITY
**Count**: 5 errors
**Pattern**: Boolean check methods returning counts instead of booleans

**Example**:
```python
# WRONG - Returns count
async def is_learning_task(self, task_uid: str) -> Result[bool]:
    count_result = await self.count_related(task_uid, "APPLIES_KNOWLEDGE")
    return count_result  # Result[int], not Result[bool]!

# CORRECT - Convert to boolean
async def is_learning_task(self, task_uid: str) -> Result[bool]:
    count_result = await self.count_related(task_uid, "APPLIES_KNOWLEDGE")
    if count_result.is_error:
        return count_result
    return Result.ok(count_result.value > 0)  # Convert int -> bool
```

**Files Affected**:
- `core/services/tasks/tasks_relationship_service.py`: Lines 1170, 1192, 1215, 1226, 1248
  - `is_learning_task()`: Returns knowledge count
  - `has_subtasks()`: Returns subtask count
  - `has_prerequisites()`: Returns prerequisite count
  - `has_dependents()`: Returns dependent count
  - `is_blocked()`: Returns blocker count

**Fix Complexity**: EASY
**Estimated Time**: 10 minutes (all in one file)
**Impact**: High (method names promise boolean, should deliver boolean)

---

### Category 2: Result[Entity] vs Result[dict] ⚠️ MEDIUM PRIORITY
**Count**: ~20 errors
**Pattern**: Methods returning domain entities when dict expected (or vice versa)

**Example**:
```python
# Declared return type suggests dict-based API
async def get_task_with_context(
    self, task_uid: str
) -> Result[dict[str, Any]]:
    task_result = await self.backend.get(task_uid)
    return task_result  # Result[Task], not Result[dict]!

# Two fix options:
# Option A: Update return type annotation (preferred)
async def get_task_with_context(
    self, task_uid: str
) -> Result[Task]:  # Match actual return
    task_result = await self.backend.get(task_uid)
    return task_result

# Option B: Convert to dict (if dict really needed)
async def get_task_with_context(
    self, task_uid: str
) -> Result[dict[str, Any]]:
    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return task_result
    return Result.ok(task_result.value.to_dto().to_dict())
```

**Common Sub-Patterns**:
- `Result[Task]` vs `Result[dict[str, Any]]` (15 occurrences)
- `Result[Task]` vs `Result[CalendarItem]` (5 occurrences - type hierarchy)
- `Result[list[T]]` vs `Result[dict[str, list[T]]]` (3 occurrences)

**Fix Complexity**: MEDIUM
**Estimated Time**: 1-2 hours (requires understanding caller expectations)
**Impact**: Medium (affects API contracts, but tests pass = runtime compatible)

---

### Category 3: Result[T] vs Result[tuple[T, Context]] 📊 LOW PRIORITY
**Count**: ~5 errors
**Pattern**: Methods missing GraphContext in return type

**Example**:
```python
# Declared with context
async def get_with_context(
    self, uid: str
) -> Result[tuple[Task, GraphContext]]:
    task_result = await self.backend.get(uid)
    return task_result  # Result[Task | None], missing context!

# Fix: Add context fetching
async def get_with_context(
    self, uid: str
) -> Result[tuple[Task, GraphContext]]:
    task_result = await self.backend.get(uid)
    if task_result.is_error:
        return task_result

    task = task_result.value
    if not task:
        return Result.fail(not_found_error(...))

    # Fetch context
    context = await self._build_context(task.uid)
    return Result.ok((task, context))
```

**Files Affected**:
- `core/services/tasks/tasks_relationship_service.py`
- `core/services/finance/finance_intelligence_service.py`

**Fix Complexity**: MEDIUM
**Estimated Time**: 30-60 minutes (need to implement context building)
**Impact**: Low (callers may not use context yet)

---

### Category 4: Result[T | None] vs Result[T] 🔍 MEDIUM PRIORITY
**Count**: ~10 errors
**Pattern**: Optional returns when non-optional declared

**Example**:
```python
# Declared non-optional
async def get_journal(self, uid: str) -> Result[JournalPure]:
    result = await self.backend.get(uid)
    return result  # Result[JournalPure | None]!

# Fix Option A: Update return type (if None is valid)
async def get_journal(self, uid: str) -> Result[JournalPure | None]:
    result = await self.backend.get(uid)
    return result

# Fix Option B: Convert None to error (if None is error case)
async def get_journal(self, uid: str) -> Result[JournalPure]:
    result = await self.backend.get(uid)
    if result.is_error:
        return result
    if not result.value:
        return Result.fail(not_found_error("Journal", uid))
    return Result.ok(result.value)
```

**Fix Complexity**: EASY
**Estimated Time**: 30 minutes
**Impact**: Medium (affects error handling assumptions)

---

### Category 5: Miscellaneous Type Mismatches 🔧 VARIOUS
**Count**: ~15 errors
**Pattern**: Various one-off type mismatches

**Examples**:
- `Result[list[EventLogEntry]]` vs `Result[str]` (export method)
- `Result[Lp]` vs `Result[list[Ls]]` (wrong entity type)
- `str | None` vs `str` (missing None handling)
- Missing return statement in comparison method

**Fix Complexity**: VARIES
**Estimated Time**: 2-3 hours (case-by-case analysis)
**Impact**: Low to Medium

---

## Fix Priority Recommendation

### Phase A: Quick Wins (1-2 hours total) ⭐
1. **Result[int] → Result[bool]** (5 errors, 10 minutes)
   - File: `tasks_relationship_service.py`
   - Methods: `is_learning_task`, `has_subtasks`, `has_prerequisites`, `has_dependents`, `is_blocked`
   - Fix: `return Result.ok(count_result.value > 0)`

2. **Result[T | None] → Result[T]** (10 errors, 30 minutes)
   - Multiple files
   - Fix: Add None check + convert to not_found error

### Phase B: Medium Complexity (2-4 hours total) 📋
3. **Result[Entity] vs Result[dict]** (20 errors, 2 hours)
   - Requires understanding caller expectations
   - Fix: Update type annotation OR convert entity to dict

4. **Result[T] vs Result[tuple[T, Context]]** (5 errors, 1 hour)
   - Requires implementing context building
   - Lower priority (functionality works without context)

### Phase C: Case-by-Case (2-3 hours) 🔍
5. **Miscellaneous Mismatches** (15 errors, 2-3 hours)
   - Each requires individual analysis
   - Some may be legitimate changes in API design

---

## Architectural Considerations

### Why Tests Pass Despite Type Errors

1. **Runtime Type Compatibility**: `int` is truthy/falsy like `bool`, `Task` has dict-like properties
2. **Duck Typing**: Python doesn't enforce static types at runtime
3. **Result Monad**: Wraps all types uniformly, hides mismatches

### Why Fix Anyway?

1. **Type Safety**: Callers depend on type annotations for correctness
2. **Code Clarity**: Annotations should match implementation
3. **IDE Support**: Better autocomplete and error detection
4. **Future Refactoring**: Type-safe refactoring tools require accurate types

---

## Comparison with Other Error Categories

| Category | Count | Fix Time | Impact | Status |
|----------|-------|----------|--------|--------|
| **Graph-Native Debt** | 25 | 2 hours | High | ✅ FIXED (Phase 1) |
| **Enum/Optional** | 7 | 30 mins | Medium | ✅ FIXED (Phase 2) |
| **Backend Infrastructure** | 46 | N/A | None | ✅ DOCUMENTED (Phase 3) |
| **Return Value** | 111→0 | Progressive | Medium | ✅ RESOLVED (Phase 4) |

---

## Implementation Strategy

### Quick Win Candidates (Do First)
- **5 Result[int] → Result[bool] fixes**: Highest ROI, lowest effort
- All in single file, clear pattern, high impact on API correctness

### Progressive Enhancement
1. Fix quick wins (Phase A) - validate approach
2. Document remaining errors with fix strategies
3. Fix Medium complexity (Phase B) when touching those files
4. Address miscellaneous (Phase C) opportunistically

### Don't Fix Yet
- Backend infrastructure errors (MyPy limitations, documented)
- Errors in archived/deprecated code
- Errors where fixing breaks more than it helps

---

## Monitoring

**When to Revisit**:
- When modifying files with return-value errors (fix opportunistically)
- After completing Phase A (assess impact, decide on Phase B)
- When MyPy version updates (some may auto-resolve)

**Success Metrics**:
- Phase A: 111 → ~95 errors (-16, quick wins)
- Phase B: ~95 → ~70 errors (-25, medium complexity)
- Phase C: ~70 → ~40 errors (-30, case-by-case)

**Last Review**: 2025-11-17
**Next Review**: After Phase A completion
