"""An update value and a filter each have one spelling in ``core/ports``.

An update is a frozen ``*UpdateIntent`` or a ``RawChanges`` patch (ADR-066). A filter is
``FilterParams``, whose keys are fields of the model the backend filters.

A TypedDict spelling of either is assignable to neither ``dict[str, Any]`` nor
``FilterParams``, so no signature can take one, and nothing holds its keys to a model:
``find_by`` skips a key the model lacks and the rows come back unfiltered on it.

See: /docs/decisions/ADR-066-typed-update-intents.md, /docs/patterns/query_architecture.md
"""

from __future__ import annotations

import ast
from pathlib import Path

import core.ports

PORTS_DIR = Path(core.ports.__file__).parent
_SUFFIXES = ("UpdatePayload", "FilterSpec")


def _declared_classes() -> list[tuple[str, str]]:
    """Every class declared at module level in ``core/ports``, as (file name, class name)."""
    found: list[tuple[str, str]] = []
    for path in sorted(PORTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend((path.name, node.name) for node in tree.body if isinstance(node, ast.ClassDef))
    return found


def test_the_scan_reads_the_ports_package() -> None:
    """The scan sees the port classes it is meant to judge."""
    names = {name for _file, name in _declared_classes()}
    assert {"TaskStats", "BackendOperations"} <= names


def test_ports_declare_no_update_payload_or_filter_spec() -> None:
    offenders = [
        f"{file}: {name}" for file, name in _declared_classes() if name.endswith(_SUFFIXES)
    ]
    assert offenders == [], (
        "core/ports declares a TypedDict spelling of an update or a filter. Take a "
        "*UpdateIntent or RawChanges for an update and FilterParams for a filter:\n  "
        + "\n  ".join(offenders)
    )


def test_ports_export_no_update_payload_or_filter_spec() -> None:
    exported = [name for name in core.ports.__all__ if name.endswith(_SUFFIXES)]
    assert exported == []
