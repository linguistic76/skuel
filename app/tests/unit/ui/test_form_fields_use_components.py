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


MODULE = "module"
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _import_kinds(node: ast.Import | ast.ImportFrom) -> list[tuple[str, str | None]]:
    """``(local name, kind)`` for each name an import binds.

    The kind is the guarded fasthtml name (``Input`` / ``Select``), ``MODULE`` for
    a fasthtml module (``import fasthtml.common`` binds its root, ``fasthtml``), or
    None for a name from anywhere else — which shadows a raw one. A ``*`` from
    fasthtml binds both guarded names.
    """
    if isinstance(node, ast.Import):
        return [
            (alias.asname or alias.name.split(".")[0], MODULE if _is_fasthtml(alias.name) else None)
            for alias in node.names
        ]
    raw = _is_fasthtml(node.module)
    kinds: list[tuple[str, str | None]] = []
    for alias in node.names:
        if alias.name == "*":
            if raw:
                kinds.extend((name, name) for name in GUARDED)
            continue
        local = alias.asname or alias.name
        if raw and alias.name in GUARDED:
            kinds.append((local, alias.name))
        elif raw and alias.name in ("common", "components"):
            kinds.append((local, MODULE))
        else:
            kinds.append((local, None))
    return kinds


def _declared_outside(function: ast.AST) -> set[str]:
    """Names a function's own body declares ``global`` or ``nonlocal``."""
    names: set[str] = set()
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif not isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))
    return names


class _ScopeScan:
    """Each scope's imports, and each call with the chain of scopes around it.

    A scope's body runs in the new scope; everything a definition evaluates where
    it stands — decorators, defaults, annotations, class bases and keywords, a
    comprehension's first iterable — runs in the enclosing one. An import of a
    name the function declares ``global`` / ``nonlocal`` binds the outer scope.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.imports: dict[int, list[tuple[int, str, str | None]]] = {}
        self.calls: list[tuple[ast.Call, tuple[ast.AST, ...]]] = []
        self._outside: dict[int, set[str]] = {}
        self._visit_all(tree.body, (tree,))

    def _visit_all(self, nodes: list[ast.AST], chain: tuple[ast.AST, ...]) -> None:
        for node in nodes:
            self._visit(node, chain)

    def _visit(self, node: ast.AST, chain: tuple[ast.AST, ...]) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for local, kind in _import_kinds(node):
                self._bind_import(local, (node.lineno, local, kind), chain)
            return
        if isinstance(node, ast.Call):
            self.calls.append((node, chain))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_all([*node.decorator_list, node.args, *node.type_params], chain)
            if node.returns:
                self._visit(node.returns, chain)
            self._outside[id(node)] = _declared_outside(node)
            self._visit_all(node.body, (*chain, node))
        elif isinstance(node, ast.Lambda):
            self._visit(node.args, chain)
            self._visit(node.body, (*chain, node))
        elif isinstance(node, ast.ClassDef):
            self._visit_all(
                [*node.decorator_list, *node.bases, *node.keywords, *node.type_params], chain
            )
            self._visit_all(node.body, (*chain, node))
        elif isinstance(node, _COMPREHENSIONS):
            first, *rest = node.generators
            self._visit(first.iter, chain)
            inner = (*chain, node)
            parts = [first.target, *first.ifs, *rest]
            parts += [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
            self._visit_all(parts, inner)
        else:
            self._visit_all(list(ast.iter_child_nodes(node)), chain)

    def _bind_import(
        self, local: str, binding: tuple[int, str, str | None], chain: tuple[ast.AST, ...]
    ) -> None:
        """Record an import in the scope that owns the name it binds."""
        index = len(chain) - 1
        if local in self._outside.get(id(chain[index]), set()):
            index = 0  # global, or nonlocal resolved conservatively to the module
        self.imports.setdefault(id(chain[index]), []).append(binding)

    def kind(self, name: str, line: int, chain: tuple[ast.AST, ...]) -> str | None:
        """What ``name`` holds at ``line``, resolved through the lexical scopes.

        The innermost scope binding the name wins; an enclosing class body is
        skipped, as Python skips it. In the call's own scope the last import at or
        before the line counts; an enclosing scope's binding is its last one, the
        value a call made later at run time sees.
        """
        for depth, scope in enumerate(reversed(chain)):
            if depth and isinstance(scope, ast.ClassDef):
                continue
            hits = [b for b in self.imports.get(id(scope), []) if b[1] == name]
            if not hits:
                continue
            if depth == 0:
                before = [b for b in hits if b[0] <= line]
                return (before or hits)[-1][2]
            return hits[-1][2]
        return None


def _root_name(expr: ast.expr) -> str | None:
    """The name at the root of an attribute chain (``fasthtml`` in ``fasthtml.common``)."""
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


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
    scan = _ScopeScan(ast.parse(source))
    found: list[str] = []
    for node, chain in scan.calls:
        func = node.func
        raw: str | None = None
        if isinstance(func, ast.Name):
            kind = scan.kind(func.id, node.lineno, chain)
            raw = kind if kind in GUARDED else None
        elif isinstance(func, ast.Attribute) and func.attr in GUARDED:
            root = _root_name(func.value)
            if root and scan.kind(root, node.lineno, chain) == MODULE:
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
        ("import fasthtml.common\nfasthtml.common.Input(type='text')", ["2: raw Input type=text"]),
        ("import fasthtml\nfasthtml.components.Select()", ["2: raw Select"]),
        ("import fasthtml.common\nother.common.Select()", []),
        # Bindings resolve through lexical scopes, not file-wide line order.
        (
            "from fasthtml.common import Input\ndef f():\n    from ui.components import Input\n"
            "    Input()\nInput(type='text')",
            ["5: raw Input type=text"],
        ),
        (
            "from ui.components import Input\ndef f():\n    from fasthtml.common import Input\n"
            "    Input(type='date')\ndef g():\n    Input()",
            ["4: raw Input type=date"],
        ),
        (
            "def f():\n    Input()\nfrom fasthtml.common import Input",
            ["2: raw Input type=text (default)"],
        ),
        # Definition-time parts run in the enclosing scope.
        (
            "from fasthtml.common import Input\ndef f(x=Input()):\n    from ui.components import Input",
            ["2: raw Input type=text (default)"],
        ),
        (
            "from fasthtml.common import Select\n@deco(Select())\ndef f():\n"
            "    from ui.components import Select",
            ["2: raw Select"],
        ),
        (
            "from fasthtml.common import Select\ndef f(x: Select() = 1) -> Select():\n"
            "    from ui.components import Select",
            ["2: raw Select", "2: raw Select"],
        ),
        (
            "from fasthtml.common import Select\nclass C(Base, meta=Select()):\n"
            "    from ui.components import Select",
            ["2: raw Select"],
        ),
        ("from fasthtml.common import Select\nf = lambda x=Select(): x", ["2: raw Select"]),
        # A comprehension in a class body skips the class's names but its first
        # iterable does not.
        (
            "from fasthtml.common import Input\nclass C:\n    from ui.components import Input\n"
            "    xs = [Input() for _ in range(2)]\n    ys = [y for y in Input()]",
            ["4: raw Input type=text (default)"],
        ),
        # A global import binds the module, for every scope that reads it.
        (
            "from ui.components import Input\ndef f():\n    global Input\n"
            "    from fasthtml.common import Input\ndef g():\n    Input(type='text')",
            ["6: raw Input type=text"],
        ),
        (
            "import fasthtml.common as fh\nclass C:\n    from ui import components as fh\n    def m(self):\n"
            "        fh.Select()",
            ["5: raw Select"],
        ),
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
