"""
Integration tests for LpIntelligenceService's consolidated methods
(validation / blockers / optimal path / adaptive) via the LpService facade.

These queries were rewritten against the REAL graph vocabulary in this PR:
the prior versions read a phantom ``step.knowledge_uid`` node property
(never written — KUs hang off steps via USES_KU edges), traversed
REQUIRES_KNOWLEDGE in the inverted direction, and referenced out-of-scope
variables (a Cypher compile error — `Variable path not defined`). These
tests pin the corrected behavior against a seeded testcontainer graph.

Graph seeded here (sanctioned vocabulary only):

  GOOD path: step1→USES_KU→alpha, step2→USES_KU→beta, beta─REQUIRES→alpha
             (prerequisite taught before its dependent — valid ordering)
  BAD path:  step1→USES_KU→delta, step2→USES_KU→gamma, delta─REQUIRES→gamma
             (step 1 depends on knowledge taught in step 2 — invalid)
  MULTI path: one step→USES_KU→{multi_a, multi_b}, multi_b─REQUIRES→gamma
             (the PathStep norm — a step composes 2+ KUs; counts as ONE step)
  Adaptive:  alpha─ENABLES{conf .9, str .8, gap .2}→next, next─REQUIRES→alpha
             alpha─ENABLES{conf .3, str .3, gap .9}→hard
  Optimal:   two domain-scoped paths, one with its prerequisite mastered
             (readiness 1.0) and one blocked (readiness 0.0)
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

_NOVICE = "user_lpintel_novice"  # no mastery at all
_ADEPT = "user_lpintel_adept"  # MASTERED: alpha, gamma, opt_prereq

_LP_GOOD = "lp.test.lpintel.good"
_LP_BAD = "lp.test.lpintel.bad"
_LP_MULTI = "lp.test.lpintel.multi"
_LP_OPT_READY = "lp.test.lpintel.opt.ready"
_LP_OPT_BLOCKED = "lp.test.lpintel.opt.blocked"
_LP_SOLO = "lp.test.lpintel.solo"  # 1 step, 1 KU, no prerequisites (depth 0)
_LP_DEEP = "lp.test.lpintel.deep"  # 1 step, 1 KU, 2-hop prerequisite chain
_LP_PRACTICE = "lp.test.lpintel.practice"  # 3 steps: full / partial / no practice
_LP_PRACTICE_FULL = "lp.test.lpintel.practice.full_path"  # 1 fully-practiced step

# Practice edge → target node, one activity node per domain (shared across the
# practice paths; MERGE-idempotent). A step wired to all six has complete practice.
_PRACTICE_EDGES = {
    "habits": "BUILDS_HABIT",
    "tasks": "ASSIGNS_TASK",
    "events": "SCHEDULES_EVENT",
    "goals": "SUPPORTS_GOAL",
    "principles": "GUIDED_BY_PRINCIPLE",
    "choices": "INFORMS_CHOICE",
}
_PRACTICE_TARGETS = {
    "habits": "act_lpintel_habit",
    "tasks": "act_lpintel_task",
    "events": "act_lpintel_event",
    "goals": "act_lpintel_goal",
    "principles": "act_lpintel_principle",
    "choices": "act_lpintel_choice",
}
_PS_PRACTICE_FULL = "ps.test.lpintel.practice.full"
_PS_PRACTICE_PARTIAL = "ps.test.lpintel.practice.partial"
_PS_PRACTICE_NONE = "ps.test.lpintel.practice.none"
_PS_PRACTICE_SOLO = "ps.test.lpintel.practice.solo"

# Domain used ONLY to scope the optimal-path query to this file's seeds.
# 'transcription' is a valid Domain member no other integration seed uses.
_OPT_DOMAIN = "transcription"

_KU_ALPHA = "ku_lpintel_alpha"
_KU_BETA = "ku_lpintel_beta"
_KU_GAMMA = "ku_lpintel_gamma"
_KU_DELTA = "ku_lpintel_delta"
_KU_NEXT = "ku_lpintel_next"
_KU_HARD = "ku_lpintel_hard"
_KU_ISLAND = "ku_lpintel_island"
_KU_DEEP_A = "ku_lpintel_deep_a"
_KU_DEEP_B = "ku_lpintel_deep_b"
_KU_DEEP_C = "ku_lpintel_deep_c"

_UIDS = [
    _NOVICE,
    _ADEPT,
    _LP_GOOD,
    _LP_BAD,
    _LP_MULTI,
    _LP_OPT_READY,
    _LP_OPT_BLOCKED,
    _LP_SOLO,
    _LP_DEEP,
    _LP_PRACTICE,
    _LP_PRACTICE_FULL,
    "ps.test.lpintel.good.1",
    "ps.test.lpintel.good.2",
    "ps.test.lpintel.bad.1",
    "ps.test.lpintel.bad.2",
    "ps.test.lpintel.multi.1",
    "ps.test.lpintel.opt.a",
    "ps.test.lpintel.opt.b",
    "ps.test.lpintel.solo.1",
    "ps.test.lpintel.deep.1",
    _PS_PRACTICE_FULL,
    _PS_PRACTICE_PARTIAL,
    _PS_PRACTICE_NONE,
    _PS_PRACTICE_SOLO,
    *_PRACTICE_TARGETS.values(),
    _KU_ALPHA,
    _KU_BETA,
    _KU_GAMMA,
    _KU_DELTA,
    _KU_NEXT,
    _KU_HARD,
    _KU_ISLAND,
    _KU_DEEP_A,
    _KU_DEEP_B,
    _KU_DEEP_C,
    "ku_lpintel_multi_a",
    "ku_lpintel_multi_b",
    "ku_lpintel_opt_a",
    "ku_lpintel_opt_b",
    "ku_lpintel_opt_prereq",
    "ku_lpintel_opt_unmet",
]


async def _seed_path(session, lp_uid: str, title: str, steps: list[tuple[str, str]], **props):
    """Create an LP with HAS_STEP{sequence}→PathStep→USES_KU→Ku chains."""
    extra = "".join(f", lp.{k} = ${k}" for k in props)
    await session.run(
        f"""
        MERGE (lp:Entity:LearningPath {{uid: $uid}})
        SET lp.title = $title, lp.entity_type = 'learning_path', lp.status = 'active'{extra}
        """,
        uid=lp_uid,
        title=title,
        **props,
    )
    for sequence, (ps_uid, ku_uid) in enumerate(steps, start=1):
        await session.run(
            """
            MATCH (lp:Entity {uid: $lp_uid})
            MERGE (ps:Entity:PathStep {uid: $ps_uid})
            SET ps.title = $ps_uid, ps.entity_type = 'path_step', ps.status = 'active'
            MERGE (lp)-[:HAS_STEP {sequence: $sequence}]->(ps)
            WITH ps
            MATCH (ku:Entity {uid: $ku_uid})
            MERGE (ps)-[:USES_KU]->(ku)
            """,
            lp_uid=lp_uid,
            ps_uid=ps_uid,
            ku_uid=ku_uid,
            sequence=sequence,
        )


async def _seed_practice(session, ps_uid: str, domains):
    """Wire the given practice domains (BUILDS_HABIT/ASSIGNS_TASK/…) onto a step.

    Each domain gets one activity target node (shared, MERGE-idempotent). A step
    seeded with all six domains has complete practice; fewer leaves a gap.
    """
    for domain in domains:
        await session.run(
            f"""
            MERGE (t:Entity {{uid: $target}})
            ON CREATE SET t.status = 'active'
            WITH t
            MATCH (ps:Entity {{uid: $ps_uid}})
            MERGE (ps)-[:{_PRACTICE_EDGES[domain]}]->(t)
            """,
            ps_uid=ps_uid,
            target=_PRACTICE_TARGETS[domain],
        )


@pytest_asyncio.fixture(loop_scope="session")
async def lpintel_graph(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)

        for user_uid in (_NOVICE, _ADEPT):
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=user_uid)

        for ku_uid in (
            _KU_ALPHA,
            _KU_BETA,
            _KU_GAMMA,
            _KU_DELTA,
            _KU_NEXT,
            _KU_HARD,
            _KU_ISLAND,
            _KU_DEEP_A,
            _KU_DEEP_B,
            _KU_DEEP_C,
            "ku_lpintel_multi_a",
            "ku_lpintel_multi_b",
            "ku_lpintel_opt_a",
            "ku_lpintel_opt_b",
            "ku_lpintel_opt_prereq",
            "ku_lpintel_opt_unmet",
        ):
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.title = $uid, k.entity_type = 'ku', k.status = 'active'
                """,
                uid=ku_uid,
            )

        await _seed_path(
            session,
            _LP_GOOD,
            "LP Intel Good Ordering",
            [("ps.test.lpintel.good.1", _KU_ALPHA), ("ps.test.lpintel.good.2", _KU_BETA)],
        )
        await _seed_path(
            session,
            _LP_BAD,
            "LP Intel Bad Ordering",
            [("ps.test.lpintel.bad.1", _KU_DELTA), ("ps.test.lpintel.bad.2", _KU_GAMMA)],
        )
        # One step composing TWO KUs (the PathStep norm — "every Ps = 2+ Kus")
        await _seed_path(
            session,
            _LP_MULTI,
            "LP Intel Multi-KU Step",
            [("ps.test.lpintel.multi.1", "ku_lpintel_multi_a")],
        )
        await session.run(
            """
            MATCH (ps:Entity {uid: 'ps.test.lpintel.multi.1'}),
                  (ku:Entity {uid: 'ku_lpintel_multi_b'})
            MERGE (ps)-[:USES_KU]->(ku)
            """
        )

        await _seed_path(
            session,
            _LP_OPT_READY,
            "LP Intel Optimal Ready",
            [("ps.test.lpintel.opt.a", "ku_lpintel_opt_a")],
            domain=_OPT_DOMAIN,
            estimated_hours=10,
        )
        await _seed_path(
            session,
            _LP_OPT_BLOCKED,
            "LP Intel Optimal Blocked",
            [("ps.test.lpintel.opt.b", "ku_lpintel_opt_b")],
            domain=_OPT_DOMAIN,
            estimated_hours=20,
        )
        # Scope isolation pair: SOLO (1 KU, no prereqs → depth 0) vs DEEP (1 KU
        # whose prereq chain runs two hops → depth 2). Same breadth, so any
        # complexity gap between them is purely the depth axis.
        await _seed_path(
            session, _LP_SOLO, "LP Intel Solo", [("ps.test.lpintel.solo.1", _KU_ISLAND)]
        )
        await _seed_path(
            session, _LP_DEEP, "LP Intel Deep Chain", [("ps.test.lpintel.deep.1", _KU_DEEP_C)]
        )

        # Practice-gap path: three steps with descending practice completeness —
        # full (all six activity domains → 1.0), partial (habit+task → 2/6), and
        # none (no practice edges → 0.0). Each step USES_KU alpha (KU coverage is
        # irrelevant to practice — the practice tests only read practice edges).
        await _seed_path(
            session,
            _LP_PRACTICE,
            "LP Intel Practice",
            [
                (_PS_PRACTICE_FULL, _KU_ALPHA),
                (_PS_PRACTICE_PARTIAL, _KU_ALPHA),
                (_PS_PRACTICE_NONE, _KU_ALPHA),
            ],
        )
        await _seed_practice(session, _PS_PRACTICE_FULL, _PRACTICE_EDGES.keys())
        await _seed_practice(session, _PS_PRACTICE_PARTIAL, ("habits", "tasks"))

        # All-complete path (one fully-practiced step) — the zero-gap case.
        await _seed_path(
            session,
            _LP_PRACTICE_FULL,
            "LP Intel Practice Full",
            [(_PS_PRACTICE_SOLO, _KU_ALPHA)],
        )
        await _seed_practice(session, _PS_PRACTICE_SOLO, _PRACTICE_EDGES.keys())

        # Prerequisite edges — sanctioned direction: dependent → prerequisite
        for dependent, prerequisite in (
            (_KU_BETA, _KU_ALPHA),
            (_KU_DELTA, _KU_GAMMA),
            (_KU_NEXT, _KU_ALPHA),
            ("ku_lpintel_multi_b", _KU_GAMMA),
            ("ku_lpintel_opt_a", "ku_lpintel_opt_prereq"),
            ("ku_lpintel_opt_b", "ku_lpintel_opt_unmet"),
            (_KU_DEEP_C, _KU_DEEP_B),  # two-hop chain: deep_c → deep_b → deep_a
            (_KU_DEEP_B, _KU_DEEP_A),
        ):
            await session.run(
                """
                MATCH (a:Entity {uid: $dep}), (b:Entity {uid: $pre})
                MERGE (a)-[:REQUIRES_KNOWLEDGE]->(b)
                """,
                dep=dependent,
                pre=prerequisite,
            )

        # Adaptive enablement edges with metadata
        await session.run(
            """
            MATCH (alpha:Entity {uid: $alpha}), (next:Entity {uid: $next})
            MERGE (alpha)-[r:ENABLES_KNOWLEDGE]->(next)
            SET r.typical_learning_order = 1, r.confidence = 0.9,
                r.strength = 0.8, r.difficulty_gap = 0.2
            """,
            alpha=_KU_ALPHA,
            next=_KU_NEXT,
        )
        await session.run(
            """
            MATCH (alpha:Entity {uid: $alpha}), (hard:Entity {uid: $hard})
            MERGE (alpha)-[r:ENABLES_KNOWLEDGE]->(hard)
            SET r.confidence = 0.3, r.strength = 0.3, r.difficulty_gap = 0.9
            """,
            alpha=_KU_ALPHA,
            hard=_KU_HARD,
        )

        # Adept's masteries
        for ku_uid in (_KU_ALPHA, _KU_GAMMA, "ku_lpintel_opt_prereq"):
            await session.run(
                """
                MATCH (u:User {uid: $user}), (k:Entity {uid: $ku})
                MERGE (u)-[:MASTERED {mastery_score: 0.9}]->(k)
                """,
                user=_ADEPT,
                ku=ku_uid,
            )

    yield {"good": _LP_GOOD, "bad": _LP_BAD}

    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


class TestValidatePathPrerequisites:
    async def test_well_ordered_path_is_valid(self, services, lpintel_graph):
        result = await services.lp.validate_path_prerequisites(_LP_GOOD)

        assert result.is_ok, f"validation failed: {result.error}"
        validation = result.value
        assert validation["is_valid"] is True
        assert validation["total_steps"] == 2, (
            "both steps must be validated — the first step has no earlier steps "
            "and used to be silently dropped from the results"
        )
        assert validation["steps_with_issues"] == 0
        assert validation["issues"] == []

    async def test_inverted_path_flags_first_step(self, services, lpintel_graph):
        result = await services.lp.validate_path_prerequisites(_LP_BAD)

        assert result.is_ok
        validation = result.value
        assert validation["is_valid"] is False
        assert validation["total_steps"] == 2
        assert validation["steps_with_issues"] == 1

        issue = validation["issues"][0]
        assert issue["sequence"] == 1
        assert issue["knowledge_uids"] == [_KU_DELTA]
        assert issue["unmet_prerequisites"] == [_KU_GAMMA]
        assert any("Reorder steps" in r for r in validation["recommendations"])

    async def test_multi_ku_step_counts_as_one_step(self, services, lpintel_graph):
        """A step composing several KUs is ONE step, not one per KU —
        total_steps/steps_with_issues derive from row counts (Codex P2)."""
        result = await services.lp.validate_path_prerequisites(_LP_MULTI)

        assert result.is_ok
        validation = result.value
        assert validation["total_steps"] == 1
        assert validation["steps_with_issues"] == 1

        issue = validation["issues"][0]
        assert set(issue["knowledge_uids"]) == {"ku_lpintel_multi_a", "ku_lpintel_multi_b"}
        # multi_b requires gamma, which no earlier step teaches
        assert issue["unmet_prerequisites"] == [_KU_GAMMA]

    async def test_unknown_path_is_trivially_valid(self, services, lpintel_graph):
        result = await services.lp.validate_path_prerequisites("lp.test.lpintel.ghost")

        assert result.is_ok
        assert result.value["total_steps"] == 0
        assert result.value["is_valid"] is True


class TestIdentifyPathBlockers:
    async def test_unmastered_prerequisite_blocks(self, services, lpintel_graph):
        result = await services.lp.identify_path_blockers(_LP_BAD, _NOVICE)

        assert result.is_ok
        analysis = result.value
        assert analysis["status"] == "blocked"
        assert analysis["blocker_count"] == 1
        assert analysis["can_progress"] is False
        assert analysis["total_steps"] == 2

        first = analysis["first_blocker"]
        assert first["sequence"] == 1
        assert first["blocking_prerequisites"] == [_KU_GAMMA]
        assert f"Focus on mastering: {_KU_GAMMA}" in analysis["recommendations"]

    async def test_mastered_prerequisite_unblocks(self, services, lpintel_graph):
        result = await services.lp.identify_path_blockers(_LP_BAD, _ADEPT)

        assert result.is_ok
        analysis = result.value
        assert analysis["status"] == "ready"
        assert analysis["blocker_count"] == 0
        assert analysis["can_progress"] is True
        assert "No blockers - continue with next step!" in analysis["recommendations"]

    async def test_multi_ku_step_is_one_blocker_entry(self, services, lpintel_graph):
        """The per-KU fan-out must collapse: one blocked multi-KU step is one
        entry in blocked_steps and total_steps counts steps, not KUs."""
        result = await services.lp.identify_path_blockers(_LP_MULTI, _NOVICE)

        assert result.is_ok
        analysis = result.value
        assert analysis["total_steps"] == 1
        assert analysis["blocker_count"] == 1
        first = analysis["first_blocker"]
        assert set(first["knowledge_uids"]) == {"ku_lpintel_multi_a", "ku_lpintel_multi_b"}
        assert first["blocking_prerequisites"] == [_KU_GAMMA]

    async def test_unknown_path_defaults_to_ready(self, services, lpintel_graph):
        result = await services.lp.identify_path_blockers("lp.test.lpintel.ghost", _NOVICE)

        assert result.is_ok
        assert result.value["status"] == "ready"
        assert result.value["blocker_count"] == 0


class TestOptimalPathRecommendation:
    async def test_readiness_orders_recommendations(self, services, lpintel_graph):
        result = await services.lp.get_optimal_path_recommendation(_ADEPT, goal_domain=_OPT_DOMAIN)

        assert result.is_ok
        rec = result.value
        assert rec["recommended_path_uid"] == _LP_OPT_READY
        assert rec["path_name"] == "LP Intel Optimal Ready"
        assert rec["readiness_score"] == pytest.approx(1.0)
        assert rec["reason"] == "High readiness - prerequisites mostly met"
        assert [a["path"]["uid"] for a in rec["alternatives"]] == [_LP_OPT_BLOCKED]
        assert rec["alternatives"][0]["readiness_score"] == pytest.approx(0.0)

    async def test_novice_gets_low_readiness_reason(self, services, lpintel_graph):
        result = await services.lp.get_optimal_path_recommendation(_NOVICE, goal_domain=_OPT_DOMAIN)

        assert result.is_ok
        rec = result.value
        # Tie at readiness 0.0 → estimated_hours ASC breaks it
        assert rec["recommended_path_uid"] == _LP_OPT_READY
        assert rec["readiness_score"] == pytest.approx(0.0)
        assert rec["reason"] == "Low readiness - build foundations first"

    async def test_completed_enrollment_is_excluded(self, services, lpintel_graph, neo4j_driver):
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user}), (lp:Entity {uid: $lp})
                MERGE (u)-[:ENROLLED_IN {status: 'completed'}]->(lp)
                """,
                user=_ADEPT,
                lp=_LP_OPT_READY,
            )

        result = await services.lp.get_optimal_path_recommendation(_ADEPT, goal_domain=_OPT_DOMAIN)

        assert result.is_ok
        assert result.value["recommended_path_uid"] == _LP_OPT_BLOCKED

    async def test_no_matching_paths_recommends_nothing(self, services, lpintel_graph):
        result = await services.lp.get_optimal_path_recommendation(_NOVICE, goal_domain="system")

        assert result.is_ok
        rec = result.value
        assert rec["recommended_path_uid"] is None
        assert rec["alternatives"] == []


class TestAdaptiveOperations:
    async def test_find_learning_sequence_walks_enablement(self, services, lpintel_graph):
        result = await services.lp.find_learning_sequence(_KU_ALPHA, _KU_NEXT)

        assert result.is_ok
        assert result.value == [_KU_ALPHA, _KU_NEXT]

    async def test_find_learning_sequence_no_route_is_empty(self, services, lpintel_graph):
        result = await services.lp.find_learning_sequence(_KU_ALPHA, _KU_ISLAND)

        assert result.is_ok
        assert result.value == []

    async def test_next_adaptive_step_prefers_confident_ready_edge(self, services, lpintel_graph):
        result = await services.lp.get_next_adaptive_step(_KU_ALPHA, _ADEPT)

        assert result.is_ok
        # 'next' scores 0.9*0.6 + 0.8*0.4 = 0.86 vs 'hard' 0.3 — and its
        # prerequisite (alpha) is mastered, so readiness passes the 0.8 gate
        assert result.value == _KU_NEXT

    async def test_next_adaptive_step_without_enablement_is_empty(self, services, lpintel_graph):
        result = await services.lp.get_next_adaptive_step(_KU_BETA, _NOVICE)

        assert result.is_ok
        assert result.value == ""

    async def test_recommended_steps_filter_difficulty(self, services, lpintel_graph):
        result = await services.lp.get_recommended_path_steps(_ADEPT)

        assert result.is_ok
        uids = [r["uid"] for r in result.value]
        assert uids == [_KU_NEXT], "hard edge (difficulty 0.9) must be filtered at 0.5"
        step = result.value[0]
        assert step["title"] == _KU_NEXT
        assert step["prerequisite_readiness"] == pytest.approx(1.0)
        assert step["difficulty_gap"] == pytest.approx(0.2)

        relaxed = await services.lp.get_recommended_path_steps(_ADEPT, max_difficulty=1.0)
        assert relaxed.is_ok
        assert [r["uid"] for r in relaxed.value] == [_KU_NEXT, _KU_HARD]

    async def test_recommended_steps_exclude_in_progress(
        self, services, lpintel_graph, neo4j_driver
    ):
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user}), (k:Entity {uid: $ku})
                MERGE (u)-[:IN_PROGRESS]->(k)
                """,
                user=_ADEPT,
                ku=_KU_NEXT,
            )

        result = await services.lp.get_recommended_path_steps(_ADEPT)

        assert result.is_ok
        assert [r["uid"] for r in result.value] == []

    async def test_recommended_steps_for_user_without_mastery(self, services, lpintel_graph):
        result = await services.lp.get_recommended_path_steps(_NOVICE)

        assert result.is_ok
        assert result.value == []


class TestProtocolMethods:
    async def test_performance_analytics_counts_paths(self, services, lpintel_graph):
        result = await services.lp.intelligence.get_performance_analytics(_ADEPT)

        assert result.is_ok, f"analytics failed: {result.error}"
        analytics = result.value
        assert analytics["user_uid"] == _ADEPT
        assert analytics["period_days"] == 30
        assert analytics["total_learning_paths"] >= 4  # this file seeds four
        assert analytics["analytics"]["total"] == analytics["total_learning_paths"]

    async def test_domain_insights_reads_real_path(self, services, lpintel_graph):
        result = await services.lp.intelligence.get_domain_insights(_LP_GOOD)

        assert result.is_ok, f"insights failed: {result.error}"
        insights = result.value
        assert insights["lp_uid"] == _LP_GOOD
        assert insights["lp_title"] == "LP Intel Good Ordering"

    async def test_domain_insights_unknown_path_is_not_found(self, services, lpintel_graph):
        from core.utils.result_simplified import ErrorCategory

        result = await services.lp.intelligence.get_domain_insights("lp.test.lpintel.ghost")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND


class TestKnowledgeScope:
    async def test_scope_counts_steps_and_unique_kus(self, services, lpintel_graph):
        result = await services.lp.analyze_path_knowledge_scope(_LP_GOOD)

        assert result.is_ok, f"scope failed: {result.error}"
        scope = result.value
        assert scope["path_uid"] == _LP_GOOD
        assert scope["total_steps"] == 2
        assert scope["total_unique_kus"] == 2
        assert scope["kus_per_step"] == pytest.approx(1.0)
        assert scope["max_prerequisite_depth"] == 1  # beta → alpha
        assert scope["all_knowledge_uids"] == [_KU_ALPHA, _KU_BETA]  # deduped + sorted
        assert 0.0 <= scope["complexity_score"] <= 1.0
        # GOOD's steps carry no practice edges → real 0.0 coverage (folded in,
        # not None: ps.intelligence is wired, the steps simply have no practice).
        assert scope["practice_coverage"] == pytest.approx(0.0)

    async def test_multi_ku_step_counts_kus_not_pairs(self, services, lpintel_graph):
        """A step composing two KUs is ONE step with two unique KUs — the
        (step, ku) fan-out must not inflate total_steps (the PathStep norm)."""
        result = await services.lp.analyze_path_knowledge_scope(_LP_MULTI)

        assert result.is_ok
        scope = result.value
        assert scope["total_steps"] == 1
        assert scope["total_unique_kus"] == 2
        assert scope["kus_per_step"] == pytest.approx(2.0)
        assert scope["all_knowledge_uids"] == ["ku_lpintel_multi_a", "ku_lpintel_multi_b"]

    async def test_prerequisite_depth_measures_longest_chain(self, services, lpintel_graph):
        solo = await services.lp.analyze_path_knowledge_scope(_LP_SOLO)
        deep = await services.lp.analyze_path_knowledge_scope(_LP_DEEP)

        assert solo.is_ok and deep.is_ok
        assert solo.value["max_prerequisite_depth"] == 0
        assert deep.value["max_prerequisite_depth"] == 2  # deep_c → deep_b → deep_a
        # The path only TEACHES deep_c; its prerequisites are not path coverage.
        assert deep.value["total_unique_kus"] == 1
        assert deep.value["all_knowledge_uids"] == [_KU_DEEP_C]

    async def test_complexity_rises_with_prerequisite_depth(self, services, lpintel_graph):
        """SOLO and DEEP have identical breadth (1 KU); DEEP's deeper prereq
        chain must make it strictly more complex — isolating the depth axis so
        the assertion holds regardless of how the blend weights are tuned."""
        solo = await services.lp.analyze_path_knowledge_scope(_LP_SOLO)
        deep = await services.lp.analyze_path_knowledge_scope(_LP_DEEP)

        assert solo.is_ok and deep.is_ok
        assert deep.value["complexity_score"] > solo.value["complexity_score"]

    async def test_broader_deeper_path_is_more_complex(self, services, lpintel_graph):
        # GOOD is both broader (2 KUs vs 1) and deeper (depth 1 vs 0) than SOLO,
        # so it is strictly more complex on both axes at once.
        good = await services.lp.analyze_path_knowledge_scope(_LP_GOOD)
        solo = await services.lp.analyze_path_knowledge_scope(_LP_SOLO)

        assert good.is_ok and solo.is_ok
        assert good.value["complexity_score"] > solo.value["complexity_score"]

    async def test_unknown_path_is_not_found(self, services, lpintel_graph):
        from core.utils.result_simplified import ErrorCategory

        result = await services.lp.analyze_path_knowledge_scope("lp.test.lpintel.ghost")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND

    async def test_scope_folds_in_practice_coverage(self, services, lpintel_graph):
        """practice_coverage on the scope dict is the path's mean per-step
        practice completeness — the same number identify_practice_gaps reports."""
        result = await services.lp.analyze_path_knowledge_scope(_LP_PRACTICE)

        assert result.is_ok
        # full 1.0 + partial 2/6 + none 0.0, over 3 steps = 4/9
        assert result.value["practice_coverage"] == pytest.approx(4 / 9, abs=1e-3)


class TestPracticeGaps:
    async def test_identifies_partial_and_empty_steps(self, services, lpintel_graph):
        result = await services.lp.identify_practice_gaps(_LP_PRACTICE)

        assert result.is_ok, f"practice gaps failed: {result.error}"
        analysis = result.value
        assert analysis["path_uid"] == _LP_PRACTICE
        assert analysis["total_steps"] == 3
        assert analysis["steps_with_gaps"] == 2  # partial + none (full is complete)
        assert analysis["overall_practice_coverage"] == pytest.approx(4 / 9, abs=1e-3)

        gaps_by_uid = {g["step_uid"]: g for g in analysis["gaps"]}
        assert set(gaps_by_uid) == {_PS_PRACTICE_PARTIAL, _PS_PRACTICE_NONE}
        assert _PS_PRACTICE_FULL not in gaps_by_uid  # complete step is not a gap

        partial = gaps_by_uid[_PS_PRACTICE_PARTIAL]
        assert partial["practice_completeness"] == pytest.approx(1 / 3, abs=1e-3)
        # habits + tasks present; the other four domains missing, in canonical order
        assert partial["missing_types"] == ["events", "goals", "principles", "choices"]

        none = gaps_by_uid[_PS_PRACTICE_NONE]
        assert none["practice_completeness"] == pytest.approx(0.0)
        assert none["missing_types"] == list(_PRACTICE_TARGETS.keys())  # all six

    async def test_recommendations_flag_zero_practice_step(self, services, lpintel_graph):
        result = await services.lp.identify_practice_gaps(_LP_PRACTICE)

        assert result.is_ok
        recommendations = result.value["recommendations"]
        assert any("2 of 3 steps" in r for r in recommendations)
        # only the fully-empty step earns a "no practice at all" callout
        no_practice_lines = [r for r in recommendations if "no practice at all" in r]
        assert len(no_practice_lines) == 1
        assert _PS_PRACTICE_NONE in no_practice_lines[0]

    async def test_fully_practiced_path_has_no_gaps(self, services, lpintel_graph):
        result = await services.lp.identify_practice_gaps(_LP_PRACTICE_FULL)

        assert result.is_ok
        analysis = result.value
        assert analysis["total_steps"] == 1
        assert analysis["steps_with_gaps"] == 0
        assert analysis["gaps"] == []
        assert analysis["overall_practice_coverage"] == pytest.approx(1.0)
        assert analysis["recommendations"] == ["All 1 steps have complete practice opportunities."]

    async def test_unknown_path_is_not_found(self, services, lpintel_graph):
        from core.utils.result_simplified import ErrorCategory

        result = await services.lp.identify_practice_gaps("lp.test.lpintel.ghost")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
