"""Every enum-valued field is typed as its enum, and every DTO reads it as one.

Two promises, held for every class at once:

- A field whose name ``ENUM_FIELD_TYPES`` registers is annotated with the registry's
  enum on every ``Entity`` and ``EntityDTO`` subclass and on every DTO that converts
  through its own ``from_dict``, except the fields in ``_STILL_TYPED_STR``. That set
  only shrinks: a field in it that is typed as its enum fails here too.
- A DTO's ``from_dict`` turns a stored member value into the member for every field
  its annotation types as an enum, and its ``update_from`` does the same for every such
  field it accepts. A field left out of a DTO's hand-written conversion lists would
  hold the raw ``str`` under an enum annotation.

The classes are found by importing every module under ``core.models``, so a new DTO or
model is held without being listed here.
"""

from __future__ import annotations

import annotationlib
import dataclasses
import importlib
import inspect
import pkgutil
import sys
import types
import typing
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Protocol, Self

import pytest

import core.models
from core.models.entity import Entity
from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import ENUM_FIELD_TYPES


class _ConvertingDTO(Protocol):
    """What a DTO in ``core.models`` offers to read stored properties and apply updates."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self: ...  # boundary: stored node properties

    def update_from(self, updates: dict[str, Any]) -> None: ...  # boundary: field updates


# Enum-named fields still annotated ``str`` — (class name, field name).
_STILL_TYPED_STR: frozenset[tuple[str, str]] = frozenset(
    {
        ("Curriculum", "confidence"),
        ("Event", "event_type"),
        ("EventDTO", "event_type"),
        ("EventTemplate", "event_type"),
        ("EventTemplate", "recurrence_pattern"),
        ("EventTemplateDTO", "event_type"),
        ("EventTemplateDTO", "recurrence_pattern"),
        ("HabitTemplate", "recurrence_pattern"),
        ("HabitTemplateDTO", "recurrence_pattern"),
        ("RevisedExerciseDTO", "expected_modality"),
        ("UserOwnedDTO", "priority"),
        ("UserOwnedEntity", "priority"),
    }
)


def _class_id(cls: type) -> str:
    return cls.__name__


def _pair_id(pair: tuple[type, str]) -> str:
    return f"{pair[0].__name__}.{pair[1]}"


def _import_every_model_module() -> None:
    for module in pkgutil.walk_packages(core.models.__path__, "core.models."):
        importlib.import_module(module.name)


def _first_party_subclasses(root: type) -> set[type]:
    found: set[type] = set()
    pending = [root]
    while pending:
        cls = pending.pop()
        if cls.__module__.startswith("core.") and cls not in found:
            found.add(cls)
            pending.extend(cls.__subclasses__())
    return found


def _dto_classes() -> list[type]:
    """Every dataclass in a ``*_dto`` module of ``core.models`` that defines its own ``from_dict``."""
    _import_every_model_module()
    classes = {
        cls
        for module_name, module in list(sys.modules.items())
        if module_name.startswith("core.models.")
        and module_name.rsplit(".", 1)[-1].endswith("_dto")
        for cls in vars(module).values()
        if inspect.isclass(cls)
        and cls.__module__ == module_name
        and dataclasses.is_dataclass(cls)
        and "from_dict" in cls.__dict__
    }
    return sorted(classes, key=_class_id)


def _annotated_classes() -> list[type]:
    _import_every_model_module()
    classes = (
        _first_party_subclasses(Entity) | _first_party_subclasses(EntityDTO) | set(_dto_classes())
    )
    return sorted(classes, key=_class_id)


def _hints(cls: type) -> dict[str, Any]:  # boundary: resolved annotations of any type
    return typing.get_type_hints(cls, format=annotationlib.Format.FORWARDREF)


def _enum_of(hint: Any) -> type[Enum] | None:  # boundary: a resolved annotation
    """The enum an annotation names, alone or as ``X | None``; ``None`` for any other type."""
    if inspect.isclass(hint) and issubclass(hint, Enum):
        return hint
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        members = [arg for arg in typing.get_args(hint) if arg is not type(None)]
        if len(members) == 1:
            return _enum_of(members[0])
    return None


def _own_enum_named_fields() -> list[tuple[type, str]]:
    """(class, field) for each field a class declares itself whose name the registry names."""
    pairs: list[tuple[type, str]] = []
    for cls in _annotated_classes():
        own = annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
        pairs.extend((cls, name) for name in sorted(own) if name in ENUM_FIELD_TYPES)
    return pairs


def _enum_fields(cls: type) -> dict[str, type[Enum]]:
    """Every dataclass field of ``cls`` its annotation types as an enum."""
    hints = _hints(cls)
    names = {field.name for field in dataclasses.fields(cls)}
    return {name: enum for name in names if (enum := _enum_of(hints.get(name))) is not None}


def _required(field: dataclasses.Field[Any]) -> bool:  # boundary: a dataclass field of any type
    return field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


def _a_member_other_than(enum: type[Enum], default: object) -> Enum:
    """A member unlike the default, so a key ``from_dict`` dropped cannot pass as read.

    A one-member enum has none: its member, sent as text, still reads back as text when
    the field is left unread.
    """
    return next((member for member in enum if member != default), next(iter(enum)))


def _stored(hint: Any) -> str:  # boundary: a resolved annotation
    """A stored value a field of this type reads: an ISO string for a temporal, else text."""
    if hint is datetime:
        return "2026-01-01T09:00:00"
    if hint is date:
        return "2026-01-01"
    if hint is time:
        return "09:00:00"
    return "stored"


def _required_properties(cls: type) -> dict[str, Any]:  # boundary: stored node properties
    """The fewest properties ``from_dict`` needs: each required field, and the class's own entity_type."""
    hints = _hints(cls)
    enums = _enum_fields(cls)
    properties: dict[str, Any] = {}  # boundary: stored node properties
    for field in dataclasses.fields(cls):
        if field.name == "entity_type" and field.default is not dataclasses.MISSING:
            properties["entity_type"] = str(field.default)
        elif _required(field):
            enum = enums.get(field.name)
            properties[field.name] = next(iter(enum)).value if enum else _stored(hints[field.name])
    return properties


def _expected_members(cls: type) -> dict[str, Enum]:
    """For each enum field but entity_type, a member other than its default."""
    defaults = {field.name: field.default for field in dataclasses.fields(cls)}
    return {
        name: _a_member_other_than(enum, defaults.get(name))
        for name, enum in _enum_fields(cls).items()
        if name != "entity_type"
    }


_ENUM_NAMED = _own_enum_named_fields()
_DTOS = _dto_classes()
_DTOS_WITH_UPDATE = [cls for cls in _DTOS if "update_from" in cls.__dict__]


class TestTheWalkReachesEveryClass:
    def test_it_finds_the_models_and_dtos_it_holds(self) -> None:
        names = {cls.__name__ for cls in _annotated_classes()}

        assert {
            "Curriculum",
            "UserOwnedEntity",
            "EventTemplate",
            "KuDTO",
            "TaskDTO",
            "PrincipleReflectionDTO",
        } <= names

    def test_no_two_classes_share_a_name(self) -> None:
        names = [cls.__name__ for cls in _annotated_classes()]

        assert len(names) == len(set(names))

    def test_every_still_str_entry_names_a_field_the_walk_reaches(self) -> None:
        reached = {(cls.__name__, name) for cls, name in _ENUM_NAMED}

        assert _STILL_TYPED_STR.issubset(reached), sorted(_STILL_TYPED_STR - reached)


@pytest.mark.parametrize(("cls", "name"), _ENUM_NAMED, ids=[_pair_id(p) for p in _ENUM_NAMED])
def test_an_enum_named_field_is_typed_as_its_registered_enum(cls: type, name: str) -> None:
    typed_as = _enum_of(_hints(cls)[name])
    registered = ENUM_FIELD_TYPES[name]

    if (cls.__name__, name) in _STILL_TYPED_STR:
        assert typed_as is not registered, (
            f"{cls.__name__}.{name} is typed as {registered.__name__}: take it out of _STILL_TYPED_STR"
        )
    else:
        assert typed_as is registered, (
            f"{cls.__name__}.{name} is not typed as {registered.__name__}, the enum "
            f"ENUM_FIELD_TYPES registers for '{name}'"
        )


@pytest.mark.parametrize("cls", _DTOS, ids=[_class_id(cls) for cls in _DTOS])
def test_from_dict_reads_each_enum_field_as_its_member(cls: type[_ConvertingDTO]) -> None:
    expected = _expected_members(cls)
    stored = {
        **_required_properties(cls),
        **{name: member.value for name, member in expected.items()},
    }

    dto = cls.from_dict(stored)

    left_as_str = sorted(
        name for name, member in expected.items() if getattr(dto, name) is not member
    )
    assert not left_as_str, f"{cls.__name__}.from_dict leaves {left_as_str} unread as their enum"


@pytest.mark.parametrize(
    "cls", _DTOS_WITH_UPDATE, ids=[_class_id(cls) for cls in _DTOS_WITH_UPDATE]
)
def test_update_from_reads_each_enum_field_it_accepts_as_its_member(
    cls: type[_ConvertingDTO],
) -> None:
    dto = cls.from_dict(_required_properties(cls))
    expected = _expected_members(cls)

    dto.update_from({name: member.value for name, member in expected.items()})

    left_as_str = sorted(name for name in expected if type(getattr(dto, name)) is str)
    assert not left_as_str, f"{cls.__name__}.update_from accepts {left_as_str} as raw text"
