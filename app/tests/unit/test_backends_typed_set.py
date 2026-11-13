"""``Backends`` names what ``create_all_backends`` returns — every key, under its class.

The composition root reads its backends by name from a typed set
(``services_bootstrap/_backends.py``), so mypy checks each one against the protocol
its consumer declares. That check is only as true as the set: an entry declared
under a class the function does not build would check a consumer against the wrong
adapter. So the declaration is held to the object — the same keys, and each value
an instance of the class its entry names (for a generic
``UniversalNeo4jBackend[Model]``, serving that model).
"""

from __future__ import annotations

from typing import get_args, get_origin, get_type_hints
from unittest.mock import MagicMock

from services_bootstrap._backends import Backends, create_all_backends


def _built() -> dict[str, object]:
    return dict(create_all_backends(MagicMock(), MagicMock()))


def mismatches(declared: dict[str, type], built: dict[str, object]) -> list[str]:
    """Each entry whose value is not what its declaration names."""
    wrong = []
    for key, annotation in declared.items():
        origin = get_origin(annotation)
        cls = origin or annotation
        value = built[key]
        if type(value) is not cls:
            wrong.append(f"{key}: declared {cls.__name__}, built {type(value).__name__}")
        elif (
            origin is not None
            and getattr(value, "entity_class", None) is not get_args(annotation)[0]
        ):
            wrong.append(f"{key}: declared over {get_args(annotation)[0].__name__}")
    return wrong


def test_the_set_declares_exactly_the_keys_built() -> None:
    assert set(get_type_hints(Backends)) == set(_built())


def test_every_entry_is_declared_under_the_class_built() -> None:
    assert mismatches(get_type_hints(Backends), _built()) == []


def test_a_wrong_class_and_a_wrong_model_are_both_named() -> None:
    """The control: the comparison refuses a declaration the object does not match."""
    declared = get_type_hints(Backends)
    built = _built()
    swapped = {
        **declared,
        "tasks_backend": declared["events_backend"],
        "askesis_backend": declared["invoice_backend"],
    }
    assert mismatches(swapped, built) == [
        "tasks_backend: declared EventsBackend, built TasksBackend",
        "askesis_backend: declared over InvoicePure",
    ]
