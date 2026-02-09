"""
Integration Test: Goal Achievement→Recommendations Event-Driven Flow
====================================================================

Tests Phase 4 event-driven architecture for Goal→Recommendations.

This test suite verifies that:
1. GoalAchieved events trigger recommendation generation
2. GoalsRecommendationService.handle_goal_achieved() receives events
3. Recommendations are generated based on goal context (domain, knowledge, habits, principles)
4. GoalRecommendationsGenerated events are published with recommendations
5. Multiple recommendation strategies work (domain progression, knowledge expansion, habit reinforcement, principle alignment)

Event Flow:
-----------
Goal achieved → GoalAchieved event → GoalsRecommendationService.handle_goal_achieved()
    → Query Neo4j for goal context (knowledge, habits, principles)
    → Generate recommendations (4 strategies)
    → Publish GoalRecommendationsGenerated event
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.goal_events import GoalAchieved, GoalRecommendationsGenerated
from core.models.goal.goal import Goal, GoalStatus, GoalType, MeasurementType
from core.models.habit.habit import Habit, HabitStatus
from core.models.ku.ku import Ku
from core.models.principle.principle import Principle
from core.models.enums import (
    Domain,
    SELCategory,
)
from core.services.goals.goals_recommendation_service import GoalsRecommendationService


@pytest.mark.asyncio
class TestGoalRecommendationsFlow:
    """Integration tests for Goal→Recommendations event-driven flow."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def goal_backend(self, neo4j_driver, clean_neo4j):
        """Create Goal backend with clean database."""
        return UniversalNeo4jBackend[Goal](neo4j_driver, "Goal", Goal)

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def habit_backend(self, neo4j_driver, clean_neo4j):
        """Create Habit backend with clean database."""
        return UniversalNeo4jBackend[Habit](neo4j_driver, "Habit", Habit)

    @pytest_asyncio.fixture
    async def principle_backend(self, neo4j_driver, clean_neo4j):
        """Create Principle backend with clean database."""
        return UniversalNeo4jBackend[Principle](neo4j_driver, "Principle", Principle)

    @pytest_asyncio.fixture
    async def recommendation_service(self, event_bus, neo4j_driver):
        """Create GoalsRecommendationService with event bus and driver."""
        return GoalsRecommendationService(
            driver=neo4j_driver,  # Phase 4: For Goal→Recommendations Cypher queries
            event_bus=event_bus,
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_goal_recommendations"

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
    async def achieved_goal_with_context(
        self,
        goal_backend,
        ku_backend,
        habit_backend,
        principle_backend,
        neo4j_driver,
        test_user_uid,
        test_user,
    ):
        """Create an achieved goal with related knowledge, habits, and principles."""
        # Create 2 related knowledge units
        kus = []
        for i, title in enumerate(["Python Basics", "Web Development Fundamentals"], start=1):
            ku = Ku(
                uid=f"ku.tech_{i}",
                title=title,
                content=f"Learn about {title.lower()}",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            result = await ku_backend.create(ku)
            assert result.is_ok
            kus.append(result.value)

        # Create 2 related habits
        habits = []
        for i, name in enumerate(["Daily Coding Practice", "Code Review Participation"], start=1):
            from core.models.habit.habit import HabitCategory

            habit = Habit(
                uid=f"habit.tech_{i}",
                user_uid=test_user_uid,
                name=name,
                description=f"Maintain {name.lower()}",
                category=HabitCategory.LEARNING,
                status=HabitStatus.ACTIVE,
            )
            result = await habit_backend.create(habit)
            assert result.is_ok
            habits.append(result.value)

        # Create 1 guiding principle
        from core.models.principle.principle import PrincipleCategory

        principle = Principle(
            uid="principle.continuous_learning",
            user_uid=test_user_uid,
            name="Continuous Learning",
            statement="Always be learning and growing",
            category=PrincipleCategory.PERSONAL,
        )
        result = await principle_backend.create(principle)
        assert result.is_ok
        principle = result.value

        # Create achieved goal
        goal = Goal(
            uid="goal.build_web_app",
            user_uid=test_user_uid,
            title="Build First Web Application",
            description="Complete a full-stack web application",
            goal_type=GoalType.PROJECT,
            measurement_type=MeasurementType.TASK_BASED,
            domain=Domain.TECH,
            progress_percentage=100.0,
            current_value=100.0,
            target_value=100.0,
            status=GoalStatus.ACHIEVED,
            target_date=date(2025, 12, 31),
        )
        result = await goal_backend.create(goal)
        assert result.is_ok
        created_goal = result.value

        # Create graph relationships
        async with neo4j_driver.session() as session:
            # Link goal to knowledge units
            for ku in kus:
                await session.run(
                    """
                    MATCH (goal:Goal {uid: $goal_uid})
                    MATCH (ku:Ku {uid: $ku_uid})
                    MERGE (goal)-[:REQUIRES_KNOWLEDGE]->(ku)
                    """,
                    goal_uid=goal.uid,
                    ku_uid=ku.uid,
                )

            # Link goal to habits
            for habit in habits:
                await session.run(
                    """
                    MATCH (goal:Goal {uid: $goal_uid})
                    MATCH (habit:Habit {uid: $habit_uid})
                    MERGE (goal)-[:SUPPORTS_GOAL]->(habit)
                    """,
                    goal_uid=goal.uid,
                    habit_uid=habit.uid,
                )

            # Link goal to principle
            await session.run(
                """
                MATCH (goal:Goal {uid: $goal_uid})
                MATCH (principle:Principle {uid: $principle_uid})
                MERGE (goal)-[:GUIDED_BY_PRINCIPLE]->(principle)
                """,
                goal_uid=goal.uid,
                principle_uid=principle.uid,
            )

        return created_goal, kus, habits, [principle]

    # ========================================================================
    # BASIC EVENT FLOW TESTS
    # ========================================================================

    async def test_goal_achieved_triggers_recommendations(
        self,
        event_bus,
        recommendation_service,
        neo4j_driver,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that achieving a goal triggers recommendation generation via events."""
        goal, kus, habits, principles = achieved_goal_with_context

        # Subscribe to GoalAchieved event
        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        # Publish GoalAchieved event
        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
            actual_duration_days=90,
            planned_duration_days=120,
            completed_ahead_of_schedule=True,
        )
        await event_bus.publish_async(achievement_event)

        # Give event processing time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Verify GoalRecommendationsGenerated event was published
        history = event_bus.get_event_history()
        recommendation_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        assert len(recommendation_events) == 1, (
            "Should publish 1 GoalRecommendationsGenerated event"
        )

        # Verify event details
        rec_event = recommendation_events[0]
        assert rec_event.goal_uid == goal.uid
        assert rec_event.user_uid == test_user_uid
        assert rec_event.triggered_by_achievement is True
        assert rec_event.recommendation_count > 0

    async def test_recommendations_generated_with_multiple_strategies(
        self,
        event_bus,
        recommendation_service,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that multiple recommendation strategies are used."""
        goal, kus, habits, principles = achieved_goal_with_context

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        # Publish GoalAchieved event
        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Get recommendation event
        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        assert len(rec_events) == 1

        recommendations = rec_events[0].recommendations

        # Should have multiple recommendations (up to 4 strategies: domain, knowledge, habit, principle)
        assert len(recommendations) >= 2, "Should generate at least 2 recommendations"
        assert len(recommendations) <= 5, "Should limit to max 5 recommendations"

        # Verify recommendation structure
        for rec in recommendations:
            assert "title" in rec
            assert "description" in rec
            assert "rationale" in rec
            assert "confidence" in rec
            assert "recommendation_type" in rec
            assert 0.0 <= rec["confidence"] <= 1.0

        # Verify different recommendation types
        rec_types = {rec["recommendation_type"] for rec in recommendations}
        assert len(rec_types) >= 2, "Should use multiple recommendation strategies"

    async def test_domain_progression_recommendation(
        self,
        event_bus,
        recommendation_service,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that domain progression recommendation is generated."""
        goal, kus, habits, principles = achieved_goal_with_context

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        recommendations = rec_events[0].recommendations

        # Should have domain progression recommendation
        domain_recs = [
            r for r in recommendations if r["recommendation_type"] == "domain_progression"
        ]
        assert len(domain_recs) >= 1, "Should generate domain progression recommendation"

        # Verify domain progression attributes
        domain_rec = domain_recs[0]
        assert domain_rec["suggested_domain"].upper() == "TECH"  # Domain stored as lowercase
        assert "confidence" in domain_rec
        assert domain_rec["confidence"] >= 0.8

    async def test_knowledge_expansion_recommendation(
        self,
        event_bus,
        recommendation_service,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that knowledge expansion recommendation is generated."""
        goal, kus, habits, principles = achieved_goal_with_context

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        recommendations = rec_events[0].recommendations

        # Should have knowledge expansion recommendation
        knowledge_recs = [
            r for r in recommendations if r["recommendation_type"] == "knowledge_expansion"
        ]
        assert len(knowledge_recs) >= 1, "Should generate knowledge expansion recommendation"

        # Verify knowledge expansion attributes
        knowledge_rec = knowledge_recs[0]
        assert "related_knowledge" in knowledge_rec
        assert len(knowledge_rec["related_knowledge"]) >= 1
        assert all(ku.uid in knowledge_rec["related_knowledge"] for ku in kus)

    async def test_habit_reinforcement_recommendation(
        self,
        event_bus,
        recommendation_service,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that habit reinforcement recommendation is generated."""
        goal, kus, habits, principles = achieved_goal_with_context

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        recommendations = rec_events[0].recommendations

        # Should have habit reinforcement recommendation
        habit_recs = [
            r for r in recommendations if r["recommendation_type"] == "habit_reinforcement"
        ]
        assert len(habit_recs) >= 1, "Should generate habit reinforcement recommendation"

        # Verify habit reinforcement attributes
        habit_rec = habit_recs[0]
        assert "related_habits" in habit_rec
        assert len(habit_rec["related_habits"]) >= 1
        assert all(habit.uid in habit_rec["related_habits"] for habit in habits)

    async def test_principle_alignment_recommendation(
        self,
        event_bus,
        recommendation_service,
        achieved_goal_with_context,
        test_user_uid,
    ):
        """Test that principle alignment recommendation is generated."""
        goal, kus, habits, principles = achieved_goal_with_context

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        recommendations = rec_events[0].recommendations

        # Should have principle alignment recommendation
        principle_recs = [
            r for r in recommendations if r["recommendation_type"] == "principle_alignment"
        ]
        assert len(principle_recs) >= 1, "Should generate principle alignment recommendation"

        # Verify principle alignment attributes
        principle_rec = principle_recs[0]
        assert "related_principles" in principle_rec
        assert len(principle_rec["related_principles"]) >= 1
        assert all(p.uid in principle_rec["related_principles"] for p in principles)
        assert principle_rec["confidence"] >= 0.85  # Principle alignment has highest confidence

    async def test_no_recommendations_when_goal_not_found(
        self,
        event_bus,
        recommendation_service,
        test_user_uid,
    ):
        """Test that no recommendations are generated when goal doesn't exist."""
        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        # Publish event for non-existent goal
        achievement_event = GoalAchieved(
            goal_uid="goal.nonexistent",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify no recommendation event published
        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        assert len(rec_events) == 0, "Should not publish recommendations for non-existent goal"

    async def test_recommendations_without_relationships(
        self,
        event_bus,
        recommendation_service,
        goal_backend,
        test_user_uid,
        test_user,
    ):
        """Test that recommendations are generated even without knowledge/habit/principle relationships."""
        # Create goal with no relationships
        goal = Goal(
            uid="goal.simple",
            user_uid=test_user_uid,
            title="Simple Goal",
            description="Goal with no relationships",
            goal_type=GoalType.OUTCOME,
            measurement_type=MeasurementType.NUMERIC,
            domain=Domain.PERSONAL,
            progress_percentage=100.0,
            current_value=100.0,
            target_value=100.0,
            status=GoalStatus.ACHIEVED,
            target_date=date(2025, 12, 31),
        )
        result = await goal_backend.create(goal)
        assert result.is_ok, "Setup failed: Could not create goal"

        event_bus.subscribe(GoalAchieved, recommendation_service.handle_goal_achieved)

        achievement_event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(achievement_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Should still generate domain progression recommendation
        history = event_bus.get_event_history()
        rec_events = [e for e in history if isinstance(e, GoalRecommendationsGenerated)]
        assert len(rec_events) == 1

        recommendations = rec_events[0].recommendations
        assert len(recommendations) >= 1, (
            "Should generate at least domain progression recommendation"
        )

        # Should have domain progression (always generated)
        rec_types = {rec["recommendation_type"] for rec in recommendations}
        assert "domain_progression" in rec_types
