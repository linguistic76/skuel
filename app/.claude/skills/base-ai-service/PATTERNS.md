# BaseAIService Patterns

> Implementation patterns for AI-powered domain services.

## Pattern 1: Semantic Search Service

Find entities by semantic similarity (meaning, not keywords).

```python
from typing import ClassVar

from core.models.task import Task
from core.services.base_ai_service import BaseAIService
from core.ports import TasksOperations
from core.utils.result_simplified import Result


class TasksAIService(BaseAIService[TasksOperations, Task]):
    """AI-powered semantic search for tasks."""

    _service_name: ClassVar[str] = "tasks.ai"
    _require_llm: ClassVar[bool] = False  # Only need embeddings
    _require_embeddings: ClassVar[bool] = True

    async def find_similar_tasks(
        self,
        task_uid: str,
        user_uid: str,
        top_k: int = 5,
    ) -> Result[list[tuple[Task, float]]]:
        """
        Find semantically similar tasks.

        Returns list of (task, similarity_score) tuples.
        """
        # Get reference task
        ref_result = await self.backend.get(task_uid)
        if ref_result.is_error:
            return ref_result

        reference = ref_result.value

        # Get user's tasks
        tasks_result = await self.backend.find_by(created_by=user_uid)
        if tasks_result.is_error:
            return tasks_result

        # Prepare candidates (exclude self)
        candidates = [
            (t.uid, f"{t.title} {t.description or ''}")
            for t in tasks_result.value
            if t.uid != task_uid
        ]

        if not candidates:
            return Result.ok([])

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
```

**Key Points:**
- Set `_require_llm = False` for embeddings-only services
- Use `_semantic_search()` for similarity matching
- Return similarity scores for transparency

---

## Pattern 2: LLM Insight Generation

Generate natural language insights using LLM.

```python
from typing import Any, ClassVar

from core.models.goal import Goal
from core.services.base_ai_service import BaseAIService
from core.ports import GoalsOperations
from core.utils.result_simplified import Result


class GoalsAIService(BaseAIService[GoalsOperations, Goal]):
    """AI-powered insights for goals."""

    _service_name: ClassVar[str] = "goals.ai"
    _require_llm: ClassVar[bool] = True
    _require_embeddings: ClassVar[bool] = False  # Only need LLM

    async def generate_goal_strategy(
        self,
        goal_uid: str,
    ) -> Result[str]:
        """Generate strategic recommendations for achieving a goal."""
        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return goal_result

        goal = goal_result.value

        # Build context
        context = {
            "title": goal.title,
            "description": goal.description or "No description",
            "timeframe": goal.timeframe.value if goal.timeframe else "unspecified",
            "progress": f"{goal.progress_percentage}%" if hasattr(goal, 'progress_percentage') else "unknown",
        }

        # Generate insight
        return await self._generate_insight(
            prompt=(
                "Analyze this goal and provide 3 specific, actionable strategies "
                "to accelerate progress. Be concise and practical."
            ),
            context=context,
            max_tokens=400,
        )

    async def suggest_milestones(
        self,
        goal_uid: str,
        count: int = 3,
    ) -> Result[list[dict[str, Any]]]:
        """Suggest milestones for breaking down a goal."""
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return goal_result

        goal = goal_result.value

        insight = await self._generate_insight(
            prompt=(
                f"Suggest {count} concrete milestones to break down this goal. "
                "Format each as: [Milestone Name]: [Brief description]. "
                "Make them specific and measurable."
            ),
            context={"goal": goal.title, "description": goal.description or ""},
            max_tokens=300,
        )

        if insight.is_error:
            return insight

        # Parse insight into structured format
        return Result.ok([{
            "raw_suggestions": insight.value,
            "goal_uid": goal_uid,
            "suggested_count": count,
        }])
```

**Key Points:**
- Set `_require_embeddings = False` for LLM-only services
- Use structured `context` dict for relevant information
- Set appropriate `max_tokens` to control response length

---

## Pattern 3: Hybrid AI + Graph Analytics

Combine AI insights with graph analytics.

```python
from typing import Any, ClassVar

from core.models.ku import KnowledgeUnit
from core.services.base_ai_service import BaseAIService
from core.ports import KuOperations
from core.utils.result_simplified import Result


class KuAIService(BaseAIService[KuOperations, KnowledgeUnit]):
    """AI-powered features for Knowledge Units."""

    _service_name: ClassVar[str] = "ku.ai"

    async def get_enriched_knowledge(
        self,
        ku_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Get knowledge unit with AI-enriched context.

        Combines:
        - Graph relationships (from graph_intel)
        - Semantic similar units (from embeddings)
        - AI-generated summary (from LLM)
        """
        # Get base KU
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return ku_result

        ku = ku_result.value
        result: dict[str, Any] = {"ku": ku}

        # Graph context (if available)
        if self.graph_intel:
            context = await self.graph_intel.get_entity_context(ku_uid, depth=2)
            if context.is_ok:
                result["graph_context"] = context.value

        # Semantic similar (if embeddings available)
        if self.embeddings:
            all_kus = await self.backend.find_by()
            if all_kus.is_ok:
                candidates = [
                    (k.uid, k.title)
                    for k in all_kus.value
                    if k.uid != ku_uid
                ]
                similar = await self._semantic_search(ku.title, candidates, top_k=3)
                if similar.is_ok:
                    result["similar_topics"] = similar.value

        # AI summary (if LLM available)
        if self.llm:
            summary = await self._generate_insight(
                prompt="Summarize this knowledge in 2-3 sentences for quick review.",
                context={"title": ku.title, "content": ku.content[:500]},
                max_tokens=150,
            )
            if summary.is_ok:
                result["ai_summary"] = summary.value

        return Result.ok(result)
```

**Key Points:**
- Check service availability before use (`if self.embeddings:`)
- Combine graph + semantic + LLM for rich results
- Gracefully handle missing services

---

## Pattern 4: Batch Embedding Generation

Efficiently process multiple items.

```python
from typing import ClassVar

from core.models.ku import KnowledgeUnit
from core.services.base_ai_service import BaseAIService
from core.ports import KuOperations
from core.utils.result_simplified import Errors, Result


class KuEmbeddingService(BaseAIService[KuOperations, KnowledgeUnit]):
    """Batch embedding management for KUs."""

    _service_name: ClassVar[str] = "ku.embeddings"
    _require_llm: ClassVar[bool] = False

    async def generate_embeddings_batch(
        self,
        ku_uids: list[str],
    ) -> Result[dict[str, list[float]]]:
        """
        Generate embeddings for multiple KUs.

        Returns:
            Dict mapping uid -> embedding vector
        """
        results: dict[str, list[float]] = {}
        errors: list[str] = []

        for uid in ku_uids:
            # Get KU
            ku_result = await self.backend.get(uid)
            if ku_result.is_error:
                errors.append(f"{uid}: not found")
                continue

            ku = ku_result.value

            # Generate embedding
            text = f"{ku.title} {ku.content[:1000]}"
            embedding_result = await self._get_embedding(text)

            if embedding_result.is_ok:
                results[uid] = embedding_result.value
            else:
                errors.append(f"{uid}: embedding failed")

        if errors and not results:
            return Result.fail(
                Errors.integration(
                    message=f"All embeddings failed: {errors}",
                    service="embeddings",
                )
            )

        self.logger.info(f"Generated {len(results)} embeddings, {len(errors)} errors")
        return Result.ok(results)
```

**Key Points:**
- Process items individually, collect errors
- Log progress for monitoring
- Return partial results when possible

---

## Pattern 5: Conditional AI Enhancement

Add AI features without breaking non-AI usage.

```python
from typing import Any, ClassVar

from core.models.task import Task
from core.services.base_ai_service import BaseAIService
from core.ports import TasksOperations
from core.utils.result_simplified import Result


class TasksAIService(BaseAIService[TasksOperations, Task]):
    """Optional AI enhancements for tasks."""

    _service_name: ClassVar[str] = "tasks.ai"
    # Allow partial initialization
    _require_llm: ClassVar[bool] = False
    _require_embeddings: ClassVar[bool] = False

    async def enhance_task_view(
        self,
        task_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Get task with optional AI enhancements.

        Works with or without AI services.
        """
        # Base task (always works)
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return task_result

        task = task_result.value
        result: dict[str, Any] = {
            "task": task,
            "ai_enabled": bool(self.llm or self.embeddings),
        }

        # Optional: AI suggestions
        if self.llm:
            suggestions = await self._generate_insight(
                prompt="Suggest one way to complete this task efficiently.",
                context={"title": task.title},
                max_tokens=100,
            )
            if suggestions.is_ok:
                result["ai_suggestion"] = suggestions.value

        # Optional: Similar tasks
        if self.embeddings:
            all_tasks = await self.backend.find_by()
            if all_tasks.is_ok:
                candidates = [(t.uid, t.title) for t in all_tasks.value if t.uid != task_uid]
                if candidates:
                    similar = await self._semantic_search(task.title, candidates, top_k=2)
                    if similar.is_ok:
                        result["similar_task_uids"] = [uid for uid, _ in similar.value]

        return Result.ok(result)
```

**Key Points:**
- Set both `_require_*` to `False` for full flexibility
- Check service availability before each AI operation
- Include `ai_enabled` flag for UI awareness

---

## Pattern 6: Error Handling with Fallbacks

Graceful degradation when AI fails.

```python
from typing import Any, ClassVar

from core.models.task import Task
from core.services.base_ai_service import BaseAIService
from core.ports import TasksOperations
from core.utils.result_simplified import Result


class TasksAIService(BaseAIService[TasksOperations, Task]):
    """AI service with robust error handling."""

    _service_name: ClassVar[str] = "tasks.ai"

    async def get_task_recommendations(
        self,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Get task recommendations with fallback.

        Returns AI recommendations if available,
        falls back to simple heuristics if AI fails.
        """
        # Get user's tasks
        tasks_result = await self.backend.find_by(created_by=user_uid, status="active")
        if tasks_result.is_error:
            return tasks_result

        tasks = tasks_result.value
        if not tasks:
            return Result.ok({"recommendations": [], "source": "empty"})

        # Try AI recommendations
        if self.llm:
            try:
                task_summary = "\n".join(f"- {t.title}" for t in tasks[:10])
                ai_result = await self._generate_insight(
                    prompt="Prioritize these tasks and explain why.",
                    context={"tasks": task_summary},
                    max_tokens=300,
                )

                if ai_result.is_ok:
                    return Result.ok({
                        "recommendations": ai_result.value,
                        "source": "ai",
                    })
                else:
                    self.logger.warning(f"AI recommendation failed: {ai_result.error}")
            except Exception as e:
                self.logger.error(f"AI recommendation error: {e}")

        # Fallback: Simple heuristics
        # Sort by due date (soonest first) and priority
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (
                t.due_date or "9999-99-99",
                -(t.priority.value if t.priority else 0),
            ),
        )

        return Result.ok({
            "recommendations": [t.title for t in sorted_tasks[:5]],
            "source": "heuristic",
        })
```

**Key Points:**
- Try AI first, fall back to heuristics
- Log warnings/errors for monitoring
- Include `source` field to indicate method used

---

## Anti-Patterns

### Don't: Skip Backend Validation

```python
# BAD - Assumes backend result is always valid
async def bad_search(self, uid: str):
    task = (await self.backend.get(uid)).value  # May raise if error!
    # ...
```

```python
# GOOD - Check result before using
async def good_search(self, uid: str):
    result = await self.backend.get(uid)
    if result.is_error:
        return result
    task = result.value
    # ...
```

### Don't: Ignore AI Service Availability

```python
# BAD - Assumes embeddings always available
async def bad_similar(self, uid: str):
    embedding = await self.embeddings.embed_text(...)  # May be None!
```

```python
# GOOD - Check availability or set _require_embeddings = True
async def good_similar(self, uid: str):
    self._require_embeddings_service("find_similar")  # Guard
    # Or check: if not self.embeddings: return error
```

### Don't: Unbounded Token Usage

```python
# BAD - No token limit on long content
await self._generate_insight(
    prompt="Analyze everything",
    context={"full_content": very_long_content},  # May exceed limits
)
```

```python
# GOOD - Limit content and tokens
await self._generate_insight(
    prompt="Analyze this summary",
    context={"content": content[:1000]},  # Truncate input
    max_tokens=300,  # Limit output
)
```

---

## Testing Patterns

### Mock AI Services

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """Mock LLM service."""
    llm = MagicMock()
    llm.generate = AsyncMock(return_value="AI generated response")
    return llm


@pytest.fixture
def mock_embeddings():
    """Mock embeddings service."""
    embeddings = MagicMock()
    embeddings.embed_text = AsyncMock(return_value=[0.1] * 1536)
    return embeddings


@pytest.fixture
def ai_service(mock_backend, mock_llm, mock_embeddings):
    """AI service with mocked dependencies."""
    return TasksAIService(
        backend=mock_backend,
        llm_service=mock_llm,
        embeddings_service=mock_embeddings,
    )


async def test_generate_insight(ai_service, mock_llm):
    """Test LLM insight generation."""
    result = await ai_service.generate_task_insights("task_001")

    assert result.is_ok
    mock_llm.generate.assert_called_once()
    assert "AI generated response" in result.value
```

### Test Without AI

```python
async def test_works_without_ai(mock_backend):
    """Test service works when AI is disabled."""
    # Create with AI disabled
    service = TasksAIService(
        backend=mock_backend,
        llm_service=None,
        embeddings_service=None,
    )
    service._require_llm = False
    service._require_embeddings = False

    # Should still work for basic operations
    result = await service.enhance_task_view("task_001")
    assert result.is_ok
    assert result.value["ai_enabled"] is False
```
