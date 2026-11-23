"""The graph census's control of a module's marker: one test in the module earns it.

A marker on a module (``pytestmark``) covers every test in it and is judged at its last
test, when every test in it ran (``_graph_census.py``). Here the first test stores a key
no read reads and the last stores none: the marker is earned, and every test passes. The
census fails the module's last test the day it stops carrying what an earlier test wrote
to the module's verdict. Its twin, ``test_graph_census_module_marker_stale_control.py``,
holds the stale verdict.
"""

import pytest
from neo4j import AsyncDriver

from tests.integration._graph_census_controls import (
    write_a_clean_task,
    write_an_undeclared_key,
)

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.stores_undeclared_key("the census's control: a module marker one test earns"),
]


async def test_the_first_stores_an_undeclared_key(control_graph: AsyncDriver) -> None:
    await write_an_undeclared_key(control_graph)


async def test_the_last_stores_none(control_graph: AsyncDriver) -> None:
    await write_a_clean_task(control_graph)
