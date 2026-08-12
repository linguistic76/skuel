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

See: adapters/persistence/neo4j/backends/curriculum_backends.py (_ENGAGEMENT_EDGES)
     scripts/publication_gate_registry.py (both surfaces are USER_STATE)
"""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
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


class _StubPsService:
    """The two methods ``AnalyticsMetricsService`` actually calls, over a real backend.

    Constructing the whole 12-sub-service ``PsService`` facade would drag in
    graph intelligence and an event bus for two delegations. The delegations
    themselves are one-liners onto ``self.core.backend``; what needs a real
    graph is the Cypher underneath, which this holds directly.
    """

    def __init__(self, backend: PsBackend) -> None:
        self._backend = backend

    async def find_engaged_steps_in_window(self, user_uid, start_date, end_date, limit=None):
        return await self._backend.find_engaged_path_steps_by_date_range(
            user_uid, start_date, end_date, limit
        )

    async def count_engaged_steps(self, user_uid):
        return await self._backend.count_engaged_path_steps(user_uid)


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
            for uid, title in (
                (ENGAGED_IN_PROGRESS, "In progress"),
                (ENGAGED_MASTERED, "Mastered"),
                (ENGAGED_BOTH, "Both edges"),
                (ENGAGED_OUT_OF_WINDOW, "Engaged long ago"),
                (VIEWED_ONLY, "Only viewed"),
                (UNTOUCHED, "Never touched"),
                (OTHER_USERS_STEP, "Another learner's"),
            ):
                # 3 habits built today: enough to clear _was_once_substantiated
                # (so days_until_review_needed returns a number rather than None)
                # and to score exactly 0.30 — the "applied" band. Written as a
                # ZONED datetime, which is what increment_substance stores and
                # what the naive-vs-aware decay arithmetic used to choke on.
                await session.run(
                    """
                    CREATE (n:Entity:PathStep {uid: $uid, entity_type: 'path_step',
                                               title: $title, status: 'active',
                                               updated_at: $updated,
                                               times_built_into_habits: 3,
                                               last_built_into_habit_date: datetime($updated)})
                    """,
                    uid=uid,
                    title=title,
                    updated=now.isoformat(),
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
        service = AnalyticsMetricsService(ku_service=_StubPsService(backend))

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok, f"knowledge metrics failed (pre-fix behaviour): {result}"

        metrics = result.value
        assert metrics["total_knowledge_units"] == 3, (
            "4 = the double-counted step or the stale-edge step; 7 = the whole corpus"
        )
        # 3 habits built today: min(0.30, 3 * 0.10 * 1.0). A zero here means the
        # subject collapsed to Ku, which inherits Entity.substance_score() and is
        # flat 0.0 — the shape the brief's own suggested fix would have produced.
        assert metrics["avg_substance_score"] == pytest.approx(0.3)
        assert metrics["applied_knowledge"] == 3, "0.30 belongs in the 0.3-0.6 band"
        assert metrics["theoretical_knowledge"] == 0
        assert metrics["user_uid"] == USER

    async def test_decay_warnings_populate(self, backend):
        """The warnings list read a method name no model carries: it was always empty.

        ``getattr(ku, "days_until_review", None)`` — the real method is
        ``days_until_review_needed`` — made ``callable(None)`` False on every
        pass, so this documented output could never contain anything. The
        seeded steps score 0.30, under the 0.5 review threshold, so each owes a
        warning at 0 days.
        """
        start, end = self._window()
        service = AnalyticsMetricsService(ku_service=_StubPsService(backend))

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        warnings = result.value["decay_warnings"]
        assert {w["ku_uid"] for w in warnings} == EXPECTED_IN_WINDOW, (
            "empty = the dead getattr branch is back; extra uids = the scope leaked"
        )
        assert all(w["days_until_review"] == 0 for w in warnings)
        assert all(w["current_substance"] == pytest.approx(0.3) for w in warnings)

    async def test_counts_match_the_windowed_read(self, backend):
        """The all-time counterpart agrees with the window, and MASTERED is a subset."""
        counts_result = await backend.count_engaged_path_steps(USER)
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
        service = AnalyticsMetricsService(ku_service=_FailingPsService())

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error, "an infrastructure failure was reported as an empty week"

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

    async def test_a_learner_with_no_engagement_gets_zeroes_not_the_corpus(self, backend):
        """The empty case must be empty — 7 here would mean the scope was never applied."""
        start, end = self._window()
        service = AnalyticsMetricsService(ku_service=_StubPsService(backend))

        result = await service.calculate_knowledge_metrics("user_with_no_knowledge", start, end)
        assert result.is_ok
        assert result.value["total_knowledge_units"] == 0

        counts_result = await backend.count_engaged_path_steps("user_with_no_knowledge")
        assert counts_result.is_ok
        assert counts_result.value == {"total": 0, "mastered": 0}
