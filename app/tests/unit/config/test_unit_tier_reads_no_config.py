"""The unit tier reads no configuration (``tests/unit/conftest.py``).

A test that reads the real config through ``get_settings()`` fails — on a laptop
whose environment holds a complete config as surely as in CI, which holds none.
Each refused read runs as a test of its own (``pytester``), and its report is
read, so no test here catches the refusal itself.
"""

import textwrap
from unittest.mock import MagicMock, patch

import pytest

import core.config.settings as settings_module
from core.config.settings import get_settings
from core.config.unified_config import create_config

pytest_plugins = ["pytester"]

UNIT_CONFTEST = """
from tests.unit.conftest import (
    no_real_settings,
    pytest_runtest_makereport,
    refuse_real_settings,
)
"""

INNER_INI = "[pytest]\nasyncio_default_fixture_loop_scope = function\n"

READERS = """
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.boundary import ui_boundary_handler
from core.config.settings import get_settings


@pytest.fixture(scope="module")
def module_settings():
    return get_settings()


def test_reads_the_config():
    get_settings()


def test_a_module_fixture_reads_the_config(module_settings):
    pass


def test_a_sync_page_crashes():
    app, rt = fast_app(pico=False, default_hdrs=False)

    @rt("/crash")
    @ui_boundary_handler("Could not load the page")
    def crash() -> str:
        raise ValueError("the page failed")

    TestClient(app).get("/crash")


def test_an_async_page_crashes():
    app, rt = fast_app(pico=False, default_hdrs=False)

    @rt("/crash")
    @ui_boundary_handler("Could not load the page")
    async def crash() -> str:
        raise ValueError("the page failed")

    TestClient(app).get("/crash")


def test_swallows_the_refusal():
    try:
        get_settings()
    except Exception:  # intentional-broad: stands in for code that swallows the refusal
        pass
"""


@pytest.fixture
def complete_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything ``get_settings()`` needs to build and validate a config."""
    monkeypatch.setenv("SKUEL_ENVIRONMENT", "local")
    monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "env")
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "unit-tier-control")
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)


@pytest.fixture
def run_reader(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """Run one of ``READERS`` under the unit tier's fixtures; return its reports.

    The inner session starts as a real one does, with the real ``create_config``:
    nothing is refused there but what its own fixtures refuse.
    """
    monkeypatch.setattr(settings_module, "create_config", create_config)
    pytester.makeconftest(UNIT_CONFTEST)
    pytester.makeini(INNER_INI)
    pytester.makepyfile(test_readers=READERS)

    def run(name: str) -> dict[str, pytest.TestReport]:
        recorder = pytester.inline_run("-p", "no:cacheprovider", "-k", name)
        return {r.when: r for r in recorder.getreports("pytest_runtest_logreport")}

    return run


@pytest.mark.usefixtures("complete_environment")
def test_a_read_fails_although_the_environment_holds_a_config(run_reader) -> None:
    call = run_reader("test_reads_the_config")["call"]
    assert call.failed
    assert "RealConfigReadError: a unit test read the real config" in str(call.longrepr)


@pytest.mark.usefixtures("complete_environment")
def test_a_module_fixture_that_reads_the_config_fails_its_test(run_reader) -> None:
    setup = run_reader("test_a_module_fixture_reads_the_config")["setup"]
    assert setup.failed
    assert "RealConfigReadError: a unit test read the real config" in str(setup.longrepr)


@pytest.mark.reads_real_settings
@pytest.mark.usefixtures("complete_environment")
def test_the_same_environment_builds_a_config_for_a_marked_test() -> None:
    assert get_settings().database.neo4j_password == "unit-tier-control"


@pytest.mark.usefixtures("complete_environment")
def test_the_refusal_ends_with_the_unit_package(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``./dev test`` runs both tiers in one session: an integration test after a
    unit test reads its real config."""
    monkeypatch.setattr(settings_module, "create_config", create_config)
    reads = "from core.config.settings import get_settings\n\n\ndef test_{}_reads():\n    get_settings()\n"
    unit = pytester.mkpydir("unit")
    (unit / "conftest.py").write_text(UNIT_CONFTEST)
    (unit / "test_unit.py").write_text(reads.format("unit"))
    (pytester.mkdir("integration") / "test_integration.py").write_text(reads.format("integration"))
    pytester.makeini(INNER_INI)

    recorder = pytester.inline_run("-p", "no:cacheprovider", "unit", "integration")
    calls = {
        report.nodeid.rsplit("::", 1)[-1]: report
        for report in recorder.getreports("pytest_runtest_logreport")
        if report.when == "call"
    }
    assert calls["test_unit_reads"].failed
    assert calls["test_integration_reads"].passed


@pytest.mark.parametrize("name", ["test_a_sync_page_crashes", "test_an_async_page_crashes"])
def test_a_crashed_page_that_reads_the_config_fails_with_the_refusal(run_reader, name) -> None:
    """A crashed route's banner reads ``application.debug``; the read fails the test."""
    call = run_reader(name)["call"]
    assert call.failed
    assert "RealConfigReadError: a unit test read the real config" in str(call.longrepr)


def test_a_refusal_the_code_under_test_catches_fails_its_test(run_reader) -> None:
    call = run_reader("test_swallows_the_refusal")["call"]
    assert call.failed
    lines = textwrap.dedent(READERS).strip().splitlines()
    read = lines.index("        get_settings()", lines.index("def test_swallows_the_refusal():"))
    assert "The code under test caught the refusal; read at " in str(call.longrepr)
    assert f"/test_readers.py:{read + 1}." in str(call.longrepr)


def test_a_test_that_fills_the_cache_leaves_it_filled() -> None:
    """The first of a pair: the next test must not find this settings object."""
    with (
        patch.object(settings_module, "create_config", return_value=MagicMock()),
        patch.object(settings_module, "validate_config", return_value=[]),
    ):
        get_settings()
    assert get_settings.cache_info().currsize == 1


def test_the_next_test_finds_the_cache_empty() -> None:
    """Runs after its pair above, in file order (a plain run and ``--dist loadfile`` keep it)."""
    assert get_settings.cache_info().currsize == 0
