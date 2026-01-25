# Profile Routes Security & Robustness Improvements

**Status:** Ready for implementation
**Priority:** Medium (prevents runtime errors, improves error handling)
**Scope:** `/adapters/inbound/user_profile_ui.py`

---

## Background

ChatGPT reviewed `user_profile_ui.py` and identified 6 improvement areas. This plan addresses the remaining medium-priority items.

**Completed:**
- ✅ Issue #4: User scoping security (CRITICAL) - Fixed 2026-01-25
- ✅ Issue #5: Missing field initialization - Fixed 2026-01-25

**This Plan:**
- Issue #2: Preferences save validation
- Issue #6: Intelligence error handling

---

## Issue #2: Preferences Save Validation

### Problem

**Location:** `/profile/settings/save` route (lines ~145-208)

Current code does unsafe type coercion:
```python
pomodoro_work_minutes = int(form_data.get("pomodoro_work_minutes"))
daily_capacity_hours = int(form_data.get("daily_capacity_hours"))
```

**Risks:**
1. `ValueError` if field is empty or contains non-numeric text
2. `TypeError` if form_data.get() returns None
3. User sees 500 error instead of validation message

**Example Failure:**
```
User submits form with empty "pomodoro_work_minutes" field
→ int("") raises ValueError
→ 500 Internal Server Error
```

### Solution

**Step 1: Create safe parsing helpers**

Add to top of file after imports:

```python
def safe_int(value: Any, default: int) -> int:
    """
    Safely parse integer from form data.

    Args:
        value: Form field value (may be None, empty string, or invalid)
        default: Default value if parsing fails

    Returns:
        Parsed integer or default
    """
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely parse boolean from form data.

    HTML checkboxes send "on" when checked, nothing when unchecked.

    Args:
        value: Form field value
        default: Default value if parsing fails

    Returns:
        Parsed boolean or default
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    # HTML checkbox values
    if value in ("on", "true", "True", "1"):
        return True
    if value in ("off", "false", "False", "0"):
        return False
    return default
```

**Step 2: Update preferences save route**

Replace unsafe parsing (lines ~160-175):

```python
# OLD (UNSAFE):
pomodoro_work_minutes = int(form_data.get("pomodoro_work_minutes"))
pomodoro_short_break = int(form_data.get("pomodoro_short_break"))
pomodoro_long_break = int(form_data.get("pomodoro_long_break"))
daily_capacity_hours = int(form_data.get("daily_capacity_hours"))
work_start_hour = int(form_data.get("work_start_hour"))
work_end_hour = int(form_data.get("work_end_hour"))

# NEW (SAFE):
pomodoro_work_minutes = safe_int(form_data.get("pomodoro_work_minutes"), 25)
pomodoro_short_break = safe_int(form_data.get("pomodoro_short_break"), 5)
pomodoro_long_break = safe_int(form_data.get("pomodoro_long_break"), 15)
daily_capacity_hours = safe_int(form_data.get("daily_capacity_hours"), 8)
work_start_hour = safe_int(form_data.get("work_start_hour"), 9)
work_end_hour = safe_int(form_data.get("work_end_hour"), 17)
```

**Step 3: Sanitize error messages**

Replace error message that leaks internals (line ~202):

```python
# OLD (LEAKS INTERNALS):
return Div(
    P(f"Error saving preferences: {update_result.error}", cls="text-error"),
    cls="p-4",
)

# NEW (USER-SAFE):
logger.error(
    "Failed to save user preferences",
    extra={"user_uid": user_uid, "error": str(update_result.error)}
)
return Div(
    P("Failed to save preferences. Please try again.", cls="text-error"),
    P("If this problem persists, contact support.", cls="text-sm text-base-content/50 mt-2"),
    cls="p-4",
)
```

### Benefits

- ✅ No more 500 errors from invalid form data
- ✅ Graceful fallback to sensible defaults
- ✅ No internal error leakage to users
- ✅ Better logging for debugging

### Testing

**Manual test cases:**
1. Submit form with all fields valid → Success
2. Submit form with empty numeric field → Uses default
3. Submit form with non-numeric text → Uses default
4. Submit form when user_service fails → Shows user-safe error

---

## Issue #6: Intelligence Error Handling

### Problem

**Location:** `_get_intelligence_data()` function (lines ~524-583)

Current code only catches `AttributeError` for configuration issues:

```python
except AttributeError as e:
    # Service interface mismatch - intelligence services not properly configured
    # This is a configuration issue, not a runtime error - use basic mode
    logger.warning(f"Intelligence services not properly configured: {e}")
    return Result.ok(None)
```

**Gap:** Other configuration errors (TypeError, KeyError) would return `Result.fail()` instead of gracefully using basic mode.

### Solution

**Step 1: Broaden exception handling**

Update exception handling (lines ~579-583):

```python
# OLD:
except AttributeError as e:
    # Service interface mismatch - intelligence services not properly configured
    # This is a configuration issue, not a runtime error - use basic mode
    logger.warning(f"Intelligence services not properly configured: {e}")
    return Result.ok(None)

# NEW:
except (AttributeError, TypeError, KeyError) as e:
    # Configuration errors - intelligence services not properly configured
    # These are setup issues, not runtime errors - degrade gracefully to basic mode
    logger.warning(
        "Intelligence services not properly configured - using basic mode",
        extra={
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
    )
    return Result.ok(None)
except Exception as e:
    # Unexpected error during intelligence computation
    # This is a true runtime error - propagate as failure
    logger.error(
        "Unexpected error in intelligence computation",
        extra={
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
    )
    return Result.fail(Errors.system(f"Intelligence computation failed: {e}"))
```

**Step 2: Update docstring**

Update docstring to document error handling strategy (lines ~524-544):

```python
"""
Get intelligence data for OverviewView if available.

Calls UserContextIntelligence methods to get:
- Daily work plan (THE flagship)
- Life path alignment (5 dimensions)
- Cross-domain synergies
- Optimal learning steps

Error Handling Strategy:
- Configuration errors (AttributeError, TypeError, KeyError) → basic mode
- Runtime computation errors → Result.fail() (propagates to HTTP boundary)
- Service not available → basic mode

Returns:
    - Result.ok(dict) - Intelligence data when fully configured
    - Result.ok(None) - Intelligence not available (use basic mode UI)
    - Result.fail() - Actual error during intelligence computation

Profile Hub operates in two modes:
- Basic mode: Core profile data always works
- Full mode: Intelligence features when properly configured
"""
```

### Benefits

- ✅ More robust configuration error handling
- ✅ Clear separation: config issues → basic mode, runtime errors → fail
- ✅ Better logging distinguishes error categories
- ✅ Clearer documentation of error handling strategy

### Testing

**Test scenarios:**
1. Intelligence factory missing → basic mode (existing)
2. Intelligence method returns wrong type (TypeError) → basic mode (NEW)
3. Intelligence method accesses missing key (KeyError) → basic mode (NEW)
4. Intelligence method has actual computation error → Result.fail() (existing)

---

## Implementation Plan

### Phase 1: Preferences Validation (30 min)

**Files to modify:** `adapters/inbound/user_profile_ui.py`

1. Add `safe_int()` and `safe_bool()` helpers after imports
2. Replace all unsafe `int()` calls in preferences save route
3. Update error message to be user-safe
4. Test with invalid form data

**Verification:**
```bash
# Start server and test /profile/settings
# Submit form with:
# - Empty pomodoro_work_minutes
# - Non-numeric daily_capacity_hours
# - All fields valid
# Expected: No crashes, uses defaults
```

### Phase 2: Intelligence Error Handling (15 min)

**Files to modify:** `adapters/inbound/user_profile_ui.py`

1. Update `_get_intelligence_data()` exception handling
2. Update docstring with error handling strategy
3. Add structured logging with extra fields

**Verification:**
```python
# Unit test: Mock intelligence service with various failures
# - AttributeError → Result.ok(None)
# - TypeError → Result.ok(None)
# - KeyError → Result.ok(None)
# - RuntimeError → Result.fail()
```

---

## Success Criteria

**Preferences Validation:**
- ✅ No 500 errors from invalid form input
- ✅ All form fields use safe parsing with defaults
- ✅ Error messages don't leak internal details
- ✅ Errors logged with structured data

**Intelligence Error Handling:**
- ✅ All configuration errors degrade to basic mode
- ✅ Runtime errors propagate as Result.fail()
- ✅ Clear logging distinguishes error types
- ✅ Docstring documents error handling strategy

---

## Low Priority Items (Deferred)

These are nice-to-have but not critical:

### Issue #1: Reduce duplication
- Extract `_load_user_or_demo()` helper
- Saves ~15 lines of duplication
- Low impact, defer to refactoring sprint

### Issue #3: Auth + demo fallback
- Decide explicit dev vs prod behavior for demo user
- Currently works but conceptually unclear
- Defer to configuration/deployment work

---

## Risk Assessment

**Changes:** Low-risk improvements to error handling
**Testing:** Manual testing sufficient (form submission, error scenarios)
**Rollback:** Each change is independent and reversible

---

## Implementation Order

**Recommended sequence:**

1. **Preferences validation** (higher user impact)
   - Users encounter this more frequently
   - Prevents visible 500 errors

2. **Intelligence error handling** (defensive improvement)
   - Improves robustness but less visible
   - Completes error handling strategy

**Total time estimate:** ~45 minutes

---

## Notes

- Both changes are defensive improvements (prevent errors, don't add features)
- No database schema changes required
- No breaking changes to existing functionality
- Safe to implement independently
