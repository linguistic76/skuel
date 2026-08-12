"""
Real-Neo4j guard for the learner scope of Life Path alignment.
==============================================================

``AnalyticsLifePathService.calculate_life_path_alignment`` reported a
corpus-global figure under a per-user heading — ``ku_dto.substance_score()``
reads counters ``KuBackend.increment_substance`` writes onto the SHARED
curriculum node with no ``user_uid``. Six learners share the live graph.

**It never got that far.** The magnitude defect was latent behind a selection
that returned nothing, five stacked ways, each of which fails SILENTLY:

1. ``life_path_uid`` came off ``UserService.get_user_context``. The STANDARD
   build never populates it — ``populate_life_path`` has one call site, inside
   ``build_rich_user_context`` — so the method took its "No Life Path designated
   yet" branch for every user, designated or not.
2. Past that, ``LpService.get(life_path_uid)`` built a ``LearningPath`` from a
   node whose ``entity_type`` designation had flipped to ``'life_path'`` in
   place, raising that model's honest-leaf-identity guard (G6).
3. The steps came from ``PathStep.knowledge_uids``, a property carried by ZERO
   of the 25 path steps in the live graph. Composition lives on
   ``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`` edges, which held 13 Kus for
   ``lp.mindfulness-101`` while the property path yielded 0.
4. Those (Ku) uids were then fetched through ``PsService.get``, whose backend
   MATCHes ``(n:PathStep {uid})`` — a Ku uid cannot match.
5. ``_analyze_domain_contributions`` read ``substance_by_type``, an attribute
   defined nowhere in the codebase, and stuffed ``user_uid`` into the
   ``dict[str, float]`` it returned; ``_generate_recommendations`` then compared
   that str ``< 0.1``. Any non-empty selection raised ``TypeError``.

So the tests here have to prove the metric RUNS, that it selects the whole
designated path, and that every magnitude on it is this learner's.

**The seeding makes the two readings disagree on every step**, so no assertion
can pass against both implementations:

    step                node counters → global    learner's channels → personal
    PS_EMBODIED         1 habit           0.10     all six channels       1.00
    PS_APPLIED          3h + 5t + 5e      0.80     2 habits + 3 tasks     0.35
    PS_CORPUS_HOT       3h + 5t + 5e      0.80     nothing                0.00
    PS_NO_KU            3 habits          0.30     teaches no Ku          0.00

``PS_APPLIED`` and ``PS_CORPUS_HOT`` carry IDENTICAL node counters and differ
only in what this learner did, so a global reading cannot tell them apart.
``PS_EMBODIED`` inverts the pair: barely substantiated by the corpus, fully
embodied by this learner — a fix that merely swapped one shared number for
another still fails it.

The designation is written by the REAL writer (``LifePathBackend.designate_life_path``)
rather than hand-seeded, because what that writer produces — a ``:LearningPath``
node whose ``entity_type`` property alone says ``'life_path'`` — is precisely
what defects 2 and 3 tripped over.

Every seeded activity is completed/archived and stamped 200 days ago, outside
any planning window and past every "still open" escape hatch. The channels are
read UNWINDOWED (``CrossDomainBackend.get_user_knowledge_channels``); sourcing
them from a ``UserContext`` instead collapses every figure below to 0.0.

See: core/services/knowledge/user_substance.py (the one weight table)
     docs/architecture/knowledge_substance_philosophy.md § Ruling: Life Path alignment
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.services.analytics.analytics_life_path_service import AnalyticsLifePathService
from core.services.lifepath.lifepath_core_service import LifePathCoreService
from core.services.ps.ps_intelligence_service import PsIntelligenceService
from core.utils.result_simplified import Errors, Result

USER = "user_life_path_scope"
OTHER_USER = "user_life_path_scope_other"

LIFE_PATH = "lp_designated_life_path"
OTHER_PATH = "lp_not_designated"

PS_EMBODIED = "ps_lp_embodied"
PS_APPLIED = "ps_lp_applied"
PS_CORPUS_HOT = "ps_lp_corpus_hot"
PS_NO_KU = "ps_lp_teaches_nothing"
PS_OFF_PATH = "ps_lp_off_path"

ON_PATH = {PS_EMBODIED, PS_APPLIED, PS_CORPUS_HOT, PS_NO_KU}

KU_DEEP = "ku_lp_all_six_channels"
KU_LIGHT = "ku_lp_partially_applied"
KU_NEVER = "ku_lp_never_applied"

# 0.30 habits + 0.25 tasks + 0.25 events + 0.20 entries + 0.14 choices
# + 0.14 principles = 1.28 raw, capped to 1.00.
EXPECTED_EMBODIED = 1.00
# 2 habits (0.20) + 3 tasks (0.15).
EXPECTED_APPLIED = 0.35
# (1.00 + 0.35 + 0.00 + 0.00) / 4
EXPECTED_ALIGNMENT = 0.34

# Summed per-channel substance over the path, normalised against its OWN total
# (1.63), not against the summed scores (1.35) — the six channels contribute up
# to 1.30 raw per Ku while the score is capped at 1.0, so the two totals differ.
EXPECTED_CONTRIBUTIONS = {
    "tasks": 0.25,  # 0.40 / 1.63
    "habits": 0.31,  # 0.50 / 1.63
    "events": 0.15,  # 0.25 / 1.63
    "entries": 0.12,  # 0.20 / 1.63
    "choices": 0.09,  # 0.14 / 1.63
    "principles": 0.09,  # 0.14 / 1.63
}

# The learner's own activity: (count, entity_type, status, ku, edge).
LEARNER_ACTIVITY = [
    (3, "habit", "archived", KU_DEEP, "REINFORCES_KNOWLEDGE"),
    (5, "task", "completed", KU_DEEP, "APPLIES_KNOWLEDGE"),
    (5, "event", "completed", KU_DEEP, "APPLIES_KNOWLEDGE"),
    (3, "user_entry", "completed", KU_DEEP, "APPLIES_KNOWLEDGE"),
    (2, "choice", "completed", KU_DEEP, "INFORMED_BY_KNOWLEDGE"),
    (2, "principle", "archived", KU_DEEP, "GROUNDED_IN_KNOWLEDGE"),
    (2, "habit", "archived", KU_LIGHT, "REINFORCES_KNOWLEDGE"),
    (3, "task", "completed", KU_LIGHT, "APPLIES_KNOWLEDGE"),
]

# 3 habits + 5 tasks + 5 events on the shared node — the "embodied" band's worth
# of OTHER learners' activity, pooled by a writer that carries no user_uid.
HOT_COUNTERS = """, times_applied_in_tasks: 5, last_applied_date: datetime($now),
                   times_practiced_in_events: 5, last_practiced_date: datetime($now)"""


class _StubPsService:
    """The one method the alignment service calls, over a real backend.

    Constructing the whole PsService facade would drag in graph intelligence and
    an event bus for a single delegation; what needs a real graph is the batched
    step→Ku read underneath, driven here through the production
    ``PsIntelligenceService`` rather than a copy of its arithmetic.
    """

    def __init__(self, backend: PsBackend) -> None:
        self._intelligence = PsIntelligenceService(
            backend=backend,
            intelligence_backend=PsIntelligenceBackend(Neo4jQueryExecutor(backend.driver)),
        )

    async def get_user_substance_breakdowns(self, ps_uids, channels):
        return await self._intelligence.calculate_user_substance_breakdown_for_steps(
            ps_uids, channels
        )


class _LifePathFacadeShim(LifePathCoreService):
    """``LifePathCoreService`` plus the one projection the facade adds.

    The alignment service calls the facade's names; the core service is what
    actually implements them, so this binds one to the other without composing
    the four-sub-service LifePathService for two delegations.

    ``get_alignment_trend_data`` is deliberately absent — the alignment payload
    carries no ``trends``, because the ``ALIGNMENT_SNAPSHOT`` history it would
    read is written only by the five-dimension metric. If a trends read is ever
    reintroduced here it will fail on this shim rather than quietly reporting
    another metric's history.
    """

    async def get_designated_life_path_uid(self, user_uid):
        designation_result = await self.get_designation(user_uid)
        if designation_result.is_error:
            return Result.fail(designation_result)
        designation = designation_result.value
        return Result.ok(designation.life_path_uid if designation else None)


@pytest.mark.asyncio
class TestLifePathAlignmentLearnerScope:
    """Alignment must cover the whole designated path, scored as THIS learner."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        """Seed the designated path, its steps, and the learner's own activity."""
        now = datetime.now(UTC)
        stale = (now - timedelta(days=200)).isoformat()

        async with neo4j_driver.session() as session:
            for uid in (USER, OTHER_USER):
                await session.run("MERGE (u:User {uid: $u})", u=uid)

            # Two learning paths. Designation promotes exactly one of them, so
            # OTHER_PATH is the control on "the path read is keyed on the
            # designation" rather than "any path will do".
            for uid, title in ((LIFE_PATH, "Become a mindful engineer"), (OTHER_PATH, "Unrelated")):
                await session.run(
                    """
                    CREATE (p:Entity:LearningPath {uid: $uid, entity_type: 'learning_path',
                                                   title: $title, status: 'active'})
                    """,
                    uid=uid,
                    title=title,
                )

            # Node counters are the SHARED, corpus-global figure — what
            # increment_substance writes with no user_uid, i.e. every learner's
            # activity pooled. Seeded to DISAGREE with this learner's channels
            # on every step, and identically on PS_APPLIED / PS_CORPUS_HOT so a
            # global reading cannot tell those two apart.
            for uid, title, habits, extra in (
                (PS_EMBODIED, "Embodied by me, cold in the corpus", 1, ""),
                (PS_APPLIED, "Partly applied by me", 3, HOT_COUNTERS),
                (PS_CORPUS_HOT, "Untouched by me, hot in the corpus", 3, HOT_COUNTERS),
                (PS_NO_KU, "Teaches no Ku", 3, ""),
                (PS_OFF_PATH, "Not on the designated path", 3, ""),
            ):
                await session.run(
                    f"""
                    CREATE (n:Entity:PathStep {{uid: $uid, entity_type: 'path_step',
                                               title: $title, status: 'active',
                                               updated_at: $now,
                                               times_built_into_habits: $habits,
                                               last_built_into_habit_date: datetime($now)
                                               {extra}}})
                    """,
                    uid=uid,
                    title=title,
                    habits=habits,
                    now=now.isoformat(),
                )

            # Composition travels over HAS_STEP. PS_OFF_PATH gets no edge; the
            # 5th step appearing means the selection collapsed to the corpus.
            for sequence, ps_uid in enumerate((PS_EMBODIED, PS_APPLIED, PS_CORPUS_HOT, PS_NO_KU)):
                await session.run(
                    """
                    MATCH (p:Entity {uid: $lp}), (s:Entity {uid: $ps})
                    MERGE (p)-[r:HAS_STEP]->(s) SET r.sequence = $sequence
                    """,
                    lp=LIFE_PATH,
                    ps=ps_uid,
                    sequence=sequence,
                )
            # A step on the OTHER path — present in the corpus, off the
            # designated path, and reachable only if the read ignores HAS_STEP.
            await session.run(
                """
                MATCH (p:Entity {uid: $lp}), (s:Entity {uid: $ps})
                MERGE (p)-[r:HAS_STEP]->(s) SET r.sequence = 0
                """,
                lp=OTHER_PATH,
                ps=PS_OFF_PATH,
            )

            for ku_uid in (KU_DEEP, KU_LIGHT, KU_NEVER):
                await session.run(
                    """
                    CREATE (k:Entity:Ku {uid: $uid, entity_type: 'ku',
                                         title: $uid, status: 'active'})
                    """,
                    uid=ku_uid,
                )
            # One Ku per scored step, so a step's substance is its Ku's and the
            # expected numbers are readable. PS_NO_KU gets none on purpose.
            # CONTAINS_KNOWLEDGE deliberately: it is the arm of the canonical
            # triple the MEGA-QUERY rollup used to omit.
            for ps_uid, ku_uid, edge in (
                (PS_EMBODIED, KU_DEEP, "USES_KU"),
                (PS_APPLIED, KU_LIGHT, "CONTAINS_KNOWLEDGE"),
                (PS_CORPUS_HOT, KU_NEVER, "TRAINS_KU"),
            ):
                await session.run(
                    f"""
                    MATCH (p:Entity {{uid: $ps}}), (k:Entity {{uid: $ku}})
                    MERGE (p)-[:{edge}]->(k)
                    """,
                    ps=ps_uid,
                    ku=ku_uid,
                )

            # The learner's OWN activity — the numerator. All of it completed or
            # archived and 200 days old, i.e. unreachable from any planning
            # window: if the channels are ever re-sourced from a UserContext,
            # every figure in this file collapses to 0.0.
            for count, entity_type, status, ku_uid, edge in LEARNER_ACTIVITY:
                await session.run(
                    f"""
                    MATCH (u:User {{uid: $u}}), (k:Entity {{uid: $ku}})
                    UNWIND range(1, $count) AS i
                    CREATE (a:Entity {{uid: $prefix + toString(i),
                                       entity_type: $entity_type, title: $prefix,
                                       status: $status,
                                       created_at: $stale, updated_at: $stale}})
                    MERGE (u)-[:OWNS]->(a)
                    MERGE (a)-[:{edge}]->(k)
                    """,
                    u=USER,
                    ku=ku_uid,
                    count=count,
                    prefix=f"{entity_type}_{ku_uid}_",
                    entity_type=entity_type,
                    status=status,
                    stale=stale,
                )

            # The tenancy control on the NUMERATOR: another learner grinding the
            # Ku behind PS_CORPUS_HOT must not move this learner's score.
            await session.run(
                """
                MATCH (u:User {uid: $u}), (k:Entity {uid: $ku})
                CREATE (a:Entity {uid: 'other_learner_habit', entity_type: 'habit',
                                  title: 'Their habit', status: 'active'})
                MERGE (u)-[:OWNS]->(a)
                MERGE (a)-[:REINFORCES_KNOWLEDGE]->(k)
                """,
                u=OTHER_USER,
                ku=KU_NEVER,
            )

        # The REAL designation writer: it promotes entity_type in place and
        # leaves the :LearningPath label alone, which is the state that used to
        # make the LP-service read raise.
        designated = await LifePathBackend(Neo4jQueryExecutor(neo4j_driver)).designate_life_path(
            USER, LIFE_PATH, datetime.now(UTC).isoformat()
        )
        assert designated.is_ok, f"designation failed: {designated}"

        return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)

    @staticmethod
    def _service(backend: PsBackend) -> AnalyticsLifePathService:
        """The service under test, wired the way the composition root wires it.

        All three collaborators are REAL over the seeded graph. Stubbing the
        channel read especially would hide what these tests exist for: where the
        channels come from IS the question.
        """
        executor = Neo4jQueryExecutor(backend.driver)
        return AnalyticsLifePathService(
            ku_service=_StubPsService(backend),
            lifepath_service=_LifePathFacadeShim(backend=LifePathBackend(executor)),
            cross_domain_backend=CrossDomainBackend(executor),
        )

    async def test_the_designated_path_is_found_at_all(self, backend, neo4j_driver):
        """The designation survives the promotion that used to break every reader.

        ``designate_life_path`` flips ``entity_type`` to ``'life_path'`` on a node
        that keeps its ``:LearningPath`` label. Reading it back through
        ``LpService`` builds a ``LearningPath`` whose G6 guard rejects the
        mismatched type — so this asserts the composition read, which is keyed on
        the property, returns the path and its steps.
        """
        composition = await LifePathBackend(
            Neo4jQueryExecutor(neo4j_driver)
        ).get_life_path_composition(LIFE_PATH)
        assert composition.is_ok, f"composition read failed: {composition}"
        assert composition.value is not None, (
            "the designated path was not found — a reader keyed on the "
            ":LearningPath label alone, or on entity_type 'learning_path', "
            "sees nothing after designation"
        )

        assert composition.value["life_path_title"] == "Become a mindful engineer"
        assert [step["ps_uid"] for step in composition.value["steps"]] == [
            PS_EMBODIED,
            PS_APPLIED,
            PS_CORPUS_HOT,
            PS_NO_KU,
        ], "steps must arrive in HAS_STEP sequence order"

    async def test_a_step_held_by_two_has_step_edges_counts_once(self, backend, neo4j_driver):
        """Duplicate composition edges must not inflate the denominator.

        ``HAS_STEP`` carries no uniqueness constraint, so a step can end up held
        by two edges. Counted twice it lowers the average by padding the
        denominator with a repeat — an over-return, which reads as a longer path
        rather than as a bug, and which "assert the result is non-empty" cannot
        see.
        """
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (p:Entity {uid: $lp}), (s:Entity {uid: $ps})
                CREATE (p)-[:HAS_STEP {sequence: 99}]->(s)
                """,
                lp=LIFE_PATH,
                ps=PS_EMBODIED,
            )

        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        assert result.value["knowledge_count"] == 4, (
            f"5 = {PS_EMBODIED} counted once per HAS_STEP edge"
        )
        assert result.value["alignment_score"] == pytest.approx(EXPECTED_ALIGNMENT), (
            "0.47 = the duplicate was scored twice, (1.00 + 1.00 + 0.35) / 5"
        )

    async def test_selection_is_the_whole_designated_path(self, backend):
        """Every step of the path counts — engaged or not, applied or not.

        The RULING: a life path is a declaration of who the learner wants to
        become, so its composition IS the denominator. ``PS_CORPUS_HOT`` and
        ``PS_NO_KU`` score 0.0 and stay in it; dropping them would make alignment
        RISE as a learner adds material and does nothing with it.

        ``PS_OFF_PATH`` is the corpus control: it exists, it is a path step, and
        it belongs to a different path.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok, f"alignment failed (pre-fix behaviour on every call): {result}"

        alignment = result.value
        assert alignment["life_path_uid"] == LIFE_PATH
        assert alignment["knowledge_count"] == 4, (
            "5 = the selection ignored HAS_STEP and swept the corpus; "
            "2 = zero-substance steps were dropped from the denominator; "
            "0 = the old property-based read, which found nothing"
        )
        assert {gap["ku_uid"] for gap in alignment["gaps"]} <= ON_PATH
        assert PS_OFF_PATH not in {gap["ku_uid"] for gap in alignment["gaps"]}

    async def test_magnitudes_are_the_learners_own_not_the_corpus(self, backend):
        """The headline number must come from THIS learner's activity channels.

        ``PS_APPLIED`` and ``PS_CORPUS_HOT`` carry IDENTICAL node counters (3
        habits + 5 tasks + 5 events) and differ only in what this learner did, so
        any assertion that separates them is proof the score is personal.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        alignment = result.value
        assert alignment["alignment_score"] == pytest.approx(EXPECTED_ALIGNMENT), (
            "0.0 = the channels arrived empty, i.e. a windowed source dropped "
            "these 200-day-old applications; a figure near 0.5 = the shared "
            "node's counters, which are five other learners' activity"
        )

        by_uid = {gap["ku_uid"]: gap["substance"] for gap in alignment["gaps"]}
        assert by_uid[PS_CORPUS_HOT] == 0.0, (
            "PS_CORPUS_HOT carries the corpus's 'embodied' counters and none of "
            "this learner's activity — it must read as theoretical for them"
        )
        assert by_uid[PS_APPLIED] == pytest.approx(EXPECTED_APPLIED), (
            "identical node counters to PS_CORPUS_HOT — a global reading cannot "
            "produce a different number here"
        )

        assert alignment["embodied_knowledge"] == 1, (
            "PS_EMBODIED is barely substantiated in the corpus (1 habit) and "
            "fully embodied by this learner — a global reading bands it low"
        )
        assert alignment["applied_knowledge"] == 1, "PS_APPLIED at 0.35"
        assert alignment["practiced_knowledge"] == 0
        assert alignment["theoretical_knowledge"] == 2, "PS_CORPUS_HOT and PS_NO_KU"

    async def test_contributions_decompose_the_learners_own_substance(self, backend):
        """``domain_contributions`` is the six channels, and it is real.

        It used to read ``substance_by_type``, an attribute defined nowhere in
        the codebase, so it emitted five zeros — plus ``user_uid`` and
        ``total_substance``, which put a str into a ``dict[str, float]`` that
        ``_generate_recommendations`` then compared ``< 0.1``.

        Proportions normalise against the breakdown's OWN total (1.63), not
        against the summed step scores (1.35): the six channels contribute up to
        1.30 raw per Ku while the score caps at 1.0.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        contributions = result.value["domain_contributions"]
        assert set(contributions) == set(EXPECTED_CONTRIBUTIONS), (
            "six channels exactly — 'user_uid'/'total_substance' present means "
            "the str is back in the float dict; a missing 'principles' means the "
            "five node counters were used instead of the six personal channels"
        )
        assert contributions == pytest.approx(EXPECTED_CONTRIBUTIONS), (
            "habits at 0.37 = normalised against the summed SCORES (1.35) "
            "instead of the summed breakdown (1.63)"
        )

    async def test_the_parts_may_total_more_than_the_whole(self, backend):
        """The cap divergence the contribution maths rests on, asserted directly.

        ``PS_EMBODIED``'s one Ku is applied through all six channels: 0.30 + 0.25
        + 0.25 + 0.20 + 0.14 + 0.14 = 1.28 raw, and the score caps that at 1.00.
        So ``sum(breakdown.values()) > score``, by design — the cap belongs to
        the score, and proportions describe the uncapped decomposition.

        Nothing else pins this. Every other assertion here would still pass if
        the breakdown were rescaled to sum to the score, which would silently
        change what every contribution percentage means.
        """
        scored = await _StubPsService(backend).get_user_substance_breakdowns(
            [PS_EMBODIED], await self._channels(backend)
        )
        assert scored.is_ok, f"scoring failed: {scored}"

        parts = scored.value[PS_EMBODIED]
        assert parts["score"] == pytest.approx(EXPECTED_EMBODIED), (
            "1.28 = the 1.0 cap was dropped from the score"
        )
        assert sum(parts["breakdown"].values()) == pytest.approx(1.28), (
            "1.00 = the breakdown was rescaled to sum to the capped score, which "
            "makes every channel proportion mean something else"
        )

    @staticmethod
    async def _channels(backend: PsBackend):
        """The learner's six channel maps, from the unwindowed source."""
        from core.services.knowledge.user_substance import (
            SUBSTANCE_ACTIVITY_TYPES,
            channel_maps_from_rows,
        )

        rows = await CrossDomainBackend(
            Neo4jQueryExecutor(backend.driver)
        ).get_user_knowledge_channels(USER, list(SUBSTANCE_ACTIVITY_TYPES))
        assert rows.is_ok, f"channel read failed: {rows}"
        return channel_maps_from_rows(rows.value or [])

    async def test_another_learners_activity_does_not_move_this_score(self, backend):
        """The tenancy control on the numerator, not just the denominator.

        ``OTHER_USER`` holds an ACTIVE habit reinforcing ``KU_NEVER`` — the Ku
        behind ``PS_CORPUS_HOT``. The channel read is anchored on
        ``(u:User {uid})-[:OWNS]->``, so that habit must not enter this learner's
        index and the step stays at 0.00 rather than 0.10.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        by_uid = {gap["ku_uid"]: gap["substance"] for gap in result.value["gaps"]}
        assert by_uid[PS_CORPUS_HOT] == 0.0, (
            "0.1 = the OWNS anchor is missing and another learner's habit counted"
        )

    async def test_gaps_are_ranked_least_substantiated_first(self, backend):
        """The under-threshold steps, worst first, so a cap keeps what matters.

        Same 0.5 threshold ``calculate_knowledge_metrics`` ranks
        ``review_recommendations`` against, so the two analytics surfaces cannot
        disagree about which of a learner's steps need work.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        gaps = result.value["gaps"]
        assert {gap["ku_uid"] for gap in gaps} == {PS_CORPUS_HOT, PS_NO_KU, PS_APPLIED}, (
            f"{PS_EMBODIED} present means a 1.00 step was called a gap"
        )
        assert gaps[-1]["ku_uid"] == PS_APPLIED, "0.35 is the least urgent of the three"
        assert [gap["substance"] for gap in gaps] == sorted(gap["substance"] for gap in gaps), (
            "least-substantiated first"
        )

    async def test_recommendations_cover_every_unused_channel(self, backend):
        """All six channels, from the table — the old branch covered three.

        It also raised ``TypeError`` before reaching them: ``user_uid`` sat in
        the contributions dict and was compared ``< 0.1``.
        """
        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok
        assert result.value["recommendations"], "recommendations must not be empty"

        # This learner uses all six channels on the path, so no channel prompt
        # fires; what remains is gap-driven. The complement is asserted below.
        assert any("Increase substance for" in rec for rec in result.value["recommendations"])

    async def test_a_learner_who_uses_no_channel_is_prompted_for_all_six(
        self, backend, neo4j_driver
    ):
        """The complement: an unused channel must produce its own prompt.

        Asserting only the happy path would pass against a recommender that
        never emits channel prompts at all — which is what the old three-branch
        version did for entries, choices and principles.
        """
        bare_user = "user_life_path_no_activity"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=bare_user)
            await session.run(
                """
                CREATE (p:Entity:LearningPath {uid: 'lp_bare', entity_type: 'learning_path',
                                               title: 'Bare path', status: 'active'})
                """
            )
            await session.run(
                """
                MATCH (p:Entity {uid: 'lp_bare'}), (s:Entity {uid: $ps})
                MERGE (p)-[r:HAS_STEP]->(s) SET r.sequence = 0
                """,
                ps=PS_EMBODIED,
            )
        assert (
            await LifePathBackend(Neo4jQueryExecutor(neo4j_driver)).designate_life_path(
                bare_user, "lp_bare", datetime.now(UTC).isoformat()
            )
        ).is_ok

        result = await self._service(backend).calculate_life_path_alignment(bare_user)
        assert result.is_ok

        assert result.value["alignment_score"] == 0.0, (
            "PS_EMBODIED is fully embodied by USER and untouched by this one — "
            "anything above zero means the score is not per-learner"
        )
        recommendations = " ".join(result.value["recommendations"])
        for fragment in ("task", "habit", "practice session", "entry", "choice", "principle"):
            assert fragment in recommendations, (
                f"no prompt for the {fragment} channel — the recommender is "
                "hand-enumerating channels again instead of reading the table"
            )

    async def test_the_payload_carries_no_trends(self, backend, neo4j_driver):
        """A trend over the OTHER metric's history must not be reported as this one's.

        `ALIGNMENT_SNAPSHOT` has exactly one writer —
        `LifePathCoreService.update_alignment_score`, reached from
        `LifePathService.designate_and_calculate`, which stores
        `LifePathAlignmentService.calculate_alignment`'s five-dimension score.
        Those snapshots have never been a history of the per-learner substance
        figure this service computes, so a `direction` derived from them compared
        two different metrics on two different scales.

        The seeded snapshot is the control: it is a *plausible* history (0.90,
        recorded today), so any reader of it produces a confident, wrong trend
        rather than an empty one.
        """
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $u}), (lp:Entity {uid: $lp})
                MERGE (u)-[r:ALIGNMENT_SNAPSHOT {date: date()}]->(lp)
                SET r.score = 0.90, r.recorded_at = datetime()
                """,
                u=USER,
                lp=LIFE_PATH,
            )

        result = await self._service(backend).calculate_life_path_alignment(USER)
        assert result.is_ok

        assert "trends" not in result.value, (
            "the payload reported a trend over five-dimension snapshots while its "
            "headline score is per-learner substance — two metrics, two scales"
        )
        assert result.value["alignment_score"] == pytest.approx(EXPECTED_ALIGNMENT), (
            "0.90 = the snapshot leaked into the headline score itself"
        )

    async def test_a_user_without_a_designation_is_not_an_error(self, backend):
        """No life path is a real state, and it must not read as a failed metric."""
        result = await self._service(backend).calculate_life_path_alignment(OTHER_USER)
        assert result.is_ok

        alignment = result.value
        assert alignment["life_path_uid"] is None
        assert alignment["alignment_score"] == 0.0
        assert alignment["knowledge_count"] == 0
        assert alignment["message"] == "No Life Path designated yet"

    async def test_a_designated_path_with_no_steps_reports_as_such(self, backend, neo4j_driver):
        """A path that composes nothing keeps its title and asks for steps.

        The composition read is OPTIONAL on HAS_STEP precisely so this case is
        distinguishable from "no such path" — an inner MATCH would report a
        stepless path as missing.
        """
        empty_user = "user_life_path_empty"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=empty_user)
            await session.run(
                """
                CREATE (p:Entity:LearningPath {uid: 'lp_stepless',
                                               entity_type: 'learning_path',
                                               title: 'Stepless', status: 'active'})
                """
            )
        assert (
            await LifePathBackend(Neo4jQueryExecutor(neo4j_driver)).designate_life_path(
                empty_user, "lp_stepless", datetime.now(UTC).isoformat()
            )
        ).is_ok

        result = await self._service(backend).calculate_life_path_alignment(empty_user)
        assert result.is_ok

        assert result.value["life_path_title"] == "Stepless"
        assert result.value["message"] == "Life Path has no path steps yet"
        assert result.value["knowledge_count"] == 0

    async def test_a_failed_channel_read_is_not_reported_as_an_unlived_path(self, backend):
        """A failed read must propagate, not degrade to "you applied nothing".

        Empty channels score every step 0.0 — a plausible reading, which is what
        makes it dangerous: it persists as a report saying the learner is living
        none of their life path.
        """

        class _FailingChannelBackend:
            async def get_user_knowledge_channels(self, *_args, **_kwargs):
                return Result.fail(
                    Errors.database(message="simulated Neo4j outage", operation="test")
                )

        executor = Neo4jQueryExecutor(backend.driver)
        service = AnalyticsLifePathService(
            ku_service=_StubPsService(backend),
            lifepath_service=_LifePathFacadeShim(backend=LifePathBackend(executor)),
            cross_domain_backend=_FailingChannelBackend(),
        )

        result = await service.calculate_life_path_alignment(USER)
        assert result.is_error, "a failed channel read was reported as an unlived life path"

    async def test_alignment_refuses_without_a_channel_source(self, backend):
        """No learner activity source, no per-learner figure — refuse.

        The fallback would be ``Curriculum.substance_score()``, i.e. reporting
        the corpus-global number under a per-learner heading. That is the defect
        this module guards; it must not be reachable through an unwired
        dependency.
        """
        executor = Neo4jQueryExecutor(backend.driver)
        service = AnalyticsLifePathService(
            ku_service=_StubPsService(backend),
            lifepath_service=_LifePathFacadeShim(backend=LifePathBackend(executor)),
        )

        result = await service.calculate_life_path_alignment(USER)
        assert result.is_error
