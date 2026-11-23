"""What the graph census's controls write, and the graphs they write it to.

Every node a control writes holds ``MARK`` in its uid and is wiped once the census has read
it (``tests/integration/_graph_census.py``). The controls are ``test_graph_census_control.py``
and the two ``test_graph_census_module_*`` files; ``tests/integration/conftest.py`` registers
the two fixtures, ``control_graph`` (the shared container's) and ``control_app_graph``
(the app's).
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid

MARK = "zzzgraphcensuscontrol"
OUTSIDE = f"task_{MARK}"  # an underscore: neither shape of the grammar
SHARED = f"task.{MARK}"  # fits — but two nodes hold it
STRAY = f"task.{MARK}-stray"  # fits, and holds a status no EntityStatus names
UNTITLED = f"task.{MARK}-untitled"  # fits, and holds no title, which a Task requires
KEYED = f"task.{MARK}-keyed"  # fits, reads, and holds a key no Task field names
OWNER = seed_user_uid("graph_census_control")  # owns every control task

NEEDS_THE_APP = pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)


async def write(driver: AsyncDriver, query: str) -> None:
    async with driver.session() as session:
        await session.run(
            query,
            outside=OUTSIDE,
            shared=SHARED,
            stray=STRAY,
            untitled=UNTITLED,
            keyed=KEYED,
            owner=OWNER,
        )


async def write_a_stray(driver: AsyncDriver) -> None:
    await write(
        driver,
        "CREATE (:Entity:Task {uid: $stray, title: 'Stray', entity_type: 'task', "
        "user_uid: $owner, status: 'no-such-status'})",
    )


async def write_an_untitled_task(driver: AsyncDriver) -> None:
    await write(
        driver,
        "CREATE (:Entity:Task {uid: $untitled, entity_type: 'task', user_uid: $owner})",
    )


async def write_an_undeclared_key(driver: AsyncDriver) -> None:
    """A task every read reads, holding one key besides: ``titel``, named by no field."""
    await write(
        driver,
        "CREATE (:Entity:Task {uid: $keyed, title: 'Keyed', entity_type: 'task', "
        "user_uid: $owner, status: 'active', titel: 'typo'})",
    )


async def write_fields_and_node_state(driver: AsyncDriver) -> None:
    """A task holding fields and registered node state, and nothing else
    (``core/models/node_state.py``): no finding of any kind."""
    await write(
        driver,
        "CREATE (:Entity:Task {uid: $keyed, title: 'Keyed', entity_type: 'task', "
        "user_uid: $owner, status: 'active', grounded_at: datetime(), "
        "embedding_text_hash: 'h', predicted_duration_minutes: 30})",
    )


async def write_a_clean_task(driver: AsyncDriver) -> None:
    await write(
        driver,
        "CREATE (:Entity:Task {uid: $shared, status: 'active', title: $shared, user_uid: $owner})",
    )


async def wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid CONTAINS $mark DETACH DELETE n", mark=MARK)


@pytest_asyncio.fixture(loop_scope="session")
async def control_graph(neo4j_driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    yield neo4j_driver
    await wipe(neo4j_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def control_app_graph(skuel_app: FastHTMLApp) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    yield driver
    await wipe(driver)
