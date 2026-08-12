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

The per-learner score is computed from the learner's six activity→knowledge
channels, over the Kus each step teaches, so the fixture links Kus AND seeds real
activity nodes with real OWNS/knowledge edges.

Those activities are all completed/archived and stamped 200 days ago on purpose.
The channels are read UNWINDOWED (``CrossDomainBackend.get_user_knowledge_channels``)
rather than off a ``UserContext``, whose copies the MEGA-QUERY builds for
PLANNING — bounded to open-or-recent rows, and unevenly (an active habit at any
age, an event only inside the window). Substance is cumulative, so sourcing it
there would drop every application below and read as "you applied nothing".

See: adapters/persistence/neo4j/backends/curriculum_backends.py (_ENGAGEMENT_EDGES)
     core/services/knowledge/user_substance.py (the one weight table)
     scripts/publication_gate_registry.py (both surfaces are USER_STATE)
"""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
from core.services.ps.ps_intelligence_service import PsIntelligenceService
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

EXPECTED_PERSONAL = {
    ENGAGED_IN_PROGRESS: 0.40,
    ENGAGED_MASTERED: 0.10,
    ENGAGED_BOTH: 0.00,
}


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

    async def get_user_substance_scores(self, ps_uids, channels):
        return await self._intelligence.calculate_user_substance_for_steps(ps_uids, channels)


def _metrics_service(backend: PsBackend):
    """The service under test, wired the way the composition root wires it.

    Both collaborators are REAL over the seeded graph — the activity-channel read
    especially. Stubbing that one would have hidden the defect this file's window
    test exists for: the channels have to be sourced somewhere, and where they
    come from IS the question.
    """
    return AnalyticsMetricsService(
        ku_service=_StubPsService(backend),
        cross_domain_backend=CrossDomainBackend(Neo4jQueryExecutor(backend.driver)),
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

            # The learner's OWN activity — the numerator, read unwindowed.
            #
            # Every one of these is deliberately COMPLETED/ARCHIVED and stamped
            # 200 days ago, i.e. outside any planning window and past every
            # "still open" escape hatch. The MEGA-QUERY's rollup admits a task
            # only if it is open or was touched inside the window, and an event
            # only if it falls inside the window at all — so if substance is ever
            # re-sourced from a UserContext, every figure below collapses to 0.0.
            for uid, entity_type, status, ku_uid, edge in (
                ("habit_1", "habit", "archived", KU_DEEP, "REINFORCES_KNOWLEDGE"),
                ("habit_2", "habit", "archived", KU_DEEP, "REINFORCES_KNOWLEDGE"),
                ("habit_3", "habit", "archived", KU_DEEP, "REINFORCES_KNOWLEDGE"),
                ("habit_4", "habit", "archived", KU_LIGHT, "REINFORCES_KNOWLEDGE"),
                ("task_1", "task", "completed", KU_DEEP, "APPLIES_KNOWLEDGE"),
                ("task_2", "task", "completed", KU_DEEP, "APPLIES_KNOWLEDGE"),
            ):
                await session.run(
                    f"""
                    MATCH (u:User {{uid: $u}}), (k:Entity {{uid: $ku_uid}})
                    CREATE (a:Entity {{uid: $uid, entity_type: $entity_type,
                                       title: $uid, status: $status,
                                       created_at: $stale, updated_at: $stale}})
                    MERGE (u)-[:OWNS]->(a)
                    MERGE (a)-[:{edge}]->(k)
                    """,
                    u=USER,
                    uid=uid,
                    entity_type=entity_type,
                    status=status,
                    ku_uid=ku_uid,
                    stale=stale,
                )

            # The tenancy control on the NUMERATOR: another learner grinding the
            # same Ku must not move this learner's score.
            await session.run(
                """
                MATCH (u:User {uid: $u}), (k:Entity {uid: $ku_uid})
                CREATE (a:Entity {uid: 'other_habit', entity_type: 'habit',
                                  title: 'Their habit', status: 'active'})
                MERGE (u)-[:OWNS]->(a)
                MERGE (a)-[:REINFORCES_KNOWLEDGE]->(k)
                """,
                u=OTHER_USER,
                ku_uid=KU_UNTOUCHED,
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
            "learner's material; 0.0 = the channels arrived empty, i.e. a "
            "windowed source dropped these 200-day-old applications"
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

    async def test_activity_older_than_any_planning_window_still_counts(self, backend):
        """Substance is cumulative: a task you finished last year still applied it.

        Every seeded activity is completed/archived and stamped 200 days back,
        so this whole file's numbers are unreachable from a ``UserContext``. The
        MEGA-QUERY builds those maps for PLANNING — a task enters only if it is
        open or was touched inside a 30-day window, an event only if it falls
        inside the window at all — which understates a cumulative figure, shifts
        the bands, and raises review warnings on knowledge the learner did apply,
        purely because of its age. It also does so INCONSISTENTLY: an active
        habit is admitted at any age while a month-old event vanishes, so there
        is no single sentence describing what such a score would mean.

        Hence ``get_user_knowledge_channels``, which applies no window and no
        status filter. A zero here is that read having been swapped back for a
        context.
        """
        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        assert result.value["avg_substance_score"] == pytest.approx(0.17), (
            "0.0 = the channels came from a windowed source, so 200-day-old "
            "applications were dropped and every step read as theoretical"
        )
        assert result.value["applied_knowledge"] == 1

    async def test_another_learners_activity_does_not_move_this_score(self, backend):
        """The tenancy control on the numerator, not just the denominator.

        ``OTHER_USER`` holds an ACTIVE habit reinforcing ``KU_UNTOUCHED`` — the
        Ku behind ``ENGAGED_BOTH``. The channel read is anchored on
        ``(u:User {uid})-[:OWNS]->``, so their habit must not appear in this
        learner's index; ``ENGAGED_BOTH`` stays at 0.00 rather than 0.10.
        """
        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        by_uid = {
            w["ku_uid"]: w["current_substance"] for w in result.value["review_recommendations"]
        }
        assert by_uid[ENGAGED_BOTH] == 0.0, (
            "0.1 = the OWNS anchor is missing and another learner's habit was counted"
        )

    async def test_a_ku_reachable_only_by_contains_knowledge_is_credited(
        self, backend, neo4j_driver
    ):
        """The step→Ku resolver and the channel rollup must agree on the edge set.

        The substance write fan-out, ``fetch_taught_ku_uids*`` and the channel
        read all traverse USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU. The MEGA-QUERY's
        rollup listed only two of the three until 2026-08-12, so a Ku reachable
        from a step only over CONTAINS_KNOWLEDGE landed in the DENOMINATOR (the
        step teaches it) and never in the numerator (no channel could see it) —
        an under-return that reads as "you never applied this".
        """
        cn_user = "user_contains_knowledge"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=cn_user)
            await session.run(
                """
                CREATE (p:Entity:PathStep {uid: 'ps_contains', entity_type: 'path_step',
                                           title: 'Contains-only step', status: 'active'})
                CREATE (k:Entity:Ku {uid: 'ku_contains_only', entity_type: 'ku',
                                     title: 'Reachable only by CONTAINS_KNOWLEDGE',
                                     status: 'active'})
                MERGE (p)-[:CONTAINS_KNOWLEDGE]->(k)
                """
            )
            # TWO shapes, because the triple has to hold on both sides of the
            # join and each side has its own arm of the query:
            #   cn_habit  -> the Ku DIRECTLY  (exercises the resolver: the step
            #                reaches its Ku only over CONTAINS_KNOWLEDGE)
            #   cn_task   -> the STEP         (exercises the channel bridge: the
            #                activity's target must expand to the step's Kus over
            #                the same triple — the exact shape the MEGA-QUERY
            #                rollup got wrong)
            await session.run(
                """
                MATCH (u:User {uid: $u}), (k:Entity {uid: 'ku_contains_only'}),
                      (p:Entity {uid: 'ps_contains'})
                CREATE (h:Entity {uid: 'cn_habit', entity_type: 'habit',
                                  title: 'Habit', status: 'active'})
                CREATE (t:Entity {uid: 'cn_task', entity_type: 'task',
                                  title: 'Task', status: 'completed'})
                MERGE (u)-[:OWNS]->(h)
                MERGE (u)-[:OWNS]->(t)
                MERGE (h)-[:REINFORCES_KNOWLEDGE]->(k)
                MERGE (t)-[:APPLIES_KNOWLEDGE]->(p)
                """,
                u=cn_user,
            )
        assert (
            await backend.mark_in_progress(cn_user, "ps_contains", datetime.now(UTC).isoformat())
        ).is_ok

        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(cn_user, start, end)
        assert result.is_ok

        # habit 0.10 + task 0.05, both landing on the one Ku the step composes.
        assert result.value["avg_substance_score"] == pytest.approx(0.15), (
            "0.0  = the resolver dropped CONTAINS_KNOWLEDGE, so the step teaches "
            "nothing;  0.10 = the CHANNEL BRIDGE dropped it, so the task's "
            "PathStep target never expanded to the Ku it composes"
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
        service = _metrics_service(backend)
        result = await service.calculate_knowledge_metrics(lone_user, start, end)
        assert result.is_ok

        assert result.value["total_knowledge_units"] == 1, "the step was dropped, not scored"
        assert result.value["avg_substance_score"] == 0.0, "0.3 = the node's own counters"
        assert result.value["theoretical_knowledge"] == 1

    async def test_review_recommendations_carry_the_personal_score(self, backend):
        """The learner's under-substantiated steps, least-substantiated first.

        This REPLACES the old ``decay_warnings`` key rather than reusing it.
        That one promised a decay PREDICTION off the node's ``last_*_date``
        fields and carried a ``days_until_review``; per-user substance has no
        clock to predict from, so the field is gone rather than pinned at 0 —
        keeping the old name over incompatible semantics would have been a
        legacy path preserved. Ranking moved to substance, so the top-10 cap
        keeps the ten that most need work rather than an arbitrary ten.
        """
        start, end = self._window()
        result = await _metrics_service(backend).calculate_knowledge_metrics(USER, start, end)
        assert result.is_ok

        warnings = result.value["review_recommendations"]
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
        assert not any("days_until_review" in w for w in warnings), (
            "an uncomputable field must be absent, not pinned at a constant"
        )
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
            ku_service=_FailingPsService(),
            cross_domain_backend=CrossDomainBackend(Neo4jQueryExecutor(backend.driver)),
        )

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error, "an infrastructure failure was reported as an empty week"

    async def test_a_failed_channel_read_is_not_reported_as_an_unapplied_week(self, backend):
        """The same rule for the SECOND read the metric now depends on.

        A learner's activity channels arriving as an error must propagate. If it
        degraded to empty channels instead, every step would score 0.0 and the
        week would persist as "learned it, applied none of it" — a plausible
        reading, which is what makes it dangerous.
        """

        class _FailingChannelBackend:
            async def get_user_knowledge_channels(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        start, end = self._window()
        service = AnalyticsMetricsService(
            ku_service=_StubPsService(backend), cross_domain_backend=_FailingChannelBackend()
        )

        result = await service.calculate_knowledge_metrics(USER, start, end)
        assert result.is_error, "a failed context read was reported as an unapplied week"

    async def test_the_metric_refuses_without_a_channel_source(self, backend):
        """No learner activity, no per-learner figure — refuse rather than fall back.

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
        service = _metrics_service(backend)

        result = await service.calculate_knowledge_metrics("user_with_no_knowledge", start, end)
        assert result.is_ok
        assert result.value["total_knowledge_units"] == 0

        counts_result = await backend.count_engaged_knowledge("user_with_no_knowledge")
        assert counts_result.is_ok
        assert counts_result.value == {"total": 0, "mastered": 0}
