"""The page chrome is built only by the page shells.

The navbar and the bottom nav come from ``BasePage`` (and ``SidebarPage`` through it),
which build them from the request a page hands over. A body that builds its own
navbar is a page without the shell: no bottom nav below ``sm``, no skip link, and a bar
inside the page's padding instead of across the top. This census reads every call to a
chrome builder under ``ui/`` and ``adapters/inbound/`` and holds each to the shells'
module.

A call is found by the name it is made through: a builder's own name, an import alias
of one (``from ui.layouts.navbar import create_navbar as nav``), or an attribute of a
module (``navbar_module.create_navbar(...)``). The census runs once against a sample
that hand-builds a navbar through an alias, which it must catch, and must find the
shell's own calls, so a walk that finds nothing fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[3]
ROOTS = ("ui", "adapters/inbound")
BUILDERS = frozenset(
    {
        "create_navbar",
        "create_navbar_for_request",
        "create_bottom_nav",
        "create_bottom_nav_for_request",
    }
)
# The shell, and the builders' own module (the request helpers call the primitives).
SHELL_MODULES = frozenset({"ui/layouts/base_page.py", "ui/layouts/navbar.py"})


def builder_calls(source: str) -> list[tuple[int, str]]:
    """Every call in ``source`` to a chrome builder: (line, builder name)."""
    tree = ast.parse(source)
    aliases = {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in BUILDERS
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in aliases:
            found.append((node.lineno, aliases[func.id]))
        elif isinstance(func, ast.Attribute) and func.attr in BUILDERS:
            found.append((node.lineno, func.attr))
    return found


def census() -> dict[str, list[tuple[int, str]]]:
    """Builder calls per module, for every module that makes one."""
    calls = {}
    for root in ROOTS:
        for path in sorted((APP / root).rglob("*.py")):
            found = builder_calls(path.read_text())
            if found:
                calls[path.relative_to(APP).as_posix()] = found
    return calls


def test_only_the_shells_build_the_page_chrome() -> None:
    outside = {module: calls for module, calls in census().items() if module not in SHELL_MODULES}

    assert outside == {}, (
        "A page builds its own navbar or bottom nav. Hand the body and the request to "
        f"BasePage (or SidebarPage) instead: {outside}"
    )


def test_the_census_finds_the_shells_own_calls() -> None:
    """The positive control: the walk reaches the shell and reads both of its builders."""
    names = {name for _, name in census().get("ui/layouts/base_page.py", [])}

    assert {"create_navbar_for_request", "create_bottom_nav_for_request"} <= names


def test_the_census_catches_a_hand_built_navbar_through_an_alias() -> None:
    """The sample that must fail: a body that builds its own navbar under another name,
    and one that reaches a builder through its module."""
    sample = (
        "from ui.layouts.navbar import create_navbar_for_request as nav\n"
        "import ui.layouts.navbar as chrome\n"
        "def page(request):\n"
        "    return Div(nav(request), chrome.create_bottom_nav(), Div('body'))\n"
    )

    assert builder_calls(sample) == [(4, "create_navbar_for_request"), (4, "create_bottom_nav")]
