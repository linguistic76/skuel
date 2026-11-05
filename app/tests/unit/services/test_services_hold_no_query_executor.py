"""A service holds no raw query executor.

Cypher lives below the hexagonal boundary (SKUEL021), so a service has nothing it
may run on an executor: a constructor that takes one takes a dependency it can only
store. Reads and writes go through a backend protocol from ``core/ports``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from core.services.ps_service import PsService

_ROOT = Path(__file__).resolve().parents[3]
_SCANNED = ("core/services", "core/orchestrator")
_EXECUTOR_PARAMETERS = {"executor", "_executor"}


def _executor_parameters(tree: ast.Module) -> list[tuple[str, int]]:
    """Every function parameter in ``tree`` named as a raw query executor."""
    return [
        (node.name, argument.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        if argument.arg in _EXECUTOR_PARAMETERS
    ]


def _scanned_files() -> list[Path]:
    return [path for root in _SCANNED for path in sorted((_ROOT / root).rglob("*.py"))]


def test_no_service_function_takes_a_query_executor() -> None:
    offenders = [
        f"{path.relative_to(_ROOT)}:{line} {name}"
        for path in _scanned_files()
        for name, line in _executor_parameters(ast.parse(path.read_text()))
    ]
    assert not offenders, offenders


def test_the_scan_reads_the_files_it_names() -> None:
    """A scan that walked nothing would read as a clean pass."""
    scanned = {path.relative_to(_ROOT).as_posix() for path in _scanned_files()}
    assert "core/services/ps_service.py" in scanned
    assert "core/services/report/progress_report_generator.py" in scanned
    assert "core/orchestrator/user_entry_orchestrator.py" in scanned


def test_the_scan_finds_a_parameter_of_each_kind() -> None:
    tree = ast.parse(
        "class Service:\n"
        "    def __init__(self, executor): ...\n"
        "async def build(*, _executor=None): ...\n"
        "def read(backend): ...\n"
    )
    assert set(_executor_parameters(tree)) == {("__init__", 2), ("build", 3)}


def test_ps_service_builds_on_its_backend_alone() -> None:
    """Boot refuses a missing required dependency; a query executor is not one."""
    service = PsService(backend=MagicMock(), graph_intel=MagicMock())
    assert service.repo is not None
