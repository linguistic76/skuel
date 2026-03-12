"""
Tasks AI Service
================

AI-powered features for Tasks domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service explicitly DOES use:
- embeddings_service (semantic task similarity)
- llm_service (AI-generated recommendations)

The app works WITHOUT this service. It's an enhancement layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.task.task import Task
from core.services.base_ai_service import BaseAIService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.services.llm_service import LLMService
    from core.services.embeddings_service import HuggingFaceEmbeddingsService


class TasksAIService(BaseAIService["TasksOperations", Task]):
    """
    AI-powered features for Tasks domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    Planned AI features:
    - Semantic task similarity (find similar tasks by meaning)
    - AI-generated task recommendations (context-aware suggestions)
    - Natural language task insights (AI-written explanations)
    - Smart task breakdown (AI suggests subtasks)
    - Intelligent prioritization (AI-assisted priority suggestions)

    NOTE: These features require LLM/embeddings services.
    If not available, this service won't be instantiated.
    """

    # Service name for hierarchical logging
    _service_name = "tasks.ai"

    # AI requirements - both required for this service

    def __init__(
        self,
        backend: TasksOperations,
        llm_service: LLMService,
        embeddings_service: HuggingFaceEmbeddingsService,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize tasks AI service.

        Args:
            backend: Tasks backend operations (protocol)
            llm_service: LLM service for AI insights (REQUIRED)
            embeddings_service: Embeddings service for semantic search (REQUIRED)
            event_bus: Event bus for publishing events (optional)

        NOTE: Both llm_service and embeddings_service are REQUIRED.
        This service should only be instantiated when AI is available.
        """
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )

    # ========================================================================
    # SEMANTIC SIMILARITY (Future AI Feature)
    # ========================================================================

    async def find_similar_tasks(
        self, task_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """
        Find semantically similar tasks using embeddings.

        Uses embeddings to find tasks with similar meaning/context,
        not just keyword matching.

        Args:
            task_uid: Task to find similar tasks for
            limit: Maximum number of similar tasks to return

        Returns:
            Result containing list of (task_uid, similarity_score) tuples
        """
        # Get the source task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        search_text = build_embedding_text(EntityType.TASK, task)

        # TODO(blocked:embeddings): Use vector similarity or limit query instead of fetching all tasks
        all_tasks_result = await self.backend.find_by(user_uid=task.user_uid)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result.expect_error())

        all_tasks = all_tasks_result.value or []
        candidates = [
            (t.uid, build_embedding_text(EntityType.TASK, t))
            for t in all_tasks
            if t.uid != task_uid
        ]

        if not candidates:
            return Result.ok([])

        # Use base class semantic search
        return await self._semantic_search(search_text, candidates, limit)

    # ========================================================================
    # AI RECOMMENDATIONS (Future AI Feature)
    # ========================================================================

    async def generate_task_breakdown(
        self, task_uid: str, max_subtasks: int = 5
    ) -> Result[list[str]]:
        """
        Generate AI-suggested subtask breakdown for a complex task.

        Uses LLM to analyze the task and suggest subtasks.

        Args:
            task_uid: Task to break down
            max_subtasks: Maximum number of subtasks to suggest

        Returns:
            Result containing list of suggested subtask titles
        """
        # Get the task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        # Build prompt for LLM
        prompt = f"""Break down this task into {max_subtasks} or fewer actionable subtasks.

Task: {task.title}
Description: {task.description or "No description provided"}

Return only the subtask titles, one per line. Be specific and actionable."""

        # Use base class LLM generation
        insight_result = await self._generate_insight(prompt, max_tokens=300)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        # Parse response into subtask list
        response = insight_result.value
        subtasks = [
            line.strip().lstrip("- ").lstrip("•").strip()
            for line in response.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        return Result.ok(subtasks[:max_subtasks])

    async def generate_task_insight(self, task_uid: str) -> Result[str]:
        """
        Generate AI-written insight about a task.

        Uses LLM to provide contextual insight about the task,
        its importance, and suggestions for completion.

        Args:
            task_uid: Task to analyze

        Returns:
            Result containing AI-generated insight text
        """
        # Get the task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        # Build context
        context = {
            "title": task.title,
            "description": task.description or "No description",
            "priority": task.priority if task.priority else "Not set",
            "status": task.status.value if task.status else "Unknown",
            "due_date": str(task.due_date) if task.due_date else "No deadline",
        }

        prompt = """Provide a brief, actionable insight about this task.
Focus on:
1. Why this task might be important
2. One specific tip for completing it effectively
Keep it under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)

    # ========================================================================
    # INTELLIGENT PRIORITIZATION (Future AI Feature)
    # ========================================================================

    async def suggest_priority(self, task_uid: str) -> Result[dict[str, Any]]:
        """
        Get AI-suggested priority for a task.

        Uses LLM to analyze task context and suggest appropriate priority.

        Args:
            task_uid: Task to analyze

        Returns:
            Result containing priority suggestion with reasoning
        """
        # Get the task
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        # Build context
        context = {
            "title": task.title,
            "description": task.description or "No description",
            "current_priority": task.priority if task.priority else "Not set",
            "due_date": str(task.due_date) if task.due_date else "No deadline",
        }

        prompt = """Analyze this task and suggest a priority level.
Priority levels: CRITICAL, HIGH, MEDIUM, LOW, NONE

Respond in this format:
PRIORITY: [your suggestion]
REASONING: [brief explanation, 1-2 sentences]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=150)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        # Parse response
        response = insight_result.value
        lines = response.strip().split("\n")

        suggested_priority = "MEDIUM"  # Default
        reasoning = "Unable to determine reasoning"

        for line in lines:
            if line.upper().startswith("PRIORITY:"):
                suggested_priority = line.split(":", 1)[1].strip().upper()
            elif line.upper().startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()

        return Result.ok(
            {
                "task_uid": task_uid,
                "current_priority": task.priority if task.priority else None,
                "suggested_priority": suggested_priority,
                "reasoning": reasoning,
            }
        )
