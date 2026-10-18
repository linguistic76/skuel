"""No annotation in the first-party trees raises over the names it resolves.

Python 3.14 defers annotations (PEP 649), so ``def f() -> Div | None`` imports
cleanly and raises only when something reads it: ``inspect.signature(...,
eval_str=True)``, ``typing.get_type_hints``, ``annotationlib`` and every
framework that binds parameters from a signature. FastHTML's tag names
(``Div``, ``Span``, ``Button``, …) are ``functools.partial`` objects, not
types, so a union over one raises ``TypeError`` on that read. MyPy cannot see
it: ``fasthtml`` ships no type information, so to MyPy ``Div`` is ``Any``.

The sweep parses each module, evaluates every annotation that Python stores —
function parameters and returns at any depth, and variable annotations at
module or class level (a local variable's annotation is never evaluated) — in
the module's namespace, and fails on any that raises. A name the namespace
does not hold (a ``TYPE_CHECKING``-only import, a type parameter, a name local
to an enclosing function) stands as a placeholder that subscripts, takes
attributes and joins a union with anything that can itself join one: deferring
those names is what PEP 649 is for, and a reader of one asks for
``annotationlib.Format.FORWARDREF`` (``inspect.signature(...,
annotation_format=...)``), which answers it as a forward reference. So only a
name that resolves can make an evaluation fail. Over resolved names, ``Div |
None`` raises under ``Format.VALUE`` (what ``get_type_hints`` and ``eval_str``
use) and comes back from ``FORWARDREF`` as a ``ForwardRef`` that never resolves
to a type.

FastHTML elements are annotated ``FT``.
"""

import ast
import builtins
import importlib
import typing
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fasthtml.common import FT, Div

APP = Path(__file__).resolve().parents[2]
TREES = ("adapters", "core", "services_bootstrap", "ui")


class _Unresolved:
    """Stands for a name the module namespace does not hold."""

    def __getitem__(self, _item: object) -> _Unresolved:
        return self

    def __getattr__(self, _name: str) -> _Unresolved:
        return self

    def __or__(self, other: object) -> object:
        return self if _joins_a_union(other) else NotImplemented

    __ror__ = __or__


UNRESOLVED = _Unresolved()


def _joins_a_union(value: object) -> bool:
    if isinstance(value, _Unresolved):
        return True
    try:
        value | int  # type: ignore[operator]
    except TypeError:
        return False
    return True


class _ModuleNames(dict[str, object]):
    """Locals for ``eval``: the module's names, then builtins, then the placeholder."""

    def __init__(self, module_names: dict[str, object], type_params: TypeParams) -> None:
        super().__init__()
        self._module_names = module_names
        self._type_params = type_params

    def __missing__(self, name: str) -> object:
        if name in self._type_params:
            return self._type_params[name]
        if name in self._module_names:
            return self._module_names[name]
        return getattr(builtins, name, UNRESOLVED)


TypeParams = dict[str, object]


def _bind(type_params: list[ast.type_param], outer: TypeParams) -> TypeParams:
    """The PEP 695 parameters a definition declares, as real typing objects."""
    bound = dict(outer)
    for param in type_params:
        if isinstance(param, ast.ParamSpec):
            bound[param.name] = typing.ParamSpec(param.name)
        elif isinstance(param, ast.TypeVarTuple):
            bound[param.name] = typing.TypeVarTuple(param.name)
        elif isinstance(param, ast.TypeVar):
            bound[param.name] = typing.TypeVar(param.name)
    return bound


def _function_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.expr]:
    args = node.args
    for arg in [
        *args.posonlyargs,
        *args.args,
        *args.kwonlyargs,
        *(a for a in (args.vararg, args.kwarg) if a is not None),
    ]:
        if arg.annotation is not None:
            yield arg.annotation
    if node.returns is not None:
        yield node.returns


def _stored_annotations(
    body: list[ast.stmt], type_params: TypeParams, *, stores_variables: bool
) -> Iterator[tuple[ast.expr, TypeParams]]:
    """Every annotation Python keeps: on any function, and on module or class variables.

    ``stores_variables`` is false inside a function body, where a variable's
    annotation is never evaluated.
    """
    for node in body:
        if isinstance(node, ast.AnnAssign):
            if stores_variables:
                yield node.annotation, type_params
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = _bind(node.type_params, type_params)
            for annotation in _function_annotations(node):
                yield annotation, scope
            yield from _stored_annotations(node.body, scope, stores_variables=False)
        elif isinstance(node, ast.ClassDef):
            yield from _stored_annotations(
                node.body, _bind(node.type_params, type_params), stores_variables=True
            )
        else:
            for field in ("body", "orelse", "finalbody", "handlers", "cases"):
                for child in getattr(node, field, []):
                    inner = (
                        child.body
                        if isinstance(child, (ast.ExceptHandler, ast.match_case))
                        else [child]
                    )
                    yield from _stored_annotations(
                        inner, type_params, stores_variables=stores_variables
                    )


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _sources() -> list[Path]:
    return sorted(p for tree in TREES for p in (APP / tree).rglob("*.py"))


def _failures_in(source: str, module_names: dict[str, object], label: str) -> list[str]:
    """Each stored annotation in ``source`` that raises when evaluated over ``module_names``."""
    tree = ast.parse(source, filename=label)
    failures = []
    for annotation, type_params in _stored_annotations(tree.body, {}, stores_variables=True):
        names = _ModuleNames(module_names, type_params)
        try:
            eval(compile(ast.Expression(annotation), label, "eval"), {}, names)
        except Exception as error:  # intentional-broad: any raise is the finding
            failures.append(
                f"{label}:{annotation.lineno}: {ast.unparse(annotation)} — "
                f"{type(error).__name__}: {error}"
            )
    return failures


def _failures(path: Path) -> list[str]:
    source = path.read_text()
    if not any(
        isinstance(n, ast.arg | ast.AnnAssign | ast.FunctionDef | ast.AsyncFunctionDef)
        for n in ast.walk(ast.parse(source))
    ):
        return []
    module = importlib.import_module(_module_name(path))
    return _failures_in(source, vars(module), str(path.relative_to(APP)))


def test_no_stored_annotation_raises_over_resolved_names() -> None:
    failures = [failure for path in _sources() for failure in _failures(path)]
    assert not failures, "annotations that raise when read:\n" + "\n".join(failures)


# The sweep's own reach: what it evaluates, what it leaves deferred.

NAMES: dict[str, object] = {"Div": Div, "FT": FT, "Callable": Callable}


@pytest.mark.parametrize(
    "source",
    [
        "def f() -> Div | None: ...",
        "def f(x: Div | str) -> None: ...",
        "def f() -> Div | Deferred: ...",
        "async def f() -> None | Div: ...",
        "def outer():\n    def inner() -> Div | None: ...",
        "class C:\n    x: Div | None",
        "class C:\n    def m(self) -> Div | None: ...",
        "x: Div | None = None",
        "if True:\n    x: Div | None = None",
        "try:\n    pass\nexcept ValueError:\n    def f() -> Div | None: ...",
    ],
)
def test_a_union_over_a_tag_is_found(source: str) -> None:
    assert len(_failures_in(source, NAMES, "probe.py")) == 1


@pytest.mark.parametrize(
    "source",
    [
        "def f() -> FT | None: ...",
        "def f() -> Deferred | None: ...",
        "def f() -> FT | Deferred: ...",
        "def f() -> list[Deferred] | dict[str, Deferred.Inner]: ...",
        "def f[**P, R](fn: Callable[P, R]) -> Callable[P, R]: ...",
        "class Box[T]:\n    item: T | None",
        "def f() -> None:\n    local: Div | None = None",
        "def f() -> list[Div]: ...",
    ],
)
def test_what_evaluates_or_is_deferred_is_left_alone(source: str) -> None:
    assert _failures_in(source, NAMES, "probe.py") == []
