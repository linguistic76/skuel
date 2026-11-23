"""The graph census's control of a module's marker that no test in the module earns.

A marker on a module (``pytestmark``) is stale when none of its tests wrote its finding,
judged at the module's last test on a run of the whole module (``_graph_census.py``). Here
no test stores a key no read reads, so the last one fails — held strict. A run of the last
test alone does not hold the whole module and judges nothing, so it reads as an unexpected
pass. Its twin, ``test_graph_census_module_marker_control.py``, holds the earned verdict.
"""

import pytest
from neo4j import AsyncDriver

from tests.integration._graph_census_controls import (
    write_a_clean_task,
)

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.stores_undeclared_key("the census's control: a module marker no test earns"),
]


async def test_the_first_stores_none(control_graph: AsyncDriver) -> None:
    await write_a_clean_task(control_graph)


@pytest.mark.xfail(strict=True, reason="the module's last test: none in it stored a key")
async def test_the_last_stores_none_either(control_graph: AsyncDriver) -> None:
    await write_a_clean_task(control_graph)
