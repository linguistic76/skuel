"""
What each integration test writes, held to the graph's invariants.

When a test's body ends — before any fixture teardown empties its graph — its graph is
read for two kinds of finding, each through the read the graph-health poller makes:

- **a uid outside the uid grammar, or one uid two nodes hold** (``core/utils/uid_grammar.py``;
  ``UidCensusBackend.read_breaches``);
- **a stored value no read of its node can read** — a value its field's type refuses
  (``adapters/persistence/neo4j/neo4j_mapper.py``; ``StoredValueCensusBackend.read_unreadable``,
  the read ``./dev stored-value-census`` makes). The mapper's writers refuse one before it
  is stored, so what this finds was written by raw Cypher: a backend's, a script's, a
  fixture's.

The test fails on a finding it wrote. Two graphs are read, each when a test reaches it:
the shared container's (``neo4j_driver``) and the bootstrapped app's (``skuel_app``). A
scratch container is its test's own and is not read.

A finding is the test's when it was not in the graph before the test began.
``clean_neo4j`` keeps every ``:User`` and plenty of tests leave what they wrote, so a test
starts on whatever the last one left; and the last one's teardown may delete what the next
one's setup writes again. So each graph is read three times: when the test's setup starts
(what it starts on), when its body starts (adding what its fixtures wrote) and when its body
ends (what the body wrote). A finding written and removed inside one of those spans is not
seen.

A test that writes one on purpose — an old-shape graph a migration reads, a refusal path —
carries its kind's marker: ``@pytest.mark.outside_uid_grammar("why")`` or
``@pytest.mark.stores_unreadable_value("why")``. Its graph is still read, so what it leaves
behind is never laid on the next test, and a marked test that wrote no such finding — or
reached no graph the census reads — fails: the marker is stale. A marker on a module
(``pytestmark``) or a class covers every test in it and is stale only when none of them
wrote such a finding, judged at its last test: the shape a module-scoped fixture's seed
needs, whose finding the census sees in whichever test reaches it first.
``test_graph_census_control.py`` holds one control per finding, graph and marker scope.

A uid this census never sees — written to a scratch container, or named and never written —
is held by the static census instead (``tests/unit/test_integration_seed_uids.py``), which
reads every uid literal in ``tests/integration`` at the edit. Its test's marker says
``outside_uid_grammar(..., static_only=True)``, and this census holds that test as unmarked:
a breach it does see fails it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from adapters.persistence.neo4j.stored_value_census_backend import StoredValueCensusBackend
from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend
from tests.helpers.production_backends import build_production_backends

if TYPE_CHECKING:
    from collections.abc import Generator

    from _pytest.nodes import Node
    from neo4j import AsyncDriver

# The test graphs hold a few hundred nodes: every breach is read back.
_READ_EVERY = 100_000
# What a failure names of each kind.
_NAMED = 12
# pytest-asyncio's session runner — the loop the session drivers were opened on.
_SESSION_RUNNER = "_session_scoped_runner"


async def _uid_breaches(backends: dict[str, object]) -> frozenset[str]:
    backend = backends["uid_census_backend"]
    assert isinstance(backend, UidCensusBackend)
    result = await backend.read_breaches(_READ_EVERY)
    if result.is_error:
        raise RuntimeError(f"uid census could not read the graph: {result.expect_error()}")
    breaches = result.value
    return frozenset(
        [f"outside the grammar: {entry}" for entry in breaches.outside_sample]
        + [f"held by two nodes: {uid}" for uid in breaches.shared_sample]
    )


async def _unreadable_values(backends: dict[str, object]) -> frozenset[str]:
    backend = backends["stored_value_census_backend"]
    assert isinstance(backend, StoredValueCensusBackend)
    result = await backend.read_unreadable()
    if result.is_error:
        raise RuntimeError(f"stored-value census could not read the graph: {result.expect_error()}")
    return frozenset(
        f"{refusal.entity_class} {refusal.uid}.{refusal.field} = {refusal.value!r:.60} "
        f"({refusal.reason:.100})"
        for refusal in result.value
    )


@dataclass(frozen=True)
class _Kind:
    """One finding the census reads, the marker that excuses it, and how it is told."""

    marker: str
    read: Callable[[dict[str, object]], Awaitable[frozenset[str]]]
    wrote: str
    remedy: str
    #: One of the findings, and none of them, as a stale marker's message names them.
    finding: str
    none_found: str


_KINDS = (
    _Kind(
        marker="outside_uid_grammar",
        read=_uid_breaches,
        wrote="the test wrote uids the uid grammar refuses (core/utils/uid_grammar.py):",
        remedy=(
            "Seed authored uids ({prefix}.{slug}) or the user uids tests/helpers/seed_uids.py "
            "mints; a test that writes one on purpose carries "
            "@pytest.mark.outside_uid_grammar(reason)."
        ),
        finding="a uid outside the grammar",
        none_found="no uid outside the grammar",
    ),
    _Kind(
        marker="stores_unreadable_value",
        read=_unreadable_values,
        wrote=(
            "the test wrote stored values no read of their node can read "
            "(adapters/persistence/neo4j/neo4j_mapper.py):"
        ),
        remedy=(
            "Seed each field a value of its type (the enum's own values, an ISO date, a "
            "list, a JSON object); a test that writes one on purpose carries "
            "@pytest.mark.stores_unreadable_value(reason)."
        ),
        finding="a value a read refuses",
        none_found="no value a read refuses",
    ),
)


@dataclass
class _Graph:
    backends: dict[str, object]
    found: dict[str, frozenset[str]] = field(default_factory=dict)


_graphs: dict[str, _Graph] = {}
_runner: asyncio.Runner | None = None
#: (scope node id, marker) → whether any test in a module/class marker's scope wrote one.
_scope_wrote: dict[tuple[str, str], bool] = {}
#: scope node id → the node id of its last collected test.
_last_in_scope: dict[str, str] = {}


async def _read(graph: _Graph) -> dict[str, frozenset[str]]:
    return {kind.marker: await kind.read(graph.backends) for kind in _KINDS}


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
        graph.found = _runner.run(_read(graph))


def _closest_marker(item: pytest.Item, name: str) -> tuple[pytest.Mark, Node] | None:
    """The marker nearest the test, and the node that carries it (the test, a class, a module)."""
    for node in reversed(item.listchain()):
        for mark in node.own_markers:
            if mark.name == name:
                return mark, node
    return None


def _is_last_in_scope(item: pytest.Item, scope: Node) -> bool:
    if not _last_in_scope:
        for collected in item.session.items:
            for node in collected.listchain():
                _last_in_scope[node.nodeid] = collected.nodeid
    return _last_in_scope.get(scope.nodeid) == item.nodeid


def census_call(item: pytest.Item) -> Generator[None, object, object]:
    """Wrap a test's call: read its graphs before and after the body, fail on its findings."""
    global _runner
    drivers = _drivers(item)
    if not drivers:
        outcome = yield
        _judge(item, {}, reached_a_graph=False)
        return outcome
    if _runner is None:
        _runner = item._request.getfixturevalue(_SESSION_RUNNER)  # type: ignore[attr-defined]
    runner = _runner
    for name, driver in drivers.items():
        if name not in _graphs:
            backends = build_production_backends(driver)
            _graphs[name] = _Graph(
                {
                    "uid_census_backend": backends["uid_census_backend"],
                    "stored_value_census_backend": backends["stored_value_census_backend"],
                }
            )

    written: dict[str, dict[str, set[str]]] = {kind.marker: {} for kind in _KINDS}

    def take(name: str, now: dict[str, frozenset[str]]) -> None:
        graph = _graphs[name]
        for kind in _KINDS:
            before = graph.found.get(kind.marker, frozenset())
            written[kind.marker].setdefault(name, set()).update(now[kind.marker] - before)
        graph.found = now

    for name in drivers:
        take(name, runner.run(_read(_graphs[name])))

    def settle() -> None:
        for name in drivers:
            take(name, runner.run(_read(_graphs[name])))

    try:
        outcome = yield
    except BaseException:
        settle()
        raise
    settle()
    _judge(
        item,
        {
            marker: {name: sorted(found) for name, found in by_graph.items() if found}
            for marker, by_graph in written.items()
        },
        reached_a_graph=True,
    )
    return outcome


def _judge(
    item: pytest.Item, findings: dict[str, dict[str, list[str]]], *, reached_a_graph: bool
) -> None:
    """Fail the test on each kind's findings its markers do not excuse, and on a stale marker."""
    failures = []
    for kind in _KINDS:
        found = findings.get(kind.marker, {})
        closest = _closest_marker(item, kind.marker)
        if closest is None:
            if found:
                failures.append(_message(kind, found))
            continue
        mark, owner = closest
        if not mark.args or not str(mark.args[0]).strip():
            failures.append(f"@pytest.mark.{kind.marker} takes the reason as its argument")
            continue
        static_only = mark.kwargs.get("static_only") is True
        if static_only:
            # The static census holds it; this census holds the test as unmarked.
            if found:
                failures.append(
                    _message(kind, found)
                    + "\nIts marker says static_only=True — a uid this census never sees — "
                    "but it saw these: drop static_only."
                )
            continue
        if owner is item:
            if not reached_a_graph:
                failures.append(
                    f"@pytest.mark.{kind.marker} is on a test that reaches no graph the "
                    "census reads — delete the marker"
                )
            elif not found:
                failures.append(
                    f"@pytest.mark.{kind.marker} is on a test that wrote {kind.none_found} — "
                    "delete the marker"
                )
            continue
        key = (owner.nodeid, kind.marker)
        _scope_wrote[key] = _scope_wrote.get(key, False) or bool(found)
        if _is_last_in_scope(item, owner) and not _scope_wrote[key]:
            failures.append(
                f"@pytest.mark.{kind.marker} is on {owner.nodeid}, and no test in it wrote "
                f"{kind.finding} — delete the marker"
            )
    if failures:
        pytest.fail("\n\n".join(failures), pytrace=False)


def _message(kind: _Kind, found: dict[str, list[str]]) -> str:
    lines = [kind.wrote]
    for name, entries in found.items():
        lines.append(f"  {name}:")
        lines.extend(f"    {entry}" for entry in entries[:_NAMED])
        if len(entries) > _NAMED:
            lines.append(f"    … and {len(entries) - _NAMED} more")
    lines.append(kind.remedy)
    return "\n".join(lines)
