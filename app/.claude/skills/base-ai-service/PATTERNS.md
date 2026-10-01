# BaseAIService Patterns

Each pattern is taken from a live service. The routes (Pattern 5) still carry the defects
listed in [SKILL.md](SKILL.md) § Measured behavior; the service methods answer as described.

---

## Pattern 1: `find_similar_*` for a User-Owned Domain

`TasksAIService.find_similar_tasks` (`core/services/tasks/tasks_ai_service.py`):

```python
async def find_similar_tasks(
    self, task_uid: str, limit: int = 5
) -> Result[list[tuple[EntityUID, float]]]:
    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return Result.fail(task_result)

    task = task_result.value
    if not task:
        return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

    all_tasks_result = await find_all_by(
        self.backend, self.logger, "Task similarity pool", user_uid=task.user_uid
    )
    if all_tasks_result.is_error:
        return Result.fail(all_tasks_result)

    return await self._rank_similar_entities(
        task,
        EntityType.TASK,
        all_tasks_result.value or [],
        exclude_uid=task_uid,
        limit=limit,
    )
```

- The candidate pool is drawn from the **source entity's owner's** entities. The method does not
  take a `user_uid` and checks nothing about the caller: reached through its route, `_ai_route`
  has verified the caller owns `task_uid`; a direct caller verifies ownership itself first.
- `_rank_similar_entities` ranks the pool by each model's stored `embedding` and leaves out a
  candidate that has none. The method passes models, not strings.
- **The pool is the owner's whole set.** `find_all_by` (`core/services/whole_set_read.py`) asks
  `find_by` for `QueryLimit.MAXIMUM` rows and logs a warning when it gets that many. The five
  other Activity `find_similar_*` methods make the same call.
- Nothing is embedded per call unless the source itself has no stored vector — then its
  canonical text is embedded once.

## Pattern 2: `find_similar_*` for Shared Curriculum

`PsAIService.find_similar_steps` (`core/services/ps/ps_ai_service.py`):

```python
async def find_similar_steps(
    self, ps_uid: str, limit: int = 5
) -> Result[list[tuple[EntityUID, float]]]:
    ps_result = await self.backend.get(ps_uid)
    if ps_result.is_error:
        return Result.fail(ps_result)

    ps = ps_result.value
    if not ps:
        return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

    return await rank_similar_curriculum(
        self.vector_search, NeoLabel.PATH_STEP, EntityType.PATH_STEP, ps, limit=limit
    )
```

- The source is still read by uid, so an unknown uid is not-found before any index query.
- The pool is the label's vector index, never `backend.list()`. `rank_similar_curriculum`
  (`core/services/curriculum_similarity.py`) sends the stored vector — or, for a source with
  none, the canonical text — through `Neo4jVectorSearchService`, whose index query withholds
  draft-marked curriculum. A similarity result is a listing, and the gate belongs to listings;
  opening one entity by its uid is a different case — a by-uid read is deliberately ungated, so
  a draft is unlisted rather than forbidden.
- The gate is a post-filter on the index's `limit + 1` nearest, so the answer can be shorter
  than `limit`. `LpAIService.find_similar_paths` is the same call on `NeoLabel.LEARNING_PATH`.
- Scores come back on the index's `[0, 1]` scale, thresholded at `ku_similar_min_score`.

## Pattern 3: An LLM Method

`TasksAIService.generate_task_insight`:

```python
async def generate_task_insight(self, task_uid: str) -> Result[str]:
    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return Result.fail(task_result)

    task = task_result.value
    if not task:
        return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

    context = {
        "title": task.title,
        "description": task.description or "No description",
        "status": task.status.value if task.status else "Unknown",
        "due_date": str(task.due_date) if task.due_date else "No deadline",
    }
    prompt = "Provide a brief, actionable insight about this task. Keep it under 100 words."

    return await self._generate_insight(prompt, context=context, max_tokens=200)
```

The shape to keep: fetch, guard not-found, build the context, one helper call, return its
`Result` — `Result.ok(str)`, or the provider's failure as `Errors.integration(service="llm")`.

**The live method does not bound its input.** `task.description` is passed whole, and
`TaskCreateRequest.description` has no maximum length; `max_tokens` caps the reply, not the
prompt. A new method truncates each free-text field before it goes into the context — see
§ Anti-Patterns, Unbounded input.

Entity fields reach the model as written by the user. Treat the output as untrusted text: it is
data for display, never an instruction to act on.

## Pattern 4: A Facade Method with an Analytics Fallback

`PsService.search_by_semantic_query` (`core/services/ps_service.py`):

```python
if self.ai is None:
    return await self.search.search(query=query_text, limit=limit)
return await self.ai.search_by_semantic_query(query_text, limit, min_score)
```

Where no analytics answer can stand in, fail with the reason:

```python
if self.ai is None:
    return Result.fail(
        Errors.system(
            message="AI service required for step application suggestions",
            operation="suggest_step_applications",
        )
    )
return await self.ai.suggest_step_applications(ps_uid)
```

Choose one per method and say which in its docstring. A caller must be able to tell a keyword
result from a semantic one when it matters.

## Pattern 5: A Route

One line in `AI_ROUTE_SPECS` (`adapters/inbound/ai_routes.py`):

```python
AIRouteSpec(
    "goals", "Goals", "goals", "milestones",
    "generate_milestones", "uid", "goals_ai_milestones", "milestones",
)
```

- `signature="uid"` passes only `(uid,)`. `generate_milestones(goal_uid, max_milestones=5)` is
  called with its default — a parameter the signature does not carry cannot be set over HTTP.
- The answer is always JSON, through `result_to_response`. With a `wrap_key` the body is
  `{wrap_key: value}`; with none it is the value itself. A method that returns a dict needs no
  key; any other return type takes one so the body names what it carries —
  `test_every_non_dict_method_has_a_wrap_key` reads the return annotation and fails otherwise.
- `func_name` must be unique across the list: FastHTML names the route after it.
- The route is `POST` only and CSRF-protected; the factories add both.

A spec that names nothing does not become a route: `create_ai_routes` runs
`unresolved_ai_route_specs(AI_ROUTE_SPECS)` first and raises `ValueError` on a `domain_attr`
without a class in `AI_SERVICE_CLASSES`, a `method_name` the class lacks, or a `signature`
without a factory. `test_live_specs_all_resolve` pins the live list clean and
`test_registration_refuses_a_spec_naming_no_method` pins the refusal
(`tests/unit/adapters/test_ai_routes_http.py`).

---

## Testing

### Against real-shaped services

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.embeddings_service import EmbeddingsService
from core.services.llm_service import LLMService
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.result_simplified import Result


@pytest.fixture
def tasks_ai() -> TasksAIService:
    task = MagicMock(uid="task_a", title="Write report", description="", user_uid="user_a")
    backend = MagicMock()
    backend.get = AsyncMock(return_value=Result.ok(task))
    backend.find_by = AsyncMock(return_value=Result.ok([task]))

    embeddings = MagicMock(
        spec=[name for name in dir(EmbeddingsService) if not name.startswith("__")]
    )
    return TasksAIService(
        backend=backend,
        llm_service=LLMService(),
        embeddings_service=embeddings,
    )
```

- `LLMService()` with no arguments is the MOCK provider: canned text, no network, the real
  return type.
- The embeddings mock is limited to the names the real class has, so a call to a method that
  does not exist raises, as it would in production. Pass the name list — `spec=EmbeddingsService`
  evaluates the class's annotations and fails on a `TYPE_CHECKING`-only name.

### With the helper replaced

`tests/unit/services/tasks/test_tasks_ai_priority_suggestion.py` replaces `_generate_insight`
with an `AsyncMock` returning `Result.ok("<text>")`. That tests the method's parsing of text. It
does not test what the helper returns.

### The routes

Patch `require_authenticated_user` and `llm_quota_allowed` in `adapters.inbound.ai_routes`, build
a container whose facades carry `.ai` and `verify_ownership`, call `create_ai_routes(app, rt,
services)`, and drive it with a `TestClient`. `POST`, with a `csrf_token` cookie and the same
value in `X-CSRF-Token` (`mint_token()` from `adapters.inbound.csrf`) — without them the request
stops at 405 or 403 before the gates. Count the calls to the quota function: a request stopped
by an earlier gate records none. `tests/unit/adapters/test_ai_routes_http.py` is the worked
example.

---

## Anti-Patterns

### Hand-built embedding text

```python
# WRONG - differs from the text the stored vectors were built from
candidates = [(t.uid, f"{t.title} {t.description}") for t in tasks]

# CORRECT
return await self._rank_similar_entities(
    task, EntityType.TASK, tasks, exclude_uid=task.uid, limit=limit
)
```

### Unbounded input

```python
# WRONG - the whole body, no cap
prompt = f"Summarize: {step.content}"

# CORRECT
excerpt = step.description[:2000] if step.description else ""
result = await self._generate_insight(
    "Summarize this path step.", context={"description": excerpt}, max_tokens=200
)
```

### A failed call reported as an empty answer

```python
# WRONG
similar = await self.ai.find_similar_tasks(uid)
return Result.ok({"similar": similar.value if similar.is_ok else []})

# CORRECT
similar = await self.ai.find_similar_tasks(uid)
if similar.is_error:
    return Result.fail(similar)
return Result.ok({"similar": similar.value})
```

### Writing an embedding from an AI service

Stored vectors are written by the embedding worker from `*EmbeddingRequested` events (ADR-074).
An AI service that stores one bypasses the content-hash check and the version stamp.
