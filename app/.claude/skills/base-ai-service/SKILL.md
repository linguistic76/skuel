---
name: base-ai-service
description: Expert guide for SKUEL's AI tier — the BaseAIService base class, the eight domain *AIService subclasses, their FULL-tier wiring onto each facade's .ai slot, and the config-driven AI routes. Use when adding or changing an LLM or embeddings feature on a domain, working with BaseAIService, _generate_insight, _rank_similar_entities, rank_similar_curriculum, AIRouteSpec, or the /api/{domain}/ai/* routes.
allowed-tools: Read, Grep, Glob
---

# BaseAIService: The AI Tier

> "AI enhances; it is never required."

`BaseAIService[B, T]` (`core/services/base_ai_service.py`) is the base of the eight domain
`*AIService` classes. They hold the features that need an LLM or embeddings. Everything else —
CRUD, search, analytics, the daily plan — runs without them.

## Two Base Classes (ADR-024)

| Layer | Base class | Dependencies | Facade slot | Tier |
|-------|------------|--------------|-------------|------|
| Analytics | `BaseAnalyticsService` | Graph + Python | `.intelligence` | CORE and FULL |
| AI | `BaseAIService` | LLM + embeddings | `.ai` | FULL only |

`BaseAnalyticsService` refuses the AI attribute names at runtime, so an AI dependency cannot be
added to an analytics service. See [base-analytics-service](../base-analytics-service/SKILL.md).

---

## The Eight Services

| Domain | Class | File |
|--------|-------|------|
| Tasks | `TasksAIService` | `core/services/tasks/tasks_ai_service.py` |
| Goals | `GoalsAIService` | `core/services/goals/goals_ai_service.py` |
| Habits | `HabitsAIService` | `core/services/habits/habits_ai_service.py` |
| Events | `EventsAIService` | `core/services/events/events_ai_service.py` |
| Choices | `ChoicesAIService` | `core/services/choices/choices_ai_service.py` |
| Principles | `PrinciplesAIService` | `core/services/principles/principles_ai_service.py` |
| PathStep | `PsAIService` | `core/services/ps/ps_ai_service.py` |
| LearningPath | `LpAIService` | `core/services/lp/lp_ai_service.py` |

There is no `KuAIService`. The KU facade has no `.ai` slot.

---

## The Base Class

```python
class BaseAIService(Generic[B, T]):
    _service_name: ClassVar[str | None] = None

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

- `backend` is required; a falsy backend raises `ValueError`.
- `llm_service` and `embeddings_service` are **optional at the base**, typed against the real
  classes (`TYPE_CHECKING` imports). A missing one is logged as a warning at construction, and
  the helper that needs it returns `Result.fail`.
- There are no `_require_llm` / `_require_embeddings` class attributes and no
  `_require_*_service()` guard methods.
- The logger is `skuel.ai.{_service_name}`.

| Attribute | Holds |
|-----------|-------|
| `self.backend` | The domain's backend protocol |
| `self.llm` | `LLMService`, or `None` |
| `self.embeddings` | `EmbeddingsService`, or `None` |
| `self.graph_intel`, `self.relationships`, `self.event_bus` | Optional; the wiring passes none of them |
| `self.logger` | Logger |

### The subclasses narrow the constructor

Each of the eight declares both AI services as required parameters. `PsAIService` and
`LpAIService` additionally require `vector_search: Neo4jVectorSearchService`, held as
`self.vector_search` — their similarity ranks through the vector index (§ The Helpers).

```python
class TasksAIService(BaseAIService["TasksOperations", Task]):
    _service_name = "tasks.ai"

    def __init__(
        self,
        backend: TasksOperations,
        llm_service: LLMService,
        embeddings_service: EmbeddingsService,
        event_bus: Any | None = None,  # boundary: EventBusOperations
    ) -> None:
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )
```

---

## Wiring (FULL Tier)

`_wire_ai_services()` (`services_bootstrap/_ai_wiring.py`), called from `compose_services`:

```python
vector_search_service = learning_services["vector_search_service"]
if not (llm_service and embeddings_service and vector_search_service):
    return  # every facade's .ai stays None

facade.ai = TasksAIService(
    backend=facade.core.backend,
    llm_service=llm_service,
    embeddings_service=embeddings_service,
)
ps_ai = PsAIService(..., vector_search=vector_search_service)
```

- All three present → all eight are built and set on their facade's `.ai`.
- Any missing → none is built. It is all or nothing. `compose_services` builds all three in
  FULL or raises (`compose.py`, `_learning_services.py`) and none in CORE, so the guard
  separates the tiers rather than a partial FULL.
- The AI service shares the backend of the facade's core service.
- No event bus is passed to any AI service, and the base class offers no declarative
  subscription: a subscriber is wired in `services_bootstrap/_event_wiring.py`.

`INTELLIGENCE_TIER=core` builds neither an LLM service nor an embeddings service, so `.ai` is
`None` on every facade (ADR-043).

### Where the SDK clients live (ADR-063)

`core/` holds no vendor SDK client. `LLMService(config=None, caller=None)` takes a
multi-provider caller; `EmbeddingsService(backend, embedding_client, prometheus_metrics=None)`
takes an embedding client. The `openai` /
`anthropic` clients are constructed in `adapters/external/llm/` and
`adapters/external/embeddings/`, and the composition root injects them.
`tests/unit/test_llm_sdk_boundary.py` fails on a vendor import in `core/`.

### Where stored embeddings come from (ADR-074)

AI services read; they do not write node embeddings. Entity and chunk vectors are written by the
embedding background worker, fed by the `*EmbeddingRequested` events every create, update and
ingest path publishes after persisting. `./dev embed-backfill` fills nodes that have none.

---

## The Helpers

### `_generate_insight(prompt, context=None, max_tokens=500) -> Result[str]`

Prepends `context` as `key: value` lines — each value through `_bounded` — calls
`self.llm.generate(full_prompt, max_tokens=max_tokens)`, and returns
`Result.ok(response.content)`.

- No LLM → `Result.fail(Errors.unavailable(feature="ai_insights", ...))`.
- An assembled prompt over `PromptInput.PROMPT_MAX_CHARS` → `Result.fail(Errors.system(...))`,
  and nothing is sent. The helper refuses instead of cutting: the instructions are the end of
  the prompt, and a cut here would take them. Bounded fields keep every live prompt under the
  ceiling; a builder that interpolates a field without `_bounded` is what reaches it.
- A response with `error` set → `Result.fail(Errors.integration(service="llm", ...))`.
  `LLMService.generate` never raises: a provider failure is a response with empty `content`
  and a set `error`, and this helper is where it becomes a failed `Result`. There is no
  `except` — the chat adapters catch their SDK exceptions below the port.

A method that returns the helper's `Result` hands the caller text; a method that parses the
text (`.split("\n")`, `json.loads`) parses a `str`.

### `_bounded(value, limit=PromptInput.FIELD_MAX_CHARS) -> str`

Renders one entity field as prompt text of at most `limit` characters
(`truncate_to_budget`, `core/utils/text_truncation.py`): a field within the limit is returned
as written; a longer one is cut at a paragraph, sentence or word boundary and ends in `...`.
`_generate_insight` applies it to every `context` value, so a field that goes into the context
dict needs nothing more. A builder that writes a field straight into its prompt string calls
it at the interpolation — `generate_task_breakdown` and `generate_milestones` do.

The bound is per field because the request models are not the only writers: a Task or Event
`description` is capped at 2000 by its request model, the limit `FIELD_MAX_CHARS` matches, and
a field written by vault ingestion or a template spawn has no cap at all.
`tests/unit/services/test_ai_prompt_input_bounds.py` runs every prompt-building method of the
eight services over an entity whose every text field is 50 000 characters.

### `_rank_similar_entities(source, entity_type, candidate_pool, *, exclude_uid, limit=5)`

The shared tail of the six Activity `find_similar_*` methods. Takes `Entity` models and ranks
the pool by the `embedding` each carries — the vector the embedding worker stored on the node:

- A candidate with `embedding is None`, and `exclude_uid`, are left out of the ranking.
- The source's own stored vector is the query. When it has none, its canonical text
  (`build_embedding_text(entity_type, source)`) is embedded **once** through
  `self.embeddings.create_embedding`; that `Result`'s failure is the ranking's failure, and no
  embeddings service is `Result.fail(Errors.unavailable(feature="semantic_search", ...))`.
- Scores are `normalized_cosine_similarity` — `(1 + cos) / 2`, the `[0, 1]` scale the vector
  indexes answer on — so an Activity ranking and a curriculum index query speak one scale.
- No threshold: the top `limit` are returned however weak. An empty pool (after the two
  exclusions) returns `Result.ok([])` without embedding anything.

The caller owns the pool read — `find_all_by(self.backend, …, user_uid=source.user_uid)`
(`core/services/whole_set_read.py`), the owner's whole set of that domain up to
`QueryLimit.MAXIMUM` rows ([PATTERNS.md](PATTERNS.md) § Pattern 1).

Do not hand-roll `f"{title} {description}"`: it drifts from the text the stored embeddings were
built from.

### `rank_similar_curriculum(vector_search, label, entity_type, source, *, limit)`

`core/services/curriculum_similarity.py` — a module function, not a base method, because it
takes the vector search service the two curriculum AI services hold. The shared tail of
`PsAIService.find_similar_steps` and `LpAIService.find_similar_paths`:

- The source's stored vector goes to `find_similar_by_vector` on its own label's index;
  a source without one is embedded once through `find_similar_by_text` from its canonical text.
- The index is asked for `limit + 1` and the source dropped, so the list holds at most
  `limit`. The index query is the vector-discovery chokepoint
  (`VectorSearchBackend.query_vector_index`), which withholds draft-marked curriculum **as a
  post-filter on the index's answer** — a draft among the nearest neighbours shortens the list
  rather than being replaced.
- `min_score` is `VectorSearchConfig.ku_similar_min_score` (0.72), the node→node threshold; the
  per-label defaults (0.75) are calibrated for text→entity queries and starve node→node.

There is no `backend.list()` pool in either service.
`PsAIService.search_by_semantic_query` is the same chokepoint by text: `find_similar_by_text`,
then `backend.get_many` reads the hits back as models in score order. It has no keyword
fallback — a keyword hit is not semantic, and the backend has no `search` method — so an
embedding or index failure is the method's failure.

### `_publish_event(event)`

`await publish_event(self.event_bus, event, self.logger)`.

---

## Routes

`adapters/inbound/ai_routes.py` registers one route per `AIRouteSpec`, at
`POST /api/{url_domain}/ai/{action}`, plus `GET /api/ai/status`. Nothing in `ui/` or `static/`
calls any of them — the tier is staged behind its first UI surface
(`/docs/roadmap/ai-tier-consumer.md`).

```python
AIRouteSpec(
    "tasks",                # domain_attr — the attribute on the services container
    "Tasks",                # domain_label — used in messages
    "tasks",                # url_domain
    "insight",              # action
    "generate_task_insight",  # method_name on the AI service
    "uid",                  # signature: uid | uid_limit | uid_level
    "tasks_ai_insight",     # func_name — unique; FastHTML names the route after it
    "insight",              # wrap_key — the response is {"insight": value}
)
```

`scope` defaults to `ContentScope.USER_OWNED`; the PathStep and LearningPath specs set
`ContentScope.SHARED`. A new spec is owner-gated unless it says otherwise. `SHARED` removes the
ownership gate and adds nothing in its place — the route applies no publication check. The two
similarity methods gate drafts at the read (§ The Helpers); the other curriculum methods read
the uid they are given, and a by-uid read is deliberately ungated.

Every route spends LLM or embeddings money, so each is registered `methods=["POST"]` and
wrapped in `@csrf_protected`: `GET` and `HEAD` answer 405 before any gate runs, and a `POST`
without a matching CSRF token answers 403 `CSRF_INVALID` the same way. `/api/ai/status` reads
the `.ai` slots and spends nothing; it is `GET` only.

### Registration

`create_ai_routes` resolves every spec before registering any: `unresolved_ai_route_specs`
names a spec whose `domain_attr` has no class in `AI_SERVICE_CLASSES`, whose `method_name` is
not a method of that class, or whose `signature` has no factory. A non-empty list raises
`ValueError` at boot, in both tiers — a spec that names nothing never becomes a route.

### The gates, in order

`_ai_route` runs them before the AI call. A request stopped by one never reaches the next.

| # | Gate | Answer when it stops the request |
|---|------|----------------------------------|
| 1 | Signed in | 401 |
| 2 | `facade.ai` is set | 503 `AI service unavailable` |
| 3 | The user's effective tier allows AI (`REGISTERED` is capped at CORE). Runs when `services.intelligence_tier` is set, which `compose_services` always does; a container built without it skips this gate. | 403 `AI features require a paid subscription`; 503 when the user cannot be read |
| 4 | `USER_OWNED`: the user owns the entity | 404 |
| 5 | Daily LLM quota (`llm_quota_allowed`) — checked **and recorded** here | 403 `Daily AI quota exceeded` |
| 6 | The AI method's `Result`, through `result_to_response` | the status of the error's category and its `to_client_dict()` body — the failure-category table in § Measured behavior |

The two 403s are told apart by their message, not their status. The verb and CSRF checks sit
in front of gate 1 and spend nothing.

### Measured behavior

Reproduced with a `TestClient` (`tests/unit/adapters/test_ai_routes_http.py`):

| Request | Status |
|---------|--------|
| No session | 401 |
| Any verb but `POST` (`GET`, `HEAD`, `PUT`, `PATCH`, `DELETE` measured) | 405, no quota unit |
| `POST` without a CSRF token | 403 `CSRF_INVALID`, no quota unit |
| A domain whose `.ai` is `None` | 503 |
| The method returns a dict | 200, the dict as JSON |
| The method returns a list or a string | 200, `{wrap_key: value}` as JSON — a value of any type is JSON; the `wrap_key` names it |
| The method returns `Result.fail` | the category's status, body `{category, code, message, severity, timestamp}` — never the error text or its capture site |

| Failure category | Status |
|------------------|--------|
| `validation` | 400 |
| `not_found` | 404 |
| `integration` (an LLM or embedding failure) | 502 |
| `database` | 503 |
| `system` (`Errors.unavailable` — a service not configured) | 500 |

`GET /api/ai/status` answers `{"ai_available": {domain: bool}}` for a signed-in user.

### Adding a route

1. Write the method on the domain's AI service; it returns `Result[T]`.
2. Add an `AIRouteSpec` whose `method_name` is that method and whose `signature` matches its
   positional parameters — `uid` passes `(uid,)`, `uid_limit` passes `(uid, limit)`,
   `uid_level` passes `(uid, level)`.
3. Give it a `wrap_key` unless the method returns a dict (`test_every_non_dict_method_has_a_wrap_key`
   reads the return annotation and fails otherwise).
4. Leave `scope` at the default for a user-owned entity.
5. Boot, or run `test_live_specs_all_resolve` — an unresolved spec fails both.

---

## Calling an AI Service from Code

```python
if tasks_service.ai is None:
    return Result.fail(
        Errors.system(
            message="AI service required for task insights",
            operation="get_task_insight",
        )
    )
return await tasks_service.ai.generate_task_insight(task_uid)
```

`.ai` is `None` at CORE tier — narrow it before every use. Where an analytics answer can stand
in, fall back to it; `PsService.search_by_semantic_query` falls back to keyword search:

```python
if self.ai is None:
    return await self.search.search(query=query_text, limit=limit)
return await self.ai.search_by_semantic_query(query_text, limit, min_score)
```

The service layer does not check ownership, tier or quota. Those gates are the route's; a new
HTTP door onto an AI method goes through `_ai_route`.

---

## Prompts

The eight domain AI services hold their prompts inline, as string literals in the method.
`PROMPT_REGISTRY` (`core/prompts/`) is the registry other LLM callers render from — Askesis
and the report generators among them. A new prompt goes in the registry — see the
[prompt-templates](../prompt-templates/SKILL.md) skill.

Entity text reaches the model bounded: put a field in the `context` dict, or pass it through
`self._bounded(...)` where the prompt string interpolates it (§ The Helpers). `max_tokens` caps
the reply only.

---

## Anti-Patterns

### Using `.ai` without narrowing

```python
# WRONG - AttributeError at CORE tier
insight = await tasks_service.ai.generate_task_insight(uid)
```

### An AI dependency on an analytics service

```python
# WRONG - BaseAnalyticsService raises AttributeError
class TasksIntelligenceService(BaseAnalyticsService[...]):
    def __init__(self, backend, llm_service):
        self.llm = llm_service
```

### Flattening a failed AI call

```python
# WRONG - the caller cannot tell "no insight" from "the LLM call failed"
result = await self.ai.generate_task_insight(uid)
insight = result.value if result.is_ok else None

# CORRECT
result = await self.ai.generate_task_insight(uid)
if result.is_error:
    return Result.fail(result)
```

### An `except` around `self.llm.generate` or `create_embedding`

Neither raises on a provider failure: `generate` answers a response with `error` set and
`create_embedding` answers `Result.fail` — the chat and embedding adapters catch their SDK
exceptions below the port. A `try` at the service is dead code; read the response or the
`Result`. Where an SDK is called directly (the adapters), catch `LLM_EXCEPTIONS`
(`core/utils/exception_types.py`); a catch-all carries a `# safety-net:` annotation (SKUEL017).

### A second HTTP door

A hand-written route that calls an AI method skips the tier, ownership and quota gates. Add an
`AIRouteSpec`.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/services/base_ai_service.py` | The base class |
| `core/services/{domain}/{domain}_ai_service.py` | The eight services |
| `services_bootstrap/_ai_wiring.py` | `_wire_ai_services()` |
| `adapters/inbound/ai_routes.py` | `AIRouteSpec`, `AI_ROUTE_SPECS`, `_ai_route` |
| `adapters/inbound/rate_limit.py` | `llm_quota_allowed` |
| `core/services/intelligence_tier_service.py` | `get_user_intelligence_tier` |
| `core/services/llm_service.py` | `LLMService`, `LLMResponse` |
| `core/services/embeddings_service.py` | `EmbeddingsService` |
| `core/utils/embedding_text_builder.py` | `build_embedding_text` |
| `core/services/curriculum_similarity.py` | `rank_similar_curriculum` |
| `core/services/neo4j_vector_search_service.py` | `Neo4jVectorSearchService` — `find_similar_by_vector`, `find_similar_by_text` |
| `core/utils/vector_math.py` | `normalized_cosine_similarity`, `cosine_similarity`, `dot`, `l2_normalize` |

## Deep Dive Resources

- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) — the inventory of both tiers
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md) — the analytics / AI separation
- [ADR-063](/docs/decisions/ADR-063-llm-embeddings-sdk-ports.md) — SDK clients behind ports
- [ADR-074](/docs/decisions/ADR-074-post-persist-embedding-events.md) — post-persist embedding events

## Related Skills

- [base-analytics-service](../base-analytics-service/SKILL.md) — the analytics tier
- [prompt-templates](../prompt-templates/SKILL.md) — the prompt registry
- [user-context-intelligence](../user-context-intelligence/SKILL.md) — the cross-domain hub
- [result-pattern](../result-pattern/SKILL.md) — `Result[T]`

## See Also

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — signatures, the route table
- [PATTERNS.md](PATTERNS.md) — worked examples and tests
