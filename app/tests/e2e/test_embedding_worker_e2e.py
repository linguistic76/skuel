"""
End-to-End Tests - Embedding Background Worker
================================================

Tests complete workflow from entity creation to embedding storage in Neo4j.

Test Coverage:
1. Worker lifecycle (start/stop)
2. Event processing (queue → batch → embeddings)
3. Neo4j storage verification
4. Multiple domains simultaneously
5. Error recovery and retry logic
"""

import asyncio
from datetime import datetime

import pytest

from core.events import GoalEmbeddingRequested, TaskEmbeddingRequested


class TestEmbeddingWorkerLifecycle:
    """Test worker startup and shutdown."""

    @pytest.mark.asyncio
    async def test_worker_starts_and_stops_cleanly(self, embedding_worker):
        """
        GIVEN: Embedding worker instance
        WHEN: Starting and stopping worker
        THEN: Worker starts without errors and stops gracefully
        """
        # Start worker in background
        worker_task = asyncio.create_task(embedding_worker.start())

        # Wait briefly for worker to initialize
        await asyncio.sleep(0.5)

        # Verify task is running
        assert not worker_task.done()

        # Stop worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass  # Expected

        # Verify task stopped
        assert worker_task.done()
        assert worker_task.cancelled()


class TestEmbeddingWorkerEventProcessing:
    """Test event queue and batch processing."""

    @pytest.mark.asyncio
    async def test_worker_processes_task_embedding_request(
        self, embedding_worker, event_bus, neo4j_driver
    ):
        """
        GIVEN: Worker listening for events
        WHEN: TaskEmbeddingRequested event published
        THEN: Embedding generated and stored in Neo4j within 60 seconds
        """
        # Create test task in Neo4j first
        task_uid = "task.test_embedding_e2e"
        user_uid = "user.test_e2e"

        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (t:Task {
                    uid: $uid,
                    user_uid: $user_uid,
                    title: $title,
                    description: $description,
                    status: 'pending',
                    created_at: datetime()
                })
                """,
                uid=task_uid,
                user_uid=user_uid,
                title="Test async embedding generation",
                description="End-to-end test for background worker",
            )

        # Start worker in background
        worker_task = asyncio.create_task(embedding_worker.start())

        try:
            # Wait for worker to initialize
            await asyncio.sleep(0.5)

            # Publish embedding request event
            event = TaskEmbeddingRequested(
                entity_uid=task_uid,
                entity_type="task",
                embedding_text="Test async embedding generation\nEnd-to-end test for background worker",
                user_uid=user_uid,
                requested_at=datetime.now(),
            )
            await event_bus.publish(event)

            # Wait for worker to process (batch interval + processing time)
            # Worker runs every 30 seconds, give it up to 35 seconds
            await asyncio.sleep(35)

            # Verify embedding was stored in Neo4j
            async with neo4j_driver.session() as session:
                result = await session.run(
                    """
                    MATCH (t:Task {uid: $uid})
                    RETURN t.embedding IS NOT NULL as has_embedding,
                           size(t.embedding) as embedding_size
                    """,
                    uid=task_uid,
                )
                record = await result.single()

                assert record is not None, "Task not found in Neo4j"
                assert record["has_embedding"], "Embedding was not generated"
                assert record["embedding_size"] > 0, "Embedding is empty"

        finally:
            # Cleanup: Stop worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            # Cleanup: Delete test task
            async with neo4j_driver.session() as session:
                await session.run("MATCH (t:Task {uid: $uid}) DETACH DELETE t", uid=task_uid)

    @pytest.mark.asyncio
    async def test_worker_processes_multiple_domains(
        self, embedding_worker, event_bus, neo4j_driver
    ):
        """
        GIVEN: Worker listening for events
        WHEN: Multiple domain events published (Task + Goal)
        THEN: All embeddings generated and stored correctly
        """
        # Create test entities in Neo4j
        task_uid = "task.multi_domain_test"
        goal_uid = "goal.multi_domain_test"
        user_uid = "user.test_multi"

        async with neo4j_driver.session() as session:
            # Create task
            await session.run(
                """
                CREATE (t:Task {
                    uid: $uid,
                    user_uid: $user_uid,
                    title: $title,
                    description: $description,
                    status: 'pending',
                    created_at: datetime()
                })
                """,
                uid=task_uid,
                user_uid=user_uid,
                title="Multi-domain task",
                description="Test batch processing",
            )

            # Create goal
            await session.run(
                """
                CREATE (g:Goal {
                    uid: $uid,
                    user_uid: $user_uid,
                    title: $title,
                    description: $description,
                    vision_statement: $vision,
                    status: 'active',
                    created_at: datetime()
                })
                """,
                uid=goal_uid,
                user_uid=user_uid,
                title="Multi-domain goal",
                description="Test concurrent processing",
                vision="Verify batch efficiency",
            )

        # Start worker
        worker_task = asyncio.create_task(embedding_worker.start())

        try:
            await asyncio.sleep(0.5)

            # Publish both events
            task_event = TaskEmbeddingRequested(
                entity_uid=task_uid,
                entity_type="task",
                embedding_text="Multi-domain task\nTest batch processing",
                user_uid=user_uid,
                requested_at=datetime.now(),
            )

            goal_event = GoalEmbeddingRequested(
                entity_uid=goal_uid,
                entity_type="goal",
                embedding_text="Multi-domain goal\nTest concurrent processing\nVerify batch efficiency",
                user_uid=user_uid,
                requested_at=datetime.now(),
            )

            await event_bus.publish(task_event)
            await event_bus.publish(goal_event)

            # Wait for processing
            await asyncio.sleep(35)

            # Verify both embeddings
            async with neo4j_driver.session() as session:
                # Check task
                task_result = await session.run(
                    "MATCH (t:Task {uid: $uid}) RETURN t.embedding IS NOT NULL as has_embedding",
                    uid=task_uid,
                )
                task_record = await task_result.single()
                assert task_record["has_embedding"], "Task embedding not generated"

                # Check goal
                goal_result = await session.run(
                    "MATCH (g:Goal {uid: $uid}) RETURN g.embedding IS NOT NULL as has_embedding",
                    uid=goal_uid,
                )
                goal_record = await goal_result.single()
                assert goal_record["has_embedding"], "Goal embedding not generated"

        finally:
            # Cleanup
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            async with neo4j_driver.session() as session:
                await session.run("MATCH (t:Task {uid: $uid}) DETACH DELETE t", uid=task_uid)
                await session.run("MATCH (g:Goal {uid: $uid}) DETACH DELETE g", uid=goal_uid)


class TestEmbeddingWorkerBatchProcessing:
    """Test batch size and performance."""

    @pytest.mark.asyncio
    async def test_worker_processes_batch_efficiently(
        self, embedding_worker, event_bus, neo4j_driver
    ):
        """
        GIVEN: Worker with batch_size=25
        WHEN: 10 embedding requests published
        THEN: All processed in single batch cycle
        """
        user_uid = "user.test_batch"
        task_uids = [f"task.batch_test_{i}" for i in range(10)]

        # Create 10 tasks in Neo4j
        async with neo4j_driver.session() as session:
            for uid in task_uids:
                await session.run(
                    """
                    CREATE (t:Task {
                        uid: $uid,
                        user_uid: $user_uid,
                        title: $title,
                        status: 'pending',
                        created_at: datetime()
                    })
                    """,
                    uid=uid,
                    user_uid=user_uid,
                    title=f"Batch test {uid}",
                )

        # Start worker
        worker_task = asyncio.create_task(embedding_worker.start())

        try:
            await asyncio.sleep(0.5)

            # Publish 10 events
            for uid in task_uids:
                event = TaskEmbeddingRequested(
                    entity_uid=uid,
                    entity_type="task",
                    embedding_text=f"Batch test {uid}",
                    user_uid=user_uid,
                    requested_at=datetime.now(),
                )
                await event_bus.publish(event)

            # Wait for one batch cycle
            await asyncio.sleep(35)

            # Verify all embeddings generated
            async with neo4j_driver.session() as session:
                result = await session.run(
                    """
                    MATCH (t:Task)
                    WHERE t.uid IN $uids
                    RETURN count(t) as total_tasks,
                           sum(CASE WHEN t.embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embeddings
                    """,
                    uids=task_uids,
                )
                record = await result.single()

                assert record["total_tasks"] == 10, "Not all tasks found"
                assert (
                    record["with_embeddings"] == 10
                ), f"Only {record['with_embeddings']}/10 embeddings generated"

        finally:
            # Cleanup
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            async with neo4j_driver.session() as session:
                await session.run(
                    "MATCH (t:Task) WHERE t.uid IN $uids DETACH DELETE t", uids=task_uids
                )


class TestEmbeddingWorkerErrorRecovery:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_worker_continues_after_single_failure(
        self, embedding_worker, event_bus, neo4j_driver
    ):
        """
        GIVEN: Worker processing batch with one invalid entity
        WHEN: Batch contains valid and invalid requests
        THEN: Valid requests processed, invalid logged and skipped
        """
        user_uid = "user.test_error"
        valid_uid = "task.valid_entity"
        invalid_uid = "task.nonexistent_entity"  # Doesn't exist in Neo4j

        # Create only valid task in Neo4j
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (t:Task {
                    uid: $uid,
                    user_uid: $user_uid,
                    title: $title,
                    status: 'pending',
                    created_at: datetime()
                })
                """,
                uid=valid_uid,
                user_uid=user_uid,
                title="Valid task",
            )

        worker_task = asyncio.create_task(embedding_worker.start())

        try:
            await asyncio.sleep(0.5)

            # Publish events for both (one will fail)
            valid_event = TaskEmbeddingRequested(
                entity_uid=valid_uid,
                entity_type="task",
                embedding_text="Valid task",
                user_uid=user_uid,
                requested_at=datetime.now(),
            )

            invalid_event = TaskEmbeddingRequested(
                entity_uid=invalid_uid,
                entity_type="task",
                embedding_text="Invalid task",
                user_uid=user_uid,
                requested_at=datetime.now(),
            )

            await event_bus.publish(valid_event)
            await event_bus.publish(invalid_event)

            # Wait for processing
            await asyncio.sleep(35)

            # Verify valid task got embedding (worker didn't crash)
            async with neo4j_driver.session() as session:
                result = await session.run(
                    "MATCH (t:Task {uid: $uid}) RETURN t.embedding IS NOT NULL as has_embedding",
                    uid=valid_uid,
                )
                record = await result.single()
                assert record is not None, "Valid task not found"
                assert record["has_embedding"], "Valid task embedding not generated"

        finally:
            # Cleanup
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            async with neo4j_driver.session() as session:
                await session.run("MATCH (t:Task {uid: $uid}) DETACH DELETE t", uid=valid_uid)
