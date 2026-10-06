"""The rig the Activity link tests share: a signed-in client, seeds, raw reads.

Each Activity link is one edge read from both of its ends (ADR-090) — a principle-goal
link is ``(Principle)-[:SUPPORTS_GOAL]->(Goal)``, a principle-choice link
``(Principle)-[:INFORMS_CHOICE]->(Choice)``. The tests that hold each link to that run
over the bootstrapped app: its composed services, its routes wired by the bootstrap's
own entry point onto a ``fast_app`` with real session middleware, and its private
graph.

Entities are created at the domains' real create doors, so each carries the label,
the ``entity_type`` and the ownership edge the app itself writes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import httpx
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from neo4j import AsyncDriver

    from core.services.ingestion.types import IncrementalStats

# The edge types that once stored each link, one set per link. A retired type is no
# longer a RelationshipName member (GUIDED_BY_PRINCIPLE stays for the PathStep's use),
# so each is named here as a string.
RETIRED_PRINCIPLE_GOAL = frozenset({"GUIDES_GOAL", "GUIDED_BY_PRINCIPLE"})
RETIRED_PRINCIPLE_CHOICE = frozenset({"GUIDES_CHOICE", "INFORMED_BY_PRINCIPLE"})


class Edge(NamedTuple):
    """One stored edge, as a raw read sees it."""

    type: str
    source: str
    target: str
    properties: dict[str, Any]  # boundary: raw neo4j relationship properties


async def wipe(driver: AsyncDriver, user_uid: str, mark: str) -> None:
    """Remove the user, everything the user owns, and every node or tracker row
    whose uid carries ``mark``."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid = $user OR n.user_uid = $user
               OR n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark
            DETACH DELETE n
            """,
            user=user_uid,
            mark=mark,
        )


def _app(skuel_app: Any) -> tuple[Any, Any]:  # boundary: fasthtml-app
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="activity-link-test-key")

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app, _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )


@asynccontextmanager
async def signed_in_client(
    skuel_app: Any,  # boundary: fasthtml-app
    user_uid: str,
    mark: str,
) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client over every route the bootstrap wires, signed in as ``user_uid``.

    The user is created first and removed, with everything it owns and every node
    marked ``mark``, on exit.
    """
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await wipe(driver, user_uid, mark)
    async with driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=user_uid)
    app, wiring = _app(skuel_app)
    await wiring
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
    ) as http:
        assert (await http.get(f"/sign-in/{user_uid}")).status_code == 200
        yield http
    await wipe(driver, user_uid, mark)


async def create(
    client: httpx.AsyncClient,
    segment: str,
    title: str,
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """Create one entity at ``POST /api/{segment}/create``; returns its uid."""
    body: dict[str, Any] = {"title": title, **fields}  # boundary: JSON body
    # The fields a domain's create request requires beyond a title.
    if segment == "principles":
        body.setdefault("statement", f"{title} statement")
    if segment == "choices":
        body.setdefault("description", f"{title} description")
    response = await client.post(f"/api/{segment}/create", json=body)
    assert response.status_code == 201, (segment, title, response.text)
    return str(response.json()["uid"])


async def seed_published_path_step(driver: AsyncDriver, uid: str, title: str) -> None:
    """A shared PathStep any learner may read: ``publication_state: published``."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Entity:PathStep {uid: $uid})
            SET s.title = $title, s.entity_type = 'path_step', s.status = 'active',
                s.publication_state = 'published'
            """,
            uid=uid,
            title=title,
        )


async def write_edge(
    driver: AsyncDriver,
    source: str,
    edge_type: str,
    target: str,
    properties: dict[str, Any] | None = None,  # boundary: raw neo4j relationship properties
) -> None:
    """MERGE one edge between two existing nodes and set its properties."""
    async with driver.session() as session:
        record = await (
            await session.run(
                f"""
                MATCH (a {{uid: $source}}), (b {{uid: $target}})
                MERGE (a)-[r:{edge_type}]->(b)
                SET r += $properties
                RETURN count(r) AS written
                """,
                source=source,
                target=target,
                properties=properties or {},
            )
        ).single()
    assert record is not None and record["written"] == 1, (source, edge_type, target)


async def edges_between(driver: AsyncDriver, one: str, other: str) -> list[Edge]:
    """Every edge joining the two nodes, in either direction."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a {uid: $one})-[r]-(b {uid: $other})
            RETURN DISTINCT elementId(r) AS id, type(r) AS type,
                   startNode(r).uid AS source, endNode(r).uid AS target,
                   properties(r) AS properties
            ORDER BY type, source
            """,
            one=one,
            other=other,
        )
        return [
            Edge(row["type"], row["source"], row["target"], dict(row["properties"]))
            async for row in result
        ]


def write_vault_file(
    vault: Path,
    name: str,
    *,
    entity_type: str,
    uid: str,
    owner: str,
    connections: dict[str, list[str]] | None = None,
    extra: tuple[str, ...] = (),
) -> Path:
    """One frontmatter file declaring an entity and, optionally, its ``connections``."""
    lines = [f"type: {entity_type}", f"uid: {uid}", f"title: {name}", f"user_uid: {owner}", *extra]
    if entity_type == "principle":
        lines.append(f"statement: {name} statement")
    if connections:
        lines.append("connections:")
        for field, targets in connections.items():
            lines.append(f"  {field}:")
            lines.extend(f"    - {target}" for target in targets)
    path = vault / f"{name}.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
    return path


async def sync_vault(driver: AsyncDriver, vault: Path, *, force: bool = False) -> IncrementalStats:
    """One smart directory sync of ``vault`` into the graph, with the tracker wired.

    ``force`` re-processes files the tracker holds as unchanged.
    """
    service = make_unified_ingestion_service(
        driver=driver, ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(driver))
    )
    result = await service.ingest_directory(vault, ingestion_mode="smart", force=force)
    assert result.is_ok, f"sync failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert not stats.errors, f"sync errors: {stats.errors}"
    return stats


def under_heading(html: str, heading: str, closing: str = "</ul>") -> str:
    """The markup between ``heading`` and the first ``closing`` tag after it."""
    start = html.find(heading)
    assert start != -1, f"no {heading!r} on the page"
    return html[start : html.index(closing, start)]
