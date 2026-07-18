"""
Tests for Cypher Query Linter
==============================

Tests _is_actual_cypher, _extract_cypher_queries, CYP001-CYP006, CYP009,
_get_line_at_position, and complexity scoring.
"""

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cypher_linter import CypherLinter, Severity  # type: ignore[import-not-found]

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
