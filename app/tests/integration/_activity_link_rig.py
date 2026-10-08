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

import os
from contextlib import asynccontextmanager, contextmanager
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
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from neo4j import AsyncDriver

    from core.ports import EventBusOperations
    from core.services.ingestion.types import IncrementalStats

# The edge types that once stored each link, one set per link. A retired type is no
# longer a RelationshipName member (GUIDED_BY_PRINCIPLE stays for the PathStep's use),
# so each is named here as a string.
RETIRED_PRINCIPLE_GOAL = frozenset({"GUIDES_GOAL", "GUIDED_BY_PRINCIPLE"})
RETIRED_PRINCIPLE_CHOICE = frozenset({"GUIDES_CHOICE", "INFORMED_BY_PRINCIPLE"})
# Event ↔ principle is the event's DEMONSTRATES_PRINCIPLE; event ↔ habit its REINFORCES_HABIT.
RETIRED_PRACTICED = frozenset({"PRACTICED_AT_EVENT"})


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


async def seed_published_learning_path(driver: AsyncDriver, uid: str, title: str) -> None:
    """A shared LearningPath any learner may read: ``publication_state: published``."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Entity:LearningPath {uid: $uid})
            SET p.title = $title, p.entity_type = 'learning_path', p.status = 'active',
                p.publication_state = 'published'
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


async def goals_contributed_to(driver: AsyncDriver, contributor_uid: str) -> set[str]:
    """The goals a task or event contributes to (``CONTRIBUTES_TO_GOAL``)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $uid})-[:CONTRIBUTES_TO_GOAL]->(g:Goal) RETURN g.uid AS uid",
            uid=contributor_uid,
        )
        return {row["uid"] async for row in result}


async def goal_contributors(driver: AsyncDriver, goal_uid: str) -> set[str]:
    """The tasks and events contributing to a goal (``CONTRIBUTES_TO_GOAL``)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Entity)-[:CONTRIBUTES_TO_GOAL]->(:Goal {uid: $uid}) RETURN c.uid AS uid",
            uid=goal_uid,
        )
        return {row["uid"] async for row in result}


async def goal_tally(driver: AsyncDriver, goal_uid: str) -> tuple[float | None, float | None]:
    """A goal's stored tally: (completed contributions, all counted contributions)."""
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (g:Goal {uid: $uid}) RETURN g.current_value AS done, g.target_value AS total",
                uid=goal_uid,
            )
        ).single()
    assert record is not None, goal_uid
    return record["done"], record["total"]


async def store_goal_tally(driver: AsyncDriver, goal_uid: str, done: int, total: int) -> None:
    """Store a goal's tally as a recompute would have left it — no door, no announcement.

    A test that holds a write to the tally seeds its "before" this way (with the edges
    from :func:`write_edge`), so the write under test is the one thing that can move the
    goal. A goal stored at 100% is stored achieved.
    """
    progress = done / total * 100 if total else 0.0
    async with driver.session() as session:
        await session.run(
            """
            MATCH (g:Goal {uid: $uid})
            SET g.current_value = $done, g.target_value = $total,
                g.progress_percentage = $progress
            FOREACH (_ IN CASE WHEN $achieved THEN [1] ELSE [] END |
                SET g.status = 'completed', g.achieved_date = date())
            """,
            uid=goal_uid,
            done=float(done),
            total=float(total),
            progress=progress,
            achieved=progress >= 100,
        )
    assert await goal_tally(driver, goal_uid) == (done, total)


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
    touch_forward(path)
    return path


def write_edge_file(vault: Path, name: str, *, source: str, edge_type: str, target: str) -> Path:
    """One Edge YAML file: ``(source)-[:edge_type]->(target)``."""
    path = vault / f"{name}.yaml"
    path.write_text(f"type: Edge\nfrom: {source}\nto: {target}\nrelationship: {edge_type}\n")
    touch_forward(path)
    return path


def touch_forward(path: Path) -> None:
    """Move the file's mtime past any earlier write, so a smart sync re-reads it.

    A rewrite inside one test can land within the filesystem's mtime granularity;
    the explicit bump keeps a changed file from being skipped as unchanged.
    """
    future = max(path.stat().st_mtime, _last_touch[0]) + 10
    _last_touch[0] = future
    os.utime(path, (future, future))


# The last mtime ``touch_forward`` set, so every later write lands after it.
_last_touch = [0.0]


@contextmanager
def published(bus: EventBusOperations, *event_types: type) -> Iterator[list[Any]]:
    """Collect every event of ``event_types`` the bus publishes inside the block."""
    seen: list[Any] = []  # boundary: domain event instances of several classes

    async def collect(event: Any) -> None:  # boundary: any of event_types
        seen.append(event)

    for event_type in event_types:
        bus.subscribe(event_type, collect)
    try:
        yield seen
    finally:
        for event_type in event_types:
            bus.unsubscribe(event_type, collect)


async def sync_vault(
    driver: AsyncDriver,
    vault: Path,
    *,
    force: bool = False,
    event_bus: EventBusOperations | None = None,
) -> IncrementalStats:
    """One smart directory sync of ``vault`` into the graph, with the tracker wired.

    ``force`` re-processes files the tracker holds as unchanged. ``event_bus`` is the
    bus the door publishes on — the composed app's, so its subscribers (goal progress
    among them) hear the sync; with none the door publishes nothing.
    """
    service = make_unified_ingestion_service(
        driver=driver,
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(driver)),
        event_bus=event_bus,
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
