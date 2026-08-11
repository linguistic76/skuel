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

**It also asserts one thing about the gate's STATE, because that much is
exactly decidable.** ``apply_publication_gate=False`` turns a composed gate off
in one word, and keying on the call alone cannot see it: the by-UID read
composes the helper and switches the predicate off, and it sat in the GATED set
for two PRs because this audit counted the call and stopped there. So a GATED
surface may not disable the gate — a carve-out must carry the disposition that
says which kind it is. The output invariant catches this only for the surfaces
it can measure; for the thirteen listed UNMEASURABLE it was caught by nothing.
A non-literal kwarg is reported as UNDECIDABLE rather than assumed, because
assuming True fails OPEN on exactly the surface whose gate is hardest to read.

**THE LIMITATION, STATED PLAINLY.** This audit is keyed on the gate CALL, so it
catches a gate that is removed, renamed, disabled or left unclassified — but a
brand-new query that never calls a helper at all produces no entry, is absent
from both sides of the comparison, and passes. **Adding an ungated discovery
surface is therefore still silent here** (Codex P2, #1012).

That hole was measured rather than argued about, and closing it was DECLINED on
the numbers. Four candidate enumerators were built and scored BLIND to
gate-composition — which is mandatory, because the 34 registered surfaces are
gate-composing by definition and a new ungated one is not, so an enumerator
allowed to key on the helper name scores 34/34 while proving nothing (#1003's
circular census). Measured over ``adapters/persistence/``:

* **execution-keyed** ("every read method"): 491 scopes, **25/34**. The misses
  are structural — composition and execution are different units. Four
  ``build_*_query`` functions RETURN Cypher for another method to execute; two
  surfaces are module-level; two delegate execution onward.
* **authoring-keyed** (a scope containing a Cypher-leading-clause literal):
  720 scopes, **31/34**, residual 689. Hand-classified sample of 24: **3 could
  project curriculum identity — 12.5% precision.** Forced classification would
  grow the registry from 34 to ~723 to admit ~86 real candidates. Following the
  three up individually found **zero live leaks**: one has no production caller
  at all, one filters curriculum on ``user_uid`` — a property 0 of 123 live Kus
  carry, so it returns nothing on every call — and the third was
  could-in-principle. Both real defects were spawned separately; neither is a
  publication leak. So the hole is LATENT rather than active, which is the
  strongest argument against gating on it and the reason the residual is
  recorded here instead.
* **exclusion-narrowed** (exempt a scope that provably binds no
  ``:Entity``-family label): 811 scopes, **31/34 before AND after** — the
  narrowing removed under 10% of scopes and moved the false-negative score by
  ZERO, so the control cannot price the second Cypher approximation it adds.
* **layered union**: 857 scopes, 32/34, and not blind.

**Three of the 34 turned out to be defects in the CONTROL, not in the
candidates.** Two are keyed in coordinates that exist only because a gate is
composed there — ``<module>:_ZONE_PUBLICATION_CLAUSE`` names the variable
RECEIVING the clause, while the Cypher lives in ``_ZONE_QUERY_TEMPLATE``; same
shape for ``<module>:_KNOWLEDGE_HEALTH_PARAMS``. No blind enumerator can name
those, and both blind candidates DID find the authoring sibling in each file, so
a future pass must match ``<module>:`` entries at MODULE granularity. The third
was a misclassification, fixed here: the by-UID read is ANCHORED, not a
discovery surface at all. Corrected, authoring-keyed enumeration passes the
false-negative control outright — **it is the false-POSITIVE cost that
disqualifies it**, and an advisory ratchet inherits that cost as a 7-in-8 noise
rate, which turns the exemption into a reflex (a suppressor that fails silent is
worse than a stated residual — #876, #868).

The runtime alternatives were priced too: only **1 of 123** integration test
files seeds ``publication_state`` at all, so a seam-wide output assertion is
vacuous across the other 122 without a session-scoped draft corpus. And moving
the chokepoint into a builder is **672 scopes / ~22,000 LOC / 73 files** to
cover the 34 that need it, on a tree where 0 of 34 obtain their Cypher from a
builder and 31 hand-author it in place — it would have caught NONE of the 21
surfaces #1008 gated.

So the honest claim stays the narrow one: this file keeps the CLASSIFIED set
honest, and asserts that a classified gate is not silently switched off. It does
not discover new surfaces, and the residual above is stated rather than papered
over.

Usage:
    uv run python scripts/audit_publication_gate.py           # CI gate
    uv run python scripts/audit_publication_gate.py --verbose # list every surface
    uv run python scripts/audit_publication_gate.py --json

Exit codes: 0 = registry complete, 1 = unregistered surface, stale entry, a GATED
surface with the gate disabled, an undecidable gate kwarg, or a file under the
scan directory that does not parse.
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
    Disposition,
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


GATE_KWARG = "apply_publication_gate"
"""The kwarg that turns a composed gate OFF.

Present on ``build_knowledge_read_clause`` and
``build_search_visibility_clause``, defaulting True so a new read is gated by
construction. ``build_publication_clause`` has no such switch — it IS the
predicate.
"""


@dataclass(frozen=True)
class Found:
    """A surface discovered in the tree that composes a gate helper."""

    module: str
    qualname: str
    lineno: int
    helpers: tuple[str, ...]
    gate_off: bool = False
    """True when a call here passes ``apply_publication_gate=False``.

    Keying on the CALL alone answers "is this surface classified?" but not "is
    the gate it composes actually ON". Those came apart in practice: the by-UID
    read composes the helper and switches the predicate off, and it sat in the
    GATED set for two PRs because the audit could not tell the difference. A
    one-word change from True to False on any GATED surface is a security
    regression the output invariant catches only for the surfaces it can
    measure — for the thirteen listed UNMEASURABLE it was caught by nothing.
    """

    gate_undecidable: bool = False
    """True when the kwarg is passed a non-literal (a name, a call, a ternary).

    Reported as a failure rather than assumed either way: guessing True here
    fails OPEN on exactly the surface whose gate is hardest to read, and this
    audit's whole claim is that it only asserts what is exactly decidable from
    the AST. Nothing in the tree does this today.
    """

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


def _display_path(path: Path) -> str:
    """``path`` relative to the app root, or absolute when it lies outside it.

    Same tolerance as ``_module_name``, for the same reason: the scanner is
    exercised against temporary directories, and ``relative_to`` raises rather
    than degrading. Reporting an unparseable file must not itself crash on the
    path it is trying to name.
    """
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


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


def _gate_state(node: ast.Call) -> tuple[bool, bool]:
    """``(gate_off, undecidable)`` for one gate-helper call.

    Absent kwarg means the default, which is ON — that is the whole point of it
    defaulting True. A literal ``False`` is off. Anything else is undecidable
    and says so rather than guessing.
    """
    for kw in node.keywords:
        if kw.arg != GATE_KWARG:
            continue
        value = kw.value
        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
            return (value.value is False, False)
        return (False, True)
    return (False, False)


MODULE_SCOPE = "<module>"
"""Qualname PREFIX for a gate composed outside any function.

Always suffixed with the assignment it binds (``<module>:_ZONE_QUERY_PARAMS``),
never used bare. A file can hold more than one module-level composition —
``curriculum_backends`` already has one — and collapsing them under a single
``<module>`` key would merge a NEW ungated-then-gated surface into an
already-registered entry, so it would pass the completeness audit without ever
receiving its own disposition or output coverage (Codex P2, #1012).

Not a curiosity: ``zpd_backend`` builds ``_ZONE_QUERY`` at import time by
substituting a sentinel, so its gate is composed by a module-level assignment.
An earlier revision of this scanner only descended into functions and reported
that file as having no surfaces at all — the instrument was blind to the purest
discovery surface in the tree, which is the exact failure mode #1008's census
had twice over.
"""


def _assignment_name(node: ast.AST) -> str | None:
    """The name an assignment binds, for identifying a module-level composition."""
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return None
    for target in targets:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Tuple):
            names = [e.id for e in target.elts if isinstance(e, ast.Name)]
            if names:
                return names[0]
    return None


def scan_file(path: Path) -> list[Found]:
    """Every surface in ``path`` that composes a gate helper, with its qualname.

    Attributes each call to its nearest enclosing function, or to
    ``<module>`` when there is none. Walks with an explicit scope stack rather
    than ``ast.walk``, which hands out nodes with no parent context — a nested
    def would otherwise be attributed to its enclosing class, and a module-level
    composition to nothing at all.
    """
    # Deliberately NOT guarded. An earlier revision returned [] on SyntaxError,
    # which meant an unparseable file contributed zero surfaces while the audit
    # still printed a confident total and exited 0 — an instrument whose failure
    # reads as a clean result (the class #883 was entirely made of). Let it
    # propagate; scan_tree names the file and main() fails the build.
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    module = _module_name(path)
    # qualname -> (first line seen, helper names, gate_off, gate_undecidable)
    hits: dict[str, tuple[int, set[str], bool, bool]] = {}

    def record(qualname: str, lineno: int, helper: str, off: bool, unknown: bool) -> None:
        line, helpers, was_off, was_unknown = hits.get(qualname, (lineno, set(), False, False))
        helpers.add(helper)
        # OR across the scope's calls: one disabled composition is enough to
        # make the surface's gate not-on, and a surface may compose more than
        # one helper (the KU->path surfaces gate two aliases).
        hits[qualname] = (min(line, lineno), helpers, was_off or off, was_unknown or unknown)

    def visit(node: ast.AST, stack: tuple[str, ...], owner: str) -> None:
        """``stack`` is the qualname path; ``owner`` is the enclosing function's."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, (*stack, child.name), owner)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = (*stack, child.name)
                visit(child, inner, ".".join(inner))
            else:
                scope = owner
                if owner.startswith(MODULE_SCOPE) and (name := _assignment_name(child)):
                    # Outside any function, the assignment IS the surface's identity.
                    scope = f"{MODULE_SCOPE}:{'.'.join((*stack, name))}"
                if isinstance(child, ast.Call) and (helper := _called_helper(child)):
                    off, unknown = _gate_state(child)
                    record(scope, child.lineno, helper, off, unknown)
                visit(child, stack, scope)

    visit(tree, (), MODULE_SCOPE)
    return [
        Found(module, qualname, line, tuple(sorted(helpers)), off, unknown)
        for qualname, (line, helpers, off, unknown) in sorted(hits.items())
    ]


HELPER_DEFINITIONS = frozenset(
    {
        ("adapters.persistence.neo4j.query.cypher.crud_queries", "build_knowledge_read_clause"),
        ("adapters.persistence.neo4j.query.cypher.crud_queries", "build_search_visibility_clause"),
    }
)
"""The helpers DELEGATING to each other, which is not a surface with an audience.

Excluded by qualname rather than by file. An earlier revision skipped
``crud_queries.py`` wholesale, which also hid four real query builders that
compose a gate and return executable Cypher — ``build_text_search_query``,
``build_graph_aware_search_query``, ``build_array_any_match_query`` and
``build_distinct_values_query``. Removing a gate from any of them would have
left both this audit and the output-invariant coverage green (Codex P2, #1012).
A file-level suppressor fails silent; a qualname-level one states exactly what
it hides.
"""


class UnparseableSourceError(Exception):
    """A file under the scan directory could not be parsed.

    Raised rather than skipped: the population this audit compares against the
    registry is only as complete as the set of files it managed to read, so a
    parse failure must fail the build instead of quietly shrinking the
    denominator.
    """


def scan_tree() -> list[Found]:
    """Every gate-composing surface under ``adapters/persistence/``.

    Raises:
        UnparseableSourceError: a ``.py`` file under the scan directory is not valid
            Python, so the surface population would be silently incomplete.
    """
    surfaces: list[Found] = []
    for path in sorted(SCAN_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            found = scan_file(path)
        except SyntaxError as exc:
            raise UnparseableSourceError(
                f"{_display_path(path)} is not parseable ({exc}). The surface "
                f"population would be incomplete, so this audit's completeness "
                f"claim cannot be made."
            ) from exc
        surfaces.extend(f for f in found if f.key not in HELPER_DEFINITIONS)
    return surfaces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="list every surface found")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        found = scan_tree()
    except UnparseableSourceError as exc:
        print(f"UNPARSEABLE   {exc}", file=sys.stderr)
        return 1

    registered = registry_keys()
    found_keys = {f.key for f in found}
    dispositions = {(s.module, s.qualname): s.disposition for s in SURFACES}

    unregistered = sorted((f for f in found if f.key not in registered), key=Found.sort_key)
    stale = sorted(registered - found_keys)

    # A GATED surface that switches the predicate off is a contradiction in one
    # word, and it is exactly decidable — so this audit can assert it even
    # though it refuses to judge whether a gate is placed CORRECTLY. The two
    # sanctioned opt-outs in the tree carry carve-out dispositions (the by-UID
    # read is ANCHORED, the hub-score writer is WRITER); a third would have to
    # say which it is.
    gate_off = sorted(
        (f for f in found if f.gate_off and dispositions.get(f.key) is Disposition.GATED),
        key=Found.sort_key,
    )
    undecidable = sorted((f for f in found if f.gate_undecidable), key=Found.sort_key)

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
                    "gate_off": [
                        {"module": f.module, "qualname": f.qualname, "line": f.lineno}
                        for f in gate_off
                    ],
                    "gate_undecidable": [
                        {"module": f.module, "qualname": f.qualname, "line": f.lineno}
                        for f in undecidable
                    ],
                },
                indent=2,
            )
        )
        return 1 if (unregistered or stale or gate_off or undecidable) else 0

    if args.verbose:
        print(f"Gate-composing surfaces in {SCAN_DIR.relative_to(ROOT)}: {len(found)}\n")
        for f in found:
            mark = " " if f.key in registered else "!"
            state = "  gate=OFF" if f.gate_off else ""
            disposition = dispositions.get(f.key)
            label = f"  <{disposition.value}>" if disposition else ""
            print(
                f" {mark} {f.module}:{f.lineno}  {f.qualname}  "
                f"[{', '.join(f.helpers)}]{label}{state}"
            )
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

    for f in gate_off:
        print(
            f"GATE OFF      {f.module}:{f.lineno}  {f.qualname}\n"
            f"              classified GATED, but composes {', '.join(f.helpers)} with\n"
            f"              {GATE_KWARG}=False — so it withholds nothing. Either the\n"
            f"              gate was disabled (a security change — say so) or the surface is\n"
            f"              a carve-out and needs the disposition that says which:\n"
            f"              ANCHORED (by-UID), CONTAINMENT, USER_STATE or WRITER.",
            file=sys.stderr,
        )

    for f in undecidable:
        print(
            f"UNDECIDABLE   {f.module}:{f.lineno}  {f.qualname}\n"
            f"              passes {GATE_KWARG} a non-literal, so whether the gate is on\n"
            f"              cannot be read from the AST. Pass a literal True/False, or split\n"
            f"              the call, so this stays exactly decidable rather than assumed.",
            file=sys.stderr,
        )

    if unregistered or stale or gate_off or undecidable:
        print(
            f"\n{len(unregistered)} unregistered, {len(stale)} stale, "
            f"{len(gate_off)} gate-off, {len(undecidable)} undecidable "
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
