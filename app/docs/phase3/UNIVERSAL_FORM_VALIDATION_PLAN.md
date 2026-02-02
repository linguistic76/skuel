# Phase 3, Task 1: Universal Early Form Validation - Implementation Plan

**Date:** 2026-02-02
**Phase:** Pattern Standardization
**Estimated Time:** 8-12 hours

---

## Overview

Apply the `validate_{domain}_form_data()` pattern to ALL domains, ensuring consistent early validation with user-friendly error messages.

---

## Current State

### ✅ Completed Domains (6)

| Domain | File | Status |
|--------|------|--------|
| Tasks | `tasks_ui.py` | ✅ Has `validate_task_form_data()` |
| Goals | `goals_ui.py` | ✅ Has `validate_goal_form_data()` |
| Habits | `habits_ui.py` | ✅ Has `validate_habit_form_data()` |
| Events | `events_ui.py` | ✅ Has `validate_event_form_data()` |
| Choices | `choice_ui.py` | ✅ Has `validate_choice_form_data()` |
| Principles | `principles_ui.py` | ✅ Has `validate_principle_form_data()` |

### ❌ Missing Domains (3)

| Domain | File | Request Model | Required Fields |
|--------|------|---------------|-----------------|
| KU (Knowledge Units) | `knowledge_ui.py` | `KuCreateRequest` | title (1-200), content (1+), domain (enum) |
| LS (Learning Steps) | `learning_ui.py` | `LsCreateRequest` | TBD |
| LP (Learning Paths) | `learning_ui.py` | `LpCreateRequest` | TBD |

---

## Validation Pattern

### Template (from tasks_ui.py)

```python
def validate_{domain}_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate {domain} form data early.

    Pure function: returns clear error messages for UI.

    Args:
        form_data: Raw form data from request

    Returns:
        Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
    """
    # Required fields
    field = form_data.get("field", "").strip()
    if not field:
        return Result.fail(Errors.validation("Field is required"))

    if len(field) > 200:
        return Result.fail(Errors.validation("Field must be 200 characters or less"))

    # Additional validation...

    return Result.ok(None)
```

### Key Characteristics

1. **Pure function** - No side effects, testable without mocks
2. **Takes raw form_data dict** - Before Pydantic parsing
3. **Returns Result[None]** - ok if valid, fail with user-friendly error
4. **User-friendly messages** - Not technical Pydantic errors
5. **Specific validation** - Required fields, length limits, business rules

---

## Implementation Steps

### Step 1: KU (Knowledge Units) Validation

**File:** `/adapters/inbound/ku_ui.py`

**Required Fields (from KuCreateRequest):**
- `title`: 1-200 characters
- `content`: Minimum 1 character
- `domain`: Valid Domain enum value

**Optional Fields:**
- `tags`: list[str]
- `prerequisites`: list[str] (KU UIDs)
- `complexity`: "basic" | "medium" | "advanced"

**Validation Rules:**
```python
def validate_ku_form_data(form_data: dict[str, Any]) -> Result[None]:
    """Validate knowledge unit form data early."""

    # Required: title
    title = form_data.get("title", "").strip()
    if not title:
        return Result.fail(Errors.validation("Knowledge title is required"))
    if len(title) > 200:
        return Result.fail(Errors.validation("Title must be 200 characters or less"))

    # Required: content
    content = form_data.get("content", "").strip()
    if not content:
        return Result.fail(Errors.validation("Knowledge content is required"))

    # Required: domain
    domain = form_data.get("domain", "").strip()
    if not domain:
        return Result.fail(Errors.validation("Knowledge domain is required"))

    # Optional: complexity (if provided, must be valid)
    complexity = form_data.get("complexity", "").strip()
    if complexity and complexity not in ["basic", "medium", "advanced"]:
        return Result.fail(
            Errors.validation("Complexity must be 'basic', 'medium', or 'advanced'")
        )

    return Result.ok(None)
```

### Step 2: LS (Learning Steps) Validation

**File:** `/adapters/inbound/learning_ui.py`

**TODO:** Check LsCreateRequest model for required fields.

### Step 3: LP (Learning Paths) Validation

**File:** `/adapters/inbound/learning_ui.py`

**TODO:** Check LpCreateRequest model for required fields.

---

## Testing Strategy

### Unit Tests (Pure Functions)

```python
# tests/unit/test_form_validation.py

def test_validate_ku_form_data_success():
    """Test valid KU form data."""
    form_data = {
        "title": "Introduction to Python",
        "content": "Python is a high-level programming language...",
        "domain": "TECH",
    }
    result = validate_ku_form_data(form_data)
    assert not result.is_error

def test_validate_ku_form_data_missing_title():
    """Test missing title."""
    form_data = {
        "content": "Some content",
        "domain": "TECH",
    }
    result = validate_ku_form_data(form_data)
    assert result.is_error
    assert "title is required" in result.error.message.lower()

def test_validate_ku_form_data_title_too_long():
    """Test title exceeds 200 characters."""
    form_data = {
        "title": "x" * 201,
        "content": "Content",
        "domain": "TECH",
    }
    result = validate_ku_form_data(form_data)
    assert result.is_error
    assert "200 characters or less" in result.error.message

def test_validate_ku_form_data_invalid_complexity():
    """Test invalid complexity value."""
    form_data = {
        "title": "Title",
        "content": "Content",
        "domain": "TECH",
        "complexity": "expert",  # Invalid - should be basic/medium/advanced
    }
    result = validate_ku_form_data(form_data)
    assert result.is_error
    assert "basic" in result.error.message.lower()
```

### Integration Testing

1. **Manual UI Testing:**
   - Submit empty form → See "Title is required" error
   - Submit 201-char title → See "200 characters or less" error
   - Submit valid form → Success

2. **HTMX Behavior:**
   - Error messages rendered in error banner
   - Focus moves to first invalid field
   - Form retains valid values

---

## Benefits

### For Users

1. **Clear Error Messages**
   - "Title is required" vs Pydantic's "field required"
   - "Title must be 200 characters or less" vs "ensure this value has at most 200 characters"

2. **Faster Feedback**
   - Validation before Pydantic parsing
   - Immediate error display

3. **Better UX**
   - User-friendly language
   - Contextual validation messages

### For Developers

1. **Testable**
   - Pure functions (no mocks needed)
   - Easy to unit test

2. **Consistent**
   - Same pattern across all domains
   - Predictable error handling

3. **Maintainable**
   - Validation logic in one place
   - Easy to update rules

---

## Implementation Checklist

- [ ] **Research**
  - [ ] Check LS request model
  - [ ] Check LP request model
  - [ ] Document required fields for each

- [ ] **Implementation**
  - [ ] Add `validate_ku_form_data()` to `knowledge_ui.py`
  - [ ] Add `validate_ls_form_data()` to `learning_ui.py`
  - [ ] Add `validate_lp_form_data()` to `learning_ui.py`

- [ ] **Integration**
  - [ ] Update KU create route to use validation
  - [ ] Update LS create route to use validation
  - [ ] Update LP create route to use validation

- [ ] **Testing**
  - [ ] Unit tests for each validation function
  - [ ] Manual UI testing for each form
  - [ ] Error message clarity review

- [ ] **Documentation**
  - [ ] Update UI_COMPONENT_PATTERNS.md with validation pattern
  - [ ] Add examples to form patterns skill

---

## Timeline

| Task | Estimated Time |
|------|----------------|
| Research LS/LP models | 1 hour |
| Implement KU validation | 1-2 hours |
| Implement LS validation | 1-2 hours |
| Implement LP validation | 1-2 hours |
| Integrate into routes | 2-3 hours |
| Unit tests | 2-3 hours |
| Manual testing | 1 hour |
| **Total** | **8-12 hours** |

---

## Success Criteria

✅ All 9 domains have `validate_{domain}_form_data()` function
✅ All validation functions are pure (testable without mocks)
✅ All error messages are user-friendly
✅ All forms use early validation before Pydantic
✅ Unit tests cover happy path + all error cases
✅ Manual testing confirms clear error messages

---

## Next Steps

After completing universal form validation:

1. **Phase 3, Task 2:** Result[T] Pattern for All Routes
2. **Phase 3, Task 3:** Typed Query Parameters
3. **Phase 3, Task 4:** Component Variant System
4. **Phase 3, Task 5:** Component Catalog Documentation

---

## Related Documentation

- **Pattern Template:** `/adapters/inbound/tasks_ui.py` (lines 326-361)
- **Error Handling:** `/docs/patterns/ERROR_HANDLING.md`
- **Form Patterns:** `/.claude/skills/skuel-form-patterns/`
- **Validation Skill:** `/.claude/skills/ui-error-handling/`
