"""
Tests for SKUEL Unified Linter
===============================

Tests all SKUEL lint rules, LintResult dataclass, and suppression logic.
Uses synthetic string content — no filesystem access needed.
"""

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from lint_skuel import (  # type: ignore[import-not-found]
    LintResult,
    Severity,
    SkuelLinter,
    Violation,
)

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
    is_core = "/core/" in str(fp) and fp.suffix == ".py"

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
    if linter._should_run_rule("SKUEL018") and not is_test:
        linter._check_rich_only_field_access(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL019") and not is_test:
        linter._check_credential_env_reads(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL020") and not is_test:
        linter._check_request_annotation(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL006"):
        linter._check_todo_comments(fp, rel, content, lines)

    # Boundary rules (ADR-044): SKUEL001 (APOC) + SKUEL021 (raw Cypher) run on all
    # of core/ as well as any /services/ path — mirror _lint_file's is_below_boundary.
    is_below_boundary = is_core or is_service
    if is_below_boundary and not is_test:
        if linter._should_run_rule("SKUEL001"):
            linter._check_apoc_in_services(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL021"):
            linter._check_raw_cypher_in_services(fp, rel, content, lines)

    if is_service and not is_test:
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

    if is_adapter and linter._should_run_rule("SKUEL008"):
        linter._check_backend_wrappers(fp, rel, content)

    if is_core and not is_test and linter._should_run_rule("SKUEL022"):
        linter._check_core_imports_adapter(fp, rel, content, lines)

    if is_core and not is_test and linter._should_run_rule("SKUEL023"):
        linter._check_adapter_type_annotations(fp, rel, content, lines)

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
        # APOC is only ever real Python as a string handed to the driver
        # (`CALL apoc...`); there is no importable `apoc` module to call directly.
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'query = "CALL apoc.cypher.run(inner, params)"')
        assert len(violations) == 1

    def test_clean_code_no_violation(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, "query = CypherGenerator.build_chain(uid)")
        assert len(violations) == 0

    def test_detects_apoc_meta(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'query = "CALL apoc.meta.data()"')
        assert len(violations) == 1

    # --- docstring-aware: APOC mentioned in documentation is not a violation ---
    # (the gate now covers all of core/, so prose mentioning a banned proc — e.g. a
    #  doc explaining why APOC is banned — must not trip this CRITICAL rule.)

    def test_skips_apoc_in_module_docstring(self) -> None:
        linter = make_linter(["SKUEL001"])
        content = '"""Cypher only here.\n\nDo NOT use apoc.meta.data() — APOC is adapter-only.\n"""\nx = 1'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_apoc_in_function_docstring(self) -> None:
        linter = make_linter(["SKUEL001"])
        content = (
            "def fetch():\n"
            '    """Fetch nodes.\n\n'
            "    Historically this used apoc.path.subgraphAll; now pure Cypher.\n"
            '    """\n'
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_apoc_in_comment(self) -> None:
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, "# apoc.schema.assert(...) is banned below the boundary")
        assert len(violations) == 0

    def test_skips_apoc_in_inline_comment(self) -> None:
        """An inline comment naming a banned proc on an otherwise-valid code line
        must not trip the rule (scanning string literals, not physical lines)."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(
            linter, "query = CypherGenerator.build_chain(uid)  # never apoc.meta.data() here"
        )
        assert len(violations) == 0

    def test_skips_apoc_in_core_utils_docstring(self) -> None:
        """Same widened-gate concern as SKUEL021: core/utils docstrings may name APOC."""
        linter = make_linter(["SKUEL001"])
        content = '"""Maps rows.\n\n    Avoid apoc.map.fromPairs() — use a dict.\n"""\nrows = []'
        violations = lint_content(
            linter, content, file_path="core/utils/neo4j_mapper.py", is_service=False
        )
        assert len(violations) == 0

    def test_detects_apoc_in_used_string_core_utils(self) -> None:
        """The widened gate still catches a real APOC leak in core/utils (is_core)."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(
            linter,
            'q = "CALL apoc.meta.data()"',
            file_path="core/utils/helper.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].severity == Severity.CRITICAL


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
# SKUEL006: Debt marker detection
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
        fp = Path("/fake/root/adapters/persistence/neo4j/backends/activity_backends.py")
        rel = Path("adapters/persistence/neo4j/backends/activity_backends.py")
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

    def test_flags_stale_lesson_alias(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "lesson":')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"

    def test_flags_interaction_magic_string(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "interaction":')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"


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


# ============================================================================
# SKUEL018: Direct access to RichUserContext RICH_ONLY_FIELDS
# ============================================================================


class TestSKUEL018:
    def test_detects_direct_read(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    if ctx.at_risk_habits:")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL018"
        assert "at_risk_habits" in violations[0].message

    def test_detects_all_six_fields(self) -> None:
        linter = make_linter(["SKUEL018"])
        content = "\n".join(
            [
                "x = ctx.tasks_by_goal",
                "y = ctx.habits_by_goal",
                "z = ctx.at_risk_habits",
                "w = ctx.blocked_task_uids",
                "v = ctx.principle_guided_choice_counts",
                "u = ctx.recent_principle_aligned_choices",
            ]
        )
        violations = lint_content(linter, content)
        assert len(violations) == 6
        flagged = {v.message.split("`.")[1].split("`")[0] for v in violations}
        assert flagged == {
            "tasks_by_goal",
            "habits_by_goal",
            "at_risk_habits",
            "blocked_task_uids",
            "principle_guided_choice_counts",
            "recent_principle_aligned_choices",
        }

    def test_does_not_flag_or_empty_accessor(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    x = ctx.at_risk_habits_or_empty()")
        assert len(violations) == 0

    def test_does_not_flag_get_accessor(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    x = ctx.get_blocked_tasks()")
        assert len(violations) == 0

    def test_does_not_flag_assignment(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    ctx.at_risk_habits = []")
        assert len(violations) == 0

    def test_flags_equality_comparison(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    if ctx.at_risk_habits == ['x']:")
        assert len(violations) == 1

    def test_whitelist_unified_user_context(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(
            linter,
            "    return self.at_risk_habits",
            file_path="core/services/user/unified_user_context.py",
        )
        assert len(violations) == 0

    def test_whitelist_populator(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(
            linter,
            "    context.at_risk_habits = at_risk",
            file_path="core/services/user/user_context_populator.py",
        )
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(
            linter,
            "    x = ctx.at_risk_habits  # skuel-lint: disable=SKUEL018 -- legitimate direct read",
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL018"])
        content = (
            "# skuel-lint: disable-file=SKUEL018 -- migration script\nx = ctx.at_risk_habits\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(
            linter,
            "    context.at_risk_habits = ['x']",
            file_path="tests/unit/test_something.py",
        )
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL018"])
        content = '"""\nAvoid ctx.at_risk_habits\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_suggestion_references_real_accessor(self) -> None:
        """Suggestion text must cite the actual accessor names (e.g. get_blocked_tasks,
        not get_blocked_task_uids)."""
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    x = ctx.blocked_task_uids")
        assert len(violations) == 1
        assert "get_blocked_tasks()" in violations[0].suggestion
        assert "blocked_task_uids_or_empty()" in violations[0].suggestion

    def test_at_risk_habits_cites_reinforcement_accessor(self) -> None:
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    x = ctx.at_risk_habits")
        assert len(violations) == 1
        assert "get_habits_needing_reinforcement()" in violations[0].suggestion

    def test_scalar_field_suggestion_omits_graceful(self) -> None:
        """principle_integration_score has no graceful accessor — suggestion
        must name only the strict accessor and flag standard-depth reads as bugs."""
        linter = make_linter(["SKUEL018"])
        violations = lint_content(linter, "    x = ctx.principle_integration_score")
        assert len(violations) == 1
        suggestion = violations[0].suggestion
        assert "get_principle_integration_score()" in suggestion
        assert "No graceful accessor" in suggestion
        assert "_or_empty" not in suggestion
        assert "_or_zero" not in suggestion


# ============================================================================
# SKUEL019: Credential-shaped env reads bypassing get_credential()
# ============================================================================


class TestSKUEL019:
    # --- Catalog hits (ERROR severity) ---

    def test_detects_os_environ_get_catalog_key(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    key = os.environ.get("OPENAI_API_KEY")')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL019"
        assert violations[0].severity == Severity.ERROR
        assert "OPENAI_API_KEY" in violations[0].message

    def test_detects_os_getenv_catalog_key(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    pw = os.getenv("NEO4J_PASSWORD")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_detects_os_environ_subscript(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    tok = os.environ["HF_API_TOKEN"]')
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "HF_API_TOKEN" in violations[0].message

    def test_catalog_key_with_default_arg(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    key = os.getenv("DEEPGRAM_API_KEY", "")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Pattern hits (WARNING severity) ---

    def test_pattern_password_suffix_warning(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    p = os.getenv("CUSTOM_DB_PASSWORD")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "credential-shaped" in violations[0].message

    def test_pattern_api_key_suffix_warning(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    k = os.getenv("THIRDPARTY_API_KEY")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_pattern_auth_suffix_warning(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    a = os.getenv("NEO4J_AUTH")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_pattern_pat_underscore_warning(self) -> None:
        linter = make_linter(["SKUEL019"])
        # FIREFLY_PAT_PERSONAL is NOT in the catalog mirror as of writing —
        # but actually it IS in the catalog. Use a synthetic name to exercise the regex.
        violations = lint_content(linter, '    p = os.getenv("VENDOR_PAT_PROD")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_pattern_secret_inside_name_warning(self) -> None:
        linter = make_linter(["SKUEL019"])
        # SESSION_SECRET_KEY ends in _SECRET_KEY — `_SECRET_` matches the regex
        # mid-word. SESSION_SECRET_KEY itself is catalogued, so use a synthetic
        # name with the _SECRET_ infix pattern to test the regex independently.
        violations = lint_content(linter, '    s = os.getenv("CUSTOM_SECRET_HANDLE")')
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Non-credential names should pass cleanly ---

    def test_neo4j_uri_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    uri = os.getenv("NEO4J_URI")')
        assert len(violations) == 0

    def test_neo4j_username_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    u = os.getenv("NEO4J_USERNAME")')
        assert len(violations) == 0

    def test_app_port_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    p = os.getenv("APP_PORT", "8000")')
        assert len(violations) == 0

    def test_intelligence_tier_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    t = os.getenv("INTELLIGENCE_TIER", "core")')
        assert len(violations) == 0

    def test_ingestion_path_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    p = os.environ.get("SKUEL_INGESTION_ALLOWED_PATHS")')
        assert len(violations) == 0

    def test_master_key_passes(self) -> None:
        """SKUEL_MASTER_KEY decrypts the Fernet store — it has to come from env,
        and its name doesn't match any credential-shape suffix."""
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    k = os.getenv("SKUEL_MASTER_KEY")')
        assert len(violations) == 0

    def test_credential_backend_selector_passes(self) -> None:
        """SKUEL_CREDENTIAL_BACKEND is the backend selector, not a credential."""
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter, '    b = os.getenv("SKUEL_CREDENTIAL_BACKEND", "").lower()'
        )
        assert len(violations) == 0

    # --- get_credential() calls don't trigger ---

    def test_get_credential_call_passes(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    key = get_credential("OPENAI_API_KEY", fallback_to_env=True)',
        )
        assert len(violations) == 0

    # --- Exempt files (credential plumbing) ---

    def test_credential_store_file_exempt(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    value = os.getenv("OPENAI_API_KEY")',
            file_path="core/config/credential_store.py",
        )
        assert len(violations) == 0

    def test_credential_setup_file_exempt(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    if not os.getenv("SKUEL_MASTER_KEY"):',
            file_path="core/config/credential_setup.py",
        )
        assert len(violations) == 0

    def test_migrate_homedir_script_exempt(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    pw = os.getenv("NEO4J_PASSWORD")',
            file_path="scripts/migrate_secrets_to_homedir.py",
        )
        assert len(violations) == 0

    def test_migrate_keychain_script_exempt(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    pw = os.getenv("NEO4J_PASSWORD")',
            file_path="scripts/migrate_secrets_to_keychain.py",
        )
        assert len(violations) == 0

    # --- Suppression ---

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    key = os.getenv("OPENAI_API_KEY")  # skuel-lint: disable=SKUEL019 -- legacy path',
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL019"])
        content = (
            "# skuel-lint: disable-file=SKUEL019 -- one-off compatibility shim\n"
            'key = os.getenv("OPENAI_API_KEY")\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(
            linter,
            '    monkeypatch.setenv("OPENAI_API_KEY", "test"); k = os.getenv("OPENAI_API_KEY")',
            file_path="tests/unit/test_something.py",
        )
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL019"])
        content = '"""\nDo not call os.getenv("OPENAI_API_KEY") — use get_credential().\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    # legacy code did os.getenv("OPENAI_API_KEY") here')
        assert len(violations) == 0

    # --- Suggestion content ---

    def test_suggestion_includes_get_credential(self) -> None:
        linter = make_linter(["SKUEL019"])
        violations = lint_content(linter, '    k = os.getenv("OPENAI_API_KEY")')
        assert len(violations) == 1
        assert "get_credential" in violations[0].suggestion
        assert "fallback_to_env=True" in violations[0].suggestion
        assert "OPENAI_API_KEY" in violations[0].suggestion

    # --- Multiple hits in one file ---

    def test_multiple_hits_one_file(self) -> None:
        linter = make_linter(["SKUEL019"])
        content = "\n".join(
            [
                'k1 = os.getenv("OPENAI_API_KEY")',
                'k2 = os.environ.get("HF_API_TOKEN")',
                'k3 = os.environ["NEO4J_PASSWORD"]',
            ]
        )
        violations = lint_content(linter, content)
        assert len(violations) == 3
        assert all(v.severity == Severity.ERROR for v in violations)


# ============================================================================
# SKUEL019: Catalog drift test
# ============================================================================


class TestCredentialCatalogDrift:
    """The linter mirrors the credential catalog from credential_setup.py.
    If those drift, lint coverage silently loses the new credentials.
    """

    def test_linter_catalog_matches_credential_setup(self) -> None:
        # Import inside the test so collection still works in environments
        # where core/ isn't importable (e.g. minimal CI lint runners).
        from core.config.credential_setup import CredentialSetup

        actual = set(CredentialSetup.CREDENTIALS.keys())
        mirrored = set(SkuelLinter.CREDENTIAL_CATALOG)

        missing = actual - mirrored
        extra = mirrored - actual
        assert not missing, (
            f"SkuelLinter.CREDENTIAL_CATALOG is missing keys present in "
            f"CredentialSetup.CREDENTIALS: {sorted(missing)}. "
            f"Add them to scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG."
        )
        assert not extra, (
            f"SkuelLinter.CREDENTIAL_CATALOG has keys not in "
            f"CredentialSetup.CREDENTIALS: {sorted(extra)}. "
            f"Remove them from scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG "
            f"(or add them to CredentialSetup.CREDENTIALS if they're real credentials)."
        )


# ============================================================================
# SKUEL020: FastHTML @rt handlers must annotate request: Request
# ============================================================================


class TestSKUEL020:
    def test_detects_request_any_on_rt_handler(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = (
            '@rt("/manifest.json")\nasync def pwa_manifest(request: Any) -> Any:\n    return None\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL020"
        assert violations[0].severity == Severity.ERROR
        assert "pwa_manifest" in violations[0].message
        assert "request: Any" in violations[0].message

    def test_detects_app_get_handler(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = (
            '@app.get("/ui/analytics")\nasync def dash(request: Any) -> Any:\n    return None\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_detects_app_post_handler(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = '@app.post("/x")\nasync def create(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_detects_nested_factory_handler(self) -> None:
        """The bug bit factory-generated nested handlers (ai_routes _make_*_route)."""
        linter = make_linter(["SKUEL020"])
        content = (
            "def make_route(rt, path):\n"
            "    @rt(path)\n"
            "    async def handler(request: Any, uid: str) -> Any:\n"
            "        return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert "handler" in violations[0].message

    def test_request_annotation_clean(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: Request) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_qualified_request_annotation_clean(self) -> None:
        """`starlette.requests.Request` (Attribute) is also a real Request class."""
        linter = make_linter(["SKUEL020"])
        content = (
            '@rt("/x")\nasync def h(request: starlette.requests.Request) -> Any:\n    return None\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_unannotated_request_clean(self) -> None:
        """FastHTML injects the request when there is no annotation."""
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_undecorated_helper_not_flagged(self) -> None:
        """A non-@rt helper with `request: Any` is never bound by FastHTML."""
        linter = make_linter(["SKUEL020"])
        content = (
            '@rt("/x")\n'
            "async def route_h(request: Request) -> Any:\n"
            "    return None\n"
            "\n"
            "def helper(request: Any) -> Any:\n"
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = (
            '@rt("/x")\n'
            "async def h(request: Any) -> Any:  # skuel-lint: disable=SKUEL020 -- legacy shim\n"
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = (
            "# skuel-lint: disable-file=SKUEL020 -- generated routes\n"
            '@rt("/x")\n'
            "async def h(request: Any) -> Any:\n"
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content, file_path="tests/unit/test_routes.py")
        assert len(violations) == 0

    def test_suggestion_names_runtime_import(self) -> None:
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert "request: Request" in violations[0].suggestion
        assert "from adapters.inbound.fasthtml_types import Request" in violations[0].suggestion

    # --- annotation matching is precise (loose `*.Request` tail is rejected) ---

    def test_non_starlette_attribute_request_flagged(self) -> None:
        """`request: foo.Request` is not a real Starlette Request — it would 400, so
        the loose `*.Request` tail must NOT be accepted (mirrors the SKUEL022 fix)."""
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: foo.Request) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL020"
        assert "foo.Request" in violations[0].message

    def test_string_forward_ref_non_request_flagged(self) -> None:
        """The string-forward-ref form is held to the same allowlist."""
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: "weird.Request") -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL020"

    def test_string_forward_ref_bare_request_clean(self) -> None:
        """`request: "Request"` (string) names the canonical class — exempt."""
        linter = make_linter(["SKUEL020"])
        content = '@rt("/x")\nasync def h(request: "Request") -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_string_forward_ref_qualified_request_clean(self) -> None:
        """`request: "starlette.requests.Request"` (string) is the real class — exempt."""
        linter = make_linter(["SKUEL020"])
        content = (
            '@rt("/x")\n'
            'async def h(request: "starlette.requests.Request") -> Any:\n'
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    # --- decorator matching is precise ---

    def test_websocket_decorator_not_treated_as_route(self) -> None:
        """`@app.ws(...)` registers a websocket handler (no `request` injection), so
        its `request: Any` is NOT the SKUEL020 400 hazard and must not be flagged."""
        linter = make_linter(["SKUEL020"])
        content = '@app.ws("/x")\nasync def h(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_non_routing_attribute_not_treated_as_route(self) -> None:
        """An arbitrary `@app.middleware`-style attr is not a routing verb."""
        linter = make_linter(["SKUEL020"])
        content = '@app.middleware("http")\nasync def h(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_routing_verb_on_unknown_base_not_matched(self) -> None:
        """`@blueprint.get(...)` uses a routing verb but the base is not `app`/`rt`,
        so it is not the FastHTML router and is not matched."""
        linter = make_linter(["SKUEL020"])
        content = '@blueprint.get("/x")\nasync def h(request: Any) -> Any:\n    return None\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_rt_name_decorator_matches_by_convention(self) -> None:
        """`@rt` (Name) is always treated as the FastHTML router. The AST cannot tell a
        rebound local `rt` from the real router, and the repo convention is `rt` == the
        router, so this is accepted (a non-router `@rt` would be a deliberate misnomer)."""
        linter = make_linter(["SKUEL020"])
        content = "@rt\nasync def h(request: Any) -> Any:\n    return None\n"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL020"


# ============================================================================
# SKUEL021: No raw Cypher above the hexagonal boundary (ADR-044)
# ============================================================================


class TestSKUEL021:
    # --- Real (used) Cypher IS flagged, in core/services, core/utils, core/models ---

    def test_detects_assigned_cypher_in_services(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'query = "MATCH (n:Task) RETURN n"')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"
        assert violations[0].severity == Severity.ERROR

    def test_detects_cypher_in_core_utils(self) -> None:
        """The widened gate covers core/utils (is_core), not just /services/."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter,
            'q = "MERGE (a:Node {uid: $uid})"',
            file_path="core/utils/helper.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_detects_cypher_in_core_models(self) -> None:
        """The widened gate covers core/models too (search_request relocation, PR #78)."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter,
            'def build(self) -> str:\n    return "OPTIONAL MATCH (e)-[r]->(t) RETURN t"',
            file_path="core/models/search_request.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_detects_used_fstring_cypher(self) -> None:
        """A marker interpolated into an f-string is still authored Cypher."""
        linter = make_linter(["SKUEL021"])
        content = "uid = 1\nq = f'MATCH (n) WHERE n.id = {uid} RETURN n'\nrun(q)"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_detects_cypher_passed_as_argument(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'self.backend.run("CREATE (n:Foo {x: 1})")')
        assert len(violations) == 1

    def test_detects_returned_cypher(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter, 'def q() -> str:\n    return "UNWIND $items AS item RETURN item"'
        )
        assert len(violations) == 1

    def test_call_db_marker(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "CALL db.index.vector.queryNodes($idx, 5, $vec)"')
        assert len(violations) == 1

    # --- Inert documentation Cypher is NOT flagged (the docstring-aware core) ---

    def test_skips_module_docstring_cypher(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = '"""Example query.\n\n    MATCH (n:Task) RETURN n\n"""\nx = 1'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_function_docstring_cypher(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = (
            "def fetch():\n"
            '    """Fetch tasks.\n\n'
            "    Example:\n"
            "        MERGE (a:Node)-[:USES]->(b)\n"
            '    """\n'
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_bare_usage_examples_block(self) -> None:
        """A mid-body bare-string ``USAGE EXAMPLES`` block legitimately quotes Cypher."""
        linter = make_linter(["SKUEL021"])
        content = (
            "def f():\n"
            "    x = 1\n"
            '    """\n'
            "    USAGE EXAMPLES:\n"
            "        OPTIONAL MATCH (a)-[r]->(b)\n"
            '    """\n'
            "    return x\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_cypher_in_core_utils_docstring(self) -> None:
        """The reason PR #75 used an AST test instead of widening the line-scan:
        core/utils docstrings legitimately quote Cypher and must not trip the rule."""
        linter = make_linter(["SKUEL021"])
        content = '"""Maps rows.\n\n    MATCH (n) RETURN n\n"""\nrows = []'
        violations = lint_content(
            linter, content, file_path="core/utils/neo4j_mapper.py", is_service=False
        )
        assert len(violations) == 0

    def test_skips_comment_cypher(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, "# old query was MATCH (n) RETURN n")
        assert len(violations) == 0

    # --- Suppression ---

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter,
            'q = "MATCH (n) RETURN n"  # skuel-lint: disable=SKUEL021 -- below-boundary shim',
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = (
            "# skuel-lint: disable-file=SKUEL021 -- generated query module\n"
            'q = "MATCH (n) RETURN n"\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    # --- Granularity ---

    def test_multiline_query_reports_once(self) -> None:
        """A single triple-quoted query with several clauses is one violation."""
        linter = make_linter(["SKUEL021"])
        content = 'q = """\nMATCH (a)\nMERGE (b)\nCREATE (c)\n"""\nrun(q)'
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_clean_service_no_violation(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, "result = await self.backend.get_tasks(user_uid)")
        assert len(violations) == 0


# ============================================================================
# SKUEL022: core/ must not import adapters/ (dependency direction, ADR-044)
# ============================================================================


class TestSKUEL022:
    def test_detects_module_level_from_import(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = "from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL022"
        assert violations[0].severity == Severity.ERROR
        assert "cross_domain_backend" in violations[0].message

    def test_detects_plain_import(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = "import adapters.persistence.neo4j.cross_domain_backend\n"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL022"

    def test_detects_function_local_import(self) -> None:
        """A function-local import is the same runtime dependency, just deferred."""
        linter = make_linter(["SKUEL022"])
        content = (
            "def build(executor):\n"
            "    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend\n"
            "    return PsEngagementBackend(executor)\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL022"
        assert violations[0].line_number == 2

    def test_type_checking_import_exempt(self) -> None:
        """An import under `if TYPE_CHECKING:` never executes — no runtime dependency."""
        linter = make_linter(["SKUEL022"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_typing_dot_type_checking_exempt(self) -> None:
        """`if typing.TYPE_CHECKING:` (Attribute form) is also exempt."""
        linter = make_linter(["SKUEL022"])
        content = (
            "import typing\n"
            "\n"
            "if typing.TYPE_CHECKING:\n"
            "    from adapters.outbound.invoice_renderer import render_invoice_pdf\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_else_branch_of_type_checking_not_exempt(self) -> None:
        """An adapter import in the `else:` of a TYPE_CHECKING block DOES execute."""
        linter = make_linter(["SKUEL022"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.user_backend import UserBackend\n"
            "else:\n"
            "    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 6  # the else-branch import, not the if-body one

    def test_non_typing_attribute_guard_not_exempt(self) -> None:
        """`if settings.TYPE_CHECKING:` is a runtime guard, not the typing sentinel."""
        linter = make_linter(["SKUEL022"])
        content = (
            "if settings.TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.user_backend import UserBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL022"

    def test_relative_import_not_flagged(self) -> None:
        """`from . import x` (relative, within core) is not an adapters import."""
        linter = make_linter(["SKUEL022"])
        content = "from . import sibling_module\nfrom .helpers import thing\n"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_non_adapter_import_clean(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = "from core.ports import BackendOperations\nimport core.constants\n"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_adapter_file_not_flagged(self) -> None:
        """Only core/ files are checked — adapters importing adapters is fine."""
        linter = make_linter(["SKUEL022"])
        content = "from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        violations = lint_content(
            linter, content, file_path="adapters/persistence/neo4j/foo.py", is_service=False
        )
        assert len(violations) == 0

    def test_composition_root_not_flagged(self) -> None:
        """services_bootstrap/ is the composition root — it SHOULD import adapters."""
        linter = make_linter(["SKUEL022"])
        content = "from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        violations = lint_content(
            linter, content, file_path="services_bootstrap/compose.py", is_service=False
        )
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = "from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        violations = lint_content(
            linter, content, file_path="core/services/test_example.py", is_service=False
        )
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = (
            "from adapters.persistence.neo4j.x import Y  "
            "# skuel-lint: disable=SKUEL022 -- composition factory below the boundary\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = (
            "# skuel-lint: disable-file=SKUEL022 -- composition helper\n"
            "from adapters.persistence.neo4j.x import Y\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    # --- the orelse/exemption boundary is exact (the compound-node-walk bug class) ---

    def test_elif_after_type_checking_not_exempt(self) -> None:
        """`elif` (an `If` in the outer `orelse`) executes at runtime — its adapter
        import is flagged, even though the leading `if TYPE_CHECKING:` body is exempt."""
        linter = make_linter(["SKUEL022"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.user_backend import UserBackend\n"
            "elif FEATURE_FLAG:\n"
            "    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 6  # the elif-branch import only

    def test_try_and_except_bodies_both_flagged(self) -> None:
        """Imports in both the `try` and `except` bodies execute at runtime."""
        linter = make_linter(["SKUEL022"])
        content = (
            "try:\n"
            "    from adapters.persistence.neo4j.fast_backend import FastBackend\n"
            "except ImportError:\n"
            "    from adapters.persistence.neo4j.slow_backend import SlowBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 2
        assert {v.line_number for v in violations} == {2, 4}

    def test_with_block_import_flagged(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = (
            "with open_context() as ctx:\n"
            "    from adapters.persistence.neo4j.user_backend import UserBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 2

    def test_for_block_import_flagged(self) -> None:
        linter = make_linter(["SKUEL022"])
        content = (
            "for name in modules:\n"
            "    from adapters.persistence.neo4j.user_backend import UserBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 2

    def test_nested_if_else_under_type_checking_fully_exempt(self) -> None:
        """A whole nested `if/else` *inside* a TYPE_CHECKING body never executes — both
        branches are exempt. Confirms the body walk still descends into nested
        structures (the legitimate use) while not leaking across sibling fields."""
        linter = make_linter(["SKUEL022"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    if USE_FAST:\n"
            "        from adapters.persistence.neo4j.fast_backend import FastBackend\n"
            "    else:\n"
            "        from adapters.persistence.neo4j.slow_backend import SlowBackend\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0


# ============================================================================
# SKUEL023 — Type Against ports, Not Adapter Classes
# ============================================================================


class TestSKUEL023:
    """Static type-direction enforcement: thin services in core/ must type
    self.backend against a core/ports protocol, not the concrete adapter
    class. Closes the TYPE_CHECKING exemption gap left open by SKUEL022."""

    def test_flags_instance_attribute_annotation(self) -> None:
        """The canonical violation: `self.backend: KuBackend = backend` typed
        against the concrete adapter (even with a TYPE_CHECKING-only import)."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            "    def __init__(self, backend) -> None:\n"
            "        self.backend: XBackend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL023"
        assert violations[0].severity == Severity.ERROR
        assert "XBackend" in violations[0].message

    def test_flags_init_param_forward_ref(self) -> None:
        """A forward-reference string annotation on an `__init__` param is parsed."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1
        assert "XBackend" in violations[0].message

    def test_flags_runtime_adapter_import(self) -> None:
        """The import doesn't need to be TYPE_CHECKING-only — a runtime adapter
        import (which SKUEL022 already flags) plus an annotation is also a
        SKUEL023 violation."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            "    def __init__(self, backend: XBackend) -> None:\n"
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1

    def test_flags_optional_subscript(self) -> None:
        """`XBackend | None` (PEP 604) annotation still resolves to XBackend."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XBackend | None" = None) -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1

    def test_clean_when_protocol_typed(self) -> None:
        """The fix: type against the port protocol — no violation."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from core.ports.x_protocols import XOperations\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XOperations") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_suffix_heuristic_excludes_enum(self) -> None:
        """A name ending in something OTHER than the backend-shaped suffixes is
        not flagged — pure-data adapter exports (enums, configs, dataclasses)
        legitimately cross the boundary as types.

        This is the QueryOptimizationStrategy-shaped case that motivated the
        suffix heuristic — naming it explicitly to lock in the contract."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.optimizer import QueryOptimizationStrategy\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, strategy: "QueryOptimizationStrategy") -> None:\n'
            "        self.strategy = strategy\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_each_backend_suffix_is_flagged(self) -> None:
        """Backend / Executor / Adapter / Repository / Client / Driver all
        trigger the rule — the full suffix heuristic."""
        names = ["XBackend", "XExecutor", "XAdapter", "XRepository", "XClient", "XDriver"]
        for name in names:
            sub_linter = make_linter(["SKUEL023"])
            content = (
                "from typing import TYPE_CHECKING\n"
                "\n"
                "if TYPE_CHECKING:\n"
                f"    from adapters.persistence.neo4j.x import {name}\n"
                "\n"
                "class XService:\n"
                f'    def __init__(self, backend: "{name}") -> None:\n'
                "        self.backend = backend\n"
            )
            violations = lint_content(sub_linter, content, file_path="core/services/x_service.py")
            assert len(violations) == 1, f"{name} should be flagged"

    def test_facade_allowlist_directory_prefix(self) -> None:
        """Files under the facade directory prefixes are exempt entirely —
        facades may keep concrete backend typing per CLAUDE.md '## Protocol-
        Based Architecture'."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.ku_backend import KuBackend\n"
            "\n"
            "class KuCoreService:\n"
            '    def __init__(self, backend: "KuBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/ku/ku_core_service.py")
        assert len(violations) == 0

    def test_facade_allowlist_explicit_file(self) -> None:
        """The standalone facade files (ku_service.py, user_service.py) are
        explicitly allowlisted."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.ku_backend import KuBackend\n"
            "\n"
            "class KuService:\n"
            '    def __init__(self, backend: "KuBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/ku_service.py")
        assert len(violations) == 0

    def test_relative_import_not_an_adapter_import(self) -> None:
        """A `from . import x` is not an adapters import — the import map is
        empty and no annotation can be flagged against it."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from .helpers import XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_non_core_file_not_flagged(self) -> None:
        """The rule runs only on core/ — adapters files annotating against
        adapter classes is fine."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XComposer:\n"
            '    def __init__(self, backend: "XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(
            linter, content, file_path="adapters/persistence/neo4j/x_composer.py", is_service=False
        )
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        """Test files under tests/ are skipped — tests legitimately import
        adapter classes for instantiation."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class TestX:\n"
            "    def test_x(self) -> None:\n"
            "        backend: XBackend = XBackend()\n"
        )
        violations = lint_content(
            linter, content, file_path="tests/unit/test_x.py", is_service=False
        )
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        """`# skuel-lint: disable=SKUEL023 -- ...` on the annotation line suppresses."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XBackend") -> None:  '
            "# skuel-lint: disable=SKUEL023 -- protocol not yet defined\n"
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        """File-level suppression disables the rule for the entire file."""
        linter = make_linter(["SKUEL023"])
        content = (
            "# skuel-lint: disable-file=SKUEL023 -- legacy concrete typing tracked elsewhere\n"
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_no_adapter_mention_short_circuits(self) -> None:
        """The cheap pre-filter — files that don't mention adapters at all are
        skipped before the AST walk."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from core.ports import BackendOperations\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "BackendOperations") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 0

    def test_aliased_import(self) -> None:
        """`from adapters... import XBackend as _XB` — the local name is _XB
        and the rule keys on local names; annotating with _XB triggers."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend as _XBackend\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "_XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1

    def test_function_param_outside_init(self) -> None:
        """Param annotations on any function (not just __init__) are checked."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "def make_thing(backend: XBackend) -> None:\n"
            "    pass\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1

    # -------------------------------------------------------------------------
    # Tier 2: module-style alias imports (`import adapters.x as xb`).
    # The annotation walker must reach the root Name through the Attribute
    # chain; without that fix the tail ("XBackend") wouldn't be in the import
    # map and the violation would be silently skipped.
    # -------------------------------------------------------------------------

    def test_flags_module_style_alias_attribute_annotation(self) -> None:
        """`import adapters.x as xb` + `self.backend: xb.XBackend` (Attribute)."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    import adapters.persistence.neo4j.x_backend as xb\n"
            "\n"
            "class XService:\n"
            "    def __init__(self, backend: object) -> None:\n"
            "        self.backend: xb.XBackend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1
        assert "XBackend" in violations[0].message
        assert "adapters.persistence.neo4j.x_backend" in violations[0].message

    def test_flags_module_style_alias_forward_ref(self) -> None:
        """Same bypass via a string forward-ref: `backend: "xb.XBackend"`."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    import adapters.persistence.neo4j.x_backend as xb\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "xb.XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1

    def test_module_style_alias_to_non_backend_name_not_flagged(self) -> None:
        """`xb.SomeConfig` — root in import map, tail not a backend suffix."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    import adapters.persistence.neo4j.x_backend as xb\n"
            "\n"
            "class XService:\n"
            "    def __init__(self, config: object) -> None:\n"
            "        self.config: xb.SomeConfig = config\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert violations == []

    def test_typing_attribute_not_flagged(self) -> None:
        """`typing.Optional` is an Attribute chain whose root isn't an adapter
        import — must not be flagged just because Attribute walking is on."""
        linter = make_linter(["SKUEL023"])
        content = (
            "import typing\n"
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend\n"
            "\n"
            "class XService:\n"
            "    field: typing.Optional[str] = None\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert violations == []

    # -------------------------------------------------------------------------
    # Tier 3: fully-qualified forward-ref strings with NO adapter import.
    # The check must fire even when `adapter_imports` is empty because the
    # parsed Attribute chain's root Name is the literal "adapters".
    # -------------------------------------------------------------------------

    def test_flags_fully_qualified_forward_ref_without_import(self) -> None:
        """`backend: "adapters.x.XBackend"` — no TYPE_CHECKING import at all."""
        linter = make_linter(["SKUEL023"])
        content = (
            "class XService:\n"
            '    def __init__(self, backend: "adapters.persistence.neo4j.x_backend.XBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert len(violations) == 1
        assert "XBackend" in violations[0].message
        # The display "module" for Tier 3 is the synthetic adapters.* — verify
        # we don't claim a real module path that wasn't imported.
        assert "adapters.*" in violations[0].message

    def test_fully_qualified_non_backend_not_flagged(self) -> None:
        """`backend: "adapters.x.SomeEnum"` — suffix heuristic still gates Tier 3."""
        linter = make_linter(["SKUEL023"])
        content = (
            'class XService:\n    field: "adapters.persistence.neo4j.x_backend.SomeEnum" = None\n'
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert violations == []

    def test_fully_qualified_in_facade_allowlist_not_flagged(self) -> None:
        """Facade allowlist applies before any tier check — covers Tier 3."""
        linter = make_linter(["SKUEL023"])
        content = (
            "class KuService:\n"
            '    def __init__(self, backend: "adapters.persistence.neo4j.backends.curriculum_backends.KuBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/ku_service.py")
        assert violations == []
