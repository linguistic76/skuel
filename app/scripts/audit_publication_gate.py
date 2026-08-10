#!/usr/bin/env python3
"""Publication-gate registry completeness audit.

Asserts that every surface in the persistence layer which composes a publication
gate helper is CLASSIFIED in ``scripts/publication_gate_registry.py`` — and,
symmetrically, that every registry entry still names a real surface.

**The claim this script makes, and the one it refuses to make.** It answers "is
this surface classified?", which is exactly decidable from the AST: a call to a
named helper either appears inside a given function or it does not. It does NOT
answer "is this surface correctly gated?" — that needs to know which alias
carries the claim, whether the predicate landed before or after a progress
match, and whether a draft uid escapes inside a ``collect()``. Approximating
that with a pattern is how #831 spent nineteen rounds on a regex standing in for
a parser for zero measured delta, and #868's rule is to narrow the claim rather
than add approximations to a CI gate. Correctness is measured instead by
``tests/integration/test_publication_gate_output_invariant.py``, which runs the
surface and looks at what actually comes back.

**Why completeness is worth gating on anyway.** Of the six defects Codex found
on #1008, two were surfaces the structural census never saw — one bound its
node without a label, the other bridged through an anonymous ``(:Entity)``.
Neither is visible to a label-keyed scan. Keying instead on "does this function
call a gate helper" is immune to both, because it reads the Python, not the
Cypher.

Usage:
    uv run python scripts/audit_publication_gate.py           # CI gate
    uv run python scripts/audit_publication_gate.py --verbose # list every surface
    uv run python scripts/audit_publication_gate.py --json

Exit codes: 0 = registry complete, 1 = unregistered surface or stale entry.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Sibling-module import, mirroring cypher_linter/cypher_vocabulary: scripts/ has
# no __init__.py, and under pytest the tests/unit/scripts/ directory shadows the
# name `scripts` outright, so a package-qualified import resolves to the wrong
# tree.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from publication_gate_registry import (  # type: ignore[import-not-found]
    SURFACES,
    registry_keys,
)

ROOT = Path(__file__).resolve().parent.parent  # /home/mike/skuel/app
SCAN_DIR = ROOT / "adapters" / "persistence"

GATE_HELPERS = frozenset(
    {
        "build_publication_clause",
        "build_knowledge_read_clause",
        "build_search_visibility_clause",
    }
)


@dataclass(frozen=True)
class Found:
    """A surface discovered in the tree that composes a gate helper."""

    module: str
    qualname: str
    lineno: int
    helpers: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.module, self.qualname)

    def sort_key(self) -> tuple[str, str]:
        """Stable ordering for reports (the dataclass is frozen, not ordered)."""
        return self.key


def _module_name(path: Path) -> str:
    """Dotted module name for ``path``, relative to the app root.

    Falls back to the bare stem for a path outside the root rather than
    raising: ``scan_file`` is exercised directly against temporary files, and a
    scanner that dies on an unexpected path fails the build for a reason that
    has nothing to do with the gate.
    """
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return path.stem
    return ".".join(relative.with_suffix("").parts)


def _called_helper(node: ast.Call) -> str | None:
    """The gate-helper name this call targets, if any.

    Matches both ``build_publication_clause(...)`` and ``mod.build_...(...)`` —
    an attribute call is how a module-qualified import would spell it, and
    keying on the attribute keeps that from reading as unclassified.
    """
    func = node.func
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return None
    return name if name in GATE_HELPERS else None


MODULE_SCOPE = "<module>"
"""Qualname for a gate composed outside any function.

Not a curiosity: ``zpd_backend`` builds ``_ZONE_QUERY`` at import time by
substituting a sentinel, so its gate is composed by a module-level assignment.
An earlier revision of this scanner only descended into functions and reported
that file as having no surfaces at all — the instrument was blind to the purest
discovery surface in the tree, which is the exact failure mode #1008's census
had twice over.
"""


def scan_file(path: Path) -> list[Found]:
    """Every surface in ``path`` that composes a gate helper, with its qualname.

    Attributes each call to its nearest enclosing function, or to
    ``<module>`` when there is none. Walks with an explicit scope stack rather
    than ``ast.walk``, which hands out nodes with no parent context — a nested
    def would otherwise be attributed to its enclosing class, and a module-level
    composition to nothing at all.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    module = _module_name(path)
    # qualname -> (first line seen, helper names)
    hits: dict[str, tuple[int, set[str]]] = {}

    def record(qualname: str, lineno: int, helper: str) -> None:
        line, helpers = hits.get(qualname, (lineno, set()))
        helpers.add(helper)
        hits[qualname] = (min(line, lineno), helpers)

    def visit(node: ast.AST, stack: tuple[str, ...], owner: str) -> None:
        """``stack`` is the qualname path; ``owner`` is the enclosing function's."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, (*stack, child.name), owner)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = (*stack, child.name)
                visit(child, inner, ".".join(inner))
            else:
                if isinstance(child, ast.Call) and (helper := _called_helper(child)):
                    record(owner, child.lineno, helper)
                visit(child, stack, owner)

    visit(tree, (), MODULE_SCOPE)
    return [
        Found(module, qualname, line, tuple(sorted(helpers)))
        for qualname, (line, helpers) in sorted(hits.items())
    ]


def scan_tree() -> list[Found]:
    """Every gate-composing surface under ``adapters/persistence/``.

    ``crud_queries`` itself is excluded: it DEFINES the helpers, and the
    composition inside ``build_knowledge_read_clause`` /
    ``build_search_visibility_clause`` is the helpers delegating to each other,
    not a discovery surface with an audience.
    """
    surfaces: list[Found] = []
    for path in sorted(SCAN_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name == "crud_queries.py":
            continue
        surfaces.extend(scan_file(path))
    return surfaces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="list every surface found")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    found = scan_tree()
    registered = registry_keys()
    found_keys = {f.key for f in found}

    unregistered = sorted((f for f in found if f.key not in registered), key=Found.sort_key)
    stale = sorted(registered - found_keys)

    if args.as_json:
        print(
            json.dumps(
                {
                    "found": len(found),
                    "registered": len(registered),
                    "unregistered": [
                        {"module": f.module, "qualname": f.qualname, "line": f.lineno}
                        for f in unregistered
                    ],
                    "stale": [{"module": m, "qualname": q} for m, q in stale],
                },
                indent=2,
            )
        )
        return 1 if (unregistered or stale) else 0

    if args.verbose:
        print(f"Gate-composing surfaces in {SCAN_DIR.relative_to(ROOT)}: {len(found)}\n")
        for f in found:
            mark = " " if f.key in registered else "!"
            print(f" {mark} {f.module}:{f.lineno}  {f.qualname}  [{', '.join(f.helpers)}]")
        print()

    for f in unregistered:
        print(
            f"UNREGISTERED  {f.module}:{f.lineno}  {f.qualname}\n"
            f"              composes {', '.join(f.helpers)} but is not classified.\n"
            f"              Add a Surface(...) to scripts/publication_gate_registry.py with a\n"
            f"              disposition and a reason. If it is GATED, the output invariant in\n"
            f"              tests/integration/test_publication_gate_output_invariant.py must\n"
            f"              also cover it.",
            file=sys.stderr,
        )

    for module, qualname in stale:
        print(
            f"STALE         {module}  {qualname}\n"
            f"              registered, but no longer composes a gate helper. Either the gate\n"
            f"              was removed (a security change — say so) or the surface was renamed.",
            file=sys.stderr,
        )

    if unregistered or stale:
        print(
            f"\n{len(unregistered)} unregistered, {len(stale)} stale "
            f"({len(found)} surfaces found, {len(registered)} registered)",
            file=sys.stderr,
        )
        return 1

    print(f"✅ publication-gate registry complete: {len(found)} surfaces, all classified")
    print(f"   dispositions: {_disposition_summary()}")
    return 0


def _disposition_summary() -> str:
    counts: dict[str, int] = {}
    for surface in SURFACES:
        counts[surface.disposition.value] = counts.get(surface.disposition.value, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))


if __name__ == "__main__":
    sys.exit(main())
