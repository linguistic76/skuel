"""The rules the integration graph census applies to a marker on a module.

A module's marker covers every test in it and is stale when none of them wrote its finding,
judged when the module's last test finishes — in its body when it runs, at its teardown
when it is skipped — and only on a run that holds the whole module
(``tests/integration/_graph_census.py``). Each case runs an inner session (``pytester``)
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
    pytest_runtest_makereport,
    pytest_runtest_setup,
    pytest_runtest_teardown,
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


def test_first(graph):
    {first}


{decorator}
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
        *args: str, first: str = NONE, last: str = NONE, decorator: str = ""
    ) -> dict[str, dict[str, pytest.TestReport]]:
        pytester.makepyfile(test_marked=MARKED.format(first=first, last=last, decorator=decorator))
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


def test_a_skipped_last_test_judges_the_marker_at_its_teardown(run) -> None:
    reports = run(decorator='@pytest.mark.skip(reason="skipped")')
    assert reports["test_last"]["setup"].skipped
    assert _stale(reports["test_last"]["teardown"])


def test_a_skipped_last_test_fails_no_marker_an_earlier_test_earned(run) -> None:
    reports = run(first=WRITES, decorator='@pytest.mark.skip(reason="skipped")')
    assert reports["test_last"]["setup"].skipped
    assert reports["test_last"]["teardown"].passed


def test_a_last_test_that_skips_in_its_body_after_writing_earns_the_marker(run) -> None:
    reports = run(last=f'{WRITES}; pytest.skip("skipped")')
    assert reports["test_last"]["call"].skipped
    assert reports["test_last"]["teardown"].passed


def test_a_last_test_that_skips_in_its_body_judges_the_marker_at_its_teardown(run) -> None:
    reports = run(last='pytest.skip("skipped")')
    assert reports["test_last"]["call"].skipped
    assert _stale(reports["test_last"]["teardown"])
