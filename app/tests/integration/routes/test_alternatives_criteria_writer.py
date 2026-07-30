"""The comparison axis has a writer, end to end (testcontainer Neo4j).

PR #877 measured that ``timeframe`` / ``difficulty`` / ``resources`` render as
"N/A" in every alternatives grid because **no code path writes them** onto an
``ALTERNATIVE_TO`` edge. The reader, the service and the renderer were all
correct; the edge was simply blank. This module pins the writer that closes
that gap.

Nothing here is stubbed between the POST and the rendered table: the real
``create_alternative`` handler writes to a real Neo4j, and the real
``get_comparison`` handler reads it back through the real service and the real
``render_alternatives_fragment``. A writer that persists the value but a reader
that cannot project it — or a renderer that drops it — fails here, which a
service-level assertion on ``comparison_data`` would not.

The suppression guard is the point of ``test_edge_carries_created_by_but_table_does_not``:
the same edge that carries the three criteria also carries ``created_by``, and
that one must NOT reach the table. Asserting absence alone is vacuous (an edge
with no properties would pass), so the test first proves the property really is
on the edge in the graph, then proves it is missing from the render.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory
from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import Errors, Result

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = "user_alt_owner"
SOURCE_UID = "goal_alt_source"
TARGET_UID = "goal_alt_target"
_FIXTURE_UIDS = [SOURCE_UID, TARGET_UID]

# Distinctive values — a substring match on the rendered HTML must not be able
# to pass on incidental page furniture.
AUTHORED_TIMEFRAME = "about 18 months"
AUTHORED_DIFFICULTY = "steep at first"
AUTHORED_RESOURCES = "one mentor plus a rowing machine"


def _make_request(user_uid: str | None = OWNER, method: str = "GET") -> Any:
    """Session-backed request stub that also satisfies ``@csrf_protected``.

    The cookie/header pair is minted from the real ``csrf`` module, so these
    tests pass whether or not ``SKUEL_CSRF_ENFORCE`` is set in the environment.
    """
    token = mint_token()
    return SimpleNamespace(
        method=method,
        session={"user_uid": user_uid} if user_uid is not None else {},
        url=SimpleNamespace(path=f"/api/goals/{SOURCE_UID}/lateral/alternatives"),
        query_params={},
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    )


@pytest.fixture
def owner_only_service() -> Any:
    """An ``OwnershipVerifier`` where only OWNER owns the fixture entities."""

    async def verify_ownership(uid: str, user_uid: str) -> Result[Any]:
        if user_uid == OWNER:
            return Result.ok(SimpleNamespace(uid=uid, user_uid=user_uid))
        return Result.fail(Errors.not_found("Goal", uid))

    service = MagicMock()
    service.verify_ownership = AsyncMock(side_effect=verify_ownership)
    return service


@pytest.fixture
def handlers(neo4j_driver, owner_only_service: Any) -> dict[tuple[str, str], Any]:
    """Real routes over a real backend, keyed by (path, method).

    Keying on the pair matters: ``POST`` and ``GET`` share the
    ``/lateral/alternatives`` path, so a path-only collector would silently
    keep whichever registered last.
    """
    backend = LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    service = LateralRelationshipService(backend=backend)

    registered: dict[tuple[str, str], Any] = {}

    def rt_collector(path: str, *_a: Any, **kwargs: Any) -> Any:
        methods = kwargs.get("methods") or ["GET"]

        def decorator(fn: Any) -> Any:
            for method in methods:
                registered[(path, method)] = fn
            return fn

        return decorator

    factory = LateralRouteFactory(
        domain="goals",
        lateral_service=service,
        entity_name="Goal",
        domain_service=owner_only_service,
    )
    factory.register_routes(MagicMock(), rt_collector)
    return registered


def _create(handlers: dict[tuple[str, str], Any]) -> Any:
    return handlers[("/api/goals/{uid}/lateral/alternatives", "POST")]


def _compare(handlers: dict[tuple[str, str], Any]) -> Any:
    return handlers[("/api/goals/{uid}/lateral/alternatives/compare", "GET")]


@pytest_asyncio.fixture(loop_scope="session")
async def two_goals(neo4j_driver):
    """Two flat, parentless goals — same depth, so ALTERNATIVE_TO validates."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Goal {uid: $source, title: 'Row the Atlantic',
                                  entity_type: 'goal', status: 'active',
                                  priority: 'high', description: 'By boat'})
            CREATE (:Entity:Goal {uid: $target, title: 'Cycle the Andes',
                                  entity_type: 'goal', status: 'active',
                                  priority: 'medium', description: 'By bike'})
            """,
            source=SOURCE_UID,
            target=TARGET_UID,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS
        )


async def _author_alternative(handlers: dict[tuple[str, str], Any], **criteria: str) -> Any:
    """POST the real create route with the three criteria."""
    return await _create(handlers)(
        request=_make_request(OWNER, method="POST"),
        uid=SOURCE_UID,
        target_uid=TARGET_UID,
        comparison_criteria="cost vs. time",
        **criteria,
    )


class TestAuthoredCriteriaReachTheTable:
    """POST → Neo4j → GET → rendered HTML, with nothing mocked in between."""

    async def test_all_three_criteria_render(
        self, handlers: dict[tuple[str, str], Any], two_goals
    ) -> None:
        """The whole point: what an author types is what the grid shows."""
        created = await _author_alternative(
            handlers,
            timeframe=AUTHORED_TIMEFRAME,
            difficulty=AUTHORED_DIFFICULTY,
            resources=AUTHORED_RESOURCES,
        )
        assert created.status_code == 201

        response = await _compare(handlers)(request=_make_request(OWNER), uid=SOURCE_UID)

        assert response.status_code == 200
        body = bytes(response.body).decode()
        # Positive control: the alternative itself came back, so a missing
        # criterion below is a criterion failure, not an empty result.
        assert "Cycle the Andes" in body
        assert AUTHORED_TIMEFRAME in body
        assert AUTHORED_DIFFICULTY in body
        assert AUTHORED_RESOURCES in body

    async def test_unauthored_criterion_stays_na_and_writes_no_property(
        self, handlers: dict[tuple[str, str], Any], two_goals, neo4j_driver
    ) -> None:
        """Omitting a criterion must leave the edge clean, not store "".

        An empty string would satisfy the renderer's ``.get(criterion, "N/A")``
        fallback only by accident — it would render as a blank cell rather than
        "N/A", and it would create the property key on the edge. Assert the
        property is genuinely absent.
        """
        await _author_alternative(handlers, timeframe=AUTHORED_TIMEFRAME)

        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (:Entity {uid: $source})-[r:ALTERNATIVE_TO]-(:Entity {uid: $target})
                RETURN r.timeframe AS timeframe,
                       'difficulty' IN keys(r) AS has_difficulty,
                       'resources' IN keys(r) AS has_resources
                """,
                source=SOURCE_UID,
                target=TARGET_UID,
            )
            record = await result.single()

        # Positive control for the two absence checks on the same edge.
        assert record["timeframe"] == AUTHORED_TIMEFRAME
        assert record["has_difficulty"] is False
        assert record["has_resources"] is False

        response = await _compare(handlers)(request=_make_request(OWNER), uid=SOURCE_UID)
        assert b"N/A" in bytes(response.body)

    async def test_edge_carries_created_by_but_table_does_not(
        self, handlers: dict[tuple[str, str], Any], two_goals, neo4j_driver
    ) -> None:
        """#877's guard, proved against the real graph rather than a stub row.

        The create route stamps ``created_by`` (a user UID) onto the edge. The
        comparison Cypher deliberately does not project it, so it cannot reach
        the fragment. Proving it IS on the edge first is what keeps the absence
        assertion from being vacuous.
        """
        await _author_alternative(handlers, timeframe=AUTHORED_TIMEFRAME)

        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (:Entity {uid: $source})-[r:ALTERNATIVE_TO]-(:Entity {uid: $target})
                RETURN r.created_by AS created_by
                """,
                source=SOURCE_UID,
                target=TARGET_UID,
            )
            record = await result.single()

        # The property really is on the edge — the absence check below is real.
        assert record["created_by"] == OWNER

        response = await _compare(handlers)(request=_make_request(OWNER), uid=SOURCE_UID)
        body = bytes(response.body)
        assert AUTHORED_TIMEFRAME.encode() in body  # positive control
        assert OWNER.encode() not in body


class TestCriteriaDescribeOneEndpoint:
    """The criteria are not symmetric even though the edge is.

    ALTERNATIVE_TO is symmetric and the comparison Cypher matches it undirected,
    so both entities list each other. The criteria, though, are authored about
    the target — projecting them from either side would show the target's
    timeframe under the *source's* column on the far entity's page.
    """

    async def test_far_endpoint_does_not_inherit_the_criteria(
        self, handlers: dict[tuple[str, str], Any], two_goals
    ) -> None:
        """Authored on A→B, B's page must not attribute them to A."""
        await _author_alternative(
            handlers,
            timeframe=AUTHORED_TIMEFRAME,
            difficulty=AUTHORED_DIFFICULTY,
            resources=AUTHORED_RESOURCES,
        )

        far = await _compare(handlers)(request=_make_request(OWNER), uid=TARGET_UID)
        body = bytes(far.body).decode()

        # Positive control: the far page DOES list the pairing, so the absences
        # below are the gate working — not an empty result.
        assert far.status_code == 200
        assert "Row the Atlantic" in body
        assert AUTHORED_TIMEFRAME not in body
        assert AUTHORED_DIFFICULTY not in body
        assert AUTHORED_RESOURCES not in body
        assert "N/A" in body

    async def test_authoring_end_still_shows_them(
        self, handlers: dict[tuple[str, str], Any], two_goals
    ) -> None:
        """The gate must not suppress the side that authored them."""
        await _author_alternative(handlers, timeframe=AUTHORED_TIMEFRAME)

        near = await _compare(handlers)(request=_make_request(OWNER), uid=SOURCE_UID)

        assert AUTHORED_TIMEFRAME.encode() in bytes(near.body)


class TestResubmitClearsBlankedCriteria:
    """``MERGE`` + ``SET r += $metadata`` keeps keys absent from the map.

    Re-selecting an already-related target is reachable — the picker only
    excludes the current entity — so a criterion cleared in the form has to be
    sent as null, or the stale value survives and the grid keeps showing it.
    """

    async def test_blanking_a_criterion_removes_it(
        self, handlers: dict[tuple[str, str], Any], two_goals, neo4j_driver
    ) -> None:
        await _author_alternative(
            handlers,
            timeframe=AUTHORED_TIMEFRAME,
            difficulty=AUTHORED_DIFFICULTY,
        )
        # Re-submit the same pair with difficulty cleared and timeframe changed.
        await _author_alternative(handlers, timeframe="now much shorter", difficulty="")

        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (:Entity {uid: $source})-[r:ALTERNATIVE_TO]-(:Entity {uid: $target})
                RETURN r.timeframe AS timeframe, 'difficulty' IN keys(r) AS has_difficulty
                """,
                source=SOURCE_UID,
                target=TARGET_UID,
            )
            record = await result.single()

        # Positive control: the edge was genuinely rewritten by the second post.
        assert record["timeframe"] == "now much shorter"
        assert record["has_difficulty"] is False

        response = await _compare(handlers)(request=_make_request(OWNER), uid=SOURCE_UID)
        body = bytes(response.body).decode()
        assert AUTHORED_DIFFICULTY not in body
        assert "now much shorter" in body


class TestOwnershipIsUnchanged:
    """The writer must not loosen the read gate #877 and its predecessor set."""

    async def test_foreign_reader_still_gets_404(
        self, handlers: dict[tuple[str, str], Any], two_goals
    ) -> None:
        await _author_alternative(handlers, timeframe=AUTHORED_TIMEFRAME)

        response = await _compare(handlers)(request=_make_request("user_intruder"), uid=SOURCE_UID)

        assert response.status_code == 404
        assert AUTHORED_TIMEFRAME.encode() not in bytes(response.body)
