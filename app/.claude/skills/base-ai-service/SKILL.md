# BaseAIService Skill

> Expert guide for creating and modifying domain AI services using BaseAIService.

## When to Use This Skill

Use this skill when:
- Adding AI-powered features to a domain (semantic search, LLM insights)
- Implementing `BaseAIService[B, T]` subclasses
- Working with embeddings or LLM integration
- Understanding the AI vs Analytics separation (ADR-030)

## Quick Reference

```python
# Import
from core.services.base_ai_service import BaseAIService

# Implementation
class TasksAIService(BaseAIService[TasksOperations, Task]):
    _service_name = "tasks.ai"
    _require_llm = True        # Fail if LLM not provided (default)
    _require_embeddings = True  # Fail if embeddings not provided (default)
```

---

## 1. Architecture Overview

### AI vs Analytics Separation (ADR-030)

SKUEL separates intelligence into two layers:

| Layer | Base Class | Dependencies | Purpose |
|-------|------------|--------------|---------|
| **Analytics** | `BaseAnalyticsService` | Graph + Python only | Works without LLM |
| **AI** | `BaseAIService` | LLM + Embeddings | Optional AI features |

**Philosophy:** AI services are OPTIONAL. The app functions fully without them. They enhance the user experience with:
- Semantic search (find similar items by meaning)
- Natural language insights (AI-generated explanations)
- Intelligent recommendations (context-aware suggestions)

**Where the vendor SDKs live (W1 / ADR-063):** A `BaseAIService` depends on `LLMService` and `EmbeddingsService` (the `llm` / `embeddings` instance attributes below). Those two services no longer construct any SDK client — each takes an **injected** port: `LLMService(chat_port=ChatCompletionPort)` and `EmbeddingsService(embedding_client=EmbeddingClientOperations)`. The concrete `openai` / `anthropic` / `huggingface_hub` clients live below the hexagonal boundary in `adapters/external/llm/` and `adapters/external/embeddings/`; the composition root reads the credential and injects the adapter. So `core/` — including every AI service — is free of vendor-SDK clients (guarded by `tests/unit/test_llm_sdk_boundary.py`). See `/docs/decisions/ADR-063-llm-embeddings-sdk-ports.md`.

**Where persisted embeddings come from (ADR-074):** AI services *consume* node embeddings; they never write them. Entity + chunk vectors are written by the `EmbeddingBackgroundWorker` (fed by the `*EmbeddingRequested` chokepoint `core/events/embedding_publisher.py` — all create/update paths and both ingest doors publish post-persist) and by the backfill script (`scripts/generate_embeddings_batch.py`, `--stale` for re-embeds). Ingestion never embeds inline. See `/docs/decisions/ADR-074-post-persist-embedding-events.md`.

### Class Hierarchy

```
BaseAIService[B, T]
    │
    ├── TasksAIService        (implemented)
    ├── GoalsAIService        (implemented)
    ├── HabitsAIService       (implemented)
    ├── EventsAIService       (implemented)
    ├── ChoicesAIService      (implemented)
    ├── PrinciplesAIService   (implemented)
    ├── PsAIService           (implemented — Curriculum)
    ├── LpAIService           (implemented — Curriculum)
    ├── AskesisAIService      (implemented — cross-cutting)
    ├── ContextAwareAIService (implemented — cross-cutting)
    ├── KuAIService           (planned)
    └── ... (domain AI services as needed)
```

**Note:** All 6 Activity Domain AI services and the PS and LP Curriculum AI services are implemented and wired via `services_bootstrap/_ai_wiring.py`. KuAIService remains planned.

---

## 2. Class Signature

```python
class BaseAIService(Generic[B, T]):
    """Base class for domain AI services (LLM/embeddings-powered features)."""

    # Class attributes
    _service_name: ClassVar[str | None] = None
    _require_llm: ClassVar[bool] = True
    _require_embeddings: ClassVar[bool] = True
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,                                    # REQUIRED
        llm_service: Any | None = None,               # Required by default
        embeddings_service: Any | None = None,        # Required by default
        graph_intel: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None: ...
```

### Class Attributes

| Attribute | Type | Default | Purpose |
|-----------|------|---------|---------|
| `_service_name` | `str \| None` | `None` | Logger name (e.g., "tasks.ai") |
| `_require_llm` | `bool` | `True` | Fail if LLM not provided |
| `_require_embeddings` | `bool` | `True` | Fail if embeddings not provided |
| `_event_handlers` | `dict[type, str]` | `{}` | Event type → handler method name |

### Instance Attributes

| Attribute | Type | Purpose |
|-----------|------|---------|
| `backend` | `B` | Domain operations (REQUIRED) |
| `llm` | `LLMService \| None` | LLM for insights/generation |
| `embeddings` | `EmbeddingsService \| None` | Embeddings for semantic search |
| `graph_intel` | `GraphIntelligenceService \| None` | Graph context retrieval |
| `relationships` | `UnifiedRelationshipService \| None` | Relationship queries |
| `event_bus` | `EventBus \| None` | Event publishing/subscription |
| `logger` | `Logger` | Hierarchical logger (`skuel.ai.*`) |

---

## 3. Fail-Fast Guards

### Constructor Validation

```python
def __init__(self, backend, llm_service=None, embeddings_service=None, ...):
    # Backend is ALWAYS required
    if not backend:
        raise ValueError(f"{service_name} backend is REQUIRED.")

    # LLM required if _require_llm = True
    if self._require_llm and not llm_service:
        raise ValueError(f"{class_name} requires llm_service.")

    # Embeddings required if _require_embeddings = True
    if self._require_embeddings and not embeddings_service:
        raise ValueError(f"{class_name} requires embeddings_service.")
```

### Runtime Guards

Use these in methods that optionally use AI:

```python
def _require_llm_service(self, operation: str) -> None:
    """Raises ValueError if LLM not available."""
    if not self.llm:
        raise ValueError(f"{self.__class__.__name__}.{operation}() requires llm_service")

def _require_embeddings_service(self, operation: str) -> None:
    """Raises ValueError if embeddings not available."""
    if not self.embeddings:
        raise ValueError(f"{self.__class__.__name__}.{operation}() requires embeddings_service")
```

**Usage:**
```python
async def get_semantic_similar(self, uid: str) -> Result[list[T]]:
    self._require_embeddings_service("get_semantic_similar")
    # Now safe to use self.embeddings
```

---

## 4. AI Helper Methods

### `_generate_insight(prompt, context, max_tokens)` - LLM Generation

```python
async def _generate_insight(
    self,
    prompt: str,
    context: dict[str, Any] | None = None,
    max_tokens: int = 500,
) -> Result[str]:
    """
    Generate AI insight using LLM service.

    Args:
        prompt: The prompt for the LLM
        context: Optional context dict (formatted and prepended)
        max_tokens: Maximum tokens in response

    Returns:
        Result containing generated text or error
    """
```

**Usage:**
```python
result = await self._generate_insight(
    prompt="Analyze this task and suggest improvements.",
    context={"title": task.title, "status": task.status.value},
    max_tokens=300,
)
if result.is_ok:
    insight = result.value  # str
```

### `_semantic_search(query, candidates, top_k)` - Semantic Similarity Search

```python
async def _semantic_search(
    self,
    query: str,
    candidates: list[tuple[str, str]],  # [(uid, text), ...]
    top_k: int = 5,
) -> Result[list[tuple[str, float]]]:  # [(uid, similarity), ...]
    """
    Perform semantic search using embeddings.

    Args:
        query: Search query
        candidates: List of (uid, text) tuples to search
        top_k: Number of results to return

    Returns:
        Result containing list of (uid, similarity_score) tuples, sorted by similarity
    """
```

**Usage:**
```python
# Find similar tasks
candidates = [(t.uid, t.title) for t in all_tasks]
result = await self._semantic_search("urgent deadline", candidates, top_k=5)
if result.is_ok:
    for uid, score in result.value:
        print(f"{uid}: {score:.3f}")
```

### Vector Similarity

`_semantic_search` ranks candidates with the shared cosine kernel in
`core/utils/vector_math.py` — import it, don't reimplement:

```python
from core.utils.vector_math import cosine_similarity, dot, l2_normalize

cosine_similarity(vec1, vec2)  # 0.0 for empty / mismatched / zero-norm inputs
# normalize-once, dot-many:  dot(l2_normalize(a), l2_normalize(b))
```

---

## 5. Event Handling

Same pattern as BaseAnalyticsService:

```python
# Define handlers in class
_event_handlers: ClassVar[dict[type, str]] = {
    TaskCompleted: "_handle_task_completed",
}

async def _handle_task_completed(self, event: TaskCompleted) -> None:
    """React to task completion."""
    # Update AI models, regenerate embeddings, etc.

# Publish events
await self._publish_event(SomeEvent(uid=uid, user_uid=user_uid))
```

---

## 6. Complete Implementation Example

```python
from typing import Any, ClassVar

from core.events import TaskCompleted
from core.models.enums.entity_enums import EntityType
from core.models.task import Task
from core.models.type_hints import EntityUID
from core.ports import TasksOperations
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result


class TasksAIService(BaseAIService[TasksOperations, Task]):
    """AI-powered features for Tasks domain."""

    _service_name: ClassVar[str] = "tasks.ai"
    _require_llm: ClassVar[bool] = True
    _require_embeddings: ClassVar[bool] = True
    _event_handlers: ClassVar[dict[type, str]] = {
        TaskCompleted: "_handle_task_completed",
    }

    # ========================================================================
    # SEMANTIC SEARCH
    # ========================================================================

    async def find_similar_tasks(
        self,
        task_uid: str,
        limit: int = 5,
    ) -> Result[list[tuple[EntityUID, float]]]:
        """
        Find semantically similar tasks.

        The caller owns only the (typed) backend I/O — fetch the source and the
        candidate pool. Ranking is the shared tail: `_rank_similar_entities` builds
        canonical embedding text (`build_embedding_text`) for the source and every
        candidate, excludes the source, and delegates to `_semantic_search`. Do NOT
        hand-roll `f"{title} {description}"` — that drifts from the stored-embedding
        representation.
        """
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result)
        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        all_tasks_result = await self.backend.find_by(user_uid=task.user_uid)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result)

        return await self._rank_similar_entities(
            task,
            EntityType.TASK,
            all_tasks_result.value or [],
            exclude_uid=task_uid,
            limit=limit,
        )

    # ========================================================================
    # AI INSIGHTS
    # ========================================================================

    async def generate_task_insights(
        self,
        task_uid: str,
    ) -> Result[str]:
        """
        Generate AI-powered insights for a task.

        Args:
            task_uid: Task to analyze

        Returns:
            Result containing insight text
        """
        # Get task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return task_result

        task = task_result.value

        # Generate insight
        return await self._generate_insight(
            prompt=(
                "Analyze this task and provide 2-3 actionable suggestions "
                "for completing it effectively."
            ),
            context={
                "title": task.title,
                "description": task.description or "No description",
                "priority": task.priority.value if task.priority else "normal",
                "status": task.status.value,
                "due_date": str(task.due_date) if task.due_date else "No deadline",
            },
            max_tokens=300,
        )

    # ========================================================================
    # INTELLIGENT RECOMMENDATIONS
    # ========================================================================

    async def get_priority_recommendations(
        self,
        user_uid: UserUID,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get AI-powered priority recommendations.

        Uses semantic analysis + LLM to suggest task prioritization.
        """
        # Get user's incomplete tasks
        tasks_result = await self.backend.find_by(
            created_by=user_uid,
            status="active",
        )
        if tasks_result.is_error:
            return tasks_result

        tasks = tasks_result.value
        if not tasks:
            return Result.ok([])

        # Build context for LLM
        task_list = "\n".join(
            f"- {t.title} (priority: {t.priority.value if t.priority else 'none'}, "
            f"due: {t.due_date or 'no deadline'})"
            for t in tasks[:10]  # Limit to avoid token overflow
        )

        insight = await self._generate_insight(
            prompt=(
                "Based on these tasks, suggest the optimal order to work on them. "
                "Consider urgency, dependencies, and effort. "
                "Return a numbered list with brief reasoning."
            ),
            context={"tasks": task_list},
            max_tokens=400,
        )

        if insight.is_error:
            return insight

        return Result.ok([{
            "recommendation": insight.value,
            "task_count": len(tasks),
        }])

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def _handle_task_completed(self, event: TaskCompleted) -> None:
        """React to task completion - could update embeddings, etc."""
        self.logger.debug(f"Task completed: {event.task_uid}")
        # Future: Update task embeddings, regenerate recommendations
```

---

## 7. Integration Patterns

### Facade Access

AI services are accessed through domain facades:

```python
# AI services created and wired by _wire_ai_services() in services_bootstrap/_ai_wiring.py
# (called from compose_services when llm_service and embeddings_service are available)
tasks_ai = TasksAIService(
    backend=activity_services["tasks"].core.backend,
    llm_service=llm_service,
    embeddings_service=embeddings_service,
)
activity_services["tasks"].ai = tasks_ai  # Post-construction wiring

# Usage
if tasks_service.ai:
    similar = await tasks_service.ai.find_similar_tasks(uid, user_uid)
    insights = await tasks_service.ai.generate_task_insights(uid)
```

### Graceful Degradation

When AI is not available:

```python
async def get_task_analysis(task_uid: str) -> dict[str, Any]:
    # Always available: graph analytics
    analytics = await tasks_service.analytics.get_behavioral_insights(user_uid)

    # Optional: AI insights
    ai_insights = None
    if tasks_service.ai:
        result = await tasks_service.ai.generate_task_insights(task_uid)
        if result.is_ok:
            ai_insights = result.value

    return {
        "analytics": analytics.value if analytics.is_ok else None,
        "ai_insights": ai_insights,
    }
```

---

## 8. Error Handling

All AI methods return `Result[T]`. Call `self.embeddings.create_embedding(text)` directly
(wrapping with `Result.fail` on error) — the `_get_embedding` helper was removed in
bloat campaign 18b as it had no callers:

```python
async def my_ai_method(self, text: str) -> Result[list[float]]:
    if not self.embeddings:
        return Result.fail(
            Errors.unavailable(feature="embeddings", operation="my_ai_method")
        )
    try:
        result = await self.embeddings.create_embedding(text)
        if result.is_error:
            return result
        return result
    except Exception as e:  # safety-net: embeddings service raises varied exceptions
        return Result.fail(
            Errors.integration(message=f"Embedding failed: {e}", service="embeddings")
        )
```

---

## 9. Key Differences: Analytics vs AI

| Aspect | BaseAnalyticsService | BaseAIService |
|--------|---------------------|---------------|
| **Dependencies** | graph_intel, relationships | llm, embeddings |
| **AI Required?** | No | Yes (configurable) |
| **Purpose** | Graph analytics | AI enhancements |
| **App Runs Without?** | Yes (full capacity) | Yes (limited features) |
| **Logger Prefix** | `skuel.analytics.*` | `skuel.ai.*` |
| **Fail-Fast Guards** | inline `if not self.graph_intel` | `_require_llm_service()` |

---

## 10. Prompt Templates (PROMPT_REGISTRY)

All LLM prompts go in `core/prompts/templates/` — never inline in service code.

```python
from core.prompts import PROMPT_REGISTRY

# In an AI service method
prompt = PROMPT_REGISTRY.render("activity_feedback",
    time_period="7d",
    stats_json=json.dumps(stats),
    insights_section=insights_text,
)
result = await self._generate_insight(prompt)
```

The inline prompt string in `generate_task_insights()` above (Section 6) — `"Analyze this task..."` — illustrates the pattern but should be a named template in `core/prompts/templates/` when the service is implemented for real. The template approach makes prompts editable without touching Python and keeps service code free of prompt engineering details.

**See:** `@prompt-templates` skill — registry architecture, template catalog, naming conventions, Askesis roadmap

---

## Related Skills

- [base-analytics-service](../base-analytics-service/SKILL.md) - Graph analytics (no AI)
- [user-context-intelligence](../user-context-intelligence/SKILL.md) - Central cross-domain intelligence
- [result-pattern](../result-pattern/SKILL.md) - Result[T] error handling
- [prompt-templates](../prompt-templates/SKILL.md) - Centralized LLM prompt registry
