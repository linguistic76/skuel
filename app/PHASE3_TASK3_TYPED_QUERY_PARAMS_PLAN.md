# Phase 3, Task 3: Typed Query Parameters - Implementation Plan

**Date:** 2026-02-02
**Plan Reference:** `/home/mike/.claude/plans/lively-greeting-meadow.md` - Phase 3, Task 3
**Status:** ✅ **COMPLETE** - See `/home/mike/skuel/app/PHASE3_TASK3_TYPED_QUERY_PARAMS_COMPLETE.md`

**Update (2026-02-02):**
- ✅ All 8 files implemented (knowledge, moc, user_profile, insights_history, assignments, journal_projects, insights, reports)
- ✅ 11 dataclasses created, 11 parser functions added
- ✅ 13 routes updated with typed parameters
- ✅ All files have valid Python syntax
- ⏸️ Manual testing pending
- **Time Invested:** ~6 hours (within 6-8 hour estimate)
- **Ready for:** Phase 3, Task 4 (Component Variant System)

---

## Overview

Replace raw `request.query_params.get()` calls with typed `@dataclass` parameters for type safety, IDE autocomplete, and testability across all UI route files.

---

## Pattern Definition

### Current Anti-Pattern
```python
@rt("/knowledge/filter")
async def knowledge_filter_fragment(request) -> Any:
    params = dict(request.query_params)
    domain_filter = params.get("domain", "all")  # No type safety, typos possible
    # ... use domain_filter
```

### Desired Pattern (from tasks_ui.py)
```python
@dataclass
class KnowledgeFilters:
    """Typed filters for knowledge unit queries."""
    domain: str
    complexity: str
    sort_by: str

def parse_knowledge_filters(request: Request) -> KnowledgeFilters:
    """Extract filter parameters from request query params."""
    return KnowledgeFilters(
        domain=request.query_params.get("domain", "all"),
        complexity=request.query_params.get("complexity", "all"),
        sort_by=request.query_params.get("sort_by", "created_at"),
    )

@rt("/knowledge/filter")
async def knowledge_filter_fragment(request) -> Any:
    filters = parse_knowledge_filters(request)  # Type-safe!
    # IDE knows: filters.domain, filters.complexity, filters.sort_by
    # ... use filters.domain
```

---

## Benefits

1. **Type Safety** - MyPy catches typos (`filters.domain` vs `filters.doamin`)
2. **IDE Autocomplete** - IntelliSense shows available fields
3. **Testability** - Create `Filters` directly without mocking `Request`
4. **Documentation** - Dataclass shows what params a route accepts
5. **Default Values** - Centralized in parser function
6. **Validation** - Can add validation logic in parser

---

## Current State Analysis

### ✅ Already Implemented (6 files)

| File | Dataclasses | Status |
|------|-------------|--------|
| `tasks_ui.py` | `Filters`, `CalendarParams` | ✅ Complete reference implementation |
| `goals_ui.py` | `Filters`, `CalendarParams` | ✅ Complete |
| `habits_ui.py` | `Filters`, `CalendarParams` | ✅ Complete |
| `events_ui.py` | `Filters`, `CalendarParams` | ✅ Complete |
| `choice_ui.py` | `Filters` | ✅ Complete |
| `principles_ui.py` | `Filters` | ✅ Complete |

**Pattern Consistency:** All 6 Activity domains use same naming convention (`Filters`, `CalendarParams`)

---

### ❌ Need Implementation (8 files)

| # | File | Query Params Used | Estimated Effort |
|---|------|-------------------|------------------|
| 1 | `knowledge_ui.py` | `domain` | 30 min (simple) |
| 2 | `moc_ui.py` | `domain` (likely) | 30 min (simple) |
| 3 | `user_profile_ui.py` | Unknown | 30 min |
| 4 | `assignments_ui.py` | 2 usages | 1 hour |
| 5 | `journal_projects_ui.py` | 2 usages | 1 hour |
| 6 | `insights_ui.py` | 2 usages | 1 hour |
| 7 | `insights_history_ui.py` | 1 usage | 30 min |
| 8 | `reports_ui.py` | 4 usages | 1.5 hours |

**Total Effort:** 6-8 hours (matches plan estimate)

---

## Implementation Strategy

### Phase 1: Simple Files (2-3 hours)

Start with files that have simple, single-purpose filters:

1. **knowledge_ui.py** (30 min)
   - Params: `domain` filter
   - Dataclass: `KnowledgeFilters`
   - Parser: `parse_knowledge_filters()`

2. **moc_ui.py** (30 min)
   - Params: `domain` filter (likely same as knowledge)
   - Dataclass: `MocFilters`
   - Parser: `parse_moc_filters()`

3. **user_profile_ui.py** (30 min)
   - Need to analyze params used
   - Dataclass: `ProfileParams` or `ProfileFilters`

4. **insights_history_ui.py** (30 min)
   - Need to analyze params used
   - Dataclass: `InsightsHistoryParams`

### Phase 2: Medium Complexity Files (2-3 hours)

Files with multiple routes or filter types:

5. **assignments_ui.py** (1 hour)
   - 2 query_params usages
   - Dataclass: `AssignmentFilters`

6. **journal_projects_ui.py** (1 hour)
   - 2 query_params usages
   - Dataclass: `JournalProjectFilters`

7. **insights_ui.py** (1 hour)
   - 2 query_params usages
   - Dataclass: `InsightsFilters`

### Phase 3: Complex File (1.5-2 hours)

File with most query param usage:

8. **reports_ui.py** (1.5 hours)
   - 4 query_params usages
   - Multiple dataclasses likely needed:
     - `ReportFilters` - For report listing
     - `ReportParams` - For report viewing
     - `PeriodParams` - For time period selection

---

## Detailed Implementation Steps

### For Each File:

1. **Analyze** (5-10 min)
   - Find all `request.query_params` usages
   - Identify param names and default values
   - Group related params

2. **Create Dataclass** (10-15 min)
   - Define `@dataclass` with typed fields
   - Add docstring describing purpose
   - Use descriptive field names

3. **Create Parser** (10-15 min)
   - Implement `parse_*_filters(request)` function
   - Extract params with defaults
   - Add any validation/transformation logic

4. **Update Routes** (10-20 min)
   - Replace `params = dict(request.query_params)` with `filters = parse_*_filters(request)`
   - Replace `params.get("key")` with `filters.field`
   - Update all usages

5. **Verify** (5 min)
   - Run `poetry run python -m py_compile <file>`
   - Check MyPy passes (if applicable)
   - Visual code review

---

## Example: knowledge_ui.py Implementation

### Step 1: Analyze

Current code (line 432-433):
```python
params = dict(request.query_params)
domain_filter = params.get("domain", "all")
```

**Params identified:**
- `domain` - default "all"

### Step 2: Create Dataclass

```python
@dataclass
class KnowledgeFilters:
    """Typed filters for knowledge unit list queries."""
    domain: str
```

### Step 3: Create Parser

```python
def parse_knowledge_filters(request: Request) -> KnowledgeFilters:
    """Extract knowledge filter parameters from request query params."""
    return KnowledgeFilters(
        domain=request.query_params.get("domain", "all"),
    )
```

### Step 4: Update Route

```python
@rt("/knowledge/filter")
async def knowledge_filter_fragment(request) -> Any:
    """Return filtered knowledge fragment for HTMX updates"""
    from ui.patterns.error_banner import render_error_banner

    # Parse typed filters
    filters = parse_knowledge_filters(request)

    # Fetch real knowledge from service
    if ku_service and hasattr(ku_service, "core") and hasattr(ku_service.core, "backend"):
        result = await ku_service.core.list(limit=50)

        # Check for errors FIRST
        if result.is_error:
            return render_error_banner(
                "Unable to load knowledge units. Please try again later.",
                result.error.message
            )

        knowledge = result.value if result.value else []

        # Apply domain filter if specified
        if filters.domain and filters.domain != "all":
            knowledge = [
                k
                for k in knowledge
                if str(getattr(k, "domain", "")).upper() == filters.domain.upper()
            ]
    else:
        knowledge = []

    return (
        Div(
            *[KnowledgeUIComponents.render_knowledge_card(unit) for unit in knowledge],
            cls="space-y-3",
        )
        if knowledge
        else P("No knowledge units found for this domain", cls="text-center text-gray-500 py-8")
    )
```

---

## Naming Conventions

Follow established patterns from Activity domains:

### Dataclass Names
- **List filtering:** `{Domain}Filters` (e.g., `KnowledgeFilters`, `ReportFilters`)
- **View parameters:** `{Domain}Params` (e.g., `CalendarParams`, `ReportParams`)
- **General parameters:** `{Feature}Params` (e.g., `PeriodParams`, `ProfileParams`)

### Parser Names
- **Pattern:** `parse_{domain}_filters()` or `parse_{domain}_params()`
- **Examples:**
  - `parse_knowledge_filters()`
  - `parse_report_filters()`
  - `parse_period_params()`

### Field Names
- Use descriptive, snake_case field names
- Match query param names where logical
- Use `_filter` suffix for filter fields (e.g., `domain_filter`, `status_filter`)
- Use defaults that make sense (usually "all" for filters)

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| All 8 files have typed query params | 100% |
| MyPy passes on modified files | ✅ |
| No breaking changes to existing routes | ✅ |
| Consistent naming conventions | ✅ |
| Parser functions documented | ✅ |
| Dataclasses have docstrings | ✅ |

---

## Testing Strategy

### Type Checking
```bash
poetry run mypy adapters/inbound/knowledge_ui.py
poetry run mypy adapters/inbound/reports_ui.py
# ... etc
```

### Syntax Validation
```bash
poetry run python -m py_compile adapters/inbound/*.py
```

### Manual Testing
1. Visit each route with query params in browser
2. Verify filtering still works
3. Test with valid params, invalid params, missing params
4. Verify default values apply correctly

### Unit Testing (Optional)
```python
def test_parse_knowledge_filters():
    """Test knowledge filter parsing."""
    # Mock request
    class MockRequest:
        query_params = {"domain": "TECH"}

    filters = parse_knowledge_filters(MockRequest())
    assert filters.domain == "TECH"

def test_parse_knowledge_filters_defaults():
    """Test default values."""
    class MockRequest:
        query_params = {}

    filters = parse_knowledge_filters(MockRequest())
    assert filters.domain == "all"
```

---

## Time Estimate

| Phase | Files | Estimated Time |
|-------|-------|----------------|
| Phase 1: Simple files | 4 | 2-3 hours |
| Phase 2: Medium files | 3 | 2-3 hours |
| Phase 3: Complex file | 1 | 1.5-2 hours |
| Testing & verification | All | 1 hour |
| **Total** | **8 files** | **6-8 hours** |

**Matches plan estimate:** ✅

---

## Next Steps

1. **Start with knowledge_ui.py** (30 min) - Simple, well-understood params
2. **Continue with moc_ui.py** (30 min) - Similar to knowledge
3. **Tackle remaining files** in order of complexity
4. **Test thoroughly** - Ensure no breaking changes
5. **Document patterns** - Update skills/guides if needed

---

## Related Documentation

- **Reference Implementation:** `/adapters/inbound/tasks_ui.py` (lines 99-141)
- **Pattern Guide:** `/docs/patterns/TYPED_QUERY_PARAMS_PATTERN.md` (to be created)
- **Skills Guide:** `/.claude/skills/skuel-form-patterns/` (may need update)

---

## Ready to Implement

All analysis complete. Ready to begin implementation starting with knowledge_ui.py.
