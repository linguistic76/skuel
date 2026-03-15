---
title: Intelligence Services - Master Index
updated: 2026-01-24
category: intelligence
status: current
related_skills:
- base-ai-service
- base-analytics-service
tracking: conceptual
last_reviewed: 2026-01-24
review_frequency: annual
---
# Intelligence Services - Master Index

**Last Updated:** January 24, 2026

## Overview

SKUEL's intelligence layer provides graph-based analytics and insights across all entity types. The unified architecture uses a **two-tier design** (ADR-030):

- **`BaseAnalyticsService`** - Graph analytics with NO AI dependencies (all 10 domain services extend this)
- **`BaseAIService`** - Optional AI-powered features (LLM, embeddings) for future use

The app functions fully without any LLM dependencies - AI services enhance but are not required.

**Total Intelligence Services:** 13
- **Activity Domains:** 6 (Tasks, Goals, Habits, Events, Choices, Principles)
- **Curriculum Domains:** 4 (KU, LS, LP, MOC)
- **Meta Intelligence:** 1 (UserContext - central intelligence hub)
- **Cross-Cutting:** 1 (Askesis - life context synthesis)
- **Specialized Graph:** 1 (ZPDService - curriculum ZPD graph analytics — FULL tier only)

**Note:** Finance is a standalone bookkeeping domain (no intelligence service).

**ZPDService** (`core/services/zpd/zpd_service.py`) is a specialized curriculum graph analytics service, distinct from the 10 `BaseAnalyticsService` subclasses. It does NOT extend `BaseAnalyticsService` — it delegates Neo4j queries to `ZPDBackend` (`adapters/persistence/neo4j/zpd_backend.py`) and computes Zone of Proximal Development assessments from the results. Only available in FULL tier; gracefully degrades (returns empty assessment) when curriculum engagement relationships are absent.

## Quick Start

**Skills:** [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md), [@base-ai-service](../../.claude/skills/base-ai-service/SKILL.md)

## One Path Forward (ADR-029)

**January 8, 2026:** GraphNativeMixin removed from UserContextIntelligence (366 lines).

**Architecture Alignment:**
- UserContextIntelligence uses **modular mixin architecture** (ADR-021)
- Simple context methods (8 lines) for cached analysis
- Domain services provide fresh Cypher queries when needed
- **No intermediate abstraction layers** - clear two-path model

**Deleted:** GraphNativeMixin with 4 methods creating alternative query paths
**Result:** UserContext methods are simple delegates to underlying data, intelligence services use domain services directly

**See:** [ADR-029](../decisions/ADR-029-graphnative-service-removal.md)

---

## Architecture Pattern

All domain intelligence services (10 of 11) follow the `BaseAnalyticsService` pattern (ADR-024, updated January 2026):

```python
class {Domain}IntelligenceService(BaseAnalyticsService[{Domain}Operations, {DomainModel}]):
    _service_name = "{domain}.analytics"

    def __init__(self, backend, graph_intelligence_service, ...):
        super().__init__(backend, graph_intelligence_service, ...)
        # NOTE: No embeddings_service or llm_service - these are analytics services
```

**Exception:** UserContextIntelligence uses a modular package architecture (ADR-021) with mixin composition instead of BaseAnalyticsService inheritance.

**Two-Tier Design (January 2026):**
| Layer | Base Class | Dependencies | Purpose |
|-------|------------|--------------|---------|
| **Analytics** | `BaseAnalyticsService` | Graph queries + Python | Works without LLM |
| **AI** | `BaseAIService` | LLM + Embeddings | Optional AI features |

### File Naming Convention (Intelligence vs Analytics)

**Why `*_intelligence_service.py` not `*_analytics_service.py`?**

The naming reflects a semantic distinction:
- **File name** = User-facing capability (what it provides)
- **Base class** = Implementation detail (how it's built)

| Layer | File Pattern | Base Class | Rationale |
|-------|-------------|-----------|-----------|
| **Intelligence** | `*_intelligence_service.py` | `BaseAnalyticsService` | "Intelligence" = insights + recommendations + analysis |
| **AI** | `*_ai_service.py` | `BaseAIService` | "AI" = LLM-powered semantic features |

**The convention:**
- `*IntelligenceService` = Graph analytics (NO AI) - the critical path
- `*AIService` = LLM/embeddings features (OPTIONAL) - the enhancement layer

All 10 domain intelligence services correctly extend `BaseAnalyticsService` - the name "Intelligence" describes what users get (actionable insights), while `BaseAnalyticsService` describes how it's implemented (graph queries + Python).

**Benefits:**
- Standardized initialization and logging
- Fail-fast validation (`_require_graph_intelligence()`, `_require_relationship_service()`)
- Consistent error handling via `Result[T]`
- Helper methods (`_to_domain_model()`)
- App runs without LLM dependencies (analytics-first design)

---

## IntelligenceOperations Protocol (January 2026)

All 10 domain intelligence services implement the standardized `IntelligenceOperations` protocol, enabling automatic route generation via `IntelligenceRouteFactory`.

**Protocol Methods:**
| Method | Returns | Purpose |
|--------|---------|---------|
| `get_with_context(uid, depth=2)` | `Result[tuple[T, GraphContext]]` | Entity with full graph neighborhood |
| `get_performance_analytics(user_uid, period_days=30)` | `Result[dict]` | User-specific analytics (or overall stats for shared content) |
| `get_domain_insights(uid, min_confidence=0.7)` | `Result[dict]` | Domain-specific intelligence and recommendations |

**Implementation Pattern:**
```python
# Each intelligence service uses GraphContextOrchestrator
if graph_intelligence_service:
    self.orchestrator = GraphContextOrchestrator[Task, TaskDTO](
        service=self,
        backend_get_method="get",
        dto_class=TaskDTO,
        model_class=Task,
        domain=Domain.TASKS,
    )

# Protocol methods delegate to orchestrator
async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Task, GraphContext]]:
    return await self.orchestrator.get_with_context(uid=uid, depth=depth)
```

**Routes Generated by IntelligenceRouteFactory:**
- `GET /api/{domain}/context?uid=...&depth=2`
- `GET /api/{domain}/analytics?period_days=30` (user_uid from session)
- `GET /api/{domain}/insights?uid=...&min_confidence=0.7`

**IntelligenceRouteFactory Security (January 2026):**
- **Content scope** via `scope` parameter (default: `ContentScope.USER_OWNED`)
- Activity Domains verify entity ownership before returning context/insights
- Shared content (KU, LS, LP, MOC) uses `scope=ContentScope.SHARED`
- Returns 404 (not 403) to prevent UID enumeration attacks

```python
from core.models.enums import ContentScope

# Factory with ownership verification (Activity Domains)
factory = IntelligenceRouteFactory(
    intelligence_service=tasks_service.intelligence,
    domain_name="tasks",
    scope=ContentScope.USER_OWNED,           # Default - ownership verification
    ownership_service=tasks_service,          # Must implement verify_ownership(uid, user_uid)
)

# Factory for shared content (Curriculum)
factory = IntelligenceRouteFactory(
    intelligence_service=lesson_service.intelligence,
    domain_name="lesson",
    scope=ContentScope.SHARED,                # No ownership checks
)
```

**FastHTML Route Parameter Style:**
Routes use function parameters with type hints (not `request.query_params`):
```python
async def context_route(request, uid: str, depth: int = 2) -> Result[Any]:
async def analytics_route(request, period_days: int = 30) -> Result[Any]:
async def insights_route(request, uid: str, min_confidence: float = 0.7) -> Result[Any]:
```

**Rollout Status (January 2026 - COMPLETE):**

| Service | Protocol Methods | Orchestrator | Status |
|---------|------------------|--------------|--------|
| TasksIntelligenceService | ✅ | ✅ | Complete |
| GoalsIntelligenceService | ✅ | ✅ (pilot) | Complete |
| HabitsIntelligenceService | ✅ | ✅ | Complete |
| EventsIntelligenceService | ✅ | ✅ | Complete |
| ChoicesIntelligenceService | ✅ | ✅ | Complete |
| PrinciplesIntelligenceService | ✅ | ✅ | Complete |
| KuIntelligenceService | ✅ | ✅ | Complete |
| LsIntelligenceService | ✅ | ✅ | Complete |
| LpIntelligenceService | ✅ | ✅ | Complete |
| MocIntelligenceService | ✅ | ✅ | Complete |

**Bug Fixes & Improvements (January 2026):**
- SUCCESS_RATE UNIT INCONSISTENCY: Fixed in `GoalsIntelligenceService` (Habit.success_rate is 0.0-1.0)
- Missing `is_on_track()`: Added to `Goal` model
- Unguarded `self.progress` calls: Added fail-fast guard
- Logging emoji: Removed from `IntelligenceRouteFactory`
- **Ownership verification**: Added to context/insights routes (security fix)
- **Parameter style consistency**: Routes use FastHTML function parameters with type hints

**Placeholder Convention (`_period_days`):**
The `period_days` parameter in `get_performance_analytics()` uses underscore prefix (`_period_days`) in 4 services (Goals, Habits, Choices, Principles) to indicate "API contract defined, implementation deferred". **Events** now fully implements period filtering (January 19, 2026). See CLAUDE.md § "Parameter Naming Convention".

**Tests:** 19/19 factory tests + 108/108 intelligence tests passing

---

## Dual-Track Assessment Pattern (ADR-030)

**Added:** January 18, 2026

SKUEL's core philosophy states: **"The user's vision is understood via the words they use to communicate, the UserContext is determined via user's actions."**

The Dual-Track Assessment Pattern implements this philosophy by comparing **user self-assessment (vision)** with **system measurement (action)** to generate perception gap analysis and insights.

### Template Method

`BaseAnalyticsService._dual_track_assessment()` provides a standardized template for all domains:

```python
async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: str,
    # USER-DECLARED (Vision)
    user_level: Any,
    user_evidence: str,
    user_reflection: str | None,
    # SYSTEM CALCULATION
    system_calculator: Callable[
        [str, str], Awaitable[tuple[Any, float, list[str]]]
    ],
    # LEVEL SCORING
    level_scorer: Callable[[Any], float],
    # OPTIONAL CUSTOMIZATION
    entity_type: str = "",
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
) -> Result[DualTrackResult[L]]
```

### Generic Result Model

`DualTrackResult[L]` is a generic frozen dataclass that captures both tracks:

```python
@dataclass(frozen=True)
class DualTrackResult(Generic[L]):
    entity_uid: str
    entity_type: str

    # USER-DECLARED (Vision)
    user_level: L           # Domain-specific level enum
    user_score: float       # 0.0-1.0 normalized
    user_evidence: str
    user_reflection: str | None

    # SYSTEM-CALCULATED (Action)
    system_level: L
    system_score: float
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS
    perception_gap: float   # Absolute difference
    gap_direction: str      # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]
```

### Domain Implementations

All 6 Activity Domain intelligence services implement dual-track assessment:

| Service | Method | Level Enum | System Metrics |
|---------|--------|------------|----------------|
| **Principles** | `assess_alignment_dual_track()` | `AlignmentLevel` | Goal alignment, choice consistency, habit support, entity count |
| **Tasks** | `assess_productivity_dual_track()` | `ProductivityLevel` | Completion rate, on-time %, overdue ratio, knowledge linking |
| **Goals** | `assess_progress_dual_track()` | `ProgressLevel` | Milestone completion, habit support, on-track %, consistency |
| **Habits** | `assess_consistency_dual_track()` | `ConsistencyLevel` | Completion rate, streak health, avg streak length, active ratio |
| **Events** | `assess_engagement_dual_track()` | `EngagementLevel` | Attendance rate, goal support, habit reinforcement, recency |
| **Choices** | `assess_decision_quality_dual_track()` | `DecisionQualityLevel` | Outcome quality, principle alignment, decision rate, confidence |

### Level Enums

Each domain has a level enum with bidirectional conversion methods:

```python
class ProductivityLevel(str, Enum):
    HIGHLY_PRODUCTIVE = "highly_productive"    # 0.85+
    PRODUCTIVE = "productive"                   # 0.70-0.85
    MODERATELY_PRODUCTIVE = "moderately_productive"  # 0.50-0.70
    STRUGGLING = "struggling"                   # 0.30-0.50
    UNPRODUCTIVE = "unproductive"              # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "ProductivityLevel": ...
```

### Usage Pattern

```python
# User provides self-assessment
result = await tasks_service.intelligence.assess_productivity_dual_track(
    user_uid="user.mike",
    user_productivity_level=ProductivityLevel.HIGHLY_PRODUCTIVE,
    user_evidence="I complete all my tasks on time",
    user_reflection="I feel very productive lately",
    period_days=30,
)

if result.is_ok:
    assessment = result.value
    if assessment.has_perception_gap():
        print(f"Gap: {assessment.gap_direction} ({assessment.perception_gap:.0%})")
        for insight in assessment.insights:
            print(f"  - {insight}")
```

### API Endpoints

Each domain exposes a dual-track endpoint:

```
POST /api/tasks/assess-productivity
POST /api/goals/assess-progress
POST /api/habits/assess-consistency
POST /api/events/assess-engagement
POST /api/choices/assess-decision-quality
POST /api/principles/assess-alignment
```

**Request Body:**
```json
{
    "user_level": "productive",
    "user_evidence": "I complete most tasks on time",
    "user_reflection": "Feeling good about my productivity",
    "period_days": 30
}
```

**Response:**
```json
{
    "entity_uid": "user.mike",
    "entity_type": "productivity_assessment",
    "user_level": "productive",
    "user_score": 0.775,
    "system_level": "moderately_productive",
    "system_score": 0.58,
    "perception_gap": 0.195,
    "gap_direction": "user_higher",
    "insights": ["Self-assessment exceeds measured productivity by ~20%"],
    "recommendations": ["Focus on reducing overdue tasks"]
}
```

### See Also

- [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)
- `core/models/shared/dual_track.py` - `DualTrackResult[L]` generic model
- `core/models/enums/activity_enums.py` - Level enums

---

## Shared Intelligence Utilities

**Guide:** [SHARED_INTELLIGENCE_UTILITIES.md](./SHARED_INTELLIGENCE_UTILITIES.md)

The 6 Activity Domain intelligence services share common patterns consolidated into 4 shared utilities + 1 template method (January 2026):

| Utility | Location | Purpose |
|---------|----------|---------|
| **RecommendationEngine** | `recommendation_engine.py` | Fluent builder for threshold-based recommendations |
| **MetricsCalculator** | `metrics_calculator.py` | Static utility methods for common calculations |
| **PatternAnalyzer** | `pattern_analyzer.py` | Pattern detection in text and data structures |
| **TrendAnalyzer** | `trend_analyzer.py` | Threshold-based trend classification |
| **Template Method** | `BaseAnalyticsService._analyze_entity_with_context()` | Fetch entity → get context → calculate metrics → generate recommendations |

**Consolidation Results:**
- **51 helper methods** analyzed across 6 services
- **~640 lines** consolidated into shared utilities
- **38-49% reduction** in helper code duplication

**Import Pattern:**
```python
from core.services.intelligence import (
    RecommendationEngine,
    MetricsCalculator,
    PatternAnalyzer,
    analyze_completion_trend,
    compare_progress_to_expected,
)
```

---

## Intelligence Services by Domain

### Activity (6)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **Tasks** | [TASKS_INTELLIGENCE.md](./TASKS_INTELLIGENCE.md) | ~935 | Knowledge generation, learning opportunities |
| **Goals** | [GOALS_INTELLIGENCE.md](./GOALS_INTELLIGENCE.md) | ~1,139 | Progress forecasting, predictive analytics |
| **Habits** | [HABITS_INTELLIGENCE.md](./HABITS_INTELLIGENCE.md) | ~539 | Streak patterns, habit formation insights |
| **Events** | [EVENTS_INTELLIGENCE.md](./EVENTS_INTELLIGENCE.md) | ~492 | Cross-domain impact, learning practice tracking |
| **Choices** | [CHOICES_INTELLIGENCE.md](./CHOICES_INTELLIGENCE.md) | ~679 | Decision support, outcome analysis |
| **Principles** | [PRINCIPLES_INTELLIGENCE.md](./PRINCIPLES_INTELLIGENCE.md) | ~650 | Alignment analysis, conflict detection |

---

### Curriculum (4)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **KU** | [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) | ~390 | Semantic recommendations, knowledge substance, per-user substance (January 2026) |
| **LS** | [LS_INTELLIGENCE.md](./LS_INTELLIGENCE.md) | ~394 | Readiness checks, practice completeness |
| **LP** | [LP_INTELLIGENCE.md](./LP_INTELLIGENCE.md) | 378 (facade) + 2,467 (sub-services) | Learning state analysis, content recommendations, adaptive sequencing |
| **MOC** | [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md) | ~777 | Navigation recommendations, coverage analysis, cross-domain bridges (January 2026) |

---

### Meta Intelligence (1)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **UserContext** | [USER_CONTEXT_INTELLIGENCE.md](./USER_CONTEXT_INTELLIGENCE.md) | ~3,124 (modular package) | Central hub, daily planning (flagship: `get_ready_to_work_on_today()`) |

---

### Cross-Cutting Intelligence (1)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **Askesis** | [ASKESIS_INTELLIGENCE.md](./ASKESIS_INTELLIGENCE.md) | ~1,180 (facade + 5 sub-services) | Life context synthesis, 13-domain recommendations (flagship: `get_daily_work_plan()`) |

**Note:** Askesis uses a custom facade pattern (not `BaseAnalyticsService`) because it synthesizes across all entity types rather than managing a single domain's entities.

---

## Common Features

### Inherited from BaseAnalyticsService

All domain intelligence services (except UserContext) inherit from `BaseAnalyticsService`:

**Fail-Fast Validation:**
```python
self._require_graph_intelligence("method_name")  # Ensures graph_intel available
self._require_relationship_service("method_name") # Ensures relationships available
```

**Standard Attributes:**
- `self.backend` - Domain operations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (optional, validated on use)
- `self.relationships` - UnifiedRelationshipService (optional)
- `self.event_bus` - EventBus (optional)
- `self.logger` - Hierarchical logger (`skuel.analytics.{domain}`)

**NOTE:** Analytics services explicitly DO NOT have `embeddings` or `llm` attributes. This is intentional - they work without AI dependencies. For AI features, use `BaseAIService`.

**Helper Methods:**
- `_to_domain_model()` - Convert DTO/dict to domain model

---

## Usage Patterns

### Access via Facade (Activity & Curriculum Domains)

All Activity and Curriculum domain services create intelligence internally:

```python
# Tasks example
tasks_service = TasksService(
    backend=tasks_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
)

# Access intelligence
insights = await tasks_service.intelligence.get_behavioral_insights(user_uid)
```

### Direct Instantiation (Meta Services)

UserContextIntelligence is created directly via factory:

```python
from core.services.user.intelligence import UserContextIntelligenceFactory

# Create with required domain services
user_intel = UserContextIntelligenceFactory.create(
    context=user_context,
    tasks_service=tasks_service,
    goals_service=goals_service,
    habits_service=habits_service,
    # ... 10 more required services
)

# Use flagship method
daily_plan = await user_intel.get_ready_to_work_on_today(user_uid)
```

---

## Dependencies

### Infrastructure Services

Intelligence services depend on shared infrastructure:

| Service | Purpose | Used By |
|---------|---------|---------|
| **GraphIntelligenceService** | Graph queries, context retrieval | All services |
| **OpenAIEmbeddingsService** | Semantic search, similarity | KU, LP, Tasks |
| **LLMService** | AI insights, text generation | KU, LP, UserContext |
| **UnifiedRelationshipService** | Relationship queries | Activity domains, Goals (REQUIRED) |

---

## Testing

### Unit Tests
```bash
# Test specific intelligence service
uv run python -m pytest tests/unit/services/test_{domain}_intelligence_service.py -v

# Test all intelligence services
uv run python -m pytest tests/unit/services/ -k "intelligence" -v
```

### Integration Tests
```bash
# Test with real backends
uv run python -m pytest tests/integration/intelligence/ -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_predict_goal_success" -v
```

---

## Migration Status (January 2026)

**Migrated to BaseAnalyticsService (ADR-024, updated ADR-030):**
- ✅ TasksIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ GoalsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ HabitsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ EventsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ ChoicesIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ PrinciplesIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ KuIntelligenceService (2026-01-08, updated 2026-01-18)
- ✅ LsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ LpIntelligenceService (2026-01-08, updated 2026-01-18)
- ✅ MocIntelligenceService (2026-01-11, updated 2026-01-18)

**Architecture Update (2026-01-18):**
- `BaseIntelligenceService` (old) → Replaced by `BaseAnalyticsService` + `BaseAIService`
- All 10 domain services now extend `BaseAnalyticsService` (NO AI deps)
- `BaseAIService` available for future AI-powered features

**IntelligenceOperations Protocol Rollout (2026-01-17):**
- ✅ All 10 domain services implement protocol methods
- ✅ GraphContextOrchestrator pattern consistent across all services
- ✅ Bug fixes applied (success_rate units, is_on_track(), progress guards)

**Standalone (modular package architecture):**
- UserContextIntelligence (ADR-021, mixin composition pattern)

---

## Service-Specific Highlights

### Activity Domains

**Tasks:**
- Knowledge extraction from action
- Learning opportunity discovery
- Cross-domain context categorization (unique semantic grouping)

**Goals:**
- Progress forecasting with velocity metrics
- Predictive analytics (success probability, habit impact, scenarios)
- Completion probability modeling (35% progress + 35% consistency + 15% time + 15% momentum)

**Habits:**
- Streak pattern analysis
- Knowledge reinforcement effectiveness (0-10 scale)
- Goal contribution strength calculation

**Events:**
- Cross-domain impact tracking
- Learning practice verification (knowledge substance philosophy)
- Schedule optimization with actionable insights

**Choices:**
- Decision complexity assessment
- Cascade impact analysis with PathAwareIntelligenceHelper
- Regret minimization through risk assessment

**Principles:**
- Cross-domain alignment measurement
- Multi-principle conflict detection
- Strength analysis (impact score 0-10)

### Curriculum Domains

**KU (Knowledge Units):**
- Semantic relationship analysis with confidence scoring
- Cross-domain knowledge connections
- Knowledge substance tracking (how knowledge is LIVED)
- Per-user substance calculation (January 2026 - KU-Activity Integration)
- New API: `GET /api/ku/{uid}/my-context` for personalized KU views

**LS (Learning Steps):**
- Lightweight intelligence (intentional design)
- Practice completeness scoring (1/3 contribution per type)
- Guidance strength calculation (40% principles + 60% choices)

**LP (Learning Paths):**
- Facade over 4 sub-services (LearningStateAnalyzer, LearningRecommendationEngine, ContentAnalyzer, ContentQualityAssessor)
- Learning state analysis (5 readiness states)
- Personalized content recommendations
- Quality assessment and similarity search

**MOC (Maps of Content):**
- Navigation recommendations based on shared content (January 2026)
- Content coverage analysis (KU, LP, Principle metrics)
- Cross-domain bridge strength calculation (40% count + 60% diversity)
- Section hierarchy depth analysis
- Event-driven coverage health assessment

### Meta Intelligence

**UserContext:**
- Central intelligence hub answering "What should I work on next?"
- 8 flagship methods across 5 mixins
- **Flagship method:** `get_ready_to_work_on_today()` - Daily planning based on goals, habits, knowledge, schedule
- Requires 13 domain services (6 Activity + 3 Curriculum + 3 Processing + 1 Temporal)
- Modular package architecture (~3,124 lines)

---

## See Also

### Architecture Documentation
- `/docs/intelligence/SHARED_INTELLIGENCE_UTILITIES.md` - **Shared utilities consolidation (5-phase guide)**
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - Unified base service pattern (now BaseAnalyticsService)
- `/docs/decisions/ADR-021-user-context-intelligence-modularization.md` - UserContext modular package
- `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` - Domain overview
- `/CLAUDE.md` - Intelligence Services Architecture section

### Implementation
- `/core/services/base_analytics_service.py` - Base class for domain analytics (NO AI deps)
- `/core/services/base_ai_service.py` - Base class for AI-powered features (optional)
- `/core/services/intelligence/` - **Shared utilities package (RecommendationEngine, MetricsCalculator, etc.)**
- `/core/services/infrastructure/graph_intelligence_service.py` - Graph queries
- `/core/services/embeddings_service.py` - Semantic search
- `/core/services/llm_service.py` - AI insights
- `/core/services/user/intelligence/` - UserContextIntelligence modular package

---

## Quick Start

### To add a new intelligence method:

1. Identify the domain (e.g., Tasks)
2. Open `/core/services/{domain}/{domain}_intelligence_service.py`
3. Add method following pattern:
   ```python
   async def get_new_insight(self, user_uid: str, ...) -> Result[dict[str, Any]]:
       self._require_graph_intelligence("get_new_insight")
       # Implementation
       return Result.ok({"insight": data})
   ```
4. Document in `/docs/intelligence/{DOMAIN}_INTELLIGENCE.md`
5. Add tests in `tests/unit/services/test_{domain}_intelligence_service.py`

### To use an intelligence method:

```python
result = await {domain}_service.intelligence.{method_name}(...)
if result.is_ok:
    data = result.value
    # Use data
else:
    error = result.expect_error()
    # Handle error
```

---

## Architecture Summary

**Total Intelligence Services:** 11
- 10 extend `BaseAnalyticsService` (unified pattern, NO AI deps)
- 1 uses modular package architecture (UserContext)

**Total Lines of Intelligence Code:** ~9,900+
- Activity Domains: ~4,434 lines
- Curriculum Domains: ~4,013 lines (facade + sub-services + MOC)
- Meta Intelligence: ~3,124 lines (modular package)

**Intelligence Philosophy:**
- Domain services provide focused, domain-specific intelligence
- UserContext synthesizes cross-domain intelligence for daily planning
- All services return `Result[T]` for consistent error handling
- Fail-fast validation ensures required dependencies are available
- Graph-native relationships eliminate N+1 queries

**January 2026 Achievements:**
- Complete intelligence architecture unification across all domains with BaseAnalyticsService pattern (ADR-024, ADR-030)
- Comprehensive documentation for all 11 services (6 Activity + 4 Curriculum + 1 Meta)
- Full migration including KU, LP, and MOC domains
- Shared utilities consolidation (5-phase consolidation reducing ~640 lines of duplicated helper code)
- **KU-Activity Integration Enhancement** (January 11, 2026): Per-user substance calculation via `calculate_user_substance()` and new `/api/ku/{uid}/my-context` endpoint
- **Finance Domain Simplification** (January 17, 2026): Finance reverted to standalone bookkeeping domain (no intelligence service)
- **IntelligenceOperations Protocol Rollout** (January 17, 2026): All 10 domain services implement standardized protocol with GraphContextOrchestrator pattern, enabling automatic route generation via IntelligenceRouteFactory
- **Dual-Track Assessment Pattern** (January 18, 2026 - ADR-030): All 6 Activity Domain intelligence services now support dual-track assessment comparing user self-assessment (vision) with system measurement (action) for perception gap analysis
