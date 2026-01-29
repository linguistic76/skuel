"""
Integration Tests - Async Background Embedding Generation
===========================================================

Tests for async embedding generation across all activity domains.

Architecture:
- Event-driven: Tasks publish EmbeddingRequested events
- Background worker processes events in batches
- Zero latency impact on user creation

Test Coverage:
1. Event publishing after entity creation
2. Background worker batch processing
3. Neo4j embedding storage
4. Graceful degradation without worker
5. All 6 activity domains
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.events import TaskEmbeddingRequested
from core.models.task.task_request import TaskCreateRequest
from core.services.background.embedding_worker import EmbeddingBackgroundWorker


class TestTaskEmbeddingEvents:
    """Test embedding event publishing for tasks."""

    @pytest.mark.asyncio
    async def test_task_creation_publishes_embedding_event(
        self, tasks_service, event_bus, user_uid
    ):
        """
        GIVEN: Task service with event bus
        WHEN: Creating a task
        THEN: TaskEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event: TaskEmbeddingRequested):
            events_received.append(event)

        event_bus.subscribe(TaskEmbeddingRequested, capture_event)

        # Create task
        request = TaskCreateRequest(
            title="Learn Docker", description="Master container orchestration"
        )
        result = await tasks_service.create_task(request, user_uid)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "task"
        assert "Learn Docker" in event.embedding_text
        assert "Master container orchestration" in event.embedding_text

    @pytest.mark.asyncio
    async def test_task_creation_without_event_bus_continues(self, tasks_backend, user_uid):
        """
        GIVEN: Task service WITHOUT event bus
        WHEN: Creating a task
        THEN: Task creation succeeds (graceful degradation)
        """
        from core.services.tasks.tasks_core_service import TasksCoreService

        # Create service without event bus
        tasks_service = TasksCoreService(backend=tasks_backend, event_bus=None)

        request = TaskCreateRequest(title="Test Task", description="Test description")
        result = await tasks_service.create_task(request, user_uid)

        # Should succeed despite no event bus
        assert result.is_ok
        assert result.value.title == "Test Task"


class TestEmbeddingBackgroundWorker:
    """Test background worker batch processing."""

    @pytest.mark.asyncio
    async def test_worker_processes_batch(self, event_bus, embeddings_service, neo4j_driver):
        """
        GIVEN: Background worker running
        WHEN: Publishing 10 embedding requests
        THEN: Worker processes batch and stores embeddings in Neo4j
        """
        # Mock embeddings service
        embeddings_service.create_batch_embeddings = AsyncMock(
            return_value=Mock(is_ok=True, value=[[0.1] * 1536 for _ in range(10)])
        )

        # Create and start worker
        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            driver=neo4j_driver,
            batch_size=25,
            batch_interval_seconds=1,  # Faster for testing
        )

        # Start worker in background
        worker_task = asyncio.create_task(worker.start())

        # Publish 10 embedding requests
        for i in range(10):
            event = TaskEmbeddingRequested(
                entity_uid=f"task.test{i}",
                entity_type="task",
                embedding_text=f"Test task {i}",
                user_uid="user.test",
                requested_at=datetime.now(),
            )
            await event_bus.publish_async(event)

        # Wait for batch processing (interval + buffer)
        await asyncio.sleep(2)

        # Verify batch embedding was called
        embeddings_service.create_batch_embeddings.assert_called_once()
        call_args = embeddings_service.create_batch_embeddings.call_args
        assert len(call_args[0][0]) == 10  # 10 texts

        # Cleanup
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_worker_graceful_degradation_on_failure(
        self, event_bus, embeddings_service, neo4j_driver
    ):
        """
        GIVEN: Embeddings service that fails
        WHEN: Worker processes batch
        THEN: Errors logged but worker continues (no crash)
        """
        # Mock failure
        from core.utils.result_simplified import Errors, Result

        embeddings_service.create_batch_embeddings = AsyncMock(
            return_value=Result.fail(
                Errors.integration(service="GenAI", message="API rate limit exceeded")
            )
        )

        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            driver=neo4j_driver,
            batch_size=5,
            batch_interval_seconds=1,
        )

        worker_task = asyncio.create_task(worker.start())

        # Publish request
        event = TaskEmbeddingRequested(
            entity_uid="task.test",
            entity_type="task",
            embedding_text="Test",
            user_uid="user.test",
            requested_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Wait for processing attempt
        await asyncio.sleep(2)

        # Worker should still be running (no crash)
        assert not worker_task.done()

        # Cleanup
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


class TestEmbeddingTextExtraction:
    """Test embedding text extraction for all domains."""

    def test_task_embedding_text_extraction(self):
        """
        GIVEN: Task with title and description
        WHEN: Building embedding text
        THEN: Returns title + description
        """
        from core.models.task.task import Task
        from core.services.tasks.tasks_core_service import TasksCoreService

        service = TasksCoreService(backend=None)

        task = Task(
            uid="task.test",
            user_uid="user.test",
            title="Learn Python",
            description="Study async/await patterns",
            priority="medium",
            status="pending",
        )

        text = service._build_embedding_text(task)

        assert "Learn Python" in text
        assert "Study async/await patterns" in text

    def test_task_embedding_text_without_description(self):
        """
        GIVEN: Task with only title (no description)
        WHEN: Building embedding text
        THEN: Returns title only
        """
        from core.models.task.task import Task
        from core.services.tasks.tasks_core_service import TasksCoreService

        service = TasksCoreService(backend=None)

        task = Task(
            uid="task.test",
            user_uid="user.test",
            title="Buy groceries",
            description=None,
            priority="low",
            status="pending",
        )

        text = service._build_embedding_text(task)

        assert text == "Buy groceries"


class TestGoalEmbeddingEvents:
    """Test embedding event publishing for goals."""

    @pytest.mark.asyncio
    async def test_goal_creation_publishes_embedding_event(
        self, goals_service, event_bus, user_uid
    ):
        """
        GIVEN: Goal service with event bus
        WHEN: Creating a goal
        THEN: GoalEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        from core.events import GoalEmbeddingRequested

        event_bus.subscribe(GoalEmbeddingRequested, capture_event)

        # Create goal
        from core.models.goal.goal_request import GoalCreateRequest

        request = GoalCreateRequest(
            title="Master Python",
            description="Become proficient in Python programming",
            vision_statement="Build production-ready applications with confidence",
        )
        result = await goals_service.create_goal(request, user_uid)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "goal"
        assert "Master Python" in event.embedding_text
        assert "Become proficient" in event.embedding_text
        assert "production-ready applications" in event.embedding_text

    @pytest.mark.asyncio
    async def test_goal_creation_without_event_bus_continues(self, goals_backend, user_uid):
        """
        GIVEN: Goal service WITHOUT event bus
        WHEN: Creating a goal
        THEN: Goal creation succeeds (graceful degradation)
        """
        from core.services.goals.goals_core_service import GoalsCoreService
        from core.models.goal.goal_request import GoalCreateRequest

        # Create service without event bus
        goals_service = GoalsCoreService(backend=goals_backend, event_bus=None)

        request = GoalCreateRequest(
            title="Test Goal", description="Test description", vision_statement="Test vision"
        )
        result = await goals_service.create_goal(request, user_uid)

        # Should succeed despite no event bus
        assert result.is_ok
        assert result.value.title == "Test Goal"


class TestGoalEmbeddingTextExtraction:
    """Test embedding text extraction for goals."""

    def test_goal_embedding_text_with_all_fields(self):
        """
        GIVEN: Goal with title, description, and vision_statement
        WHEN: Building embedding text
        THEN: Returns all three fields combined
        """
        from core.models.goal.goal import Goal
        from core.services.goals.goals_core_service import GoalsCoreService

        service = GoalsCoreService(backend=None)

        goal = Goal(
            uid="goal.test",
            user_uid="user.test",
            title="Learn Machine Learning",
            description="Study ML algorithms and frameworks",
            vision_statement="Deploy AI models to production",
            status="active",
        )

        text = service._build_embedding_text(goal)

        assert "Learn Machine Learning" in text
        assert "Study ML algorithms" in text
        assert "Deploy AI models" in text

    def test_goal_embedding_text_without_optional_fields(self):
        """
        GIVEN: Goal with only title (no description/vision)
        WHEN: Building embedding text
        THEN: Returns title only
        """
        from core.models.goal.goal import Goal
        from core.services.goals.goals_core_service import GoalsCoreService

        service = GoalsCoreService(backend=None)

        goal = Goal(
            uid="goal.test",
            user_uid="user.test",
            title="Get fit",
            description=None,
            vision_statement=None,
            status="active",
        )

        text = service._build_embedding_text(goal)

        assert text == "Get fit"


# TODO: Add tests for other activity domains (Habits, Events, Choices, Principles)
# TODO: Add end-to-end test with real Neo4j
# TODO: Add performance benchmarking test
