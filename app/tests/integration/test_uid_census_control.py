"""
The uid census's own controls: each of its breaches, on each graph it reads.

Every test here writes what the census refuses — a uid outside the grammar, or
one uid two nodes hold — and carries ``outside_uid_grammar``. A marked test that
wrote no breach the census saw fails as a stale marker (``_uid_census.py``), so
each of these fails the day the census stops reading its graph or stops
recognising the breach. The nodes are deleted after the census has read them.
The last control's ``static_only`` marker excuses nothing the census sees, so it
fails — an expected failure, held strict.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MARK = "zzzuidcensuscontrol"
_OUTSIDE = f"task_{_MARK}"  # an underscore: neither shape of the grammar
_SHARED = f"task.{_MARK}"  # fits — but two nodes hold it


async def _write(driver: AsyncDriver, query: str) -> None:
    async with driver.session() as session:
        await session.run(query, outside=_OUTSIDE, shared=_SHARED)


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid CONTAINS $mark DETACH DELETE n", mark=_MARK)


@pytest_asyncio.fixture(loop_scope="session")
async def shared_graph(neo4j_driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    yield neo4j_driver
    await _wipe(neo4j_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def app_graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    yield driver
    await _wipe(driver)


@pytest.mark.outside_uid_grammar("the census's control: a uid outside the grammar")
async def test_the_census_reads_a_uid_outside_the_grammar(shared_graph: AsyncDriver) -> None:
    await _write(shared_graph, "CREATE (:Entity:Task {uid: $outside})")


@pytest.mark.outside_uid_grammar("the census's control: one uid two nodes hold")
async def test_the_census_reads_a_uid_two_nodes_hold(shared_graph: AsyncDriver) -> None:
    await _write(
        shared_graph, "CREATE (:Entity:Task {uid: $shared}), (:Entity:Task {uid: $shared})"
    )


@pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)
@pytest.mark.outside_uid_grammar(
    "the census's control: a uid outside the grammar, in the app's graph"
)
async def test_the_census_reads_the_apps_graph(app_graph: AsyncDriver) -> None:
    await _write(app_graph, "CREATE (:Entity:Task {uid: $outside})")


@pytest.mark.xfail(
    strict=True, reason="a static_only marker is held as no marker: a breach it sees fails"
)
@pytest.mark.outside_uid_grammar(
    "the census's control: static_only, on a uid the census does see", static_only=True
)
async def test_a_static_only_marker_does_not_excuse_a_breach_the_census_sees(
    shared_graph: AsyncDriver,
) -> None:
    await _write(shared_graph, "CREATE (:Entity:Task {uid: 'task_zzzuidcensuscontrol'})")
