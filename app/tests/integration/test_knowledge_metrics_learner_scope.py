"""
Real-Neo4j guard for the learner scope of the Layer-0 knowledge metrics.
=======================================================================

``AnalyticsMetricsService.calculate_knowledge_metrics`` used to try two ways of
fetching "the user's knowledge units", and **both** were dead:

1. ``getattr(self.ku_service, "backend", None)`` — the wired service is
   ``PsService``, which stores its backend as ``self.repo``. The attribute is
   absent, so the ``find_by_date_range`` branch never executed. Had it run, it
   would have emitted ``n.user_uid = $user_uid`` against ownerless curriculum
   and matched zero rows.
2. The fallback then called ``self.ku_service.list_by_user(...)``, a method
   neither ``PsService`` nor ``KuService`` defines. The ``AttributeError`` was
   swallowed by the method's own exception handler, so the metric returned
   ``Result.fail`` on **every** call rather than anything wrong-looking.

Note what the obvious assertion would miss. "Seed a learner and assert the
result is non-empty" passes against a query that returns the whole 25-step
corpus, and passes against one that counts a step twice because the learner
holds it by two engagement edges. So every test here pins the **identities**
and the exact counts:

* ``ENGAGED_IN_PROGRESS`` / ``ENGAGED_MASTERED`` — in window, must appear.
* ``ENGAGED_BOTH`` — held by two edges, must appear **once** (a missing
  aggregation shows up as 4 units, not 3).
* ``ENGAGED_OUT_OF_WINDOW`` — engaged 200 days ago, must be excluded.
* ``VIEWED_ONLY`` — VIEWED is not uptake, must be excluded.
* ``UNTOUCHED`` — the corpus control; its presence means the scope collapsed
  to "all path steps".
* ``OTHER_USERS_STEP`` — engaged by a different learner; the tenancy control.

The window is keyed on the LEARNER's engagement timestamp rather than the
node's ``updated_at``, so ``ENGAGED_OUT_OF_WINDOW`` carries a *fresh*
``updated_at`` and a stale edge: a "fix" that windowed on the node would admit
it and fail at 4.

**The MAGNITUDES are per-learner too, since 2026-08-12.** They were not: the
score came from ``Curriculum.substance_score()``, which reads counters
``increment_substance`` writes onto the SHARED node with no ``user_uid``. The
selection was one learner's, every number on it was six learners'.

That is what the seeding below is shaped around. Each in-window step carries
NODE counters (the global figure) that DISAGREE with the learner's own activity
channels, so the two readings are never the same number and no assertion here
can pass against both implementations:

    step                  node counters → global    learner's channels → personal
    ENGAGED_IN_PROGRESS   3 habits          0.30     3 habits + 2 tasks     0.40
    ENGAGED_MASTERED      3 habits          0.30     1 habit                0.10
    ENGAGED_BOTH          3h + 5t + 5e      0.80     nothing                0.00

``ENGAGED_BOTH`` is the sharpest form of the defect: material other learners
have EMBODIED, which this learner opened and never applied. It must report as
theoretical for them, and 0.80/"embodied" is the pre-fix answer.

The per-learner score is computed from the six ``UserContext`` activity→
knowledge maps, over the Kus each step teaches (USES_KU), so the fixture links
Kus and the stub user service supplies the maps.

See: adapters/persistence/neo4j/backends/curriculum_backends.py (_ENGAGEMENT_EDGES)
     core/services/knowledge/user_substance.py (the one weight table)
     scripts/publication_gate_registry.py (both surfaces are USER_STATE)
"""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
from core.services.ps.ps_intelligence_service import PsIntelligenceService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

USER = "user_knowledge_scope"
OTHER_USER = "user_knowledge_scope_other"

ENGAGED_IN_PROGRESS = "ps_engaged_in_progress"
ENGAGED_MASTERED = "ps_engaged_mastered"
ENGAGED_BOTH = "ps_engaged_both"
ENGAGED_OUT_OF_WINDOW = "ps_engaged_stale"
VIEWED_ONLY = "ps_viewed_only"
UNTOUCHED = "ps_untouched"
OTHER_USERS_STEP = "ps_other_users"

# The three steps that must come back for USER in a 30-day window.
EXPECTED_IN_WINDOW = {ENGAGED_IN_PROGRESS, ENGAGED_MASTERED, ENGAGED_BOTH}

# One Ku per in-window step, so a step's personal substance is its Ku's.
KU_DEEP = "ku_learner_applied_deeply"  # 3 habits + 2 tasks -> 0.30 + 0.10
KU_LIGHT = "ku_learner_applied_once"  # 1 habit           -> 0.10
KU_UNTOUCHED = "ku_learner_never_applied"  # nothing            -> 0.00

# What the learner's own six channels say, as the rich UserContext carries them:
# {activity_uid: [ku_uid, ...]}.
LEARNER_HABITS = {"habit_1": [KU_DEEP], "habit_2": [KU_DEEP], "habit_3": [KU_DEEP, KU_LIGHT]}
LEARNER_TASKS = {"task_1": [KU_DEEP], "task_2": [KU_DEEP]}

EXPECTED_PERSONAL = {
    ENGAGED_IN_PROGRESS: 0.40,
    ENGAGED_MASTERED: 0.10,
    ENGAGED_BOTH: 0.00,
}


def _learner_context(user_uid: str = USER) -> UserContext:
    """A RICH context: the six activity→knowledge maps populated."""
    return UserContext(
        user_uid=user_uid,
        habit_knowledge_applied=dict(LEARNER_HABITS),
        task_knowledge_applied=dict(LEARNER_TASKS),
    )


class _StubUserService:
    """Both context depths, so the metric's CHOICE of depth is observable.

    ``get_user_context`` — the standard build — returns a context whose six
    activity→knowledge maps are EMPTY, which is what the real standard build
    returns: ``populate_graph_sourced_fields`` is called only from
    ``build_rich_user_context``. A caller that reaches for the standard depth
    therefore scores every step 0.0 and reports a learner who applied nothing.
    It does not raise. Serving both depths here turns that wiring mistake into
    a wrong number a test can see.
    """

    def __init__(self, rich: UserContext) -> None:
        self._rich = rich

    async def get_user_context(self, user_uid):
        return Result.ok(UserContext(user_uid=user_uid))

    async def get_rich_unified_context(self, user_uid, min_confidence: float = 0.7):
        return Result.ok(self._rich)


class _StubPsService:
    """The three methods ``AnalyticsMetricsService`` actually calls, over a real backend.

    Constructing the whole 12-sub-service ``PsService`` facade would drag in
    graph intelligence and an event bus for three delegations. The delegations
    themselves are one-liners; what needs a real graph is the Cypher underneath,
    which this holds directly — including the batched step→Ku read, driven
    through the real ``PsIntelligenceService`` so the scoring path under test is
    the production one rather than a copy of it.
    """

    def __init__(self, backend: PsBackend) -> None:
        self._backend = backend
        self._intelligence = PsIntelligenceService(
            backend=backend,
            intelligence_backend=PsIntelligenceBackend(Neo4jQueryExecutor(backend.driver)),
        )

    async def find_engaged_steps_in_window(self, user_uid, start_date, end_date, limit=None):
        return await self._backend.find_engaged_path_steps_by_date_range(
            user_uid, start_date, end_date, limit
        )

    async def count_engaged_knowledge(self, user_uid):
        return await self._backend.count_engaged_knowledge(user_uid)

    async def get_user_substance_scores(self, ps_uids, user_context):
        return await self._intelligence.calculate_user_substance_for_steps(ps_uids, user_context)


def _metrics_service(backend: PsBackend, context: UserContext | None = None):
    """The service under test, wired the way the composition root wires it."""
    return AnalyticsMetricsService(
        ku_service=_StubPsService(backend),
        user_service=_StubUserService(context if context is not None else _learner_context()),
    )


@pytest.mark.asyncio
class TestKnowledgeMetricsLearnerScope:
    """Knowledge metrics must cover the learner's engaged steps — those and no others."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        """Seed seven path steps and the engagement edges described in the module docstring."""
        now = datetime.now(UTC)
        recent = (now - timedelta(days=5)).isoformat()
        stale = (now - timedelta(days=200)).isoformat()

        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=USER)
            await session.run("MERGE (u:User {uid: $u})", u=OTHER_USER)

            # Every step carries a fresh updated_at so a reader that windows on
            # the NODE cannot distinguish them — only the edges differ.
            #
            # The counters are the SHARED, corpus-global figure: they are what
            # increment_substance writes with no user_uid, i.e. every learner's
            # activity pooled. They are seeded to disagree with this learner's
            # own channels so a global reading is a different number, never a
            # coincidentally equal one. Written as ZONED datetimes, which is
            # what increment_substance stores.
            for uid, title, extra in (
                (ENGAGED_IN_PROGRESS, "In progress", ""),
                (ENGAGED_MASTERED, "Mastered", ""),
                # 3 habits + 5 tasks + 5 events = 0.80, the "embodied" band —
                # material the corpus has thoroughly substantiated and THIS
                # learner has not touched at all.
                (
                    ENGAGED_BOTH,
                    "Both edges",
                    """, times_applied_in_tasks: 5, last_applied_date: datetime($updated),
                        times_practiced_in_events: 5, last_practiced_date: datetime($updated)""",
                ),
                (ENGAGED_OUT_OF_WINDOW, "Engaged long ago", ""),
                (VIEWED_ONLY, "Only viewed", ""),
                (UNTOUCHED, "Never touched", ""),
                (OTHER_USERS_STEP, "Another learner's", ""),
            ):
                await session.run(
                    f"""
                    CREATE (n:Entity:PathStep {{uid: $uid, entity_type: 'path_step',
                                               title: $title, status: 'active',
                                               updated_at: $updated,
                                               times_built_into_habits: 3,
                                               last_built_into_habit_date: datetime($updated)
                                               {extra}}})
                    """,
                    uid=uid,
                    title=title,
                    updated=now.isoformat(),
                )

            # One Ku per in-window step. Personal substance is scored over the
            # Kus a step teaches, so without these edges every step would score
            # 0.0 for structural reasons and the test would prove nothing.
            for ku_uid in (KU_DEEP, KU_LIGHT, KU_UNTOUCHED):
                await session.run(
                    """
                    CREATE (k:Entity:Ku {uid: $uid, entity_type: 'ku',
                                         title: $uid, status: 'active'})
                    """,
                    uid=ku_uid,
                )
            for ps_uid, ku_uid in (
                (ENGAGED_IN_PROGRESS, KU_DEEP),
                (ENGAGED_MASTERED, KU_LIGHT),
                (ENGAGED_BOTH, KU_UNTOUCHED),
            ):
                await session.run(
                    """
                    MATCH (p:Entity {uid: $ps_uid}), (k:Entity {uid: $ku_uid})
                    MERGE (p)-[:USES_KU]->(k)
                    """,
                    ps_uid=ps_uid,
                    ku_uid=ku_uid,
                )

            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[r:IN_PROGRESS]->(n) SET r.last_activity_at = datetime($t)
                """,
                u=USER,
                uid=ENGAGED_IN_PROGRESS,
                t=recent,
            )
            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[r:MASTERED]->(n) SET r.mastered_at = datetime($t)
                """,
                u=USER,
                uid=ENGAGED_MASTERED,
                t=recent,
            )
            # Held by BOTH edges — the de-duplication control.
            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[a:IN_PROGRESS]->(n) SET a.last_activity_at = datetime($t)
                MERGE (u)-[b:MASTERED]->(n) SET b.mastered_at = datetime($t)
                """,
                u=USER,
                uid=ENGAGED_BOTH,
                t=recent,
            )
            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[r:IN_PROGRESS]->(n) SET r.last_activity_at = datetime($t)
                """,
                u=USER,
                uid=ENGAGED_OUT_OF_WINDOW,
                t=stale,
            )
            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[r:VIEWED]->(n) SET r.last_viewed_at = datetime($t)
                """,
                u=USER,
                uid=VIEWED_ONLY,
                t=recent,
            )
            await session.run(
                """
                MATCH (u:User {uid: $u}), (n:Entity {uid: $uid})
                MERGE (u)-[r:MASTERED]->(n) SET r.mastered_at = datetime($t)
                """,
                u=OTHER_USER,
                uid=OTHER_USERS_STEP,
                t=recent,
            )

        return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)

    @staticmethod
    def _window() -> tuple[date, date]:
        today = datetime.now(UTC).date()
        return today - timedelta(days=30), today

    async def test_window_returns_exactly_the_engaged_steps(self, backend):
        """The identity set, not just a non-empty one. Pre-fix this branch never ran."""
        start, end = self._window()
        result = await backend.find_engaged_path_steps_by_date_range(USER, start, end, limit=100)
        assert result.is_ok, f"engaged-step read failed: {result}"

        uids = [step.uid for step in result.value]
        assert set(uids) == EXPECTED_IN_WINDOW, (
            "scope wrong: UNTOUCHED present = collapsed to the whole corpus; "
            "ENGAGED_OUT_OF_WINDOW present = windowed on the node, not the edge; "
            "VIEWED_ONLY present = a glance counted as uptake; "
            "OTHER_USERS_STEP present = the learner scope leaked"
        )
        assert len(uids) == len(set(uids)), (
            f"{ENGAGED_BOTH} counted twice — the max() over engagement edges was lost"
        )

    async def test_metric_reports_the_engaged_steps(self, backend):
        """End to end through the service. Pre-fix: is_error, on every call."""
        start, end = self._window()
        service = _metrics_service(backend)

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok, f"knowledge metrics failed (pre-fix behaviour): {result}"

        metrics = result.value
        assert metrics["total_knowledge_units"] == 3, (
            "4 = the double-counted step or the stale-edge step; 7 = the whole corpus"
        )
        assert metrics["user_uid"] == USER

    async def test_magnitudes_are_the_learners_own_not_the_corpus(self, backend):
        """The headline number must come from THIS learner's activity channels.

        Pre-fix the score was ``Curriculum.substance_score()`` — counters
        written onto the shared node by every learner's activity, since
        ``increment_substance`` carries no ``user_uid``. The seeded nodes make
        the two readings disagree on every step, so each assertion here names
        the wrong answer it excludes.
        """
        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        metrics = result.value
        # (0.40 + 0.10 + 0.00) / 3. The global reading is (0.30 + 0.30 + 0.80) / 3.
        assert metrics["avg_substance_score"] == pytest.approx(0.17), (
            "0.47 = the shared node's counters — six learners' activity on this "
            "learner's material; 0.0 = the channel maps arrived empty, i.e. the "
            "STANDARD UserContext was used where the rich one is required"
        )
        assert metrics["applied_knowledge"] == 1, f"only {ENGAGED_IN_PROGRESS} (0.40) is applied"
        assert metrics["theoretical_knowledge"] == 2, (
            f"{ENGAGED_MASTERED} (0.10) and {ENGAGED_BOTH} (0.00)"
        )
        assert metrics["embodied_knowledge"] == 0, (
            f"{ENGAGED_BOTH} carries 0.80 of OTHER learners' substance — it must "
            "not read as embodied for a learner who never applied it"
        )
        assert metrics["practiced_knowledge"] == 0

    async def test_a_standard_context_would_be_a_flat_zero_not_an_error(self, backend):
        """Why the depth choice is load-bearing, asserted rather than asserted-about.

        The six activity→knowledge maps are populated only by
        ``build_rich_user_context``. Feeding the metric a standard-depth context
        does not fail — it scores every step 0.0 and publishes a week in which
        the learner applied nothing. This pins that the metric asks for the rich
        depth by showing what the other one produces.
        """
        start, end = self._window()
        standard = UserContext(user_uid=USER)  # what get_user_context returns
        result = await _metrics_service(backend, standard).calculate_knowledge_metrics(
            USER, start, end
        )
        assert result.is_ok

        assert result.value["avg_substance_score"] == 0.0
        assert result.value["theoretical_knowledge"] == 3, (
            "an empty context is indistinguishable from an unapplied learner — "
            "which is exactly why the depth cannot be chosen by accident"
        )

    async def test_a_step_teaching_no_ku_scores_zero(self, backend, neo4j_driver):
        """Structural emptiness reports as 0.0, and the step still counts.

        The batched read returns a row for every requested step, empty
        ``ku_uids`` included, precisely so this case is a reading rather than a
        missing key the caller has to guess a default for. Dropping it instead
        would shrink the denominator and quietly raise the average.
        """
        lone_user = "user_step_without_kus"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=lone_user)
            await session.run(
                """
                CREATE (n:Entity:PathStep {uid: 'ps_teaches_nothing',
                                           entity_type: 'path_step',
                                           title: 'Teaches nothing', status: 'active',
                                           times_built_into_habits: 3})
                """
            )
        assert (
            await backend.mark_in_progress(
                lone_user, "ps_teaches_nothing", datetime.now(UTC).isoformat()
            )
        ).is_ok

        start, end = self._window()
        service = _metrics_service(backend, _learner_context(lone_user))
        result = await service.calculate_knowledge_metrics(lone_user, start, end)
        assert result.is_ok

        assert result.value["total_knowledge_units"] == 1, "the step was dropped, not scored"
        assert result.value["avg_substance_score"] == 0.0, "0.3 = the node's own counters"
        assert result.value["theoretical_knowledge"] == 1

    async def test_review_warnings_carry_the_personal_score(self, backend):
        """Warnings list the learner's under-substantiated steps, least first.

        Historically this was a decay PREDICTION off the node's ``last_*_date``
        fields. There is no personal decay clock — the UserContext channel maps
        carry uids and no timestamps — so ``days_until_review`` is 0 ("review
        now") on every row and the ranking moved to substance. Sorting by the
        old key would order a column that is constant, truncating the top-10 to
        an arbitrary ten rather than the ten that most need work.
        """
        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        warnings = result.value["decay_warnings"]
        assert {w["ku_uid"] for w in warnings} == EXPECTED_IN_WINDOW, (
            "all three sit under the 0.5 review threshold for THIS learner; "
            f"a missing {ENGAGED_BOTH} means the 0.80 of other learners' "
            "substance on it was read as this learner's"
        )
        assert [w["ku_uid"] for w in warnings] == [
            ENGAGED_BOTH,
            ENGAGED_MASTERED,
            ENGAGED_IN_PROGRESS,
        ], "least-substantiated first"
        assert all(w["days_until_review"] == 0 for w in warnings)
        assert {w["ku_uid"]: w["current_substance"] for w in warnings} == pytest.approx(
            EXPECTED_PERSONAL
        )

    async def test_counts_match_the_windowed_read(self, backend):
        """The all-time counterpart agrees with the window, and MASTERED is a subset."""
        counts_result = await backend.count_engaged_knowledge(USER)
        assert counts_result.is_ok, f"engagement counts failed: {counts_result}"

        counts = counts_result.value
        # All-time picks up the stale-edge step the 30-day window excludes.
        assert counts["total"] == 4, "expected the 3 in-window steps plus the stale-edge one"
        assert counts["mastered"] == 2, f"{ENGAGED_MASTERED} and {ENGAGED_BOTH}"
        assert counts["mastered"] <= counts["total"]

    async def test_a_failed_read_is_not_reported_as_an_empty_week(self, backend):
        """A DB failure must propagate, not become a successful all-zero report.

        The guard used to be `if kus_result.is_error or not kus_result.value`,
        which collapsed the two cases: an outage produced
        ``Result.ok(total_knowledge_units=0)`` that downstream persisted as a
        week in which the learner genuinely learned nothing.
        """

        class _FailingPsService:
            async def find_engaged_steps_in_window(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        start, end = self._window()
        service = AnalyticsMetricsService(
            ku_service=_FailingPsService(), user_service=_StubUserService(_learner_context())
        )

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error, "an infrastructure failure was reported as an empty week"

    async def test_a_failed_context_read_is_not_reported_as_an_unapplied_week(self, backend):
        """The same rule for the SECOND read the metric now depends on.

        A learner's activity channels arriving as an error must propagate. If it
        degraded to an empty context instead, every step would score 0.0 and the
        week would persist as "learned it, applied none of it" — a plausible
        reading, which is what makes it dangerous.
        """

        class _FailingUserService:
            async def get_rich_unified_context(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        start, end = self._window()
        service = AnalyticsMetricsService(
            ku_service=_StubPsService(backend), user_service=_FailingUserService()
        )

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error, "a failed context read was reported as an unapplied week"

    async def test_the_metric_refuses_without_a_user_service(self, backend):
        """No learner, no per-learner figure — refuse rather than fall back.

        The fallback would be ``Curriculum.substance_score()``, i.e. silently
        reporting the corpus-global number under a per-learner heading. That is
        the defect this whole module guards; it must not be reachable through an
        unwired dependency.
        """
        start, end = self._window()
        service = AnalyticsMetricsService(ku_service=_StubPsService(backend))

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error

    async def test_the_window_read_is_not_capped(self, backend):
        """An aggregate must cover every engaged step, not the newest page of them.

        The read defaulted to `limit=100` and the caller passed
        `QueryLimit.COMPREHENSIVE`, which IS 100 — so a learner past that many
        engaged steps in one window got a wrong `total_knowledge_units` rather
        than a shorter list. 120 steps here is deliberately over that boundary.
        """
        now = datetime.now(UTC)
        recent = (now - timedelta(days=3)).isoformat()
        async with backend.driver.session() as session:
            await session.run(
                """
                UNWIND range(1, 120) AS i
                CREATE (n:Entity:PathStep {uid: 'ps_bulk_' + toString(i),
                                           entity_type: 'path_step',
                                           title: 'Bulk ' + toString(i), status: 'active'})
                WITH n
                MATCH (u:User {uid: $u})
                MERGE (u)-[r:IN_PROGRESS]->(n) SET r.last_activity_at = datetime($t)
                """,
                u=USER,
                t=recent,
            )

        start, end = self._window()
        result = await backend.find_engaged_path_steps_by_date_range(USER, start, end)
        assert result.is_ok

        # 120 bulk + the 3 originally in-window steps.
        assert len(result.value) == 123, (
            f"got {len(result.value)} — 100 means the LIMIT is still capping the aggregate"
        )

    async def test_every_real_writer_path_lands_in_the_window(self, backend, neo4j_driver):
        """Engagement must be recognised however the edge was written.

        Six backend methods write these three edge types and between them use
        NINE timestamp field names. The first version of this query hand-listed
        four, so a step mastered through ``_AdaptiveMixin.track_mastery_completion``
        (``created_at``/``updated_at``) evaluated to NULL and vanished from every
        windowed report — an under-return, which is indistinguishable from "the
        learner did nothing" unless a test drives the actual writer.

        So this drives the REAL methods rather than seeding properties by hand:
        a hand-seeded fixture can only ever confirm the names its author already
        thought of.
        """
        writer_user = "user_writer_paths"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=writer_user)
            for uid in ("ps_w_learning_state", "ps_w_adaptive", "ps_w_read"):
                await session.run(
                    """
                    CREATE (n:Entity:PathStep {uid: $uid, entity_type: 'path_step',
                                               title: $uid, status: 'active'})
                    """,
                    uid=uid,
                )

        now_iso = datetime.now(UTC).isoformat()
        # started_at / last_activity_at
        assert (await backend.mark_in_progress(writer_user, "ps_w_learning_state", now_iso)).is_ok
        # created_at only — the field family the original enumeration missed
        assert (await backend.track_mastery_completion(writer_user, "ps_w_adaptive", 30)).is_ok
        # marked_at
        assert (await backend.mark_as_read(writer_user, "ps_w_read")).is_ok

        start, end = self._window()
        result = await backend.find_engaged_path_steps_by_date_range(writer_user, start, end)
        assert result.is_ok

        assert {s.uid for s in result.value} == {
            "ps_w_learning_state",
            "ps_w_adaptive",
            "ps_w_read",
        }, "a writer path was dropped — its timestamp field is not being recognised"

    async def test_counts_include_ku_mastery_from_the_report_pipeline(self, backend, neo4j_driver):
        """Mastery earned through the learning loop attaches to :Ku, and must count.

        ``ReportMasteryService.propagate_mastery`` feeds uids from
        ``get_linked_ku_and_student`` — which filters ``{entity_type: 'ku'}`` —
        into a ``mark_mastered`` whose MATCH carries no label. So the AI-report
        and teacher-approval paths, i.e. the loop's MAIN route to mastery, write
        MASTERED to :Ku nodes. A PathStep-pinned count saw none of it and
        returned a confident zero.

        The windowed sibling stays PathStep-only on purpose — a step's personal
        substance is the mean over the Kus it teaches, so admitting Kus there
        would count the same applications twice — so this asserts the two scopes
        differ rather than assuming they agree.
        """
        ku_user = "user_ku_mastery"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=ku_user)
            await session.run(
                """
                CREATE (k:Entity:Ku {uid: 'ku_mastered_via_report', entity_type: 'ku',
                                     title: 'Mastered KU', status: 'active'})
                CREATE (p:Entity:PathStep {uid: 'ps_engaged_alongside',
                                           entity_type: 'path_step',
                                           title: 'Engaged step', status: 'active'})
                """
            )

        now_iso = datetime.now(UTC).isoformat()
        # The report pipeline's own call path, verbatim: no label pin, Ku target.
        assert (
            await backend.mark_mastered(
                ku_user, "ku_mastered_via_report", now_iso, 0.8, "activity_report"
            )
        ).is_ok
        assert (await backend.mark_in_progress(ku_user, "ps_engaged_alongside", now_iso)).is_ok

        counts = (await backend.count_engaged_knowledge(ku_user)).value
        assert counts["total"] == 2, "the :Ku node was dropped by a label pin"
        assert counts["mastered"] == 1, "report-driven Ku mastery was not counted"

        # The substance window is deliberately narrower — steps only.
        start, end = self._window()
        windowed = (await backend.find_engaged_path_steps_by_date_range(ku_user, start, end)).value
        assert {s.uid for s in windowed} == {"ps_engaged_alongside"}, (
            "the substance window must stay PathStep-only — a step's substance "
            "already averages its Kus', so admitting both double-counts"
        )

    async def test_a_learner_with_no_engagement_gets_zeroes_not_the_corpus(self, backend):
        """The empty case must be empty — 7 here would mean the scope was never applied."""
        start, end = self._window()
        service = _metrics_service(backend, _learner_context("user_with_no_knowledge"))

        result = await service.calculate_knowledge_metrics("user_with_no_knowledge", start, end)
        assert result.is_ok
        assert result.value["total_knowledge_units"] == 0

        counts_result = await backend.count_engaged_knowledge("user_with_no_knowledge")
        assert counts_result.is_ok
        assert counts_result.value == {"total": 0, "mastered": 0}
