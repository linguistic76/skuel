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
    ScanIssue,
    looks_like_cypher,
    recording_scan_diagnostics,
    scan_names,
    scanning_fragment_at,
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
            # Cypher 25 / GQL create clause — carries `(n:Label)` like CREATE.
            "INSERT (n:Bogus)",
            "NODETACH DELETE n",
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
            "INSERTS a row into the audit table",
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

    def test_declared_cypher_bypasses_the_gate_entirely(self) -> None:
        """A caller holding text that IS Cypher should not consult the gate.

        The gate is calibrated for text that MIGHT be Cypher — Python string
        literals, where prose is a real risk. Applying it to a `.cypher` file
        only invented ways to discard real queries: lowercase Cypher, then
        `CYPHER runtime=slotted RETURN ...` (Codex P2 on #831, twice).

        Only the lowercase case is left here. The `CYPHER` preamble is now
        stripped by the gate itself, because SKUEL030 needed it on the Python
        side where no declaration exists — so the bypass is no longer what
        saves that one. `test_query_option_preamble_is_stripped_before_the_anchor`
        owns it now.
        """
        query = "match (n:Typo) return n"
        assert looks_like_cypher(query) is False
        assert scan_names(query, declared_cypher=True) != []

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
    def test_declared_cypher_reaches_every_scanner(self, query: str, expected: list[str]) -> None:
        """A half-threaded flag is a trap.

        The flag was first wired into the GATE alone, so CYP011 admitted a
        lowercase statement and then scanned it with case-sensitive scanners —
        `set n:Bogus` still reported clean (Codex P2 on #831).
        """
        assert [n.value for n in scan_names(query, declared_cypher=True)] == expected

    def test_declared_cypher_does_not_relax_the_name_shape(self) -> None:
        """Only the KEYWORDS relax. PascalCase is what tells a label from a map key."""
        assert [
            n.value for n in scan_names("match (n) where n:content return n", declared_cypher=True)
        ] == []

    def test_paren_anchor_still_admits_mid_fragment_cypher(self) -> None:
        """Anchor 1 is not replaced — it catches Cypher that does not LEAD."""
        fragment = "some prefix ... MATCH (n:Ku) RETURN n"
        assert looks_like_cypher(fragment) is True

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            # These two are the ones that actually misfired: an expression
            # variable SHAPED like vocabulary (PascalCase label, UPPER_SNAKE
            # type). A lowercase variable never matched the name shape anyway.
            ("MATCH (n:$(LabelExpr)) RETURN n", []),
            ("MATCH ()-[r:$(REL_TYPE)]->() RETURN r", []),
            ("MATCH (n:$(labelExpr)) RETURN n", []),
            ("MATCH ()-[r:$relParam]->() RETURN r", []),
            # The WHOLE operand is dynamic, not just the identifier next to the
            # `$`. Skipping only the adjacent one reported the nested names.
            ("MATCH (n:$(coalesce(Foo,Bogus))) RETURN n", []),
            ("MATCH ()-[r:$(coalesce(A_EDGE,B_EDGE))]->() RETURN r", []),
            # The `$any(...)` / `$all(...)` label-expression functions — same
            # span, one more shape the `$(`-vs-`$param` branch did not cover.
            ("MATCH (n:$any(LabelExpr)) RETURN n", []),
            ("MATCH (n:$all(coalesce(Foo,Bogus))) RETURN n", []),
            ("MATCH ()-[r:$any(REL_TYPE)]->() RETURN r", []),
            # A static sibling next to a dynamic one is still checked.
            ("MATCH (n:Typo:$(x)) RETURN n", ["Typo"]),
        ],
    )
    def test_dynamic_label_expressions_are_not_static_names(
        self, query: str, expected: list[str]
    ) -> None:
        """`$(labelExpr)` resolves at runtime — there is no name to validate.

        Reading identifier RUNS out of a pattern body (rather than whole
        colon-separated chunks) made the expression variable look like
        vocabulary and reported it unregistered (Codex P2 on #831).
        """
        assert [n.value for n in scan_names(query)] == expected

    @pytest.mark.parametrize(
        "query",
        [
            "CYPHER runtime=slotted RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "CYPHER 25 RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs",
            "CYPHER 5 runtime=pipelined RETURN [(a)-[:TYPO_EDGE]->(b)] AS xs",
        ],
    )
    def test_query_option_preamble_is_stripped_before_the_anchor(self, query: str) -> None:
        """`CYPHER runtime=...` is a pre-parser preamble, not a clause.

        The `.cypher` side sidesteps this by bypassing the gate; SKUEL030 reads
        Python string literals and has no such declaration (Codex P2 on #831).
        """
        assert [n.value for n in scan_names(query)] == ["TYPO_EDGE"]

    @pytest.mark.parametrize(
        "fragment",
        ["CYPHER RETURN the value to the caller", "CYPHER is the query language"],
    )
    def test_bare_cypher_word_is_not_a_preamble(self, fragment: str) -> None:
        """Requiring an option or version is what keeps the strip out of prose."""
        assert looks_like_cypher(fragment) is False

    def test_insert_is_on_the_paren_anchor_too(self) -> None:
        """Same reason CREATE is: the form is prose-safe wherever it appears."""
        assert [n.value for n in scan_names("... INSERT (n:Typo) ...")] == ["Typo"]

    @pytest.mark.parametrize(
        "query",
        ["CYPHER runtime=slotted MATCH (n:Typo) RETURN n", "USING PERIODIC COMMIT MERGE (n:Typo)"],
    )
    def test_query_prefixes_reach_anchor_1(self, query: str) -> None:
        """Completeness check: these need no clause-list entry of their own."""
        assert [n.value for n in scan_names(query)] == ["Typo"]


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
            "MATCH (n) SET n:Known&Typo RETURN n",
            "MATCH (n) REMOVE n:Known&Typo RETURN n",
        ],
    )
    def test_ampersand_joins_labels_too(self, query: str) -> None:
        """The PATTERN scanner already read `(n:A&B)`; the item regex did not.

        A colon-only item regex was an asymmetry inside this module, not just a
        missing form (Codex P2 on #831).
        """
        assert _labels(query) == ["Known", "Typo"]

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

    @pytest.mark.parametrize(
        ("query", "expected", "declared"),
        [
            # A keyword-shaped PROPERTY name — the `.` separator satisfies the
            # terminator regex's word boundary all by itself.
            ("MATCH (n) SET n.order = 1, n:Typo RETURN n", ["Typo"], False),
            ("set n.order = 1, n:Typo return n", ["Typo"], True),
            # A keyword-shaped LABEL — same problem one separator over.
            ("set n:Return return n", ["Return"], True),
            # A keyword-shaped PARAMETER — the third and last sigil that binds a
            # word to the current item.
            ("MATCH (n) SET n.v = $return, n:Typo RETURN n", ["Typo"], True),
            ("MATCH (n) SET n.v = $RETURN, n:Typo RETURN n", ["Typo"], False),
            # Case is not what saves this: a PascalCase label collides in strict
            # mode too.
            ("MATCH (n) SET n:ORDER RETURN n", ["ORDER"], False),
        ],
    )
    def test_keyword_shaped_names_do_not_end_the_region(
        self, query: str, expected: list[str], declared: bool
    ) -> None:
        """A keyword after `.` or `:` belongs to the item, not to a new clause.

        The region stopped at the property `order` and inside the label
        `Return`, so every item from there on went unvalidated (Codex P2 on
        #831).
        """
        assert [
            n.value for n in scan_names(query, declared_cypher=declared) if n.kind is NameKind.LABEL
        ] == expected

    def test_each_label_is_recorded_at_its_own_position(self) -> None:
        """A multiline colon group reported every label on the FIRST one's line.

        That is both a wrong location and a suppression comment that cannot be
        placed beside the name it must suppress (Codex P2 on #831).
        """
        fragment = "MATCH (n)\nSET n:Known:\n  Typo\nRETURN n"
        assert [(n.value, n.line_offset) for n in scan_names(fragment)] == [
            ("Known", 1),
            ("Typo", 2),
        ]

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
    """Backtick handling is SPLIT, not uniform — measured, not assumed.

    This class previously asserted that no position recovers an escaped name,
    with ``[n for n in scan_names(f) if "Bogus" in n.value.upper()] == []``.
    ``.upper()`` turns every candidate into ``BOGUS``/``BOGUS_EDGE``, which can
    never contain the mixed-case needle ``"Bogus"`` — so the comprehension was
    empty whatever the scanner returned, and the guard passed on any behaviour
    at all. Running the four fragments showed pattern position recovering both
    names all along, while the claim on the class said otherwise. That is this
    module's own failure mode — a check that reports clean without looking —
    and it is what left #831's single declined finding resting on an unmeasured
    premise.

    Now pinned to what the scanner actually does, each direction asserted
    positively so neither can drift into the other unnoticed.
    """

    @pytest.mark.parametrize(
        ("fragment", "expected"),
        [
            ("MATCH (n:`Bogus`) RETURN n", ["Bogus"]),
            ("MATCH ()-[r:`BOGUS_EDGE`]->() RETURN r", ["BOGUS_EDGE"]),
        ],
    )
    def test_pattern_position_recovers_escaped_names(
        self, fragment: str, expected: list[str]
    ) -> None:
        """An escaped label IS a label — an unregistered one is a real miss."""
        assert [n.value for n in scan_names(fragment)] == expected

    @pytest.mark.parametrize(
        "fragment",
        [
            "MATCH (n) SET n:`Bogus` RETURN n",
            "MATCH (n) REMOVE n:`Bogus` RETURN n",
        ],
    )
    def test_mutation_position_does_not_recover_escaped_names(self, fragment: str) -> None:
        """The remaining half of the limit, stated accurately.

        ``_LABEL_MUTATION_ITEM_RE`` requires an identifier character straight
        after the ``:``. Closing this is a behaviour widening with its own
        before/after measurement, not a free rider on a refactor.
        """
        assert [n.value for n in scan_names(fragment)] == []


# ============================================================================
# Pattern bodies are SPLIT on separators, not mined for identifier runs
# ============================================================================


class TestPatternBodySplitting:
    """`(n:A:B)` is a separator-joined list of names, read by splitting it.

    Extracting identifier RUNS instead reached inside `$( ... )` and reported
    the expression's internals as vocabulary — three rounds of Codex P2 on #831
    and a 57-line blanking walk to undo. Splitting makes every dynamic operand
    one unsplittable segment that simply fails the name regex.
    """

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("MATCH (n:A:B) RETURN n", ["A", "B"]),
            ("MATCH ()-[:A|B]->() RETURN 1", ["A", "B"]),
            ("MATCH (n:A&B) RETURN n", ["A", "B"]),
            ("MATCH ()-[r:A|B*1..3]->() RETURN r", ["A", "B"]),
        ],
    )
    def test_separator_joined_names_are_all_read(self, query: str, expected: list[str]) -> None:
        """Guard — already true before the split; the three separators Cypher has."""
        assert [n.value for n in scan_names(query)] == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            # Negation and grouping WRAP a name rather than joining two, so
            # splitting alone left `!Bogus` / `(Known` as segments that failed
            # the name regex — a typo'd label went from reported to invisible
            # (Codex P2 on #833). Live on `ad9afcb76`; a silent-miss rule cannot
            # lose coverage in a refactor.
            ("MATCH (n:!Bogus) RETURN n", ["Bogus"]),
            ("MATCH ()-[r:!BOGUS_EDGE]->() RETURN r", ["BOGUS_EDGE"]),
            ("MATCH (n:(Known|Bogus)) RETURN n", ["Known", "Bogus"]),
            # `%` is the wildcard — it names nothing, and must not be read as one.
            ("MATCH (n:%) RETURN n", []),
            # Grouping next to a dynamic operand: the static arm is still read,
            # the dynamic one is still opaque.
            ("MATCH (n:(Known|$(x))) RETURN n", ["Known"]),
            ("MATCH (n:!$(x)) RETURN n", []),
        ],
    )
    def test_label_expression_operators_wrap_a_readable_name(
        self, query: str, expected: list[str]
    ) -> None:
        """Cypher's label-expression operators are `& | ! % ( )`.

        Two are the separators, `%` names nothing, and the rest wrap. The set is
        DERIVED from the grammar rather than grown one report at a time — and
        the whole-segment full-match is what keeps `$(coalesce(Foo,Bogus` opaque
        regardless of which characters the atom regex is willing to strip.
        """
        assert [n.value for n in scan_names(query)] == expected

    @pytest.mark.parametrize("query", ["MATCH (n:A.B) RETURN n", "MATCH (n:A-B) RETURN n"])
    def test_non_separator_joins_yield_no_names(self, query: str) -> None:
        """`.` and `-` do not join labels in Cypher, so `A.B` is ONE bad token.

        Run-extraction invented two names out of it and would have reported both
        as unregistered. Nothing in the tree writes the form either way; the
        point is that the reader no longer manufactures names from a token it
        cannot parse.
        """
        assert scan_names(query) == []


# ============================================================================
# The instrument — what the scanner admitted but could not read
# ============================================================================


class TestScanDiagnostics:
    """Every drop `scan_names` makes is silent; the recorder makes it visible.

    The rules exist because Neo4j reports nothing for a name it cannot match.
    The scanner had the same shape: an item that does not full-match, a body
    whose parts all fail, a fragment the gate refuses — each vanishes without a
    word, so the only way to find a gap was for a reviewer to imagine an input.
    """

    def test_recording_is_off_by_default(self) -> None:
        """Guard — the production path must not change when nobody is listening."""
        assert [n.value for n in scan_names("MATCH (n:Ku) RETURN n")] == ["Ku"]

    def test_readable_input_records_nothing(self) -> None:
        with recording_scan_diagnostics() as sink:
            scan_names("MATCH (n:Ku)-[:OWNS]->(m:Entity) RETURN n")
        assert sink == []

    def test_unreadable_pattern_body_is_recorded(self) -> None:
        """`(n:$(labelExpr))` has no static name — a CORRECT drop, now visible."""
        with recording_scan_diagnostics() as sink:
            scan_names("MATCH (n:$(labelExpr)) RETURN n")
        assert [d.issue for d in sink] == [ScanIssue.UNREADABLE_PATTERN_BODY]
        assert "labelExpr" in sink[0].text

    def test_unparsed_mutation_item_is_recorded(self) -> None:
        """A label-SHAPED item the item regex cannot read — the real signal."""
        with recording_scan_diagnostics() as sink:
            scan_names("MATCH (n) SET n:`Bogus` RETURN n")
        assert ScanIssue.UNPARSED_MUTATION_ITEM in [d.issue for d in sink]

    def test_property_only_mutation_is_recorded_as_the_raw_denominator(self) -> None:
        """`SET n.title = $t` carries no label, so it is NOT an unparsed item.

        It still lands in the unfiltered category, which is what proves the
        label-shape filter above hides no whole class of input.
        """
        with recording_scan_diagnostics() as sink:
            scan_names("MATCH (n) SET n.title = $t RETURN n")
        assert [d.issue for d in sink] == [ScanIssue.MUTATION_CLAUSE_NO_ITEM_MATCHED]

    def test_gate_rejection_is_recorded_when_a_real_name_is_present(self) -> None:
        """A bare pattern fragment composed into a query later — anchor blind spot.

        `activity_backends.py:94` assigns exactly this shape to a variable. Both
        of its names are registered, so no rule fires today; the gate would not
        have seen a typo'd one either.
        """
        with recording_scan_diagnostics() as sink:
            assert scan_names("(t:Entity)") == []
        assert [d.issue for d in sink] == [ScanIssue.REJECTED_BY_GATE]

    @pytest.mark.parametrize(
        "fragment",
        [
            "WHERE n:Bogus",
            "type(r) = 'BOGUS_EDGE'",
            "AND NOT a:Bogus",
        ],
    )
    def test_gate_rejection_covers_every_scanner_position(self, fragment: str) -> None:
        """The filter asks the scanners, so it cannot lag behind them.

        A hand-written approximation asked about PATTERN position alone, and
        these three — refused by the gate, carrying names `scan_names` recovers
        — reported nothing (Codex P2 on #833). The instrument built to expose
        silent drops had grown its own, one layer further down again.
        """
        with recording_scan_diagnostics() as sink:
            assert scan_names(fragment) == []
        assert [d.issue for d in sink] == [ScanIssue.REJECTED_BY_GATE]

    def test_gate_rejection_probe_records_only_the_rejection(self) -> None:
        """The probe re-scans; its OWN drops describe text never admitted.

        Recording them would answer a question nobody asked and bury the single
        finding that matters under the noise of a fragment that was refused.
        """
        with recording_scan_diagnostics() as sink:
            scan_names("(t:Entity) SET n.title = $t")
        assert [d.issue for d in sink] == [ScanIssue.REJECTED_BY_GATE]

    def test_gate_rejection_of_prose_is_not_recorded(self) -> None:
        """Without the name filter every non-Cypher string is a 'drop' — true, useless."""
        with recording_scan_diagnostics() as sink:
            assert scan_names("just some ordinary prose") == []
        assert sink == []

    def test_source_line_is_absolute_when_the_caller_declares_a_base(self) -> None:
        """`(+2 lines)` is not navigable; 265 rows of it cannot be acted on.

        The offset is relative to the fragment and the base lives with the
        caller — `node.lineno` for SKUEL030, the statement's `start_line` for
        CYP011 (Codex P2 on #833).
        """
        with recording_scan_diagnostics() as sink, scanning_fragment_at(300):
            scan_names("MATCH (n:Ku)\nWITH n\nMATCH (m:$(labelExpr)) RETURN m")
        assert [(d.line_offset, d.source_line) for d in sink] == [(2, 302)]

    def test_source_line_is_none_when_no_base_is_declared(self) -> None:
        """An undeclared base must read as absent, never as line 0 or line 2."""
        with recording_scan_diagnostics() as sink:
            scan_names("MATCH (n:$(labelExpr)) RETURN n")
        assert sink[0].source_line is None

    def test_nested_recording_restores_the_outer_sink(self) -> None:
        """The sink is module-global; a nested block must not steal the outer's."""
        with recording_scan_diagnostics() as outer:
            scan_names("MATCH (n:$(a)) RETURN n")
            with recording_scan_diagnostics() as inner:
                scan_names("MATCH (n:$(b)) RETURN n")
            scan_names("MATCH (n:$(c)) RETURN n")
        assert len(inner) == 1
        assert len(outer) == 2


def _truncations(fragment: str, *, declared_cypher: bool = False) -> list[tuple[str, str | None]]:
    """``(span, keyword that broke the region)`` for each truncation reported."""
    with recording_scan_diagnostics() as sink:
        scan_names(fragment, declared_cypher=declared_cypher)
    return [
        (d.text.strip(), d.detail) for d in sink if d.issue is ScanIssue.TRUNCATED_MUTATION_REGION
    ]


class TestMutationRegionTruncation:
    """The one silent drop the categories above structurally cannot report.

    Every other diagnostic describes a span that WAS produced and could not be
    read. When the mutation walk ends EARLY, no span is produced for anything
    after the break, so there is nothing to record — #833 stated this as a limit
    rather than closing it. It is also the densest blind spot left: six of #831's
    findings were this walk stopping in the wrong place.

    The detector runs the SAME walk under two termination policies — strict
    (today's) and permissive (no keyword break) — and diffs the readable label
    items. Neither walk has to be correct; only their disagreement is read, and
    disagreement has exactly one cause. That is what makes this a measurement
    rather than a second guess at where a clause really ends.
    """

    def test_a_truncated_region_is_detected(self) -> None:
        """`order` is a legal variable name AND a clause word — the region dies on it.

        In the relaxed dialect a `.cypher` file may spell any clause keyword in
        lowercase, so a variable named after one is indistinguishable from a
        clause head to the terminator regex. `Bogus` is never scanned: the walk
        stops at `order` and every item after the break is lost.
        """
        assert [
            n.value for n in scan_names("MATCH (n) SET n:Ku, order:Bogus", declared_cypher=True)
        ] == ["Ku"]
        assert _truncations("MATCH (n) SET n:Ku, order:Bogus", declared_cypher=True) == [
            ("order:Bogus", "order")
        ]

    def test_the_report_names_the_keyword_that_broke_the_region(self) -> None:
        """A span without its cause makes the reader re-derive the walk by hand."""
        assert _truncations("MATCH (n) SET a:Ku, order:Bogus", declared_cypher=True) == [
            ("order:Bogus", "order")
        ]

    def test_a_break_inside_an_item_is_detected_too(self) -> None:
        """`&` joins labels, and it is not a name-component sigil.

        So `_starts_a_clause` admits the word after it and the walk stops in the
        MIDDLE of a label expression, losing both names rather than a trailing
        item. The disputed-item rule covers this without knowing the shape: the
        break is inside the item, and the item reads as a label item.
        """
        assert scan_names("MATCH (n) SET n:Ku&Order", declared_cypher=True) == []
        assert _truncations("MATCH (n) SET n:Ku&Order", declared_cypher=True) == [
            ("n:Ku&Order", "Order")
        ]

    def test_ordinary_syntax_the_overrun_reaches_is_not_a_truncation(self) -> None:
        """`RETURN n, n:Entity` is a label predicate in a RETURN list, not a loss.

        The region genuinely ended at `RETURN`. A permissive walk running past it
        splits that list on its comma and can read `` n:Entity`` as a label item —
        but only the item STRADDLING the break is in dispute, and everything after
        it is downstream of a question this detector cannot answer. Reporting it
        described arbitrary Cypher the overrun happened to reach (Codex P2).
        """
        assert _truncations("MATCH (n) SET n:Ku RETURN n, n:Entity") == []

    def test_a_tail_past_an_undecidable_break_is_not_claimed(self) -> None:
        """Same rule, the other direction: we cannot tell, so we do not say.

        If `ORDER` really heads a clause, `m:Entity` was never part of the SET
        region; if it is a variable, it was. Nothing here can decide it, and the
        disputed item (`` x ORDER y``) does not read as a label item.
        """
        assert _truncations("MATCH (n) SET n:Ku, x ORDER y, m:Entity RETURN n") == []

    def test_the_documented_miss_stays_silent(self) -> None:
        """Guard on the detector's stated edge, so a change to it is visible.

        When the disputed item has no comma or statement end to bound it, it
        arrives glued to the following clause, cannot full-match, and is missed.
        One-sided by construction — under-reporting, never an invented boundary.
        """
        assert _truncations("MATCH (n) SET n:Ku, order:Bogus RETURN n", declared_cypher=True) == []

    @pytest.mark.parametrize(
        ("fragment", "declared_cypher"),
        [
            # Every break the walk makes CORRECTLY. A detector that fired on
            # these would report most of the tree and be read by nobody.
            ("MATCH (n) SET n:Ku WITH n RETURN n", False),
            ("MATCH (n) SET n:Ku RETURN n", False),
            ("MATCH (n) SET n.title = $t RETURN n", False),
            ("MATCH (n) SET n:Ku, n.x = 1 RETURN n", False),
            ("MATCH (n) SET n.ok = all(x IN $xs WHERE x > 0), n:Ku RETURN n", False),
            ("FOREACH (x IN $xs | SET x:Ku) RETURN 1", False),
            ("CALL { MATCH (n) SET n:Ku } RETURN 1", False),
            ("MATCH (n) SET n:Ku; MATCH (m) SET m:Entity", False),
            ("MERGE (n) ON CREATE SET n:Ku ON MATCH SET n:Entity RETURN n", False),
            ("MATCH (n) SET n.order = 1, n:Ku RETURN n", True),
            ("MATCH (n) SET n:Ku WITH n MATCH (m) SET m:Entity, k:Entity RETURN m", False),
            ("MATCH (n) SET n:Ku RETURN n, n:Entity", False),
            ("MATCH (n) SET n:Ku RETURN n, n:Entity", True),
        ],
    )
    def test_a_correct_boundary_is_never_reported(
        self, fragment: str, declared_cypher: bool
    ) -> None:
        assert _truncations(fragment, declared_cypher=declared_cypher) == []

    def test_an_item_reached_by_two_walks_is_not_a_disagreement(self) -> None:
        """The FP this cost, and the reason `_item_key` normalises whitespace.

        A permissive region overrunning into a later `SET` re-derives that
        clause's items — but `mutation_head` ends in a greedy `\\s+`, so a
        re-headed span starts one character later than the original walk's.
        Keyed on the raw offset, the same item read twice looked like two, and
        every correctly-scanned `SET a:X, b:Y RETURN ...` in the tree reported
        itself as lost.
        """
        fragment = "MATCH (n) SET n:Ku WITH n MATCH (m) SET m:Entity, k:Entity RETURN m"
        assert [n.value for n in scan_names(fragment)] == ["Ku", "Entity", "Entity"]
        assert _truncations(fragment) == []

    def test_the_permissive_walk_still_stops_at_a_statement_boundary(self) -> None:
        """Only the KEYWORD break is dropped. `;` and a depth-negative closer stay.

        Were they dropped too, a region would run across statements and mine the
        next one's items as this one's losses.
        """
        assert _truncations("MATCH (n) SET n:Ku; MATCH (m) SET m:Entity, order:Bogus") == []
