"""Every Activity Template service consumer holds the read-only protocol.

Templates are authored only in the content vault (ADR-091 S8). The six template
services still inherit ``BaseService``'s generic writers, so no consumer may hold the
concrete class: the ``Services`` container fields are typed
``ActivityTemplateOperations``, which names one read, and only the composition root
imports the concrete services.
"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_FIELDS = (
    "task_templates",
    "goal_templates",
    "habit_templates",
    "event_templates",
    "choice_templates",
    "principle_templates",
)
# The one module that may construct the concrete services.
COMPOSITION_ROOT = APP_ROOT / "services_bootstrap" / "_template_services.py"
FIRST_PARTY = ("core", "adapters", "ui", "services_bootstrap", "scripts")


def test_the_protocol_names_one_read_and_no_writer() -> None:
    from core.ports.template_protocols import ActivityTemplateOperations

    members = {name for name in vars(ActivityTemplateOperations) if not name.startswith("_")}
    assert members == {"list_for_pathstep"}


def test_the_attachment_port_names_one_read_and_no_writer() -> None:
    from core.ports.template_protocols import TemplateAttachmentOperations

    members = {name for name in vars(TemplateAttachmentOperations) if not name.startswith("_")}
    assert members == {"list_for_pathstep"}


@pytest.mark.parametrize("field_name", TEMPLATE_FIELDS)
def test_every_container_field_holds_the_protocol(field_name: str) -> None:
    from services_bootstrap._container import Services

    declared = {field.name: field.type for field in fields(Services)}
    assert "ActivityTemplateOperations" in str(declared[field_name]), declared[field_name]


def _imports_concrete_services(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.services.templates":
            return True
        if isinstance(node, ast.Import) and any(
            alias.name == "core.services.templates" for alias in node.names
        ):
            return True
    return False


def test_only_the_composition_root_imports_the_concrete_services() -> None:
    importers = {
        path.relative_to(APP_ROOT).as_posix()
        for package in FIRST_PARTY
        for path in (APP_ROOT / package).rglob("*.py")
        if _imports_concrete_services(path)
    }
    assert importers == {COMPOSITION_ROOT.relative_to(APP_ROOT).as_posix()}
