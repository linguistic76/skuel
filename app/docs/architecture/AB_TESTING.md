# A/B Testing Infrastructure

**Version:** 1.0.0
**Date:** January 2026 (Phase 2 Enhancement)
**Status:** Active

---

## Overview

Simple, hash-based A/B testing infrastructure for comparing search strategies and features.

**Design Philosophy:**
- **Stateless**: No database storage needed (deterministic hash assignment)
- **Fast**: Simple MD5 hash calculation per request
- **Configuration-driven**: Enable/disable tests via config
- **Metrics-aware**: Integrates with existing search metrics tracking

---

## Architecture

### Core Components

```
ABTestingService
    ├── get_test_group(test_id, user_uid) → TestGroup (CONTROL | TREATMENT)
    ├── is_in_treatment(test_id, user_uid) → bool
    └── is_in_control(test_id, user_uid) → bool

TestGroup (Enum)
    ├── CONTROL    # Standard behavior
    └── TREATMENT  # New feature being tested

ABTestConfig (Dataclass)
    ├── test_id: str                 # "semantic_search_v1"
    ├── enabled: bool                # True/False
    ├── treatment_percentage: float  # 0.0-1.0 (default: 0.5)
    └── description: str             # Human-readable description
```

### Hash-Based Assignment

**Algorithm:**
1. Combine `test_id` and `user_uid` → `"semantic_search_v1:user.alice"`
2. Hash with MD5 → `a1b2c3d4...`
3. Take first 8 hex chars → `a1b2c3d4`
4. Convert to integer → `2712847316`
5. Normalize to 0.0-1.0 → `2712847316 / 0xFFFFFFFF = 0.632`
6. Compare to treatment percentage:
   - `0.632 < 0.5` → **TREATMENT**
   - `0.632 >= 0.5` → **CONTROL**

**Properties:**
- ✅ Deterministic: Same user always gets same group for a test
- ✅ Balanced: Approaches 50/50 split with large user base
- ✅ Independent: Different test IDs produce different assignments
- ✅ Fast: Single hash calculation (~microseconds)

---

## Usage

### 1. Configuration

Add test configuration to `unified_config.py`:

```python
@dataclass
class ABTestingConfig:
    # Semantic search A/B test
    semantic_search_enabled: bool = True  # Enable test
    semantic_search_treatment_pct: float = 0.5  # 50% in treatment group
```

### 2. Service Initialization

```python
from core.services.ab_testing_service import ABTestingService, ABTestConfig, TestGroup

# Create test config
config = ABTestConfig(
    test_id="semantic_search_v1",
    enabled=True,
    treatment_percentage=0.5,
    description="Compare semantic vs standard search performance"
)

# Initialize service
ab_service = ABTestingService({"semantic_search_v1": config})
```

### 3. Route Integration

Example: SearchRouter with A/B testing

```python
# In search route
async def search_results(request: Request, query: str) -> Any:
    user_uid = require_authenticated_user(request)

    # Check test group
    if ab_service.is_in_treatment("semantic_search_v1", user_uid):
        # Use semantic search (treatment)
        result = await vector_search.semantic_enhanced_search(
            label="Ku",
            text=query,
            context_uids=context.learning_goals,
            limit=20
        )
    else:
        # Use standard search (control)
        result = await ku_service.search(
            query_text=query,
            user_uid=user_uid,
            limit=20
        )

    # Track metrics (same for both groups)
    await track_search_metrics(user_uid, query, result)

    return render_results(result)
```

### 4. Metrics Analysis

Use the analyzer script to compare results:

```bash
poetry run python scripts/analyze_ab_test_results.py semantic_search_v1 --days 7
```

**Output:**
```
============================================================
A/B Test Analysis: semantic_search_v1
Period: 7 days
============================================================

Total Users: 1000
  Control: 498
  Treatment: 502

Metrics Comparison:
Metric                          Control    Treatment     Change
------------------------------------------------------------------
Total Searches                      824          856     ✅ +3.9%
Click-Through Rate                 0.65         0.72     ✅ +10.8%
Avg Results/Query                  8.50         9.20     ✅ +8.2%
Avg Time to Click                  3.20s        2.80s    ✅ +12.5%

============================================================
```

---

## Metrics Tracked

The A/B test analyzer compares these metrics between control and treatment groups:

| Metric | Description | Higher = Better? |
|--------|-------------|------------------|
| **Click-Through Rate** | % of searches resulting in clicks | ✅ Yes |
| **Avg Results/Query** | Average number of results returned | ✅ Yes (to a point) |
| **Time to First Click** | Seconds from search to first click | ❌ No (lower is better) |
| **Total Searches** | Volume of searches performed | Neutral (context-dependent) |

**Data Source:** `SearchMetrics` nodes in Neo4j

---

## Best Practices

### Test Design

1. **Single Variable**: Change only one thing per test
   - ✅ Good: "Semantic boost vs no boost"
   - ❌ Bad: "Semantic boost + learning-aware + hybrid search"

2. **Sufficient Sample Size**: Run for at least 7 days with 100+ users per group
   - Small samples → unreliable results
   - Large samples → statistical significance

3. **Clear Success Criteria**: Define what "better" means before starting
   - CTR > 10% improvement?
   - Time to click < 20% reduction?

### Avoiding Bias

- **Don't peek early**: Wait for full test duration
- **Consider seasonality**: Account for day-of-week effects
- **Equal exposure**: Both groups should have equal access to features

### When to Stop a Test

**Stop early if:**
- ❌ Treatment significantly **worse** (>20% degradation in key metric)
- ❌ Technical issues causing errors in one group

**Wait full duration if:**
- ✅ Results look promising but not conclusive
- ✅ Metrics are close (within 5%)

---

## Example: Semantic Search A/B Test

### Hypothesis

"Semantic relationship boosting improves search relevance, increasing click-through rate by 10%+"

### Test Setup

```python
# Config
test_config = ABTestConfig(
    test_id="semantic_search_v1",
    enabled=True,
    treatment_percentage=0.5,
    description="Semantic boost vs standard vector search"
)

# Control Group: Standard vector search
results = await vector_search.find_similar_by_text(
    label="Ku",
    text=query,
    limit=20,
    min_score=0.75
)

# Treatment Group: Semantic-enhanced search
results = await vector_search.semantic_enhanced_search(
    label="Ku",
    text=query,
    context_uids=user_context.learning_goals,
    limit=20,
    min_score=0.75
)
```

### Success Criteria

**Primary Metric:**
- CTR improvement > 10%

**Secondary Metrics:**
- Time to click reduction > 15%
- User return rate increase > 5%

### Duration

- **Minimum**: 7 days
- **Target**: 14 days for statistical confidence

---

## Advanced: Multiple Concurrent Tests

**Question:** Can I run multiple A/B tests at once?

**Answer:** Yes, but be careful about interactions.

```python
# Independent tests (no conflict)
group1 = ab_service.get_test_group("semantic_search_v1", user_uid)
group2 = ab_service.get_test_group("new_ui_design_v1", user_uid)

# User could be:
# - Control for both
# - Treatment for both
# - Control for one, Treatment for other
```

**Best Practice:** Avoid overlapping tests that affect the same user experience. For example, don't run two search ranking tests simultaneously—results will be confounded.

---

## Troubleshooting

### Problem: Unbalanced Groups

**Symptom:** 60/40 split instead of 50/50

**Cause:** Small sample size (hash distribution approaches 50/50 with large N)

**Solution:** Wait for more users or adjust `treatment_percentage`

### Problem: No Difference in Metrics

**Symptom:** Both groups show identical metrics

**Cause:**
1. Feature not actually different between groups
2. Insufficient sample size
3. Metric not sensitive enough

**Solution:** Verify feature implementation, increase sample size, or choose different metrics

### Problem: One Group Has More Active Users

**Symptom:** Treatment group has 2x searches despite 50/50 split

**Cause:** Random variance (some active users happen to hash to treatment)

**Solution:** This is expected and okay! Compare **rates** (CTR, avg time), not absolute counts.

---

## API Reference

### ABTestingService

```python
class ABTestingService:
    def __init__(self, test_configs: dict[str, ABTestConfig] | None = None)

    def get_test_group(self, test_id: str, user_uid: str) -> TestGroup
    """Get test group assignment (deterministic)."""

    def is_in_treatment(self, test_id: str, user_uid: str) -> bool
    """Check if user is in treatment group."""

    def is_in_control(self, test_id: str, user_uid: str) -> bool
    """Check if user is in control group."""

    def add_test(self, config: ABTestConfig) -> None
    """Add or update test configuration."""

    def remove_test(self, test_id: str) -> None
    """Remove test configuration."""

    def list_active_tests(self) -> list[str]
    """Get list of currently active test IDs."""
```

### TestGroup Enum

```python
class TestGroup(str, Enum):
    CONTROL = "control"      # Standard behavior
    TREATMENT = "treatment"  # New feature being tested
```

### ABTestConfig Dataclass

```python
@dataclass(frozen=True)
class ABTestConfig:
    test_id: str                        # Unique identifier
    enabled: bool = False               # Active/inactive
    treatment_percentage: float = 0.5   # 0.0-1.0
    description: str = ""               # Human-readable
```

---

## Future Enhancements

Potential improvements for Phase 3:

1. **Multi-Armed Bandit**: Automatically adjust traffic based on performance
2. **Segmentation**: Different splits for different user cohorts (e.g., new vs returning)
3. **Metrics Dashboard**: Real-time visualization of test results
4. **Statistical Significance**: Automated p-value calculation
5. **Gradual Rollout**: Slowly increase treatment percentage (0% → 10% → 50% → 100%)

---

## Related Documentation

- **Search Architecture**: `/docs/architecture/SEARCH_ARCHITECTURE.md`
- **Semantic Search Phase 1**: `/docs/architecture/SEMANTIC_SEARCH_PHASE1_IMPLEMENTATION.md`
- **ADR-034**: Semantic Search Enhancement Decision

---

## Summary

SKUEL's A/B testing infrastructure provides:

✅ **Simple**: Hash-based assignment, no DB storage
✅ **Fast**: Microsecond-level overhead
✅ **Reliable**: Deterministic and balanced
✅ **Actionable**: Clear metrics for decision-making

Use it to confidently roll out new features while measuring real-world impact.
