# Service Layer Refactoring Analysis
*Generated: 2026-01-25*

## Summary

Analyzed 44 route files in `/adapters/inbound/` for anti-patterns similar to those found in `context_aware_api.py`.

**Key Finding:** Most route files follow clean patterns with thin controllers. Found **3 files with significant anti-patterns** that would benefit from refactoring.

---

## Anti-Patterns Identified

### Pattern 1: Business Logic in Helper Functions
Helper functions in route files that perform calculations, transformations, or business logic.

### Pattern 2: Manual Dictionary Assembly
Routes that manually build complex response dictionaries instead of using service methods.

### Pattern 3: Complex Data Processing in Routes
Routes with extensive data filtering, aggregation, or calculation logic.

---

## Files Requiring Refactoring (Priority Order)

### 🔴 HIGH PRIORITY

#### 1. `/adapters/inbound/visualization_routes.py`
**Lines:** 574 total
**Anti-Patterns:** All 3 patterns present
**Severity:** HIGH

**Issues:**

**A. Business Logic in Helper Functions (lines 550-575)**
```python
def _task_due_on(task: Any, d: date) -> bool:
    """Check if task is due on specific date."""
    due = getattr(task, "due_date", None)
    scheduled = getattr(task, "scheduled_date", None)
    return (due == d) or (scheduled == d)

def _task_in_range(task: Any, start: date, end: date) -> bool:
    """Check if task falls within date range."""
    # Date range business logic

def _is_completed(task: Any) -> bool:
    """Check if task is completed."""
    # Status checking business logic
```

**B. Complex Data Processing in Routes**

**Route: `/api/visualizations/completion` (lines 68-132)**
- 64 lines of date calculation and task filtering logic
- Nested conditionals for week/month/quarter periods
- Iterating through tasks to calculate completion rates
- Business logic: determining which period bucket a task belongs to

```python
# Lines 98-120 (excerpt)
if period == "week":
    for i in range(7):
        d = start_date + timedelta(days=i)
        day_tasks = [t for t in tasks if _task_due_on(t, d)]
        day_completed = [t for t in day_tasks if _is_completed(t)]
        total.append(len(day_tasks))
        completed.append(len(day_completed))
elif period == "month":
    for i in range(0, 30, 3):
        # ... more calculation logic
```

**Route: `/api/visualizations/priority-distribution` (lines 146-178)**
- Lines 146-159: Priority distribution calculation
- Dict building with enum conversion

**Route: `/api/visualizations/streaks` (lines 194-222)**
- Lines 194-206: Streak data extraction and transformation

**Route: `/api/visualizations/status-distribution` (lines 236-268)**
- Lines 236-251: Status distribution calculation

**Recommended Refactoring:**
1. Move helper functions to `VisualizationService`
2. Create service methods:
   - `get_completion_data(user_uid, period, start_date, end_date)` → Returns completed/total arrays
   - `get_priority_distribution(user_uid)` → Returns distribution dict
   - `get_streak_data(user_uid)` → Returns streak list
   - `get_status_distribution(user_uid, days_back)` → Returns distribution dict
3. Routes become 3-5 line pass-throughs calling service + formatting

**Impact:** ~150 lines moved from routes → service

---

#### 2. `/adapters/inbound/assignments_api.py`
**Lines:** 586 total
**Anti-Pattern:** Business logic in helper function
**Severity:** HIGH

**Issue:**

**Helper Function: `_assignment_to_dict()` (lines 561-585)**
- 25 lines of transformation logic
- Converts Assignment domain model to API response dict
- Field mapping, type conversions, conditional formatting
- **Used in 5+ routes** throughout the file

```python
def _assignment_to_dict(assignment) -> dict[str, Any]:
    """Convert Assignment to dictionary for JSON response"""
    return {
        "uid": assignment.uid,
        "user_uid": assignment.user_uid,
        "assignment_type": assignment.assignment_type.value,
        "status": assignment.status.value,
        "original_filename": assignment.original_filename,
        "file_size": assignment.file_size,
        "file_type": assignment.file_type,
        "processor_type": assignment.processor_type.value,
        "processing_started_at": assignment.processing_started_at.isoformat()
        if assignment.processing_started_at
        else None,
        # ... 10+ more fields
    }
```

**Recommended Refactoring:**
1. Create `assignment_converters.py` following the pattern in `journal_converters.py`
2. Move `_assignment_to_dict()` to `assignment_dto_to_response()` converter
3. Use consistent converter pattern across codebase

**Precedent:** Journals domain already follows this pattern:
- `core/models/journal/journal_converters.py`
- Uses `journal_dto_to_response()` instead of route helpers

**Impact:** 25 lines moved from routes → converters module

---

### 🟡 MEDIUM PRIORITY

#### 3. `/adapters/inbound/search_routes.py`
**Lines:** ~500+ total
**Anti-Pattern:** Extensive parameter validation/transformation in routes
**Severity:** MEDIUM (borderline acceptable)

**Issues:**

**A. Helper Functions for Parameter Cleaning (lines 69-77)**
```python
def _none_if_empty(value: str | None) -> str | None:
    """Convert empty strings to None."""
    return None if not value or value.strip() == "" else value

def _checkbox_to_bool(value: str | None) -> bool:
    """Convert checkbox values to boolean."""
    return value == "true" if value else False
```

**B. Extensive Parameter Processing in Route (lines 157-243)**
- Lines 157-183: Cleaning 15+ filter parameters
- Lines 186-202: Building extended_facets dict
- Lines 204-243: SearchRequest construction with complex enum conversions

```python
# Lines 157-168 (excerpt)
entity_type = _none_if_empty(entity_type)
status = _none_if_empty(status)
priority = _none_if_empty(priority)
frequency = _none_if_empty(frequency)
event_type = _none_if_empty(event_type)
urgency = _none_if_empty(urgency)
strength = _none_if_empty(strength)
sel_category = _none_if_empty(sel_category)
learning_level = _none_if_empty(learning_level)
content_type = _none_if_empty(content_type)
educational_level = _none_if_empty(educational_level)
nous_section = _none_if_empty(nous_section)
```

**Discussion:**
This is **borderline acceptable** because:
- ✅ Parameter validation/parsing often lives in routes (HTTP boundary)
- ✅ Pydantic request models could handle this, but search has 20+ optional params
- ⚠️ However, the pattern is repetitive and could be simplified

**Recommended Refactoring (Optional):**
1. Create a `SearchRequestBuilder` helper class
2. Use Pydantic request model with custom validators
3. Or accept as-is since it's parameter handling, not business logic

**Impact:** Lower priority - functional boundary logic

---

## Files That Are Clean ✅

### Well-Architected Route Files

**`journals_api.py`:**
- ✅ Simple helper for sorting (`_get_journal_entry_date()`)
- ✅ Uses converters: `journal_dto_to_response()`, `journal_pure_to_dto()`
- ✅ Thin routes that pass through to service

**`system_api.py`:**
- ✅ No helper functions
- ✅ Simple dict assembly for HTTP responses (not business logic)
- ✅ Clean boundary_handler usage

**`ai_routes.py`:**
- ✅ One helper for error responses (`_ai_unavailable_response()`)
- ✅ Thin pass-throughs to AI services
- ✅ Consistent pattern across all routes

**`context_aware_api.py` (after refactoring):**
- ✅ Now follows thin-controller pattern
- ✅ Business logic moved to service
- ✅ Routes are 3-line pass-throughs

---

## Refactoring Recommendations

### Implementation Order

**Phase 1: High-Impact Fixes**
1. ✅ **COMPLETED:** `context_aware_api.py` - Refactored (2026-01-25)
2. **NEXT:** `visualization_routes.py` - ~150 lines of business logic to move
3. **THEN:** `assignments_api.py` - Create converter pattern

**Phase 2: Optional Cleanup**
4. **Optional:** `search_routes.py` - Consider Pydantic request model

### Estimated Effort

| File | Lines to Move | Complexity | Time Estimate |
|------|---------------|------------|---------------|
| visualization_routes.py | ~150 lines | Medium-High | 45-60 min |
| assignments_api.py | ~25 lines | Low | 15-30 min |
| search_routes.py | ~90 lines | Medium | 30-45 min (if done) |

### Success Criteria

**After refactoring, all routes should:**
- ✅ Be 3-10 lines max
- ✅ Only handle: auth, param validation, service call, return result
- ✅ Use `@boundary_handler()` for consistent error handling
- ✅ No business logic calculations
- ✅ No manual dict assembly beyond simple HTTP formatting

---

## Architecture Patterns to Follow

### ✅ GOOD: Thin Controller Pattern

```python
@rt("/api/context/health")
@boundary_handler()
async def get_context_health_route(request: Request, user_uid: str) -> Result[Any]:
    """Get overall context system health metrics."""
    return await context_service.get_context_health(user_uid)
```

### ❌ BAD: Business Logic in Routes

```python
@rt("/api/visualizations/completion")
async def get_completion_chart(request: Request) -> JSONResponse:
    """Get task completion rate data."""
    # ... 60 lines of date calculations, filtering, and aggregation
    for i in range(7):
        d = start_date + timedelta(days=i)
        day_tasks = [t for t in tasks if _task_due_on(t, d)]
        day_completed = [t for t in day_tasks if _is_completed(t)]
        # ... more logic
```

---

## Key Takeaways

1. **Most route files are clean** - Only 3 of 44 files need refactoring
2. **Visualization routes are the biggest offender** - Contains extensive business logic
3. **Assignments should use converters** - Follow journals pattern
4. **Search parameter handling is borderline** - Could be improved but not critical

---

## Next Steps

1. Review this analysis with the team
2. Decide priority: Fix visualization_routes.py next?
3. Create plan for assignments_api.py converter refactoring
4. Determine if search_routes.py parameter handling needs optimization
