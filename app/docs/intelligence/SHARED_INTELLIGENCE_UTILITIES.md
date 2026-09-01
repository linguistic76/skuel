---
updated: 2026-08-08
---

# Shared Intelligence Utilities

**Last Updated:** June 12, 2026

## Overview

SKUEL's intelligence services share common patterns across all 9 domain intelligence services (6 Activity + 3 Curriculum). This document describes:
1. Shared utilities in `/core/services/intelligence/` that consolidate patterns
2. BaseAnalyticsService foundation that all domain intelligence services extend

**Consolidation Results:**
- **51 helper methods** analyzed across 6 Activity services
- **~640 lines** consolidated into 4 shared utilities + BaseAnalyticsService
- **38-49% reduction** in helper code duplication

**All Domain Intelligence Services:**
- Activity (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum (3): KU (Knowledge Units), PS (Path Steps), LP (Learning Paths)

All extend `BaseAnalyticsService` for graph analytics WITHOUT AI dependencies.

---

## BaseAnalyticsService Enhancements (January 2026)

### __slots__ Architectural Guard

**Purpose:** Enforce "Analytics must never depend on AI" at runtime.

```python
# File: /core/services/base_analytics_service.py

class BaseAnalyticsService(Generic[B]):
    """
    Foundation for all intelligence services.

    CRITICAL: Analytics services work WITHOUT AI (no llm, no embeddings).
    AI features go in separate BaseAIService subclasses.
    """

    # Architectural constraint: Restrict attributes to prevent AI coupling
    __slots__ = ("backend", "event_bus", "graph_intel", "insight_store", "logger", "relationships")

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
# File: /core/services/base_analytics_service.py

async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: UserUID,
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
# File: /core/services/principles/_alignment_intelligence_mixin.py

from core.models.enums.principle_enums import AlignmentLevel
from core.models.shared.dual_track import DualTrackResult

async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: UserUID,
    user_alignment_level: AlignmentLevel,
    user_evidence: str,
    user_reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
    """Compare user's declared alignment vs system-measured alignment."""
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_alignment_level,     # Vision: AlignmentLevel.ALIGNED
        user_evidence=user_evidence,         # Vision: "I always act with integrity"
        user_reflection=user_reflection,
        system_calculator=self._calculate_system_alignment_for_dual_track,  # Action: measures actual behavior
        level_scorer=self._alignment_level_to_score,         # delegates to AlignmentLevel.to_score()
        entity_type=EntityType.PRINCIPLE.value,
    )

async def _calculate_system_alignment_for_dual_track(
    self, principle: Principle, user_uid: UserUID
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
    user_score=0.85,  # AlignmentLevel.ALIGNED.to_score()
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
# Declared on any BaseAnalyticsService subclass:

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
│   └── _analyze_entity_with_typed_context() # Template: fetch + typed analyze

/core/services/intelligence/
├── __init__.py                       # Re-exports all shared utilities
├── _core_intelligence_mixin.py       # Shared get_with_context core (inherited by domain services)
├── recommendation_engine.py          # Phase 1: Fluent recommendation builder
├── metrics_calculator.py             # Phase 2: Shared calculations (generic static math)
├── metrics_calculators.py            # Domain-specific path-aware metrics functions
├── pattern_analyzer.py               # Phase 3: Pattern detection
├── trend_analyzer.py                 # Phase 4: Trend classification
└── path_aware_analyzer.py            # Cascade impact + path-strength recommendations

/core/models/shared/
└── dual_track.py                     # DualTrackResult[L] generic model

All 9 Domain Intelligence Services extend BaseAnalyticsService:
├── tasks/tasks_intelligence_service.py
├── goals/goals_intelligence_service.py
├── habits/habits_intelligence_service.py
├── events/events_intelligence_service.py
├── choices/choices_intelligence_service.py
├── principles/principles_intelligence_service.py
├── ku/ku_intelligence_service.py
├── ps/ps_intelligence_service.py
└── lp/lp_intelligence_service.py
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
| `add_conditional(condition, message)` | Add recommendation if condition is True |
| `add_message(message)` | Add recommendation unconditionally |
| `build()` | Return accumulated recommendations as list |

### Services Using RecommendationEngine

| Service | Consuming Methods |
|---------|-------------------|
| Tasks | `_generate_behavioral_recommendations` (`tasks/_analytics_mixin.py`) |
| Goals | `_generate_prediction_recommendations` (`goals/_predictive_mixin.py`) |
| Events | `_generate_scheduling_recommendations` (`events/_analytics_mixin.py`) |
| Principles | `_generate_adherence_recommendations` (`_alignment_intelligence_mixin.py`), `_generate_conflict_recommendations` (`_influence_mixin.py`) |

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

# Extractors as named functions (SKUEL012: no lambdas)
def get_score(x) -> float: return x.score
def get_weight(x) -> float: return x.weight
consistency = MetricsCalculator.weighted_average(data, get_score, get_weight)
```

### Key Methods

| Method | Purpose | Example Use |
|--------|---------|-------------|
| `weighted_average(items, value_fn, weight_fn)` | Compute weighted average | Consistency scores |
| `sigmoid_scale(value, midpoint, steepness)` | Apply S-curve scaling | Progress factors |
| `clamp(value, min_val, max_val)` | Constrain value to range | Score bounds |
| `combine_weighted_factors(factors, weights)` | Combine multiple factors | Probability calculation |
| `calculate_ratio(numerator, denominator, default)` | Safe division | Completion rates |
| `calculate_harmony_score(total_items, conflict_count)` | Harmony from conflicts | Principle alignment |

### Services Using MetricsCalculator

| Service | Methods Used |
|---------|--------------|
| Goals (`_predictive_mixin.py`) | `sigmoid_scale`, `weighted_average`, `combine_weighted_factors`, `clamp` |
| Habits (`_behavioral_signals_mixin.py`) | `clamp` |
| Principles (`_alignment_intelligence_mixin.py`, `_influence_mixin.py`) | `calculate_ratio`, `calculate_harmony_score` |

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
| `detect_by_indicator_tuples(...)` | Find patterns via (indicator, weight) tuples |
| `extract_skill_keywords(...)` | Extract skill-shaped keywords from text |
| `extract_dict_field_counts(dict, field_keys)` | Count list lengths from dict fields |
| `identify_factors(entities, conditions)` | Identify matching conditions |
| `find_peak_time(entities, time_extractor)` | Find peak activity hour |

### Services Using PatternAnalyzer

| Service | Methods Used |
|---------|--------------|
| Tasks (`_analytics_mixin.py`) | `find_peak_time`, `identify_factors` |
| Principles (`_alignment_intelligence_mixin.py`) | `extract_dict_field_counts` |
| Knowledge intelligence (`activity_knowledge_intelligence_service.py`) | `extract_word_frequencies`, `detect_by_keywords`, `detect_by_indicator_tuples`, `extract_skill_keywords` |

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

## Context Analysis Template (Canonical Typed Reader)

**Location:** `/core/services/base_analytics_service.py` (`_analyze_entity_with_typed_context`)

**Purpose:** THE template method in BaseAnalyticsService that consolidates the common
"fetch entity → get typed cross-domain context → calculate metrics → generate
recommendations → return" pattern. It sources its context from the single canonical
reader `UnifiedRelationshipService.get_cross_domain_context_typed` — the factory-built
**path-aware** context (`core/models/graph/path_aware_types.py`). All 6 activity domains
run on this one path (the legacy UID-family / `from_dict` reader was deleted in the
intent-traversal ↔ registry convergence cleanup).

### Usage

```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
    analysis_result = await self._analyze_entity_with_typed_context(
        uid=uid,
        metrics_fn=calculate_goal_progress_metrics,
        recommendations_fn=goal_recommendations,
        min_confidence=0.7,  # Optional kwargs (depth, min_confidence) supported
    )

    if analysis_result.is_error:
        return Result.fail(analysis_result)

    # Access via dict (template returns dict, not object)
    analysis = analysis_result.value
    goal = analysis["entity"]
    context = analysis["context"]  # path-aware GoalCrossContext
    metrics = analysis["metrics"]
    recommendations = analysis["recommendations"]

    # Build domain-specific response...
```

### Template Method Signature

```python
async def _analyze_entity_with_typed_context(
    self,
    uid: str,
    metrics_fn: Callable,          # (entity, path_aware_context) -> dict
    recommendations_fn: Callable | None = None,  # (entity, context, metrics) -> list
    **context_kwargs: Any,         # min_confidence, depth (forwarded to
                                   # get_cross_domain_context_typed)
) -> Result[dict[str, Any]]:
```

There is no `context_type` parameter — the typed reader resolves the domain context type
itself via the per-domain `*CrossContext.from_categorized` factory seam.

### Return Structure

```python
{
    "entity": <domain model>,
    "context": <path-aware cross-domain context>,
    "metrics": <calculated metrics dict>,
    "recommendations": <list of recommendations>,
}
```

### Services Using the Template

| Service | Path-aware metrics function |
|---------|-----------------------------|
| Tasks | `calculate_task_cross_domain_metrics` |
| Goals | `calculate_goal_progress_metrics` |
| Habits | `calculate_habit_integration_metrics` |
| Events | `calculate_event_performance_metrics` |
| Choices | `calculate_choice_impact_metrics` / `calculate_decision_metrics` |
| Principles | `calculate_principle_alignment_metrics` |

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

For path-aware metrics calculators (domain-specific, over the canonical typed reader):
```python
from core.services.intelligence import (
    calculate_goal_progress_metrics,
    calculate_habit_integration_metrics,
    calculate_event_performance_metrics,
    calculate_principle_alignment_metrics,
    calculate_task_cross_domain_metrics,
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
# Integration pipelines exercising the shared utilities end-to-end
uv run pytest tests/integration/test_goals_analytics_pipeline.py -v
uv run pytest tests/integration/test_habits_analytics_pipeline.py -v
uv run pytest tests/integration/test_cross_domain_context_pipeline.py -v

# Dual-track assessment behavior
uv run pytest tests/unit/test_principles_alignment_tracking.py -v
```

---

## See Also

- **BaseAnalyticsService:** `/core/services/base_analytics_service.py`
- **ADR-024:** BaseAnalyticsService Migration
- **Individual Domain Guides:** See `INTELLIGENCE_SERVICES_INDEX.md`
