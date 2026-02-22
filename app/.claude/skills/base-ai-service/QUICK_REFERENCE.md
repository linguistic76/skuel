# BaseAIService Quick Reference

## File Locations

### Core Files

| File | Purpose |
|------|---------|
| `/core/services/base_ai_service.py` | Base class (~337 lines) |
| `/core/services/base_analytics_service.py` | Analytics base (separate skill) |

### Domain AI Services

| Domain | File | Status |
|--------|------|--------|
| Tasks | `/core/services/tasks/tasks_ai_service.py` | Planned |
| Goals | `/core/services/goals/goals_ai_service.py` | Planned |
| KU | `/core/services/ku/ku_ai_service.py` | Planned |

**Note:** Domain AI services are planned but not yet implemented (January 2026).

---

## Imports

### Base Class

```python
from core.services.base_ai_service import BaseAIService
```

### Result Pattern

```python
from core.utils.result_simplified import Result
from core.utils.errors_simplified import Errors
```

### Protocols

```python
from core.ports import TasksOperations, GoalsOperations  # etc.
```

---

## Class Signature

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

---

## Method Signatures

### Fail-Fast Guards

```python
def _require_llm_service(self, operation: str) -> None:
    """Raises ValueError if LLM not available."""

def _require_embeddings_service(self, operation: str) -> None:
    """Raises ValueError if embeddings not available."""
```

### AI Helpers

```python
async def _get_embedding(self, text: str) -> Result[list[float]]:
    """Get embedding vector for text."""

async def _generate_insight(
    self,
    prompt: str,
    context: dict[str, Any] | None = None,
    max_tokens: int = 500,
) -> Result[str]:
    """Generate AI insight using LLM."""

async def _semantic_search(
    self,
    query: str,
    candidates: list[tuple[str, str]],  # [(uid, text), ...]
    top_k: int = 5,
) -> Result[list[tuple[str, float]]]:  # [(uid, score), ...]
    """Perform semantic search using embeddings."""

@staticmethod
def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between vectors."""
```

### Event Handling

```python
def _register_event_handlers(self) -> None:
    """Auto-register handlers from _event_handlers."""

async def _publish_event(self, event: Any) -> None:
    """Publish event to bus if available."""
```

---

## Instance Attributes After Init

| Attribute | Type | Nullable | Purpose |
|-----------|------|----------|---------|
| `backend` | `B` | No | Domain operations |
| `llm` | `LLMService` | Yes* | LLM for insights |
| `embeddings` | `EmbeddingsService` | Yes* | Semantic search |
| `graph_intel` | `GraphIntelligenceService` | Yes | Graph queries |
| `relationships` | `UnifiedRelationshipService` | Yes | Relationships |
| `event_bus` | `EventBus` | Yes | Event publishing |
| `logger` | `Logger` | No | Hierarchical logger |

*Required by default unless `_require_llm = False` or `_require_embeddings = False`.

---

## Class Attribute Configuration

| Attribute | Default | Description |
|-----------|---------|-------------|
| `_service_name` | `None` | Logger name (e.g., "tasks.ai") |
| `_require_llm` | `True` | Fail if LLM not provided |
| `_require_embeddings` | `True` | Fail if embeddings not provided |
| `_event_handlers` | `{}` | Event type → method name mapping |

**Example - LLM only (no embeddings):**
```python
class InsightOnlyService(BaseAIService[Backend, Model]):
    _require_embeddings = False  # Don't fail without embeddings
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

For graph analytics features, see the **[base-analytics-service](../base-analytics-service/SKILL.md)** skill.

---

## Common Patterns

### Minimal AI Service

```python
class TasksAIService(BaseAIService[TasksOperations, Task]):
    _service_name = "tasks.ai"

    async def find_similar(self, uid: str) -> Result[list[Task]]:
        # Get reference
        ref = await self.backend.get(uid)
        if ref.is_error:
            return ref

        # Get candidates
        all_tasks = await self.backend.find_by()
        candidates = [(t.uid, t.title) for t in all_tasks.value if t.uid != uid]

        # Semantic search
        results = await self._semantic_search(ref.value.title, candidates)
        # ... fetch and return tasks
```

### Embeddings-Only Service

```python
class SemanticSearchService(BaseAIService[Backend, Model]):
    _service_name = "search.semantic"
    _require_llm = False  # Don't need LLM
```

### LLM-Only Service

```python
class InsightService(BaseAIService[Backend, Model]):
    _service_name = "insights"
    _require_embeddings = False  # Don't need embeddings
```

---

## Error Types

| Error | Use Case |
|-------|----------|
| `Errors.system(...)` | Service not available |
| `Errors.integration(...)` | External service failure |
| `Errors.not_found(...)` | Entity not found |

```python
# Service unavailable
return Result.fail(Errors.system(
    message="Embeddings service not available",
    operation="semantic_search",
))

# External failure
return Result.fail(Errors.integration(
    message=f"LLM generation failed: {e}",
    service="llm",
))
```
