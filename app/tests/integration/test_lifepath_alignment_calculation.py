"""
Integration tests for LifePath alignment calculation + facade flows.

Exercises LifePathAlignmentService's 5-dimension Cypher against a seeded
real graph (testcontainer): knowledge (MASTERED + APPLIES_KNOWLEDGE
substance), activity (OWNS + APPLIES_KNOWLEDGE ratios), goal/principle
(SERVES_LIFE_PATH), and momentum (recent vs previous week). Then drives
the LifePathService facade end-to-end: designate_and_calculate,
get_full_status, and check_word_action_alignment.

The dimension assertions pin the documented weights (25/25/20/15/15) and
per-query scoring rules — if a weight changes deliberately, update both
the service and these numbers together.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.lifepath.lifepath_alignment_service import LifePathAlignmentService
from core.services.lifepath.lifepath_service import LifePathService
from core.services.user.unified_user_context import UserContext

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Rich-scenario user (pre-designated, with activity)
_USER_RICH = "user_test_lifepath_align_rich"
# Facade-flow user (designates during the test, no activity)
_USER_FACADE = "user_test_lifepath_align_facade"
# Blank user (no vision, no designation)
_USER_BLANK = "user_test_lifepath_align_blank"

_LP_RICH = "lp.test.align.rich"
_LP_FACADE = "lp.test.align.facade"

_UIDS = [
    _USER_RICH,
    _USER_FACADE,
    _USER_BLANK,
    _LP_RICH,
    _LP_FACADE,
    "ps.test.align.rich",
    "ps.test.align.facade",
    "ku_test_align_mastered",
    "ku_test_align_gap",
    "ku_test_align_facade",
    "task_test_align_recent",
    "task_test_align_previous",
    "task_test_align_offpath",
    "habit_test_align_aligned",
    "habit_test_align_offpath",
    "goal_test_align_serving",
    "goal_test_align_other",
    "principle_test_align_serving",
    "principle_test_align_other",
]


@pytest_asyncio.fixture(loop_scope="session")
async def alignment_graph(neo4j_driver):
    """Seed the full 5-dimension scenario with production vocabulary."""
    now = datetime.now()
    three_days_ago = (now - timedelta(days=3)).isoformat()
    ten_days_ago = (now - timedelta(days=10)).isoformat()

    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)

        for user_uid in (_USER_RICH, _USER_FACADE, _USER_BLANK):
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=user_uid)

        # --- Rich scenario: designated life path with two KUs -------------
        await session.run(
            """
            MERGE (lp:Entity:LearningPath {uid: $lp})
            SET lp.title = 'Rich Alignment LP', lp.entity_type = 'life_path',
                lp.status = 'active'
            MERGE (ps:Entity:PathStep {uid: 'ps.test.align.rich'})
            SET ps.title = 'Rich Step', ps.entity_type = 'path_step', ps.status = 'active'
            MERGE (lp)-[:HAS_STEP {sequence: 1}]->(ps)
            MERGE (ku1:Entity:Ku {uid: 'ku_test_align_mastered'})
            SET ku1.title = 'Mastered KU', ku1.entity_type = 'ku'
            MERGE (ku2:Entity:Ku {uid: 'ku_test_align_gap'})
            SET ku2.title = 'Gap KU', ku2.entity_type = 'ku'
            MERGE (ps)-[:USES_KU]->(ku1)
            MERGE (ps)-[:USES_KU]->(ku2)
            """,
            lp=_LP_RICH,
        )
        await session.run(
            """
            MATCH (u:User {uid: $user}), (lp:Entity {uid: $lp})
            MERGE (u)-[:ULTIMATE_PATH {designated_at: $ts}]->(lp)
            """,
            user=_USER_RICH,
            lp=_LP_RICH,
            ts=now.isoformat(),
        )
        await session.run(
            """
            MATCH (u:User {uid: $user}), (ku:Entity {uid: 'ku_test_align_mastered'})
            MERGE (u)-[:MASTERED {mastery_score: 0.9}]->(ku)
            """,
            user=_USER_RICH,
        )

        # Tasks: two aligned (one recent, one previous week), one off-path
        for uid, created_at, applies in (
            ("task_test_align_recent", three_days_ago, True),
            ("task_test_align_previous", ten_days_ago, True),
            ("task_test_align_offpath", three_days_ago, False),
        ):
            await session.run(
                """
                MATCH (u:User {uid: $user})
                MERGE (t:Entity:Task {uid: $uid})
                SET t.title = $uid, t.entity_type = 'task', t.status = 'active',
                    t.user_uid = $user, t.created_at = $created_at
                MERGE (u)-[:OWNS]->(t)
                """,
                user=_USER_RICH,
                uid=uid,
                created_at=created_at,
            )
            if applies:
                await session.run(
                    """
                    MATCH (t:Entity {uid: $uid}), (ku:Entity {uid: 'ku_test_align_mastered'})
                    MERGE (t)-[:APPLIES_KNOWLEDGE]->(ku)
                    """,
                    uid=uid,
                )

        # Habits: one aligned, one off-path
        for uid, applies in (
            ("habit_test_align_aligned", True),
            ("habit_test_align_offpath", False),
        ):
            await session.run(
                """
                MATCH (u:User {uid: $user})
                MERGE (h:Entity:Habit {uid: $uid})
                SET h.title = $uid, h.entity_type = 'habit', h.status = 'active',
                    h.user_uid = $user
                MERGE (u)-[:OWNS]->(h)
                """,
                user=_USER_RICH,
                uid=uid,
            )
            if applies:
                await session.run(
                    """
                    MATCH (h:Entity {uid: $uid}), (ku:Entity {uid: 'ku_test_align_mastered'})
                    MERGE (h)-[:APPLIES_KNOWLEDGE]->(ku)
                    """,
                    uid=uid,
                )

        # Goals: one serving the life path, one not
        for uid, serves in (
            ("goal_test_align_serving", True),
            ("goal_test_align_other", False),
        ):
            await session.run(
                """
                MATCH (u:User {uid: $user})
                MERGE (g:Entity:Goal {uid: $uid})
                SET g.title = $uid, g.entity_type = 'goal', g.status = 'active',
                    g.user_uid = $user
                MERGE (u)-[:OWNS]->(g)
                """,
                user=_USER_RICH,
                uid=uid,
            )
            if serves:
                await session.run(
                    """
                    MATCH (g:Entity {uid: $uid}), (lp:Entity {uid: $lp})
                    MERGE (g)-[:SERVES_LIFE_PATH]->(lp)
                    """,
                    uid=uid,
                    lp=_LP_RICH,
                )

        # Principles: one serving, one not
        for uid, serves in (
            ("principle_test_align_serving", True),
            ("principle_test_align_other", False),
        ):
            await session.run(
                """
                MATCH (u:User {uid: $user})
                MERGE (p:Entity:Principle {uid: $uid})
                SET p.title = $uid, p.entity_type = 'principle', p.status = 'active',
                    p.user_uid = $user
                MERGE (u)-[:OWNS]->(p)
                """,
                user=_USER_RICH,
                uid=uid,
            )
            if serves:
                await session.run(
                    """
                    MATCH (p:Entity {uid: $uid}), (lp:Entity {uid: $lp})
                    MERGE (p)-[:SERVES_LIFE_PATH]->(lp)
                    """,
                    uid=uid,
                    lp=_LP_RICH,
                )

        # --- Facade scenario: undesignated LP with one untouched KU -------
        await session.run(
            """
            MERGE (lp:Entity:LearningPath {uid: $lp})
            SET lp.title = 'Facade Flow LP', lp.entity_type = 'learning_path',
                lp.status = 'active'
            MERGE (ps:Entity:PathStep {uid: 'ps.test.align.facade'})
            SET ps.title = 'Facade Step', ps.entity_type = 'path_step', ps.status = 'active'
            MERGE (lp)-[:HAS_STEP {sequence: 1}]->(ps)
            MERGE (ku:Entity:Ku {uid: 'ku_test_align_facade'})
            SET ku.title = 'Facade KU', ku.entity_type = 'ku'
            MERGE (ps)-[:USES_KU]->(ku)
            """,
            lp=_LP_FACADE,
        )

    yield {"user_uid": _USER_RICH, "lp_uid": _LP_RICH}

    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


@pytest_asyncio.fixture(loop_scope="session")
async def alignment_service(neo4j_driver) -> LifePathAlignmentService:
    backend = LifePathBackend(Neo4jQueryExecutor(neo4j_driver))
    return LifePathAlignmentService(backend=backend, lp_service=None, ku_service=None)


@pytest_asyncio.fixture(loop_scope="session")
async def lifepath_facade(neo4j_driver) -> LifePathService:
    """Facade with real backend; peer services None (CORE-tier shape)."""
    backend = LifePathBackend(Neo4jQueryExecutor(neo4j_driver))
    return LifePathService(
        backend=backend,
        lp_service=None,
        ku_service=None,
        user_service=None,
        llm_service=None,
    )


class TestCalculateAlignment:
    async def test_no_designation_yields_undefined_response(
        self, alignment_service, alignment_graph
    ):
        result = await alignment_service.calculate_alignment(UserContext(user_uid=_USER_BLANK))

        assert result.is_ok
        data = result.value
        assert data["life_path_uid"] is None
        assert data["alignment_score"] == pytest.approx(0.0)
        assert data["alignment_level"] == "undefined"
        assert data["message"]

    async def test_five_dimensions_scored_from_real_graph(self, alignment_service, alignment_graph):
        result = await alignment_service.calculate_alignment(UserContext(user_uid=_USER_RICH))

        assert result.is_ok
        data = result.value
        assert data["life_path_uid"] == _LP_RICH
        dims = data["dimensions"]

        # knowledge: avg over 2 KUs of (mastery*0.6 + tasks*0.05 + habits*0.10)
        #   mastered KU: 0.9*0.6 + 2*0.05 + 1*0.10 = 0.74; gap KU: 0.0
        assert dims["knowledge"] == pytest.approx(0.37, abs=1e-3)
        # activity: task_ratio 2/3 * 0.4 + habit_ratio 1/2 * 0.6
        assert dims["activity"] == pytest.approx(2 / 3 * 0.4 + 0.5 * 0.6, abs=1e-3)
        # goal / principle: 1 serving of 2 active
        assert dims["goal"] == pytest.approx(0.5, abs=1e-3)
        assert dims["principle"] == pytest.approx(0.5, abs=1e-3)
        # momentum: 1 recent vs 1 previous aligned task → ratio 1.0 band
        assert dims["momentum"] == pytest.approx(0.7, abs=1e-3)

        # overall = documented 25/25/20/15/15 weighting of the returned dims
        expected_overall = (
            dims["knowledge"] * 0.25
            + dims["activity"] * 0.25
            + dims["goal"] * 0.20
            + dims["principle"] * 0.15
            + dims["momentum"] * 0.15
        )
        assert data["alignment_score"] == pytest.approx(expected_overall, abs=1e-3)

        # substance stats: mastered KU is embodied (≥0.7), gap KU theoretical (<0.5)
        assert data["knowledge_stats"] == {"total": 2, "embodied": 1, "theoretical": 1}

        # knowledge (0.37) is the only dimension under 0.5 → exactly its rec
        assert data["recommendations"] == [
            "Focus on mastering the knowledge units in your life path"
        ]


class TestFacadeFlows:
    async def test_designate_and_calculate_writes_alignment_to_edge(
        self, lifepath_facade, alignment_graph, neo4j_driver
    ):
        result = await lifepath_facade.designate_and_calculate(_USER_FACADE, _LP_FACADE)

        assert result.is_ok
        payload = result.value
        assert payload["designation"]["life_path_uid"] == _LP_FACADE
        assert payload["designation"]["designated_at"] is not None

        # Untouched LP: knowledge 0, everything else at the 0.5 neutral default
        # → overall 0*0.25 + 0.5*0.25 + 0.5*0.20 + 0.5*0.15 + 0.5*0.15 = 0.375
        assert payload["alignment"]["alignment_score"] == pytest.approx(0.375, abs=1e-3)

        # The score must land on the ULTIMATE_PATH edge (trend/source of truth)
        async with neo4j_driver.session() as session:
            edge = await session.run(
                """
                MATCH (:User {uid: $user})-[r:ULTIMATE_PATH]->(:Entity {uid: $lp})
                RETURN r.alignment_score AS score
                """,
                user=_USER_FACADE,
                lp=_LP_FACADE,
            )
            record = await edge.single()
        assert record is not None
        assert record["score"] == pytest.approx(0.375, abs=1e-3)

        # Recommendations derive from the weakest dimension (knowledge = 0.0)
        recs = payload["recommendations"]
        assert recs
        assert recs[0]["type"] == "dimension_knowledge"

    async def test_get_full_status_for_blank_user(self, lifepath_facade, alignment_graph):
        result = await lifepath_facade.get_full_status(_USER_BLANK)

        assert result.is_ok
        status = result.value
        assert status["has_vision"] is False
        assert status["has_designation"] is False
        assert status["alignment"] is None
        assert status["next_step"] == "Express your vision to get started"
        assert status["recommendations"][0]["type"] == "getting_started"

    async def test_get_full_status_after_vision_and_designation(
        self, lifepath_facade, alignment_graph
    ):
        saved = await lifepath_facade.core.save_vision(
            _USER_FACADE, "become someone who ships mindfully", ["mindfulness"]
        )
        assert saved.is_ok
        designated = await lifepath_facade.core.designate_life_path(_USER_FACADE, _LP_FACADE)
        assert designated.is_ok

        result = await lifepath_facade.get_full_status(_USER_FACADE)

        assert result.is_ok
        status = result.value
        assert status["has_vision"] is True
        assert status["has_designation"] is True
        assert status["vision"] is not None
        assert status["vision"]["statement"] == "become someone who ships mindfully"
        assert status["vision"]["captured_at"] is not None  # ISO round-trip survives
        assert status["designation"] is not None
        assert status["designation"]["life_path_uid"] == _LP_FACADE
        assert status["alignment"] is not None
        assert status["alignment"]["life_path_uid"] == _LP_FACADE
        assert status["recommendations"]
        assert status["daily_focus"] is not None

    async def test_get_alignment_via_facade_matches_direct_calculation(
        self, lifepath_facade, alignment_service, alignment_graph
    ):
        facade_result = await lifepath_facade.get_alignment(_USER_RICH)
        direct_result = await alignment_service.calculate_alignment(
            UserContext(user_uid=_USER_RICH)
        )

        assert facade_result.is_ok and direct_result.is_ok
        assert facade_result.value["alignment_score"] == pytest.approx(
            direct_result.value["alignment_score"], abs=1e-6
        )
        assert facade_result.value["dimensions"] == direct_result.value["dimensions"]


class TestWordActionAlignment:
    async def test_without_vision_reports_zero_and_guidance(self, lifepath_facade, alignment_graph):
        result = await lifepath_facade.check_word_action_alignment(
            _USER_BLANK, UserContext(user_uid=_USER_BLANK)
        )

        assert result.is_ok
        alignment = result.value
        assert alignment.alignment_score == pytest.approx(0.0)
        assert any("No vision captured yet" in i for i in alignment.insights)

    async def test_vision_themes_matched_against_context_actions(
        self, lifepath_facade, alignment_graph
    ):
        saved = await lifepath_facade.core.save_vision(
            _USER_FACADE, "a mindful and healthy life", ["mindfulness", "health"]
        )
        assert saved.is_ok

        ctx = UserContext(
            user_uid=_USER_FACADE,
            habit_streaks={"habit_meditation": 4, "habit_workout": 2},
        )
        result = await lifepath_facade.check_word_action_alignment(_USER_FACADE, ctx)

        assert result.is_ok
        alignment = result.value
        assert alignment.alignment_score == pytest.approx(1.0)
        assert set(alignment.matched_themes) == {"mindfulness", "health"}
