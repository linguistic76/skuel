"""Unit tests for the shared graph-vocabulary gate and scanner.

``cypher_vocabulary`` is read by BOTH graph-vocabulary rules — CYP011 (`.cypher`
files, `cypher_linter.py`) and SKUEL030 (`.py` strings under
`adapters/persistence/`, `lint_skuel.py`). ``scan_names`` returns ``[]`` outright
for a fragment the gate rejects, so a gate that is too narrow makes both rules
report clean on Cypher they never looked at.

Rule-level behaviour is covered in ``test_cypher_linter.py`` /
``test_lint_skuel.py``; these tests pin the two primitives themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cypher_vocabulary import (  # type: ignore[import-not-found]
    INTERPOLATION_SENTINEL,
    NameKind,
    looks_like_cypher,
    scan_names,
)

# ============================================================================
# The gate — anchor 2 (clause keyword at the head of the fragment)
# ============================================================================


class TestLeadingClauseAnchor:
    """Statement families the paren/sigil anchor is structurally blind to.

    Each of these carries real graph vocabulary and was gated OUT before the
    head anchor existed, so both CYP011 and SKUEL030 scanned nothing.
    """

    @pytest.mark.parametrize(
        "fragment",
        [
            # RETURN-led pattern comprehension — a real relationship type with no
            # paren adjacent to the clause keyword. The canonical missed case.
            "RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "WITH [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            # A function call sits between `=` and the pattern, so the
            # `MATCH x = (` arm cannot see it.
            "MATCH path = shortestPath((a:Entity)-[:ENABLES_KNOWLEDGE*]-(b:Ku))",
            # `UNWIND $` only matches a parameter; a literal list is just as real.
            "UNWIND [1, 2, 3] AS x",
            # `CALL db.` only matches the db namespace.
            "CALL apoc.version() YIELD version RETURN version",
            "SHOW INDEXES YIELD name, labelsOrTypes",
            "SHOW CONSTRAINTS",
            "PROFILE RETURN 1 AS ping",
            "EXPLAIN RETURN 1 AS ping",
            "DETACH DELETE n",
            "REMOVE n.content",
            "SET n.title = $title",
            "DROP INDEX entity_uid_idx IF EXISTS",
            "LOAD CSV FROM $url AS row",
            "RETURN 1 AS ping",
        ],
    )
    def test_admits_statement_head_clauses(self, fragment: str) -> None:
        assert looks_like_cypher(fragment) is True

    def test_skips_leading_comment_lines(self) -> None:
        """A planner-hint comment must not hide the first real clause."""
        fragment = "// index hint: entity_uid_idx\n\nRETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs"
        assert looks_like_cypher(fragment) is True

    @pytest.mark.parametrize(
        "fragment",
        [
            "/* hint */\nRETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "/* hint */ RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "/* multi\n   line\n   hint */\nRETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
        ],
    )
    def test_skips_leading_block_comments(self, fragment: str) -> None:
        """`cypher_linter` masks these for `.cypher`; SKUEL030 does not.

        SKUEL030 hands an AST string literal over verbatim, so a `/* ... */`
        opener would reopen exactly the blind spot the head anchor closes
        (Codex P2 on #831).
        """
        assert looks_like_cypher(fragment) is True

    def test_block_comment_alone_is_not_cypher(self) -> None:
        """Stripping the comment must not invent a clause that was never there."""
        assert looks_like_cypher("/* just a note about MATCH and RETURN */") is False

    @pytest.mark.parametrize(
        "fragment",
        [
            # Head position is the signal — naming a clause mid-sentence is prose.
            "cascade DETACH DELETE (default False)",
            "Removes an entity and RETURN s the deleted count",
            "Returns the SET of labels for a node",
            # Whitespace + operand rules out bare verbs and header names.
            "DELETE",
            "SET-COOKIE: session=abc",
            "MATCH",
            # A word that merely starts with a clause name.
            "RETURNS a mapping of uid to title",
            "CREATED at the ingestion boundary",
            "WITHOUT a registered owner",
            "USES_KU is the composition edge",
            # Uppercase is required; lowercase English would flood the rules.
            "return 1 as ping",
            "set the label on the node",
        ],
    )
    def test_rejects_prose(self, fragment: str) -> None:
        assert looks_like_cypher(fragment) is False

    def test_paren_anchor_still_admits_mid_fragment_cypher(self) -> None:
        """Anchor 1 is not replaced — it catches Cypher that does not LEAD."""
        fragment = "some prefix ... MATCH (n:Ku) RETURN n"
        assert looks_like_cypher(fragment) is True


# ============================================================================
# The scanner — labels attached/detached by SET and REMOVE
# ============================================================================


def _labels(fragment: str) -> list[str]:
    return [n.value for n in scan_names(fragment) if n.kind is NameKind.LABEL]


class TestLabelMutationPosition:
    """`SET n:Label` / `REMOVE n:Label` never appear in pattern position.

    Neo4j writes the label it is given, so a typo here is strictly worse than a
    typo'd read: it persists a label nothing will ever match.
    """

    def test_set_label_is_scanned(self) -> None:
        assert _labels("MATCH (n) SET n:Typo RETURN n") == ["Typo"]

    def test_remove_label_is_scanned(self) -> None:
        assert _labels("MATCH (n) REMOVE n:Article RETURN n") == ["Article"]

    def test_multi_label_set_scans_each_part(self) -> None:
        assert _labels("MATCH (n) SET n:Entity:Ku RETURN n") == ["Entity", "Ku"]

    def test_on_create_set_is_scanned(self) -> None:
        """The MERGE upsert form — `SET` is not at the head of the clause."""
        assert _labels("MERGE (n {uid: $uid}) ON CREATE SET n:Typo RETURN n") == ["Typo"]

    def test_property_set_is_not_a_label(self) -> None:
        """`SET n.prop = $x` is a dot, not a colon — nothing to validate."""
        assert _labels("MATCH (n) SET n.title = $title RETURN n") == []

    def test_map_assignment_is_not_a_label(self) -> None:
        assert _labels("MATCH (n) SET n += $props RETURN n") == []

    def test_interpolated_label_is_skipped(self) -> None:
        """A runtime-composed label has no static name to check."""
        fragment = f"MATCH (n) SET n:{INTERPOLATION_SENTINEL} RETURN n"
        assert _labels(fragment) == []
