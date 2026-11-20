"""
The graph census's own controls: each of its findings, on each graph it reads, under
each scope a marker can take.

Every marked test here writes what the census refuses — a uid outside the grammar, one
uid two nodes hold, a stored value no read of its node can read, or a node without a
property its class requires — and carries that finding's marker. A marked test that wrote no such finding fails as a stale marker
(``_graph_census.py``), so each of these fails the day the census stops reading its graph
or stops recognising the finding. A class marker covers every test in it and is stale only
when none of them wrote one. The nodes are deleted after the census has read them. The
expected failures — a ``static_only`` marker on a breach the census sees, an unmarked
stray, a stale marker on a test and on a class — are held strict.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MARK = "zzzgraphcensuscontrol"
_OUTSIDE = f"task_{_MARK}"  # an underscore: neither shape of the grammar
_SHARED = f"task.{_MARK}"  # fits — but two nodes hold it
_STRAY = f"task.{_MARK}-stray"  # fits, and holds a status no EntityStatus names
_UNTITLED = f"task.{_MARK}-untitled"  # fits, and holds no title, which a Task requires
_OWNER = seed_user_uid("graph_census_control")  # owns every control task

_NEEDS_THE_APP = pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)


async def _write(driver: AsyncDriver, query: str) -> None:
    async with driver.session() as session:
        await session.run(
            query,
            outside=_OUTSIDE,
            shared=_SHARED,
            stray=_STRAY,
            untitled=_UNTITLED,
            owner=_OWNER,
        )


async def _write_a_stray(driver: AsyncDriver) -> None:
    await _write(
        driver,
        "CREATE (:Entity:Task {uid: $stray, title: 'Stray', entity_type: 'task', "
        "user_uid: $owner, status: 'no-such-status'})",
    )


async def _write_an_untitled_task(driver: AsyncDriver) -> None:
    await _write(
        driver,
        "CREATE (:Entity:Task {uid: $untitled, entity_type: 'task', user_uid: $owner})",
    )


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid CONTAINS $mark DETACH DELETE n", mark=_MARK)


@pytest_asyncio.fixture(loop_scope="session")
async def shared_graph(neo4j_driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    yield neo4j_driver
    await _wipe(neo4j_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def app_graph(skuel_app: FastHTMLApp) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    yield driver
    await _wipe(driver)


@pytest.mark.outside_uid_grammar("the census's control: a uid outside the grammar")
async def test_the_census_reads_a_uid_outside_the_grammar(shared_graph: AsyncDriver) -> None:
    await _write(
        shared_graph, "CREATE (:Entity:Task {uid: $outside, title: $outside, user_uid: $owner})"
    )


@pytest.mark.outside_uid_grammar("the census's control: one uid two nodes hold")
async def test_the_census_reads_a_uid_two_nodes_hold(shared_graph: AsyncDriver) -> None:
    await _write(
        shared_graph,
        "CREATE (:Entity:Task {uid: $shared, title: $shared, user_uid: $owner}), (:Entity:Task {uid: $shared, title: $shared, user_uid: $owner})",
    )


@_NEEDS_THE_APP
@pytest.mark.outside_uid_grammar(
    "the census's control: a uid outside the grammar, in the app's graph"
)
async def test_the_census_reads_the_apps_graph(app_graph: AsyncDriver) -> None:
    await _write(
        app_graph, "CREATE (:Entity:Task {uid: $outside, title: $outside, user_uid: $owner})"
    )


@pytest.mark.xfail(
    strict=True, reason="a static_only marker is held as no marker: a breach it sees fails"
)
@pytest.mark.outside_uid_grammar(
    "the census's control: static_only, on a uid the census does see", static_only=True
)
async def test_a_static_only_marker_does_not_excuse_a_breach_the_census_sees(
    shared_graph: AsyncDriver,
) -> None:
    await _write(
        shared_graph,
        "CREATE (:Entity:Task {uid: 'task_zzzgraphcensuscontrol', title: 'Control', user_uid: $owner})",
    )


@pytest.mark.stores_unreadable_value("the census's control: a value no read can read")
async def test_the_census_reads_an_unreadable_stored_value(shared_graph: AsyncDriver) -> None:
    await _write_a_stray(shared_graph)


@_NEEDS_THE_APP
@pytest.mark.stores_unreadable_value(
    "the census's control: a value no read can read, in the app's graph"
)
async def test_the_census_reads_an_unreadable_value_in_the_apps_graph(
    app_graph: AsyncDriver,
) -> None:
    await _write_a_stray(app_graph)


@pytest.mark.xfail(strict=True, reason="an unmarked test that stores a stray fails")
async def test_an_unmarked_stray_fails_its_test(shared_graph: AsyncDriver) -> None:
    await _write_a_stray(shared_graph)


@pytest.mark.stores_unreadable_value("the census's control: a node without a required property")
async def test_the_census_reads_a_required_property_the_node_lacks(
    shared_graph: AsyncDriver,
) -> None:
    await _write_an_untitled_task(shared_graph)


@_NEEDS_THE_APP
@pytest.mark.stores_unreadable_value(
    "the census's control: a node without a required property, in the app's graph"
)
async def test_the_census_reads_a_required_property_a_node_lacks_in_the_apps_graph(
    app_graph: AsyncDriver,
) -> None:
    await _write_an_untitled_task(app_graph)


@pytest.mark.xfail(strict=True, reason="an unmarked test that leaves a required property out fails")
async def test_an_unmarked_node_without_a_required_property_fails_its_test(
    shared_graph: AsyncDriver,
) -> None:
    await _write_an_untitled_task(shared_graph)


@pytest.mark.xfail(strict=True, reason="a marked test that stores no stray fails as stale")
@pytest.mark.stores_unreadable_value("the census's control: a marker with nothing to excuse")
async def test_a_marker_on_a_test_that_stores_none_is_stale(shared_graph: AsyncDriver) -> None:
    await _write(
        shared_graph,
        "CREATE (:Entity:Task {uid: $shared, status: 'active', title: $shared, user_uid: $owner})",
    )


@pytest.mark.stores_unreadable_value("the census's control: a class marker covers its tests")
class TestAClassMarkerCoversEveryTestInIt:
    async def test_one_test_stores_the_stray(self, shared_graph: AsyncDriver) -> None:
        await _write_a_stray(shared_graph)

    async def test_another_stores_none(self, shared_graph: AsyncDriver) -> None:
        await _write(
            shared_graph,
            "CREATE (:Entity:Task {uid: $shared, status: 'active', title: $shared, user_uid: $owner})",
        )


@pytest.mark.stores_unreadable_value("the census's control: a class marker none of its tests earns")
class TestAClassMarkerNoTestEarnsIsStaleAtItsLastTest:
    async def test_the_first_stores_none(self, shared_graph: AsyncDriver) -> None:
        await _write(
            shared_graph,
            "CREATE (:Entity:Task {uid: $shared, status: 'active', title: $shared, user_uid: $owner})",
        )

    @pytest.mark.xfail(strict=True, reason="the class's last test: none in it stored a stray")
    async def test_the_last_stores_none_either(self, shared_graph: AsyncDriver) -> None:
        await _write(
            shared_graph,
            "CREATE (:Entity:Task {uid: $shared, status: 'active', title: $shared, user_uid: $owner})",
        )
