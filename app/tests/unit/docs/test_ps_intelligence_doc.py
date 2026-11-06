"""Pin PS_INTELLIGENCE.md's method table to the class and the PLANNED registry.

The per-method sections this table replaced drifted without anyone noticing: three
methods were never added, and the prose named a query executor the service no longer
held. Both sides here are derived, so a new public method, a removed one, or a
registration without its row breaks the build until the table agrees.
``app/docs/intelligence/PS_INTELLIGENCE.md`` is in CI's ``py`` path filter so a
docs-only edit to the table still runs this module.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_DOC = _ROOT / "docs" / "intelligence" / "PS_INTELLIGENCE.md"
_SERVICE_REL = "core/services/ps/ps_intelligence_service.py"

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(_ROOT / "scripts"))

from detect_bloat import PLANNED_METHODS  # type: ignore[import-not-found]  # noqa: E402

# Inherited from _CoreIntelligenceMixin, so the class body does not define it.
_INHERITED = {"get_with_context"}


def _method_rows() -> dict[str, str]:
    """The table under ``## Methods``: method name -> its "Called by" cell."""
    section = _DOC.read_text().split("## Methods", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"\| `(\w+)\(.*\| ([^|]*) \|$", line)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def _public_methods() -> set[str]:
    tree = ast.parse((_ROOT / _SERVICE_REL).read_text())
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PsIntelligenceService"
    )
    return {
        node.name
        for node in service.body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        and not node.name.startswith("_")
    }


def test_the_table_names_every_public_method_and_nothing_else() -> None:
    assert set(_method_rows()) == _public_methods() | _INHERITED


def test_a_planned_row_is_a_planned_registration() -> None:
    planned_in_doc = {name for name, called_by in _method_rows().items() if called_by == "PLANNED"}
    registered = {
        key.rpartition("::")[2] for key in PLANNED_METHODS if key.startswith(f"{_SERVICE_REL}::")
    }
    assert planned_in_doc == registered
