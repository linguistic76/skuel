"""Every edge writer under ``core/services/`` says how its far end is admitted.

Five calls turn two uids into an edge: ``create_relationship``,
``create_relationships_batch``, ``replace_relationships``, ``write_guarded_links`` and
``add_relationship`` — the last through the
``relate(backend, uid).via(...).to(...).create()`` builder, so a ``relate(`` call is
a write site too. A call that hands any of them a uid from a request without
admitting it joins one user's entity to another's (ADR-085 § G11). This census holds
every call site to one of five answers, and fails on a call site it does not know:

- it goes through ``UnifiedRelationshipService`` and declares its far end
  (``far_end=`` / ``far_ends=``) — the service admits it;
- it is the service's own write, behind that admission — in a function that admits, or
  in the one writer (``_write_links``) every caller of which admits;
- it is a pass-through — the builder's ``create`` and the mixin's ``add_relationship``
  — whose callers are themselves sites of this census;
- its enclosing function admits through the link-edge guard itself;
- it is named in ``OTHERWISE_ADMITTED`` with the reason.

A new call site lands in none of them and fails here until it picks one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVICES = Path(__file__).resolve().parents[3] / "core" / "services"
_WRITER_METHODS = {
    "create_relationship",
    "create_relationships_batch",
    "replace_relationships",
    "write_guarded_links",
    "add_relationship",
}
_BUILDER = "relate"
_GUARDS = {
    "keep_permitted_link_edges",
    "partition_link_edges",
    "admit_far_ends_for_owner",
    "admit_far_ends_for_source",
}
_THE_SERVICE = "relationships/unified_relationship_service.py"
# What a function of the service calls to admit its far ends: the admission itself, or
# the helper that admits or checks a proof covers the link.
_SERVICE_ADMISSIONS = {"admit_far_ends", "_admitted"}
_SERVICE_WRITER = "_write_links"

# Writes that only forward to another write this census sees:
# ``"<path under core/services>::<function>"`` -> what forwards to what.
PASS_THROUGHS: dict[str, str] = {
    "relationship_builder.py::create": (
        "the builder's terminal step — backend.add_relationship, reached only from a "
        "relate( site, each censused here"
    ),
    "mixins/relationship_operations_mixin.py::add_relationship": (
        "the service-side add_relationship — one relate( call, reached only from an "
        "add_relationship site, each censused here"
    ),
}

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
        "one caller, UserEntryService._create_interaction_record: context_path_step_uid is "
        "the entry's about_path_step_uid, admitted as a published PathStep by "
        "AudienceResolver._validate_reference_claims (PATH_STEP_FAR_END) before the entry "
        "is written; source_entity_uid is the entry the service just wrote; "
        "context_learning_path_uid has no writer"
    ),
    "user_entry/user_entry_service.py::create_entry": (
        "the TRANSFORMS predecessor (transforms_of_uid) is admitted as the caller's own "
        "entity by AudienceResolver._validate_reference_claims before the entry is written"
    ),
    "tasks/tasks_progress_service.py::assign_task_to_user": (
        "reached only through TasksService.assign_task_to_user, which no route calls "
        "(staged — PLANNED in scripts/detect_bloat.py); its far end is a User, the "
        "assignee, not another user's entity"
    ),
    "mixins/relationship_operations_mixin.py::add_prerequisite": (
        "no caller (staged — PLANNED in scripts/detect_bloat.py); a door that reaches it "
        "admits the prerequisite before this write, which checks the uid's shape only"
    ),
    "infrastructure/semantic_relationship_linker.py::create_semantic_relationship": (
        "no door: every caller is a facade's create_semantic_*_relationship (PLANNED in "
        "scripts/detect_bloat.py), reached by no route"
    ),
}


def _is_write(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in _WRITER_METHODS
    return isinstance(node.func, ast.Name) and node.func.id == _BUILDER


def _receiver(call: ast.Call) -> str | None:
    """The object a writer method is called on; ``None`` for the builder function."""
    if isinstance(call.func, ast.Attribute):
        return ast.unparse(call.func.value)
    return None


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
                if isinstance(node, ast.Call) and _is_write(node)
            )
    return sites


def _how_admitted(key: str, call: ast.Call, function: ast.AST) -> str | None:
    relative = key.split("::", 1)[0]
    keywords = {keyword.arg for keyword in call.keywords}
    if _receiver(call) == "self.relationships":
        return "declared" if keywords & {"far_end", "far_ends"} else None
    if relative == _THE_SERVICE:
        if _admits(function):
            return "the service"
        name = getattr(function, "name", "")
        return "the service" if name == _SERVICE_WRITER and _every_caller_admits(name) else None
    if key in PASS_THROUGHS:
        return "pass-through"
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    if names & _GUARDS:
        return "guard"
    return "named" if key in OTHERWISE_ADMITTED else None


def _admits(function: ast.AST) -> bool:
    names = {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)}
    return bool(names & _SERVICE_ADMISSIONS)


def _every_caller_admits(writer: str) -> bool:
    """Whether the service calls ``writer`` at least once, and only from functions that admit."""
    tree = ast.parse((_SERVICES / _THE_SERVICE).read_text())
    callers = [
        function
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(node, ast.Attribute) and node.attr == writer for node in ast.walk(function)
        )
        and function.name != writer
    ]
    return bool(callers) and all(_admits(function) for function in callers)


_SITES = _call_sites()


def test_the_census_sees_the_writers() -> None:
    """The walk finds the call sites it is a census of — an empty walk passes nothing."""
    keys = {key for key, _, _ in _SITES}

    assert "goals_service.py::link_goal_to_knowledge" in keys
    assert "events_service.py::_replace_edges" in keys
    assert "tasks_service.py::_sync_relationship_edges" in keys
    assert f"{_THE_SERVICE}::_write_links" in keys
    assert "goals/goals_core_service.py::_write_link_edges" in keys
    # The add_relationship family: the builder's own write, a relate( site, an
    # add_relationship site.
    assert "relationship_builder.py::create" in keys
    assert "user_entry/user_entry_service.py::create_entry" in keys
    assert "user_entry/user_entry_service.py::link_applied_knowledge" in keys
    assert len(_SITES) >= 35


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
    keys = {key for key, _, _ in _SITES}
    assert set(OTHERWISE_ADMITTED) <= keys
    assert set(PASS_THROUGHS) <= keys
