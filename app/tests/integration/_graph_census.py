"""
What each integration test writes, held to the graph's invariants.

When a test's body ends — before any fixture teardown empties its graph — its graph is
read for three kinds of finding, each through the read the graph-health poller makes:

- **a uid outside the uid grammar, or one uid two nodes hold** (``core/utils/uid_grammar.py``;
  ``UidCensusBackend.read_breaches``);
- **a node no read can read** — a stored value its field's type refuses, or a property
  its class requires that the node does not hold
  (``adapters/persistence/neo4j/neo4j_mapper.py``);
- **a stored key no read reads** — a property that is neither a field nor registered node
  state of the class its node is read as (``core/models/node_state.py``).

The last two come from one read of the stored nodes (``StoredValueCensusBackend.read_findings``,
the read ``./dev stored-value-census`` makes). The mapper's writers leave no required field
out, refuse a value before it is stored and refuse a key no field names, so what this finds
was written by raw Cypher: a backend's, a script's, a fixture's.

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
carries its kind's marker: ``@pytest.mark.outside_uid_grammar("why")``,
``@pytest.mark.stores_unreadable_value("why")`` or ``@pytest.mark.stores_undeclared_key("why")``.
Its graph is still read, so what it leaves behind is never laid on the next test, and a
marked test that wrote no such finding — or reached no graph the census reads — fails: the
marker is stale. A marker on a module (``pytestmark``) or a class covers every test in it
and is stale only when none of them wrote such a finding: the shape a module-scoped
fixture's seed needs, whose finding the census sees in whichever test reaches it first. It
is judged at the scope's last test, and only when every test the scope holds ran its body
to the end: a run of part of a module or class (a node id, ``-k``, ``--deselect``), or one
in which a test in it skipped (an environment guard) or failed, cannot tell a stale marker
from one a test that did not run earns, and judges none. ``test_graph_census_control.py`` and the two
``test_graph_census_module_*`` files hold a control for each finding, each graph and each
marker scope; ``tests/unit/test_graph_census_marker_scopes.py`` holds the rules a run
applies to a scope.

A uid this census never sees — written to a scratch container, or named and never written —
is held by the static census instead (``tests/unit/test_integration_seed_uids.py``), which
reads every uid literal in ``tests/integration`` at the edit. Its test's marker says
``outside_uid_grammar(..., static_only=True)``, and this census holds that test as unmarked:
a breach it does see fails it. No other kind has a static census, and its marker takes no
``static_only``.

The hooks below are the census; ``tests/integration/conftest.py`` imports them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from tests.helpers.production_backends import build_production_backends

if TYPE_CHECKING:
    from collections.abc import Generator

    from _pytest.nodes import Node
    from _pytest.reports import CollectReport

    from adapters.persistence.neo4j.stored_value_census_backend import (
        StoredNodeFindings,
        StoredValueCensusBackend,
    )
    from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend
    from core.infrastructure.monitoring.uid_grammar_check import UidBreaches

# The test graphs hold a few hundred nodes: every breach is read back.
_READ_EVERY = 100_000
# What a failure names of each kind.
_NAMED = 12
# pytest-asyncio's session runner — the loop the session drivers were opened on.
_SESSION_RUNNER = "_session_scoped_runner"


@dataclass(frozen=True)
class _Reading:
    """One read of a graph: its uid breaches and what its stored nodes hold."""

    uids: UidBreaches
    stored: StoredNodeFindings


def _uid_findings(reading: _Reading) -> frozenset[str]:
    return frozenset(
        [f"outside the grammar: {entry}" for entry in reading.uids.outside_sample]
        + [f"held by two nodes: {uid}" for uid in reading.uids.shared_sample]
    )


def _unreadable_findings(reading: _Reading) -> frozenset[str]:
    return frozenset(
        f"{refusal.entity_class} {refusal.uid}.{refusal.field} = {refusal.value!r:.60} "
        f"({refusal.reason:.100})"
        for refusal in reading.stored.unreadable
    )


def _undeclared_findings(reading: _Reading) -> frozenset[str]:
    return frozenset(f"{key.entity_class} {key.uid}.{key.key}" for key in reading.stored.undeclared)


@dataclass(frozen=True)
class _Kind:
    """One finding the census reads, the marker that excuses it, and how it is told."""

    marker: str
    findings: Callable[[_Reading], frozenset[str]]
    wrote: str
    remedy: str
    #: One of the findings, and none of them, as a stale marker's message names them.
    finding: str
    none_found: str
    #: A static census holds what this one never sees (the marker's ``static_only=True``).
    static_half: bool = False


_KINDS = (
    _Kind(
        marker="outside_uid_grammar",
        findings=_uid_findings,
        wrote="the test wrote uids the uid grammar refuses (core/utils/uid_grammar.py):",
        remedy=(
            "Seed authored uids ({prefix}.{slug}) or the user uids tests/helpers/seed_uids.py "
            "mints; a test that writes one on purpose carries "
            "@pytest.mark.outside_uid_grammar(reason)."
        ),
        finding="a uid outside the grammar",
        none_found="no uid outside the grammar",
        static_half=True,
    ),
    _Kind(
        marker="stores_unreadable_value",
        findings=_unreadable_findings,
        wrote=(
            "the test wrote nodes no read can read — a stored value its field's type "
            "refuses, or a property its class requires left out "
            "(adapters/persistence/neo4j/neo4j_mapper.py):"
        ),
        remedy=(
            "Seed every property the node's class requires, each a value of its type (the "
            "enum's own values, an ISO date, a list, a JSON object); a test that writes one "
            "on purpose carries @pytest.mark.stores_unreadable_value(reason)."
        ),
        finding="a value a read refuses",
        none_found="no value a read refuses",
    ),
    _Kind(
        marker="stores_undeclared_key",
        findings=_undeclared_findings,
        wrote=(
            "the test wrote properties no read reads — a key that is neither a field nor "
            "registered node state of its node's class (core/models/node_state.py):"
        ),
        remedy=(
            "Seed only the fields the node's class declares (a user's name is its title or "
            "display_name, a group's is its name), or register a key a backend writes and "
            "reads as node state beside its class's fields; a test that writes one on "
            "purpose carries @pytest.mark.stores_undeclared_key(reason)."
        ),
        finding="an undeclared key",
        none_found="no undeclared key",
    ),
)


@dataclass
class _Graph:
    read: Callable[[], Awaitable[dict[str, frozenset[str]]]]
    found: dict[str, frozenset[str]] = field(default_factory=dict)


def _graph_for(driver: object) -> _Graph:
    """The census of one graph: every kind's findings, from one read of its uids and one
    of its stored nodes."""
    backends = build_production_backends(driver)
    uid_census: UidCensusBackend = backends["uid_census_backend"]
    stored_census: StoredValueCensusBackend = backends["stored_value_census_backend"]

    async def read() -> dict[str, frozenset[str]]:
        uids = await uid_census.read_breaches(_READ_EVERY)
        if uids.is_error:
            raise RuntimeError(f"uid census could not read the graph: {uids.expect_error()}")
        stored = await stored_census.read_findings()
        if stored.is_error:
            raise RuntimeError(
                f"stored-value census could not read the graph: {stored.expect_error()}"
            )
        reading = _Reading(uids=uids.value, stored=stored.value)
        return {kind.marker: kind.findings(reading) for kind in _KINDS}

    return _Graph(read)


@dataclass
class _Census:
    """One session's census: its graphs and what it knows of the run's scopes."""

    graphs: dict[str, _Graph] = field(default_factory=dict)
    runner: asyncio.Runner | None = None
    #: (scope node id, marker) → whether any test in a module/class marker's scope wrote one.
    scope_wrote: dict[tuple[str, str], bool] = field(default_factory=dict)
    #: scope node id → the node id of its last selected test.
    last_in_scope: dict[str, str] = field(default_factory=dict)
    #: collector node id → the node ids of everything it collected.
    collected: dict[str, list[str]] = field(default_factory=dict)
    #: the tests whose body ran to its end.
    ran: set[str] = field(default_factory=set)


_CENSUS = pytest.StashKey[_Census]()


def _census(session: pytest.Session) -> _Census:
    return session.stash.setdefault(_CENSUS, _Census())


def _drivers(item: pytest.Item) -> dict[str, object]:
    funcargs = getattr(item, "funcargs", {})
    drivers: dict[str, object] = {}
    if "neo4j_driver" in funcargs:
        drivers["shared container"] = funcargs["neo4j_driver"]
    if "skuel_app" in funcargs:
        drivers["app container"] = funcargs["skuel_app"].state.services.neo4j_driver
    return drivers


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(
    collector: pytest.Collector,
) -> Generator[None, CollectReport, CollectReport]:
    """Record what each collector holds: a scope's marker is judged only when all of it ran."""
    report = yield
    if report.passed:
        _census(collector.session).collected[collector.nodeid] = [
            node.nodeid for node in report.result
        ]
    return report


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    """Read every graph a test has reached so far: what the next test starts on."""
    census = _census(item.session)
    if census.runner is not None:
        for graph in census.graphs.values():
            graph.found = census.runner.run(graph.read())
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    """Read the test's graphs before and after its body; fail it on what it wrote that the
    graph's invariants refuse — a uid outside the grammar, a stored value no read can read,
    a stored key no read reads."""
    census = _census(item.session)
    drivers = _drivers(item)
    if not drivers:
        outcome = yield
        census.ran.add(item.nodeid)
        _fail_on(_judge(item, {}, reached_a_graph=False))
        return outcome
    if census.runner is None:
        census.runner = item._request.getfixturevalue(_SESSION_RUNNER)  # type: ignore[attr-defined]
    runner = census.runner
    for name, driver in drivers.items():
        if name not in census.graphs:
            census.graphs[name] = _graph_for(driver)

    written: dict[str, dict[str, set[str]]] = {kind.marker: {} for kind in _KINDS}

    def take(name: str) -> None:
        graph = census.graphs[name]
        now = runner.run(graph.read())
        for kind in _KINDS:
            before = graph.found.get(kind.marker, frozenset())
            written[kind.marker].setdefault(name, set()).update(now[kind.marker] - before)
        graph.found = now

    def findings() -> dict[str, dict[str, list[str]]]:
        return {
            marker: {name: sorted(found) for name, found in by_graph.items() if found}
            for marker, by_graph in written.items()
        }

    for name in drivers:
        take(name)
    try:
        outcome = yield
    except BaseException:
        # A body that skips or fails is not judged, and its scope's markers are judged by
        # no test: what it would have written is unknown. What it did write still counts.
        for name in drivers:
            take(name)
        _tally(item, findings())
        raise
    for name in drivers:
        take(name)
    census.ran.add(item.nodeid)
    _fail_on(_judge(item, findings(), reached_a_graph=True))
    return outcome


def _closest_marker(item: pytest.Item, name: str) -> tuple[pytest.Mark, Node] | None:
    """The marker nearest the test, and the node that carries it (the test, a class, a module)."""
    for node in reversed(item.listchain()):
        for mark in node.own_markers:
            if mark.name == name:
                return mark, node
    return None


def _ran_whole(census: _Census, nodeid: str) -> bool:
    """Whether everything ``nodeid`` collected ran its body to the end — a test, or a scope."""
    children = census.collected.get(nodeid)
    if children is None:
        return nodeid in census.ran
    return all(_ran_whole(census, child) for child in children)


def _is_last_in_scope(census: _Census, item: pytest.Item, scope: Node) -> bool:
    if not census.last_in_scope:
        for selected in item.session.items:
            for node in selected.listchain():
                census.last_in_scope[node.nodeid] = selected.nodeid
    return census.last_in_scope.get(scope.nodeid) == item.nodeid


def _stale_scope(item: pytest.Item, kind: _Kind, owner: Node) -> str | None:
    """A module/class marker none of its tests earned, judged at its last test."""
    census = _census(item.session)
    if not _is_last_in_scope(census, item, owner):
        return None
    if census.scope_wrote.get((owner.nodeid, kind.marker), False):
        return None
    if not _ran_whole(census, owner.nodeid):
        return None
    return (
        f"@pytest.mark.{kind.marker} is on {owner.nodeid}, and no test in it wrote "
        f"{kind.finding} — delete the marker"
    )


def _marker_refusal(kind: _Kind, mark: pytest.Mark) -> str | None:
    if not mark.args or not str(mark.args[0]).strip():
        return f"@pytest.mark.{kind.marker} takes the reason as its argument"
    if "static_only" in mark.kwargs and not kind.static_half:
        return (
            f"@pytest.mark.{kind.marker} takes no static_only — no static census reads "
            "what this census never sees of its kind"
        )
    return None


def _tally(item: pytest.Item, findings: dict[str, dict[str, list[str]]]) -> None:
    """Count what the test wrote toward each module/class marker over it."""
    census = _census(item.session)
    for kind in _KINDS:
        closest = _closest_marker(item, kind.marker)
        if closest is None or closest[1] is item:
            continue
        key = (closest[1].nodeid, kind.marker)
        census.scope_wrote[key] = census.scope_wrote.get(key, False) or bool(
            findings.get(kind.marker)
        )


def _judge(
    item: pytest.Item, findings: dict[str, dict[str, list[str]]], *, reached_a_graph: bool
) -> list[str]:
    """Each kind's findings its markers do not excuse, and each stale marker."""
    _tally(item, findings)
    failures = []
    for kind in _KINDS:
        found = findings.get(kind.marker, {})
        closest = _closest_marker(item, kind.marker)
        if closest is None:
            if found:
                failures.append(_message(kind, found))
            continue
        mark, owner = closest
        refusal = _marker_refusal(kind, mark)
        if refusal:
            failures.append(refusal)
            continue
        if mark.kwargs.get("static_only") is True:
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
        stale = _stale_scope(item, kind, owner)
        if stale:
            failures.append(stale)
    return failures


def _fail_on(failures: list[str]) -> None:
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
