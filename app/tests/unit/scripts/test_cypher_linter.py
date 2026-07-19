"""
Tests for Cypher Query Linter
==============================

Tests _is_actual_cypher, _extract_cypher_queries, _extract_cypher_statements
(.cypher files), CYP001-CYP006, CYP009, _get_line_at_position, complexity
scoring, and file discovery.
"""

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cypher_linter import (  # type: ignore[import-not-found]
    CypherLinter,
    Severity,
    find_lintable_files,
)

# ============================================================================
# HELPERS
# ============================================================================


def make_linter() -> CypherLinter:
    return CypherLinter(errors_only=False)


# ============================================================================
# _is_actual_cypher
# ============================================================================


class TestIsActualCypher:
    def test_real_match_query(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = $uid RETURN n"
        assert linter._is_actual_cypher(query) is True

    def test_real_create_query(self) -> None:
        linter = make_linter()
        query = "CREATE (n:Entity {uid: $uid, title: $title}) RETURN n"
        assert linter._is_actual_cypher(query) is True

    def test_merge_query(self) -> None:
        linter = make_linter()
        query = "MERGE (n:Entity {uid: $uid}) RETURN n"
        assert linter._is_actual_cypher(query) is True

    def test_natural_language_rejected(self) -> None:
        linter = make_linter()
        text = "This is a description of how MATCH works in Neo4j"
        assert linter._is_actual_cypher(text) is False

    def test_documentation_rejected(self) -> None:
        linter = make_linter()
        text = "MATCH the user to the correct task for optimal learning"
        assert linter._is_actual_cypher(text) is False

    def test_no_cypher_keywords(self) -> None:
        linter = make_linter()
        text = "just some plain text without any cypher"
        assert linter._is_actual_cypher(text) is False

    def test_only_one_keyword_rejected(self) -> None:
        linter = make_linter()
        # Only MATCH, no second keyword, no syntax patterns
        text = "MATCH something"
        assert linter._is_actual_cypher(text) is False

    def test_relationship_pattern(self) -> None:
        linter = make_linter()
        query = "MATCH (a:Entity)-[r:OWNS]->(b:Entity) WHERE a.uid = $uid RETURN b"
        assert linter._is_actual_cypher(query) is True

    def test_single_command_merge_accepted(self) -> None:
        # The >= 2 keyword floor silently skipped one-command upserts — exactly
        # the interpolated MERGE shape CYP003 exists to catch (docs_to_neo4j.py).
        linter = make_linter()
        query = "MERGE (c:DocumentCategory {name: $name})"
        assert linter._is_actual_cypher(query) is True

    def test_call_procedure_with_params_accepted(self) -> None:
        # Procedure calls have no (n:Label) pattern — $params are their only
        # structural signal (query_template_registry fulltext template).
        linter = make_linter()
        query = (
            "CALL db.index.fulltext.queryNodes($index_name, $search_term)\n"
            "YIELD node, score\n"
            "RETURN node as n, score ORDER BY score DESC LIMIT $limit"
        )
        assert linter._is_actual_cypher(query) is True

    def test_merge_set_upsert_accepted(self) -> None:
        # SET was not a counted keyword — MERGE+SET upserts scored 1 and were
        # skipped before 2026-07.
        linter = make_linter()
        query = "MERGE (d:Document {uid: $uid})\nSET d.title = $title"
        assert linter._is_actual_cypher(query) is True


# ============================================================================
# _extract_cypher_queries
# ============================================================================


class TestExtractCypherQueries:
    def test_triple_quoted_cypher(self) -> None:
        linter = make_linter()
        content = '''
query = """
MATCH (n:Entity)
WHERE n.uid = $uid
RETURN n
"""
'''
        queries = linter._extract_cypher_queries(content, Path("test.py"))
        assert len(queries) == 1

    def test_session_run_cypher(self) -> None:
        linter = make_linter()
        content = '''
result = session.run("""
MATCH (n:Entity)
WHERE n.uid = $uid
RETURN n
""")
'''
        queries = linter._extract_cypher_queries(content, Path("test.py"))
        # Both triple-quote and session.run patterns match, but dedup
        assert len(queries) >= 1

    def test_deduplication(self) -> None:
        linter = make_linter()
        content = '''
query1 = """
MATCH (n:Entity)
WHERE n.uid = $uid
RETURN n
"""
query2 = """
MATCH (n:Entity)
WHERE n.uid = $uid
RETURN n
"""
'''
        queries = linter._extract_cypher_queries(content, Path("test.py"))
        assert len(queries) == 1  # Duplicates removed

    def test_non_cypher_triple_quotes_skipped(self) -> None:
        linter = make_linter()
        content = '''
docstring = """
This is just documentation, not a query.
"""
'''
        queries = linter._extract_cypher_queries(content, Path("test.py"))
        assert len(queries) == 0


# ============================================================================
# _extract_cypher_statements (.cypher files)
# ============================================================================


class TestExtractCypherStatements:
    def test_splits_on_semicolons(self) -> None:
        linter = make_linter()
        content = (
            "MATCH (n:Entity) WHERE n.uid = 'a' RETURN n;\n"
            "MATCH (m:Entity) WHERE m.uid = 'b' RETURN m;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 2
        assert statements[0][1] == 1
        assert statements[1][1] == 2

    def test_last_statement_without_semicolon_kept(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) RETURN n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1

    def test_multiline_statement_line_number(self) -> None:
        linter = make_linter()
        content = (
            "// Migration header\n"
            "MATCH (n:Entity {uid: 'a'})\n"
            "DETACH DELETE n;\n"
            "\n"
            "MATCH (m:Entity)\n"
            "RETURN m.uid;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 2
        # start_line anchors at the first real token; internal newline offsets
        # resolve to true file lines
        _first_text, first_line = statements[0]
        assert first_line == 2
        second_text, second_line = statements[1]
        assert second_line == 5
        assert second_line + second_text[: second_text.index("RETURN")].count("\n") == 6

    def test_full_line_comments_blanked(self) -> None:
        # Commented-out queries are not live code; prose headers must not
        # leak into statements and trip prose-shaped rules
        linter = make_linter()
        content = (
            "// MATCH (n:Entity) RETURN n;\n"
            "// This migration DELETE the stale edges safely\n"
            "MATCH (n:Entity) WHERE n.uid = 'a' RETURN n;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "stale edges" not in statements[0][0]

    def test_semicolon_inside_string_literal_not_split(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) WHERE n.title = 'a; b' RETURN n;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1

    def test_semicolon_inside_trailing_comment_not_split(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) // don't split; really\nRETURN n;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1

    def test_trailing_comment_kept_for_noqa(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity {uid: 'a'})\nDELETE n // noqa: CYP002 - leaf node\n;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "noqa: CYP002" in statements[0][0]

    def test_noqa_after_semicolon_folded_into_statement(self) -> None:
        # Codex, PR #710 round 3: the natural placement puts noqa AFTER the
        # terminator — it must belong to the statement the ';' just closed
        linter = make_linter()
        content = (
            "MATCH (n:Entity {uid: 'a'})\nDELETE n; // noqa: CYP002 - leaf node\n"
            "MATCH (m:Entity) RETURN m LIMIT 1;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 2
        assert "noqa: CYP002" in statements[0][0]
        assert "noqa" not in statements[1][0]

    def test_trailing_comment_after_final_semicolon_no_phantom_statement(self) -> None:
        # Codex, PR #710: the tail append turned a keyword-bearing trailing
        # comment into a phantom raw statement
        linter = make_linter()
        content = "MATCH (n:Entity) RETURN n LIMIT 1; // then DELETE n manually\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "DELETE" not in statements[0][0]

    def test_trailing_comment_after_semicolon_not_leaked_into_next_statement(self) -> None:
        # Codex, PR #710 (sibling shape): a trailing comment between two
        # statements belonged to neither, but its prose landed in statement 2
        linter = make_linter()
        content = (
            "MATCH (n:Entity) RETURN n LIMIT 1; // cleanup: DELETE n afterwards\n"
            "MATCH (m:Entity) RETURN m LIMIT 1;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 2
        assert "DELETE" not in statements[1][0]
        assert statements[1][1] == 2

    def test_block_comment_masked(self) -> None:
        # Codex, PR #710 round 2: /* */ is a legal Cypher comment; its prose
        # must not trip prose-shaped rules and its ';' must not split
        linter = make_linter()
        content = (
            "/* Migration: DELETE stale nodes; then verify */\nMATCH (n:Entity) RETURN n LIMIT 1;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "DELETE" not in statements[0][0]

    def test_multiline_block_comment_preserves_line_numbers(self) -> None:
        linter = make_linter()
        content = (
            "/*\n * Header prose\n * spanning lines\n */\nMATCH (n:Entity) RETURN n LIMIT 1;\n"
        )
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert statements[0][1] == 5

    def test_inline_block_comment_masked_mid_statement(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) /* DELETE n later */ RETURN n LIMIT 1;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "DELETE" not in statements[0][0]

    def test_unterminated_block_comment_masked_to_eof(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) RETURN n LIMIT 1;\n/* dangling DELETE n prose\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "DELETE" not in statements[0][0]

    def test_block_comment_marker_inside_string_not_a_comment(self) -> None:
        linter = make_linter()
        content = "MATCH (n:Entity) WHERE n.note = 'a /* b */ c' RETURN n LIMIT 1;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1
        assert "/* b */" in statements[0][0]

    def test_keywordless_statements_skipped(self) -> None:
        # DROP INDEX / SHOW carry no linted keyword — no rule applies
        linter = make_linter()
        content = "DROP INDEX entity_uid_idx IF EXISTS;\nSHOW INDEXES;\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 0

    def test_create_index_statement_kept(self) -> None:
        linter = make_linter()
        content = "CREATE INDEX task_uid_idx IF NOT EXISTS FOR (n:Task) ON (n.uid);\n"
        statements = linter._extract_cypher_statements(content)
        assert len(statements) == 1


# ============================================================================
# lint_file on .cypher files (end-to-end)
# ============================================================================


class TestLintCypherFile:
    def test_detects_cyp002_at_correct_line(self, tmp_path: Path) -> None:
        linter = make_linter()
        cypher_file = tmp_path / "bad_migration.cypher"
        cypher_file.write_text(
            "// Migration: remove stale nodes\nMATCH (n:Entity {uid: 'stale'})\nDELETE n;\n"
        )
        violations = linter.lint_file(cypher_file)
        cyp002 = [v for v in violations if v.rule_code == "CYP002"]
        assert len(cyp002) == 1
        assert cyp002[0].severity == Severity.ERROR
        assert cyp002[0].line_number == 3

    def test_noqa_suppression_in_cypher_file(self, tmp_path: Path) -> None:
        linter = make_linter()
        cypher_file = tmp_path / "suppressed.cypher"
        cypher_file.write_text(
            "MATCH (n:Entity {uid: 'stale'})\nDELETE n // noqa: CYP002 - node is a leaf\n;\n"
        )
        violations = linter.lint_file(cypher_file)
        assert [v for v in violations if v.rule_code == "CYP002"] == []

    def test_noqa_after_semicolon_suppresses(self, tmp_path: Path) -> None:
        # Codex, PR #710 round 3: `DELETE n; // noqa: CYP002` — the natural
        # single-line form — must suppress, and only for its own statement
        linter = make_linter()
        cypher_file = tmp_path / "suppressed_natural.cypher"
        cypher_file.write_text(
            "MATCH (n:Entity {uid: 'a'})\nDELETE n; // noqa: CYP002 - node is a leaf\n"
            "MATCH (m:Entity {uid: 'b'})\nDELETE m;\n"
        )
        violations = linter.lint_file(cypher_file)
        cyp002 = [v for v in violations if v.rule_code == "CYP002"]
        assert len(cyp002) == 1
        assert cyp002[0].line_number == 4

    def test_violation_only_in_own_statement(self, tmp_path: Path) -> None:
        # Per-statement splitting: a LIMIT in statement 1 must not exempt an
        # unbounded RETURN in statement 2 (whole-file linting would)
        linter = make_linter()
        cypher_file = tmp_path / "two_statements.cypher"
        cypher_file.write_text(
            "MATCH (n:Entity) RETURN n LIMIT 10;\nMATCH (m:Entity) RETURN m.uid;\n"
        )
        violations = linter.lint_file(cypher_file)
        cyp006 = [v for v in violations if v.rule_code == "CYP006"]
        assert len(cyp006) == 1
        assert cyp006[0].line_number == 2

    def test_indexes_style_file_clean(self, tmp_path: Path) -> None:
        linter = make_linter()
        cypher_file = tmp_path / "indexes.cypher"
        cypher_file.write_text(
            "DROP INDEX entity_uid_idx IF EXISTS;\n"
            "CREATE CONSTRAINT Entity_uid_unique IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.uid IS UNIQUE;\n"
            "CREATE INDEX task_uid_idx IF NOT EXISTS FOR (n:Task) ON (n.uid);\n"
        )
        assert linter.lint_file(cypher_file) == []

    def test_commented_out_query_not_linted(self, tmp_path: Path) -> None:
        linter = make_linter()
        cypher_file = tmp_path / "commented.cypher"
        cypher_file.write_text("// MATCH (n:Entity {uid: 'x'})\n// DELETE n;\n")
        assert linter.lint_file(cypher_file) == []


# ============================================================================
# find_lintable_files
# ============================================================================


class TestFindLintableFiles:
    def test_collects_cypher_and_python(self, tmp_path: Path) -> None:
        (tmp_path / "scripts" / "migrations").mkdir(parents=True)
        (tmp_path / "tests" / "unit").mkdir(parents=True)
        (tmp_path / "scripts" / "indexes.cypher").write_text("// indexes\n")
        (tmp_path / "scripts" / "migrations" / "fix.cypher").write_text("// migration\n")
        (tmp_path / "scripts" / "tool.py").write_text("")
        (tmp_path / "tests" / "unit" / "fixture.cypher").write_text("// bad fixture\n")

        found = {p.relative_to(tmp_path).as_posix() for p in find_lintable_files(tmp_path)}

        assert "scripts/indexes.cypher" in found
        assert "scripts/migrations/fix.cypher" in found
        assert "scripts/tool.py" in found
        # tests/unit is deliberately excluded — fixtures are intentionally bad
        assert "tests/unit/fixture.cypher" not in found


# ============================================================================
# CYP001: Nested aggregates
# ============================================================================


class TestCYP001:
    def test_detects_nested_aggregates(self) -> None:
        linter = make_linter()
        query = "RETURN collect({uid: n.uid, count: count(r)})"
        violations = linter._check_nested_aggregates(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP001"
        assert violations[0].severity == Severity.ERROR

    def test_clean_staged_aggregation(self) -> None:
        linter = make_linter()
        query = "WITH n, count(r) as r_count\nRETURN collect({uid: n.uid, count: r_count})"
        violations = linter._check_nested_aggregates(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_single_aggregate_clean(self) -> None:
        linter = make_linter()
        query = "RETURN count(n)"
        violations = linter._check_nested_aggregates(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP002: DELETE without DETACH
# ============================================================================


class TestCYP002:
    def test_detects_delete_without_detach(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity {uid: $uid})\nDELETE n"
        violations = linter._check_delete_without_detach(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP002"

    def test_detach_delete_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity {uid: $uid})\nDETACH DELETE n"
        violations = linter._check_delete_without_detach(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_relationship_delete_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[r:OWNS]->(b)\nDELETE r"
        violations = linter._check_delete_without_detach(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP003: String interpolation
# ============================================================================


class TestCYP003:
    def test_detects_interpolation(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = {user_uid} RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) >= 1
        assert violations[0].rule_code == "CYP003"

    def test_severity_is_error(self) -> None:
        # Promoted 2026-07 (was WARNING): value interpolation is the injection
        # shape, and CI's --errors-only --strict gate only enforces ERRORs.
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = {user_uid} RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert violations[0].severity == Severity.ERROR

    def test_detects_quoted_interpolation(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.status = '{status}' RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 1

    def test_detects_quoted_map_value(self) -> None:
        # The old ':'-within-5-chars exemption skipped exactly this shape.
        linter = make_linter()
        query = "MERGE (d:Document {{uid: '{node_uid}'}})\nRETURN d"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 1

    def test_detects_dotted_expression(self) -> None:
        linter = make_linter()
        query = "MATCH (d:Document) SET d.path = '{node.path}' RETURN d"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 1

    def test_detects_comparison_operand(self) -> None:
        linter = make_linter()
        query = "MATCH p = (n:Entity)-[*]-(m) WHERE length(p) <= {depth} RETURN m"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 1

    def test_detects_in_operand(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.status IN {statuses} RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 1

    def test_parameterized_query_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = $uid RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_cypher_map_syntax_clean(self) -> None:
        linter = make_linter()
        query = "CREATE (n:Entity {uid: $uid, title: $title})"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_clause_fragment_clean(self) -> None:
        # Structural composition — the sanctioned below-boundary pattern.
        linter = make_linter()
        query = "MATCH (n:Entity)\nWHERE true {where_clause}\nRETURN n {order_clause}"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_label_interpolation_clean(self) -> None:
        # Validated-identifier interpolation ((n:{label}), [r:{rel_type}]) is
        # structural — labels/reltypes cannot be driver parameters.
        linter = make_linter()
        query = "MATCH (n:{label})-[r:{rel_type}]->(m) WHERE n.uid = $uid RETURN m"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_depth_bound_clean(self) -> None:
        # *1..{depth} bounds cannot be parameterized in Cypher.
        linter = make_linter()
        query = "MATCH (u:Entity {uid: $uid})-[r*0..{depth}]-(related) RETURN related"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_relationship_arrow_then_fragment_clean(self) -> None:
        # -> before an interpolated fragment must not read as a > comparison.
        linter = make_linter()
        query = "MATCH (a:Entity)-[:OWNS]->{target_pattern}\nRETURN a"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_doubled_brace_escape_clean(self) -> None:
        # {{var}} renders to literal {var} — an f-string escape, not interpolation.
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = {{uid}} RETURN n"
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_noqa_suppression(self) -> None:
        linter = make_linter()
        query = (
            "MATCH (n:Entity) WHERE n.uid = {user_uid} "
            "// noqa: CYP003 - template rendered pre-execution\nRETURN n"
        )
        violations = linter._check_string_interpolation(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP004: Unbounded traversal
# ============================================================================


class TestCYP004:
    def test_detects_unbounded(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[:OWNS*]->(b) RETURN b"
        violations = linter._check_unbounded_traversal(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP004"

    def test_bounded_traversal_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[:OWNS*1..5]->(b) RETURN b"
        violations = linter._check_unbounded_traversal(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP005: Missing depth limit
# ============================================================================


class TestCYP005:
    def test_excessive_depth(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[:OWNS*1..50]->(b) RETURN b"
        violations = linter._check_missing_depth_limit(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP005"

    def test_reasonable_depth_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[:OWNS*1..5]->(b) RETURN b"
        violations = linter._check_missing_depth_limit(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_depth_exactly_10_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (a)-[:OWNS*1..10]->(b) RETURN b"
        violations = linter._check_missing_depth_limit(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP006: Missing LIMIT
# ============================================================================


class TestCYP006:
    def test_missing_limit(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.status = 'active' RETURN n"
        violations = linter._check_missing_limit(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP006"
        assert violations[0].severity == Severity.INFO

    def test_with_limit_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) RETURN n LIMIT 100"
        violations = linter._check_missing_limit(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_aggregation_exempt(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) RETURN count(n)"
        violations = linter._check_missing_limit(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_collect_aggregation_exempt(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) RETURN collect(n.uid)"
        violations = linter._check_missing_limit(query, Path("test.py"), 1)
        assert len(violations) == 0


# ============================================================================
# CYP009: Query complexity
# ============================================================================


class TestCYP009:
    def test_simple_query_clean(self) -> None:
        linter = make_linter()
        query = "MATCH (n:Entity) WHERE n.uid = $uid RETURN n"
        violations = linter._check_query_complexity(query, Path("test.py"), 1)
        assert len(violations) == 0

    def test_high_complexity_warning(self) -> None:
        linter = make_linter()
        # 5 MATCH (10pts) + 3 WITH (9pts) + 2 WHERE (2pts) = 21 > 20
        query = (
            "MATCH (a:Entity)\nMATCH (b:Entity)\nMATCH (c:Entity)\n"
            "MATCH (d:Entity)\nMATCH (e:Entity)\n"
            "WITH a, b\nWITH c, d\nWITH e\n"
            "WHERE a.uid = $uid\nWHERE b.uid = $uid2\n"
            "RETURN a"
        )
        violations = linter._check_query_complexity(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP009"

    def test_very_high_complexity(self) -> None:
        linter = make_linter()
        # 8 MATCH (16pts) + 5 WITH (15pts) = 31 > 30
        query = "\n".join(
            [f"MATCH (n{i}:Entity)" for i in range(8)]
            + [f"WITH n{i}" for i in range(5)]
            + ["RETURN n0"]
        )
        violations = linter._check_query_complexity(query, Path("test.py"), 1)
        assert len(violations) == 1
        assert (
            "Very high" in violations[0].message or "architecture review" in violations[0].message
        )

    def test_aggregation_adds_complexity(self) -> None:
        linter = make_linter()
        # Aggregations add 2 points each
        query = (
            "MATCH (a:Entity)\nMATCH (b:Entity)\nMATCH (c:Entity)\n"
            "MATCH (d:Entity)\nMATCH (e:Entity)\n"
            "WITH a, count(b) as cnt\nWITH a, sum(cnt) as total\nWITH a, avg(total) as average\n"
            "RETURN collect(a)"
        )
        violations = linter._check_query_complexity(query, Path("test.py"), 1)
        # This should trigger since we have many MATCH, WITH, and aggregations
        assert len(violations) >= 1


# ============================================================================
# _get_line_at_position
# ============================================================================


class TestGetLineAtPosition:
    def test_first_line(self) -> None:
        linter = make_linter()
        text = "line one\nline two\nline three"
        assert linter._get_line_at_position(text, 0) == "line one"

    def test_second_line(self) -> None:
        linter = make_linter()
        text = "line one\nline two\nline three"
        assert linter._get_line_at_position(text, 9) == "line two"

    def test_position_beyond_text(self) -> None:
        linter = make_linter()
        text = "short"
        assert linter._get_line_at_position(text, 100) == ""


# ============================================================================
# CYP011: vocabulary registry
# ============================================================================


class TestCYP011:
    """`.cypher` half of the graph-vocabulary contract (SKUEL030 owns `.py`)."""

    def test_detects_unregistered_label(self, tmp_path: Path) -> None:
        linter = make_linter()
        f = tmp_path / "probe.cypher"
        f.write_text("CREATE CONSTRAINT c IF NOT EXISTS FOR (n:Taskk) REQUIRE n.uid IS UNIQUE;")
        violations = linter._check_vocabulary_registry(f.read_text(), f, 1)
        assert len(violations) == 1
        assert violations[0].rule_code == "CYP011"
        assert violations[0].severity == Severity.ERROR
        assert "Taskk" in violations[0].message

    def test_detects_unregistered_relationship(self, tmp_path: Path) -> None:
        linter = make_linter()
        f = tmp_path / "probe.cypher"
        f.write_text("MATCH (u:User)-[:OWNS_ENTITY]->(t:Task) RETURN t;")
        violations = linter._check_vocabulary_registry(f.read_text(), f, 1)
        assert [v.message.count("OWNS_ENTITY") for v in violations] == [1]

    def test_allows_registered_vocabulary(self, tmp_path: Path) -> None:
        linter = make_linter()
        f = tmp_path / "probe.cypher"
        f.write_text("MATCH (u:User)-[:OWNS]->(t:Task) RETURN t;")
        assert linter._check_vocabulary_registry(f.read_text(), f, 1) == []

    def test_python_files_are_left_to_skuel030(self, tmp_path: Path) -> None:
        """Running here too would double-report every .py hit."""
        linter = make_linter()
        f = tmp_path / "backend.py"
        f.write_text('q = "MATCH (n:Taskk) RETURN n"')
        assert linter._check_vocabulary_registry(f.read_text(), f, 1) == []

    def test_migrations_are_excluded(self, tmp_path: Path) -> None:
        linter = make_linter()
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        f = migrations / "rename_2026.cypher"
        f.write_text("MATCH (n:RetiredLabel) REMOVE n:RetiredLabel;")
        assert linter._check_vocabulary_registry(f.read_text(), f, 1) == []

    def test_line_noqa_suppression(self, tmp_path: Path) -> None:
        linter = make_linter()
        f = tmp_path / "probe.cypher"
        query = "MATCH (n:Taskk) RETURN n; // noqa: CYP011 - external schema"
        f.write_text(query)
        assert linter._check_vocabulary_registry(query, f, 1) == []

    def test_file_noqa_suppression(self, tmp_path: Path) -> None:
        linter = make_linter()
        f = tmp_path / "probe.cypher"
        query = "MATCH (n:Taskk) RETURN n;"
        f.write_text("// noqa-file: CYP011 - dead template\n" + query)
        assert linter._check_vocabulary_registry(query, f, 1) == []
