"""
Every facade the composition root registers as a filtered-context provider is one.

``_filtered_context_providers`` builds the ``filtered_providers`` dict the
intelligence factory hands to ``DailyPlanningMixin``. Both sets it reads are typed,
so the type checker holds each facade to ``FilteredContextProvider`` where it is
registered. The protocol takes everything after ``user_uid`` by keyword: a facade
may add filters of its own, and no caller can pass one facade's filter into
another's by position.
"""

import ast
from pathlib import Path

from core.ports.filtered_context_protocols import FilteredContextProvider
from core.services.activity_services import ActivityServices
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.ku_service import KuService
from core.services.learning_services import LearningServices
from core.services.lp.lp_intelligence_service import LpIntelligenceService
from core.services.lp_service import LpService
from core.services.principles_service import PrinciplesService
from core.services.ps_service import PsService
from core.services.tasks_service import TasksService
from core.services.user_progress_service import UserProgressService
from services_bootstrap._intelligence_hub import _filtered_context_providers

_CORE = Path(__file__).resolve().parents[2] / "core"
_SERVICES_ROOT = _CORE / "services"
_PROTOCOL = _CORE / "ports" / "filtered_context_protocols.py"


def _activity_services() -> ActivityServices:
    return {
        "tasks": object.__new__(TasksService),
        "goals": object.__new__(GoalsService),
        "habits": object.__new__(HabitsService),
        "events": object.__new__(EventsService),
        "choices": object.__new__(ChoicesService),
        "principles": object.__new__(PrinciplesService),
    }


def _learning_services() -> LearningServices:
    ps = object.__new__(PsService)
    learning_paths = object.__new__(LpService)
    return {
        "learning_intelligence": object.__new__(LpIntelligenceService),
        "atomic_ku_service": object.__new__(KuService),
        "user_progress": object.__new__(UserProgressService),
        "learning_paths": learning_paths,
        "ps": ps,
        "embeddings_service": None,
        "vector_search_service": None,
    }


def _signatures() -> dict[str, ast.AsyncFunctionDef]:
    """``get_filtered_context`` as the protocol and each implementing class declare it."""
    found: dict[str, ast.AsyncFunctionDef] = {}
    for path in [*_SERVICES_ROOT.rglob("*.py"), _PROTOCOL]:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if (
                    isinstance(member, ast.AsyncFunctionDef)
                    and member.name == "get_filtered_context"
                ):
                    found[node.name] = member
    return found


def positional_parameters(function: ast.AsyncFunctionDef) -> list[str]:
    return [parameter.arg for parameter in function.args.posonlyargs + function.args.args]


def _classes_defining_get_filtered_context() -> set[str]:
    """Every class under ``core/services`` that defines ``get_filtered_context``."""
    names: set[str] = set()
    for path in _SERVICES_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(member, ast.AsyncFunctionDef) and member.name == "get_filtered_context"
                for member in node.body
            ):
                names.add(node.name)
    return names


def test_every_registered_facade_is_a_provider() -> None:
    providers = _filtered_context_providers(_activity_services(), _learning_services())

    assert providers
    for domain, facade in providers.items():
        assert isinstance(facade, FilteredContextProvider), domain


def test_the_registry_is_exactly_the_facades_that_implement_it() -> None:
    providers = _filtered_context_providers(_activity_services(), _learning_services())

    registered = {type(facade).__name__ for facade in providers.values()}
    assert registered == _classes_defining_get_filtered_context()
    assert len(registered) == len(providers)


def test_the_ku_facade_is_not_a_provider() -> None:
    assert not isinstance(object.__new__(KuService), FilteredContextProvider)
    providers = _filtered_context_providers(_activity_services(), _learning_services())
    assert "ku" not in providers


def test_only_the_user_is_taken_by_position() -> None:
    signatures = _signatures()
    assert set(signatures) == _classes_defining_get_filtered_context() | {"FilteredContextProvider"}
    assert len(signatures) == 9
    for owner, function in signatures.items():
        assert positional_parameters(function) == ["self", "user_uid"], owner
        keywords = {parameter.arg for parameter in function.args.kwonlyargs}
        assert {"status_filter", "sort_by"} <= keywords, owner


def test_a_filter_taken_by_position_is_named() -> None:
    """The control: the read sees a parameter declared before the ``*``."""
    function = ast.parse("async def f(self, user_uid, project=None, *, sort_by=''): ...").body[0]
    assert isinstance(function, ast.AsyncFunctionDef)
    assert positional_parameters(function) == ["self", "user_uid", "project"]
