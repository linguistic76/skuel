"""
The uid grammar, held over what each integration test writes.

When a test's body ends — before any fixture teardown empties its graph — the
graph is read against the uid grammar (``core/utils/uid_grammar.py``) through
the read the graph-health poller makes (``UidCensusBackend.read_breaches``), and
the test fails on a uid it wrote that is outside the grammar, or that two nodes
hold. Two graphs are read, each when a test reaches it: the shared container's
(``neo4j_driver``) and the bootstrapped app's (``skuel_app``). A scratch
container is its test's own and is not read.

A breach is the test's when it was not in the graph before the test began.
``clean_neo4j`` keeps every ``:User`` and plenty of tests leave what they wrote,
so a test starts on whatever the last one left; and the last one's teardown may
delete a uid the next one's setup writes again. So each graph is read three
times: when the test's setup starts (what it starts on), when its body starts
(adding what its fixtures wrote) and when its body ends (what the body wrote).
A uid written and deleted inside one of those spans is not seen.

A test that writes a uid outside the grammar on purpose — an old-shape graph a
migration reads, a refusal path — carries
``@pytest.mark.outside_uid_grammar("why")``. Its graph is still read, so what it
leaves behind is never laid on the next test, and a marked test that wrote no
breach — or reached no graph the census reads — fails: the marker is stale.
``test_uid_census_control.py`` holds one such test per breach and graph.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend

if TYPE_CHECKING:
    from collections.abc import Generator

    from neo4j import AsyncDriver

MARKER = "outside_uid_grammar"

# The test graphs hold a few hundred nodes: every breach is read back.
_READ_EVERY = 100_000
# What a failure names of each kind.
_NAMED = 12
# pytest-asyncio's session runner — the loop the session drivers were opened on.
_SESSION_RUNNER = "_session_scoped_runner"


@dataclass
class _Graph:
    backend: UidCensusBackend
    breaches: frozenset[str] = frozenset()


_graphs: dict[str, _Graph] = {}
_runner: asyncio.Runner | None = None


async def _read(backend: UidCensusBackend) -> frozenset[str]:
    result = await backend.read_breaches(_READ_EVERY)
    if result.is_error:
        raise RuntimeError(f"uid census could not read the graph: {result.expect_error()}")
    breaches = result.value
    return frozenset(
        [f"outside the grammar: {entry}" for entry in breaches.outside_sample]
        + [f"held by two nodes: {uid}" for uid in breaches.shared_sample]
    )


def _drivers(item: pytest.Item) -> dict[str, AsyncDriver]:
    funcargs = getattr(item, "funcargs", {})
    drivers: dict[str, AsyncDriver] = {}
    if "neo4j_driver" in funcargs:
        drivers["shared container"] = funcargs["neo4j_driver"]
    if "skuel_app" in funcargs:
        drivers["app container"] = funcargs["skuel_app"].state.services.neo4j_driver
    return drivers


def read_before_setup() -> None:
    """Read every graph a test has reached so far: what the next test starts on."""
    if _runner is None:
        return
    for graph in _graphs.values():
        graph.breaches = _runner.run(_read(graph.backend))


def census_call(item: pytest.Item) -> Generator[None, object, object]:
    """Wrap a test's call: read its graphs before and after the body, fail on its breaches."""
    global _runner
    drivers = _drivers(item)
    if not drivers:
        outcome = yield
        if item.get_closest_marker(MARKER) is not None:
            pytest.fail(
                f"@pytest.mark.{MARKER} is on a test that reaches no graph the census reads — "
                "delete the marker",
                pytrace=False,
            )
        return outcome
    if _runner is None:
        _runner = item._request.getfixturevalue(_SESSION_RUNNER)  # type: ignore[attr-defined]
    runner = _runner
    for name, driver in drivers.items():
        if name not in _graphs:
            _graphs[name] = _Graph(UidCensusBackend(Neo4jQueryExecutor(driver)))

    written: dict[str, set[str]] = {}
    for name in drivers:
        graph = _graphs[name]
        now = runner.run(_read(graph.backend))
        written[name] = set(now - graph.breaches)
        graph.breaches = now

    def settle() -> None:
        for name in drivers:
            graph = _graphs[name]
            now = runner.run(_read(graph.backend))
            written[name] |= now - graph.breaches
            graph.breaches = now

    try:
        outcome = yield
    except BaseException:
        settle()
        raise
    settle()
    breaches = {name: sorted(found) for name, found in written.items() if found}
    marker = item.get_closest_marker(MARKER)
    if marker is None:
        if breaches:
            pytest.fail(_message(breaches), pytrace=False)
    elif not marker.args or not str(marker.args[0]).strip():
        pytest.fail(f"@pytest.mark.{MARKER} takes the reason as its argument", pytrace=False)
    elif not breaches:
        pytest.fail(
            f"@pytest.mark.{MARKER} is on a test that wrote every uid in the grammar — "
            "delete the marker",
            pytrace=False,
        )
    return outcome


def _message(breaches: dict[str, list[str]]) -> str:
    lines = ["the test wrote uids the uid grammar refuses (core/utils/uid_grammar.py):"]
    for name, found in breaches.items():
        lines.append(f"  {name}:")
        lines.extend(f"    {entry}" for entry in found[:_NAMED])
        if len(found) > _NAMED:
            lines.append(f"    … and {len(found) - _NAMED} more")
    lines.append(
        "Seed authored uids ({prefix}.{slug}) or the user uids tests/helpers/seed_uids.py "
        f"mints; a test that writes one on purpose carries @pytest.mark.{MARKER}(reason)."
    )
    return "\n".join(lines)
