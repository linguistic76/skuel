"""
Integration Test: Knowledge Mastery→Learning Path Event-Driven Progress Updates
================================================================================

Tests Phase 4 event-driven architecture for cross-domain dependencies.

This test suite verifies that:
1. KnowledgeMastered events trigger LP progress updates
2. LpProgressService.handle_knowledge_mastered() receives events
3. LP progress is calculated correctly based on mastered KUs
4. LearningPathProgressUpdated events are published when progress changes
5. LearningPathCompleted events are published when all KUs mastered
6. Multiple LPs can be updated from a single KU mastery
7. Unrelated KU mastery doesn't affect LP progress

Event Flow:
-----------
KU mastered → KnowledgeMastered event → LpProgressService.handle_knowledge_mastered()
    → Query Neo4j for LPs containing KU → Calculate new progress → Update LP
    → Publish LearningPathProgressUpdated event → (If 100%) Publish LearningPathCompleted event
"""

from datetime import datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.learning_events import (
    KnowledgeMastered,
    LearningPathCompleted,
    LearningPathProgressUpdated,
)
from core.models.enums import Domain, SELCategory
from core.models.enums.ku_enums import LpType
from core.models.ku.curriculum import Curriculum
from core.models.ku.learning_path import LearningPath
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.lp.lp_progress_service import LpProgressService


@pytest.mark.asyncio
class TestKuLpEventFlow:
    """Integration tests for KU→LP event-driven progress updates."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Ku", Curriculum)

    @pytest_asyncio.fixture
    async def lp_backend(self, neo4j_driver, clean_neo4j):
        """Create LP backend with clean database (unified Ku model)."""
        return UniversalNeo4jBackend[LearningPath](
            neo4j_driver, "Ku", LearningPath, default_filters={"ku_type": "learning_path"}
        )

    @pytest_asyncio.fixture
    async def lp_progress_service(self, event_bus, neo4j_driver):
        """Create LpProgressService with event bus and executor."""
        return LpProgressService(
            executor=Neo4jQueryExecutor(neo4j_driver),  # Phase 4: For KU→LP Cypher queries
            event_bus=event_bus,
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_ku_lp_flow"

    @pytest_asyncio.fixture
    async def test_user(self, neo4j_driver, test_user_uid):
        """Create test user node in Neo4j."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET u.created_at = datetime()
                RETURN u
                """,
                user_uid=test_user_uid,
            )
        return test_user_uid

    @pytest_asyncio.fixture
    async def python_basics_path(
        self, lp_backend, neo4j_driver, ku_backend, test_user_uid, test_user
    ):
        """Create a learning path for Python basics with 3 KUs."""
        # Create 3 KUs
        kus = []
        for i, title in enumerate(
            ["Python Variables", "Python Functions", "Python Classes"], start=1
        ):
            ku = Curriculum(
                uid=f"ku.python_basics_{i}",
                title=title,
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            result = await ku_backend.create(ku)
            assert result.is_ok
            kus.append(result.value)

        # Create learning path
        lp = LearningPath(
            uid="lp.python_basics",
            title="Python Basics",
            description="Master Python fundamentals",
            domain=Domain.TECH,
            path_type=LpType.STRUCTURED,
        )
        result = await lp_backend.create(lp)
        assert result.is_ok
        created_lp = result.value

        # Create graph relationships: (LP)-[:INCLUDES_KU]->(KU)
        async with neo4j_driver.session() as session:
            for ku in kus:
                await session.run(
                    """
                    MATCH (lp:Ku {uid: $lp_uid})
                    MATCH (ku:Ku {uid: $ku_uid})
                    MERGE (lp)-[:INCLUDES_KU]->(ku)
                    RETURN lp.uid, ku.uid
                    """,
                    lp_uid=lp.uid,
                    ku_uid=ku.uid,
                )

        return created_lp, kus

    # ========================================================================
    # BASIC EVENT FLOW TESTS
    # ========================================================================

    async def test_ku_mastered_event_triggers_lp_progress_update(
        self,
        event_bus,
        lp_progress_service,
        neo4j_driver,
        python_basics_path,
        test_user_uid,
    ):
        """Test that mastering a KU triggers LP progress update via events."""
        lp, kus = python_basics_path

        # Subscribe to KnowledgeMastered event
        event_bus.subscribe(KnowledgeMastered, lp_progress_service.handle_knowledge_mastered)

        # Create MASTERED relationship for first KU
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (user:User {uid: $user_uid})
                MATCH (ku:Ku {uid: $ku_uid})
                MERGE (user)-[:MASTERED]->(ku)
                """,
                user_uid=test_user_uid,
                ku_uid=kus[0].uid,
            )

        # Publish KnowledgeMastered event
        event = KnowledgeMastered(
            ku_uid=kus[0].uid,
            user_uid=test_user_uid,
            mastery_score=0.85,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Give event processing time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Verify LearningPathProgressUpdated event was published
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, LearningPathProgressUpdated)]
        assert len(progress_events) == 1
        assert progress_events[0].path_uid == lp.uid
        assert progress_events[0].kus_completed == 1
        assert progress_events[0].kus_total == 3

    async def test_lp_progress_calculated_correctly(
        self,
        event_bus,
        lp_progress_service,
        neo4j_driver,
        python_basics_path,
        test_user_uid,
    ):
        """Test that LP progress is calculated correctly (mastered_kus / total_kus)."""
        lp, kus = python_basics_path

        event_bus.subscribe(KnowledgeMastered, lp_progress_service.handle_knowledge_mastered)

        # Master 2 out of 3 KUs
        async with neo4j_driver.session() as session:
            for ku in kus[:2]:  # First 2 KUs
                await session.run(
                    """
                    MATCH (user:User {uid: $user_uid})
                    MATCH (ku:Ku {uid: $ku_uid})
                    MERGE (user)-[:MASTERED]->(ku)
                    """,
                    user_uid=test_user_uid,
                    ku_uid=ku.uid,
                )

        # Publish event for second KU (first one already mastered)
        event = KnowledgeMastered(
            ku_uid=kus[1].uid,
            user_uid=test_user_uid,
            mastery_score=0.90,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify progress is 66.67% (2/3)
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, LearningPathProgressUpdated)]
        assert len(progress_events) == 1
        assert progress_events[0].kus_completed == 2
        assert progress_events[0].kus_total == 3
        assert progress_events[0].new_progress == pytest.approx(0.6667, abs=0.01)

    async def test_lp_completed_event_published_at_100_percent(
        self,
        event_bus,
        lp_progress_service,
        neo4j_driver,
        python_basics_path,
        test_user_uid,
    ):
        """Test that LearningPathCompleted event is published when all KUs mastered."""
        lp, kus = python_basics_path

        event_bus.subscribe(KnowledgeMastered, lp_progress_service.handle_knowledge_mastered)

        # Master all 3 KUs
        async with neo4j_driver.session() as session:
            for ku in kus:
                await session.run(
                    """
                    MATCH (user:User {uid: $user_uid})
                    MATCH (ku:Ku {uid: $ku_uid})
                    MERGE (user)-[:MASTERED]->(ku)
                    """,
                    user_uid=test_user_uid,
                    ku_uid=ku.uid,
                )

        # Publish event for last KU
        event = KnowledgeMastered(
            ku_uid=kus[2].uid,
            user_uid=test_user_uid,
            mastery_score=0.95,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify LearningPathCompleted event was published
        history = event_bus.get_event_history()
        completed_events = [e for e in history if isinstance(e, LearningPathCompleted)]
        assert len(completed_events) == 1
        assert completed_events[0].path_uid == lp.uid
        assert completed_events[0].kus_mastered == 3

    async def test_no_update_when_ku_not_in_lp(
        self,
        event_bus,
        lp_progress_service,
        ku_backend,
        python_basics_path,
        test_user_uid,
    ):
        """Test that mastering an unrelated KU doesn't affect LP progress."""
        lp, kus = python_basics_path

        event_bus.subscribe(KnowledgeMastered, lp_progress_service.handle_knowledge_mastered)

        # Create unrelated KU
        unrelated_ku = Curriculum(
            uid="ku.advanced_algorithms",
            title="Advanced Algorithms",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        result = await ku_backend.create(unrelated_ku)
        assert result.is_ok, "Setup failed: Could not create KU"

        # Publish event for unrelated KU
        event = KnowledgeMastered(
            ku_uid=unrelated_ku.uid,
            user_uid=test_user_uid,
            mastery_score=0.88,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify no LearningPathProgressUpdated events
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, LearningPathProgressUpdated)]
        assert len(progress_events) == 0

    async def test_multiple_lps_updated_from_single_ku(
        self,
        event_bus,
        lp_progress_service,
        lp_backend,
        neo4j_driver,
        python_basics_path,
        test_user_uid,
    ):
        """Test that mastering a KU updates multiple LPs containing it."""
        lp1, kus = python_basics_path

        # Create second LP that also includes the first KU
        lp2 = LearningPath(
            uid="lp.python_advanced",
            title="Python Advanced",
            description="Master advanced Python",
            domain=Domain.TECH,
            path_type=LpType.STRUCTURED,
        )
        result = await lp_backend.create(lp2)
        assert result.is_ok, "Setup failed: Could not create LP"

        # Link first KU to second LP
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (lp:Ku {uid: $lp_uid})
                MATCH (ku:Ku {uid: $ku_uid})
                MERGE (lp)-[:INCLUDES_KU]->(ku)
                """,
                lp_uid=lp2.uid,
                ku_uid=kus[0].uid,
            )

        event_bus.subscribe(KnowledgeMastered, lp_progress_service.handle_knowledge_mastered)

        # Create MASTERED relationship
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (user:User {uid: $user_uid})
                MATCH (ku:Ku {uid: $ku_uid})
                MERGE (user)-[:MASTERED]->(ku)
                """,
                user_uid=test_user_uid,
                ku_uid=kus[0].uid,
            )

        # Publish event
        event = KnowledgeMastered(
            ku_uid=kus[0].uid,
            user_uid=test_user_uid,
            mastery_score=0.85,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify both LPs got progress updates
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, LearningPathProgressUpdated)]
        assert len(progress_events) == 2  # One for each LP
        lp_uids = {e.path_uid for e in progress_events}
        assert lp_uids == {lp1.uid, lp2.uid}
