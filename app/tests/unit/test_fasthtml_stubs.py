"""The local FastHTML stubs (``typings/``) describe the installed FastHTML.

mypy and Pyright read ``typings/`` in place of FastHTML, which ships no types, so they
believe whatever the stubs say. A stub that drifts from the installed package is
believed silently: a tag FastHTML adds is ``Any`` (through the stub's ``__getattr__``),
and a tag it moves or reshapes keeps its old declaration. mypy cannot see that drift.
These pins can:

* **Every tag is declared, and nothing else is.** The tag functions a stub module
  declares are exactly the tags its runtime module builds (``fasthtml.components``: its
  ``ft_hx`` partials; ``fastcore.xml``: its ``ft`` partials), each declared
  ``(*c: Any, **kwargs: Any) -> FT``. ``fasthtml.common`` declares every one of them.
* **Each declaration is true of the runtime.** Every function a stub declares accepts
  what its declaration says it accepts (the same leading parameters, ``*`` and ``**``
  where declared, each keyword-only name), and every tag, called, returns an ``FT``.
* **``fasthtml.common`` re-exports each name from where it lives.** Each name the
  ``common`` stub imports from a module is, at runtime, that module's own object, so a
  tag FastHTML moves into ``xtend`` fails here instead of keeping a stale shape.
* **A stub class declares only what the runtime class has.** Every member the stubs
  declare on ``FT`` and ``NotStr`` exists on a real instance (read statically:
  ``FT.__getattr__`` answers any name).

Each pin's checker is exercised by controls that plant the defect it exists to find.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import fastcore.xml as fastcore_xml
import fasthtml.common as fasthtml_common
import fasthtml.components as fasthtml_components
import fasthtml.xtend as fasthtml_xtend
from fastcore.xml import FT, Safe, ft, to_xml
from fasthtml.common import Html, NotStr

STUBS = Path(__file__).resolve().parents[2] / "typings"

# A stub module's ``__getattr__`` keeps every undeclared name ``Any``; it is no claim
# about a runtime function.
_UNDECLARED = "__getattr__"


def _stub(relative: str) -> ast.Module:
    return ast.parse((STUBS / relative).read_text())


def _functions(module: ast.Module) -> dict[str, list[ast.FunctionDef]]:
    """Top-level function declarations by name (an overloaded name keeps every variant)."""
    found: dict[str, list[ast.FunctionDef]] = {}
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name != _UNDECLARED:
            found.setdefault(node.name, []).append(node)
    return found


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    return next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == name)


def _runtime_tags(module: ModuleType, builder: Any) -> set[str]:
    """The tags a FastHTML module builds: the names in its ``__all__`` that partial ``builder``."""
    return {
        name
        for name in module.__all__
        if isinstance(obj := getattr(module, name), functools.partial) and obj.func is builder
    }


def _is_tag_declaration(fn: ast.FunctionDef) -> bool:
    """``def X(*c: Any, **kwargs: Any) -> FT`` — any child, any attribute, one FT."""
    a = fn.args
    return (
        not a.posonlyargs
        and not a.args
        and not a.kwonlyargs
        and a.vararg is not None
        and a.kwarg is not None
        and ast.unparse(a.vararg.annotation or ast.Constant(None)) == "Any"
        and ast.unparse(a.kwarg.annotation or ast.Constant(None)) == "Any"
        and fn.returns is not None
        and ast.unparse(fn.returns) == "FT"
    )


def tag_set_defects(stub: ast.Module, runtime_tags: set[str]) -> list[str]:
    """Every runtime tag declared in the tag shape; no tag-shaped declaration that is not one."""
    functions = _functions(stub)
    defects = []
    for name in sorted(runtime_tags):
        declarations = functions.get(name)
        if declarations is None:
            defects.append(f"{name}: a tag at runtime, not declared")
        elif not all(_is_tag_declaration(fn) for fn in declarations):
            defects.append(f"{name}: declared, but not as (*c: Any, **kwargs: Any) -> FT")
    for name, declarations in sorted(functions.items()):
        if name not in runtime_tags and any(_is_tag_declaration(fn) for fn in declarations):
            defects.append(f"{name}: declared as a tag, not one at runtime")
    return defects


def signature_defects(declaration: ast.FunctionDef, runtime: Any) -> list[str]:
    """What the declaration says a call may pass, the runtime callable accepts."""
    name = declaration.name
    try:
        parameters = list(inspect.signature(runtime).parameters.values())
    except TypeError, ValueError:
        return [f"{name}: the runtime object has no readable signature"]
    a = declaration.args
    if a.args and a.args[0].arg in ("self", "cls"):
        a = ast.arguments(
            posonlyargs=a.posonlyargs,
            args=a.args[1:],
            vararg=a.vararg,
            kwonlyargs=a.kwonlyargs,
            kw_defaults=a.kw_defaults,
            kwarg=a.kwarg,
            defaults=a.defaults,
        )
    kinds = {p.kind for p in parameters}
    positional = [
        p.name for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    keywords = {p.name for p in parameters if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
    defects = []
    declared_positional = [arg.arg for arg in [*a.posonlyargs, *a.args]]
    if positional[: len(declared_positional)] != declared_positional:
        defects.append(
            f"{name}: declares positional {declared_positional}, runtime takes {positional}"
        )
    if a.vararg is not None and inspect.Parameter.VAR_POSITIONAL not in kinds:
        defects.append(f"{name}: declares *{a.vararg.arg}, the runtime takes no *args")
    if a.kwarg is not None and inspect.Parameter.VAR_KEYWORD not in kinds:
        defects.append(f"{name}: declares **{a.kwarg.arg}, the runtime takes no **kwargs")
    if inspect.Parameter.VAR_KEYWORD not in kinds:
        defects.extend(
            f"{name}: declares keyword {arg.arg!r}, the runtime takes none"
            for arg in a.kwonlyargs
            if arg.arg not in keywords
        )
    return defects


def declaration_defects(stub: ast.Module, runtime_module: Any) -> list[str]:
    """Every function the stub declares exists in the runtime module and accepts its calls."""
    defects = []
    for name, declarations in sorted(_functions(stub).items()):
        runtime = getattr(runtime_module, name, None)
        if runtime is None:
            defects.append(f"{name}: declared, absent at runtime")
            continue
        for declaration in declarations:
            defects.extend(signature_defects(declaration, runtime))
    return defects


def tag_result_defects(runtime_module: Any, names: set[str]) -> list[str]:
    """Each named tag, called with nothing, returns an FT."""
    return [
        f"{name}: returns {type(result).__name__}, not FT"
        for name in sorted(names)
        if not isinstance(result := getattr(runtime_module, name)(), FT)
    ]


def _imported_names(stub: ast.Module) -> dict[str, str]:
    """``{public name: source module}`` for each ``from M import N as N`` in a stub."""
    names = {}
    for node in stub.body:
        if isinstance(node, ast.ImportFrom) and node.module != "typing":
            assert node.level == 0 and node.module is not None, "the stubs import absolutely"
            for alias in node.names:
                names[alias.asname or alias.name] = node.module
    return names


def _exported(stub: ast.Module) -> list[str]:
    """The stub's ``__all__``: a plain import in a stub re-exports only a name listed there."""
    for node in stub.body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__":
            return list(ast.literal_eval(node.value))
    return []


def common_origin_defects(stub: ast.Module, runtime_common: Any, required: set[str]) -> list[str]:
    """Each re-exported name is its source module's object, and every required name is declared.

    A name imported but missing from ``__all__`` is not re-exported: mypy refuses an import
    of it, and Pyright reads it as ``Any`` through the stub's ``__getattr__``, silently.
    """
    imported = _imported_names(stub)
    exported = _exported(stub)
    defects = [
        f"{name}: the stub takes it from {source}, runtime fasthtml.common has another object"
        for name, source in sorted(imported.items())
        if getattr(runtime_common, name, None) is not getattr(importlib.import_module(source), name)
    ]
    defects.extend(
        f"{name}: imported, not in __all__" for name in sorted(imported.keys() - set(exported))
    )
    defects.extend(
        f"{name}: in __all__, neither imported nor declared"
        for name in sorted(set(exported) - imported.keys() - _functions(stub).keys())
    )
    declared = (imported.keys() & set(exported)) | _functions(stub).keys()
    defects.extend(
        f"{name}: on fasthtml.common at runtime, Any through the stub"
        for name in sorted(required - declared)
    )
    return defects


def class_member_defects(stub_class: ast.ClassDef, instance: object) -> list[str]:
    """Every member the stub class declares is on the real instance, read without ``__getattr__``."""
    declared = [
        node.name if isinstance(node, ast.FunctionDef) else ast.unparse(node.target)
        for node in stub_class.body
        if isinstance(node, ast.FunctionDef | ast.AnnAssign)
    ]
    missing = []
    for name in declared:
        try:
            inspect.getattr_static(instance, name)
        except AttributeError:
            missing.append(f"{stub_class.name}.{name}: declared, absent at runtime")
    return missing


# --- the shared reads --------------------------------------------------------------

COMPONENT_TAGS = _runtime_tags(fasthtml_components, fasthtml_components.ft_hx)
FASTCORE_TAGS = _runtime_tags(fastcore_xml, ft)
XTEND_REDEFINED = {
    name
    for name in COMPONENT_TAGS
    if getattr(fasthtml_xtend, name) is not getattr(fasthtml_components, name)
}


# --- pins -------------------------------------------------------------------------


def test_the_reads_find_tags() -> None:
    """A guard on the reads themselves: an empty tag set would pass every pin below."""
    assert {"Div", "Span", "A", "Input", "HxPartial"} <= COMPONENT_TAGS
    assert {"Div", "Math", "Svg"} <= FASTCORE_TAGS
    assert XTEND_REDEFINED


def test_every_component_tag_is_declared() -> None:
    assert tag_set_defects(_stub("fasthtml/components.pyi"), COMPONENT_TAGS) == []


def test_every_fastcore_tag_is_declared() -> None:
    assert tag_set_defects(_stub("fastcore/xml.pyi"), FASTCORE_TAGS) == []


def test_xtend_declares_exactly_its_redefinitions() -> None:
    declared = set(_functions(_stub("fasthtml/xtend.pyi")))
    assert declared == XTEND_REDEFINED


def test_every_declaration_is_true_of_the_runtime() -> None:
    pairs = [
        ("fastcore/xml.pyi", fastcore_xml),
        ("fasthtml/components.pyi", fasthtml_components),
        ("fasthtml/xtend.pyi", fasthtml_xtend),
    ]
    defects = [d for stub, module in pairs for d in declaration_defects(_stub(stub), module)]
    assert defects == []


def test_every_tag_returns_ft() -> None:
    defects = tag_result_defects(fasthtml_components, COMPONENT_TAGS)
    defects += tag_result_defects(fastcore_xml, FASTCORE_TAGS)
    defects += tag_result_defects(fasthtml_xtend, XTEND_REDEFINED)
    assert defects == []


def test_the_declared_results_hold() -> None:
    """The non-tag declarations whose results the stubs state."""
    page = Html()
    assert isinstance(page, tuple) and len(page) == 2 and all(isinstance(o, FT) for o in page)
    assert isinstance(Html(doctype=False), FT)
    assert type(to_xml(ft("div"))) is Safe
    assert isinstance(fasthtml_components.ft_hx("div"), FT)
    assert isinstance(fasthtml_components.ft_html("div"), FT)
    assert isinstance(ft("div")("child"), FT)
    assert isinstance(ft("div") + "x", str) and isinstance("x" + ft("div"), str)
    assert not isinstance(NotStr("x"), str)


def test_common_reexports_each_name_from_where_it_lives() -> None:
    required = COMPONENT_TAGS | FASTCORE_TAGS | {"FT", "to_xml", "NotStr", "Html"}
    defects = common_origin_defects(_stub("fasthtml/common.pyi"), fasthtml_common, required)
    assert defects == []


def test_stub_classes_declare_only_runtime_members() -> None:
    defects = class_member_defects(_class(_stub("fastcore/xml.pyi"), "FT"), ft("div"))
    defects += class_member_defects(_class(_stub("fastcore/basics.pyi"), "NotStr"), NotStr("x"))
    assert defects == []


# --- controls: each checker finds the defect it exists to find ---------------------


def _edited(relative: str, old: str, new: str) -> ast.Module:
    text = (STUBS / relative).read_text()
    assert text.count(old) == 1, old
    return ast.parse(text.replace(old, new))


def test_control_a_missing_tag_is_found() -> None:
    stub = _edited(
        "fasthtml/components.pyi", "def HxPartial(*c: Any, **kwargs: Any) -> FT: ...\n", ""
    )
    assert tag_set_defects(stub, COMPONENT_TAGS) == ["HxPartial: a tag at runtime, not declared"]


def test_control_a_tag_that_is_not_one_is_found() -> None:
    stub = _edited(
        "fasthtml/components.pyi",
        "def Div(*c: Any, **kwargs: Any) -> FT: ...\n",
        "def Div(*c: Any, **kwargs: Any) -> FT: ...\ndef Bogus(*c: Any, **kwargs: Any) -> FT: ...\n",
    )
    assert tag_set_defects(stub, COMPONENT_TAGS) == ["Bogus: declared as a tag, not one at runtime"]


def test_control_a_tag_declared_with_another_result_is_found() -> None:
    stub = _edited(
        "fasthtml/components.pyi",
        "def Span(*c: Any, **kwargs: Any) -> FT: ...\n",
        "def Span(*c: Any, **kwargs: Any) -> str: ...\n",
    )
    assert tag_set_defects(stub, COMPONENT_TAGS) == [
        "Span: declared, but not as (*c: Any, **kwargs: Any) -> FT"
    ]


def test_control_a_runtime_without_star_args_or_kwargs_is_found() -> None:
    declaration = _functions(_stub("fasthtml/components.pyi"))["Div"][0]

    def no_children(**kwargs: object) -> FT:
        return ft("div", **kwargs)

    def no_attributes(*c: object) -> FT:
        return ft("div", *c)

    assert signature_defects(declaration, no_children) == [
        "Div: declares *c, the runtime takes no *args"
    ]
    assert signature_defects(declaration, no_attributes) == [
        "Div: declares **kwargs, the runtime takes no **kwargs"
    ]


def test_control_a_declared_parameter_the_runtime_lacks_is_found() -> None:
    stub = _edited(
        "fasthtml/xtend.pyi",
        'def Script(code: str = "", **kwargs: Any) -> FT: ...',
        'def Script(source: str = "", **kwargs: Any) -> FT: ...',
    )
    assert declaration_defects(stub, fasthtml_xtend) == [
        "Script: declares positional ['source'], runtime takes ['code']"
    ]


def test_control_a_tag_that_returns_no_ft_is_found() -> None:
    runtime = SimpleNamespace(Div=functools.partial(str, "div"))
    assert tag_result_defects(runtime, {"Div"}) == ["Div: returns str, not FT"]


def test_control_a_name_taken_from_the_wrong_module_is_found() -> None:
    stub = _stub("fasthtml/common.pyi")
    imports = {n.module: n for n in stub.body if isinstance(n, ast.ImportFrom)}
    xtend, components = imports["fasthtml.xtend"], imports["fasthtml.components"]
    moved = next(alias for alias in xtend.names if alias.name == "A")
    xtend.names.remove(moved)
    components.names.append(moved)
    assert common_origin_defects(stub, fasthtml_common, set()) == [
        "A: the stub takes it from fasthtml.components, runtime fasthtml.common has another object"
    ]


def test_control_an_unimported_common_name_is_found() -> None:
    stub = _edited("fasthtml/common.pyi", "    Div,\n", "")
    assert common_origin_defects(stub, fasthtml_common, {"Div"}) == [
        "Div: in __all__, neither imported nor declared",
        "Div: on fasthtml.common at runtime, Any through the stub",
    ]


def test_control_an_unexported_common_name_is_found() -> None:
    stub = _edited("fasthtml/common.pyi", '    "Div",\n', "")
    assert common_origin_defects(stub, fasthtml_common, {"Div"}) == [
        "Div: imported, not in __all__",
        "Div: on fasthtml.common at runtime, Any through the stub",
    ]


def test_control_a_class_member_the_runtime_lacks_is_found() -> None:
    stub = _edited(
        "fastcore/xml.pyi",
        "    def changed(self) -> Self: ...\n",
        "    def changed(self) -> Self: ...\n    def rerender(self) -> Self: ...\n",
    )
    assert class_member_defects(_class(stub, "FT"), ft("div")) == [
        "FT.rerender: declared, absent at runtime"
    ]
