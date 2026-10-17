"""Every visible text field and select in the UI is ``Input`` / ``Select`` from ``ui.components``.

The components carry the field heights (44px on phones, 40px from ``md``; the
``compact`` size for dense chat chrome), the shared focus ring and the theme
tokens. A raw ``fasthtml`` ``Input`` or ``Select`` carries none of it unless its
caller re-types every class by hand, so the guard fails on one anywhere in
``ui/`` or ``adapters/inbound/`` outside ``ui/components/`` — imported by name
(aliased or not), by ``*``, or called through the module (``fh.Input``).

A name is resolved through Python's lexical scopes, and within the scope that
binds it, it is raw when ANY binding there is raw — an import, or an alias such
as ``Field = fh.Input`` — whatever the order or the condition (``if
TYPE_CHECKING``, ``try`` / ``except``) around it. A ``*`` import counts only where
the scope binds the name nowhere else. A file that wants both spellings aliases
the raw one (``from fasthtml.common import Input as FTInput``). Dynamic access
(``getattr``, ``importlib``) is beyond an AST walk.

A raw ``Input`` of type ``hidden``, ``checkbox``, ``radio`` or ``file`` is exempt
by rule — none of them is a text field. The type must be readable from the call:
an ``Input(**attrs)`` whose type lives in the dict is reported, and the fix is a
literal ``type=`` at the call or the component, never an allowlist entry.

Raw ``Textarea`` is out of scope (unruled); field markup built inside HTML or JS
strings is invisible to an AST walk.
"""

import ast
from dataclasses import dataclass
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


def _import_kinds(node: ast.Import | ast.ImportFrom) -> list[tuple[str, str | None, bool]]:
    """``(local name, kind, from a *)`` for each name an import binds.

    The kind is the guarded fasthtml name (``Input`` / ``Select``), ``MODULE`` for
    a fasthtml module (``import fasthtml.common`` binds its root, ``fasthtml``), or
    None for a name from anywhere else. A ``*`` from fasthtml binds both guarded
    names.
    """
    if isinstance(node, ast.Import):
        return [
            (
                alias.asname or alias.name.split(".")[0],
                MODULE if _is_fasthtml(alias.name) else None,
                False,
            )
            for alias in node.names
        ]
    raw = _is_fasthtml(node.module)
    kinds: list[tuple[str, str | None, bool]] = []
    for alias in node.names:
        if alias.name == "*":
            if raw:
                kinds.extend((name, name, True) for name in GUARDED)
            continue
        local = alias.asname or alias.name
        if raw and alias.name in GUARDED:
            kinds.append((local, alias.name, False))
        elif raw and alias.name in ("common", "components"):
            kinds.append((local, MODULE, False))
        else:
            kinds.append((local, None, False))
    return kinds


@dataclass(frozen=True)
class _Binding:
    """One name bound in one scope: by an import (``kind``) or an alias (``value``)."""

    name: str
    kind: str | None = None
    star: bool = False
    value: ast.expr | None = None
    chain: tuple[ast.AST, ...] = ()


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
        self.bindings: dict[int, list[_Binding]] = {}
        self.calls: list[tuple[ast.Call, tuple[ast.AST, ...]]] = []
        self._outside: dict[int, set[str]] = {}
        self._visit_all(tree.body, (tree,))

    def _visit_all(self, nodes: list[ast.AST], chain: tuple[ast.AST, ...]) -> None:
        for node in nodes:
            self._visit(node, chain)

    def _visit(self, node: ast.AST, chain: tuple[ast.AST, ...]) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for local, kind, star in _import_kinds(node):
                self._bind(_Binding(local, kind, star), chain)
            return
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self._bind_target(target, node.value, chain)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            self._bind_target(node.target, node.value, chain)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            elements: list[ast.expr | None] = (
                list(node.iter.elts)
                if isinstance(node.iter, (ast.Tuple, ast.List, ast.Set))
                else []
            )
            for element in elements or [None]:
                self._bind_target(node.target, element, chain)
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

    def _bind_target(
        self, target: ast.expr, value: ast.expr | None, chain: tuple[ast.AST, ...]
    ) -> None:
        """Bind every name in an assignment target, pairing unpacked names with their values.

        ``Input, other = fh.Input, x`` binds ``Input`` to ``fh.Input``; an unpacking
        whose values cannot be paired binds its names to nothing raw.
        """
        if isinstance(target, ast.Name):
            self._bind(_Binding(target.id, value=value, chain=chain), chain)
        elif isinstance(target, (ast.Tuple, ast.List)):
            values: list[ast.expr | None] = [None] * len(target.elts)
            if (
                isinstance(value, (ast.Tuple, ast.List))
                and len(value.elts) == len(target.elts)
                and not any(isinstance(e, ast.Starred) for e in (*value.elts, *target.elts))
            ):
                values = list(value.elts)
            for element, element_value in zip(target.elts, values, strict=True):
                self._bind_target(element, element_value, chain)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value, None, chain)

    def _bind(self, binding: _Binding, chain: tuple[ast.AST, ...]) -> None:
        """Record a binding in the scope that owns its name."""
        index = len(chain) - 1
        if binding.name in self._outside.get(id(chain[index]), set()):
            index = 0  # global, or nonlocal resolved conservatively to the module
        self.bindings.setdefault(id(chain[index]), []).append(binding)

    def kind(self, name: str, chain: tuple[ast.AST, ...], depth: int = 0) -> str | None:
        """What ``name`` may hold in a scope chain: a guarded name, ``MODULE`` or None.

        The innermost scope binding the name decides; an enclosing class body is
        skipped, as Python skips it. Within that scope the name is raw when any of
        its bindings is raw; a ``*`` binding counts only when it is the only kind.
        """
        if depth > 8:  # an alias cycle (``Input = Input``)
            return None
        for level, scope in enumerate(reversed(chain)):
            if level and isinstance(scope, ast.ClassDef):
                continue
            hits = [b for b in self.bindings.get(id(scope), []) if b.name == name]
            if not hits:
                continue
            explicit = [b for b in hits if not b.star] or hits
            kinds = {self._binding_kind(b, depth) for b in explicit}
            guarded = sorted(kinds & GUARDED)
            if guarded:
                return guarded[0]
            return MODULE if MODULE in kinds else None
        return None

    def _binding_kind(self, binding: _Binding, depth: int) -> str | None:
        if binding.value is None:
            return binding.kind
        return self.expr_kind(binding.value, binding.chain, depth + 1)

    def expr_kind(self, expr: ast.expr, chain: tuple[ast.AST, ...], depth: int = 0) -> str | None:
        """What a name or attribute chain refers to: a guarded name, ``MODULE`` or None."""
        if isinstance(expr, ast.Name):
            return self.kind(expr.id, chain, depth)
        if isinstance(expr, ast.Attribute):
            if self.expr_kind(expr.value, chain, depth) != MODULE:
                return None
            if expr.attr in GUARDED:
                return expr.attr
            return MODULE if expr.attr in ("common", "components") else None
        return None


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
        kind = scan.expr_kind(node.func, chain)
        raw = kind if kind in GUARDED else None
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
        # Any raw binding in the resolving scope makes the name raw, whatever the
        # order or condition; an alias is a binding.
        (
            "from fasthtml.common import Input\nif TYPE_CHECKING:\n"
            "    from ui.components import Input\nInput()",
            ["4: raw Input type=text (default)"],
        ),
        (
            "try:\n    from ui.components import Input\nexcept ImportError:\n"
            "    from fasthtml.common import Input\nInput(name='q')",
            ["5: raw Input type=text (default)"],
        ),
        (
            "import fasthtml.common as fh\nField = fh.Input\nField(type='text')",
            ["3: raw Input type=text"],
        ),
        ("from fasthtml.common import Select\nPick: Any = Select\nPick()", ["3: raw Select"]),
        ("import fasthtml\nfh = fasthtml.common\nfh.Select()", ["3: raw Select"]),
        ("from ui.components import Select\nPick = Select\nPick()", []),
        (
            "import fasthtml.common as fh\nInput, other = fh.Input, value\nInput()",
            ["3: raw Input type=text (default)"],
        ),
        (
            "import fasthtml.common as fh\n[a, [b, Pick]] = [1, [2, fh.Select]]\nPick()",
            ["3: raw Select"],
        ),
        ("import fasthtml.common as fh\nfor Pick in (fh.Select,):\n    Pick()", ["3: raw Select"]),
        ("import fasthtml.common as fh\nif (Pick := fh.Select):\n    Pick()", ["3: raw Select"]),
        ("from ui.components import Input\nInput, other = make()\nInput()", []),
        (
            "from fasthtml.common import Input\nInput = Input\nInput()",
            ["3: raw Input type=text (default)"],
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
