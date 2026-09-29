# BaseAnalyticsService Quick Reference

## File Locations

| File | Purpose |
|------|---------|
| `core/services/base_analytics_service.py` | The base class |
| `core/services/base_ai_service.py` | The AI base class (separate skill) |
| `core/services/intelligence/_core_intelligence_mixin.py` | `_CoreIntelligenceMixin[T]` — shared `get_with_context()` |
| `core/services/intelligence/metrics_calculators.py` | Per-domain `metrics_fn` / `recommendations_fn` |
| `core/services/intelligence/recommendation_engine.py` | `RecommendationEngine` |
| `core/services/intelligence/metrics_calculator.py` | `MetricsCalculator` |
| `core/services/intelligence/pattern_analyzer.py` | `PatternAnalyzer` |
| `core/services/intelligence/trend_analyzer.py` | `Trend` and the trend functions |
| `core/ports/intelligence_protocols.py` | `KnowledgeIntelligenceOperations` |
| `adapters/inbound/route_factories/intelligence_route_factory.py` | `IntelligenceOperations`, `IntelligenceRouteFactory` |

### The services

| Domain | File |
|--------|------|
| Tasks | `core/services/tasks/tasks_intelligence_service.py` |
| Goals | `core/services/goals/goals_intelligence_service.py` |
| Habits | `core/services/habits/habits_intelligence_service.py` |
| Events | `core/services/events/events_intelligence_service.py` |
| Choices | `core/services/choices/choices_intelligence_service.py` |
| Principles | `core/services/principles/principles_intelligence_service.py` |
| KU | `core/services/ku/ku_intelligence_service.py` |
| PS | `core/services/ps/ps_intelligence_service.py` |
| LP | `core/services/lp/lp_intelligence_service.py` |
| Shared knowledge | `core/services/knowledge/activity_knowledge_intelligence_service.py` |
| Corpus health | `core/services/analytics/knowledge_health_service.py` |

---

## Imports

```python
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin

from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
from adapters.inbound.route_factories import IntelligenceOperations, IntelligenceRouteFactory

from core.services.intelligence import (
    MetricsCalculator,
    PatternAnalyzer,
    RecommendationEngine,
    Trend,
    analyze_activity_trajectory,
    analyze_completion_trend,
    analyze_trend_with_details,
    compare_progress_to_expected,
    determine_trend_from_rate,
)

from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships import UnifiedRelationshipService

from core.utils.result_simplified import Errors, Result
```

`adapters.inbound.route_factories` is imported by route modules, never by `core/` (SKUEL022).

---

## Class Signature

```python
class BaseAnalyticsService(Generic[B, T]):
    _service_name: ClassVar[str | None] = None
    _require_relationships: ClassVar[bool] = False
    _require_graph_intel: ClassVar[bool] = False
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: Any | None = None,  # boundary: UnifiedRelationshipService, params vary per domain
        event_bus: Any | None = None,  # boundary: EventBusOperations
        insight_store: Any | None = None,  # boundary: InsightStore
    ) -> None: ...
```

---

## Method Signatures

### Helpers

```python
def _to_domain_model[MT](
    self,
    dto_or_dict: Any,  # boundary: model, DTO or dict
    dto_class: type,
    model_class: type[MT],
) -> MT: ...

async def _publish_event(self, event: Any) -> None: ...  # boundary: any BaseEvent subclass
```

`_fetch_entity_or_fail(uid)` returns the entity in a `Result`, or a failed `Result` to propagate.

### Templates

The base is generic over nine domains, so the entity and the typed context are not pinned in
its signatures. `Entity` and `Context` below stand for the domain model and its
`{Domain}CrossContext`.

```python
type Metrics = dict[str, Any]  # boundary: per-domain metrics map

async def _analyze_entity_with_typed_context(
    self,
    uid: str,
    metrics_fn: Callable[[Entity, Context], Metrics],
    recommendations_fn: Callable[[Entity, Context, Metrics], list[str]] | None = None,
    **context_kwargs: Any,  # boundary: depth, min_confidence — forwarded to the typed reader
) -> Result[dict[str, Any]]: ...  # boundary: {entity, metrics, recommendations, context}

async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: UserUID,
    user_level: L,
    user_evidence: str,
    user_reflection: str | None,
    system_calculator: Callable[[Entity | None, str], Awaitable[tuple[L, float, list[str]]]],
    level_scorer: Callable[[L], float],
    entity_type: str = "",
    require_entity: bool = True,
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Entity | None, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, DualTrackResult[L]], Awaitable[None]] | None = None,
) -> Result[DualTrackResult[L]]: ...

async def _store_dual_track_checkin(self, uid: str, result: DualTrackResult[L]) -> None: ...
```

In the base itself the `Entity` and `Context` positions are written `Any`.

### The route-facing three

```python
# inherited from _CoreIntelligenceMixin[T]
async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]: ...

# written per service
async def get_performance_analytics(
    self, user_uid: UserUID, period_days: int = 30
) -> Result[dict[str, Any]]: ...  # boundary: per-domain analytics payload

async def get_domain_insights(
    self, uid: str, min_confidence: float = 0.7
) -> Result[dict[str, Any]]: ...  # boundary: per-domain insights payload
```

### Dual-track methods

| Service | Method | Level enum |
|---------|--------|------------|
| Principles | `assess_alignment_dual_track` | `AlignmentLevel` |
| Goals | `assess_progress_dual_track` | `ProgressLevel` |
| Habits | `assess_consistency_dual_track` | `ConsistencyLevel` |
| Tasks | `assess_productivity_dual_track` | `ProductivityLevel` |
| Events | `assess_engagement_dual_track` | `EngagementLevel` |
| Choices | `assess_decision_quality_dual_track` | `DecisionQualityLevel` |
| KU | `assess_mastery_dual_track` | `MasteryLevel` |

`AlignmentLevel` is in `core/models/enums/principle_enums.py`; the others are in
`core/models/enums/activity_enums.py`. Each has `to_score()` and `from_score()`.

---

## Generated Routes

`IntelligenceRouteFactory` registers three `GET` routes per wired domain. The user comes from
the session — no route takes a `user_uid` parameter.

| Method | Route | Query parameters |
|--------|-------|------------------|
| `get_performance_analytics` | `GET /api/{domain}/analytics` | `period_days=30` |
| `get_with_context` | `GET /api/{domain}/context` | `uid`, `depth=2` |
| `get_domain_insights` | `GET /api/{domain}/insights` | `uid`, `min_confidence=0.7` |

Wired: `tasks`, `goals`, `habits`, `events`, `choices`, `principles`, `path-steps`, `pathways`.
Not wired: KU.

---

## Facade Access

```python
context_result = await tasks_service.intelligence.get_with_context(task_uid)
if context_result.is_error:
    return Result.fail(context_result)
task, graph_context = context_result.value
```

`intelligence` is a slot on all six Activity facades and on the KU, PS and LP facades.

---

## Analytics vs AI

| Aspect | `BaseAnalyticsService` | `BaseAIService` |
|--------|------------------------|-----------------|
| Dependencies | `graph_intel`, `relationships` | `llm_service`, `embeddings_service` |
| Tier | CORE and FULL | FULL only |
| Facade slot | `.intelligence` | `.ai` — `None` at CORE |
| Logger prefix | `skuel.analytics.*` | `skuel.ai.*` |

See [base-ai-service](../base-ai-service/SKILL.md).
