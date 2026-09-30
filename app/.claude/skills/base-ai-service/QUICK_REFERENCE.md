# BaseAIService Quick Reference

## File Locations

| File | Purpose |
|------|---------|
| `core/services/base_ai_service.py` | The base class |
| `core/services/base_analytics_service.py` | The analytics base (separate skill) |
| `services_bootstrap/_ai_wiring.py` | `_wire_ai_services()` |
| `adapters/inbound/ai_routes.py` | `AIRouteSpec`, `AI_ROUTE_SPECS`, `_ai_route`, `create_ai_routes` |
| `core/services/llm_service.py` | `LLMService`, `LLMResponse`, `LLMConfig` |
| `core/services/embeddings_service.py` | `EmbeddingsService` |
| `core/services/curriculum_similarity.py` | `rank_similar_curriculum` — the curriculum `find_similar_*` tail |
| `core/services/neo4j_vector_search_service.py` | `Neo4jVectorSearchService` — the index chokepoint the curriculum pair rank through |

### The services

| Domain | File | `_service_name` |
|--------|------|-----------------|
| Tasks | `core/services/tasks/tasks_ai_service.py` | `tasks.ai` |
| Goals | `core/services/goals/goals_ai_service.py` | `goals.ai` |
| Habits | `core/services/habits/habits_ai_service.py` | `habits.ai` |
| Events | `core/services/events/events_ai_service.py` | `events.ai` |
| Choices | `core/services/choices/choices_ai_service.py` | `choices.ai` |
| Principles | `core/services/principles/principles_ai_service.py` | `principles.ai` |
| PathStep | `core/services/ps/ps_ai_service.py` | `ps.ai` |
| LearningPath | `core/services/lp/lp_ai_service.py` | `lp.ai` |

---

## Imports

```python
from core.services.base_ai_service import BaseAIService

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import EntityUID
from core.services.curriculum_similarity import rank_similar_curriculum
from core.utils.result_simplified import Errors, Result
from core.utils.vector_math import normalized_cosine_similarity
```

Models and backend protocols are imported from their own modules — for Tasks,
`core.models.task.task` and `core.ports.domain_protocols`.

---

## Class Signature

```python
class BaseAIService(Generic[B, T]):
    _service_name: ClassVar[str | None] = None
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        llm_service: LLMService | None = None,
        embeddings_service: EmbeddingsService | None = None,
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: Any | None = None,  # boundary: UnifiedRelationshipService
        event_bus: Any | None = None,  # boundary: EventBusOperations
    ) -> None: ...
```

## Helper Signatures

```python
async def _generate_insight(
    self,
    prompt: str,
    context: dict[str, Any] | None = None,  # boundary: free-form prompt context
    max_tokens: int = 500,
) -> Result[str]: ...

async def _rank_similar_entities(
    self,
    source: Entity,
    entity_type: EntityType,
    candidate_pool: Sequence[Entity],
    *,
    exclude_uid: str,
    limit: int = 5,
) -> Result[list[tuple[EntityUID, float]]]: ...

async def _publish_event(self, event: Any) -> None: ...  # boundary: any BaseEvent subclass
```

```python
# core/services/curriculum_similarity.py — held by PsAIService / LpAIService as self.vector_search
async def rank_similar_curriculum(
    vector_search: Neo4jVectorSearchService,
    label: NeoLabel,
    entity_type: EntityType,
    source: Entity,
    *,
    limit: int,
) -> Result[list[tuple[EntityUID, float]]]: ...
```

`_generate_insight` returns the response's `content`, or `Errors.integration(service="llm")`
when the response's `error` is set. Both rankings score on the index's `[0, 1]` cosine scale.

## The Services the Helpers Call

```python
# core/services/llm_service.py
async def generate(
    self,
    prompt: str,
    context: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> LLMResponse: ...


@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    usage: dict[str, int] | None = None
    error: str | None = None
```

```python
# core/services/embeddings_service.py
async def create_embedding(
    self,
    text: str,
    metadata: dict[str, Any] | None = None,  # boundary: accepted, unused
) -> Result[list[float]]: ...

async def create_batch_embeddings(
    self,
    texts: list[str],
    metadata_list: list[dict[str, Any]] | None = None,  # boundary: accepted, unused
) -> Result[list[list[float]]]: ...
```

`generate` does not raise on a provider failure: it returns an `LLMResponse` with empty
`content` and `error` set.

---

## Routes

Path: `POST /api/{url_domain}/ai/{action}`, registered `methods=["POST"]` under
`@csrf_protected`; `GET` / `HEAD` answer 405 and a `POST` without a CSRF token 403, both before
any gate and without a quota unit. `GET /api/ai/status` is the one read. No file under `ui/` or
`static/` calls any of them (`/docs/roadmap/ai-tier-consumer.md`).

| `signature` | Handler parameters | Arguments passed to the method |
|-------------|--------------------|--------------------------------|
| `uid` | `uid: str` | `(uid,)` |
| `uid_limit` | `uid: str`, `limit: int = default_limit` | `(uid, limit)` |
| `uid_level` | `uid: str`, `level: str = "intermediate"` | `(uid, level)` |

A handler always passes every argument in its row, so over HTTP the method's own defaults for
those parameters are not reached: `explain_step(target_level="standard")` is called with
`"intermediate"` when the request names no level.

| `url_domain` | Actions | Scope |
|--------------|---------|-------|
| `tasks` | `similar`, `insight`, `breakdown`, `priority-suggestion` | `USER_OWNED` |
| `goals` | `similar`, `insight`, `milestones`, `smart-refinement`, `strategy` | `USER_OWNED` |
| `habits` | `similar`, `streak-insight`, `habit-stack`, `optimize-loop`, `identity` | `USER_OWNED` |
| `events` | `similar`, `insight`, `preparation`, `reflection` | `USER_OWNED` |
| `choices` | `similar`, `insight`, `framework`, `alternatives` | `USER_OWNED` |
| `principles` | `similar`, `insight`, `deepen`, `practices` | `USER_OWNED` |
| `path-steps` | `similar`, `insight`, `explain`, `practice` | `SHARED` |
| `learning-paths` | `similar`, `insight`, `overview`, `strategy` | `SHARED` |

Every spec resolves on its AI class (`AI_SERVICE_CLASSES`) or `create_ai_routes` raises at boot.
`AI_ROUTE_SPECS` is the authority — read it rather than this table when the two differ.

### Status codes

| Status | Meaning |
|--------|---------|
| 405 | Any verb but `POST` (`/api/ai/status`: any but `GET`) |
| 403 `CSRF_INVALID` | `POST` without a matching CSRF token |
| 401 | Not signed in |
| 503 | `.ai` is `None` for the domain, or the user's tier could not be read |
| 403 | The user's tier does not include AI, **or** the daily quota is spent — read the message |
| 404 | `USER_OWNED`: the entity is not the user's, or does not exist |
| 200 | JSON: the method's dict, or `{wrap_key: value}` for any other return type |
| 400 / 404 / 502 / 503 / 500 | A failed `Result`, by category: `validation` / `not_found` / `integration` / `database` / `system` — body `to_client_dict()` |

---

## Error Construction

```python
# A feature whose service is not configured
Errors.unavailable(
    feature="semantic_search",
    reason="Embeddings service not configured",
    operation="find_similar_tasks",
)

# A provider call that failed
Errors.integration(service="llm", message="LLM generation failed")

# A missing entity — a resource name, never a sentence
Errors.not_found(resource="Task", identifier=task_uid)
```

`Errors.unavailable` takes `feature` and `reason`; both are required.

---

## Analytics vs AI

| Aspect | `BaseAnalyticsService` | `BaseAIService` |
|--------|------------------------|-----------------|
| Dependencies | `graph_intel`, `relationships` | `llm`, `embeddings` |
| AI attributes | Refused by `__setattr__` | Optional on the base; required by each subclass constructor |
| Facade slot | `.intelligence` | `.ai` — `None` at CORE tier |
| Dependency guards | Class attribute, decorator, or inline check | Inline check inside each helper |
| Logger prefix | `skuel.analytics.*` | `skuel.ai.*` |
