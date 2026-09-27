"""No uncalled ``date.today`` reference in the guarded trees (UTC arc, PR 2b).

Ruff's ``DTZ011`` sees a *call* to ``date.today()``. A reference passed on
uncalled — ``Field(default_factory=date.today)``, a stamp factory in a table, a
callable default — reads the host's day just the same, and no rule sees it.
This check does: it walks every module's AST, resolves the names ``date`` and
``datetime`` are imported under, and lists each ``date.today`` that is not the
function of a call. "Today" is today in a zone
(``core.utils.zone_context.today_in_current_zone``, or ``today_in(zone)``).

The guarded trees grow with the arc: ``core/`` from PR 2b's first sub-row,
``adapters/`` and ``ui/`` from its second; PR 8 adds ``datetime.now`` and PR 9
moves the check into the lint.

See: /docs/roadmap/utc-instants-arc.md § PR 2b
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2]

GUARDED_TREES = ("core",)


def _clock_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The local names bound to the ``date`` class and to the ``datetime`` module."""
    date_names: set[str] = set()
    module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            for alias in node.names:
                if alias.name == "date":
                    date_names.add(alias.asname or "date")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datetime":
                    module_names.add(alias.asname or "datetime")
    return date_names, module_names


def _is_date_today(node: ast.Attribute, date_names: set[str], module_names: set[str]) -> bool:
    if node.attr != "today":
        return False
    value = node.value
    if isinstance(value, ast.Name):
        return value.id in date_names
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "date"
        and isinstance(value.value, ast.Name)
        and value.value.id in module_names
    )


def uncalled_date_today(source: str) -> list[int]:
    """Line numbers of every ``date.today`` reference in ``source`` that is not called."""
    tree = ast.parse(source)
    date_names, module_names = _clock_names(tree)
    called = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and id(node) not in called
        and _is_date_today(node, date_names, module_names)
    )


@pytest.mark.parametrize("tree", GUARDED_TREES)
def test_no_uncalled_date_today_in_the_guarded_trees(tree: str) -> None:
    found = [
        f"{path.relative_to(APP_ROOT)}:{line}"
        for path in sorted((APP_ROOT / tree).rglob("*.py"))
        for line in uncalled_date_today(path.read_text())
    ]
    assert found == [], (
        "an uncalled date.today reads the host's day; use "
        "today_in_current_zone (core.utils.zone_context):\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        ("from datetime import date\nx = Field(default_factory=date.today)\n", [2]),
        ("from datetime import date as _d\nf = _d.today\n", [2]),
        ("import datetime\nspec = (1, datetime.date.today)\n", [2]),
        ("import datetime as dt\nf = dt.date.today\n", [2]),
        # A call is DTZ011's, not this check's; an unrelated `today` is nobody's.
        ("from datetime import date\nx = date.today()\n", []),
        ("from datetime import date\nx = report.today\n", []),
        ("x = date.today\n", []),  # no `date` imported from datetime here
    ],
)
def test_the_check_finds_every_spelling_of_an_uncalled_reference(
    source: str, lines: list[int]
) -> None:
    assert uncalled_date_today(source) == lines
