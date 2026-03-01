# BaseAnalyticsService Quick Reference

## File Locations

### Core Files

| File | Purpose |
|------|---------|
| `/core/services/base_analytics_service.py` | Base class (~608 lines) |
| `/core/services/base_ai_service.py` | AI base class (separate skill) |
| `/core/ports/intelligence_protocols.py` | IntelligenceOperations protocol |
| `/core/services/intelligence/orchestrator.py` | GraphContextOrchestrator |
| `/core/services/intelligence/recommendation_engine.py` | RecommendationEngine utility |
| `/core/services/intelligence/metrics_calculator.py` | MetricsCalculator utility |
| `/core/services/intelligence/pattern_analyzer.py` | PatternAnalyzer utility |
| `/core/services/intelligence/trend_analyzer.py` | TrendAnalyzer utility |

### Domain Intelligence Services

| Domain | File | Notes |
|--------|------|-------|
| Tasks | `/core/services/tasks/tasks_intelligence_service.py` | |
| Goals | `/core/services/goals/goals_intelligence_service.py` | |
| Habits | `/core/services/habits/habits_intelligence_service.py` | |
| Events | `/core/services/events/events_intelligence_service.py` | |
| Choices | `/core/services/choices/choices_intelligence_service.py` | |
| Principles | `/core/services/principles/principles_intelligence_service.py` | |
| KU | `/core/services/ku_intelligence_service.py` | top-level (not in ku/ subdir) |
| LS | `/core/services/ls/ls_intelligence_service.py` | |
| LP | `/core/services/lp_intelligence_service.py` | top-level (not in lp/ subdir) |

### Documentation

| File | Purpose |
|------|---------|
| `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` | Master index |
| `/docs/intelligence/SHARED_INTELLIGENCE_UTILITIES.md` | Shared utilities guide |
| `/docs/intelligence/{DOMAIN}_INTELLIGENCE.md` | Per-domain guides |
| `/docs/decisions/ADR-030-analytics-vs-ai-separation.md` | Architecture decision |

---

## Imports

### Base Class
```python
from core.services.base_analytics_service import BaseAnalyticsService
```

### Protocol
```python
from core.ports.intelligence_protocols import IntelligenceOperations
```

### Orchestrator
```python
from core.services.intelligence.orchestrator import GraphContextOrchestrator
```

### Shared Utilities
```python
from core.services.intelligence import (
    RecommendationEngine,
    MetricsCalculator,
    PatternAnalyzer,
    analyze_completion_trend,
    compare_progress_to_expected,
)
```

### Infrastructure Services
```python
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships import UnifiedRelationshipService
```

### Result Pattern
```python
from core.utils.result_simplified import Result
from core.utils.errors_simplified import Errors
```

---

## Class Signature

```python
class BaseAnalyticsService(Generic[B, T]):
    """Base class for domain analytics services (no AI dependencies)."""

    # Class attributes
    _service_name: ClassVar[str | None] = None
    _require_relationships: ClassVar[bool] = False
    _require_graph_intel: ClassVar[bool] = False
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None: ...
```

**NOTE:** No `embeddings_service` or `llm_service` - analytics services have no AI dependencies.

---

## Method Signatures

### Fail-Fast Guards

```python
def _require_graph_intelligence(self, operation: str) -> None:
    """Raises ValueError if graph_intel unavailable."""

def _require_relationship_service(self, operation: str) -> None:
    """Raises ValueError if relationships unavailable."""
```

### Helpers

```python
def _to_domain_model(
    self,
    dto_or_dict: Any,
    dto_class: type,
    model_class: type[T]
) -> T:
    """Convert DTO or dict to domain model."""

async def _publish_event(self, event: Any) -> None:
    """Publish event to bus if available."""
```

### Template Methods

```python
async def _analyze_entity_with_context(
    self,
    uid: str,
    context_method: str,           # e.g., "get_goal_cross_domain_context"
    context_type: type,            # e.g., GoalCrossContext
    metrics_fn: Callable[[Any, Any], dict[str, Any]],
    recommendations_fn: Callable[[Any, Any, dict], list[str]] | None = None,
    **context_kwargs: Any,
) -> Result[dict[str, Any]]:
    """Template for entity + context analysis."""

async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: str,
    user_level: L,
    user_evidence: str,
    user_reflection: str | None,
    system_calculator: Callable[[Any, str], Awaitable[tuple[L, float, list[str]]]],
    level_scorer: Callable[[L], float],
    entity_type: str = "",
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Result[DualTrackResult[L]]:
    """Template for dual-track assessment (vision vs action)."""
```

---

## Three Standardized Methods (All 9 Services)

```python
async def get_with_context(
    self, uid: str, depth: int = 2
) -> Result[tuple[T, GraphContext]]:
    """Entity with full graph neighborhood."""

async def get_performance_analytics(
    self, user_uid: str, period_days: int = 30
) -> Result[dict[str, Any]]:
    """User-specific analytics."""

async def get_domain_insights(
    self, uid: str, min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
    """Domain-specific intelligence."""
```

---

## Generated Routes (IntelligenceRouteFactory)

| Method | Route | Parameters |
|--------|-------|------------|
| `get_with_context` | `GET /api/{domain}/context` | `?uid=...&depth=2` |
| `get_performance_analytics` | `GET /api/{domain}/analytics` | `?user_uid=...&period_days=30` |
| `get_domain_insights` | `GET /api/{domain}/insights` | `?uid=...&min_confidence=0.7` |

---

## Instance Attributes After Init

| Attribute | Type | Nullable | Purpose |
|-----------|------|----------|---------|
| `backend` | `B` | No | Domain operations |
| `graph_intel` | `GraphIntelligenceService` | Yes | Graph queries |
| `relationships` | `UnifiedRelationshipService` | Yes | Relationships |
| `event_bus` | `EventBus` | Yes | Event publishing |
| `logger` | `Logger` | No | Hierarchical logger |
| `orchestrator` | `GraphContextOrchestrator` | Yes* | Context retrieval |

*Orchestrator is created only if `graph_intelligence_service` is provided.

---

## Common Pattern: Facade Access

Access intelligence through domain facades:

```python
# At bootstrap
tasks_service = TasksService(
    backend=tasks_backend,
    graph_intelligence_service=graph_intel,
)

# Usage
insights = await tasks_service.intelligence.get_behavioral_insights(user_uid)
context = await tasks_service.intelligence.get_with_context(task_uid)
```

---

## Key Difference: Analytics vs AI

| Aspect | BaseAnalyticsService | BaseAIService |
|--------|---------------------|---------------|
| **Dependencies** | graph_intel, relationships | llm, embeddings |
| **AI Required?** | No | Yes (configurable) |
| **Purpose** | Graph analytics | AI enhancements |
| **App Runs Without?** | Yes (full capacity) | Yes (limited features) |
| **Logger Prefix** | `skuel.analytics.*` | `skuel.ai.*` |

For AI features, see the **[base-ai-service](../base-ai-service/SKILL.md)** skill.
