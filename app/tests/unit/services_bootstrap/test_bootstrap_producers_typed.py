"""The composition root's service producers return typed sets, and take typed arguments.

Five functions build the services that are not Activity facades — the curriculum
set, the core set, the two orchestration services, the two advanced services and
the template set. Each returns a ``TypedDict`` whose keys are exactly the keys it
builds, so a read by key is checked as the class declared under it; each takes
every argument under a type, as do the wiring functions the sets are handed to.

Annotations are read from source: most of the names are ``TYPE_CHECKING``-only
where they are declared.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[3]
BOOTSTRAP = APP / "services_bootstrap"

# (module holding the producer, producer, module holding the set, set)
PRODUCERS = (
    (
        BOOTSTRAP / "_learning_services.py",
        "_create_learning_services",
        APP / "core" / "services" / "learning_services.py",
        "LearningServices",
    ),
    (
        BOOTSTRAP / "_core_services.py",
        "_create_core_services",
        BOOTSTRAP / "_core_services.py",
        "CoreServices",
    ),
    (
        BOOTSTRAP / "_core_services.py",
        "_create_orchestration_services",
        BOOTSTRAP / "_core_services.py",
        "OrchestrationServices",
    ),
    (
        BOOTSTRAP / "_core_services.py",
        "_create_advanced_services",
        BOOTSTRAP / "_core_services.py",
        "AdvancedServices",
    ),
    (
        BOOTSTRAP / "_template_services.py",
        "_create_template_services",
        BOOTSTRAP / "_template_services.py",
        "TemplateServices",
    ),
)
PRODUCER_IDS = [producer for _, producer, _, _ in PRODUCERS]

# The functions the curriculum set is handed to.
WIRING = (
    (BOOTSTRAP / "_ai_wiring.py", "_wire_ai_services"),
    (BOOTSTRAP / "_event_wiring.py", "_wire_event_subscribers"),
    (BOOTSTRAP / "_intelligence_hub.py", "_filtered_context_providers"),
    (BOOTSTRAP / "_intelligence_hub.py", "_create_intelligence_hub"),
    (APP / "core" / "services" / "askesis_factory.py", "create_askesis_service"),
)


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in {path.name}")


def _declared_keys(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            }
    raise AssertionError(f"{name} is not defined in {path.name}")


def _built_keys(function: ast.FunctionDef) -> set[str]:
    """The keys of the one dict literal the producer builds its result from."""
    literals = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Return | ast.AnnAssign) and isinstance(node.value, ast.Dict)
    ]
    assert len(literals) == 1, f"{function.name} builds its result from one dict literal"
    keys = set()
    for key in literals[0].keys:
        assert isinstance(key, ast.Constant), "every key is a literal"
        assert isinstance(key.value, str), "every key is a string"
        keys.add(key.value)
    return keys


def weak_parameters(function: ast.FunctionDef) -> list[str]:
    """Each parameter with no annotation, or one that names ``Any``."""
    parameters = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    return [
        parameter.arg
        for parameter in parameters
        if parameter.annotation is None
        or any(
            isinstance(node, ast.Name) and node.id == "Any"
            for node in ast.walk(parameter.annotation)
        )
    ]


@pytest.mark.parametrize(
    ("module", "producer", "set_module", "typed_set"), PRODUCERS, ids=PRODUCER_IDS
)
def test_the_producer_returns_its_typed_set(
    module: Path, producer: str, set_module: Path, typed_set: str
) -> None:
    returns = _function(module, producer).returns
    assert returns is not None
    assert ast.unparse(returns) == typed_set


@pytest.mark.parametrize(
    ("module", "producer", "set_module", "typed_set"), PRODUCERS, ids=PRODUCER_IDS
)
def test_the_set_declares_exactly_the_keys_built(
    module: Path, producer: str, set_module: Path, typed_set: str
) -> None:
    built = _built_keys(_function(module, producer))
    assert built
    assert _declared_keys(set_module, typed_set) == built


@pytest.mark.parametrize(
    ("module", "producer", "set_module", "typed_set"), PRODUCERS, ids=PRODUCER_IDS
)
def test_every_producer_parameter_names_a_type_that_is_not_any(
    module: Path, producer: str, set_module: Path, typed_set: str
) -> None:
    function = _function(module, producer)
    assert function.args.args + function.args.kwonlyargs, "the producer takes its dependencies"
    assert weak_parameters(function) == []


@pytest.mark.parametrize(("module", "function"), WIRING, ids=[name for _, name in WIRING])
def test_every_wiring_parameter_names_a_type_that_is_not_any(module: Path, function: str) -> None:
    assert weak_parameters(_function(module, function)) == []


def test_an_untyped_and_an_any_parameter_are_both_named() -> None:
    """The control: the sweep refuses a bare parameter and one that names ``Any``."""
    function = ast.parse("def f(a: int, b, c: Any | None, *, d: dict[str, Any]): ...").body[0]
    assert isinstance(function, ast.FunctionDef)
    assert weak_parameters(function) == ["b", "c", "d"]


def test_every_function_handed_the_curriculum_set_names_its_type() -> None:
    weak: list[str] = []
    seen = 0
    for tree_name in ("core", "services_bootstrap"):
        for path in sorted((APP / tree_name).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for parameter in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    if parameter.arg != "learning_services":
                        continue
                    seen += 1
                    annotation = (
                        ast.unparse(parameter.annotation) if parameter.annotation else "<none>"
                    )
                    if annotation != "LearningServices":
                        weak.append(f"{path.relative_to(APP)}:{node.lineno} {node.name}")
    assert seen == 5
    assert weak == []
