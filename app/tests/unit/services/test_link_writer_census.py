"""Every edge writer under ``core/services/`` says how its far end is admitted.

``create_relationship`` and ``create_relationships_batch`` turn two uids into an
edge. A call that hands them a uid from a request without admitting it joins one
user's entity to another's (ADR-085 § G11). This census holds every call site to
one of four answers, and fails on a call site it does not know:

- it goes through ``UnifiedRelationshipService`` and declares its far end
  (``far_end=`` / ``far_ends=``) — the service admits it;
- it is the service's own write, behind that admission;
- its enclosing function admits through the link-edge guard itself;
- it is named in ``OTHERWISE_ADMITTED`` with the reason.

A new call site lands in none of them and fails here until it picks one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVICES = Path(__file__).resolve().parents[3] / "core" / "services"
_WRITERS = {"create_relationship", "create_relationships_batch"}
_GUARDS = {
    "keep_permitted_link_edges",
    "admit_far_ends_for_owner",
    "admit_far_ends_for_source",
}
_THE_SERVICE = "relationships/unified_relationship_service.py"

# Call sites whose far end is admitted by something this census cannot read off the
# call: ``"<path under core/services>::<function>"`` -> why the far end is safe.
OTHERWISE_ADMITTED: dict[str, str] = {
    "ps_engagement/_spawn_orchestrator.py::_persist": (
        "both ends are instances this spawn minted for one user in one engagement"
    ),
    "lateral_relationships/lateral_relationship_service.py::create_lateral_relationship": (
        "admits both ends through _verify_write_endpoints"
    ),
    "tasks_service.py::create_task_dependency": (
        "its one door (POST /tasks/{uid}/dependencies/add) verifies the caller owns both tasks"
    ),
    "interaction/interaction_service.py::create_interaction": (
        "NOT admitted — the context uids of an Interaction are an open row of ADR-085 § G11"
    ),
}


def _receiver(call: ast.Call) -> str:
    assert isinstance(call.func, ast.Attribute)
    return ast.unparse(call.func.value)


def _call_sites() -> list[tuple[str, ast.Call, ast.AST]]:
    """``(key, call, enclosing function)`` for every writer call under core/services."""
    sites: list[tuple[str, ast.Call, ast.AST]] = []
    for path in sorted(_SERVICES.rglob("*.py")):
        relative = path.relative_to(_SERVICES).as_posix()
        tree = ast.parse(path.read_text())
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            sites.extend(
                (f"{relative}::{function.name}", node, function)
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _WRITERS
            )
    return sites


def _how_admitted(key: str, call: ast.Call, function: ast.AST) -> str | None:
    relative = key.split("::", 1)[0]
    keywords = {keyword.arg for keyword in call.keywords}
    if _receiver(call) == "self.relationships":
        return "declared" if keywords & {"far_end", "far_ends"} else None
    if relative == _THE_SERVICE:
        names = {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)}
        return "the service" if "admit_far_ends" in names else None
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    if names & _GUARDS:
        return "guard"
    return "named" if key in OTHERWISE_ADMITTED else None


_SITES = _call_sites()


def test_the_census_sees_the_writers() -> None:
    """The walk finds the call sites it is a census of — an empty walk passes nothing."""
    keys = {key for key, _, _ in _SITES}

    assert "goals_service.py::link_goal_to_knowledge" in keys
    assert "events_service.py::_replace_edge" in keys
    assert "goals/goals_core_service.py::_write_link_edges" in keys
    assert f"{_THE_SERVICE}::create_relationship" in keys
    assert len(_SITES) >= 30


@pytest.mark.parametrize(
    ("key", "call", "function"),
    _SITES,
    ids=[f"{key}:{call.lineno}" for key, call, _ in _SITES],
)
def test_every_edge_writer_admits_its_far_end(key: str, call: ast.Call, function: ast.AST) -> None:
    assert _how_admitted(key, call, function) is not None, (
        f"{key} (line {call.lineno}) writes an edge and names no admission for its far end. "
        "Go through UnifiedRelationshipService with far_end=, admit through "
        "core/services/mixins/link_edge_guard.py, or name the reason in OTHERWISE_ADMITTED."
    )


def test_no_named_reason_outlives_its_call_site() -> None:
    assert set(OTHERWISE_ADMITTED) <= {key for key, _, _ in _SITES}
