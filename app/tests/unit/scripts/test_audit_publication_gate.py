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

import pytest

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
    assert f"{MODULE_SCOPE}:_CLAUSE" in found, (
        "a gate composed outside any function must still be attributed — this "
        "is how the ZPD zone query is built"
    )


def test_two_module_level_compositions_get_distinct_keys(tmp_path: Path) -> None:
    """Collapsing them would let a NEW one ride in on an existing registration.

    curriculum_backends already holds one module-level composition, so a second
    added there would merge into the same key and pass the completeness audit
    without its own disposition or output coverage (Codex P2, #1012).
    """
    found = _scan(
        tmp_path,
        "FIRST = build_publication_clause('a')[0]\nSECOND = build_publication_clause('b')[0]\n",
    )
    assert f"{MODULE_SCOPE}:FIRST" in found
    assert f"{MODULE_SCOPE}:SECOND" in found
    assert MODULE_SCOPE not in found, "the bare prefix must never be used as a key"


def test_finds_a_class_body_composition(tmp_path: Path) -> None:
    """A class-level assignment is not inside a function either."""
    found = _scan(
        tmp_path,
        "class Backend:\n    CLAUSE = build_publication_clause('n')[0]\n",
    )
    assert f"{MODULE_SCOPE}:Backend.CLAUSE" in found


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


def test_unparseable_file_is_fatal_not_skipped(tmp_path: Path) -> None:
    """Reversed deliberately. An earlier revision returned ``{}`` here, reasoning
    that a scanner crashing on bad input "fails the build for the wrong reason".

    For a COMPLETENESS audit it is the right reason: the population this file
    compares against the registry is only as complete as the set of files it
    managed to read, so swallowing the error shrinks the denominator while the
    audit still prints a confident total and exits 0 — an instrument whose
    failure reads as a clean result, which is the whole of #883. Nor is the
    build break spurious: an unparseable module under ``adapters/persistence/``
    already fails ruff, mypy, and every test that imports it.
    """
    with pytest.raises(SyntaxError):
        _scan(tmp_path, "def broken(:\n")


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


def test_gate_state_reads_the_disabling_kwarg(tmp_path: Path) -> None:
    """``apply_publication_gate=False`` composes the helper and withholds nothing.

    Keying on the CALL cannot see this, and the two came apart in practice: the
    by-UID read composed the helper with the gate off and sat in the GATED set
    for two PRs. Absent kwarg means the default, which is ON — that is why it
    defaults True.
    """
    off = _scan(
        tmp_path,
        "class B:\n"
        "    def read(self):\n"
        "        return build_knowledge_read_clause('ku', apply_publication_gate=False)\n",
    )
    assert off["B.read"].gate_off is True
    assert off["B.read"].gate_undecidable is False

    on = _scan(
        tmp_path,
        "class B:\n"
        "    def read(self):\n"
        "        return build_knowledge_read_clause('ku', apply_publication_gate=True)\n",
    )
    assert on["B.read"].gate_off is False

    default = _scan(
        tmp_path,
        "class B:\n    def read(self):\n        return build_knowledge_read_clause('ku')\n",
    )
    assert default["B.read"].gate_off is False, "an absent kwarg is the default, which is ON"


def test_a_non_literal_gate_kwarg_is_undecidable_not_assumed(tmp_path: Path) -> None:
    """Guessing True here would fail OPEN on the hardest surface to read.

    The audit's whole claim is that it asserts only what the AST decides
    exactly, so a name, call or ternary in this position is reported rather
    than resolved. Nothing in the tree does this today; the check exists so
    that introducing it cannot pass silently.
    """
    found = _scan(
        tmp_path,
        "class B:\n"
        "    def read(self, flag):\n"
        "        return build_search_visibility_clause(v, apply_publication_gate=flag)\n",
    )
    assert found["B.read"].gate_undecidable is True
    assert found["B.read"].gate_off is False


def test_one_disabled_call_marks_the_whole_scope(tmp_path: Path) -> None:
    """A surface may compose more than one helper — the KU->path surfaces gate
    two aliases. The flags OR across the scope, so a second, gated call cannot
    mask a disabled first one."""
    found = _scan(
        tmp_path,
        "class B:\n"
        "    def read(self):\n"
        "        a = build_publication_clause('lp')\n"
        "        b = build_knowledge_read_clause('ku', apply_publication_gate=False)\n"
        "        return a, b\n",
    )
    assert found["B.read"].gate_off is True


def test_scan_tree_names_the_unparseable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``scan_tree`` turns the raw SyntaxError into a message naming the file.

    Scanned against a redirected SCAN_DIR rather than by planting a broken
    module in the real tree — a unit test that writes into
    ``adapters/persistence/`` breaks every other test in the session if it dies
    before its cleanup runs.
    """
    import audit_publication_gate as audit  # type: ignore[import-not-found]

    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr(audit, "SCAN_DIR", tmp_path)

    with pytest.raises(audit.UnparseableSourceError, match="not parseable"):
        audit.scan_tree()


def test_no_gated_surface_disables_its_own_gate() -> None:
    """The end-to-end form of the check, against the shipped tree.

    The two sanctioned opt-outs carry carve-out dispositions: the by-UID read is
    ANCHORED, the hub-score writer is WRITER. A third would have to say which.
    """
    from audit_publication_gate import scan_tree  # type: ignore[import-not-found]
    from publication_gate_registry import (  # type: ignore[import-not-found]
        SURFACES,
        Disposition,
    )

    dispositions = {(s.module, s.qualname): s.disposition for s in SURFACES}
    offenders = [
        f.key for f in scan_tree() if f.gate_off and dispositions.get(f.key) is Disposition.GATED
    ]
    assert offenders == [], (
        f"GATED surfaces composing a helper with apply_publication_gate=False, "
        f"so they withhold nothing: {sorted(offenders)}"
    )

    undecidable = [f.key for f in scan_tree() if f.gate_undecidable]
    assert undecidable == [], f"gate state not decidable from the AST: {sorted(undecidable)}"


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
