"""
Every facade the composition root registers as a filtered-context provider is one.

``_filtered_context_providers`` builds the ``filtered_providers`` dict the
intelligence factory hands to ``DailyPlanningMixin``. The service dicts it reads
are ``Any``-valued, so the dict's annotation checks nothing; the function checks
each facade against ``FilteredContextProvider`` itself and stops the boot on one
that has no ``get_filtered_context``.
"""

import ast
from pathlib import Path

import pytest

from core.ports.filtered_context_protocols import FilteredContextProvider
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.exercises.exercise_service import ExerciseService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.ku_service import KuService
from core.services.lp_service import LpService
from core.services.principles_service import PrinciplesService
from core.services.ps_service import PsService
from core.services.tasks_service import TasksService
from services_bootstrap._intelligence_hub import _filtered_context_providers

_SERVICES_ROOT = Path(__file__).resolve().parents[2] / "core" / "services"


def _bare(cls: type) -> object:
    """An instance of the real class without its constructor — the check is structural."""
    return object.__new__(cls)


def _activity_services() -> dict[str, object]:
    return {
        "tasks": _bare(TasksService),
        "goals": _bare(GoalsService),
        "habits": _bare(HabitsService),
        "events": _bare(EventsService),
        "choices": _bare(ChoicesService),
        "principles": _bare(PrinciplesService),
    }


def _learning_services() -> dict[str, object]:
    return {
        "atomic_ku_service": _bare(KuService),
        "ps": _bare(PsService),
        "learning_paths": _bare(LpService),
    }


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
    providers = _filtered_context_providers(
        _activity_services(), _learning_services(), _bare(ExerciseService)
    )

    assert providers
    for domain, facade in providers.items():
        assert isinstance(facade, FilteredContextProvider), domain


def test_the_registry_is_exactly_the_facades_that_implement_it() -> None:
    providers = _filtered_context_providers(
        _activity_services(), _learning_services(), _bare(ExerciseService)
    )

    registered = {type(facade).__name__ for facade in providers.values()}
    assert registered == _classes_defining_get_filtered_context()
    assert len(registered) == len(providers)


def test_the_ku_facade_is_not_a_provider() -> None:
    assert not isinstance(_bare(KuService), FilteredContextProvider)
    providers = _filtered_context_providers(
        _activity_services(), _learning_services(), _bare(ExerciseService)
    )
    assert "ku" not in providers


def test_a_facade_without_the_method_stops_the_boot() -> None:
    learning = _learning_services()
    learning["ps"] = _bare(KuService)

    with pytest.raises(RuntimeError, match=r"filtered_providers\['ps'\] is a KuService"):
        _filtered_context_providers(_activity_services(), learning, _bare(ExerciseService))
