"""No test module reads the clock at import.

A day fixed when a module is imported stays fixed for the whole run, and the service under
test asks the clock when it is called, so a run crossing midnight fails whatever the change.
A module takes its day from ``tests/helpers/run_clock.py`` and holds the clock on it, or
names a literal when the test never asks what day it is. That module is the one place the
clock is read at import, with the probe that crosses midnight on purpose.

Read: every statement that runs at import, at module level or in a class body, with the
decorators and default arguments of what it defines. A function body runs later, and a
lambda too. A fixture that seeds today and a test that reads it again is the same defect,
out of this census's sight: ``tests/helpers/midnight_probe.py`` is what finds that, and
``usefixtures("held_run_clock")`` is the cure for both.
"""

from __future__ import annotations

import ast
from pathlib import Path

import core.utils.timestamp_helpers
import core.utils.zone_context

TESTS_ROOT = Path(__file__).resolve().parents[1]
ROOTS = tuple(TESTS_ROOT / tree for tree in ("integration", "unit", "helpers", "fixtures"))
READS_THE_CLOCK_ON_PURPOSE = frozenset(
    TESTS_ROOT / "helpers" / name for name in ("run_clock.py", "midnight_probe.py")
)

_STDLIB_CLOCK_READS = frozenset({"now", "utcnow", "today"})


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _clock_reads() -> frozenset[str]:
    """The stdlib's reads plus every project helper that reaches one, directly or through
    another helper. Derived, so a new helper is covered."""
    functions: list[ast.FunctionDef] = []
    for module in (core.utils.timestamp_helpers, core.utils.zone_context):
        assert module.__file__ is not None
        functions.extend(
            node
            for node in ast.parse(Path(module.__file__).read_text()).body
            if isinstance(node, ast.FunctionDef)
        )
    reads = set(_STDLIB_CLOCK_READS)
    while True:
        reached = {
            function.name
            for function in functions
            if any(
                isinstance(inner, ast.Call) and _called_name(inner) in reads
                for inner in ast.walk(function)
            )
        }
        if reached <= reads:
            return frozenset(reads)
        reads |= reached


_CLOCK_READS = _clock_reads()


def _clock_calls(node: ast.AST) -> list[ast.Call]:
    """The clock reads under ``node``, stopping where evaluation is deferred."""
    if isinstance(node, ast.Lambda):
        return []
    found = [node] if isinstance(node, ast.Call) and _called_name(node) in _CLOCK_READS else []
    for child in ast.iter_child_nodes(node):
        found.extend(_clock_calls(child))
    return found


def _import_time_expressions(body: list[ast.stmt]) -> list[ast.AST]:
    """What this block evaluates when it runs: all of a statement but a def's or class's body."""
    expressions: list[ast.AST] = []
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            expressions.extend(statement.decorator_list)
            expressions.extend(statement.args.defaults)
            expressions.extend(d for d in statement.args.kw_defaults if d is not None)
        elif isinstance(statement, ast.ClassDef):
            expressions.extend(statement.decorator_list)
            expressions.extend(_import_time_expressions(statement.body))
        else:
            expressions.append(statement)
    return expressions


def read_source(source: str) -> list[str]:
    """Each import-time clock read in ``source``, as ``line: call``."""
    return [
        f"{call.lineno}: {ast.unparse(call.func)}()"
        for expression in _import_time_expressions(ast.parse(source).body)
        for call in _clock_calls(expression)
    ]


def _sources() -> list[Path]:
    trees = [path for root in ROOTS for path in sorted(root.rglob("*.py"))]
    return [
        path
        for path in [*trees, TESTS_ROOT / "conftest.py"]
        if path not in READS_THE_CLOCK_ON_PURPOSE
    ]


def test_no_test_module_reads_the_clock_at_import() -> None:
    findings = [
        f"{path.relative_to(TESTS_ROOT)}:{finding}"
        for path in _sources()
        for finding in read_source(path.read_text())
    ]

    assert not findings, (
        "Read the clock inside a test, or take the day from tests/helpers/run_clock.py and "
        "hold it with usefixtures('held_run_clock'), or name a literal:\n  " + "\n  ".join(findings)
    )


def test_the_census_reads_the_helpers_the_project_tells_the_time_with() -> None:
    assert {"today_in", "now_in", "now_utc", "today_in_current_zone"} <= _CLOCK_READS


def test_the_census_refuses_each_shape() -> None:
    for source in (
        "TODAY = today_in(current_zone())",
        "NOW: datetime = datetime.now(UTC)",
        "TOMORROW = date.today() + timedelta(days=1)",
        "SPAN = [today_in(zone) - timedelta(days=n) for n in range(3)]",
        "SEED = {'expires_at': now_utc() - timedelta(days=1)}",
        "class T:\n    DAY = date.today()",
        "def f(day=date.today()): ...",
        "async def f(*, day=date.today()): ...",
        "@pytest.mark.parametrize('day', [date.today()])\ndef test(day): ...",
        "class T:\n    @pytest.mark.parametrize('day', [today_in(z)])\n    def test(self, day): ...",
        "@skipif(date.today().weekday() == 5)\nclass T: ...",
    ):
        assert read_source(source), source


def test_the_census_passes_what_is_not_read_at_import() -> None:
    for source in (
        "def f():\n    return date.today()",
        "async def f():\n    return datetime.now(UTC)",
        "class T:\n    def f(self):\n        return today_in(z)",
        "FACTORY = lambda: date.today()",
        "DAY = RUN_TODAY",
        "UPCOMING = date(2099, 1, 5)",
        "def f():\n    @decorate(date.today())\n    def g(): ...",
    ):
        assert not read_source(source), source


def test_a_finding_names_its_line_and_its_call() -> None:
    assert read_source("A = 1\nTODAY = date.today()") == ["2: date.today()"]
