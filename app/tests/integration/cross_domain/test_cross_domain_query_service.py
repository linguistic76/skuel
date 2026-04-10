"""
Integration tests for CrossDomainQueryService against real Neo4j.
=================================================================

The unit tests mock ``QueryExecutor`` and verify marshalling. These tests
verify the Cypher itself — the whole reason the service exists.

Fixture graph
-------------
One user (``user.xdq``) owns:

- principle_1 ("Continuous Learning")
    - GUIDES_GOAL -> goal_1
    - INSPIRES_HABIT -> habit_1
- goal_1 ("Ship v2")
    - goal_1 <-[FULFILLS_GOAL]- task_1 (active)
    - goal_1 <-[CONTRIBUTES_TO_GOAL]- task_2 (active)
- goal_2 ("Stay Healthy") — no task links
- task_1 ("Write tests") — status: active
    - APPLIES_KNOWLEDGE -> ku_1
- task_2 ("Review PR") — status: active
    - REQUIRES_KNOWLEDGE -> ku_1
- task_3 ("Old cleanup") — status: completed (terminal)
    - FULFILLS_GOAL -> goal_1
- habit_1 ("Morning reading") — status: active, streak 12, rate 0.85
    - REINFORCES_KNOWLEDGE -> ku_1
    - REINFORCES_KNOWLEDGE -> ku_2
- habit_2 ("Exercise") — status: active, no KU links
- choice_1 (recent, aligned)
    - ALIGNED_WITH_PRINCIPLE -> principle_1
    - satisfaction_score: 4.5
- choice_2 (recent, no alignment)
- choice_3 (recent, conflicting)
    - CONFLICTS_WITH_PRINCIPLE -> principle_1
- ku_1 ("Python Basics")
- ku_2 ("Neo4j Fundamentals")

All entities are :Entity nodes with ``entity_type`` set, matching
the multi-label convention (domain label + :Entity base).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.principle_enums import AlignmentLevel
from core.services.cross_domain import CrossDomainQueryService

USER_UID = "user.xdq"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j):
    """Seed the fixture graph described in the module docstring."""
    now = datetime.now(tz=UTC).isoformat()
    recent = (datetime.now(tz=UTC) - timedelta(days=5)).isoformat()

    async with neo4j_driver.session() as s:
        # -- User --
        await s.run(
            "MERGE (u:User {uid: $uid}) SET u.created_at = datetime($ts)",
            uid=USER_UID,
            ts=now,
        )

        # -- KUs --
        for ku_uid, title in [
            ("ku_python_xdq", "Python Basics"),
            ("ku_neo4j_xdq", "Neo4j Fundamentals"),
        ]:
            await s.run(
                """
                CREATE (k:Entity {
                    uid: $uid, entity_type: 'ku', title: $title,
                    created_at: datetime($ts)
                })
                """,
                uid=ku_uid,
                title=title,
                ts=now,
            )

        # -- Principle --
        await s.run(
            """
            CREATE (p:Entity {
                uid: 'principle_cl_xdq', entity_type: 'principle',
                title: 'Continuous Learning', created_at: datetime($ts)
            })
            """,
            ts=now,
        )

        # -- Goals --
        for uid, title in [("goal_ship_xdq", "Ship v2"), ("goal_health_xdq", "Stay Healthy")]:
            await s.run(
                """
                CREATE (g:Entity {
                    uid: $uid, entity_type: 'goal', title: $title,
                    status: 'active', created_at: datetime($ts)
                })
                """,
                uid=uid,
                title=title,
                ts=now,
            )

        # -- Tasks --
        for uid, title, status in [
            ("task_tests_xdq", "Write tests", "active"),
            ("task_review_xdq", "Review PR", "active"),
            ("task_cleanup_xdq", "Old cleanup", "completed"),
        ]:
            await s.run(
                """
                CREATE (t:Entity {
                    uid: $uid, entity_type: 'task', title: $title,
                    status: $status, created_at: datetime($ts)
                })
                """,
                uid=uid,
                title=title,
                status=status,
                ts=now,
            )

        # -- Habits --
        await s.run(
            """
            CREATE (h:Entity {
                uid: 'habit_reading_xdq', entity_type: 'habit',
                title: 'Morning reading', status: 'active',
                current_streak: 12, success_rate: 0.85,
                created_at: datetime($ts)
            })
            """,
            ts=now,
        )
        await s.run(
            """
            CREATE (h:Entity {
                uid: 'habit_exercise_xdq', entity_type: 'habit',
                title: 'Exercise', status: 'active',
                current_streak: 3, success_rate: 0.6,
                created_at: datetime($ts)
            })
            """,
            ts=now,
        )

        # -- Choices --
        await s.run(
            """
            CREATE (c:Entity {
                uid: 'choice_aligned_xdq', entity_type: 'choice',
                title: 'Pick a book', satisfaction_score: 4.5,
                created_at: datetime($ts)
            })
            """,
            ts=recent,
        )
        await s.run(
            """
            CREATE (c:Entity {
                uid: 'choice_plain_xdq', entity_type: 'choice',
                title: 'Go for a walk',
                created_at: datetime($ts)
            })
            """,
            ts=recent,
        )
        await s.run(
            """
            CREATE (c:Entity {
                uid: 'choice_conflict_xdq', entity_type: 'choice',
                title: 'Skip studying',
                created_at: datetime($ts)
            })
            """,
            ts=recent,
        )

        # ── OWNS edges (user -> every owned entity) ──
        owned = [
            "principle_cl_xdq",
            "goal_ship_xdq",
            "goal_health_xdq",
            "task_tests_xdq",
            "task_review_xdq",
            "task_cleanup_xdq",
            "habit_reading_xdq",
            "habit_exercise_xdq",
            "choice_aligned_xdq",
            "choice_plain_xdq",
            "choice_conflict_xdq",
        ]
        for entity_uid in owned:
            await s.run(
                """
                MATCH (u:User {uid: $user_uid}), (e:Entity {uid: $entity_uid})
                CREATE (u)-[:OWNS]->(e)
                """,
                user_uid=USER_UID,
                entity_uid=entity_uid,
            )

        # ── Domain relationships ──

        # Principle -> Goal: GUIDES_GOAL
        await s.run(
            """
            MATCH (p:Entity {uid: 'principle_cl_xdq'}), (g:Entity {uid: 'goal_ship_xdq'})
            CREATE (p)-[:GUIDES_GOAL]->(g)
            """,
        )

        # Principle -> Habit: INSPIRES_HABIT
        await s.run(
            """
            MATCH (p:Entity {uid: 'principle_cl_xdq'}), (h:Entity {uid: 'habit_reading_xdq'})
            CREATE (p)-[:INSPIRES_HABIT]->(h)
            """,
        )

        # Task -> Goal: FULFILLS_GOAL, CONTRIBUTES_TO_GOAL
        await s.run(
            """
            MATCH (t:Entity {uid: 'task_tests_xdq'}), (g:Entity {uid: 'goal_ship_xdq'})
            CREATE (t)-[:FULFILLS_GOAL]->(g)
            """,
        )
        await s.run(
            """
            MATCH (t:Entity {uid: 'task_review_xdq'}), (g:Entity {uid: 'goal_ship_xdq'})
            CREATE (t)-[:CONTRIBUTES_TO_GOAL]->(g)
            """,
        )
        await s.run(
            """
            MATCH (t:Entity {uid: 'task_cleanup_xdq'}), (g:Entity {uid: 'goal_ship_xdq'})
            CREATE (t)-[:FULFILLS_GOAL]->(g)
            """,
        )

        # Task -> KU: APPLIES_KNOWLEDGE, REQUIRES_KNOWLEDGE
        await s.run(
            """
            MATCH (t:Entity {uid: 'task_tests_xdq'}), (k:Entity {uid: 'ku_python_xdq'})
            CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)
            """,
        )
        await s.run(
            """
            MATCH (t:Entity {uid: 'task_review_xdq'}), (k:Entity {uid: 'ku_python_xdq'})
            CREATE (t)-[:REQUIRES_KNOWLEDGE]->(k)
            """,
        )

        # Habit -> KU: REINFORCES_KNOWLEDGE
        await s.run(
            """
            MATCH (h:Entity {uid: 'habit_reading_xdq'}), (k:Entity {uid: 'ku_python_xdq'})
            CREATE (h)-[:REINFORCES_KNOWLEDGE]->(k)
            """,
        )
        await s.run(
            """
            MATCH (h:Entity {uid: 'habit_reading_xdq'}), (k:Entity {uid: 'ku_neo4j_xdq'})
            CREATE (h)-[:REINFORCES_KNOWLEDGE]->(k)
            """,
        )

        # Choice -> Principle: ALIGNED_WITH_PRINCIPLE, CONFLICTS_WITH_PRINCIPLE
        await s.run(
            """
            MATCH (c:Entity {uid: 'choice_aligned_xdq'}), (p:Entity {uid: 'principle_cl_xdq'})
            CREATE (c)-[:ALIGNED_WITH_PRINCIPLE]->(p)
            """,
        )
        await s.run(
            """
            MATCH (c:Entity {uid: 'choice_conflict_xdq'}), (p:Entity {uid: 'principle_cl_xdq'})
            CREATE (c)-[:CONFLICTS_WITH_PRINCIPLE]->(p)
            """,
        )

    yield  # graph is ready; clean_neo4j tears it down


@pytest.fixture
def service(neo4j_driver):
    """CrossDomainQueryService wired to a real Neo4j executor."""
    return CrossDomainQueryService(Neo4jQueryExecutor(neo4j_driver))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrincipleAlignmentEvidence:
    async def test_finds_aligned_goals_and_habits(self, service, graph):
        result = await service.get_principle_alignment_evidence(
            principle_uid="principle_cl_xdq",
            user_uid=USER_UID,
        )

        assert result.is_ok
        ev = result.value
        assert ev.principle_uid == "principle_cl_xdq"
        assert ev.user_uid == USER_UID

        goal_uids = {g.uid for g in ev.aligned_goals}
        assert "goal_ship_xdq" in goal_uids

        habit_uids = {h.uid for h in ev.aligned_habits}
        assert "habit_reading_xdq" in habit_uids

        # 2 connections -> score = 2/5 = 0.4
        assert ev.score == pytest.approx(0.4)
        assert ev.alignment_level != AlignmentLevel.UNKNOWN

    async def test_unowned_principle_returns_empty(self, service, graph):
        """Principle that doesn't exist returns zero-score evidence."""
        result = await service.get_principle_alignment_evidence(
            principle_uid="principle_nonexistent",
            user_uid=USER_UID,
        )

        assert result.is_ok
        assert result.value.total_connections == 0
        assert result.value.score == 0.0
        assert result.value.alignment_level == AlignmentLevel.UNKNOWN


@pytest.mark.asyncio
class TestTasksApplyingKnowledge:
    async def test_finds_tasks_for_ku(self, service, graph):
        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python_xdq",
            user_uid=USER_UID,
        )

        assert result.is_ok
        payload = result.value
        assert payload.knowledge_uid == "ku_python_xdq"

        task_uids = {t.uid for t in payload.tasks}
        assert "task_tests_xdq" in task_uids
        assert "task_review_xdq" in task_uids

        rels = {t.uid: t.relationship for t in payload.tasks}
        assert rels["task_tests_xdq"] == "APPLIES_KNOWLEDGE"
        assert rels["task_review_xdq"] == "REQUIRES_KNOWLEDGE"

    async def test_ku_with_no_tasks_returns_empty(self, service, graph):
        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_neo4j_xdq",
            user_uid=USER_UID,
        )

        assert result.is_ok
        assert result.value.tasks == ()

    async def test_respects_limit(self, service, graph):
        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python_xdq",
            user_uid=USER_UID,
            limit=1,
        )

        assert result.is_ok
        assert len(result.value.tasks) == 1


@pytest.mark.asyncio
class TestGoalsForTask:
    async def test_finds_goals_via_fulfills_and_contributes(self, service, graph):
        # task_tests_xdq FULFILLS_GOAL goal_ship_xdq
        result = await service.get_goals_for_task(task_uid="task_tests_xdq")

        assert result.is_ok
        goal_uids = {g.uid for g in result.value}
        assert "goal_ship_xdq" in goal_uids

    async def test_contributes_to_also_found(self, service, graph):
        # task_review_xdq CONTRIBUTES_TO_GOAL goal_ship_xdq
        result = await service.get_goals_for_task(task_uid="task_review_xdq")

        assert result.is_ok
        goal_uids = {g.uid for g in result.value}
        assert "goal_ship_xdq" in goal_uids

    async def test_orphan_task_returns_empty(self, service, graph):
        result = await service.get_goals_for_task(task_uid="task_nonexistent")

        assert result.is_ok
        assert result.value == ()


@pytest.mark.asyncio
class TestCountActiveTasksForGoal:
    async def test_counts_only_active_fulfills(self, service, graph):
        """Only FULFILLS_GOAL edges count, not CONTRIBUTES_TO_GOAL.

        goal_ship_xdq has 3 task links:
        - task_tests (active, FULFILLS_GOAL) -> counted
        - task_review (active, CONTRIBUTES_TO_GOAL) -> NOT counted
        - task_cleanup (completed, FULFILLS_GOAL) -> excluded by status
        """
        result = await service.count_active_tasks_for_goal(goal_uid="goal_ship_xdq")

        assert result.is_ok
        assert result.value.count == 1

    async def test_goal_with_no_tasks(self, service, graph):
        result = await service.count_active_tasks_for_goal(goal_uid="goal_health_xdq")

        assert result.is_ok
        assert result.value.count == 0

    async def test_nonexistent_goal(self, service, graph):
        result = await service.count_active_tasks_for_goal(goal_uid="goal_nonexistent")

        assert result.is_ok
        assert result.value.count == 0


@pytest.mark.asyncio
class TestHabitKnowledgeReinforcement:
    async def test_returns_habits_with_ku_links(self, service, graph):
        result = await service.get_habit_knowledge_reinforcement(user_uid=USER_UID)

        assert result.is_ok
        rows = result.value

        # Only habit_reading has KU links; habit_exercise has none (filtered out)
        assert len(rows) == 1
        row = rows[0]
        assert row.habit_uid == "habit_reading_xdq"
        assert row.current_streak == 12
        assert row.success_rate == pytest.approx(0.85)
        assert set(row.ku_uids) == {"ku_python_xdq", "ku_neo4j_xdq"}

    async def test_user_with_no_habits(self, service, graph):
        result = await service.get_habit_knowledge_reinforcement(user_uid="user.nobody")

        assert result.is_ok
        assert result.value == ()


@pytest.mark.asyncio
class TestChoicePrincipleAdherence:
    async def test_counts_aligned_vs_total(self, service, graph):
        result = await service.get_choice_principle_adherence(
            user_uid=USER_UID,
            period_days=90,
        )

        assert result.is_ok
        adh = result.value
        assert adh.total_choices == 3
        assert adh.aligned_count == 1  # only choice_aligned has ALIGNED_WITH_PRINCIPLE

        # Verify per-choice detail
        detail_map = {d.choice_uid: d for d in adh.choice_details}
        assert "choice_aligned_xdq" in detail_map
        aligned = detail_map["choice_aligned_xdq"]
        assert "principle_cl_xdq" in aligned.principle_uids
        assert aligned.satisfaction == pytest.approx(4.5)

        # Unaligned choice has empty principle_uids
        plain = detail_map["choice_plain_xdq"]
        assert plain.principle_uids == ()

    async def test_period_filter_excludes_old_choices(self, service, graph, neo4j_driver):
        """Create an old choice and verify it's excluded by period_days."""
        old_ts = (datetime.now(tz=UTC) - timedelta(days=200)).isoformat()
        async with neo4j_driver.session() as s:
            await s.run(
                """
                CREATE (c:Entity {
                    uid: 'choice_old_xdq', entity_type: 'choice',
                    title: 'Ancient choice', created_at: datetime($ts)
                })
                """,
                ts=old_ts,
            )
            await s.run(
                """
                MATCH (u:User {uid: $user_uid}), (c:Entity {uid: 'choice_old_xdq'})
                CREATE (u)-[:OWNS]->(c)
                """,
                user_uid=USER_UID,
            )

        result = await service.get_choice_principle_adherence(
            user_uid=USER_UID,
            period_days=90,
        )

        assert result.is_ok
        # Still 3 — the old choice is outside the 90-day window
        assert result.value.total_choices == 3

    async def test_user_with_no_choices(self, service, graph):
        result = await service.get_choice_principle_adherence(
            user_uid="user.nobody",
            period_days=90,
        )

        assert result.is_ok
        assert result.value.total_choices == 0


@pytest.mark.asyncio
class TestChoiceConflictCount:
    async def test_counts_conflicting_choices(self, service, graph):
        result = await service.get_choice_conflict_count(user_uid=USER_UID)

        assert result.is_ok
        assert result.value.conflict_count == 1  # choice_conflict_xdq

    async def test_user_with_no_conflicts(self, service, graph):
        result = await service.get_choice_conflict_count(user_uid="user.nobody")

        assert result.is_ok
        assert result.value.conflict_count == 0
