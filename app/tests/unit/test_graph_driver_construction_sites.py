"""Every Neo4j driver is built by the one factory, in a process pinned to UTC.

``adapters/persistence/neo4j/graph_driver.py`` holds the only construction of a
driver (``open_async_driver``), and the factory refuses a process whose clock is
not pinned (``tests/unit/utils/test_process_clock.py``). These tests hold the two
halves of that shut over the whole tracked tree:

- no other file names the neo4j driver constructors (``AsyncGraphDatabase``,
  ``GraphDatabase`` and the driver classes behind them), so every driver goes
  through the factory's check;
- outside the tests, only ``Neo4jConnection`` calls the factory, so every
  production opener also runs the graph's data-version check;
- every entry point that opens the graph pins the process clock before its first
  first-party import — the scripts, ``main.py``, the test root.

See: /docs/roadmap/utc-instants-arc.md § PR 4
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[2]

#: The one file allowed to construct a driver, and the one production caller of it.
FACTORY = "adapters/persistence/neo4j/graph_driver.py"
CONNECTION = "adapters/persistence/neo4j/neo4j_connection.py"

#: The neo4j names that construct a driver.
CONSTRUCTORS = frozenset(
    {
        "AsyncGraphDatabase",
        "GraphDatabase",
        "AsyncBoltDriver",
        "AsyncNeo4jDriver",
        "BoltDriver",
        "Neo4jDriver",
    }
)

#: Importing any of these opens (or can open) the graph.
OPENERS = (
    "adapters.persistence.neo4j.neo4j_connection",
    "adapters.persistence.neo4j_adapter",
    "adapters.persistence.neo4j.graph_driver",
    "scripts.dev.bootstrap",
    "services_bootstrap",
)

FIRST_PARTY = frozenset({"core", "adapters", "services_bootstrap", "scripts", "ui", "tests"})
PIN_MODULE = "core.utils.process_clock"
PIN_CALL = "pin_process_clock_to_utc"


def _tracked(*patterns: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *patterns], cwd=APP, capture_output=True, text=True, check=True
    ).stdout
    return sorted(set(out.split()))


def _python_sources() -> dict[str, str]:
    """Every tracked Python source, by path."""
    return {path: (APP / path).read_text() for path in _tracked("*.py")}


def _constructor_uses(tree: ast.AST) -> list[int]:
    """Lines that import a driver constructor from neo4j or reach one as ``neo4j.X``."""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "neo4j":
            if any(alias.name in CONSTRUCTORS for alias in node.names):
                lines.append(node.lineno)
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in CONSTRUCTORS
            and isinstance(node.value, ast.Name)
            and node.value.id == "neo4j"
        ):
            lines.append(node.lineno)
    return lines


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def _opens_the_graph(tree: ast.AST) -> bool:
    return any(
        module == opener or module.startswith(opener + ".")
        for module in _imported_modules(tree)
        for opener in OPENERS
    )


def _is_entry_point(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.If) and "__main__" in ast.unparse(node.test) for node in tree.body
    )


def _pins_before_first_party(body: list[ast.stmt]) -> bool:
    """Whether a top-level ``pin_process_clock_to_utc()`` precedes every other first-party import."""
    for node in body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == PIN_CALL
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == PIN_MODULE:
                continue
            if node.module.split(".")[0] in FIRST_PARTY:
                return False
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] in FIRST_PARTY for alias in node.names
        ):
            return False
    return False


def test_only_the_factory_constructs_a_driver() -> None:
    offenders = {}
    for path, source in _python_sources().items():
        if path == FACTORY:
            continue
        lines = _constructor_uses(ast.parse(source))
        if lines:
            offenders[path] = lines
    assert not offenders, (
        "A Neo4j driver is constructed outside the factory. Build it with "
        f"open_async_driver ({FACTORY}), or open the graph with Neo4jConnection: {offenders}"
    )


def test_outside_the_tests_only_the_connection_calls_the_factory() -> None:
    """Every production opener goes through ``Neo4jConnection.connect``, which runs the
    data-version check after building the driver; a test fixture may build one directly."""
    callers = set()
    for path, source in _python_sources().items():
        if path.startswith("tests/"):
            continue
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open_async_driver"
            ):
                callers.add(path)
    assert callers == {CONNECTION}, (
        f"open_async_driver is called outside {CONNECTION}: {sorted(callers - {CONNECTION})}. "
        "Open the graph with Neo4jConnection, so the data-version check runs."
    )


def test_the_factory_is_the_constructor_it_claims_to_be() -> None:
    """The scan above would pass over an empty factory; the factory names the constructor."""
    assert _constructor_uses(ast.parse((APP / FACTORY).read_text()))


def test_every_entry_point_that_opens_the_graph_pins_the_clock_first() -> None:
    sources = _python_sources()
    unpinned = []
    entry_points = 0
    for path, source in sources.items():
        tree = ast.parse(source)
        if path in ("main.py", "tests/conftest.py") or (
            _is_entry_point(tree) and _opens_the_graph(tree)
        ):
            entry_points += 1
            if not _pins_before_first_party(tree.body):
                unpinned.append(path)
    assert entry_points > 50, f"the scan found only {entry_points} graph-opening entry points"
    assert not unpinned, (
        f"These entry points open the graph but do not call {PIN_CALL}() before their "
        f"first first-party import ({PIN_MODULE}): {unpinned}"
    )
