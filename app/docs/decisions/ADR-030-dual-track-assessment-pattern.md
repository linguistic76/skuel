# ADR-030: Dual-Track Assessment Pattern (BaseAnalyticsService Extension)

**Status:** Accepted
**Date:** 2026-01-18
**Author:** Claude (with Mike)
**Category:** Pattern/Practice

## Context

SKUEL's core philosophy states: **"The user's vision is understood via the words they use to communicate, the UserContext is determined via user's actions."**

This insight was first implemented in LifePath's `WordActionAlignment` and recently extended to Principles via `assess_with_user_input()`. The pattern is generalizable across all Activity Domains.

### The Pattern

| Track | Source | Data |
|-------|--------|------|
| **Vision** | User self-assessment | "I feel aligned with integrity" |
| **Action** | System measurement | Goals/habits/choices expressing the principle |
| **Insight** | Gap analysis | Perception vs reality comparison |

### Current Implementations

1. **LifePath** - `WordActionAlignment` (existing)
2. **Principles** - `assess_with_user_input()` in PrinciplesAlignmentService
3. **All 6 Activity Domains** - Dual-track via `_dual_track_assessment()` template

### Activity Domain Implementations (January 2026)

| Domain | Method | Level Enum | System Metrics |
|--------|--------|------------|----------------|
| **Principles** | `assess_alignment_dual_track()` | `AlignmentLevel` | Expression count, goal alignment, behavioral consistency |
| **Tasks** | `assess_productivity_dual_track()` | `ProductivityLevel` | Completion rate, overdue ratio, on-time rate (custom impl*) |
| **Goals** | `assess_progress_dual_track()` | `ProgressLevel` | Progress %, milestone completion, status factor |
| **Habits** | `assess_consistency_dual_track()` | `ConsistencyLevel` | Success rate, current streak, best streak |
| **Events** | `assess_engagement_dual_track()` | `EngagementLevel` | Attendance rate, goal support, habit reinforcement |
| **Choices** | `assess_decision_quality_dual_track()` | `DecisionQualityLevel` | Outcome quality, principle alignment, confidence calibration |

**Note on Tasks:** Tasks uses a custom implementation (not the template) because it assesses USER productivity across all tasks, not a single entity. The template expects `uid → entity lookup`, which doesn't apply for user-level assessments. The custom implementation follows the same DualTrackResult contract with `entity_uid=user_uid` and `entity_type="productivity"`.

### Future Extensions

| Domain | User Self-Assessment | System Measurement |
|--------|---------------------|-------------------|
| **Knowledge** | "I've mastered this" | Substance score |

## Decision

**Extend `BaseAnalyticsService` with a `_dual_track_assessment()` template method.**

### Rejected Alternative: DualTrackAssessmentMixin

| Concern | Mixin | BaseAnalyticsService |
|---------|-------|------------------------|
| Scope | Too broad (any service) | Correct scope (intelligence) |
| Dependencies | Must re-specify | Already available |
| Philosophy | "Bolted on" | "Fundamental" |
| One Path Forward | Creates alternative | Extends single path |
| Inheritance | Composition required | Automatic for 10 services |

### Rationale

1. **Dual-track IS intelligence work** - Comparing user perception with measured behavior is core intelligence, not a utility.

2. **Infrastructure exists** - `BaseAnalyticsService` already has `backend`, `relationships`, `event_bus`, and `_analyze_entity_with_context()` template.

3. **Template pattern matches** - The existing `_analyze_entity_with_context()` is 80% of what we need. Extending it maintains consistency.

4. **One Path Forward** - All 10 domain intelligence services inherit from `BaseAnalyticsService`. Adding the method there means automatic availability without additional composition.

5. **Grounded design** - This "roots it deepest into the codebase" rather than existing as an add-on.

## Implementation

### Phase 1: Generic Result Model

Created `core/models/shared/dual_track.py` with `DualTrackResult[T]`:

```python
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

L = TypeVar("L")  # Level enum type


@dataclass(frozen=True)
class DualTrackResult(Generic[L]):
    """
    Generic dual-track assessment result.

    Captures both user self-assessment and system measurement,
    enabling gap analysis between perception and reality.
    """
    entity_uid: str
    entity_type: str  # EntityType.value

    # USER-DECLARED (Vision)
    user_level: L
    user_score: float  # 0.0-1.0 normalized
    user_evidence: str
    user_reflection: str | None

    # SYSTEM-CALCULATED (Action)
    system_level: L
    system_score: float  # 0.0-1.0 normalized
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS (Insight)
    perception_gap: float  # Absolute difference (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # GENERATED INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

    def has_perception_gap(self, threshold: float = 0.15) -> bool:
        """Check if gap exceeds threshold."""
        return self.perception_gap >= threshold

    def is_self_aware(self) -> bool:
        """Check if user perception matches system measurement."""
        return self.gap_direction == "aligned"
```

### Phase 2-3: BaseAnalyticsService Extension

Added to `core/services/base_analytics_service.py`:

```python
async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: str,
    # USER-DECLARED (Vision)
    user_level: L,
    user_evidence: str,
    user_reflection: str | None,
    # SYSTEM CALCULATION
    system_calculator: Callable[
        [Any, str], Awaitable[tuple[L, float, list[str]]]
    ],
    # LEVEL SCORING (domain-specific enum → float)
    level_scorer: Callable[[L], float],
    # OPTIONAL CUSTOMIZATION
    entity_type: str = "",
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Result[DualTrackResult[L]]:
    """Template method for dual-track assessment."""
```

Also added:
- `_calculate_perception_gap()` - Gap calculation
- `_default_gap_insights()` - Default insight generation
- `_default_gap_recommendations()` - Default recommendation generation

### Phase 4: Domain Implementation Example

In `PrinciplesIntelligenceService`:

```python
async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: str,
    user_alignment_level: AlignmentLevel,
    user_evidence: str,
    user_reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
    """Dual-track alignment assessment for principles."""
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_alignment_level,
        user_evidence=user_evidence,
        user_reflection=user_reflection,
        system_calculator=self._calculate_system_alignment_for_dual_track,
        level_scorer=self._alignment_level_to_score,
        entity_type="principle",
        insight_generator=self._generate_principle_gap_insights,
        recommendation_generator=self._generate_principle_gap_recommendations,
        store_callback=self._store_alignment_assessment,
    )
```

## Files Modified

| File | Change |
|------|--------|
| `core/models/shared/__init__.py` | NEW: Package init |
| `core/models/shared/dual_track.py` | NEW: Generic `DualTrackResult[T]` model |
| `core/models/enums/activity_enums.py` | Add 5 level enums: ProductivityLevel, ProgressLevel, ConsistencyLevel, EngagementLevel, DecisionQualityLevel |
| `core/services/base_analytics_service.py` | Add `_dual_track_assessment()` template and helpers |
| `core/services/principles/principles_intelligence_service.py` | Add `assess_alignment_dual_track()` implementation |
| `core/services/tasks/tasks_intelligence_service.py` | Add `assess_productivity_dual_track()` implementation |
| `core/services/goals/goals_intelligence_service.py` | Add `assess_progress_dual_track()` implementation |
| `core/services/habits/habits_intelligence_service.py` | Add `assess_consistency_dual_track()` implementation |
| `core/services/events/events_intelligence_service.py` | Add `assess_engagement_dual_track()` implementation |
| `core/services/choices/choices_intelligence_service.py` | Add `assess_decision_quality_dual_track()` implementation |
| `docs/decisions/ADR-030-dual-track-assessment-pattern.md` | NEW: This ADR |

## Migration Path

1. **Phase 1** (January 2026): Add generic model and template to BaseAnalyticsService ✅
2. **Phase 2**: Implement for Principles (demonstrate pattern) ✅
3. **Phase 3**: Implement for Tasks (productivity self-assessment) ✅
4. **Phase 4**: Implement for Goals (progress self-assessment) ✅
5. **Phase 5**: Implement for Habits (consistency self-assessment) ✅
6. **Phase 6**: Implement for Events (engagement self-assessment) ✅
7. **Phase 7**: Implement for Choices (decision quality self-assessment) ✅
8. **Future**: Extend to Knowledge domain as needed

## Verification

1. **Unit tests**: Test `_dual_track_assessment()` with mock calculators
2. **Integration**: Verify Principles endpoint returns dual-track response
3. **MyPy**: Ensure generic `DualTrackResult[L]` type-checks correctly
4. **Linter**: Run `uv run python scripts/lint_skuel.py`

## Consequences

### Positive
- Unified pattern across all intelligence services
- No additional mixins or composition required
- Automatic inheritance for all 10 domain intelligence services
- Consistent API response structure
- Enables cross-domain perception gap synthesis in UserContextIntelligence

### Negative
- Adds complexity to BaseAnalyticsService (~200 lines)
- Domain-specific calculators must be provided by each service
- Existing `assess_with_user_input()` in PrinciplesAlignmentService can coexist

### Neutral
- Each domain can choose to implement or not
- Existing implementations continue to work

## Future Extensions

Once all Activity Domains implement dual-track:

```python
# In UserContextIntelligence
async def get_cross_domain_perception_analysis(
    self, user_uid: str
) -> Result[dict[str, Any]]:
    """
    Synthesize perception gaps across all domains.

    Returns insights like:
    - "You consistently underestimate yourself across Goals and Habits"
    - "Your self-perception is accurate for Principles but optimistic for Tasks"
    """
```

## References

- LifePath `WordActionAlignment`: `core/models/lifepath/`
- Principles alignment service: `core/services/principles/principles_alignment_service.py`
- Principles intelligence service: `core/services/principles/principles_intelligence_service.py`
- BaseAnalyticsService: `core/services/base_analytics_service.py`
- ADR-024: BaseAnalyticsService Migration
