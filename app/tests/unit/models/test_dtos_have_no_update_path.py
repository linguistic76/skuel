"""A DTO offers no in-place update.

An update is a patch: a typed ``*UpdateIntent`` (or a ``RawChanges`` patch) through the
service contract, written by the backend and held to each field's type by the write gate
(ADR-066, ADR-087). No class in ``core.models`` defines ``update_from``, and
``dto_helpers`` has no ``update_from_dict``.

The classes are found by importing every module under ``core.models``, so a new DTO is
held without being listed here.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys

import core.models
from core.models import dto_helpers


def _qualified(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _model_classes() -> list[type]:
    """Every class defined in a module under ``core.models``."""
    for module in pkgutil.walk_packages(core.models.__path__, "core.models."):
        importlib.import_module(module.name)
    classes = {
        cls
        for module_name, module in list(sys.modules.items())
        if module_name.startswith("core.models.")
        for cls in vars(module).values()
        if inspect.isclass(cls) and cls.__module__ == module_name
    }
    return sorted(classes, key=_qualified)


def test_the_walk_reaches_the_dtos() -> None:
    names = {cls.__name__ for cls in _model_classes()}

    assert {"EntityDTO", "UserOwnedDTO", "TaskDTO", "TaskTemplateDTO", "UserDTO"} <= names


def test_no_class_in_core_models_defines_update_from() -> None:
    defining = [_qualified(cls) for cls in _model_classes() if "update_from" in vars(cls)]

    assert not defining, f"update a DTO through a patch, not in place: {defining}"


def test_dto_helpers_has_no_update_from_dict() -> None:
    defined = "update_from_dict" in vars(dto_helpers)

    assert not defined, "core.models.dto_helpers defines update_from_dict"
