# Context Health Score Enum Improvement
*Completed: 2026-01-25*

## Overview

Improved the `_calculate_health_score()` method in `UserContextService` by replacing string literals with a proper enum type, following ChatGPT's code review suggestion.

---

## Changes Made

### ✅ New Enum: `ContextHealthScore`

**Created:** `core/models/enums/user_enums.py` (added to existing file)

```python
class ContextHealthScore(str, Enum):
    """
    User context health scoring levels.

    Matches FinancialHealthTier pattern for consistency across domains.
    Used to assess overall user context system health based on metrics
    and alerts.

    Hierarchy (lowest to highest):
        POOR < FAIR < GOOD < EXCELLENT
    """

    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
```

**Dynamic Enum Methods (following SKUEL pattern):**

| Method | Purpose | Example Return |
|--------|---------|----------------|
| `get_numeric()` | Numeric score for comparison | `1.0` (EXCELLENT) |
| `get_color()` | Tailwind CSS color class | `"text-green-600"` |
| `get_icon()` | Emoji representation | `"🟢"` |

---

### ✅ Updated Service Method

**Modified:** `core/services/user/user_context_service.py`

**Before:**
```python
def _calculate_health_score(self, summary: ContextSummary) -> str:
    """Returns: "excellent", "good", "fair", "poor" """
    # ...
    completion_rate = metrics.get("completion_rate", 0.0)  # Silent default

    if high_severity_count >= 2:
        return "poor"
    if high_severity_count == 1 or completion_rate < 0.5:
        return "fair"
    # ...
    return "good"
```

**After:**
```python
def _calculate_health_score(self, summary: ContextSummary) -> "ContextHealthScore":
    """Returns: ContextHealthScore (EXCELLENT, GOOD, FAIR, POOR)"""
    from core.models.enums import ContextHealthScore

    # Get completion rate (log if missing - could indicate data issues)
    completion_rate = metrics.get("completion_rate")
    if completion_rate is None:
        self.logger.warning(
            "Context health check: completion_rate metric missing, defaulting to 0.0"
        )
        completion_rate = 0.0

    if high_severity_count >= 2:
        return ContextHealthScore.POOR
    if high_severity_count == 1 or completion_rate < 0.5:
        return ContextHealthScore.FAIR
    # ...
    return ContextHealthScore.GOOD
```

**Key Improvements:**
1. ✅ Type-safe return value (enum instead of string)
2. ✅ Explicit logging when critical metric is missing
3. ✅ Clear warning if `completion_rate` defaults to 0.0

---

### ✅ Updated Exports

**Modified:** `core/models/enums/__init__.py`

Added `ContextHealthScore` to centralized enum exports:

```python
from .user_enums import ContextHealthScore, UserRole

__all__ = [
    # ...
    "ContextHealthScore",
    # ...
]
```

---

## Benefits

### 1. Type Safety ✅

**Before:** String literals allowed typos and inconsistencies
```python
# Could accidentally return "goood" or "Good"
return "good"
```

**After:** Enum enforces valid values at compile-time
```python
# MyPy catches invalid values
return ContextHealthScore.GOOD  # Type-safe
```

### 2. Consistency with SKUEL Patterns ✅

Matches existing domain patterns:
- `FinancialHealthTier` (finance domain)
- `ActivityStatus` (activity domains)
- `Priority` (all domains)

### 3. Presentation Logic in Enum ✅

Following SKUEL's Dynamic Enum Pattern:
```python
score = ContextHealthScore.EXCELLENT
badge_color = score.get_color()  # "text-green-600"
icon = score.get_icon()           # "🟢"
numeric = score.get_numeric()     # 1.0
```

### 4. Better Debugging ✅

**Missing metrics now logged:**
```
WARNING: Context health check: completion_rate metric missing, defaulting to 0.0
```

Previously, missing metrics silently defaulted to 0.0, potentially masking data issues.

### 5. JSON Serialization Works ✅

```python
# Enum inherits from str, so serializes automatically
{"overall_health": ContextHealthScore.EXCELLENT}
# Serializes to:
{"overall_health": "excellent"}
```

---

## Architecture Alignment

### Consistent with Finance Domain

**Finance Health Tiers:**
```python
class FinancialHealthTier(str, Enum):
    CRITICAL = "critical"
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
```

**Context Health Scores (new):**
```python
class ContextHealthScore(str, Enum):
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
```

**Note:** Context health doesn't need CRITICAL tier - POOR is sufficient for "2+ high-severity alerts"

### Dynamic Enum Pattern

All SKUEL enums provide presentation methods:

| Enum | Methods |
|------|---------|
| `Priority` | `get_color()`, `get_icon()` |
| `ActivityStatus` | `is_terminal()`, `is_active()`, `get_color()` |
| `ContextHealthScore` | `get_numeric()`, `get_color()`, `get_icon()` |

---

## Code Quality

**Linting:** ✅ All ruff checks passed
**Formatting:** ✅ All files formatted with ruff
**Type hints:** ✅ Fully typed with TYPE_CHECKING import
**JSON serialization:** ✅ Tested and verified

---

## Migration Impact

### API Response Format (No Breaking Changes)

**Before:**
```json
{
  "overall_health": "excellent",
  "metrics": {...},
  "recommendations": [...]
}
```

**After:**
```json
{
  "overall_health": "excellent",
  "metrics": {...},
  "recommendations": [...]
}
```

**Note:** Enum serializes to same string value - zero breaking changes.

### Enhanced Logging

New warning when metrics are missing:
```
WARNING: Context health check: completion_rate metric missing, defaulting to 0.0
```

This helps detect:
- Data pipeline issues
- Missing summary fields
- Context builder problems

---

## Future Enhancements (Optional)

### 1. Numeric Score in Response

Could add numeric score to API response for trend analysis:

```python
health = {
    "user_uid": user_uid,
    "overall_health": score,
    "health_score": score.get_numeric(),  # 0.0-1.0
    "metrics": summary.get("key_metrics", {}),
    # ...
}
```

**Use case:** Track health trends over time (0.75 → 0.50 = declining)

### 2. Additional Health Factors

Consider incorporating:
- Habit consistency scores
- Goal progress rates
- Knowledge application rates

```python
def _calculate_health_score(
    self,
    summary: ContextSummary,
    context: UserContext  # For additional signals
) -> ContextHealthScore:
    # More comprehensive scoring
```

### 3. Health Thresholds as Constants

Move magic numbers to constants:

```python
# In SystemConstants
HEALTH_EXCELLENT_THRESHOLD = 0.8
HEALTH_FAIR_THRESHOLD = 0.5
HEALTH_POOR_ALERT_THRESHOLD = 2  # High-severity alerts
```

---

## Testing Recommendations

```bash
# Test enum functionality
python3 -c "
from core.models.enums import ContextHealthScore
print(ContextHealthScore.EXCELLENT.get_numeric())  # 1.0
print(ContextHealthScore.EXCELLENT.get_color())    # text-green-600
print(ContextHealthScore.EXCELLENT.get_icon())     # 🟢
"

# Test API endpoint
curl http://localhost:8000/api/context/health?user_uid=user.demo

# Check logs for missing metrics warning
tail -f logs/skuel.log | grep "completion_rate metric missing"
```

---

## Conclusion

**Successfully improved context health scoring:**
- ✅ Type-safe enum replaces string literals
- ✅ Explicit logging for missing metrics
- ✅ Consistent with SKUEL's domain patterns
- ✅ Dynamic enum methods for presentation
- ✅ No breaking changes to API

**Impact:**
- Better type safety and IDE support
- Easier debugging with metric warnings
- Consistent patterns across domains
- Foundation for future enhancements

**Pattern established:** All health/quality scoring in SKUEL should use typed enums with presentation methods.

---

**Improvement Complete - January 25, 2026**
