"""Every class that calls the dual-track template inherits it.

``BaseAnalyticsService`` defines ``_dual_track_assessment`` and
``_store_dual_track_checkin``. A class whose methods call either on ``self`` is a
subclass of the base, so the type checker reads the call against the base's
signature; it declares neither name itself and silences no error on the call.
"""

import ast
import importlib
from pathlib import Path

from core.services.base_analytics_service import BaseAnalyticsService

APP = Path(__file__).resolve().parents[3]
SERVICES = APP / "core" / "services"
TEMPLATE_MEMBERS = frozenset({"_dual_track_assessment", "_store_dual_track_checkin"})


def _self_reads(cls: ast.ClassDef) -> set[tuple[str, int]]:
    """Each ``self.<template member>`` read in the class body, with its line."""
    return {
        (node.attr, node.lineno)
        for node in ast.walk(cls)
        if isinstance(node, ast.Attribute)
        and node.attr in TEMPLATE_MEMBERS
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }


def _classes_reading_the_template() -> list[tuple[Path, ast.ClassDef, list[str]]]:
    found: list[tuple[Path, ast.ClassDef, list[str]]] = []
    for path in sorted(SERVICES.rglob("*.py")):
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        found.extend(
            (path, node, source.splitlines())
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and _self_reads(node)
        )
    return found


def _import_class(path: Path, name: str) -> type:
    module = ".".join(path.relative_to(APP).with_suffix("").parts)
    return getattr(importlib.import_module(module), name)


def test_the_sweep_finds_the_callers() -> None:
    callers = _classes_reading_the_template()
    assert len(callers) > 1, "the sweep found no more than one class calling the template"


def test_every_caller_is_a_subclass_of_the_base() -> None:
    orphans = [
        f"{path.relative_to(APP)}::{cls.name}"
        for path, cls, _lines in _classes_reading_the_template()
        if not issubclass(_import_class(path, cls.name), BaseAnalyticsService)
    ]
    assert orphans == []


def test_no_class_declares_a_template_member_it_does_not_define() -> None:
    declared = [
        f"{path.relative_to(APP)}:{statement.lineno} {cls.name}.{statement.target.id}"
        for path in sorted(SERVICES.rglob("*.py"))
        for cls in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        if isinstance(cls, ast.ClassDef)
        for statement in cls.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id in TEMPLATE_MEMBERS
    ]
    assert declared == []


def test_no_call_of_the_template_silences_the_type_checker() -> None:
    silenced = [
        f"{path.relative_to(APP)}:{line} {cls.name}.{member}"
        for path, cls, lines in _classes_reading_the_template()
        for member, line in sorted(_self_reads(cls))
        if "type: ignore" in lines[line - 1]
    ]
    assert silenced == []
