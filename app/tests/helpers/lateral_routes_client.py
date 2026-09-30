"""The lateral routes over real HTTP against a real Neo4j.

A real ``fast_app`` with session middleware, reached through
``httpx.ASGITransport``, with the routes registered through
``create_lateral_routes`` — the bootstrap's own entry point — so the role, the
verifier and the curriculum marker reach ``LateralRouteFactory`` exactly as they
do in the app. The service and the backend are real; only the user service and
the six Activity verifiers are stand-ins, and both keep their real contracts (a
``User`` record with a role; ``verify_ownership`` answering not-found).

Shared by the curriculum lateral write-gate and read-anchor tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.lateral_routes import create_lateral_routes
from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums import UserRole
from core.models.user.user import User
from core.orchestrator.lateral_relationships_orchestrator import (
    LateralRelationshipsOrchestrator,
)
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import Errors, Result


def role_user_service(roles: dict[str, UserRole]) -> Any:
    """Real ``User`` records, so the role hierarchy check runs for real.

    ``.calls`` records every uid looked up — an Activity route that consults
    no role leaves it empty.
    """
    calls: list[str] = []

    async def get_user(user_uid: str) -> Result[User]:
        calls.append(user_uid)
        role = roles.get(user_uid)
        if role is None:
            return Result.fail(Errors.not_found("User"))
        return Result.ok(User(uid=user_uid, title=user_uid, role=role))

    return SimpleNamespace(get_user=get_user, calls=calls)


def task_verifier(owners: dict[str, str]) -> Any:
    """The Tasks domain's ownership verifier: each task belongs to its ``user_uid``."""

    async def verify_ownership(uid: str, user_uid: str) -> Result[Any]:
        if owners.get(uid) == user_uid:
            return Result.ok(SimpleNamespace(uid=uid, user_uid=user_uid))
        return Result.fail(Errors.not_found("Task"))

    return SimpleNamespace(verify_ownership=verify_ownership)


def lateral_client(
    neo4j_driver: Any, user_service: Any, task_owners: dict[str, str], secret_key: str
) -> httpx.AsyncClient:
    """An HTTP client over the lateral routes, signed out.

    ``GET /sign-in/{uid}`` opens a session as that user. The CSRF cookie and
    header are pre-set so the write routes are reachable.
    """
    from fasthtml.common import fast_app

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key=secret_key)
    lateral = LateralRelationshipService(
        LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )
    tasks = task_verifier(task_owners)
    orchestrator = LateralRelationshipsOrchestrator(
        lateral,
        tasks,  # type: ignore[arg-type]
        tasks,  # type: ignore[arg-type]
        tasks,  # type: ignore[arg-type]
        tasks,  # type: ignore[arg-type]
        tasks,  # type: ignore[arg-type]
        tasks,  # type: ignore[arg-type]
    )
    services = SimpleNamespace(lateral_orchestrator=orchestrator, user=user_service)
    create_lateral_routes(app, rt, services)

    @rt("/sign-in/{uid}")
    def sign_in(request, uid: str):
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    )


def without_timestamp(response: httpx.Response) -> Any:
    """A JSON error body with its per-request timestamp removed, for parity checks."""
    body = response.json()
    body.pop("timestamp", None)
    return body
