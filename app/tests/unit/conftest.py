"""
Unit-tier fixtures
==================

The unit tier reads no configuration. ``get_settings()`` builds the real config
from the environment and the credential store: on a laptop that is ``.env``
(loaded by the root conftest) and the keychain; in CI it is nothing — no Neo4j
password, no keychain backend — so a test that reads it passes on the laptop and
fails only in CI. Here every such read fails the test, on both.

A module that reads ``get_settings()`` is stubbed where it looks the name up
(``tests/helpers/settings_stub.py``). A test of ``get_settings()`` itself, which
sets the environment it reads, is marked ``reads_real_settings``.

The integration tier keeps its real config (``tests/integration/conftest.py``).
"""

import traceback
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import NoReturn

import pytest

import core.config.settings as settings_module
from core.config.unified_config import Environment, create_config

REFUSAL = (
    "a unit test read the real config through get_settings(). The unit tier has "
    "none (CI has no Neo4j password and no keychain). Stub get_settings in the "
    "module that reads it (tests/helpers/settings_stub.py), or mark a test of "
    "get_settings() itself @pytest.mark.reads_real_settings."
)

_APP_ROOT = Path(__file__).resolve().parents[2]

# The reads refused in the test phase now running — setup, call or teardown.
_refused_reads: list[str] = []


class RealConfigReadError(RuntimeError):
    """A unit test reached the real ``get_settings()``."""


def _reader() -> str:
    """Where ``get_settings()`` was called from: the frame below it."""
    frame = traceback.extract_stack()[-4]
    path = Path(frame.filename)
    shown = path.relative_to(_APP_ROOT) if path.is_relative_to(_APP_ROOT) else path
    return f"{shown}:{frame.lineno}"


def _refuse(environment: Environment | None = None) -> NoReturn:
    _refused_reads.append(_reader())
    raise RealConfigReadError(REFUSAL)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """A test phase that passed although a read was refused in it fails.

    The refusal raises, so a read fails its phase unless the code under test
    catches ``RealConfigReadError`` — then the phase's report fails instead,
    naming the line that read.
    """
    report = yield
    readers = list(_refused_reads)
    _refused_reads.clear()
    if readers and report.passed:
        report.outcome = "failed"
        report.longrepr = f"{REFUSAL} The code under test caught the refusal; read at {readers[0]}."
    return report


@pytest.fixture(scope="package", autouse=True)
def refuse_real_settings() -> Iterator[None]:
    """Refuse the real ``get_settings()`` while the unit tier runs.

    Package scope, so the refusal is in place before any module- or class-scoped
    fixture reads, and lifted before an integration test in the same session.
    Whatever import cached is dropped on the way in.
    """
    settings_module.get_settings.cache_clear()
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(settings_module, "create_config", _refuse)
        yield
    settings_module.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_real_settings(
    refuse_real_settings: None, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Lift the refusal for a test marked ``reads_real_settings``; empty the cache after each test.

    Emptied after, so no settings object a test built — by patching
    ``create_config`` — answers the next test's read, or its fixtures'.
    """
    if request.node.get_closest_marker("reads_real_settings") is not None:
        monkeypatch.setattr(settings_module, "create_config", create_config)
    yield
    settings_module.get_settings.cache_clear()
