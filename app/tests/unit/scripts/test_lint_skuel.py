"""
Tests for SKUEL Unified Linter
===============================

Tests all 17 lint rules, LintResult dataclass, and suppression logic.
Uses synthetic string content — no filesystem access needed.
"""

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from lint_skuel import LintResult, Severity, SkuelLinter, Violation


# ============================================================================
# HELPERS
# ============================================================================


def make_linter(rules_filter: list[str] | None = None) -> SkuelLinter:
    """Create a linter with a fake root dir."""
    return SkuelLinter(root_dir=Path("/fake/root"), rules_filter=rules_filter)


def lint_content(
    linter: SkuelLinter,
    content: str,
    *,
    file_path: str = "core/services/example_service.py",
    is_service: bool = True,
    is_adapter: bool = False,
) -> list[Violation]:
    """Run linter checks on synthetic content and return violations."""
    fp = Path("/fake/root") / file_path
    rel = Path(file_path)
    lines = content.split("\n")

    # Determine context flags
    is_test = "test_" in fp.name or "/tests/" in str(fp)

    # Run applicable rules based on the same logic as _lint_file
    if linter._should_run_rule("SKUEL003"):
        linter._check_is_err_usage(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL009"):
        linter._check_tuple_defaults(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL010"):
        linter._check_nested_tuple_defaults(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL011") and not is_test:
        linter._check_hasattr_usage(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL012") and not is_test:
        linter._check_lambda_usage(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL015") and not is_test:
        linter._check_print_statements(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL016"):
        linter._check_poetry_references(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL017") and not is_test:
        linter._check_broad_exception_catches(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL006"):
        linter._check_todo_comments(fp, rel, content, lines)

    if is_service and not is_test:
        if linter._should_run_rule("SKUEL001"):
            linter._check_apoc_in_services(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL002"):
            linter._check_semantic_type_strings(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL004"):
            linter._check_confidence_thresholds(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL005"):
            linter._check_result_return_types(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL007"):
            linter._check_string_result_fail(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL013"):
            linter._check_relationship_name_strings(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL014"):
            linter._check_entity_type_strings(fp, rel, content, lines)

    if is_adapter:
        if linter._should_run_rule("SKUEL008"):
            linter._check_backend_wrappers(fp, rel, content)

    return linter.result.violations


# ============================================================================
# LintResult DATACLASS
# ============================================================================


class TestLintResult:
    def test_empty_result(self) -> None:
        result = LintResult()
        assert result.has_critical is False
        assert result.has_error is False
        assert result.has_warning is False
        assert result.by_severity(Severity.CRITICAL) == []

    def test_has_critical(self) -> None:
        v = Violation(
            file_path=Path("x.py"),
            line_number=1,
            column=0,
            severity=Severity.CRITICAL,
            rule_id="SKUEL001",
            message="test",
            suggestion="fix",
        )
        result = LintResult(violations=[v])
        assert result.has_critical is True
        assert result.has_error is False

    def test_has_error(self) -> None:
        v = Violation(
            file_path=Path("x.py"),
            line_number=1,
            column=0,
            severity=Severity.ERROR,
            rule_id="SKUEL003",
            message="test",
            suggestion="fix",
        )
        result = LintResult(violations=[v])
        assert result.has_error is True
        assert result.has_critical is False

    def test_has_warning(self) -> None:
        v = Violation(
            file_path=Path("x.py"),
            line_number=1,
            column=0,
            severity=Severity.WARNING,
            rule_id="SKUEL011",
            message="test",
            suggestion="fix",
        )
        result = LintResult(violations=[v])
        assert result.has_warning is True

    def test_by_severity(self) -> None:
        v1 = Violation(
            file_path=Path("a.py"),
            line_number=1,
            column=0,
            severity=Severity.ERROR,
            rule_id="SKUEL003",
            message="err",
            suggestion="fix",
        )
        v2 = Violation(
            file_path=Path("b.py"),
            line_number=2,
            column=0,
            severity=Severity.WARNING,
            rule_id="SKUEL011",
            message="warn",
            suggestion="fix",
        )
        result = LintResult(violations=[v1, v2])
        assert len(result.by_severity(Severity.ERROR)) == 1
        assert len(result.by_severity(Severity.WARNING)) == 1
        assert len(result.by_severity(Severity.CRITICAL)) == 0

    def test_by_file(self) -> None:
        v1 = Violation(
            file_path=Path("a.py"),
            line_number=1,
            column=0,
            severity=Severity.ERROR,
            rule_id="X",
            message="",
            suggestion="",
        )
        v2 = Violation(
            file_path=Path("a.py"),
            line_number=2,
            column=0,
            severity=Severity.ERROR,
            rule_id="Y",
            message="",
            suggestion="",
        )
        v3 = Violation(
            file_path=Path("b.py"),
            line_number=1,
            column=0,
            severity=Severity.WARNING,
            rule_id="Z",
            message="",
            suggestion="",
        )
        result = LintResult(violations=[v1, v2, v3])
        by_file = result.by_file()
        assert len(by_file[Path("a.py")]) == 2
        assert len(by_file[Path("b.py")]) == 1

    def test_by_rule(self) -> None:
        v1 = Violation(
            file_path=Path("a.py"),
            line_number=1,
            column=0,
            severity=Severity.ERROR,
            rule_id="SKUEL003",
            message="",
            suggestion="",
        )
        v2 = Violation(
            file_path=Path("b.py"),
            line_number=1,
            column=0,
            severity=Severity.WARNING,
            rule_id="SKUEL011",
            message="",
            suggestion="",
        )
        result = LintResult(violations=[v1, v2])
        assert len(result.by_rule("SKUEL003")) == 1
        assert len(result.by_rule("SKUEL011")) == 1
        assert len(result.by_rule("SKUEL999")) == 0


# ============================================================================
# SUPPRESSION
# ============================================================================


class TestSuppression:
    def test_line_suppressed(self) -> None:
        linter = make_linter()
        line = "x = hasattr(obj, 'val')  # skuel-lint: disable=SKUEL011 -- known pattern"
        assert linter._is_line_suppressed(line, "SKUEL011") is True

    def test_line_not_suppressed(self) -> None:
        linter = make_linter()
        line = "x = hasattr(obj, 'val')"
        assert linter._is_line_suppressed(line, "SKUEL011") is False

    def test_line_suppressed_wrong_rule(self) -> None:
        linter = make_linter()
        line = "x = hasattr(obj, 'val')  # skuel-lint: disable=SKUEL012"
        assert linter._is_line_suppressed(line, "SKUEL011") is False

    def test_file_suppressed(self) -> None:
        linter = make_linter()
        content = "# skuel-lint: disable-file=SKUEL005 -- protocol file\nimport foo"
        assert linter._is_file_suppressed(content, "SKUEL005") is True

    def test_file_not_suppressed(self) -> None:
        linter = make_linter()
        content = "import foo\nbar = 1"
        assert linter._is_file_suppressed(content, "SKUEL005") is False

    def test_should_run_rule_no_filter(self) -> None:
        linter = make_linter()
        assert linter._should_run_rule("SKUEL003") is True

    def test_should_run_rule_with_filter(self) -> None:
        linter = make_linter(rules_filter=["SKUEL003"])
        assert linter._should_run_rule("SKUEL003") is True
        assert linter._should_run_rule("SKUEL011") is False


# ============================================================================
# SKUEL001: No APOC in domain services
# ============================================================================


class TestSKUEL001:
    def test_detects_apoc_path(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(
            linter,
            'query = "CALL apoc.path.subgraphAll(n, {maxLevel: 3})"',
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL001"
        assert violations[0].severity == Severity.CRITICAL

    def test_detects_apoc_cypher_run(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'result = apoc.cypher.run("MATCH (n) RETURN n")')
        assert len(violations) == 1

    def test_clean_code_no_violation(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, "query = CypherGenerator.build_chain(uid)")
        assert len(violations) == 0

    def test_detects_apoc_meta(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'query = "CALL apoc.meta.data()"')
        assert len(violations) == 1


# ============================================================================
# SKUEL002: Semantic type strings
# ============================================================================


class TestSKUEL002:
    def test_detects_magic_string(self) -> None:
        linter = make_linter(["SKUEL002"])
        violations = lint_content(linter, 'rel_type = "REQUIRES_THEORETICAL_UNDERSTANDING"')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL002"

    def test_enum_usage_clean(self) -> None:
        linter = make_linter(["SKUEL002"])
        violations = lint_content(
            linter,
            "rel_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING",
        )
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL002"])
        violations = lint_content(linter, '# Use "REQUIRES_THEORETICAL_UNDERSTANDING" enum')
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL002"])
        violations = lint_content(linter, '"""Use REQUIRES_THEORETICAL_UNDERSTANDING"""')
        assert len(violations) == 0


# ============================================================================
# SKUEL003: .is_err deprecated
# ============================================================================


class TestSKUEL003:
    def test_detects_is_err(self) -> None:
        linter = make_linter(["SKUEL003"])
        violations = lint_content(linter, "if result.is_err:")
        assert len(violations) == 1
        assert violations[0].fix_available is True
        assert violations[0].original_text == ".is_err"
        assert violations[0].fixed_text == ".is_error"

    def test_is_error_clean(self) -> None:
        linter = make_linter(["SKUEL003"])
        violations = lint_content(linter, "if result.is_error:")
        assert len(violations) == 0

    def test_skips_lint_skuel_itself(self) -> None:
        linter = make_linter(["SKUEL003"])
        fp = Path("/fake/root/scripts/lint_skuel.py")
        rel = Path("scripts/lint_skuel.py")
        content = "if result.is_err:"
        lines = content.split("\n")
        linter._check_is_err_usage(fp, rel, content, lines)
        assert len(linter.result.violations) == 0

    def test_auto_fix_metadata(self) -> None:
        linter = make_linter(["SKUEL003"])
        violations = lint_content(linter, "x = result.is_err")
        assert violations[0].severity == Severity.ERROR


# ============================================================================
# SKUEL004: Confidence thresholds
# ============================================================================


class TestSKUEL004:
    def test_semantic_query_without_confidence(self) -> None:
        linter = make_linter(["SKUEL004"])
        content = "MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)\nRETURN b"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL004"

    def test_semantic_query_with_confidence(self) -> None:
        linter = make_linter(["SKUEL004"])
        content = (
            "MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)\n"
            "WHERE r.confidence >= 0.7\n"
            "RETURN b"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_structural_query_no_warning(self) -> None:
        linter = make_linter(["SKUEL004"])
        content = "MATCH (a)-[r:ENABLES]->(b)\nRETURN b"
        violations = lint_content(linter, content)
        assert len(violations) == 0


# ============================================================================
# SKUEL005: Result[T] return types
# ============================================================================


class TestSKUEL005:
    def test_service_method_without_result(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "    async def get_tasks(self, uid: str) -> list[Task]:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL005"

    def test_service_method_with_result(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "    async def get_tasks(self, uid: str) -> Result[list[Task]]:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_private_method_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "    async def _get_internal(self) -> Task:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "# skuel-lint: disable-file=SKUEL005 -- protocol file\n"
            "    async def get_tasks(self, uid: str) -> list[Task]:\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "    async def publish(self, msg: str) -> None:  # skuel-lint: disable=SKUEL005 -- fire-and-forget\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_protocol_file_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        fp = Path("/fake/root/core/ports/domain_protocols.py")
        rel = Path("core/ports/domain_protocols.py")
        content = "    async def get_tasks(self, uid: str) -> list[Task]:\n        pass"
        lines = content.split("\n")
        linter._check_result_return_types(fp, rel, content, lines)
        assert len(linter.result.violations) == 0


# ============================================================================
# SKUEL006: TODO/FIXME comments
# ============================================================================


class TestSKUEL006:
    def test_uncategorized_todo(self) -> None:
        linter = make_linter(["SKUEL006"])
        violations = lint_content(linter, "# TODO: implement this")
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO
        assert "uncategorized" in violations[0].message

    def test_categorized_todo(self) -> None:
        linter = make_linter(["SKUEL006"])
        violations = lint_content(linter, "# TODO(blocked:graph-data): needs alignment nodes")
        assert len(violations) == 1
        assert "categorized" in violations[0].message
        assert "blocked:graph-data" in violations[0].suggestion

    def test_fixme(self) -> None:
        linter = make_linter(["SKUEL006"])
        violations = lint_content(linter, "# FIXME: broken logic")
        assert len(violations) == 1
        assert "FIXME" in violations[0].message

    def test_no_todo(self) -> None:
        linter = make_linter(["SKUEL006"])
        violations = lint_content(linter, "x = 1  # normal comment")
        assert len(violations) == 0


# ============================================================================
# SKUEL007: String Result.fail()
# ============================================================================


class TestSKUEL007:
    def test_detects_string_fail(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, 'return Result.fail("Task not found")')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL007"

    def test_detects_fstring_fail(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, 'return Result.fail(f"Error: {e}")')
        assert len(violations) == 1

    def test_errors_factory_clean(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, 'return Result.fail(Errors.not_found("Task", uid))')
        assert len(violations) == 0


# ============================================================================
# SKUEL008: Backend wrappers
# ============================================================================


class TestSKUEL008:
    def test_detects_wrapper_class(self) -> None:
        linter = make_linter(["SKUEL008"])
        content = "class MyBackend(UniversalNeo4jBackend[Task]):\n    pass"
        violations = lint_content(
            linter,
            content,
            file_path="adapters/persistence/neo4j/my_backend.py",
            is_service=False,
            is_adapter=True,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL008"

    def test_domain_backends_exempt(self) -> None:
        linter = make_linter(["SKUEL008"])
        content = "class TasksBackend(UniversalNeo4jBackend[Task]):\n    pass"
        fp = Path("/fake/root/adapters/persistence/neo4j/domain_backends.py")
        rel = Path("adapters/persistence/neo4j/domain_backends.py")
        linter._check_backend_wrappers(fp, rel, content)
        assert len(linter.result.violations) == 0

    def test_universal_backend_self_exempt(self) -> None:
        linter = make_linter(["SKUEL008"])
        content = "class UniversalNeo4jBackend:\n    pass"
        fp = Path("/fake/root/adapters/persistence/neo4j/universal_backend.py")
        rel = Path("adapters/persistence/neo4j/universal_backend.py")
        linter._check_backend_wrappers(fp, rel, content)
        assert len(linter.result.violations) == 0


# ============================================================================
# SKUEL009: Single-element tuple defaults
# ============================================================================


class TestSKUEL009:
    def test_detects_tuple_default(self) -> None:
        linter = make_linter(["SKUEL009"])
        violations = lint_content(linter, "    count: int = (0,)")
        assert len(violations) == 1
        assert violations[0].fix_available is True

    def test_clean_scalar_default(self) -> None:
        linter = make_linter(["SKUEL009"])
        violations = lint_content(linter, "    count: int = 0")
        assert len(violations) == 0

    def test_skips_tuple_type_annotation(self) -> None:
        linter = make_linter(["SKUEL009"])
        violations = lint_content(linter, "    items: tuple[int] = (0,)")
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL009"])
        violations = lint_content(linter, "# count: int = (0,)")
        assert len(violations) == 0

    def test_auto_fix_text(self) -> None:
        linter = make_linter(["SKUEL009"])
        violations = lint_content(linter, '    name: str = ("",)')
        assert len(violations) == 1
        assert violations[0].original_text == '= ("",)'
        assert violations[0].fixed_text == '= ""'


# ============================================================================
# SKUEL010: Nested empty tuple defaults
# ============================================================================


class TestSKUEL010:
    def test_detects_nested_tuple(self) -> None:
        linter = make_linter(["SKUEL010"])
        violations = lint_content(linter, "    items: tuple = ((),)")
        assert len(violations) == 1
        assert violations[0].fix_available is True
        assert violations[0].original_text == "((),)"
        assert violations[0].fixed_text == "()"

    def test_clean_empty_tuple(self) -> None:
        linter = make_linter(["SKUEL010"])
        violations = lint_content(linter, "    items: tuple = ()")
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL010"])
        violations = lint_content(linter, "# items: tuple = ((),)")
        assert len(violations) == 0


# ============================================================================
# SKUEL011: hasattr() usage
# ============================================================================


class TestSKUEL011:
    def test_detects_hasattr(self) -> None:
        linter = make_linter(["SKUEL011"])
        violations = lint_content(linter, "if hasattr(obj, 'value'):")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL011"

    def test_clean_isinstance(self) -> None:
        linter = make_linter(["SKUEL011"])
        violations = lint_content(linter, "if isinstance(obj, HasValue):")
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL011"])
        violations = lint_content(
            linter,
            "if hasattr(obj, 'value'):  # skuel-lint: disable=SKUEL011 -- dynamic check",
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL011"])
        violations = lint_content(
            linter,
            "# skuel-lint: disable-file=SKUEL011 -- adapter file\nif hasattr(obj, 'value'):",
        )
        assert len(violations) == 0

    def test_sort_functions_exempt(self) -> None:
        linter = make_linter(["SKUEL011"])
        fp = Path("/fake/root/core/utils/sort_functions.py")
        rel = Path("core/utils/sort_functions.py")
        content = "if hasattr(obj, 'value'):"
        lines = content.split("\n")
        linter._check_hasattr_usage(fp, rel, content, lines)
        assert len(linter.result.violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL011"])
        violations = lint_content(linter, "# if hasattr(obj, 'value'):")
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL011"])
        content = '"""\nUse hasattr(obj, \'value\') for checking.\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0


# ============================================================================
# SKUEL012: Lambda expressions
# ============================================================================


class TestSKUEL012:
    def test_detects_lambda(self) -> None:
        linter = make_linter(["SKUEL012"])
        violations = lint_content(linter, "tasks.sort(key=lambda t: t.priority)")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL012"

    def test_named_function_clean(self) -> None:
        linter = make_linter(["SKUEL012"])
        violations = lint_content(linter, "tasks.sort(key=get_priority_value)")
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL012"])
        violations = lint_content(
            linter,
            "x = sorted(items, key=lambda i: i.name)  # skuel-lint: disable=SKUEL012 -- one-shot",
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL012"])
        violations = lint_content(
            linter,
            "# skuel-lint: disable-file=SKUEL012 -- adapter\ntasks.sort(key=lambda t: t.priority)",
        )
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL012"])
        violations = lint_content(linter, "# lambda t: t.priority")
        assert len(violations) == 0

    def test_examples_dir_exempt(self) -> None:
        linter = make_linter(["SKUEL012"])
        fp = Path("/fake/root/examples/demo.py")
        rel = Path("examples/demo.py")
        content = "tasks.sort(key=lambda t: t.priority)"
        lines = content.split("\n")
        linter._check_lambda_usage(fp, rel, content, lines)
        assert len(linter.result.violations) == 0


# ============================================================================
# SKUEL013: RelationshipName enum
# ============================================================================


class TestSKUEL013:
    def test_detects_magic_string(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter, 'await backend.add_relationship(uid1, "SERVES_GOAL", uid2)'
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL013"

    def test_enum_usage_clean(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter,
            "await backend.add_relationship(uid1, RelationshipName.SERVES_GOAL, uid2)",
        )
        assert len(violations) == 0

    def test_cypher_query_exempt(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(linter, 'query = "MATCH (a)-[:SERVES_GOAL]->(b) RETURN b"')
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL013"])
        content = '"""\nUses "SERVES_GOAL" relationship.\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0


# ============================================================================
# SKUEL014: EntityType enum
# ============================================================================


class TestSKUEL014:
    def test_detects_string_comparison(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "task":')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"

    def test_enum_usage_clean(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, "if entity.entity_type == EntityType.TASK:")
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, '# entity_type == "task"')
        assert len(violations) == 0


# ============================================================================
# SKUEL015: print() in production code
# ============================================================================


class TestSKUEL015:
    def test_detects_print(self) -> None:
        linter = make_linter(["SKUEL015"])
        violations = lint_content(linter, 'print("Hello world")')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL015"

    def test_logger_clean(self) -> None:
        linter = make_linter(["SKUEL015"])
        violations = lint_content(linter, 'logger.info("Hello world")')
        assert len(violations) == 0

    def test_scripts_dir_exempt(self) -> None:
        linter = make_linter(["SKUEL015"])
        fp = Path("/fake/root/scripts/migrate.py")
        rel = Path("scripts/migrate.py")
        content = 'print("Migrating...")'
        lines = content.split("\n")
        linter._check_print_statements(fp, rel, content, lines)
        assert len(linter.result.violations) == 0

    def test_main_block_exempt(self) -> None:
        linter = make_linter(["SKUEL015"])
        content = 'x = 1\nif __name__ == "__main__":\n    print("running")'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL015"])
        violations = lint_content(
            linter,
            'print("debug")  # skuel-lint: disable=SKUEL015 -- CLI output',
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL015"])
        violations = lint_content(
            linter,
            '# skuel-lint: disable-file=SKUEL015 -- CLI tool\nprint("hello")',
        )
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL015"])
        violations = lint_content(linter, '# print("debug")')
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL015"])
        content = '"""\nExample: print("hello")\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0


# ============================================================================
# SKUEL016: Poetry references
# ============================================================================


class TestSKUEL016:
    def test_detects_poetry_install(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "poetry install")
        assert len(violations) == 1
        assert "uv sync" in violations[0].suggestion

    def test_detects_poetry_run(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "poetry run python main.py")
        assert len(violations) == 1
        assert "uv run" in violations[0].suggestion

    def test_detects_poetry_lock(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "COPY poetry.lock .")
        assert len(violations) == 1

    def test_detects_tool_poetry(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "[tool.poetry]")
        assert len(violations) == 1

    def test_uv_clean(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "uv sync")
        assert len(violations) == 0

    def test_migration_comment_exempt(self) -> None:
        linter = make_linter(["SKUEL016"])
        violations = lint_content(linter, "# was poetry install, now migrated to uv")
        assert len(violations) == 0


# ============================================================================
# SKUEL017: Bare except Exception
# ============================================================================


class TestSKUEL017:
    def test_detects_bare_except(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, "    except Exception as e:")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL017"

    def test_specific_exception_clean(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, "    except NEO4J_EXCEPTIONS as e:")
        assert len(violations) == 0

    def test_intentional_broad_comment(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            "    except Exception as e:  # intentional-broad: event handler top-level",
        )
        assert len(violations) == 0

    def test_safety_net_comment(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            "    except Exception as e:  # safety-net: narrowing in progress",
        )
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            "    except Exception as e:  # skuel-lint: disable=SKUEL017 -- top-level handler",
        )
        assert len(violations) == 0

    def test_prev_line_suppression(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = "    # intentional-broad: event bus\n    except Exception as e:"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_scripts_dir_exempt(self) -> None:
        linter = make_linter(["SKUEL017"])
        fp = Path("/fake/root/scripts/migrate.py")
        rel = Path("scripts/migrate.py")
        content = "    except Exception as e:"
        lines = content.split("\n")
        linter._check_broad_exception_catches(fp, rel, content, lines)
        assert len(linter.result.violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = '"""\nexcept Exception as e:\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0
