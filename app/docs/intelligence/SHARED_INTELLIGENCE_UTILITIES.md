# Shared Intelligence Utilities

**Last Updated:** January 24, 2026

## Overview

SKUEL's intelligence services share common patterns across all 10 domain intelligence services (6 Activity + 3 Curriculum + Finance). This document describes:
1. Shared utilities in `/core/services/intelligence/` that consolidate patterns
2. BaseAnalyticsService foundation that all domain intelligence services extend

**Consolidation Results:**
- **51 helper methods** analyzed across 6 Activity services
- **~640 lines** consolidated into 4 shared utilities + BaseAnalyticsService
- **38-49% reduction** in helper code duplication

**All Domain Intelligence Services:**
- Activity (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum (3): KU (Knowledge Units), LS (Learning Steps), LP (Learning Paths)
- Finance (1): ExpenseIntelligence (admin-only)

All extend `BaseAnalyticsService` for graph analytics WITHOUT AI dependencies.

---

## BaseAnalyticsService Enhancements (January 2026)

### __slots__ Architectural Guard

**Purpose:** Enforce "Analytics must never depend on AI" at runtime.

```python
# File: /core/services/base_analytics_service.py (lines 70-100)

class BaseAnalyticsService(Generic[B]):
    """
    Foundation for all intelligence services.

    CRITICAL: Analytics services work WITHOUT AI (no llm, no embeddings).
    AI features go in separate BaseAIService subclasses.
    """

    # Architectural constraint: Restrict attributes to prevent AI coupling
    __slots__ = ("backend", "event_bus", "graph_intel", "logger", "orchestrator", "relationships")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Enforce architectural invariant: Analytics services cannot have AI dependencies.

        This prevents setting llm or embeddings attributes, even if child classes
        have __dict__ due to not defining __slots__.
        """
        if name in ("llm", "embeddings", "llm_service", "embeddings_service"):
            raise AttributeError(
                f"Cannot set '{name}' on {self.__class__.__name__}. "
                f"Analytics services must never depend on AI (llm/embeddings). "
                f"Use BaseAIService for AI-powered features."
            )
        object.__setattr__(self, name, value)
```

**Benefit:** Type errors become runtime errors - attempting to add AI dependencies to analytics services fails immediately.

### Dual-Track Assessment Template

**Purpose:** Compare user self-assessment (vision) vs system measurement (action) to generate perception gap analysis.

This implements SKUEL's core philosophy: *"The user's vision is understood via words, UserContext is determined via actions."*

```python
# File: /core/services/base_analytics_service.py (lines 365-522)

async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: str,
    # USER-DECLARED (Vision)
    user_level: L,              # User's self-reported level (enum)
    user_evidence: str,         # User's evidence for assessment
    user_reflection: str | None,
    # SYSTEM CALCULATION
    system_calculator: Callable[[Any, str], Awaitable[tuple[L, float, list[str]]]],
    # LEVEL SCORING (domain-specific enum → float)
    level_scorer: Callable[[L], float],
    # OPTIONAL CUSTOMIZATION
    entity_type: str = "",
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Result[DualTrackResult[L]]:
    """
    Template method for dual-track assessment.

    1. Fetch entity from backend
    2. Calculate user score from user_level (vision)
    3. Calculate system score via system_calculator (action)
    4. Calculate perception gap (|user_score - system_score|)
    5. Generate insights about gap
    6. Generate recommendations
    7. Store assessment (optional)
    8. Return DualTrackResult[L]

    Returns:
        Result[DualTrackResult[L]] containing:
            - user_level, user_score, user_evidence, user_reflection
            - system_level, system_score, system_evidence
            - perception_gap (0.0-1.0), gap_direction
            - insights, recommendations
    """
```

**Usage Example (Principles):**
```python
# File: /core/services/principles/principles_intelligence_service.py

from core.models.enums.principle_enums import AlignmentLevel
from core.models.shared.dual_track import DualTrackResult

async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: str,
    user_level: AlignmentLevel,
    evidence: str,
    reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
    """Compare user's declared alignment vs system-measured alignment."""
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_level,              # Vision: AlignmentLevel.ALIGNED
        user_evidence=evidence,              # Vision: "I always act with integrity"
        user_reflection=reflection,
        system_calculator=self._calculate_system_alignment,  # Action: measures actual behavior
        level_scorer=self._alignment_level_to_score,         # AlignmentLevel → 0.0-1.0
        entity_type=EntityType.PRINCIPLE.value,
    )

async def _calculate_system_alignment(
    self, principle: Principle, user_uid: str
) -> tuple[AlignmentLevel, float, list[str]]:
    """
    Calculate alignment from behavior (goals, choices, habits).

    Returns:
        (AlignmentLevel, score 0.0-1.0, evidence list)
    """
    # Measure actual behavior: goals that embody principle, choices that reflect it, etc.
    # Return (AlignmentLevel.MOSTLY_ALIGNED, 0.75, ["Goal 'Be Honest' embodies this"])
```

**Result:**
```python
result = DualTrackResult[AlignmentLevel](
    entity_uid="principle.integrity",
    entity_type="principle",
    # VISION (what user says)
    user_level=AlignmentLevel.ALIGNED,
    user_score=1.0,
    user_evidence="I always act with integrity",
    user_reflection="This is my core value",
    # ACTION (what system measures)
    system_level=AlignmentLevel.MOSTLY_ALIGNED,
    system_score=0.75,
    system_evidence=("Goal 'Be Honest' embodies this", "Choice 'Told truth' reflects this"),
    # GAP ANALYSIS
    perception_gap=0.25,  # 25% gap
    gap_direction="user_higher",  # User thinks more aligned than behavior shows
    # INSIGHTS
    insights=("Self-assessment is higher than measured behavior",),
    recommendations=("Track specific instances of integrity", "Create daily integrity habit"),
)
```

### Event Handling System

**Purpose:** Declarative event handler registration via ClassVar.

```python
# File: /core/services/base_analytics_service.py (lines 83-85)

class GoalsIntelligenceService(BaseAnalyticsService):
    # Declare event handlers at class level
    _event_handlers: ClassVar[dict[type, str]] = {
        GoalCompleted: "on_goal_completed",
        GoalAbandoned: "on_goal_abandoned",
    }

    async def on_goal_completed(self, event: GoalCompleted) -> None:
        """Handle goal completion - recalculate achievement rate."""
        # React to event
```

BaseAnalyticsService `__init__` auto-registers handlers from `_event_handlers`.

---

## The Problem: Duplicated Patterns

Before consolidation, each Activity Domain intelligence service implemented its own versions of:

| Pattern | Occurrences | Example Methods |
|---------|-------------|-----------------|
| Threshold-based recommendations | 45+ | `_generate_progress_recommendations()` |
| Metric calculations | 25 | `_calculate_consistency_score()` |
| Pattern extraction | 11 | `_extract_word_frequencies()` |
| Trend classification | 6 | `_determine_trend()` |
| Context-based analysis | 15+ | Fetch entity → Get context → Calculate → Return |
| Dual-track assessment | NEW | Compare vision vs action |

This led to:
- **Inconsistent behavior** (different thresholds across services)
- **Bug propagation** (fixing a bug required 6 updates)
- **Maintenance overhead** (~1,300 lines of duplicated logic)

---

## The Solution: 5-Phase Consolidation + BaseAnalyticsService

### Architecture

```
/core/services/
├── base_analytics_service.py         # Foundation for all intelligence services
│   ├── __slots__ guard               # Prevent AI dependencies
│   ├── _dual_track_assessment()      # Template: vision vs action gap
│   ├── _event_handlers ClassVar      # Declarative event subscription
│   └── _analyze_entity_with_context() # Template: fetch + analyze

/core/services/intelligence/
├── __init__.py                       # Re-exports all shared utilities
├── recommendation_engine.py          # Phase 1: Fluent recommendation builder
├── metrics_calculator.py             # Phase 2: Shared calculations
├── pattern_analyzer.py               # Phase 3: Pattern detection
├── trend_analyzer.py                 # Phase 4: Trend classification
└── cross_domain_context_service.py  # Existing context retrieval

/core/models/shared/
└── dual_track.py                     # DualTrackResult[L] generic model

All 10 Domain Intelligence Services extend BaseAnalyticsService:
├── tasks/tasks_intelligence_service.py
├── goals/goals_intelligence_service.py
├── habits/habits_intelligence_service.py
├── events/events_intelligence_service.py
├── choices/choices_intelligence_service.py
├── principles/principles_intelligence_service.py
├── ku/ku_intelligence_service.py
├── ls/ls_intelligence_service.py
├── lp/lp_intelligence_service.py
└── finance/finance_intelligence_service.py
```

---

## Phase 1: RecommendationEngine

**Location:** `/core/services/intelligence/recommendation_engine.py`

**Purpose:** Fluent builder for generating threshold-based recommendations consistently across all domains.

### The Pattern It Replaces

Before (duplicated in each service):
```python
def _generate_progress_recommendations(self, metrics: dict) -> list[str]:
    recommendations = []
    if metrics.get("consistency") < 0.5:
        recommendations.append("Low consistency - build habits")
    if metrics.get("progress") < 0.3:
        recommendations.append("Behind schedule - increase focus")
    if metrics.get("streak", 0) > 7:
        recommendations.append("Great streak! Keep going")
    return recommendations
```

After (single shared utility):
```python
from core.services.intelligence import RecommendationEngine

recommendations = (
    RecommendationEngine()
    .with_metrics(metrics)
    .add_threshold_check("consistency", 0.5, "Low consistency - build habits")
    .add_threshold_check("progress", 0.3, "Behind schedule - increase focus", comparison="lt")
    .add_conditional(metrics.get("streak", 0) > 7, "Great streak! Keep going")
    .build()
)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `with_metrics(dict)` | Set metrics for threshold checks |
| `add_threshold_check(metric, threshold, message, comparison)` | Add recommendation if metric crosses threshold |
| `add_range_check(metric, ranges, level)` | Add recommendation based on value range |
| `add_conditional(condition, message)` | Add recommendation if condition is True |
| `build()` | Return accumulated recommendations as list |

### Services Using RecommendationEngine

| Service | Methods Migrated |
|---------|-----------------|
| Tasks | `_generate_behavioral_recommendations` |
| Goals | `_generate_prediction_recommendations`, `_generate_progress_recommendations`, `_generate_learning_recommendations` |
| Habits | `_generate_performance_recommendations`, `_generate_goal_support_recommendations` |
| Events | `_generate_scheduling_recommendations` |
| Principles | `_generate_alignment_recommendations`, `_generate_adherence_recommendations`, `_generate_conflict_recommendations` |

---

## Phase 2: MetricsCalculator

**Location:** `/core/services/intelligence/metrics_calculator.py`

**Purpose:** Static utility methods for common metric calculations (thresholds, weighted averages, scaling).

### The Pattern It Replaces

Before:
```python
def _calculate_progress_factor(self, progress: float) -> float:
    # Sigmoid scaling for progress 0-100%
    return 1 / (1 + math.exp(-10 * (progress - 0.5)))

def _calculate_consistency_factor(self, data: list) -> float:
    if not data:
        return 0.0
    total = sum(item.weight * item.score for item in data)
    weights = sum(item.weight for item in data)
    return total / weights if weights > 0 else 0.0
```

After:
```python
from core.services.intelligence import MetricsCalculator

progress_factor = MetricsCalculator.sigmoid_scale(progress, midpoint=0.5)
consistency = MetricsCalculator.weighted_average(
    data,
    value_fn=lambda x: x.score,
    weight_fn=lambda x: x.weight
)
```

### Key Methods

| Method | Purpose | Example Use |
|--------|---------|-------------|
| `classify_by_threshold(value, thresholds, default)` | Classify value into categories | Status determination |
| `weighted_average(items, value_fn, weight_fn)` | Compute weighted average | Consistency scores |
| `sigmoid_scale(value, midpoint, steepness)` | Apply S-curve scaling | Progress factors |
| `clamp(value, min_val, max_val)` | Constrain value to range | Score bounds |
| `combine_weighted_factors(factors, weights)` | Combine multiple factors | Probability calculation |
| `calculate_ratio(numerator, denominator, default)` | Safe division | Completion rates |
| `calculate_harmony_score(total_items, conflict_count)` | Harmony from conflicts | Principle alignment |

### Services Using MetricsCalculator

| Service | Methods Migrated |
|---------|-----------------|
| Goals | `_calculate_progress_factor`, `_calculate_consistency_factor`, `_calculate_time_factor`, `_combine_probability_factors` |
| Habits | `_calculate_practice_effectiveness` |
| Principles | `_analyze_consistency`, `_calculate_harmony_score` |

---

## Phase 3: PatternAnalyzer

**Location:** `/core/services/intelligence/pattern_analyzer.py`

**Purpose:** Static utility methods for pattern detection in text and data structures.

### The Pattern It Replaces

Before:
```python
def _extract_activities_from_dict(self, context_dict: dict) -> dict[str, int]:
    return {
        "choices": len(context_dict.get("choices", [])),
        "habits": len(context_dict.get("habits", [])),
        "goals": len(context_dict.get("goals", [])),
    }
```

After:
```python
from core.services.intelligence import PatternAnalyzer

counts = PatternAnalyzer.extract_dict_field_counts(
    context_dict,
    ["choices", "habits", "goals"]
)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `extract_word_frequencies(texts, min_length, exclude, top_n)` | Extract common words from text list |
| `detect_by_keywords(entities, keyword_sets, text_fn, min_matches)` | Find patterns via keyword matching |
| `extract_dict_field_counts(dict, field_keys)` | Count list lengths from dict fields |
| `identify_factors(entities, conditions)` | Identify matching conditions |

### Services Using PatternAnalyzer

| Service | Methods Migrated |
|---------|-----------------|
| Tasks | `_analyze_task_patterns`, `_identify_learning_opportunities` |
| Principles | `_extract_activities_from_dict`, `_extract_recent_activities_from_dict` |

---

## Phase 4: TrendAnalyzer

**Location:** `/core/services/intelligence/trend_analyzer.py`

**Purpose:** Threshold-based trend classification utilities.

### The Pattern It Replaces

Before:
```python
def _determine_trend(self, actual: float, expected: float) -> str:
    if actual > expected:
        return "improving"
    elif actual < expected * 0.8:
        return "declining"
    return "stable"
```

After:
```python
from core.services.intelligence import compare_progress_to_expected

trend = compare_progress_to_expected(
    actual_progress=current,
    expected_progress=target
)
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `analyze_completion_trend(completed, total, thresholds)` | Classify completion rates |
| `analyze_activity_trajectory(count, periods, thresholds)` | Classify activity frequency trends |
| `compare_progress_to_expected(actual, expected, improving_items, declining_items)` | Compare actual vs expected with tiebreaker |
| `determine_trend_from_rate(rate, thresholds, default)` | Classify single rate value |

### Services Using TrendAnalyzer

| Service | Methods Migrated |
|---------|-----------------|
| Tasks | `_analyze_performance_trends` |
| Goals | `_determine_trend` |
| Principles | `_analyze_trajectory`, `_determine_trend` |

---

## Phase 5: Context Analysis Template

**Location:** `/core/services/base_analytics_service.py` (`_analyze_entity_with_context`)

**Purpose:** Template method in BaseAnalyticsService that consolidates the common "fetch entity → get context → calculate metrics → generate recommendations → return" pattern.

### The Pattern It Replaces

Before (repeated in every service):
```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
    # 1. Fetch entity
    entity_result = await self.backend.get(uid)
    if entity_result.is_error:
        return Result.fail(entity_result.expect_error())
    entity = entity_result.value

    # 2. Get context
    context_result = await self.context_service.analyze_with_context(
        entity_uid=uid,
        backend=self.backend,
        relationships=self.relationships,
        context_method="get_goal_cross_domain_context",
        context_type=GoalCrossContext,
        metrics_fn=calculate_goal_metrics,
        ...
    )
    if context_result.is_error:
        return Result.fail(context_result.expect_error())

    # 3. Extract and calculate
    analysis = context_result.value
    goal = analysis.entity
    context = analysis.context
    metrics = analysis.metrics

    # 4. Build response...
```

After (delegating to template):
```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
    # Phase 5: Use base class template
    analysis_result = await self._analyze_entity_with_context(
        uid=uid,
        context_method="get_goal_cross_domain_context",
        context_type=GoalCrossContext,
        metrics_fn=calculate_goal_metrics,
        recommendations_fn=self._generate_progress_recommendations,
        min_confidence=0.7,  # Optional kwargs supported
    )

    if analysis_result.is_error:
        return analysis_result

    # Access via dict (template returns dict, not object)
    analysis = analysis_result.value
    goal = analysis["entity"]
    context = analysis["context"]
    metrics = analysis["metrics"]
    recommendations = analysis["recommendations"]

    # Build domain-specific response...
```

### Template Method Signature

```python
async def _analyze_entity_with_context(
    self,
    uid: str,
    context_method: str,           # e.g., "get_goal_cross_domain_context"
    context_type: type,            # e.g., GoalCrossContext
    metrics_fn: Callable,          # (entity, context) -> dict
    recommendations_fn: Callable | None = None,  # (entity, context, metrics) -> list
    **context_kwargs: Any,         # min_confidence, depth, etc.
) -> Result[dict[str, Any]]:
```

### Return Structure

```python
{
    "entity": <domain model>,
    "context": <typed cross-domain context>,
    "metrics": <calculated metrics dict>,
    "recommendations": <list of recommendations>,
}
```

### Services Using the Template

| Service | Methods Migrated |
|---------|-----------------|
| Goals | `get_goal_progress_dashboard`, `get_goal_completion_forecast`, `get_goal_learning_requirements` |
| Habits | `analyze_habit_performance`, `get_habit_knowledge_reinforcement`, `get_habit_goal_support` |
| Principles | `assess_principle_alignment` |

### Events Exception

**EventsIntelligenceService** uses a different pattern and was not migrated:
- Uses `get_event_with_context()` returning `(Event, GraphContext)`
- Helper methods are async and require `GraphContext`, not `EventCrossContext`
- Migrating would require significant refactoring of the async helper methods

This is a documented architectural difference, not a limitation.

---

## Import Patterns

All shared utilities are re-exported from the intelligence package:

```python
# Recommended imports
from core.services.intelligence import (
    RecommendationEngine,
    MetricsCalculator,
    PatternAnalyzer,
    analyze_completion_trend,
    analyze_activity_trajectory,
    compare_progress_to_expected,
    determine_trend_from_rate,
)
```

For metrics calculators (domain-specific):
```python
from core.services.intelligence import (
    calculate_goal_metrics,
    calculate_habit_metrics,
    calculate_event_metrics,
    calculate_choice_metrics,
    calculate_principle_metrics,
    calculate_task_metrics,
)
```

---

## Benefits

### 1. Consistency
Single implementation of recommendation, metric, and pattern logic ensures consistent behavior across all domains.

### 2. Testability
Test shared utilities once instead of testing duplicated implementations in 6 services.

### 3. Maintainability
Fix bugs or add features in one place, affecting all consumers.

### 4. Documentation
Shared utilities are self-documenting with clear interfaces.

### 5. Future Domains
New intelligence services inherit proven patterns without reimplementing.

---

## Testing

```bash
# Test shared utilities
poetry run pytest tests/unit/services/intelligence/ -v

# Test intelligence services (verify behavior unchanged)
poetry run pytest tests/test_goals_intelligence.py -v
poetry run pytest tests/test_habits_intelligence.py -v
poetry run pytest tests/test_events_intelligence.py -v
poetry run pytest tests/test_principles_alignment_tracking.py -v
poetry run pytest tests/test_tasks_intelligence.py -v
```

---

## See Also

- **Implementation Plan:** `/home/mike/.claude/plans/intelligence-helper-consolidation.md`
- **BaseAnalyticsService:** `/core/services/base_analytics_service.py`
- **ADR-024:** BaseAnalyticsService Migration
- **Individual Domain Guides:** See `INTELLIGENCE_SERVICES_INDEX.md`
