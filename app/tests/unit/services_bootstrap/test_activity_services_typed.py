"""The six Activity facades leave the composition root under their own types.

``_create_activity_services`` takes each backend as its port and returns
``ActivityServices`` — one key per Activity Domain, each naming the facade built
under it — and a function that takes the set as ``activity_services`` names that
type, so a read of ``activity_services["goals"]`` is checked as a ``GoalsService``.
One function takes a read-only mapping instead and checks each value itself.

Annotations are read from source: the facade and port names are
``TYPE_CHECKING``-only where they are declared.
"""

import ast
from pathlib import Path

from core.services.activity_services import ActivityServices

APP = Path(__file__).resolve().parents[3]
FACTORY = APP / "services_bootstrap" / "_activity_services.py"
TYPED_SET = APP / "core" / "services" / "activity_services.py"
TREES = ("core", "services_bootstrap")
SET_PARAMETERS = frozenset({"activity_services", "_activity_services"})
# ``_filtered_context_providers`` checks each value against a protocol itself and
# is handed plain dicts by its tests, so it takes the widest read-only mapping.
SET_ANNOTATIONS = frozenset({"ActivityServices", "Mapping[str, object]"})


def _factory() -> ast.FunctionDef:
    tree = ast.parse(FACTORY.read_text(), filename=str(FACTORY))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_create_activity_services":
            return node
    raise AssertionError("_create_activity_services is not defined in its module")


def _built_under_each_key(factory: ast.FunctionDef) -> dict[str, str]:
    """The class each key's value is constructed from, read off the returned dict."""
    for node in ast.walk(factory):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            built: dict[str, str] = {}
            for key, value in zip(node.value.keys, node.value.values, strict=True):
                assert isinstance(key, ast.Constant), "every key is a literal"
                assert isinstance(key.value, str), "every key is a string"
                assert isinstance(value, ast.Call), f"{key.value!r} is constructed in place"
                built[key.value] = ast.unparse(value.func)
            return built
    raise AssertionError("_create_activity_services does not return a dict literal")


def _declared_under_each_key() -> dict[str, str]:
    """The class each ``ActivityServices`` key is annotated with, read from source."""
    tree = ast.parse(TYPED_SET.read_text(), filename=str(TYPED_SET))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ActivityServices":
            return {
                statement.target.id: ast.unparse(statement.annotation)
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            }
    raise AssertionError("ActivityServices is not defined in its module")


def _annotation_names_any(annotation: ast.expr) -> bool:
    return any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(annotation))


def test_every_factory_parameter_names_a_type_that_is_not_any() -> None:
    factory = _factory()
    parameters = factory.args.posonlyargs + factory.args.args + factory.args.kwonlyargs
    assert parameters, "the factory takes its backends and shared dependencies"
    weak = [
        parameter.arg
        for parameter in parameters
        if parameter.annotation is None or _annotation_names_any(parameter.annotation)
    ]
    assert weak == []


def test_the_factory_returns_the_typed_set() -> None:
    returns = _factory().returns
    assert returns is not None
    assert ast.unparse(returns) == "ActivityServices"


def test_each_key_is_declared_as_the_facade_built_under_it() -> None:
    built = _built_under_each_key(_factory())
    declared = _declared_under_each_key()
    assert declared == built
    assert set(declared) == set(ActivityServices.__required_keys__)
    assert len(declared) == 6


def test_every_function_handed_the_set_names_its_type() -> None:
    weak: list[str] = []
    seen = 0
    for tree_name in TREES:
        for path in sorted((APP / tree_name).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for parameter in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    if parameter.arg not in SET_PARAMETERS:
                        continue
                    seen += 1
                    annotation = (
                        ast.unparse(parameter.annotation) if parameter.annotation else "<none>"
                    )
                    if annotation not in SET_ANNOTATIONS:
                        weak.append(f"{path.relative_to(APP)}:{node.lineno} {node.name}")
    assert seen, "the sweep found no function that takes the set"
    assert weak == []
