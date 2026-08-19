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
import contextlib
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.events import TaskEmbeddingRequested
from core.models.enums.entity_enums import EntityType
from core.models.task.task_request import TaskCreateRequest as TaskCreateRequest
from core.services.background.embedding_worker import EmbeddingBackgroundWorker
from core.utils.embedding_text_builder import build_embedding_text


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
        # Mock embeddings service (worker generates per item via create_embedding)
        embeddings_service.create_embedding = AsyncMock(
            return_value=Mock(is_ok=True, is_error=False, value=[0.1] * 1024)
        )

        # Create and start worker
        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            batch_size=25,
            batch_interval_seconds=1,  # Faster for testing
        )

        # Start worker in background
        worker_task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)  # Let worker register event handlers

        # Publish 10 embedding requests
        for i in range(10):
            event = TaskEmbeddingRequested(
                entity_uid=f"task.test{i}",
                entity_type="task",
                embedding_text=f"Test task {i}",
                requested_at=datetime.now(),
                occurred_at=datetime.now(),
            )
            await event_bus.publish_async(event)

        # Wait for batch processing (interval + buffer)
        await asyncio.sleep(2)

        # Verify per-item embedding was called for every request in the batch
        assert embeddings_service.create_embedding.await_count == 10
        called_texts = {c.args[0] for c in embeddings_service.create_embedding.await_args_list}
        assert called_texts == {f"Test task {i}" for i in range(10)}

        # Cleanup
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task

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

        embeddings_service.create_embedding = AsyncMock(
            return_value=Result.fail(
                Errors.integration(service="GenAI", message="API rate limit exceeded")
            )
        )

        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            batch_size=5,
            batch_interval_seconds=1,
        )

        worker_task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)  # Let worker register event handlers

        # Publish request
        event = TaskEmbeddingRequested(
            entity_uid="task.test",
            entity_type="task",
            embedding_text="Test",
            requested_at=datetime.now(),
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Wait for processing attempt
        await asyncio.sleep(2)

        # Worker should still be running (no crash)
        assert not worker_task.done()

        # Cleanup
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task


class TestEmbeddingTextExtraction:
    """Test embedding text extraction for all domains."""

    def test_task_embedding_text_extraction(self):
        """
        GIVEN: Task with title and description
        WHEN: Building embedding text
        THEN: Returns title + description
        """
        from core.models.task.task import Task as Task

        task = Task(
            uid="task.test",
            user_uid="user_test",
            title="Learn Python",
            description="Study async/await patterns",
            priority="medium",
            status="pending",
        )

        text = build_embedding_text(EntityType.TASK, task)

        assert "Learn Python" in text
        assert "Study async/await patterns" in text

    def test_task_embedding_text_without_description(self):
        """
        GIVEN: Task with only title (no description)
        WHEN: Building embedding text
        THEN: Returns title only
        """
        from core.models.task.task import Task as Task

        task = Task(
            uid="task.test",
            user_uid="user_test",
            title="Buy groceries",
            description=None,
            priority="low",
            status="pending",
        )

        text = build_embedding_text(EntityType.TASK, task)

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

    @pytest.mark.asyncio
    async def test_goal_creation_without_event_bus_continues(self, goals_backend, user_uid):
        """
        GIVEN: Goal service WITHOUT event bus
        WHEN: Creating a goal
        THEN: Goal creation succeeds (graceful degradation)
        """
        # Create service without event bus

        from core.models.goal.goal_request import GoalCreateRequest
        from core.services.goals.goals_core_service import GoalsCoreService

        goals_service = GoalsCoreService(
            backend=goals_backend,
            event_bus=None,
        )

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

        goal = Goal(
            uid="goal.test",
            user_uid="user_test",
            title="Learn Machine Learning",
            description="Study ML algorithms and frameworks",
            vision_statement="Deploy AI models to production",
            status="active",
        )

        text = build_embedding_text(EntityType.GOAL, goal)

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

        goal = Goal(
            uid="goal.test",
            user_uid="user_test",
            title="Get fit",
            description=None,
            vision_statement=None,
            status="active",
        )

        text = build_embedding_text(EntityType.GOAL, goal)

        assert text == "Get fit"


class TestHabitEmbeddingEvents:
    """Test embedding event publishing for habits."""

    @pytest.mark.asyncio
    async def test_habit_creation_publishes_embedding_event(
        self, habits_service, event_bus, user_uid
    ):
        """
        GIVEN: Habit service with event bus
        WHEN: Creating a habit
        THEN: HabitEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        from core.events import HabitEmbeddingRequested

        event_bus.subscribe(HabitEmbeddingRequested, capture_event)

        # Create habit
        from core.models.habit.habit_request import HabitCreateRequest

        request = HabitCreateRequest(
            title="Morning Meditation",
            description="Practice mindfulness for 10 minutes",
            cue="After waking up",
            reward="Feel calm and centered",
        )
        result = await habits_service.create_habit(request, user_uid)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "habit"
        assert "Morning Meditation" in event.embedding_text
        assert "Practice mindfulness" in event.embedding_text


class TestEventEmbeddingEvents:
    """Test embedding event publishing for events."""

    @pytest.mark.asyncio
    async def test_event_creation_publishes_embedding_event(
        self, events_service, event_bus, user_uid
    ):
        """
        GIVEN: Event service with event bus
        WHEN: Creating an event
        THEN: EventEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        from core.events import EventEmbeddingRequested

        event_bus.subscribe(EventEmbeddingRequested, capture_event)

        # Create event
        from core.models.event.event import Event

        event_entity = Event(
            uid="event.test",
            user_uid=user_uid,
            title="Team Meeting",
            description="Quarterly planning session",
            location="Conference Room A",
            event_date=datetime.now().date(),
        )
        result = await events_service.create(event_entity)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "event"
        assert "Team Meeting" in event.embedding_text


class TestChoiceEmbeddingEvents:
    """Test embedding event publishing for choices."""

    @pytest.mark.asyncio
    async def test_choice_creation_publishes_embedding_event(
        self, choices_service, event_bus, user_uid
    ):
        """
        GIVEN: Choice service with event bus
        WHEN: Creating a choice
        THEN: ChoiceEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        from core.events import ChoiceEmbeddingRequested

        event_bus.subscribe(ChoiceEmbeddingRequested, capture_event)

        # Create choice
        from core.models.choice.choice_request import ChoiceCreateRequest

        request = ChoiceCreateRequest(
            title="Career Path Decision",
            description="Choose between staying at current company or joining startup",
            decision_context="Looking for growth opportunities",
        )
        result = await choices_service.create_choice(request, user_uid)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "choice"
        assert "Career Path Decision" in event.embedding_text
        assert "current company or joining startup" in event.embedding_text
        # ``decision_context`` is a real Choice column now, and the CHOICE embedding
        # field map names it — so the circumstance is part of what gets embedded.
        assert "Looking for growth opportunities" in event.embedding_text


class TestPrincipleEmbeddingEvents:
    """Test embedding event publishing for principles."""

    @pytest.mark.asyncio
    async def test_principle_creation_publishes_embedding_event(
        self, principles_service, event_bus, user_uid
    ):
        """
        GIVEN: Principle service with event bus
        WHEN: Creating a principle
        THEN: PrincipleEmbeddingRequested event is published
        """
        # Capture events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        from core.events import PrincipleEmbeddingRequested

        event_bus.subscribe(PrincipleEmbeddingRequested, capture_event)

        # Create principle
        from core.models.enums.principle_enums import PrincipleCategory
        from core.models.principle.principle_request import PrincipleCreateRequest

        request = PrincipleCreateRequest(
            title="Continuous Learning",
            statement="Always seek to expand knowledge and skills",
            principle_category=PrincipleCategory.PERSONAL,
            why_important="Growth mindset enables adaptation and success",
        )
        result = await principles_service.create_principle(request, user_uid)

        # Wait for event propagation
        await asyncio.sleep(0.1)

        # Verify
        assert result.is_ok
        assert len(events_received) == 1

        event = events_received[0]
        assert event.entity_uid == result.value.uid
        assert event.entity_type == "principle"
        assert "Continuous Learning" in event.embedding_text
        assert "expand knowledge and skills" in event.embedding_text


class TestEndToEndEmbeddingIntegration:
    """End-to-end tests verifying the full flow from creation to Neo4j storage."""

    @pytest.mark.asyncio
    async def test_end_to_end_neo4j_embedding_storage(
        self, tasks_service, event_bus, embeddings_service, neo4j_driver, user_uid
    ):
        """
        GIVEN: Real Neo4j database and mocked HuggingFace service
        WHEN: Creating an entity and running background worker
        THEN: Embedding vector is physically stored against the node in Neo4j
        """
        from core.models.task.task_request import TaskCreateRequest
        from core.services.background.embedding_worker import EmbeddingBackgroundWorker

        # 1. Mock external embedding API (we want to test DB storage, not external HTTP calls)
        mock_embedding = [0.123] * 1024
        embeddings_service.create_embedding = AsyncMock(
            return_value=Mock(is_ok=True, is_error=False, value=mock_embedding)
        )
        # 2. Give the embeddings_service a real backend if it doesn't have one
        from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        executor = Neo4jQueryExecutor(neo4j_driver)
        embeddings_service.backend = EmbeddingsBackend(executor)

        # 3. Create background worker
        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            batch_size=5,
            batch_interval_seconds=1,
        )

        worker_task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)  # Let worker register

        # 4. Create an entity (triggers event internally)
        request = TaskCreateRequest(
            title="End to End Test Task", description="Verify Neo4j embedding storage"
        )
        result = await tasks_service.create_task(request, user_uid)
        assert result.is_ok
        task_uid = result.value.uid

        # Wait for worker to process batch and store in Neo4j
        await asyncio.sleep(2.0)

        # 5. Verify Neo4j Graph directly
        query_result = await executor.execute(
            query="MATCH (n:Task {uid: $uid}) RETURN n.embedding_version AS version, n.embedding AS embedding",
            params={"uid": task_uid},
            processor=lambda records: records[0] if records else None,
            operation="verify_embedding",
        )
        assert query_result.is_ok
        record = query_result.value

        from core.services.embeddings_service import EMBEDDING_VERSION

        assert record is not None, "Task node NOT FOUND in Neo4j"
        # Worker stores via the service, which owns the canonical version.
        assert record["version"] == EMBEDDING_VERSION, "Embedding version not set correctly"
        assert record["embedding"] is not None, "Embedding vector missing in Neo4j"
        assert len(record["embedding"]) == 1024, "Embedding vector length mismatch"
        assert record["embedding"][0] == 0.123, "Embedding vector value mismatch"

        # Cleanup
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
