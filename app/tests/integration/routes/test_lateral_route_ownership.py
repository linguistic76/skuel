"""Ownership coverage for the three enhanced-UX lateral read routes.

Covers the routes built by ``LateralRouteFactory`` that render a view rather
than a relationship list:

- GET /api/{domain}/{uid}/lateral/chain
- GET /api/{domain}/{uid}/lateral/alternatives/compare
- GET /api/{domain}/{uid}/lateral/graph

All three previously called ``require_authenticated_user(request)`` and
discarded the return value, then called service methods that accepted no
verifier — so any authenticated user could read another user's blocking chain,
alternatives, or relationship graph by entity UID. These tests pin the closed
form: the route must thread ``user_uid`` AND ``domain_service`` down to the
service, a foreign entity must come back **404** (not 403 — a UID's existence
must not leak), and the ``domain_service is None`` curriculum path must keep
returning data to every user.

The service is real (``LateralRelationshipService``) and only the Neo4j backend
is mocked, so these exercise route → service → ownership gate end to end. A
route that forgets to thread the pair reaches the backend and returns 200,
failing the ``_foreign`` cases.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import Errors, Result

OWNER = "user_owner"
INTRUDER = "user_intruder"
OWNED_UID = "goal_owned_001"

# One row per backend read, shaped as the real Cypher returns them. Enough for
# the service to build a non-empty payload, so a missing ownership gate shows up
# as a 200 with data rather than an incidental empty result.
_CHAIN_ROW = {
    "uid": "goal_blocker",
    "title": "Blocker",
    "entity_type": "goal",
    "status": "active",
    "blocks_count": 1,
    "depth": 1,
}
_ALTERNATIVE_ROW = {
    "uid": "goal_alt",
    "title": "Alternative",
    "entity_type": "goal",
    "status": "active",
    "priority": "medium",
    "description": "Another way",
    "timeframe": "Q3",
    "difficulty": "hard",
    "resources": "budget",
    "tradeoffs": "slower",
    "comparison_criteria": "cost",
    "rel_properties": {"comparison_criteria": "cost", "custom_field": "kept"},
}
_GRAPH_ROW = {
    "center_title": "Owned Goal",
    "center_type": "Goal",
    "center_entity_type": "goal",
    "center_status": "active",
    "related_uid": "goal_neighbour",
    "related_title": "Neighbour",
    "related_type": "Goal",
    "related_entity_type": "goal",
    "related_status": "active",
    "depth_level": 1,
    "relationships": [
        {"from": OWNED_UID, "to": "goal_neighbour", "type": RelationshipName.BLOCKS.value}
    ],
}


def _make_request(user_uid: str | None = OWNER) -> Any:
    """Minimal session-backed request stub for ``require_authenticated_user``."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid} if user_uid is not None else {},
        url=SimpleNamespace(path="/api/goals/x/lateral/chain"),
        query_params={},
        cookies={},
    )


@pytest.fixture
def mock_backend() -> Any:
    """Backend that answers every read with a populated row."""
    backend = MagicMock()
    backend.get_blocking_chain = AsyncMock(return_value=Result.ok([_CHAIN_ROW]))
    backend.get_alternatives_comparison = AsyncMock(return_value=Result.ok([_ALTERNATIVE_ROW]))
    backend.get_relationship_graph = AsyncMock(return_value=Result.ok([_GRAPH_ROW]))
    return backend


@pytest.fixture
def owner_only_service() -> Any:
    """An ``OwnershipVerifier`` where only OWNER owns OWNED_UID."""

    async def verify_ownership(uid: str, user_uid: str) -> Result[Any]:
        if user_uid == OWNER:
            return Result.ok(SimpleNamespace(uid=uid, user_uid=user_uid))
        return Result.fail(Errors.not_found("Goal", uid))

    service = MagicMock()
    service.verify_ownership = AsyncMock(side_effect=verify_ownership)
    return service


def _register(lateral_service: Any, domain_service: Any, domain: str) -> dict[str, Any]:
    """Build the factory's routes and return path → handler."""
    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    factory = LateralRouteFactory(
        domain=domain,
        lateral_service=lateral_service,
        entity_name="Goal" if domain == "goals" else "Path Step",
        domain_service=domain_service,
    )
    factory.register_routes(MagicMock(), rt_collector)
    return registered


@pytest.fixture
def owned_handlers(mock_backend: Any, owner_only_service: Any) -> dict[str, Any]:
    """Routes for a user-owned domain (goals) — ownership enforced."""
    service = LateralRelationshipService(backend=mock_backend)
    return _register(service, owner_only_service, "goals")


@pytest.fixture
def curriculum_handlers(mock_backend: Any) -> dict[str, Any]:
    """Routes for shared curriculum (ps) — ``domain_service`` is None."""
    service = LateralRelationshipService(backend=mock_backend)
    return _register(service, None, "ps")


def _chain(handlers: dict[str, Any], domain: str) -> Any:
    return handlers[f"/api/{domain}/{{uid}}/lateral/chain"]


def _compare(handlers: dict[str, Any], domain: str) -> Any:
    return handlers[f"/api/{domain}/{{uid}}/lateral/alternatives/compare"]


def _graph(handlers: dict[str, Any], domain: str) -> Any:
    return handlers[f"/api/{domain}/{{uid}}/lateral/graph"]


# ============================================================================
# A user who does not own the entity gets not-found
# ============================================================================


class TestForeignEntityIsNotFound:
    """Each route must refuse another user's entity as 404, never 403."""

    async def test_chain_foreign_entity_404(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _chain(owned_handlers, "goals")(
            request=_make_request(INTRUDER), uid=OWNED_UID
        )

        assert response.status_code == 404
        # The gate must run BEFORE the read — no data may be fetched at all.
        mock_backend.get_blocking_chain.assert_not_awaited()

    async def test_comparison_foreign_entity_404(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _compare(owned_handlers, "goals")(
            request=_make_request(INTRUDER), uid=OWNED_UID
        )

        assert response.status_code == 404
        mock_backend.get_alternatives_comparison.assert_not_awaited()

    async def test_graph_foreign_entity_404(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _graph(owned_handlers, "goals")(
            request=_make_request(INTRUDER), uid=OWNED_UID
        )

        assert response.status_code == 404
        mock_backend.get_relationship_graph.assert_not_awaited()

    async def test_foreign_and_missing_are_indistinguishable(
        self, owned_handlers: dict[str, Any], owner_only_service: Any
    ) -> None:
        """The response must not reveal WHICH failure occurred.

        "Not yours" and "does not exist" both surface as the same 404 with the
        same error code and category, so a UID cannot be probed for existence.
        """

        async def missing_for_everyone(uid: str, user_uid: str) -> Result[Any]:
            return Result.fail(Errors.not_found("Goal", uid))

        foreign = await _graph(owned_handlers, "goals")(
            request=_make_request(INTRUDER), uid=OWNED_UID
        )
        foreign_body = json.loads(bytes(foreign.body).decode())

        # Same UID, but now nobody owns it — i.e. it does not exist.
        owner_only_service.verify_ownership = AsyncMock(side_effect=missing_for_everyone)
        missing = await _graph(owned_handlers, "goals")(request=_make_request(OWNER), uid=OWNED_UID)
        missing_body = json.loads(bytes(missing.body).decode())

        assert foreign.status_code == missing.status_code == 404
        assert foreign_body["code"] == missing_body["code"]
        assert foreign_body["category"] == missing_body["category"]
        assert foreign_body["message"] == missing_body["message"]
        # 404, never 403 — nothing may hint that the entity is real but withheld.
        assert "forbidden" not in json.dumps(foreign_body).lower()

    async def test_verifier_is_called_with_the_requesting_user(
        self, owned_handlers: dict[str, Any], owner_only_service: Any
    ) -> None:
        """The route must pass the session user — not a default or None."""
        await _chain(owned_handlers, "goals")(request=_make_request(INTRUDER), uid=OWNED_UID)

        owner_only_service.verify_ownership.assert_awaited_once_with(OWNED_UID, INTRUDER)


# ============================================================================
# The owner still gets their data
# ============================================================================


class TestOwnerStillSucceeds:
    """Threading the verifier must not break the legitimate case."""

    async def test_chain_owner_gets_fragment(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _chain(owned_handlers, "goals")(
            request=_make_request(OWNER), uid=OWNED_UID
        )

        assert response.status_code == 200
        mock_backend.get_blocking_chain.assert_awaited_once()
        assert b"Blocker" in bytes(response.body)

    async def test_comparison_owner_gets_fragment(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _compare(owned_handlers, "goals")(
            request=_make_request(OWNER), uid=OWNED_UID
        )

        assert response.status_code == 200
        mock_backend.get_alternatives_comparison.assert_awaited_once()
        assert b"Alternative" in bytes(response.body)

    async def test_graph_owner_gets_nodes_and_edges(
        self, owned_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _graph(owned_handlers, "goals")(
            request=_make_request(OWNER), uid=OWNED_UID
        )

        assert response.status_code == 200
        payload = json.loads(bytes(response.body).decode())
        assert {node["id"] for node in payload["nodes"]} == {OWNED_UID, "goal_neighbour"}
        assert len(payload["edges"]) == 1
        # The url enrichment that runs after the gate is still applied.
        assert payload["nodes"][0]["url"] is not None

    async def test_comparison_renders_the_built_in_criteria(
        self, owned_handlers: dict[str, Any]
    ) -> None:
        """The comparison table still shows timeframe / difficulty / resources."""
        response = await _compare(owned_handlers, "goals")(
            request=_make_request(OWNER), uid=OWNED_UID, fields="custom_field"
        )

        assert response.status_code == 200
        body = bytes(response.body)
        assert b"Q3" in body and b"hard" in body and b"budget" in body


# ============================================================================
# The call contract: the pair actually reaches the service
# ============================================================================


class TestRouteThreadsTheVerifier:
    """Pin the exact arguments each route hands the service.

    The defect was a route dropping ``user_uid`` on the floor, so assert the
    threading itself — not only its observable 404 — and confirm the
    pre-existing arguments still arrive alongside the new keywords.
    """

    @pytest.fixture
    def spy(self, owner_only_service: Any) -> tuple[Any, dict[str, Any]]:
        lateral = MagicMock()
        lateral.get_blocking_chain = AsyncMock(
            return_value=Result.ok(
                {
                    "root_uid": OWNED_UID,
                    "total_blockers": 0,
                    "chain_depth": 0,
                    "levels": [],
                    "critical_path": [OWNED_UID],
                }
            )
        )
        lateral.get_alternatives_with_comparison = AsyncMock(return_value=Result.ok([]))
        lateral.get_relationship_graph = AsyncMock(
            return_value=Result.ok({"nodes": [], "edges": []})
        )
        return lateral, _register(lateral, owner_only_service, "goals")

    async def test_chain_passes_user_and_verifier(
        self, spy: tuple[Any, dict[str, Any]], owner_only_service: Any
    ) -> None:
        lateral, handlers = spy
        await _chain(handlers, "goals")(request=_make_request(OWNER), uid=OWNED_UID, max_depth=4)

        args, kwargs = lateral.get_blocking_chain.await_args
        assert args == (OWNED_UID, 4)
        assert kwargs == {"user_uid": OWNER, "domain_service": owner_only_service}

    async def test_comparison_passes_user_and_verifier(
        self, spy: tuple[Any, dict[str, Any]], owner_only_service: Any
    ) -> None:
        lateral, handlers = spy
        await _compare(handlers, "goals")(request=_make_request(OWNER), uid=OWNED_UID, fields="a,b")

        args, kwargs = lateral.get_alternatives_with_comparison.await_args
        assert args == (OWNED_UID, ["a", "b"])
        assert kwargs == {"user_uid": OWNER, "domain_service": owner_only_service}

    async def test_graph_passes_user_and_verifier(
        self, spy: tuple[Any, dict[str, Any]], owner_only_service: Any
    ) -> None:
        lateral, handlers = spy
        await _graph(handlers, "goals")(
            request=_make_request(OWNER), uid=OWNED_UID, depth=3, types="BLOCKS"
        )

        args, kwargs = lateral.get_relationship_graph.await_args
        assert args == (OWNED_UID, 3, [RelationshipName.BLOCKS])
        assert kwargs == {"user_uid": OWNER, "domain_service": owner_only_service}

    async def test_curriculum_passes_none_as_the_verifier(self) -> None:
        """The shared path must pass ``domain_service=None``, not omit it."""
        lateral = MagicMock()
        lateral.get_relationship_graph = AsyncMock(
            return_value=Result.ok({"nodes": [], "edges": []})
        )
        handlers = _register(lateral, None, "ps")

        await _graph(handlers, "ps")(request=_make_request(INTRUDER), uid="ps.math.algebra")

        assert lateral.get_relationship_graph.await_args.kwargs["domain_service"] is None


# ============================================================================
# Curriculum (domain_service is None) stays public
# ============================================================================


class TestCurriculumRemainsPublic:
    """KU/PS/LP are shared content: no verifier, no 404 for a non-owner."""

    async def test_chain_public_for_any_user(
        self, curriculum_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _chain(curriculum_handlers, "ps")(
            request=_make_request(INTRUDER), uid="ps.math.algebra"
        )

        assert response.status_code == 200
        mock_backend.get_blocking_chain.assert_awaited_once()

    async def test_comparison_public_for_any_user(
        self, curriculum_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _compare(curriculum_handlers, "ps")(
            request=_make_request(INTRUDER), uid="ps.math.algebra"
        )

        assert response.status_code == 200
        mock_backend.get_alternatives_comparison.assert_awaited_once()

    async def test_graph_public_for_any_user(
        self, curriculum_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        response = await _graph(curriculum_handlers, "ps")(
            request=_make_request(INTRUDER), uid="ps.math.algebra"
        )

        assert response.status_code == 200
        mock_backend.get_relationship_graph.assert_awaited_once()

    async def test_knowledge_dependency_view_still_works(
        self, curriculum_handlers: dict[str, Any], mock_backend: Any
    ) -> None:
        """The Explore sidebar graph: ``?types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE``.

        This is the graph route's second job — a knowledge-dependency view on
        curriculum entities. It must survive the ownership change untouched,
        including the non-lateral type filter.
        """
        response = await _graph(curriculum_handlers, "ps")(
            request=_make_request(INTRUDER),
            uid="ps.math.algebra",
            types="REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE",
        )

        assert response.status_code == 200
        payload = json.loads(bytes(response.body).decode())
        assert payload["nodes"]
        type_filter = mock_backend.get_relationship_graph.await_args.kwargs["type_filter"]
        assert set(type_filter.split("|")) == {"REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE"}

    async def test_invalid_relationship_type_still_400s(
        self, curriculum_handlers: dict[str, Any]
    ) -> None:
        """Validation ordering is unchanged for the no-verifier path."""
        response = await _graph(curriculum_handlers, "ps")(
            request=_make_request(INTRUDER), uid="ps.math.algebra", types="NOT_A_REAL_TYPE"
        )

        assert response.status_code == 400


# ============================================================================
# Unauthenticated is still 401, not 404
# ============================================================================


class TestUnauthenticated:
    async def test_chain_requires_a_session(self, owned_handlers: dict[str, Any]) -> None:
        from starlette.exceptions import HTTPException

        with pytest.raises(HTTPException) as exc:
            await _chain(owned_handlers, "goals")(request=_make_request(None), uid=OWNED_UID)

        assert exc.value.status_code == 401
