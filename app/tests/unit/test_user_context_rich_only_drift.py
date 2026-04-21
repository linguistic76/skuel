"""
Drift Test — RICH_ONLY_FIELDS stays in sync with the populator.

The sentinel in ``test_user_context_rich_only_sentinel.py`` pins the *current*
six rich-only fields. This file catches *drift*: a seventh field quietly added
to a rich-only populator without being registered in
``UserContext.RICH_ONLY_FIELDS`` or given a ``None`` default.

The risk surface:

``UserContextPopulator.populate_from_consolidated_data`` (standard-depth) does
NOT touch the six rich-only fields. ``populate_derived_fields`` and
``populate_principle_choice_integration`` (rich-only) do. If a new container
field is added to a rich-only populator but forgotten in the registry, it
silently defaults to an empty container at standard depth — exactly the
blind spot the registry exists to prevent.

Mechanism:

1. AST-scan ``user_context_populator.py`` and collect every
   ``context.<field> = ...`` target in the three methods of interest.
2. Cross-check the three invariants below against the registry and dataclass
   defaults.

Scope: container fields (list/dict/set) only. Scalar fields have a distinct
ambiguity (``0.0`` can be legitimate zero state) that a None-default cannot
express; they are out of scope for this test.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import MISSING, fields
from functools import cache

import pytest

from core.services.user import user_context_populator
from core.services.user.unified_user_context import UserContext

# =============================================================================
# Populator AST — extract `context.<field>` assignment targets per method
# =============================================================================

STANDARD_POPULATOR = "populate_from_consolidated_data"
RICH_ONLY_POPULATORS = ("populate_derived_fields", "populate_principle_choice_integration")


@cache
def _populator_ast() -> ast.Module:
    return ast.parse(inspect.getsource(user_context_populator))


def _assigned_context_fields(method_name: str) -> frozenset[str]:
    """Return the set of ``context.<field>`` targets assigned in ``method_name``.

    AST-based so we count writes, not reads, and do not descend into calls
    like ``self.populate_activity_report(context, ...)`` — only direct
    ``context.X = ...`` in the method body counts.
    """
    for node in ast.walk(_populator_ast()):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            targets: set[str] = set()
            for assign in ast.walk(node):
                if not isinstance(assign, ast.Assign):
                    continue
                for target in assign.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "context"
                    ):
                        targets.add(target.attr)
            return frozenset(targets)

    pytest.fail(f"Populator method not found: {method_name}")


# =============================================================================
# Dataclass introspection — which fields are None-defaulted containers?
# =============================================================================


def _none_default_fields() -> frozenset[str]:
    """Fields on UserContext that explicitly default to ``None``."""
    return frozenset(f.name for f in fields(UserContext) if f.default is None)


def _container_fields() -> frozenset[str]:
    """Fields on UserContext whose default produces a list/dict/set container.

    We treat any field with a ``default_factory`` resolving to list/dict/set
    as a container. Fields with ``default=None`` are explicitly *not* containers
    at standard depth — that is the whole point of the registry.
    """
    out: set[str] = set()
    for f in fields(UserContext):
        if f.default_factory is MISSING:
            continue
        try:
            default = f.default_factory()
        except TypeError:
            continue
        if isinstance(default, (list, dict, set)):
            out.add(f.name)
    return frozenset(out)


# =============================================================================
# Invariant 1 — registry membership matches populator writes
# =============================================================================


def test_every_rich_only_field_is_written_by_a_rich_only_populator() -> None:
    """A registered field must actually be populated by build_rich().

    If a field is in the registry but no rich-only populator writes it, the
    entry is dead — either the populator regressed or the registry is stale.
    """
    written_by_rich: set[str] = set()
    for method in RICH_ONLY_POPULATORS:
        written_by_rich |= _assigned_context_fields(method)

    unwritten = UserContext.RICH_ONLY_FIELDS - written_by_rich
    assert not unwritten, (
        f"Fields in RICH_ONLY_FIELDS with no rich-only populator writing them: "
        f"{sorted(unwritten)}. Either add a populator assignment or remove the "
        f"entry from RICH_ONLY_FIELDS."
    )


def test_rich_only_fields_are_absent_from_standard_populator() -> None:
    """The standard populator must NOT touch a registered rich-only field.

    If it did, the field would no longer be rich-only — either drop it from
    the registry or remove the write from the standard populator.
    """
    written_by_standard = _assigned_context_fields(STANDARD_POPULATOR)
    leaked = UserContext.RICH_ONLY_FIELDS & written_by_standard
    assert not leaked, (
        f"RICH_ONLY_FIELDS written by {STANDARD_POPULATOR}: {sorted(leaked)}. "
        f"A field cannot be both rich-only and populated at standard depth. "
        f"Either promote it (remove from RICH_ONLY_FIELDS, switch default to a "
        f"container) or remove the standard-depth write."
    )


# =============================================================================
# Invariant 2 — registered fields default to None on the dataclass
# =============================================================================


def test_every_rich_only_field_defaults_to_none_on_the_dataclass() -> None:
    """Typed None default is the mechanism that makes the blind spot loud.

    An empty-container default would let a standard-depth read look like
    legitimate zero state. Enforce None at the field declaration.
    """
    none_defaults = _none_default_fields()
    missing_none = UserContext.RICH_ONLY_FIELDS - none_defaults
    assert not missing_none, (
        f"RICH_ONLY_FIELDS not declared with default=None: {sorted(missing_none)}. "
        f"Change the field declaration to `<Type> | None = field(default=None)`."
    )


# =============================================================================
# Invariant 3 — drift guard: no *new* rich-only container field slips in
# =============================================================================


def test_no_rich_only_container_field_is_unregistered() -> None:
    """Any container field written only by rich-only populators must be registered.

    This is the drift catch: if someone adds a new ``list``/``dict``/``set``
    field, wires it into ``populate_derived_fields`` or
    ``populate_principle_choice_integration``, and forgets both the registry
    and the ``| None`` default, it reintroduces the silent blind spot. The
    test fails and names the field so the fix is obvious.

    Resolution options, when this fires:
      a) Register in RICH_ONLY_FIELDS + switch default to None (true rich-only)
      b) Also populate it in populate_from_consolidated_data (promote to
         standard depth — mirrors commit a37eb040)
    """
    rich_only_writes: set[str] = set()
    for method in RICH_ONLY_POPULATORS:
        rich_only_writes |= _assigned_context_fields(method)

    standard_writes = _assigned_context_fields(STANDARD_POPULATOR)
    containers = _container_fields()

    unregistered = rich_only_writes - standard_writes - UserContext.RICH_ONLY_FIELDS
    drift = unregistered & containers
    assert not drift, (
        f"Container field(s) written only by rich-only populators but not "
        f"registered in RICH_ONLY_FIELDS: {sorted(drift)}. This is the silent "
        f"blind-spot pattern. Either register the field (+ default=None) or "
        f"populate it in populate_from_consolidated_data too."
    )
