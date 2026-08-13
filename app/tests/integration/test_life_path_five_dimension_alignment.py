"""
Real-Neo4j guard for the FIVE-DIMENSION Life Path alignment metric.
===================================================================

``LifePathAlignmentService.calculate_alignment`` — the metric written to
``ULTIMATE_PATH.alignment_score`` and rendered on ``/lifepath``. Not to be
confused with ``AnalyticsLifePathService.calculate_life_path_alignment``, a
separate per-learner substance mean guarded by
``test_life_path_alignment_learner_scope.py``.

**Habits contributed exactly zero to all three dimensions that name them.**
Habits reach knowledge over ``REINFORCES_KNOWLEDGE`` (writer:
``HabitsCoreService``); two queries matched them over ``APPLIES_KNOWLEDGE``, an
edge no habit writer emits, and momentum had no habit arm at all. Neo4j does not
object to an edge type nothing writes — it matches zero rows — so every one of
these returned a plausible number.

The activity dimension therefore INVERTED. ``habit_ratio`` defaulted to 0.5 with
no habits at all, so a learner's first life-path habit moved it *down*:

    no habits at all         habit_ratio 0.5 (default)   activity 0.50
    one aligned habit, bug   habit_ratio 0.0 (0 of 1)    activity 0.20
    one aligned habit, fixed habit_ratio 1.0 (1 of 1)    activity 0.67

⚠ **Asserting that a dimension "changed" is satisfied BY the defect** — 0.50 →
0.20 is a change. Every habit-dependent assertion below therefore pins an exact
value, and ``test_a_first_aligned_habit_raises_every_habit_dependent_dimension``
asserts the DIRECTION on all three at once. Seeding ``APPLIES_KNOWLEDGE`` on a
habit passes against the bug, so nothing here does.

The designation is written by the REAL writer
(``LifePathBackend.designate_life_path``), which promotes ``entity_type`` in
place and leaves the ``:LearningPath`` label alone — the state every one of
these reads has to survive.

See: docs/technical_debt/LIFEPATH_ALIGNMENT_DEBT.md
     core/services/knowledge/user_substance.py (the one weight table)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.ports.query_types import AlignmentDimensions
from core.services.knowledge.user_substance import USER_SUBSTANCE_CHANNELS
from core.services.lifepath.lifepath_alignment_service import LifePathAlignmentService
from core.services.lifepath.lifepath_service import LifePathService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import Errors, Result

# One learner per scenario; each gets its own LearningPath because
# designate_life_path MATCHes entity_type 'learning_path' and flips it in place,
# so a path already designated by someone else can no longer be designated.
USER_BARE = "user_lp5d_bare"
USER_HABIT = "user_lp5d_habit_only"
USER_SIX = "user_lp5d_six_channels"
USER_CAP = "user_lp5d_capped"
USER_OTHER = "user_lp5d_other_learner"

DESIGNATED = {
    USER_BARE: "lp.test.5d.bare",
    USER_HABIT: "lp.test.5d.habit",
    USER_SIX: "lp.test.5d.six",
    USER_CAP: "lp.test.5d.cap",
}

PS_SHARED = "ps.test.5d.shared"
KU_PATH = "ku_test_5d_on_path"
KU_OFF_PATH = "ku_test_5d_off_path"

# (user, count, entity_type, ku, edge) — the production vocabulary per channel.
# Tasks, events and entries share APPLIES_KNOWLEDGE and are told apart by
# entity_type; habits use REINFORCES_KNOWLEDGE, choices INFORMED_BY_KNOWLEDGE,
# principles GROUNDED_IN_KNOWLEDGE.
SEEDED_ACTIVITY = [
    (USER_HABIT, 1, "habit", KU_PATH, "REINFORCES_KNOWLEDGE"),
    (USER_SIX, 1, "task", KU_PATH, "APPLIES_KNOWLEDGE"),
    (USER_SIX, 1, "habit", KU_PATH, "REINFORCES_KNOWLEDGE"),
    (USER_SIX, 1, "event", KU_PATH, "APPLIES_KNOWLEDGE"),
    (USER_SIX, 1, "user_entry", KU_PATH, "APPLIES_KNOWLEDGE"),
    (USER_SIX, 1, "choice", KU_PATH, "INFORMED_BY_KNOWLEDGE"),
    (USER_SIX, 1, "principle", KU_PATH, "GROUNDED_IN_KNOWLEDGE"),
    (USER_CAP, 10, "task", KU_PATH, "APPLIES_KNOWLEDGE"),
    # The tenancy control on the numerator: another learner grinding the very Ku
    # these paths teach must not move anybody else's score.
    (USER_OTHER, 3, "habit", KU_PATH, "REINFORCES_KNOWLEDGE"),
]

# The one weight table's numbers, read from it rather than restated, so a
# deliberate reweighting moves this file's expectations with the source.
W = {channel.name: channel.weight for channel in USER_SUBSTANCE_CHANNELS}
CAPS = {channel.name: channel.cap for channel in USER_SUBSTANCE_CHANNELS}

# Activity blends its two ratios in the table's task:habit proportion (⅓ : ⅔).
HABIT_SHARE = W["habits"] / (W["tasks"] + W["habits"])
TASK_SHARE = 1.0 - HABIT_SHARE


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j):
    """One shared step and Ku; a designated path and a learner per scenario."""
    now = datetime.now(UTC)
    recent = (now - timedelta(days=2)).isoformat()

    async with neo4j_driver.session() as session:
        for uid in (*DESIGNATED, USER_OTHER):
            await session.run("MERGE (u:User {uid: $u})", u=uid)

        await session.run(
            """
            CREATE (ps:Entity:PathStep {uid: $ps, entity_type: 'path_step',
                                        title: 'Shared step', status: 'active'})
            CREATE (on:Entity:Ku {uid: $on, entity_type: 'ku', title: 'On path',
                                  status: 'active'})
            CREATE (off:Entity:Ku {uid: $off, entity_type: 'ku', title: 'Off path',
                                   status: 'active'})
            CREATE (ps)-[:USES_KU]->(on)
            """,
            ps=PS_SHARED,
            on=KU_PATH,
            off=KU_OFF_PATH,
        )

        for lp_uid in DESIGNATED.values():
            await session.run(
                """
                CREATE (lp:Entity:LearningPath {uid: $lp, entity_type: 'learning_path',
                                                title: 'Become a mindful engineer',
                                                status: 'active'})
                WITH lp
                MATCH (ps:Entity {uid: $ps})
                CREATE (lp)-[:HAS_STEP {sequence: 0}]->(ps)
                """,
                lp=lp_uid,
                ps=PS_SHARED,
            )

        for user_uid, count, entity_type, ku_uid, edge in SEEDED_ACTIVITY:
            await session.run(
                f"""
                MATCH (u:User {{uid: $u}}), (k:Entity {{uid: $ku}})
                UNWIND range(1, $count) AS i
                CREATE (a:Entity {{uid: $prefix + toString(i), entity_type: $entity_type,
                                   title: $prefix, status: 'active', user_uid: $u,
                                   created_at: $created, updated_at: $created}})
                MERGE (u)-[:OWNS]->(a)
                MERGE (a)-[:{edge}]->(k)
                """,
                u=user_uid,
                ku=ku_uid,
                count=count,
                prefix=f"{user_uid}_{entity_type}_",
                entity_type=entity_type,
                created=recent,
            )

    # The REAL designation writer, not a hand-seeded promoted state.
    backend = LifePathBackend(Neo4jQueryExecutor(neo4j_driver))
    for user_uid, lp_uid in DESIGNATED.items():
        designated = await backend.designate_life_path(
            user_uid, lp_uid, datetime.now(UTC).isoformat()
        )
        assert designated.is_ok, f"designation failed for {user_uid}: {designated}"

    return neo4j_driver


def _service(driver, *, cross_domain=None) -> LifePathAlignmentService:
    """The service wired the way the composition root wires it."""
    executor = Neo4jQueryExecutor(driver)
    return LifePathAlignmentService(
        backend=LifePathBackend(executor),
        cross_domain_backend=cross_domain
        if cross_domain is not None
        else CrossDomainBackend(executor),
    )


async def _dimensions(driver, user_uid: str) -> AlignmentDimensions:
    result = await _service(driver).calculate_alignment(UserContext(user_uid=user_uid))
    assert result.is_ok, f"alignment failed for {user_uid}: {result}"
    return result.value["dimensions"]


@pytest.mark.asyncio
class TestHabitsCountTowardAlignment:
    """The item-1 defect: habits were worth zero in all three dimensions."""

    async def test_a_first_aligned_habit_raises_every_habit_dependent_dimension(self, graph):
        """The DIRECTION assertion — the one the defect cannot satisfy.

        ``USER_BARE`` and ``USER_HABIT`` hold identical designated paths and
        differ by exactly one habit reinforcing the path's Ku. Under the bug that
        habit lowered activity (0.50 → 0.20) and left knowledge and momentum
        untouched; a test asserting only "the dimension changed" passes on that.
        """
        bare = await _dimensions(graph, USER_BARE)
        habit = await _dimensions(graph, USER_HABIT)

        assert habit["activity"] > bare["activity"], (
            "0.20 vs 0.50 = THE INVERSION: the habit entered the denominator "
            "while the wrong read edge kept it out of the numerator"
        )
        assert habit["knowledge"] > bare["knowledge"], (
            "flat = the knowledge dimension's habit term still never fires"
        )
        assert habit["momentum"] > bare["momentum"], (
            "flat = momentum still has no habit arm and counts tasks only"
        )

    async def test_the_habit_learner_scores_the_exact_expected_dimensions(self, graph):
        """Pinned values, so a fix that merely moves the numbers is not enough."""
        dims = await _dimensions(graph, USER_HABIT)

        # One Ku, no mastery, one habit: min(1.0, 0.0*0.6 + 0.10).
        assert dims["knowledge"] == pytest.approx(W["habits"], abs=1e-3)
        # No tasks (0.0, no data) and 1 of 1 habits aligned, blended ⅓ : ⅔.
        assert dims["activity"] == pytest.approx(HABIT_SHARE, abs=1e-3)
        # A habit committed to this week, nothing the week before.
        assert dims["momentum"] == pytest.approx(0.8, abs=1e-3)

    async def test_a_learner_with_no_activity_scores_zero_not_half(self, graph):
        """Ruling 2: a level with no evidence is 0.0; only momentum stays neutral.

        The 0.5 no-data default is what made the inversion possible — it gave a
        learner who had done nothing a score to fall FROM.
        """
        dims = await _dimensions(graph, USER_BARE)

        assert dims["knowledge"] == pytest.approx(0.0)
        assert dims["activity"] == pytest.approx(0.0), "0.5 = the neutral default is back"
        assert dims["goal"] == pytest.approx(0.0)
        assert dims["principle"] == pytest.approx(0.0)
        assert dims["momentum"] == pytest.approx(0.5), (
            "momentum is a derivative — no trend data really is neutral, and "
            "0.0 here would permanently dock a learner who has just started"
        )

    async def test_momentum_counts_habit_commitments_not_only_tasks(self, graph):
        """The third habit-dependent site, which had no habit arm at all.

        ``USER_HABIT`` owns exactly one activity — a habit — created this week.
        Task-only momentum sees nothing either week and returns the neutral 0.5.
        """
        dims = await _dimensions(graph, USER_HABIT)

        assert dims["momentum"] == pytest.approx(0.8), (
            "0.5 = momentum saw no activity at all, i.e. it is still task-only"
        )


@pytest.mark.asyncio
class TestKnowledgeUsesTheOneWeightTable:
    """The knowledge dimension scores substance from USER_SUBSTANCE_CHANNELS."""

    async def test_all_six_channels_contribute(self, graph):
        """The hand-rolled Cypher knew only tasks and habits.

        ``USER_SIX`` applies the path's single Ku through every channel once, so
        the dimension is the whole table's per-instance weights summed. A reading
        that still knows only two channels lands on 0.15.
        """
        dims = await _dimensions(graph, USER_SIX)

        expected = sum(W.values())
        assert dims["knowledge"] == pytest.approx(expected, abs=1e-3), (
            f"0.15 = tasks and habits only, the two channels the hand-copied "
            f"weights carried; {expected:.2f} = all six, from the table"
        )

    async def test_per_channel_caps_are_applied(self, graph):
        """The hand-rolled sum had no caps — 10 tasks scored 0.50, uncapped.

        ``USER_CAP`` also holds mastery 0.5, so this pins the mastery term at the
        same time: 0.6*0.5 = 0.30, plus the task channel capped at 0.25.
        """
        async with graph.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $u}), (k:Entity {uid: $ku})
                MERGE (u)-[m:MASTERED]->(k) SET m.mastery_score = 0.5
                """,
                u=USER_CAP,
                ku=KU_PATH,
            )

        dims = await _dimensions(graph, USER_CAP)

        expected = 0.6 * 0.5 + CAPS["tasks"]
        assert dims["knowledge"] == pytest.approx(expected, abs=1e-3), (
            f"0.80 = 10 tasks scored uncapped at 0.50; {expected:.2f} = the "
            f"table's 0.25 task cap plus the 0.6 mastery term"
        )

    async def test_another_learners_activity_does_not_move_this_score(self, graph):
        """Tenancy on the numerator, over the very Ku every path here teaches.

        ``USER_OTHER`` owns three habits reinforcing ``KU_PATH``. The channel
        read is anchored on ``(u:User {uid})-[:OWNS]->``, so ``USER_BARE`` must
        still read as having applied nothing.
        """
        dims = await _dimensions(graph, USER_BARE)

        assert dims["knowledge"] == pytest.approx(0.0), (
            "0.30 = another learner's three habits entered this learner's index"
        )


@pytest.mark.asyncio
class TestAlignmentRefusesRatherThanScoringAConfidentZero:
    """A failed or absent read must not be reported as an unlived life path."""

    async def test_a_failed_channel_read_propagates(self, graph):
        """Empty channels score every dimension's substance at 0.0 — plausible,
        persisted onto ULTIMATE_PATH, and wrong."""

        class _FailingChannels:
            async def get_user_knowledge_channels(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        result = await _service(graph, cross_domain=_FailingChannels()).calculate_alignment(
            UserContext(user_uid=USER_SIX)
        )

        assert result.is_error, "a failed channel read was scored as 'you applied nothing'"

    async def test_an_unwired_channel_source_refuses(self, graph):
        """Without the channel source the knowledge dimension would be mastery
        alone reported under a substance-weighted heading."""
        service = LifePathAlignmentService(
            backend=LifePathBackend(Neo4jQueryExecutor(graph)),
        )

        result = await service.calculate_alignment(UserContext(user_uid=USER_SIX))

        assert result.is_error, "scored the substance-weighted metric with no substance source"

    async def test_a_user_without_a_designation_is_not_an_error(self, graph):
        """No life path is a real state, not a failed metric."""
        result = await _service(graph).calculate_alignment(UserContext(user_uid=USER_OTHER))

        assert result.is_ok
        assert result.value["life_path_uid"] is None
        assert result.value["alignment_score"] == pytest.approx(0.0)
        assert result.value["alignment_level"] == "undefined"

    async def test_the_facade_does_not_swallow_a_failed_scoring_run(self, graph):
        """The refusal has to survive the layer the UI actually calls.

        A service that fails correctly buys nothing if the facade reports the
        failure as success. ``designate_and_calculate`` returned ``Result.ok``
        with an EMPTY alignment payload and no write to ``ULTIMATE_PATH``, and
        ``get_full_status`` returned ``has_designation=True`` with
        ``alignment=None`` — a state indistinguishable from the genuine
        no-designation case, produced by a database outage.
        """

        class _FailingChannels:
            async def get_user_knowledge_channels(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        executor = Neo4jQueryExecutor(graph)
        facade = LifePathService(
            backend=LifePathBackend(executor),
            cross_domain_backend=_FailingChannels(),
        )

        designated = await facade.designate_and_calculate(USER_SIX, DESIGNATED[USER_SIX])
        assert designated.is_error, (
            "designate_and_calculate reported success while scoring nothing — "
            "the method is named for both halves of what it does"
        )

        status = await facade.get_full_status(USER_SIX)
        assert status.is_error, (
            "get_full_status returned a designated learner with alignment=None, "
            "which reads as 'no life path' rather than as an outage"
        )
