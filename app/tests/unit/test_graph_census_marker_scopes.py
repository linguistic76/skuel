"""The rules the integration graph census applies to a marker on a module.

A module's marker covers every test in it and is stale when none of them wrote its finding,
judged at the module's last test and only when every test in the module ran its body to the
end (``tests/integration/_graph_census.py``): a run of part of it, or one in which a test
skipped or failed, judges no marker. Each case runs an inner session (``pytester``)
under the census's own hooks over a fake graph: a test writes a finding by adding it to
``graph``, and the fake's teardown empties it, as a fixture's wipe empties a real one.
What the census reads of a real graph is held by its integration controls
(``tests/integration/test_graph_census_control.py``).
"""

import pytest

pytest_plugins = ["pytester"]

CONFTEST = """
import importlib

import pytest

from tests.integration._graph_census import (
    pytest_make_collect_report,
    pytest_runtest_call,
    pytest_runtest_setup,
)

# The module the hooks were imported from: an earlier inner session's copy can linger on
# the package as an attribute after the session's imports are undone.
_graph_census = importlib.import_module("tests.integration._graph_census")

GRAPH = {kind.marker: set() for kind in _graph_census._KINDS}


def _graph_for(driver):
    async def read():
        return {marker: frozenset(found) for marker, found in GRAPH.items()}

    return _graph_census._Graph(read)


@pytest.fixture(scope="session", autouse=True)
def _fake_graphs():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_graph_census, "_graph_for", _graph_for)
        yield


@pytest.fixture
def neo4j_driver():
    return object()


@pytest.fixture
def graph(neo4j_driver):
    yield GRAPH
    for found in GRAPH.values():
        found.clear()
"""

INI = """[pytest]
asyncio_default_fixture_loop_scope = function
filterwarnings =
    ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning:neo4j
markers =
    outside_uid_grammar(reason, static_only=False): census marker
    stores_unreadable_value(reason): census marker
    stores_undeclared_key(reason): census marker
"""

MARKED = """
import pytest

pytestmark = pytest.mark.stores_undeclared_key("the module's seed")


{first_decorator}
def test_first(graph):
    {first}


{last_decorator}
def test_last(graph):
    {last}
"""

WRITES = 'graph["stores_undeclared_key"].add("Task task.x.titel")'
NONE = "pass"
STALE = "no test in it wrote an undeclared key — delete the marker"


@pytest.fixture
def run(pytester: pytest.Pytester):
    """Run a module-marked file; return each test's reports by phase."""
    pytester.makeconftest(CONFTEST)
    pytester.makeini(INI)

    def run_module(
        *args: str,
        first: str = NONE,
        last: str = NONE,
        first_decorator: str = "",
        last_decorator: str = "",
    ) -> dict[str, dict[str, pytest.TestReport]]:
        pytester.makepyfile(
            test_marked=MARKED.format(
                first=first,
                last=last,
                first_decorator=first_decorator,
                last_decorator=last_decorator,
            )
        )
        recorder = pytester.inline_run("-p", "no:cacheprovider", *args)
        reports: dict[str, dict[str, pytest.TestReport]] = {}
        for report in recorder.getreports("pytest_runtest_logreport"):
            reports.setdefault(report.nodeid.rsplit("::", 1)[-1], {})[report.when] = report
        return reports

    return run_module


def _stale(report: pytest.TestReport) -> bool:
    return report.failed and STALE in str(report.longrepr)


def test_a_marker_no_test_earns_fails_the_modules_last_test(run) -> None:
    reports = run()
    assert reports["test_first"]["call"].passed
    assert _stale(reports["test_last"]["call"])


def test_a_marker_one_test_earns_fails_none(run) -> None:
    reports = run(first=WRITES)
    assert all(report.passed for phases in reports.values() for report in phases.values())


def test_a_run_of_one_test_by_node_id_judges_no_marker(run) -> None:
    reports = run("test_marked.py::test_last")
    assert reports["test_last"]["call"].passed


def test_a_run_that_deselects_a_test_judges_no_marker(run) -> None:
    by_keyword = run("-k", "test_last")
    assert by_keyword["test_last"]["call"].passed
    by_deselect = run("--deselect", "test_marked.py::test_first")
    assert by_deselect["test_last"]["call"].passed


def _no_failure(reports: dict[str, dict[str, pytest.TestReport]]) -> bool:
    return not any(report.failed for phases in reports.values() for report in phases.values())


SKIP = '@pytest.mark.skip(reason="skipped")'


def test_a_module_whose_every_test_is_skipped_judges_no_marker(run) -> None:
    reports = run(first_decorator=SKIP, last_decorator=SKIP)
    assert reports["test_first"]["setup"].skipped
    assert reports["test_last"]["setup"].skipped
    assert _no_failure(reports)


def test_a_skipped_test_that_may_earn_the_marker_judges_none(run) -> None:
    reports = run(first_decorator=SKIP)
    assert reports["test_first"]["setup"].skipped
    assert reports["test_last"]["call"].passed
    assert _no_failure(reports)


def test_a_skipped_last_test_judges_no_marker(run) -> None:
    reports = run(last_decorator=SKIP)
    assert reports["test_last"]["setup"].skipped
    assert _no_failure(reports)


def test_a_test_that_skips_in_its_body_judges_no_marker(run) -> None:
    reports = run(last='pytest.skip("skipped")')
    assert reports["test_last"]["call"].skipped
    assert _no_failure(reports)


def test_a_failing_test_judges_no_marker_beside_its_own_failure(run) -> None:
    reports = run(first="assert False")
    assert reports["test_first"]["call"].failed
    assert reports["test_last"]["call"].passed
