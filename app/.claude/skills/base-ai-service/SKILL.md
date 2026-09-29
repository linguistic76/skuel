---
name: base-ai-service
description: Expert guide for SKUEL's AI tier — the BaseAIService base class, the eight domain *AIService subclasses, their FULL-tier wiring onto each facade's .ai slot, and the config-driven AI routes. Use when adding or changing an LLM or embeddings feature on a domain, working with BaseAIService, _generate_insight, _semantic_search, AIRouteSpec, or the /api/{domain}/ai/* routes.
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
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        llm_service: Any | None = None,  # boundary: LLMService, typed on each subclass
        embeddings_service: Any | None = None,  # boundary: EmbeddingsService, typed on each subclass
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: Any | None = None,  # boundary: UnifiedRelationshipService
        event_bus: Any | None = None,  # boundary: EventBusOperations
    ) -> None: ...
```

- `backend` is required; a falsy backend raises `ValueError`.
- `llm_service` and `embeddings_service` are **optional at the base**. A missing one is logged
  as a warning at construction, and the helper that needs it returns `Result.fail`.
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

Each of the eight declares both AI services as required, typed parameters:

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
if not (llm_service and embeddings_service):
    return  # every facade's .ai stays None

facade.ai = TasksAIService(
    backend=facade.core.backend,
    llm_service=llm_service,
    embeddings_service=embeddings_service,
)
```

- Both services present → all eight are built and set on their facade's `.ai`.
- Either missing → none is built. It is all or nothing.
- The AI service shares the backend of the facade's core service.
- No event bus is passed, so an `_event_handlers` declaration on an AI service would register
  nothing. No AI service declares any.

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

Prepends `context` as `key: value` lines, calls `self.llm.generate(full_prompt,
max_tokens=max_tokens)`, and returns `Result.ok(<what generate returned>)`.

- No LLM → `Result.fail(Errors.unavailable(feature="ai_insights", ...))`.
- An exception from the call → `Result.fail(Errors.integration(service="llm", ...))`.

### `_semantic_search(query, candidates, top_k=5) -> Result[list[tuple[EntityUID, float]]]`

Embeds the query and each `(uid, text)` candidate, ranks by cosine similarity
(`core/utils/vector_math.py`), returns the top `top_k`.

- No embeddings service → `Result.fail(Errors.unavailable(feature="semantic_search", ...))`.
- Any exception → `Result.fail(Errors.integration(service="embeddings", ...))`.

It embeds every candidate on every call — one request per candidate. It does not read the
vectors stored on the nodes.

### `_rank_similar_entities(source, entity_type, candidate_pool, *, exclude_uid, limit=5)`

The shared tail of every `find_similar_*`. Builds the canonical embedding text for the source and
each candidate with `build_embedding_text(entity_type, entity)`, drops `exclude_uid`, and
delegates to `_semantic_search`. An empty pool returns `Result.ok([])` without embedding
anything.

The caller owns the two backend reads, because the pool differs by domain:

| Domain family | Candidate pool |
|---------------|----------------|
| Activities | `backend.find_by(user_uid=source.user_uid)` — the owner's own entities, at most 100 (`find_by`'s default `limit`) |
| Curriculum | `backend.list(limit=...)` — shared content; PathStep passes 200, LearningPath 100 |

Entities past the cap are never ranked.

Do not hand-roll `f"{title} {description}"`: it drifts from the text the stored embeddings were
built from.

### `_publish_event(event)`

`await publish_event(self.event_bus, event, self.logger)`.

---

## Known Mismatch Between the Helpers and the Wired Services

Measured against the classes `_wire_ai_services` passes in. The `Any`-typed constructor
parameters on the base are why mypy does not see it.

| Helper | Written against | The wired service | Result today |
|--------|-----------------|-------------------|--------------|
| `_generate_insight` | a `generate` that returns text | `LLMService.generate` returns an `LLMResponse` dataclass (`content`, `provider`, `model`, `usage`, `error`) and never raises — a provider failure comes back as `LLMResponse(content="", error=...)` | `Result.ok` holds an `LLMResponse`, not a `str`. A method that returns it directly hands the object on; a method that parses it (`.strip()`, `.split()`) raises `AttributeError`. An LLM failure is reported as success. |
| `_semantic_search` | an `embed_text(text)` that returns a vector | `EmbeddingsService` has no `embed_text`; its method is `create_embedding(text) -> Result[list[float]]` | With one or more candidates, every call returns `Result.fail(Errors.integration(...))`. |

The unit tests replace `_generate_insight` and `_semantic_search` themselves, so they do not
exercise either call.

The correction belongs in the two helpers — one chokepoint each — not in their call sites.
Until it lands:

- Do not copy `response = insight_result.value` followed by string parsing as working code.
- Do not describe a `find_similar_*` method, or a method that parses LLM text, as working.
- In a test, pass a real `LLMService()` — with no arguments it is the MOCK provider and makes no
  network call — instead of replacing `_generate_insight`, so the test sees what the method
  sees.

---

## Routes

`adapters/inbound/ai_routes.py` registers one route per `AIRouteSpec`, at
`/api/{url_domain}/ai/{action}`, plus `/api/ai/status`.

```python
AIRouteSpec(
    "tasks",                # domain_attr — the attribute on the services container
    "Tasks",                # domain_label — used in messages
    "tasks",                # url_domain
    "insight",              # action
    "generate_task_insight",  # method_name on the AI service
    "uid",                  # signature: uid | uid_limit | query_limit | uid_level
    "tasks_ai_insight",     # func_name — unique
    "insight",              # wrap_key — the response is {"insight": value}
)
```

`scope` defaults to `ContentScope.USER_OWNED`; the PathStep and LearningPath specs set
`ContentScope.SHARED`. A new spec is owner-gated unless it says otherwise.

### The gates, in order

`_ai_route` runs them before the AI call. A request stopped by one never reaches the next.

| # | Gate | Answer when it stops the request |
|---|------|----------------------------------|
| 1 | Signed in | 401 |
| 2 | `facade.ai` is set | 503 `AI service unavailable` |
| 3 | The user's effective tier allows AI (`REGISTERED` is capped at CORE) | 403 `AI features require a paid subscription` |
| 4 | `USER_OWNED` with a uid: the user owns the entity | 404 |
| 5 | Daily LLM quota (`llm_quota_allowed`) — checked **and recorded** here | 403 `Daily AI quota exceeded` |
| 6 | The AI method's `Result` | 400 on any failure, with the error text |

The two 403s are told apart by their message, not their status.

### Measured behavior

Reproduced with a `TestClient`:

| Request | Status |
|---------|--------|
| No session | 401 |
| `GET`, `HEAD` or `POST` | handled — the routes are registered without `methods=`, and each of the three runs the gates and spends a quota unit |
| `PUT`, `DELETE` | 405 |
| A domain whose `.ai` is `None` | 503 |
| The AI method returns a failed `Result` — of any category | 400 |
| A spec whose `method_name` the service does not define | 500, after the quota unit is recorded |
| A spec with no `wrap_key` whose method returns a dict | 200, JSON |
| A spec with no `wrap_key` whose method returns a list | 200, `text/html` — FastHTML renders the list as a page |

The missing-method row is live for six specs: `tasks/ai/knowledge-generation`
(`identify_knowledge_generation`) and the five `knowledge/ai/*` routes (`find_related_steps`,
`semantic_search`, `generate_summary`, `explain_at_level`, `suggest_applications`), none of which
exists on `TasksAIService` / `PsAIService`.

The list-return row is live for six other specs: `goals/ai/milestones`, `events/ai/preparation`,
`events/ai/reflection`, `choices/ai/alternatives`, `principles/ai/practices` and
`path-steps/ai/practice`.

`GET /api/ai/status` answers `{"ai_available": {domain: bool}}` for a signed-in user.

### Adding a route

1. Write the method on the domain's AI service; it returns `Result[T]`.
2. Add an `AIRouteSpec` whose `method_name` is that method and whose `signature` matches its
   positional parameters — `uid` passes `(uid,)`, `uid_limit` passes `(uid, limit)`,
   `query_limit` passes `(query, limit)`, `uid_level` passes `(uid, level)`.
3. Give it a `wrap_key` unless the method returns a dict.
4. Leave `scope` at the default for a user-owned entity.
5. Check the spec resolves: `getattr(TasksAIService, spec.method_name)`.

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

Bound what reaches the model: truncate long fields, cap list lengths, and pass `max_tokens`.

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

### An unannotated broad `except`

Catch `LLM_EXCEPTIONS` (`core/utils/exception_types.py`). A catch-all around a provider call
carries a `# safety-net:` annotation (SKUEL017).

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
| `core/utils/vector_math.py` | `cosine_similarity`, `dot`, `l2_normalize` |

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
