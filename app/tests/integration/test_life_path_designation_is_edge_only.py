"""
The designation lives on the edge, and the path keeps its identity.
===================================================================

LIFEPATH_ALIGNMENT_DEBT item 2. Designation used to promote a LearningPath by
flipping its ``entity_type`` to ``'life_path'`` **in place** while leaving the
``:LearningPath`` label untouched. Label and discriminator then disagreed
permanently, and it cost three separate things:

1. **The title.** ``LpBackend`` MATCHes ``(n:LearningPath {uid})``, still found
   the node, then built a ``LearningPath`` from it — tripping that model's
   honest-leaf-identity guard (G6). ``@safe_backend_operation``'s safety net
   converted the ``ValueError`` into a ``Result.fail`` indistinguishable from a
   database outage, so ``_get_life_path_details`` took its fallback and the
   alignment payload named every designated learner's path **"Unknown"**.
2. **Re-designation.** The writer MATCHed its target only while ``entity_type``
   was still ``'learning_path'``, so designating the same path twice failed —
   which also meant a caller could not retry after a mid-flow failure.
3. **Vault re-sync.** Bulk ingest is
   ``MERGE (n:Entity:LearningPath {uid}) ... ON MATCH SET n += props`` and
   ``props`` carries ``entity_type: 'learning_path'``, so re-ingesting an
   authored LP silently UN-designated it for every property-keyed reader while
   the ``ULTIMATE_PATH`` edge survived.

⚠ **The invariant asserted here is the TITLE, not any particular reader.** The
debt file lays out three options and they disagree about which reader should
succeed while designated; asserting "``LpService.get`` works" would have ruled
out the label-swap option by construction. What all three share — and what the
production wiring actually needs — is that the alignment payload carries the
path's real title and survives a ``remove_designation`` round trip.

A score-movement test cannot see any of this: all five dimensions return
numbers either way.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.learning_path import LearningPath
from core.services.lifepath.lifepath_alignment_service import LifePathAlignmentService
from core.services.user.unified_user_context import UserContext

USER = "user_lp_designation_edge"
OTHER_USER = "user_lp_designation_edge_other"

LP = "lp.test.designation.primary"
LP_SECOND = "lp.test.designation.second"

TITLE = "Become a mindful engineer"
TITLE_SECOND = "Learn to sail"


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j):
    """Two undesignated LearningPaths and two users."""
    async with neo4j_driver.session() as session:
        for uid in (USER, OTHER_USER):
            await session.run("MERGE (u:User {uid: $u})", u=uid)
        for lp_uid, title in ((LP, TITLE), (LP_SECOND, TITLE_SECOND)):
            await session.run(
                """
                CREATE (lp:Entity:LearningPath {uid: $lp, entity_type: 'learning_path',
                                                title: $title, status: 'active'})
                """,
                lp=lp_uid,
                title=title,
            )
    return neo4j_driver


def _backend(driver) -> LifePathBackend:
    return LifePathBackend(Neo4jQueryExecutor(driver))


def _lp_backend(driver) -> LpBackend:
    return LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)


def _alignment(driver) -> LifePathAlignmentService:
    executor = Neo4jQueryExecutor(driver)
    return LifePathAlignmentService(
        backend=LifePathBackend(executor),
        lp_service=_LpServiceShim(_lp_backend(driver)),
        cross_domain_backend=CrossDomainBackend(executor),
    )


class _LpServiceShim:
    """The one attribute path ``_get_life_path_details`` uses: ``.core.get``.

    Composing the whole LpService facade would drag in PS, graph intelligence
    and an event bus for a single delegation. What must be REAL is the backend
    underneath — that is where the model is built and where the G6 guard fires.
    """

    def __init__(self, backend: LpBackend) -> None:
        self.core = backend


@pytest.mark.asyncio
class TestTheDesignatedPathKeepsItsTitle:
    async def test_the_alignment_payload_carries_the_real_title(self, graph):
        """THE invariant. It read "Unknown" for every designated learner."""
        assert (
            await _backend(graph).designate_life_path(USER, LP, datetime.now(UTC).isoformat())
        ).is_ok

        result = await _alignment(graph).calculate_alignment(UserContext(user_uid=USER))

        assert result.is_ok, f"alignment failed: {result}"
        assert result.value["life_path_title"] == TITLE, (
            "'Unknown' = the designated node no longer reads as a LearningPath, "
            "so the LP read failed and _get_life_path_details took its fallback"
        )

    async def test_the_title_survives_a_remove_designation_round_trip(self, graph):
        """Where a half-implemented promotion breaks: on the way back.

        The old writer reverted ``entity_type`` on removal, so a promotion that
        also swapped a label — or any state the removal did not fully undo —
        would strand the node in a shape no reader agrees on.
        """
        backend = _backend(graph)
        assert (await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())).is_ok
        assert (await backend.remove_designation(USER)).is_ok

        # Undesignated, so the path must read as an ordinary LearningPath again.
        read_back = await _lp_backend(graph).get(LP)
        assert read_back.is_ok, f"the path did not survive the round trip: {read_back}"
        assert read_back.value is not None
        assert read_back.value.title == TITLE

        # And the designation is genuinely gone, not merely unreadable.
        designation = await backend.get_user_life_path(USER)
        assert designation.is_ok
        assert not (designation.value or []), "remove_designation left the edge behind"

    async def test_a_designated_path_still_reads_through_the_lp_service(self, graph):
        """Ruling (b)'s distinguishing consequence, asserted deliberately.

        Under the label-swap option this read SHOULD miss; under ruling (b) the
        node never stops being a LearningPath, so it must not. This assertion is
        therefore option-specific on purpose — it pins the ruling that was
        taken, while the title test above pins the invariant every option shares.
        """
        assert (
            await _backend(graph).designate_life_path(USER, LP, datetime.now(UTC).isoformat())
        ).is_ok

        read = await _lp_backend(graph).get(LP)

        assert read.is_ok, (
            "designation made the path unreadable as a LearningPath — the G6 "
            "raise, converted by the safety net into an outage-shaped failure"
        )
        assert read.value is not None
        assert read.value.title == TITLE

    async def test_designation_leaves_the_node_untouched(self, graph):
        """Label AND discriminator both unchanged — nothing to disagree about."""
        assert (
            await _backend(graph).designate_life_path(USER, LP, datetime.now(UTC).isoformat())
        ).is_ok

        async with graph.session() as session:
            result = await session.run(
                "MATCH (lp:Entity {uid: $lp}) RETURN lp.entity_type AS t, labels(lp) AS labels",
                lp=LP,
            )
            record = await result.single()

        assert record is not None
        assert record["t"] == "learning_path", "the in-place entity_type mutation is back"
        assert set(record["labels"]) == {"Entity", "LearningPath"}


@pytest.mark.asyncio
class TestDesignationIsIdempotentAndSingular:
    async def test_designating_the_same_path_twice_succeeds(self, graph):
        """The old writer matched only entity_type 'learning_path', so the
        second call found nothing and failed — which also blocked any retry
        after a mid-flow failure in ``designate_and_calculate``."""
        backend = _backend(graph)
        first = await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())
        assert first.is_ok

        second = await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())

        assert second.is_ok, "re-designating the same path failed — retry is impossible"
        assert (second.value or [])[0]["life_path_uid"] == LP

    async def test_re_designating_preserves_the_original_timestamp(self, graph):
        """Re-designation is a no-op, not a delete-and-recreate.

        ``designated_at`` is when the learner committed to this path; a second
        call for the same path must not silently restart that clock.
        """
        backend = _backend(graph)
        original = "2026-01-01T00:00:00+00:00"
        assert (await backend.designate_life_path(USER, LP, original)).is_ok
        assert (await backend.designate_life_path(USER, LP, "2026-08-12T00:00:00+00:00")).is_ok

        async with graph.session() as session:
            result = await session.run(
                """
                MATCH (:User {uid: $u})-[r:ULTIMATE_PATH]->(:Entity {uid: $lp})
                RETURN r.designated_at AS designated_at
                """,
                u=USER,
                lp=LP,
            )
            record = await result.single()

        assert record is not None
        assert record["designated_at"] == original, "the commitment date was reset"

    async def test_the_service_reports_the_preserved_timestamp(self, graph):
        """The facade must not report `now` for a designation it did not make.

        The writer preserves ``designated_at``; a service that stamps its own
        clock instead would tell the caller the commitment had just been made.
        """
        from core.services.lifepath.lifepath_core_service import LifePathCoreService

        service = LifePathCoreService(backend=_backend(graph))
        first = await service.designate_life_path(USER, LP)
        assert first.is_ok
        original = first.value.designated_at

        second = await service.designate_life_path(USER, LP)

        assert second.is_ok
        assert second.value.designated_at == original, (
            "re-designation reported a fresh timestamp while the edge kept the "
            "original — two answers to when the learner committed"
        )

    async def test_designating_a_second_path_replaces_the_first(self, graph):
        """One life path per user — and the displaced path stays usable."""
        backend = _backend(graph)
        assert (await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())).is_ok
        assert (
            await backend.designate_life_path(USER, LP_SECOND, datetime.now(UTC).isoformat())
        ).is_ok

        designation = await backend.get_user_life_path(USER)
        assert designation.is_ok
        assert [row["life_path_uid"] for row in (designation.value or [])] == [LP_SECOND]

        # The displaced path is an ordinary LearningPath again — under the old
        # writer this depended on a revert that ran only when it matched.
        displaced = await _lp_backend(graph).get(LP)
        assert displaced.is_ok and displaced.value is not None
        assert displaced.value.title == TITLE

    async def test_two_users_can_designate_the_same_path(self, graph):
        """A shared curriculum path is not consumed by the first learner.

        The old writer flipped a GLOBAL node property, so the first designation
        made the path undesignatable by anyone else — and one learner removing
        their designation reverted a property the other still depended on.
        """
        backend = _backend(graph)
        assert (await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())).is_ok
        assert (
            await backend.designate_life_path(OTHER_USER, LP, datetime.now(UTC).isoformat())
        ).is_ok

        for user_uid in (USER, OTHER_USER):
            designation = await backend.get_user_life_path(user_uid)
            assert designation.is_ok
            assert [row["life_path_uid"] for row in (designation.value or [])] == [LP], (
                f"{user_uid} lost their designation to the other learner"
            )

        # One removing theirs must not disturb the other.
        assert (await backend.remove_designation(USER)).is_ok
        still_designated = await backend.get_user_life_path(OTHER_USER)
        assert still_designated.is_ok
        assert [row["life_path_uid"] for row in (still_designated.value or [])] == [LP]


@pytest.mark.asyncio
class TestAVaultResyncDoesNotUndesignate:
    async def test_re_ingesting_the_path_leaves_the_designation_intact(self, graph):
        """The hazard that decided the ruling.

        LearningPaths are vault-authored (``lp:{ns}:{slug}``) and bulk ingest is
        ``MERGE (n:Entity:LearningPath {uid}) ... ON MATCH SET n += props`` with
        ``props`` carrying ``entity_type: 'learning_path'``. Against the old
        writer that reverted the promotion on the next content sync, silently
        un-designating the path for every property-keyed reader while the
        ``ULTIMATE_PATH`` edge survived — designation and dashboard disagreeing
        with no error anywhere.
        """
        backend = _backend(graph)
        assert (await backend.designate_life_path(USER, LP, datetime.now(UTC).isoformat())).is_ok

        # Exactly what the ingest upsert does to an existing node.
        async with graph.session() as session:
            await session.run(
                """
                MERGE (n:Entity:LearningPath {uid: $uid})
                  ON MATCH SET n += {entity_type: 'learning_path', title: $title,
                                     status: 'active'}
                """,
                uid=LP,
                title=TITLE,
            )

        result = await _alignment(graph).calculate_alignment(UserContext(user_uid=USER))

        assert result.is_ok
        assert result.value["life_path_uid"] == LP, (
            "the content sync un-designated the path: the designation lived on a "
            "node property that ingestion overwrites"
        )
        assert result.value["life_path_title"] == TITLE
