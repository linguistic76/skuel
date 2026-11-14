"""Askesis is handed typed services, and the hub refuses to build it without the FULL-tier ones.

``AskesisDeps`` names the class the composition root hands over for every field, so
``AskesisService.__init__`` checks each one against the slice its sub-service reads.
A sub-service that takes a handle as ``Any`` checks nothing there, so the constructors
it is passed to are pinned as well.

The LLM and embeddings services are ``None`` in the CORE tier. Askesis is built in
FULL only, and ``_create_intelligence_hub`` refuses to build it when either is
missing, so the factory takes both non-``None``.

Annotations are read from source: most of the names are ``TYPE_CHECKING``-only where
they are declared.
"""

import ast
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from core.services.askesis_service import AskesisService
from services_bootstrap._intelligence_hub import _create_intelligence_hub

APP = Path(__file__).resolve().parents[3]
ASKESIS = APP / "core" / "services" / "askesis"

# (module, class, constructor parameters that take a service handle)
CONSTRUCTORS = (
    (ASKESIS / "intent_classifier.py", "IntentClassifier", ("embeddings_service",)),
    (ASKESIS / "context_retriever.py", "ContextRetriever", ("ps_engagement_service",)),
)


def _class(path: Path, name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in {path.name}")


def _names_any(annotation: ast.expr | None) -> bool:
    return annotation is None or any(
        isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(annotation)
    )


def test_every_askesis_deps_field_names_a_type() -> None:
    deps = _class(APP / "core" / "services" / "askesis_service.py", "AskesisDeps")
    fields = [
        statement
        for statement in deps.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    ]
    assert len(fields) == 20, "the pin reads every field"
    weak = [
        statement.target.id
        for statement in fields
        if isinstance(statement.target, ast.Name) and _names_any(statement.annotation)
    ]
    assert weak == []


@pytest.mark.parametrize(
    ("module", "cls", "parameters"), CONSTRUCTORS, ids=[cls for _, cls, _ in CONSTRUCTORS]
)
def test_the_sub_service_takes_its_handle_under_a_type(
    module: Path, cls: str, parameters: tuple[str, ...]
) -> None:
    init = next(
        node
        for node in _class(module, cls).body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    declared = {argument.arg: argument for argument in init.args.args + init.args.kwonlyargs}
    weak = [name for name in parameters if _names_any(declared[name].annotation)]
    assert weak == []


# ---------------------------------------------------------------------------
# The hub's FULL-tier refusals
# ---------------------------------------------------------------------------


def _hub_arguments(
    *, llm_service: MagicMock | None, embeddings_service: MagicMock | None
) -> dict[str, Any]:  # boundary: keyword arguments of mixed mock types
    """Everything _create_intelligence_hub reads, as mocks, in the FULL tier."""
    learning_services = {
        "atomic_ku_service": MagicMock(),
        "ps": MagicMock(),
        "learning_paths": MagicMock(),
        "embeddings_service": embeddings_service,
    }
    activity_services = {
        domain: MagicMock()
        for domain in ("tasks", "goals", "habits", "events", "choices", "principles")
    }
    return {
        "services": MagicMock(),
        "activity_services": activity_services,
        "learning_services": learning_services,
        "graph_intelligence": MagicMock(),
        "llm_service": llm_service,
        "user_entry_backend": MagicMock(),
        "calendar_service": MagicMock(),
        "vector_search_service": MagicMock(),
        "zpd_backend": MagicMock(),
        "zpd_snapshot_backend": MagicMock(),
        "ps_backend": MagicMock(),
        "event_bus": MagicMock(),
        "tier": MagicMock(ai_enabled=True),
        "context_builder": MagicMock(),
        "user_service": MagicMock(),
        "askesis_core_service": MagicMock(),
    }


def test_the_hub_refuses_askesis_without_the_llm_service() -> None:
    arguments = _hub_arguments(llm_service=None, embeddings_service=MagicMock())
    with pytest.raises(RuntimeError, match="requires LLMService"):
        _create_intelligence_hub(**arguments)
    assert not isinstance(arguments["services"].askesis, AskesisService)


def test_the_hub_refuses_askesis_without_the_embeddings_service() -> None:
    arguments = _hub_arguments(llm_service=MagicMock(), embeddings_service=None)
    with pytest.raises(RuntimeError, match="requires EmbeddingsService"):
        _create_intelligence_hub(**arguments)
    assert not isinstance(arguments["services"].askesis, AskesisService)


def test_the_hub_builds_askesis_with_both() -> None:
    """The control: the same mocks with both services build Askesis."""
    arguments = _hub_arguments(llm_service=MagicMock(), embeddings_service=MagicMock())
    _create_intelligence_hub(**arguments)
    assert isinstance(arguments["services"].askesis, AskesisService)
