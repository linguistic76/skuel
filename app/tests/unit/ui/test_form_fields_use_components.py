"""Every visible text field and select in the UI is ``Input`` / ``Select`` from ``ui.components``.

The components carry the field heights (44px on phones, 40px from ``md``; the
``compact`` size for dense chat chrome), the shared focus ring and the theme
tokens. A raw ``fasthtml`` ``Input`` or ``Select`` carries none of it unless its
caller re-types every class by hand, so the guard fails on one anywhere in
``ui/`` or ``adapters/inbound/`` outside ``ui/components/`` — imported by name
(aliased or not), by ``*``, or called through the module (``fh.Input``).

A raw ``Input`` of type ``hidden``, ``checkbox``, ``radio`` or ``file`` is exempt
by rule — none of them is a text field. The type must be readable from the call:
an ``Input(**attrs)`` whose type lives in the dict is reported, and the fix is a
literal ``type=`` at the call or the component, never an allowlist entry.

Raw ``Textarea`` is out of scope (unruled); field markup built inside HTML or JS
strings is invisible to an AST walk.
"""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCANNED_TREES = ("ui", "adapters/inbound")
EXEMPT_TREE = APP_ROOT / "ui" / "components"
GUARDED = frozenset({"Input", "Select"})
EXEMPT_INPUT_TYPES = frozenset({"hidden", "checkbox", "radio", "file"})


def _is_fasthtml(module: str | None) -> bool:
    return module is not None and (module == "fasthtml" or module.startswith("fasthtml."))


def _bindings(tree: ast.Module) -> tuple[list[tuple[int, str, str | None]], set[str]]:
    """Every import that binds a name, in line order, plus the fasthtml module aliases.

    Each binding is ``(line, local name, guarded fasthtml name or None)`` — None
    when the name comes from anywhere else, so a later ``from ui.components
    import Input`` shadows an earlier raw import. A ``*`` from fasthtml binds
    both guarded names.
    """
    bindings: list[tuple[int, str, str | None]] = []
    module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            raw = _is_fasthtml(node.module)
            for alias in node.names:
                if alias.name == "*":
                    if raw:
                        bindings.extend((node.lineno, name, name) for name in GUARDED)
                    continue
                local = alias.asname or alias.name
                if raw and alias.name in GUARDED:
                    bindings.append((node.lineno, local, alias.name))
                elif raw and alias.name in ("common", "components"):
                    module_aliases.add(local)
                else:
                    bindings.append((node.lineno, local, None))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_fasthtml(alias.name):
                    module_aliases.add(alias.asname or alias.name)
    bindings.sort(key=lambda binding: binding[0])
    return bindings, module_aliases


def _raw_name_at(bindings: list[tuple[int, str, str | None]], name: str, line: int) -> str | None:
    """The guarded fasthtml name ``name`` holds at ``line`` (the last import before it)."""
    matching = [binding for binding in bindings if binding[1] == name]
    before = [binding for binding in matching if binding[0] <= line]
    chosen = before[-1] if before else (matching[-1] if matching else None)
    return chosen[2] if chosen else None


def _input_type(call: ast.Call) -> str | None:
    """The literal ``type=`` of a call, ``""`` when absent, None when unreadable."""
    has_spread = False
    for keyword in call.keywords:
        if keyword.arg == "type":
            value = keyword.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            return None
        if keyword.arg is None:
            has_spread = True
    return None if has_spread else ""


def raw_field_calls(source: str) -> list[str]:
    """``line: what`` for every raw fasthtml text-field ``Input`` / ``Select`` call in ``source``."""
    tree = ast.parse(source)
    bindings, module_aliases = _bindings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        raw: str | None = None
        if isinstance(func, ast.Name):
            raw = _raw_name_at(bindings, func.id, node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in GUARDED
            and isinstance(func.value, ast.Name)
            and func.value.id in module_aliases
        ):
            raw = func.attr
        if raw is None:
            continue
        if raw == "Select":
            found.append(f"{node.lineno}: raw Select")
            continue
        input_type = _input_type(node)
        if input_type is None:
            found.append(f"{node.lineno}: raw Input, type unreadable (spread or non-literal)")
        elif input_type not in EXEMPT_INPUT_TYPES:
            found.append(f"{node.lineno}: raw Input type={input_type or 'text (default)'}")
    return sorted(found, key=lambda entry: int(entry.split(":", 1)[0]))


def _scanned_files() -> list[Path]:
    return [
        path
        for tree in SCANNED_TREES
        for path in sorted((APP_ROOT / tree).rglob("*.py"))
        if EXEMPT_TREE not in path.parents
    ]


def test_scan_covers_the_ui_and_inbound_trees() -> None:
    files = _scanned_files()
    assert len(files) > 100
    assert any(path.parent.name == "inbound" for path in files)
    assert not any(EXEMPT_TREE in path.parents for path in files)


def test_no_raw_text_field_or_select_outside_the_components() -> None:
    offenders = [
        f"{path.relative_to(APP_ROOT)}:{entry}"
        for path in _scanned_files()
        for entry in raw_field_calls(path.read_text())
    ]
    assert not offenders, (
        "Use Input / Select from ui.components (compact=True for dense chat chrome):\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('from fasthtml.common import Input\nInput(type="text")', ["2: raw Input type=text"]),
        (
            "from fasthtml.common import Input\nInput(name='q')",
            ["2: raw Input type=text (default)"],
        ),
        ('from fasthtml.common import Input\nInput(type="search")', ["2: raw Input type=search"]),
        ("from fasthtml.common import Select\nSelect()", ["2: raw Select"]),
        (
            "from fasthtml.common import Input\nInput(**attrs)",
            ["2: raw Input, type unreadable (spread or non-literal)"],
        ),
        (
            "from fasthtml.common import Input\nInput(type=kind)",
            ["2: raw Input, type unreadable (spread or non-literal)"],
        ),
        ("from fasthtml.common import Input as I\nI(type='date')", ["2: raw Input type=date"]),
        ("from fasthtml.common import *\nSelect()", ["2: raw Select"]),
        ("import fasthtml.common as fh\nfh.Input(type='number')", ["2: raw Input type=number"]),
        ("from fasthtml import common as c\nc.Select()", ["2: raw Select"]),
        # Exempt types, and a type literal beside a spread, are readable and allowed.
        ('from fasthtml.common import Input\nInput(type="checkbox")', []),
        ('from fasthtml.common import Input\nInput(type="hidden", **attrs)', []),
        ('from fasthtml.common import Input\nInput(type="radio")', []),
        ('from fasthtml.common import Input\nInput(type="file")', []),
        # The components, and a raw import shadowed by them, are not raw.
        ("from ui.components import Input, Select\nInput()\nSelect()", []),
        ("from fasthtml.common import *\nfrom ui.components import Input\nInput()", []),
        ("from fasthtml.common import Textarea\nTextarea()", []),
    ],
)
def test_the_scanner_reads_each_spelling(source: str, expected: list[str]) -> None:
    assert raw_field_calls(source) == expected
