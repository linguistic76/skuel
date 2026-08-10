"""Tests for the publication-gate registry audit's SCANNER.

The scanner is the part most likely to be wrong. An earlier revision descended
only into functions and therefore reported ``zpd_backend`` — which composes its
gate in a module-level assignment, because ``_ZONE_QUERY`` substitutes a
sentinel at import time — as having no surfaces at all. It would have passed
a green CI over the purest discovery surface in the tree.

That is the same failure mode as #1008's census twice over, and #872's rule
applies: score the instrument, not just its output. Each case below is a shape
that has actually appeared in this tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py, and this directory is itself named `scripts`,
# so it shadows the real package under pytest's prepend import mode.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from audit_publication_gate import (  # type: ignore[import-not-found]
    MODULE_SCOPE,
    Found,
    scan_file,
)


def _scan(tmp_path: Path, source: str) -> dict[str, Found]:
    path = tmp_path / "adapters" / "persistence" / "probe.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return {f.qualname: f for f in scan_file(path)}


def test_finds_a_method_level_composition(tmp_path: Path) -> None:
    found = _scan(
        tmp_path,
        "class Backend:\n"
        "    async def list_things(self):\n"
        "        published, params = build_publication_clause('n')\n"
        "        return published, params\n",
    )
    assert "Backend.list_things" in found
    assert found["Backend.list_things"].helpers == ("build_publication_clause",)


def test_finds_a_module_level_composition(tmp_path: Path) -> None:
    """The zpd_backend shape — the blind spot that motivated this test."""
    found = _scan(tmp_path, "_CLAUSE, _PARAMS = build_publication_clause('cand')\n")
    assert MODULE_SCOPE in found, (
        "a gate composed outside any function must still be attributed — this "
        "is how the ZPD zone query is built"
    )


def test_finds_a_class_body_composition(tmp_path: Path) -> None:
    """A class-level assignment is not inside a function either."""
    found = _scan(
        tmp_path,
        "class Backend:\n    CLAUSE = build_publication_clause('n')[0]\n",
    )
    assert MODULE_SCOPE in found


def test_attributes_a_nested_def_to_itself(tmp_path: Path) -> None:
    """``ast.walk`` would credit the enclosing function; the scope stack must not."""
    found = _scan(
        tmp_path,
        "class Backend:\n"
        "    def outer(self):\n"
        "        def inner():\n"
        "            return build_publication_clause('n')\n"
        "        return inner\n",
    )
    assert "Backend.outer.inner" in found
    assert "Backend.outer" not in found


def test_finds_an_attribute_style_call(tmp_path: Path) -> None:
    """``crud_queries.build_publication_clause(...)`` is the same composition."""
    found = _scan(
        tmp_path,
        "def build():\n    return crud_queries.build_publication_clause('n')\n",
    )
    assert "build" in found


def test_collects_every_helper_a_surface_composes(tmp_path: Path) -> None:
    found = _scan(
        tmp_path,
        "def build():\n"
        "    a = build_publication_clause('n')\n"
        "    b = build_knowledge_read_clause('ku')\n"
        "    return a, b\n",
    )
    assert found["build"].helpers == (
        "build_knowledge_read_clause",
        "build_publication_clause",
    )


def test_ignores_a_function_with_no_gate(tmp_path: Path) -> None:
    found = _scan(tmp_path, "def plain():\n    return 'MATCH (n:Entity) RETURN n'\n")
    assert found == {}


def test_unparseable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    """A scanner that crashes on bad input fails the build for the wrong reason."""
    assert _scan(tmp_path, "def broken(:\n") == {}


def test_crud_queries_builders_are_scanned_but_helper_defs_are_not() -> None:
    """The suppressor is qualname-scoped, not file-scoped (Codex P2, #1012).

    Skipping ``crud_queries.py`` wholesale also hid four real query builders
    that compose a gate and return executable Cypher. A removed gate in any of
    them would have left both this audit and the output-invariant coverage
    green — a suppressor that fails silent, which is the class #876 is about.
    """
    from audit_publication_gate import scan_tree  # type: ignore[import-not-found]

    module = "adapters.persistence.neo4j.query.cypher.crud_queries"
    scanned = {f.qualname for f in scan_tree() if f.module == module}

    for builder in (
        "build_text_search_query",
        "build_graph_aware_search_query",
        "build_array_any_match_query",
        "build_distinct_values_query",
    ):
        assert builder in scanned, f"{builder} composes a gate and must be classified"

    for helper in ("build_knowledge_read_clause", "build_search_visibility_clause"):
        assert helper not in scanned, (
            f"{helper} is a helper DEFINITION delegating to another helper, not "
            f"a surface with an audience"
        )


def test_registry_audit_passes_against_the_tree() -> None:
    """The end-to-end claim: the shipped registry matches the shipped code.

    Fails loudly when someone adds a gate-composing surface without classifying
    it — which is the entire point of the mechanism.
    """
    from audit_publication_gate import scan_tree  # type: ignore[import-not-found]
    from publication_gate_registry import registry_keys  # type: ignore[import-not-found]

    found = {f.key for f in scan_tree()}
    registered = registry_keys()
    assert found - registered == set(), (
        f"unclassified gate-composing surfaces: {sorted(found - registered)}"
    )
    assert registered - found == set(), (
        f"registry entries that no longer compose a gate: {sorted(registered - found)}"
    )
