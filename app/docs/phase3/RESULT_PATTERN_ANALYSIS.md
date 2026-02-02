# Phase 3, Task 2: Result[T] Pattern for All Routes - Analysis

**Date:** 2026-02-02
**Plan Reference:** `/home/mike/.claude/plans/lively-greeting-meadow.md` - Phase 3, Task 2
**Estimated Time:** 12-16 hours

---

## Overview

Extend the Result[T] pattern from Activity domains (which have 100% coverage) to Curriculum, Content, and Infrastructure domains.

---

## Pattern Definition

### The Result[T] Pattern

**In Services/Helpers:**
```python
async def get_tasks_for_user(user_uid: str) -> Result[list[Task]]:
    """Fetch tasks - returns Result[T]."""
    try:
        tasks = await backend.find_by(user_uid=user_uid)
        return Result.ok(tasks)
    except Exception as e:
        logger.error(f"Failed to fetch tasks: {e}")
        return Result.fail(Errors.database(f"Could not load tasks: {e}"))
```

**In Routes:**
```python
@rt("/tasks")
async def tasks_page(request):
    """Render tasks page - checks .is_error."""
    user_uid = require_authenticated_user(request)

    # Call helper that returns Result[T]
    tasks_result = await get_tasks_for_user(user_uid)

    # Check for errors BEFORE accessing .value
    if tasks_result.is_error:
        return render_error_banner(tasks_result.error.message)

    # Safe to access .value
    tasks = tasks_result.value
    return render_tasks_list(tasks)
```

### Key Characteristics

1. **Services return Result[T]** - Not raw values or exceptions
2. **Routes check `.is_error`** - Before accessing `.value`
3. **User-friendly errors** - Via `render_error_banner()` or similar
4. **Type safety** - `Result.ok(value)` or `Result.fail(error)`

---

## Current State Analysis

### ✅ Activity Domains (100% Coverage)

| Domain | File | Status | Notes |
|--------|------|--------|-------|
| Tasks | `tasks_ui.py` | ✅ Full | Complete Result[T] pattern |
| Goals | `goals_ui.py` | ✅ Full | Complete Result[T] pattern |
| Habits | `habits_ui.py` | ✅ Full | Complete Result[T] pattern |
| Events | `events_ui.py` | ✅ Full | Complete Result[T] pattern |
| Choices | `choice_ui.py` | ✅ Full | Complete Result[T] pattern |
| Principles | `principles_ui.py` | ✅ Full | Complete Result[T] pattern |

### ❓ Curriculum Domains (Unknown Coverage)

| Domain | File | Status | Analysis Needed |
|--------|------|--------|-----------------|
| KU (Knowledge) | `knowledge_ui.py`, `knowledge_api.py` | ❓ | Check service calls |
| LS (Learning Steps) | `learning_ui.py`, `learning_steps_api.py` | ❓ | Check service calls |
| LP (Learning Paths) | `learning_ui.py`, `learning_api.py` | ❓ | Check service calls |

### ❓ Content Domains (Unknown Coverage)

| Domain | File | Status | Analysis Needed |
|--------|------|--------|-----------------|
| Journals | `journals_ui.py`, `journals_api.py` | ❓ | Check service calls |
| Assignments | `assignments_ui.py` | ❓ | Check service calls |
| Transcriptions | `transcription_ui.py` | ❓ | Check service calls |

### ❓ Infrastructure (Unknown Coverage)

| Domain | File | Status | Analysis Needed |
|--------|------|--------|-----------------|
| User/Profile | `user_profile_ui.py` | ❓ | Check service calls |
| Reports | `reports_ui.py` | ❓ | Check service calls |
| Calendar | `calendar_routes.py` | ❓ | Check service calls |
| Search | `search_ui.py` | ❓ | Check service calls |
| Askesis | `askesis_ui.py` | ❓ | Check service calls |

---

## Analysis Strategy

For each domain, check:

1. **Service layer** - Do methods return `Result[T]`?
2. **Route layer** - Do routes check `.is_error` before `.value`?
3. **Error handling** - Are errors rendered with user-friendly messages?

### Analysis Questions

1. Does the service method return `Result[T]`?
   - ✅ Yes → Route just needs to check `.is_error`
   - ❌ No → Service needs refactoring

2. Does the route check `.is_error`?
   - ✅ Yes → Pattern already implemented
   - ❌ No → Route needs error handling added

3. Are errors user-friendly?
   - ✅ Yes → Uses `render_error_banner()` or similar
   - ❌ No → Error rendering needs improvement

---

## Implementation Approach

### Step 1: Analyze Current State (2-3 hours)

For each domain:
- Read service method signatures
- Check if they return `Result[T]`
- Check if routes handle errors properly

### Step 2: Categorize Domains (1 hour)

Create three lists:
1. **Already compliant** - No changes needed
2. **Routes only** - Service returns Result[T], route needs error handling
3. **Full refactor** - Service needs Result[T], route needs error handling

### Step 3: Implement Changes (8-12 hours)

**For "Routes only" domains:**
- Add `.is_error` check before `.value`
- Add error rendering (e.g., `render_error_banner()`)

**For "Full refactor" domains:**
- Update service to return `Result[T]`
- Wrap try/except with Result.ok/fail
- Update all route callers

### Step 4: Testing (1-2 hours)

- Manual testing: Trigger errors, verify user-friendly messages
- Unit tests: Service methods return correct Result types

---

## Next Steps

1. **Analyze Knowledge (KU) domain** - Start with curriculum
2. **Analyze Learning (LS/LP) domain** - Continue curriculum
3. **Analyze Content domains** - Journals, Assignments
4. **Analyze Infrastructure** - User, Reports, Calendar

---

## Success Criteria

✅ All service methods return `Result[T]`
✅ All routes check `.is_error` before `.value`
✅ All errors rendered with user-friendly messages
✅ No raw exceptions bubbling to UI
✅ Type safety maintained (MyPy compliance)

---

## Related Documentation

- **Pattern Reference:** `/adapters/inbound/tasks_ui.py` (complete example)
- **Error Handling:** `/docs/patterns/ERROR_HANDLING.md`
- **Result[T] Guide:** `/.claude/skills/result-pattern/`
