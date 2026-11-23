"""
The graph census's own controls: each of its findings, on each graph it reads, under a
test's and a class's marker. The module's own marker is controlled by the two
``test_graph_census_module_*`` files.

Every marked test here writes what the census refuses — a uid outside the grammar, one
uid two nodes hold, a stored value no read of its node can read, a node without a property
its class requires, a stored key no read reads — and carries that finding's marker. A
marked test that wrote no such finding fails as a stale marker (``_graph_census.py``), so
each of these fails the day the census stops reading its graph or stops recognising the
finding. A class marker covers every test in it and is stale only when none of them wrote
one, judged at its last test when every test in the class ran. Fields and registered node state
are no finding. The nodes are deleted after the census has read them
(``_graph_census_controls.py``). The expected failures — a ``static_only`` marker on a
breach the census sees, a ``static_only`` marker on a kind no static census reads, an
unmarked stray, an unmarked undeclared key, a stale marker on a test and on a class — are
held strict.
"""

import pytest
from neo4j import AsyncDriver

from tests.integration._graph_census_controls import (
    NEEDS_THE_APP,
    write,
    write_a_clean_task,
    write_a_stray,
    write_an_undeclared_key,
    write_an_untitled_task,
    write_fields_and_node_state,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.outside_uid_grammar("the census's control: a uid outside the grammar")
async def test_the_census_reads_a_uid_outside_the_grammar(control_graph: AsyncDriver) -> None:
    await write(
        control_graph, "CREATE (:Entity:Task {uid: $outside, title: $outside, user_uid: $owner})"
    )


@pytest.mark.outside_uid_grammar("the census's control: one uid two nodes hold")
async def test_the_census_reads_a_uid_two_nodes_hold(control_graph: AsyncDriver) -> None:
    await write(
        control_graph,
        "CREATE (:Entity:Task {uid: $shared, title: $shared, user_uid: $owner}), (:Entity:Task {uid: $shared, title: $shared, user_uid: $owner})",
    )


@NEEDS_THE_APP
@pytest.mark.outside_uid_grammar(
    "the census's control: a uid outside the grammar, in the app's graph"
)
async def test_the_census_reads_the_apps_graph(control_app_graph: AsyncDriver) -> None:
    await write(
        control_app_graph,
        "CREATE (:Entity:Task {uid: $outside, title: $outside, user_uid: $owner})",
    )


@pytest.mark.xfail(
    strict=True, reason="a static_only marker is held as no marker: a breach it sees fails"
)
@pytest.mark.outside_uid_grammar(
    "the census's control: static_only, on a uid the census does see", static_only=True
)
async def test_a_static_only_marker_does_not_excuse_a_breach_the_census_sees(
    control_graph: AsyncDriver,
) -> None:
    await write(
        control_graph,
        "CREATE (:Entity:Task {uid: 'task_zzzgraphcensuscontrol', title: 'Control', user_uid: $owner})",
    )


@pytest.mark.stores_unreadable_value("the census's control: a value no read can read")
async def test_the_census_reads_an_unreadable_stored_value(control_graph: AsyncDriver) -> None:
    await write_a_stray(control_graph)


@NEEDS_THE_APP
@pytest.mark.stores_unreadable_value(
    "the census's control: a value no read can read, in the app's graph"
)
async def test_the_census_reads_an_unreadable_value_in_the_apps_graph(
    control_app_graph: AsyncDriver,
) -> None:
    await write_a_stray(control_app_graph)


@pytest.mark.xfail(strict=True, reason="an unmarked test that stores a stray fails")
async def test_an_unmarked_stray_fails_its_test(control_graph: AsyncDriver) -> None:
    await write_a_stray(control_graph)


@pytest.mark.stores_unreadable_value("the census's control: a node without a required property")
async def test_the_census_reads_a_required_property_the_node_lacks(
    control_graph: AsyncDriver,
) -> None:
    await write_an_untitled_task(control_graph)


@NEEDS_THE_APP
@pytest.mark.stores_unreadable_value(
    "the census's control: a node without a required property, in the app's graph"
)
async def test_the_census_reads_a_required_property_a_node_lacks_in_the_apps_graph(
    control_app_graph: AsyncDriver,
) -> None:
    await write_an_untitled_task(control_app_graph)


@pytest.mark.xfail(strict=True, reason="an unmarked test that leaves a required property out fails")
async def test_an_unmarked_node_without_a_required_property_fails_its_test(
    control_graph: AsyncDriver,
) -> None:
    await write_an_untitled_task(control_graph)


@pytest.mark.xfail(strict=True, reason="a marked test that stores no stray fails as stale")
@pytest.mark.stores_unreadable_value("the census's control: a marker with nothing to excuse")
async def test_a_marker_on_a_test_that_stores_none_is_stale(control_graph: AsyncDriver) -> None:
    await write_a_clean_task(control_graph)


@pytest.mark.stores_undeclared_key("the census's control: a key no read reads")
async def test_the_census_reads_an_undeclared_key(control_graph: AsyncDriver) -> None:
    await write_an_undeclared_key(control_graph)


@NEEDS_THE_APP
@pytest.mark.stores_undeclared_key("the census's control: a key no read reads, in the app's graph")
async def test_the_census_reads_an_undeclared_key_in_the_apps_graph(
    control_app_graph: AsyncDriver,
) -> None:
    await write_an_undeclared_key(control_app_graph)


@pytest.mark.xfail(strict=True, reason="an unmarked test that stores an undeclared key fails")
async def test_an_unmarked_undeclared_key_fails_its_test(control_graph: AsyncDriver) -> None:
    await write_an_undeclared_key(control_graph)


async def test_fields_and_registered_node_state_are_no_finding(control_graph: AsyncDriver) -> None:
    await write_fields_and_node_state(control_graph)


@pytest.mark.xfail(
    strict=True,
    reason="fields and registered node state are no undeclared key: the marker is stale",
)
@pytest.mark.stores_undeclared_key("the census's control: fields and node state excuse nothing")
async def test_a_key_marker_on_fields_and_node_state_is_stale(control_graph: AsyncDriver) -> None:
    await write_fields_and_node_state(control_graph)


@pytest.mark.xfail(strict=True, reason="a kind with no static census takes no static_only")
@pytest.mark.stores_undeclared_key(
    "the census's control: static_only on a kind no static census reads", static_only=True
)
async def test_static_only_on_a_kind_with_no_static_census_is_refused(
    control_graph: AsyncDriver,
) -> None:
    # It writes no finding: held as no marker, the test would pass — only the refusal fails it.
    await write_a_clean_task(control_graph)


@pytest.mark.stores_unreadable_value("the census's control: a class marker covers its tests")
class TestAClassMarkerCoversEveryTestInIt:
    async def test_one_test_stores_the_stray(self, control_graph: AsyncDriver) -> None:
        await write_a_stray(control_graph)

    async def test_another_stores_none(self, control_graph: AsyncDriver) -> None:
        await write_a_clean_task(control_graph)


@pytest.mark.stores_unreadable_value("the census's control: a class marker none of its tests earns")
class TestAClassMarkerNoTestEarnsIsStaleAtItsLastTest:
    async def test_the_first_stores_none(self, control_graph: AsyncDriver) -> None:
        await write_a_clean_task(control_graph)

    @pytest.mark.xfail(strict=True, reason="the class's last test: none in it stored a stray")
    async def test_the_last_stores_none_either(self, control_graph: AsyncDriver) -> None:
        await write_a_clean_task(control_graph)
