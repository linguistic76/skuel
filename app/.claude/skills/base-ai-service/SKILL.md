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

### Class Hierarchy

```
BaseAIService[B, T]
    │
    ├── TasksAIService        (planned)
    ├── GoalsAIService        (planned)
    ├── HabitsAIService       (planned)
    ├── KuAIService           (planned)
    └── ... (domain AI services as needed)
```

**Note:** As of January 2026, domain AI services are planned but not yet implemented. All 10 domain intelligence services currently extend `BaseAnalyticsService` (pure graph analytics).

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
        graph_intelligence_service: Any | None = None,
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

### `_get_embedding(text)` - Generate Embedding Vector

```python
async def _get_embedding(self, text: str) -> Result[list[float]]:
    """
    Get embedding vector for text using embeddings service.

    Returns:
        Result containing embedding vector or error
    """
```

**Usage:**
```python
result = await self._get_embedding("machine learning basics")
if result.is_ok:
    embedding = result.value  # list[float]
```

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

### `_cosine_similarity(vec1, vec2)` - Vector Similarity

```python
@staticmethod
def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
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
from core.models.task import Task
from core.services.base_ai_service import BaseAIService
from core.ports import TasksOperations
from core.utils.result_simplified import Result


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
        user_uid: str,
        top_k: int = 5,
    ) -> Result[list[tuple[Task, float]]]:
        """
        Find semantically similar tasks.

        Args:
            task_uid: Reference task UID
            user_uid: User's UID (for ownership filtering)
            top_k: Number of results

        Returns:
            Result containing list of (Task, similarity_score) tuples
        """
        # Get reference task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return task_result

        reference = task_result.value

        # Get user's tasks
        all_tasks_result = await self.backend.find_by(created_by=user_uid)
        if all_tasks_result.is_error:
            return all_tasks_result

        # Prepare candidates (exclude self)
        candidates = [
            (t.uid, f"{t.title} {t.description or ''}")
            for t in all_tasks_result.value
            if t.uid != task_uid
        ]

        # Semantic search
        search_result = await self._semantic_search(
            query=f"{reference.title} {reference.description or ''}",
            candidates=candidates,
            top_k=top_k,
        )
        if search_result.is_error:
            return search_result

        # Fetch full task objects
        results: list[tuple[Task, float]] = []
        for uid, score in search_result.value:
            task_result = await self.backend.get(uid)
            if task_result.is_ok:
                results.append((task_result.value, score))

        return Result.ok(results)

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
        user_uid: str,
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
# At bootstrap (when AI is enabled)
tasks_ai = TasksAIService(
    backend=tasks_backend,
    llm_service=llm,
    embeddings_service=embeddings,
)
tasks_service = TasksService(
    backend=tasks_backend,
    ai_service=tasks_ai,  # Optional
)

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

All AI methods return `Result[T]`:

```python
async def _get_embedding(self, text: str) -> Result[list[float]]:
    if not self.embeddings:
        return Result.fail(
            Errors.system(
                message="Embeddings service not available",
                operation="get_embedding",
            )
        )

    try:
        embedding = await self.embeddings.embed_text(text)
        return Result.ok(embedding)
    except Exception as e:
        return Result.fail(
            Errors.integration(
                message=f"Embedding generation failed: {e}",
                service="embeddings",
            )
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
| **Fail-Fast Guards** | `_require_graph_intelligence()` | `_require_llm_service()` |

---

## Related Skills

- [base-analytics-service](../base-analytics-service/SKILL.md) - Graph analytics (no AI)
- [user-context-intelligence](../user-context-intelligence/SKILL.md) - Central cross-domain intelligence
- [result-pattern](../result-pattern/SKILL.md) - Result[T] error handling
