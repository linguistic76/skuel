"""A DTO with no status reads its type's default status, as the model does.

``Entity.status`` is filled in from ``EntityType.default_status()`` when none is
given; the DTO follows the same rule. A node stored with no ``status`` (a Ku or Resource
the content-vault sync writes from a file that authors none) therefore reads one status whichever way it
is read: through the mapper (``from_neo4j_node``) or through ``DTO.from_dict`` →
``from_dto`` (``to_domain_model``, the Askesis bundle, the sharing lists).

The census covers every leaf DTO under ``core/models`` — one per ``EntityType`` — so
a new DTO is held without being listed here. The default is a status the type
allows (``valid_statuses()``), and each create factory starts its entity there.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.choice.choice_dto import ChoiceDTO
from core.models.entity_dto import EntityDTO
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.event_dto import EventDTO
from core.models.goal.goal_dto import GoalDTO
from core.models.habit.habit_dto import HabitDTO
from core.models.principle.principle_dto import PrincipleDTO
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import UserUID
from core.utils.dto_converters import to_domain_model

_MODELS = Path(__file__).resolve().parents[3] / "core" / "models"


def _leaf_dtos() -> dict[
    EntityType, tuple[type[EntityDTO], type[Any]]
]:  # boundary: 25 model classes
    """Every DTO that names its own entity type, with the model beside it.

    The model lives in the sibling module (``resource_dto.py`` → ``resource.py``)
    under the DTO's name without its suffix (``ResourceDTO`` → ``Resource``).
    """
    found: dict[EntityType, tuple[type[EntityDTO], type[Any]]] = {}  # boundary: as above
    for path in sorted(_MODELS.rglob("*_dto.py")):
        module_name = ".".join(path.relative_to(_MODELS.parents[1]).with_suffix("").parts)
        module = importlib.import_module(module_name)
        for candidate in vars(module).values():
            if not (
                isinstance(candidate, type)
                and issubclass(candidate, EntityDTO)
                and candidate.__module__ == module_name
            ):
                continue
            entity_type = next(
                f.default for f in dataclasses.fields(candidate) if f.name == "entity_type"
            )
            if not isinstance(entity_type, EntityType):
                continue  # a base DTO (EntityDTO, UserOwnedDTO, CurriculumDTO)
            model_module = importlib.import_module(module_name.removesuffix("_dto"))
            model = getattr(model_module, candidate.__name__.removesuffix("DTO"))
            found[entity_type] = (candidate, model)
    return found


_LEAVES = _leaf_dtos()


def test_the_census_finds_one_dto_per_entity_type() -> None:
    assert set(_LEAVES) == set(EntityType)


def _stored_without_status(entity_type: EntityType) -> dict[str, Any]:  # boundary: node props
    return {
        "uid": f"{entity_type.value}.probe",
        "title": "Probe",
        "entity_type": entity_type.value,
        "user_uid": "user_0123456789abcdef",
    }


@pytest.mark.parametrize("entity_type", sorted(_LEAVES, key=str), ids=str)
def test_a_dto_with_no_status_reads_its_types_default(entity_type: EntityType) -> None:
    dto_class, _ = _LEAVES[entity_type]

    dto = dto_class.from_dict(_stored_without_status(entity_type))

    assert dto.status is entity_type.default_status()
    assert dto.status in entity_type.valid_statuses()


@pytest.mark.parametrize("entity_type", sorted(_LEAVES, key=str), ids=str)
def test_a_null_status_reads_its_types_default(entity_type: EntityType) -> None:
    dto_class, _ = _LEAVES[entity_type]

    dto = dto_class.from_dict({**_stored_without_status(entity_type), "status": None})

    assert dto.status is entity_type.default_status()


@pytest.mark.parametrize("entity_type", sorted(_LEAVES, key=str), ids=str)
def test_the_mapper_and_the_dto_path_read_one_status(entity_type: EntityType) -> None:
    dto_class, model = _LEAVES[entity_type]
    stored = _stored_without_status(entity_type)

    via_mapper = from_neo4j_node(dict(stored), model)
    via_dto = to_domain_model(dict(stored), dto_class, model)

    assert via_dto.status is via_mapper.status is entity_type.default_status()


def test_a_base_dto_reads_the_default_of_the_type_it_is_told() -> None:
    assert EntityDTO.from_dict({"entity_type": "resource"}).status is EntityStatus.COMPLETED
    assert EntityDTO(entity_type=EntityType.HABIT).status is EntityStatus.ACTIVE


def test_a_stated_status_is_kept() -> None:
    assert EventDTO(status=EntityStatus.COMPLETED).status is EntityStatus.COMPLETED


_USER = UserUID("user_0123456789abcdef")


@pytest.mark.parametrize(
    ("dto", "entity_type"),
    [
        (TaskDTO.create_task(_USER, "t"), EntityType.TASK),
        (GoalDTO.create_goal(_USER, "g"), EntityType.GOAL),
        (HabitDTO.create_habit(_USER, "h"), EntityType.HABIT),
        (EventDTO.create_event(_USER, "e"), EntityType.EVENT),
        (ChoiceDTO.create_choice(_USER, "c"), EntityType.CHOICE),
        (PrincipleDTO.create_principle(_USER, "p"), EntityType.PRINCIPLE),
    ],
    ids=["task", "goal", "habit", "event", "choice", "principle"],
)
def test_each_create_factory_starts_at_its_types_default(
    dto: EntityDTO, entity_type: EntityType
) -> None:
    assert dto.status is entity_type.default_status()
