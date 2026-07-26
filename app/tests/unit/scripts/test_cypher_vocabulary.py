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
            "RETURN\n  [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "WITH\n  [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "MATCH\n  path = shortestPath((a:Entity)-[:X]-(b))",
        ],
    )
    def test_operand_may_wrap_to_the_next_line(self, fragment: str) -> None:
        """Cypher wraps freely; a clause alone on line one is still Cypher.

        Head position and uppercase carry the prose guard — requiring the
        operand on the SAME line only ever added a wrapping restriction
        (Codex P2 on #831).
        """
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

    def test_ignore_case_drops_the_uppercase_requirement(self) -> None:
        """Prose risk is a property of the CALLER, not of Cypher.

        A `.cypher` file is Cypher by declaration and has no prose to be
        confused with, so callers on that side opt out (Codex P2 on #831).
        Callers reading arbitrary Python string literals must not.
        """
        assert looks_like_cypher("match (n:Typo) return n") is False
        assert looks_like_cypher("match (n:Typo) return n", ignore_case=True) is True
        assert [n.value for n in scan_names("match (n:Typo) return n", ignore_case=True)] == [
            "Typo"
        ]

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            # Mutation position — head keyword AND the terminator walk.
            ("match (n) set n:Typo return n", ["Typo"]),
            ("MATCH (n) SET n:Typo return n", ["Typo"]),
            ("match (n) set n.a = 1, n:Typo return n", ["Typo"]),
            # Label-predicate position.
            ("match (n) where n:Typo return n", ["Typo"]),
            # Type-predicate position.
            ("match ()-[r]->() where type(r) = 'BAD_EDGE' return r", ["BAD_EDGE"]),
        ],
    )
    def test_ignore_case_reaches_every_scanner(self, query: str, expected: list[str]) -> None:
        """A half-threaded flag is a trap.

        `ignore_case` was first wired into the GATE alone, so CYP011 admitted a
        lowercase statement and then scanned it with case-sensitive scanners —
        `set n:Bogus` still reported clean (Codex P2 on #831).
        """
        assert [n.value for n in scan_names(query, ignore_case=True)] == expected

    def test_ignore_case_does_not_relax_the_name_shape(self) -> None:
        """Only the KEYWORDS relax. PascalCase is what tells a label from a map key."""
        assert [
            n.value for n in scan_names("match (n) where n:content return n", ignore_case=True)
        ] == []

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

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) SET n :Typo RETURN n",
            "MATCH (n) SET n: Typo RETURN n",
            "MATCH (n) REMOVE n : Typo RETURN n",
        ],
    )
    def test_whitespace_around_the_colon_is_allowed(self, query: str) -> None:
        """The pattern-position scanners already tolerate it (Codex P2 on #831)."""
        assert _labels(query) == ["Typo"]

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

    def test_comma_separated_items_are_each_scanned(self) -> None:
        """`SET a:X, b:Y` is two label writes.

        Anchoring on the item immediately after the clause keyword validated
        only the first and let the rest through (Codex P2 on #831).
        """
        assert _labels("MATCH (n) SET lp1:LearningPath, lp2:Typo RETURN lp1") == [
            "LearningPath",
            "Typo",
        ]
        assert _labels("MATCH (n) REMOVE a:Article, b:Lesson RETURN a") == ["Article", "Lesson"]

    def test_label_write_mixed_with_property_write_is_scanned(self) -> None:
        """Cypher allows `SET n.prop = $x, n:Label` — each item judged alone."""
        assert _labels("MATCH (n) SET n.title = $t, n:Typo RETURN n") == ["Typo"]

    def test_map_literal_is_not_a_label_list(self) -> None:
        """`SET n = {a:Foo, b:Bar}` splits into items that are not `var:Label`."""
        assert _labels("MATCH (n) SET n = {a:Foo, b:Bar} RETURN n") == []

    def test_clause_word_inside_a_property_value_does_not_end_the_region(self) -> None:
        """The mutation scanner alone must know where the clause ENDS.

        An uppercase clause word inside a quoted property value closed the
        region early and hid every item after it (Codex P2 on #831).
        """
        assert _labels("MATCH (n) SET n.note = 'RETURN later', n:Typo RETURN n") == ["Typo"]
        assert _labels("MATCH (n) SET n.note = 'a WITH b', n:Typo RETURN n") == ["Typo"]

    def test_a_mutation_written_inside_a_string_is_not_a_mutation(self) -> None:
        """Falls out of the same quote-blindness — and is the right answer."""
        assert _labels("RETURN 'SET n:Bogus' AS example") == []

    def test_unterminated_string_swallows_to_the_end(self) -> None:
        """Fail closed: no clause boundary can be trusted after an open quote."""
        assert _labels("MATCH (n) SET n.s = 'unterminated") == []

    @pytest.mark.parametrize(
        "tail",
        [
            "FINISH",  # Neo4j's row-less query ending
            "OPTIONAL MATCH (m) RETURN m",
            "ORDER BY n.x",
            "UNION MATCH (m) RETURN m",
            "RETURN n",
            "",  # clause runs to the end of the fragment
        ],
    )
    def test_clause_region_ends_at_any_following_clause(self, tail: str) -> None:
        """The terminator set is DERIVED from the clause list, not hand-written.

        A hand-written one was missing both `FINISH` and `OPTIONAL` on its first
        outing (Codex P2 on #831) — the same case-by-case failure the gate's two
        anchors exist to end.
        """
        assert _labels(f"MATCH (n) SET n:Typo {tail}".strip()) == ["Typo"]

    def test_uppercase_variable_is_accepted(self) -> None:
        """Cypher variables are case-neutral — `SET N:Ku` is as valid as `n`."""
        assert _labels("MATCH (N) SET N:Typo RETURN N") == ["Typo"]
        assert _labels("MATCH (n) REMOVE Node1:Typo RETURN n") == ["Typo"]

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) SET n:Typo;",  # statement terminator
            "MATCH (n) FOREACH (x IN xs | SET n:Typo)",  # closing paren
            "CALL { MATCH (n) SET n:Typo }",  # subquery brace
            "CALL (n) { SET n:Typo }",  # scoped-subquery form
        ],
    )
    def test_clause_closed_by_punctuation_is_scanned(self, query: str) -> None:
        """A clause can end in punctuation rather than a keyword.

        Each of these failed the item full-match on its trailing character
        alone — the same root cause as the missing `FINISH` terminator (Codex P2
        on #831 named the semicolon).
        """
        assert _labels(query) == ["Typo"]

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) SET n = {a:Foo, b:Bar} RETURN n",
            "MATCH (n) SET n = {a: {b: Foo}} RETURN n",
            "MATCH (n) SET n = point({x:1, y:2}) RETURN n",
        ],
    )
    def test_map_literals_stay_invisible(self, query: str) -> None:
        """Tolerating a trailing `}` is only safe because maps are blanked.

        `{a:Foo, b:Bar}` split on its INNER comma into `n = {a:Foo` and
        ` b:Bar}`, and the second half reads exactly like a label write.
        """
        assert _labels(query) == []

    def test_subquery_braces_are_transparent_but_maps_inside_are_not(self) -> None:
        """`CALL { ... }` is executable Cypher; a map literal in it is not."""
        assert _labels("CALL { MATCH (n) SET n = {a:Foo} SET n:Typo }") == ["Typo"]

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) SET n.ok = all(x IN $xs WHERE x > 0), n:Typo RETURN n",
            "MATCH (n) SET n.c = size([(a) WHERE a.x | a]), n:Typo RETURN n",
            "MATCH (n) SET n.p = coalesce(n.a, n.b), n:Typo RETURN n",
        ],
    )
    def test_keyword_nested_in_an_expression_does_not_end_the_region(self, query: str) -> None:
        """Depth is what a keyword-anywhere lookahead could not supply.

        `all(x IN $xs WHERE x > 0)` is a sub-expression, not a clause boundary,
        so every item after it went unscanned (Codex P2 on #831 — the sixth
        finding of this shape, and the reason the region is now walked with
        bracket depth instead of matched with a lookahead).
        """
        assert "Typo" in _labels(query)


# ============================================================================
# Comment masking
# ============================================================================


class TestCommentMasking:
    """A comment cannot execute, so vocabulary written in one is not real.

    Same reasoning that exempts docstrings. `cypher_linter` already masked
    comments out of `.cypher` files; SKUEL030 receives an AST string literal
    with nothing pre-masked, so the scanner has to do it itself.
    """

    @pytest.mark.parametrize(
        "fragment",
        [
            "/* retired (:Bogus) */ RETURN 1 AS ping",
            "MATCH (n:Ku) // retired (:Bogus)\nRETURN n",
            "MATCH (n:Ku)\n/* was [:BOGUS_EDGE] */\nRETURN n",
        ],
    )
    def test_vocabulary_in_comments_is_not_scanned(self, fragment: str) -> None:
        assert [n.value for n in scan_names(fragment) if n.value.startswith("Bogus")] == []
        assert "BOGUS_EDGE" not in [n.value for n in scan_names(fragment)]

    def test_comment_only_fragment_is_not_cypher(self) -> None:
        assert looks_like_cypher("/* a note about MATCH and RETURN */") is False
        assert looks_like_cypher("// MATCH (n:Bogus) RETURN n") is False

    def test_double_slash_inside_a_string_is_not_a_comment(self) -> None:
        """`'bolt://host'` must not blank the rest of the line."""
        fragment = "MATCH (n:Typo) WHERE n.uri = 'bolt://host' RETURN n"
        assert _labels(fragment) == ["Typo"]

    @pytest.mark.parametrize(
        "identifier",
        [
            "http://key",  # `//` inside an escaped property name
            "/* odd */",  # a block-comment opener inside one
            "a``b//c",  # a DOUBLED backtick — escapes, does not close
        ],
    )
    def test_comment_openers_inside_backtick_identifiers_are_not_comments(
        self, identifier: str
    ) -> None:
        """Masking a live clause away would make the rule silent.

        That is the exact failure this rule exists to prevent, so the masker
        has to track backtick-escaped identifiers as well as quoted strings
        (Codex P2 on #831).
        """
        fragment = f"MATCH (n:Task) WHERE n.`{identifier}` = $x RETURN [(a)-[:BAD_EDGE]->(b)]"
        assert "BAD_EDGE" in [n.value for n in scan_names(fragment)]

    def test_line_offsets_survive_masking(self) -> None:
        """Masking preserves length and newlines, so offsets stay truthful."""
        fragment = "/* header */\nMATCH (n:Typo)\nRETURN n"
        assert [(n.value, n.line_offset) for n in scan_names(fragment)] == [("Typo", 1)]


class TestBacktickEscapedVocabulary:
    """Pins a KNOWN LIMIT: escaped names are not scanned, in any position.

    Every name regex requires an identifier character straight after the `:`,
    so a backtick-escaped label or edge type has never been recovered — not on
    `main`, not before the string-blanking pass, not now. Verified against all
    three revisions rather than assumed (Codex P2 on #831 attributed it to
    `blank_strings`; it predates it and is uniform).

    Closing this means teaching all four positions at once. Patching it in one
    is exactly the case-by-case habit this module's gate design argues against.
    """

    @pytest.mark.parametrize(
        "fragment",
        [
            "MATCH (n:`Bogus`) RETURN n",
            "MATCH ()-[r:`BOGUS_EDGE`]->() RETURN r",
            "MATCH (n) SET n:`Bogus` RETURN n",
            "MATCH (n) REMOVE n:`Bogus` RETURN n",
        ],
    )
    def test_escaped_names_are_not_recovered(self, fragment: str) -> None:
        assert [n.value for n in scan_names(fragment) if "Bogus" in n.value.upper()] == []
