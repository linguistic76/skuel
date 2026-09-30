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

from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
from neo4j import AsyncDriver
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
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


@dataclass
class RoleUserService:
    """Real ``User`` records, so the role hierarchy check runs for real.

    ``calls`` records every uid looked up — an Activity route that consults no
    role leaves it empty.
    """

    roles: dict[str, UserRole]
    calls: list[str] = field(default_factory=list)

    async def get_user(self, user_uid: str) -> Result[User]:
        self.calls.append(user_uid)
        role = self.roles.get(user_uid)
        if role is None:
            return Result.fail(Errors.not_found("User"))
        return Result.ok(User(uid=user_uid, title=user_uid, role=role))


@dataclass(frozen=True)
class OwnedTask:
    """What the verifier hands back for a task the caller owns."""

    uid: str
    user_uid: str


@dataclass
class TaskVerifier:
    """The Tasks domain's ownership verifier: each task belongs to its ``user_uid``."""

    owners: dict[str, str]

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[OwnedTask]:
        if self.owners.get(uid) == user_uid:
            return Result.ok(OwnedTask(uid=uid, user_uid=user_uid))
        return Result.fail(Errors.not_found("Task"))


def lateral_client(
    neo4j_driver: AsyncDriver,
    user_service: RoleUserService,
    task_owners: dict[str, str],
    secret_key: str,
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
    tasks = TaskVerifier(task_owners)
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
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    )


def without_timestamp(response: httpx.Response) -> dict[str, object]:
    """A JSON error body with its per-request timestamp removed, for parity checks."""
    body: dict[str, object] = response.json()
    body.pop("timestamp", None)
    return body
