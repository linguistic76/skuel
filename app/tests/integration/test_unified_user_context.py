"""
Integration Tests for UserContext
=========================================

Tests the master user context that provides complete awareness across all domains.

Architecture:
- UserContext is THE read-only aggregate view of user state
- Contains rich domain awareness with UIDs (not just counts)
- Includes intelligence methods for recommendations and analysis
- Cached for performance, invalidated on mutations

Coverage:
- Basic instantiation and defaults
- Intelligence methods (get_ready_to_learn, calculate_life_alignment)
- Property calculations (mastery_average, overdue_count, etc.)
- Cache validity checks
- Cross-domain relationships
"""

from datetime import date, datetime, timedelta

import pytest

from core.models.enums import (
    Domain,
    EnergyLevel,
    GuidanceMode,
    LearningLevel,
    Personality,
    ResponseTone,
)
from core.services.user.unified_user_context import UserContext


class TestUnifiedUserContextBasics:
    """Test basic instantiation and field validation"""

    def test_create_minimal_context(self):
        """Should create context with only required fields"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
        )

        assert context.user_uid == "user:test"
        assert context.username == "testuser"
        assert context.context_version == "3.0"  # Bumped for services layer move
        assert context.active_task_uids == []
        assert context.active_goal_uids == []
        assert context.knowledge_mastery == {}

    def test_create_full_context(self):
        """Should create context with all fields populated"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
            # Task awareness
            active_task_uids=["task:1", "task:2"],
            current_task_focus="task:1",
            task_priorities={"task:1": 0.9, "task:2": 0.5},
            completed_task_uids={"task:100", "task:101"},
            overdue_task_uids=["task:3"],
            today_task_uids=["task:1"],
            # Goal awareness
            active_goal_uids=["goal:1"],
            primary_goal_focus="goal:1",
            goal_progress={"goal:1": 0.6},
            # Habit awareness
            active_habit_uids=["habit:1", "habit:2"],
            habit_streaks={"habit:1": 30, "habit:2": 7},
            habit_completion_rates={"habit:1": 0.95, "habit:2": 0.75},
            # Knowledge awareness
            knowledge_mastery={"ku:python": 0.8, "ku:testing": 0.6},
            mastered_knowledge_uids={"ku:python"},
            in_progress_knowledge_uids={"ku:testing"},
            # Learning path
            life_path_uid="lp:engineer",
            life_path_alignment_score=0.75,
            # Preferences
            learning_level=LearningLevel.ADVANCED,
            current_energy_level=EnergyLevel.HIGH,
            preferred_personality=Personality.TUTOR,
            preferred_tone=ResponseTone.ENCOURAGING,
            preferred_guidance=GuidanceMode.DETAILED,
        )

        # Verify all fields set correctly
        assert context.user_uid == "user:test"
        assert len(context.active_task_uids) == 2
        assert context.task_priorities["task:1"] == 0.9
        assert context.goal_progress["goal:1"] == 0.6
        assert context.habit_streaks["habit:1"] == 30
        assert context.knowledge_mastery["ku:python"] == 0.8
        assert context.life_path_uid == "lp:engineer"
        assert context.learning_level == LearningLevel.ADVANCED

    def test_default_field_types(self):
        """Should initialize all collection fields with correct types"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
        )

        # List fields
        assert isinstance(context.active_task_uids, list)
        assert isinstance(context.active_goal_uids, list)
        assert isinstance(context.active_habit_uids, list)
        assert isinstance(context.upcoming_event_uids, list)

        # Dict fields
        assert isinstance(context.task_priorities, dict)
        assert isinstance(context.knowledge_mastery, dict)
        assert isinstance(context.habit_streaks, dict)
        assert isinstance(context.goal_progress, dict)

        # Set fields
        assert isinstance(context.completed_task_uids, set)
        assert isinstance(context.completed_goal_uids, set)
        assert isinstance(context.mastered_knowledge_uids, set)


class TestCacheValidity:
    """Test cache TTL and validity checks"""

    def test_fresh_context_is_valid(self):
        """Should be valid immediately after creation"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
        )

        assert context.is_cached_valid() is True

    def test_expired_context_is_invalid(self):
        """Should be invalid after TTL expires"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            cache_ttl_seconds=1,  # 1 second TTL
        )

        # Manually set last_refresh to past
        context.last_refresh = datetime.now() - timedelta(seconds=5)

        assert context.is_cached_valid() is False

    def test_custom_ttl(self):
        """Should respect custom TTL settings"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            cache_ttl_seconds=600,  # 10 minutes
        )

        # Set refresh time to 5 minutes ago
        context.last_refresh = datetime.now() - timedelta(minutes=5)

        # Should still be valid (within 10 minute window)
        assert context.is_cached_valid() is True

        # Set refresh time to 11 minutes ago
        context.last_refresh = datetime.now() - timedelta(minutes=11)

        # Should be invalid (outside 10 minute window)
        assert context.is_cached_valid() is False


class TestIntelligenceMethods:
    """Test intelligence and recommendation methods"""

    def test_get_ready_to_learn_no_prerequisites(self):
        """Should return knowledge with no prerequisites"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            next_recommended_knowledge=["ku:python", "ku:testing"],
            prerequisites_needed={},  # No prerequisites
            prerequisites_completed=set(),
        )

        ready = context.get_ready_to_learn()

        assert len(ready) == 2
        assert "ku:python" in ready
        assert "ku:testing" in ready

    def test_get_ready_to_learn_with_prerequisites_met(self):
        """Should return knowledge where all prerequisites are completed"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            next_recommended_knowledge=["ku:advanced_python", "ku:web_dev"],
            prerequisites_needed={
                "ku:advanced_python": ["ku:python"],
                "ku:web_dev": ["ku:python", "ku:html"],
            },
            prerequisites_completed={"ku:python", "ku:html"},
        )

        ready = context.get_ready_to_learn()

        # Both prerequisites met - both should be ready
        assert len(ready) == 2
        assert "ku:advanced_python" in ready
        assert "ku:web_dev" in ready

    def test_get_ready_to_learn_with_prerequisites_missing(self):
        """Should exclude knowledge with missing prerequisites"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            next_recommended_knowledge=["ku:advanced_python", "ku:web_dev"],
            prerequisites_needed={
                "ku:advanced_python": ["ku:python"],
                "ku:web_dev": ["ku:python", "ku:html"],
            },
            prerequisites_completed={"ku:python"},  # Missing ku:html
        )

        ready = context.get_ready_to_learn()

        # Only advanced_python has prerequisites met
        assert len(ready) == 1
        assert "ku:advanced_python" in ready
        assert "ku:web_dev" not in ready  # Missing ku:html

    def test_calculate_life_alignment_empty_path(self):
        """Should return 0.0 for empty life path"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
        )

        alignment = context.calculate_life_alignment([])

        assert alignment == 0.0
        assert context.life_path_alignment_score == 0.0

    def test_calculate_life_alignment_high_substance(self):
        """Should return high alignment for high substance knowledge"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            knowledge_mastery={
                "ku:meditation": 0.9,
                "ku:yoga": 0.85,
                "ku:mindfulness": 0.8,
            },
        )

        # Life path focuses on wellness
        life_path_knowledge = ["ku:meditation", "ku:yoga", "ku:mindfulness"]
        alignment = context.calculate_life_alignment(life_path_knowledge)

        # Average of 0.9, 0.85, 0.8 = 0.85
        assert alignment == pytest.approx(0.85, abs=0.01)
        assert context.life_path_alignment_score == pytest.approx(0.85, abs=0.01)

    def test_calculate_life_alignment_low_substance(self):
        """Should return low alignment for theoretical knowledge"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            knowledge_mastery={
                "ku:meditation": 0.3,  # Theoretical only
                "ku:yoga": 0.2,
                "ku:mindfulness": 0.1,
            },
        )

        life_path_knowledge = ["ku:meditation", "ku:yoga", "ku:mindfulness"]
        alignment = context.calculate_life_alignment(life_path_knowledge)

        # Average of 0.3, 0.2, 0.1 = 0.2 (theoretical knowledge, not lived)
        assert alignment == pytest.approx(0.2, abs=0.01)

    def test_is_life_aligned_default_threshold(self):
        """Should check alignment against default threshold (0.7)"""
        # High alignment - should pass
        context_aligned = UserContext(
            user_uid="user:test",
            username="testuser",
            life_path_alignment_score=0.8,
        )
        assert context_aligned.is_life_aligned() is True

        # Low alignment - should fail
        context_unaligned = UserContext(
            user_uid="user:test2",
            username="testuser2",
            life_path_alignment_score=0.5,
        )
        assert context_unaligned.is_life_aligned() is False

    def test_is_life_aligned_custom_threshold(self):
        """Should check alignment against custom threshold"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            life_path_alignment_score=0.6,
        )

        # Fails default threshold (0.7)
        assert context.is_life_aligned() is False

        # Passes custom threshold (0.5)
        assert context.is_life_aligned(threshold=0.5) is True

    def test_get_knowledge_gaps_for_goal(self):
        """Should identify missing knowledge for goals"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            prerequisites_needed={
                "ku:advanced_python": ["ku:python"],
                "ku:web_dev": ["ku:html", "ku:css"],
            },
            mastered_knowledge_uids={"ku:python"},  # Only python mastered
        )

        gaps = context.get_knowledge_gaps_for_goal("goal:build_webapp")

        # Should include web_dev (not mastered, has prereqs)
        assert "ku:web_dev" in gaps
        # Should NOT include advanced_python (python prerequisite met, but not started)


class TestPropertyCalculations:
    """Test computed properties"""

    def test_mastery_average_empty(self):
        """Should return 0.0 for no knowledge"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            knowledge_mastery={},
        )

        assert context.mastery_average == 0.0

    def test_mastery_average_calculation(self):
        """Should correctly calculate average mastery"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            knowledge_mastery={
                "ku:python": 0.8,
                "ku:testing": 0.6,
                "ku:docker": 0.9,
            },
        )

        # Average of 0.8, 0.6, 0.9 = 0.7666...
        assert context.mastery_average == pytest.approx(0.7667, abs=0.01)

    def test_concepts_needing_review(self):
        """Should identify knowledge in review range (0.4-0.8)"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            knowledge_mastery={
                "ku:mastered": 0.9,  # Above review range
                "ku:needs_review_1": 0.6,  # In review range
                "ku:needs_review_2": 0.5,  # In review range
                "ku:forgotten": 0.2,  # Below review range
            },
        )

        needs_review = context.concepts_needing_review

        assert len(needs_review) == 2
        assert "ku:needs_review_1" in needs_review
        assert "ku:needs_review_2" in needs_review
        assert "ku:mastered" not in needs_review
        assert "ku:forgotten" not in needs_review


class TestCrossDomainRelationships:
    """Test cross-domain awareness and relationships"""

    def test_tasks_by_goal_relationship(self):
        """Should maintain task-goal relationships"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            tasks_by_goal={
                "goal:1": ["task:1", "task:2"],
                "goal:2": ["task:3"],
            },
        )

        assert len(context.tasks_by_goal["goal:1"]) == 2
        assert "task:1" in context.tasks_by_goal["goal:1"]
        assert len(context.tasks_by_goal["goal:2"]) == 1

    def test_habits_by_goal_relationship(self):
        """Should maintain habit-goal relationships"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            habits_by_goal={
                "goal:fitness": ["habit:run", "habit:yoga"],
                "goal:learning": ["habit:read"],
            },
        )

        assert len(context.habits_by_goal["goal:fitness"]) == 2
        assert "habit:run" in context.habits_by_goal["goal:fitness"]

    def test_events_by_habit_relationship(self):
        """Should maintain event-habit relationships"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            events_by_habit={
                "habit:meditation": ["event:1", "event:2", "event:3"],
            },
        )

        assert len(context.events_by_habit["habit:meditation"]) == 3


class TestWorkloadAndCapacity:
    """Test workload tracking and capacity management"""

    def test_workload_score_calculation(self):
        """Should track current workload"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            current_workload_score=0.75,  # 75% capacity
            recommended_daily_tasks=3,
            recommended_daily_events=2,
        )

        assert context.current_workload_score == 0.75
        assert context.recommended_daily_tasks == 3

    def test_capacity_by_domain(self):
        """Should track capacity across domains"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            capacity_by_domain={
                Domain.TECH: 0.8,
                Domain.PERSONAL: 0.5,
                Domain.HEALTH: 0.3,
            },
        )

        assert context.capacity_by_domain[Domain.TECH] == 0.8
        assert context.capacity_by_domain[Domain.PERSONAL] == 0.5

    def test_overwhelmed_state(self):
        """Should track overwhelmed state"""
        context_normal = UserContext(
            user_uid="user:test",
            username="testuser",
            is_overwhelmed=False,
        )
        assert context_normal.is_overwhelmed is False

        context_overwhelmed = UserContext(
            user_uid="user:test2",
            username="testuser2",
            is_overwhelmed=True,
        )
        assert context_overwhelmed.is_overwhelmed is True


class TestDomainProgress:
    """Test progress and velocity tracking across domains"""

    def test_domain_progress_tracking(self):
        """Should track progress by domain"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            domain_progress={
                Domain.TECH: 0.75,
                Domain.PERSONAL: 0.60,
                Domain.HEALTH: 0.40,
            },
        )

        assert context.domain_progress[Domain.TECH] == 0.75
        assert context.domain_progress[Domain.PERSONAL] == 0.60

    def test_velocity_tracking(self):
        """Should track velocity by domain"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            velocity_by_domain={
                Domain.TECH: 0.05,  # 5% progress per week
                Domain.PERSONAL: 0.03,
            },
        )

        assert context.velocity_by_domain[Domain.TECH] == 0.05

    def test_acceleration_tracking(self):
        """Should track acceleration (velocity change)"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            acceleration_by_domain={
                Domain.TECH: 0.01,  # Velocity increasing
                Domain.PERSONAL: -0.005,  # Velocity decreasing
            },
        )

        assert context.acceleration_by_domain[Domain.TECH] == 0.01
        assert context.acceleration_by_domain[Domain.PERSONAL] == -0.005

    def test_consistency_tracking(self):
        """Should track consistency by domain"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            overall_consistency_score=0.85,
            consistency_by_domain={
                Domain.TECH: 0.9,
                Domain.HEALTH: 0.7,
            },
        )

        assert context.overall_consistency_score == 0.85
        assert context.consistency_by_domain[Domain.TECH] == 0.9


class TestFacetAwareness:
    """Test facet profile and content preferences"""

    def test_facet_profile(self):
        """Should track facet profile"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["python", "testing", "docker"],
                "domains": ["TECH"],
                "difficulty": ["intermediate", "advanced"],
            },
        )

        assert "python" in context.facet_profile["tags"]
        assert len(context.facet_profile["tags"]) == 3

    def test_facet_affinities(self):
        """Should track facet affinities (preference scores)"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_affinities={
                "python": 0.9,
                "testing": 0.7,
                "frontend": 0.4,
            },
        )

        assert context.facet_affinities["python"] == 0.9
        assert context.facet_affinities["testing"] == 0.7

    def test_content_type_preferences(self):
        """Should track content type preferences"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            content_type_preferences={
                "tutorial": 0.8,
                "reference": 0.6,
                "exercise": 0.9,
            },
        )

        assert context.content_type_preferences["tutorial"] == 0.8
        assert context.content_type_preferences["exercise"] == 0.9


class TestUserContextBuilder:
    """Test UserContextBuilder builds context from real Neo4j data"""

    # This is the fixed version of the test - consolidates all entity creation into ONE session

    @pytest.mark.asyncio
    async def test_context_builder_integration(self, user_service, clean_neo4j):
        """Verify UserContextBuilder correctly populates context from real services."""
        from datetime import time, timedelta

        from core.models.enums import (
            EntityStatus,
            Priority,
            RecurrencePattern,
        )
        from core.models.user.user import User

        # Setup: Create test user directly via Cypher (bypassing UserService serialization bug)
        test_user_uid = "user:context_builder_test"
        driver = user_service.context_builder.executor.driver

        # Clean up any existing test data from previous runs
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                OPTIONAL MATCH (u)-[r]-()
                DETACH DELETE r, u
                """,
                user_uid=test_user_uid,
            )
            await session.run(
                """
                MATCH (n)
                WHERE n.uid STARTS WITH 'task:builder_'
                   OR n.uid STARTS WITH 'habit:builder_'
                   OR n.uid STARTS WITH 'goal:builder_'
                   OR n.uid STARTS WITH 'event:builder_'
                   OR n.uid STARTS WITH 'ku:builder_'
                DETACH DELETE n
                """
            )

        # Create user directly in Neo4j via Cypher
        async with driver.session() as session:
            await session.run(
                """
                CREATE (u:User {
                    uid: $uid,
                    title: $title,
                    email: $email,
                    display_name: $display_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                """,
                uid=test_user_uid,
                title="Context Builder Test User",
                email="test@context.com",
                display_name="Context Builder Test User",
            )

        # Verify user exists in Neo4j
        async with driver.session() as session:
            user_check = await session.run(
                "MATCH (u:User {uid: $user_uid}) RETURN u.uid as uid, u.title as title",
                user_uid=test_user_uid,
            )
            user_record = await user_check.single()
            if not user_record:
                raise ValueError(f"User {test_user_uid} not found in Neo4j!")
            print(f"\n✅ User verified in Neo4j: {user_record['uid']} - {user_record['title']}\n")

        # Create User object for context building (needed by builder.build_user_context())
        test_user = User(
            uid=test_user_uid,
            title="Context Builder Test User",
            email="test@context.com",
        )

        # Create all test entities in a SINGLE session to avoid transaction isolation
        async with driver.session() as session:
            # Tasks (MEGA-QUERY expects status IN ['draft', 'scheduled', 'active', 'blocked'])
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (t1:Task {
                    uid: $uid1,
                    title: 'Test Task 1',
                    user_uid: $user_uid,
                    status: $status,
                    priority: $priority,
                    due_date: date($due_date),
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (t2:Task {
                    uid: $uid2,
                    title: 'Test Task 2',
                    user_uid: $user_uid,
                    status: $status,
                    priority: $priority,
                    due_date: date($today),
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:OWNS]->(t1)
                CREATE (u)-[:OWNS]->(t2)
                """,
                uid1="task:builder_1",
                uid2="task:builder_2",
                user_uid=test_user_uid,
                status="active",
                priority=Priority.HIGH.value,
                due_date=(date.today() + timedelta(days=5)).isoformat(),
                today=date.today().isoformat(),
            )

            # Habit
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (h:Habit {
                    uid: $uid,
                    title: 'Test Habit',
                    user_uid: $user_uid,
                    status: $status,
                    frequency: $frequency,
                    current_streak: $streak,
                    completion_rate: $rate,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:OWNS]->(h)
                """,
                uid="habit:builder_1",
                user_uid=test_user_uid,
                status="active",
                frequency=RecurrencePattern.DAILY.value,
                streak=15,
                rate=0.85,
            )

            # Goal
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (g:Goal {
                    uid: $uid,
                    title: 'Test Goal',
                    user_uid: $user_uid,
                    status: $status,
                    progress: $progress,
                    target_date: date($target_date),
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:OWNS]->(g)
                """,
                uid="goal:builder_1",
                user_uid=test_user_uid,
                status=EntityStatus.ACTIVE.value,
                progress=0.6,
                target_date=(date.today() + timedelta(days=30)).isoformat(),
            )

            # Event
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (e:Event {
                    uid: $uid,
                    title: 'Test Event',
                    user_uid: $user_uid,
                    status: $status,
                    event_date: date($event_date),
                    start_time: time($start_time),
                    end_time: time($end_time),
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:OWNS]->(e)
                """,
                uid="event:builder_1",
                user_uid=test_user_uid,
                status=EntityStatus.SCHEDULED.value,
                event_date=(date.today() + timedelta(days=2)).isoformat(),
                start_time=time(14, 0).isoformat(),
                end_time=time(15, 0).isoformat(),
            )

            # Knowledge
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (k:Entity {
                    uid: $uid,
                    title: 'Test Knowledge',
                    content: 'Test content',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:MASTERED {mastery_score: $score}]->(k)
                """,
                uid="ku:builder_1",
                user_uid=test_user_uid,
                score=0.9,
            )

        # Verify entities exist before calling builder (debug query)
        async with driver.session() as session:
            verify_result = await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
                OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
                OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
                OPTIONAL MATCH (u)-[:OWNS]->(e:Event)
                OPTIONAL MATCH (u)-[:MASTERED]->(k:Entity)
                RETURN
                    count(DISTINCT t) as task_count,
                    count(DISTINCT h) as habit_count,
                    count(DISTINCT g) as goal_count,
                    count(DISTINCT e) as event_count,
                    count(DISTINCT k) as knowledge_count
                """,
                user_uid=test_user_uid,
            )
            verify_record = await verify_result.single()
            print("\n=== Entity Verification ===")
            print(f"Tasks: {verify_record['task_count']}")
            print(f"Habits: {verify_record['habit_count']}")
            print(f"Goals: {verify_record['goal_count']}")
            print(f"Events: {verify_record['event_count']}")
            print(f"Knowledge: {verify_record['knowledge_count']}")
            print("==========================\n")

        # Test: Build context using UserContextBuilder
        builder = user_service.context_builder
        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify result is ok and unwrap
        assert context_result.is_ok, f"Failed to build context: {context_result.error}"
        context = context_result.value

        # Verify context is populated with real UIDs from Neo4j
        assert context.user_uid == test_user_uid
        assert context.username == "Context Builder Test User"
        assert context.email == "test@context.com"

        # Verify task data
        assert len(context.active_task_uids) == 2
        assert "task:builder_1" in context.active_task_uids
        assert "task:builder_2" in context.active_task_uids
        assert "task:builder_2" in context.today_task_uids  # Due today

        # Verify habit data
        assert len(context.active_habit_uids) == 1
        assert "habit:builder_1" in context.active_habit_uids
        assert context.habit_streaks["habit:builder_1"] == 15
        assert context.habit_completion_rates["habit:builder_1"] == 0.85

        # Verify goal data
        assert len(context.active_goal_uids) == 1
        assert "goal:builder_1" in context.active_goal_uids
        assert context.goal_progress["goal:builder_1"] == 0.6

        # Verify event data
        assert len(context.upcoming_event_uids) == 1
        assert "event:builder_1" in context.upcoming_event_uids

        # Verify knowledge data
        assert len(context.mastered_knowledge_uids) == 1
        assert "ku:builder_1" in context.mastered_knowledge_uids
        assert context.knowledge_mastery["ku:builder_1"] == 0.9

    @pytest.mark.asyncio
    async def test_context_builder_empty_user(self, user_service, clean_neo4j):
        """
        Verify builder handles user with no domain entities gracefully.
        """
        from core.models.user.user import User

        # Create user with no tasks/habits/goals
        test_user_uid = "user:empty_context"
        test_user = User(
            uid=test_user_uid,
            title="Empty User",
            email="empty@test.com",
        )

        user_result = await user_service.create_user(test_user)
        assert user_result.is_ok

        # Build context for user with no entities
        builder = user_service.context_builder
        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify result is ok and unwrap
        assert context_result.is_ok, f"Failed to build context: {context_result.error}"
        context = context_result.value

        # Verify context has empty collections (not errors)
        assert context.user_uid == test_user_uid
        assert context.active_task_uids == []
        assert context.active_goal_uids == []
        assert context.active_habit_uids == []
        assert context.upcoming_event_uids == []
        assert context.mastered_knowledge_uids == set()
        assert context.knowledge_mastery == {}
        assert context.current_workload_score == 0.0  # No workload


class TestActivityRichField:
    """activity_rich field: empty without time_period, populated when provided."""

    def test_activity_rich_defaults_to_empty_dict(self):
        """UserContext.activity_rich is an empty dict by default."""
        context = UserContext(user_uid="user:test", username="testuser")
        assert context.activity_rich == {}

    def test_activity_window_metadata_defaults_to_none(self):
        """Window metadata fields are None when no time_period is in use."""
        context = UserContext(user_uid="user:test", username="testuser")
        assert context.activity_window_period is None
        assert context.activity_window_start is None
        assert context.activity_window_end is None

    @pytest.mark.asyncio
    async def test_build_rich_without_time_period_leaves_activity_rich_empty(
        self, user_service, clean_neo4j
    ):
        """build_rich_user_context() with no time_period → activity_rich stays empty dict."""
        from core.models.user.user import User

        user_uid = "user:ar_no_period"
        driver = user_service.context_builder.executor.driver
        async with driver.session() as session:
            await session.run(
                "CREATE (u:User {uid: $uid, title: 'AR No Period', "
                "email: 'ar_no_period@test.com', created_at: datetime(), updated_at: datetime()})",
                uid=user_uid,
            )

        test_user = User(uid=user_uid, title="AR No Period", email="ar_no_period@test.com")
        builder = user_service.context_builder
        result = await builder.build_rich_user_context(user_uid, test_user)

        assert result.is_ok, f"build_rich_user_context failed: {result.error}"
        assert result.value.activity_rich == {}
        assert result.value.activity_window_period is None

    @pytest.mark.asyncio
    async def test_build_rich_with_time_period_populates_activity_rich(
        self, user_service, clean_neo4j
    ):
        """build_rich_user_context(time_period='7d') → activity_rich has correct structure."""
        from datetime import date, timedelta

        from core.models.user.user import User

        user_uid = "user:ar_with_period"
        driver = user_service.context_builder.executor.driver

        async with driver.session() as session:
            await session.run(
                """
                CREATE (u:User {uid: $uid, title: 'AR With Period',
                    email: 'ar_with_period@test.com',
                    created_at: datetime(), updated_at: datetime()})
                WITH u
                CREATE (t:Task {
                    uid: $task_uid,
                    title: 'Recent Task',
                    user_uid: $uid,
                    status: 'completed',
                    priority: 'high',
                    due_date: date($due_date),
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:OWNS]->(t)
                """,
                uid=user_uid,
                task_uid="task:ar_recent_1",
                due_date=(date.today() + timedelta(days=1)).isoformat(),
            )

        test_user = User(uid=user_uid, title="AR With Period", email="ar_with_period@test.com")
        builder = user_service.context_builder
        result = await builder.build_rich_user_context(user_uid, test_user, time_period="7d")

        assert result.is_ok, f"build_rich_user_context failed: {result.error}"
        ctx = result.value

        # Window metadata is set
        assert ctx.activity_window_period == "7d"
        assert ctx.activity_window_start is not None
        assert ctx.activity_window_end is not None

        # activity_rich has the expected domain keys
        assert "tasks" in ctx.activity_rich
        assert "goals" in ctx.activity_rich
        assert "habits" in ctx.activity_rich
        assert "events" in ctx.activity_rich
        assert "choices" in ctx.activity_rich
        assert "principles" in ctx.activity_rich

        # The recently-updated task appears in the window
        tasks = ctx.activity_rich["tasks"]
        assert len(tasks) == 1
        item = tasks[0]
        assert "entity" in item
        assert "graph_context" in item
        assert item["entity"]["uid"] == "task:ar_recent_1"
        assert item["entity"]["title"] == "Recent Task"
        assert item["entity"]["status"] == "completed"
