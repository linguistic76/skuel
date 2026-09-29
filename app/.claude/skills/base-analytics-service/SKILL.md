---
name: base-analytics-service
description: Expert guide for creating and modifying domain analytics services using BaseAnalyticsService. Use when adding analytics methods, implementing KnowledgeIntelligenceOperations or the route factory's IntelligenceOperations protocol, cross-domain context retrieval (mechanism B / get_with_context), or working with the 9 domain intelligence services.
allowed-tools: Read, Grep, Glob
---

# BaseAnalyticsService: Domain Analytics Pattern

> "Graph analytics without AI dependencies"

`BaseAnalyticsService[B, T]` (`core/services/base_analytics_service.py`) is the base of every
`*IntelligenceService` in SKUEL. "Intelligence" names what the user gets; the implementation is
graph reads plus Python, with no LLM and no embeddings.

## Two Base Classes (ADR-024)

| Base class | Purpose | AI dependencies |
|------------|---------|-----------------|
| **`BaseAnalyticsService`** | Graph analytics, pure Python | None — enforced |
| `BaseAIService` | LLM / embedding features | LLM and embeddings; built at FULL tier only |

The separation is executable: `BaseAnalyticsService.__setattr__` raises `AttributeError` on an
attempt to set `llm`, `embeddings`, `llm_service` or `embeddings_service`.

For the AI side see [base-ai-service](../base-ai-service/SKILL.md).

---

## The Subclasses

Eleven classes extend the base.

### Nine per-domain services

| Domain | Service | Bases before `BaseAnalyticsService[...]` |
|--------|---------|------------------------------------------|
| Tasks | `TasksIntelligenceService` | `_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_ProductivityMixin`, `_DualTrackMixin` |
| Goals | `GoalsIntelligenceService` | `_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_PredictiveMixin`, `_DualTrackMixin` |
| Habits | `HabitsIntelligenceService` | `_CoreIntelligenceMixin`, `_BehavioralSignalsMixin`, `_DualTrackMixin` |
| Events | `EventsIntelligenceService` | `_CoreIntelligenceMixin` (events wrapper), `_AnalyticsMixin`, `_BehavioralSignalsMixin` |
| Choices | `ChoicesIntelligenceService` | `_CoreIntelligenceMixin` (choices wrapper), `_AnalyticsMixin`, `_BehavioralSignalsMixin` |
| Principles | `PrinciplesIntelligenceService` | `_CoreIntelligenceMixin` (principles wrapper), `_AlignmentIntelligenceMixin`, `_InfluenceMixin` |
| KU | `KuIntelligenceService` | `_CoreIntelligenceMixin[Ku]` |
| PS | `PsIntelligenceService` | `_CoreIntelligenceMixin[PathStep]` |
| LP | `LpIntelligenceService` | `_CoreIntelligenceMixin[LearningPath]`, `_PathAnalysisMixin` |

The mixin files sit beside the service in its package (`core/services/{domain}/`). Mixin names
repeat across packages — `tasks._AnalyticsMixin` and `goals._AnalyticsMixin` are different
classes. When to extract one: [SERVICE_DECOMPOSITION_RULE.md](/docs/patterns/SERVICE_DECOMPOSITION_RULE.md).

The second type parameter is the domain's own model. The first is the backend protocol:
the Activity services name their `*Operations` protocol; KU and PS use
`BackendOperations[Ku]` / `BackendOperations[PathStep]`; LP uses `LpOperations`.

### Two that are not per-domain

| Service | What it is |
|---------|------------|
| `ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) | One shared instance, `BaseAnalyticsService[BackendOperations[Entity], Entity]`, wired into all six Activity facades as `knowledge_intelligence`. Satisfies `KnowledgeIntelligenceOperations`. |
| `KnowledgeHealthService` (`core/services/analytics/knowledge_health_service.py`) | Corpus-level gauge over the knowledge subgraph (ADR-080). Its one method takes no `user_uid`. The constructor takes the structural `backend` (required) and `coverage`, an optional `EmbeddingCoverageOperations` probe; it passes no `graph_intel` or relationship service to the base. Exposed through the `AnalyticsService` facade as `analyze_knowledge_subgraph_health()`. |

`analyze_knowledge_subgraph_health()` reads the structural measurement and, when `coverage` is
wired, the embedding-coverage counts. A failure of either read fails the report. Without
`coverage` the report has no `embedding_coverage` block and no retrievability flag —
`AnalyticsService` wires both, so construct the service with both. The probe counts nodes whose
`embedding` is null; it is a graph read, not an embedding client.

Two rules `KnowledgeHealthService` illustrates: a corpus gauge **excludes user-generated data**
(learner-state edges; PERSONAL, ASSIGNED and ASSESSMENT exercises), and it **matches knowledge
nodes by `entity_type`, not by domain label** — an API-created path step is
`:Entity {entity_type: 'path_step'}`, so a label-only match drops it.

### Not subclasses

`UserContextIntelligence` (mixin composition — see
[user-context-intelligence](../user-context-intelligence/SKILL.md)), `ZPDService`,
`CrossDomainAnalyticsService`, `LifePathIntelligenceService` and the Askesis facade do not
extend this base.

---

## Class Attributes

```python
class BaseAnalyticsService(Generic[B, T]):
    __slots__ = ("backend", "event_bus", "graph_intel", "insight_store", "logger", "relationships")

    _service_name: ClassVar[str | None] = None
    _require_relationships: ClassVar[bool] = False
    _require_graph_intel: ClassVar[bool] = False
    _event_handlers: ClassVar[dict[type, str]] = {}
```

| Attribute | Purpose | In use |
|-----------|---------|--------|
| `_service_name` | Logger name: `skuel.analytics.{_service_name}`; falls back to the class name | Every service. The live values end in `.intelligence` — `"tasks.intelligence"`, `"ku.intelligence"`. |
| `_require_relationships` | `True` makes `__init__` raise `ValueError` without a relationship service | Goals, Habits, Choices |
| `_require_graph_intel` | `True` makes `__init__` raise `ValueError` without `graph_intel` | No service sets it |
| `_event_handlers` | `{EventClass: "handler_method_name"}`, subscribed on `__init__` when an `event_bus` is passed | No service declares any |

A subclass that declares no `__slots__` has a `__dict__`, so it may set its own attributes
(`self.cross_domain_query`, `self._knowledge_analyzer`). The `__setattr__` guard still applies
to the four AI names.

---

## Initialization

### The base constructor

```python
def __init__(
    self,
    backend: B,
    graph_intel: GraphIntelligenceService | None = None,
    relationship_service: Any | None = None,  # boundary: UnifiedRelationshipService, params vary per domain
    event_bus: Any | None = None,  # boundary: EventBusOperations
    insight_store: Any | None = None,  # boundary: InsightStore
) -> None: ...
```

- `backend` is required; a falsy backend raises `ValueError`.
- The keyword is `relationship_service`; the attribute it is stored on is `self.relationships`.
- There is no `embeddings_service` or `llm_service` parameter.

### A subclass constructor

Subclass signatures differ — each takes what its methods need. Tasks mirrors the base; Habits
requires the relationship service and a `CrossDomainQueryService` and takes no event bus:

```python
class HabitsIntelligenceService(
    _CoreIntelligenceMixin,
    _BehavioralSignalsMixin,
    _DualTrackMixin,
    BaseAnalyticsService[HabitsOperations, Habit],
):
    _service_name = "habits.intelligence"
    _require_relationships = True

    def __init__(
        self,
        backend: HabitsOperations,
        relationship_service: UnifiedRelationshipService[Any, Any, Any],  # boundary: domain-generic params
        cross_domain_query: CrossDomainQueryService,
        graph_intel: GraphIntelligenceService | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.cross_domain_query = cross_domain_query
```

Call `super().__init__()` first: it validates the backend, stores the services, creates the
logger and registers event handlers.

`CrossDomainQueryService` takes a `CrossDomainBackendOperations` backend. No Cypher is written
in `core/` (SKUEL021).

### Attributes after init

| Attribute | Type | May be `None` |
|-----------|------|---------------|
| `self.backend` | `B` | no |
| `self.graph_intel` | `GraphIntelligenceService` | yes |
| `self.relationships` | `UnifiedRelationshipService` | yes, unless `_require_relationships` |
| `self.event_bus` | event bus | yes |
| `self.insight_store` | `InsightStore` | yes |
| `self.logger` | logger | no |

### Who constructs it

| Domain | Built by |
|--------|----------|
| Tasks, Goals, Habits, Events, Choices | The facade's own `__init__` (`self.intelligence = TasksIntelligenceService(...)`) — each needs an argument the common factory does not have. |
| Principles | `create_common_sub_services()` — the one Activity domain whose `ActivityDomainConfig.intelligence_class` is set. |
| KU, PS, LP | The curriculum sub-service factories in `core/services/curriculum_domain_config.py`. |

`intelligence` is not a key of the factory's `skip` parameter: whether it is built is a property
of the domain's config.

---

## Dependency Guards

There are no `_require_*()` guard methods. Three mechanisms exist:

**1. Class attribute — refuse to construct.**

```python
_require_relationships = True
```

**2. Decorator — return `Result.fail` when `graph_intel` is missing.**

```python
from core.utils.decorators import requires_graph_intelligence

@requires_graph_intelligence("get_with_context")
async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]: ...
```

**3. Inline check — return `Result.fail`.**

```python
if self.relationships is None:
    return Result.fail(
        Errors.system(
            message="relationship_service required for get_with_context",
            operation="get_with_context",
        )
    )
```

A service with `_require_relationships = True` narrows the Optional for mypy with
`assert self.relationships is not None` — the constructor has already guaranteed it.

---

## Helper Methods

### `_to_domain_model(dto_or_dict, dto_class, model_class)`

Returns the domain model from a model (passed through), a DTO (`model_class.from_dto`), or a
dict (`dto_class(**d)` then `from_dto`).

### `_publish_event(event)`

`await publish_event(self.event_bus, event, self.logger)`. An analytics service publishes
findings; it does not perform the domain write — completing a task is the Tasks core service's
job.

### `_fetch_entity_or_fail(uid)`

`backend.get(uid)` plus the not-found guard: `Result.ok(entity)` or a failed `Result`.

---

## The Three Route-Facing Methods

Every one of the nine per-domain services has these. The contract is the
`IntelligenceOperations` protocol in
`adapters/inbound/route_factories/intelligence_route_factory.py`; the services satisfy it
structurally. There is no per-domain core protocol.

| Method | Provided by |
|--------|-------------|
| `get_with_context(uid, depth=2)` | Inherited from `_CoreIntelligenceMixin` — never written per service |
| `get_performance_analytics(user_uid, period_days=30)` | Each service |
| `get_domain_insights(uid, min_confidence=0.7)` | Each service |

Signatures vary within the contract:

- Habits, Choices and Principles declare `_period_days` — the underscore marks a parameter
  that is accepted and not applied; their analytics cover all of the user's entities. The
  register is `docs/reference/PLACEHOLDER_INDEX.md`.
- Tasks' `get_domain_insights` takes an extra optional `user_context`.
- Habits and Choices default `min_confidence` to `ConfidenceLevel.MEDIUM`.

Routes: eight domains have them (the six Activity domains, PS and LP). KU implements the
methods and has no generated routes. See [PROTOCOL_INTEGRATION.md](PROTOCOL_INTEGRATION.md).

---

## Cross-Domain Context (Mechanism B)

`get_with_context()` lives on the shared `_CoreIntelligenceMixin[T]`
(`core/services/intelligence/_core_intelligence_mixin.py`). It routes through
`self.relationships.get_with_context(uid, depth)`, whose edge vocabulary is the domain's
`DomainRelationshipConfig.cross_domain_relationship_types` — the registry. There is nothing to
wire per service, and no loader object.

| Services | How they inherit |
|----------|------------------|
| KU, PS, LP | `_CoreIntelligenceMixin[Model]` — typed return `Result[tuple[Model, GraphContext]]` |
| Tasks, Goals, Habits | The shared mixin, unparameterized |
| Events, Choices, Principles | A per-package `_CoreIntelligenceMixin` that subclasses the shared one and adds domain methods |

There are no domain-named variants (`get_goal_with_context`): `get_with_context` is the one
path.

The traversal follows edges out from the origin entity and is not owner-scoped. Ownership of
the origin is verified by the route before the call.

## Cross-Domain Analysis: `_analyze_entity_with_typed_context()`

The template for "fetch the entity, read its typed cross-domain context, compute metrics,
produce recommendations". All six Activity services use it.

```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict[str, Any]]:  # boundary: analysis envelope
    return await self._analyze_entity_with_typed_context(
        uid=uid,
        metrics_fn=calculate_goal_progress_metrics,
        recommendations_fn=goal_recommendations,
        min_confidence=0.7,
    )
```

- The context comes from `UnifiedRelationshipService.get_cross_domain_context_typed(entity_uid,
  depth=2, min_confidence=0.7)` — the path-aware types in
  `core/models/graph/path_aware_types.py`, built per domain by
  `{Domain}CrossContext.from_categorized`.
- `metrics_fn(entity, context) -> dict` and `recommendations_fn(entity, context, metrics) ->
  list[str]` live in `core/services/intelligence/metrics_calculators.py`.
- Extra keyword arguments (`depth`, `min_confidence`) are forwarded to the reader.
- The envelope is `{"entity", "metrics", "recommendations", "context"}`.

**Failure policy.** A missing entity, a missing relationship service, or a failed context read
returns `Result.fail`. An entity with no edges yields an `ok` result with an empty context.

**`depth` is transitive.** Entities up to `depth` hops away are bucketed by the edge incident to
each, and each entry carries its `distance`. Pass `depth=1` to count direct relationships only.

**Buckets are de-duplicated by the typed context, not by the producer.** A node reachable by
several paths appears once per path in the raw buckets. `from_categorized` keeps one entry per
uid — the strongest path (lowest `distance`, then highest `path_strength`; `_path_rank` and
`_union_path_buckets` in `path_aware_types.py`). Code that reads raw buckets and skips this
inflates every count. See
[UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md).

## Relationship Reads

```python
knowledge_result = await self.relationships.get_related_uids("knowledge", habit.uid)
goals_result = await self.relationships.get_related_uids("supported_goals", habit.uid)
```

`get_related_uids(relationship_key, entity_uid)` takes a **config method key** and a uid. The
relationship type, direction and any edge filter come from the registry spec for that key. It
does not take a `RelationshipName` or a `direction=` argument. The keys are per domain — the two
above are Habits keys; read the domain's relationship config for the rest.

---

## Dual-Track Assessment (ADR-030-dual-track-assessment-pattern.md)

`_dual_track_assessment()` compares the user's self-rating (vision) with a system measurement
(action) and returns a `DualTrackResult[L]` carrying both, the perception gap and its
direction.

```python
async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: UserUID,
    user_alignment_level: AlignmentLevel,
    user_evidence: str,
    user_reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_alignment_level,
        user_evidence=user_evidence,
        user_reflection=user_reflection,
        system_calculator=self._calculate_system_alignment_for_dual_track,
        level_scorer=self._alignment_level_to_score,
        entity_type=EntityType.PRINCIPLE.value,
        insight_generator=principle_gap_insights,
        recommendation_generator=principle_gap_recommendations,
        store_callback=self._store_dual_track_checkin,
    )
```

- `system_calculator(entity, user_uid)` returns `(level, score, evidence)`. An exception it
  raises is caught and returned as `Result.fail(Errors.system(...))`.
- The gap is `user_score - system_score`. Under 0.15 in magnitude the direction is `aligned`;
  otherwise `user_higher` or `system_higher`.
- `recommendations` is capped at four.

### Seven dimensions, three subjects

| Subject | Dimensions | `require_entity` | Persisted to |
|---------|------------|------------------|--------------|
| Per-entity | Goals, Habits, Principles | `True` | The entity's `dual_track_checkins`, via `self._store_dual_track_checkin` |
| User-level | Tasks (productivity), Events (engagement), Choices (decision quality) | `False`, `uid == user_uid` | `User.dual_track_checkins`, keyed by `DualTrackDimension`, via `UserService.append_dual_track_checkin` |
| Per-(user, Ku) | Knowledge — `KuIntelligenceService.assess_mastery_dual_track` | `True` | `User.knowledge_checkins`, keyed by Ku uid, via `UserService.append_knowledge_checkin` |

A Ku is shared, so its check-ins live on the user, never on the `:Ku` node.

### `store_callback`

`store_callback(uid, result)` runs after the result is built, so it sees the system level,
score and gap. A failure inside it is logged and swallowed: **the assessment returns
`Result.ok` whether or not the check-in was stored.** A caller that must know the snapshot
persisted cannot learn it from the result.

Every callback ends in one appender —
`adapters/persistence/neo4j/_dual_track_checkin_store.py::atomic_append_checkin` — which does
the read-modify-write of the JSON log under the node's write lock, capped at
`DualTrackCheckin.HISTORY_LIMIT` (20). Do not write a check-in with a plain `get()` then
`update()`: two concurrent check-ins would lose one.

### HTTP surfaces

| Surface | Route | Dimensions |
|---------|-------|------------|
| Self Check-In page | `POST /self-checkin/results` | user-level |
| Activity detail pages | `POST /{domain}/dual-track/results` | per-entity |
| Ku detail page | `POST /explore/ku/{uid}/mastery-checkin` | Knowledge |

Each is `@csrf_protected`.

---

## Shared Utilities

```python
from core.services.intelligence import (
    MetricsCalculator,
    PatternAnalyzer,
    RecommendationEngine,
    Trend,
    analyze_completion_trend,
    compare_progress_to_expected,
)
```

`RecommendationEngine` is a fluent builder: `with_metrics(...)`, `add_threshold_check(...)`,
`add_conditional(...)`, `add_message(...)`, `build()`. Worked examples are in
[PATTERNS.md](PATTERNS.md).

---

## Adding a Method

1. Find the service. If it is decomposed, put the method in the mixin whose subject it shares;
   otherwise in the service file.
2. Return `Result[T]`. Propagate a failed read with `Result.fail(result)`.
3. Guard an optional dependency with one of the three mechanisms above.
4. A method with no `await` is `def` (SKUEL029).
5. Add the facade delegation if callers reach it through the facade.
6. No Cypher in the service — a new read is a backend method (SKUEL021).

## Anti-Patterns

### Skipping `super().__init__()`

```python
# WRONG - no backend validation, no logger, no handler registration
def __init__(self, backend: HabitsOperations) -> None:
    self.backend = backend
```

### Reaching for an AI service

```python
# WRONG - raises AttributeError at construction
self.llm = llm_service
```

Put the feature on the domain's `*AIService`.

### Turning a failed read into an empty answer

```python
# WRONG - "no linked knowledge" and "the read failed" become the same answer
knowledge = await self.relationships.get_related_uids("knowledge", habit_uid)
return Result.ok({"knowledge_uids": knowledge.value if knowledge.is_ok else []})

# CORRECT
knowledge = await self.relationships.get_related_uids("knowledge", habit_uid)
if knowledge.is_error:
    return Result.fail(knowledge)
return Result.ok({"knowledge_uids": knowledge.value})
```

### Raising instead of returning

```python
# WRONG
raise ValueError("uid required")

# CORRECT
return Result.fail(Errors.validation(message="uid required", field="uid"))
```

`Errors` and `Result` both come from `core.utils.result_simplified`.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/services/base_analytics_service.py` | The base class |
| `core/services/intelligence/_core_intelligence_mixin.py` | Shared `get_with_context()` |
| `core/services/intelligence/metrics_calculators.py` | `metrics_fn` / `recommendations_fn` per domain |
| `core/services/intelligence/` | `RecommendationEngine`, `MetricsCalculator`, `PatternAnalyzer`, trend functions |
| `core/models/graph/path_aware_types.py` | Path-aware cross-domain context types |
| `core/models/graph_context.py` | `GraphContext` |
| `core/ports/intelligence_protocols.py` | `KnowledgeIntelligenceOperations` |
| `adapters/inbound/route_factories/intelligence_route_factory.py` | `IntelligenceOperations`, `IntelligenceRouteFactory` |
| `core/services/activity_domain_config.py` | `create_common_sub_services()`, `intelligence_class` |
| `core/services/{domain}/{domain}_intelligence_service.py` | The nine services |

## Related Skills

- **[base-ai-service](../base-ai-service/SKILL.md)** — the AI tier
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — the cross-domain hub
- **[activity-domains](../activity-domains/SKILL.md)** — the facades that hold `.intelligence`
- **[result-pattern](../result-pattern/SKILL.md)** — `Result[T]`
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — where queries are written

## Deep Dive Resources

- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) — the inventory
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) — facades and sub-services
- [SERVICE_DECOMPOSITION_RULE.md](/docs/patterns/SERVICE_DECOMPOSITION_RULE.md) — when to extract a mixin
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md) — the analytics / AI separation
- [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) — mixin decomposition
- [ADR-080](/docs/decisions/ADR-080-auradb-three-horizon-strategy.md) — the knowledge-health gauge

## See Also

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — locations, imports, signatures
- [PATTERNS.md](PATTERNS.md) — worked examples from the live services
- [PROTOCOL_INTEGRATION.md](PROTOCOL_INTEGRATION.md) — the protocols and the route factory
