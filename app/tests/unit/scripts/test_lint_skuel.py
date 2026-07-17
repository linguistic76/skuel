"""
Tests for SKUEL Unified Linter
===============================

Tests all SKUEL lint rules, LintResult dataclass, and suppression logic.
Uses synthetic string content — no filesystem access needed.
"""

import ast
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
    is_ui = "/ui/" in str(fp) and fp.suffix == ".py"

    # Shared parse — mirrors _lint_file: AST rules receive one tree per file,
    # None on syntax error (they skip; ruff owns syntax errors).
    try:
        tree: ast.Module | None = ast.parse(content)
    except SyntaxError:
        tree = None

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
        linter._check_broad_exception_catches(fp, rel, content, lines, tree)
    if linter._should_run_rule("SKUEL018") and not is_test:
        linter._check_rich_only_field_access(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL019") and not is_test:
        linter._check_credential_env_reads(fp, rel, content, lines)
    if linter._should_run_rule("SKUEL020") and not is_test:
        linter._check_request_annotation(fp, rel, content, lines, tree)
    if linter._should_run_rule("SKUEL024") and not is_test:
        linter._check_cls_kwargs_collision(fp, rel, content, lines, tree)
    if linter._should_run_rule("SKUEL025") and not is_test:
        linter._check_deleted_activity_update_payloads(fp, rel, content, lines, tree)
    if linter._should_run_rule("SKUEL006"):
        linter._check_todo_comments(fp, rel, content, lines)

    # Boundary rules (ADR-044): SKUEL001 (APOC) + SKUEL021 (raw Cypher) run on all
    # of core/ as well as any /services/ path — mirror _lint_file's is_below_boundary.
    is_below_boundary = is_core or is_service
    if is_below_boundary and not is_test:
        if linter._should_run_rule("SKUEL001"):
            linter._check_apoc_in_services(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL021"):
            linter._check_raw_cypher_in_services(fp, rel, content, lines, tree)

    if is_service and not is_test:
        if linter._should_run_rule("SKUEL002"):
            linter._check_semantic_type_strings(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL005"):
            linter._check_result_return_types(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL007"):
            linter._check_string_result_fail(fp, rel, content, lines)
        if linter._should_run_rule("SKUEL013"):
            linter._check_relationship_name_strings(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL014"):
            linter._check_entity_type_strings(fp, rel, content, lines, tree)

    if is_adapter and linter._should_run_rule("SKUEL008"):
        linter._check_backend_wrappers(fp, rel, content)

    if is_core and not is_test and linter._should_run_rule("SKUEL022"):
        linter._check_core_imports_adapter(fp, rel, content, lines, tree)

    if is_core and not is_test and linter._should_run_rule("SKUEL023"):
        linter._check_adapter_type_annotations(fp, rel, content, lines, tree)

    if is_ui and not is_test and linter._should_run_rule("SKUEL027"):
        linter._check_ui_imports_adapter(fp, rel, content, lines, tree)

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

    def test_quoted_name_in_docstring_clean(self) -> None:
        # The old quote-counting heuristic flagged quoted names in docstrings.
        linter = make_linter(["SKUEL002"])
        content = 'def f() -> None:\n    """Pass "BUILDS_ON_FOUNDATION" to the builder."""\n'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_embedded_in_longer_string_clean(self) -> None:
        # Exact-value matching: a name inside a longer string is prose, not the enum.
        linter = make_linter(["SKUEL002"])
        violations = lint_content(linter, 'msg = "edge BUILDS_ON_FOUNDATION missing"')
        assert len(violations) == 0

    def test_multiline_arg_now_caught(self) -> None:
        linter = make_linter(["SKUEL002"])
        content = 'link(\n    "ANALOGOUS_TO",\n)'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 2


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
# SKUEL005: Result[T] return types
# ============================================================================


class TestSKUEL005:
    def test_service_method_without_result(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "class S:\n    async def get_tasks(self, uid: str) -> list[Task]:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL005"

    def test_service_method_with_result(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n    async def get_tasks(self, uid: str) -> Result[list[Task]]:\n        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_bare_result_and_optional_result_clean(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n"
            "    async def a(self) -> Result:\n"
            "        pass\n"
            '    async def b(self) -> "Result[Task] | None":\n'
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_result_lookalike_names_still_flagged(self) -> None:
        # Word-bounded match: LintResult / Results are not Result.
        linter = make_linter(["SKUEL005"])
        content = "class S:\n    async def scan(self) -> LintResult:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_multiline_signature_now_caught(self) -> None:
        # The old check fired only when "async def" and "->" shared a physical
        # line — every formatter-wrapped signature was invisible.
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n"
            "    async def create_entity(\n"
            "        self,\n"
            "        title: str,\n"
            "        description: str,\n"
            "    ) -> dict[str, str]:\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 2
        assert violations[0].suppression_span == (2, 6)

    def test_private_method_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "class S:\n    async def _get_internal(self) -> Task:\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_unannotated_method_not_flagged(self) -> None:
        # Missing annotations are mypy's job (disallow_untyped_defs).
        linter = make_linter(["SKUEL005"])
        content = "class S:\n    async def fire(self):\n        pass"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_nested_helper_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n"
            "    async def run(self) -> Result[None]:\n"
            "        async def helper() -> int:\n"
            "            return 1\n"
            "        return await helper()"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_classmethod_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = "class S:\n    @classmethod\n    async def build(cls) -> S:\n        return cls()"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_utility_names_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "class Cache:\n"
            "    async def get(self, key: str) -> str:\n"
            "        pass\n"
            "    async def handle_event(self, e: Event) -> None:\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "# skuel-lint: disable-file=SKUEL005 -- protocol file\n"
            "class S:\n"
            "    async def get_tasks(self, uid: str) -> list[Task]:\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n"
            "    async def publish(self, msg: str) -> None:  # skuel-lint: disable=SKUEL005 -- fire-and-forget\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_suppression_on_wrapped_signature_end_honored(self) -> None:
        # ruff-format strands a long trailing suppression on the `) -> X:` line
        # (the #590 class); the whole def header honors it.
        linter = make_linter(["SKUEL005"])
        content = (
            "class S:\n"
            "    async def publish(\n"
            "        self,\n"
            "        msg: str,\n"
            "    ) -> None:  # skuel-lint: disable=SKUEL005 -- fire-and-forget\n"
            "        pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_protocol_file_exempt(self) -> None:
        linter = make_linter(["SKUEL005"])
        fp = Path("/fake/root/core/ports/domain_protocols.py")
        rel = Path("core/ports/domain_protocols.py")
        content = "class S:\n    async def get_tasks(self, uid: str) -> list[Task]:\n        pass"
        lines = content.split("\n")
        linter._check_result_return_types(fp, rel, content, lines, ast.parse(content))
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

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(linter, 'x = 1  # pass "SERVES_GOAL" here')
        assert len(violations) == 0

    def test_multiline_call_now_caught(self) -> None:
        # The old rule's 10-line Cypher-context lookback could swallow real
        # violations near any line containing "MATCH"; the AST rule flags the
        # used literal regardless of surrounding text.
        linter = make_linter(["SKUEL013"])
        content = (
            "# a comment mentioning MATCH above the call\n"
            "await backend.add_relationship(\n"
            "    uid1,\n"
            '    "SERVES_GOAL",\n'
            "    uid2,\n"
            ")"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 4


# ============================================================================
# SKUEL014: EntityType enum
# ============================================================================


class TestSKUEL014:
    def test_detects_string_comparison(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "task":\n    pass')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"

    def test_enum_usage_clean(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, "if entity.entity_type == EntityType.TASK:\n    pass")
        assert len(violations) == 0

    def test_enum_value_comparison_exempt(self) -> None:
        # EntityType referenced inside the Compare — the enum is already in play.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'ok = EntityType.TASK.value == "task"')
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, '# entity_type == "task"')
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(
            linter, '"""Example: entity_type == "task" routes to TasksService."""'
        )
        assert len(violations) == 0

    def test_flags_membership_string_left_of_in(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if "task" in contexts:\n    pass')
        assert len(violations) == 1

    def test_flags_membership_in_literal_container(self) -> None:
        # Old line-regex missed the container form entirely.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type in ("task", "goal"):\n    pass')
        assert len(violations) == 1

    def test_multiline_container_now_caught(self) -> None:
        # Wrapped comparisons were invisible to the old single-line regex.
        linter = make_linter(["SKUEL014"])
        content = 'if entity_type in (\n    "task",\n    "goal",\n):\n    pass'
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_plain_string_literal_not_flagged(self) -> None:
        # "task" outside a comparison (log message, dict key) is not a discriminator.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'logger.info("task completed")\nd = {"task": 1}')
        assert len(violations) == 0

    def test_flags_stale_lesson_alias(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "lesson":\n    pass')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"

    def test_flags_interaction_magic_string(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'if entity_type == "interaction":\n    pass')
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


def try_except(except_clause: str, prefix: str = "") -> str:
    """Build a minimal valid try/except snippet around the given except clause."""
    return f"try:\n    x()\n{prefix}{except_clause}\n    pass"


class TestSKUEL017:
    def test_detects_bare_except(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, try_except("except Exception as e:"))
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL017"
        assert violations[0].line_number == 3

    def test_specific_exception_clean(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, try_except("except NEO4J_EXCEPTIONS as e:"))
        assert len(violations) == 0

    def test_wrapped_except_now_caught(self) -> None:
        # Formatter-wrapped `except (\n Exception\n) as e:` was invisible to the
        # old single-line regex.
        linter = make_linter(["SKUEL017"])
        content = "try:\n    x()\nexcept (\n    Exception\n) as e:\n    pass"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 3
        assert violations[0].suppression_span == (3, 5)

    def test_exception_inside_tuple_caught(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, try_except("except (ValueError, Exception) as e:"))
        assert len(violations) == 1

    def test_bare_colon_except_not_this_rules_territory(self) -> None:
        # `except:` is ruff E722's job.
        linter = make_linter(["SKUEL017"])
        violations = lint_content(linter, try_except("except:"))
        assert len(violations) == 0

    def test_intentional_broad_comment(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            try_except("except Exception as e:  # intentional-broad: event handler top-level"),
        )
        assert len(violations) == 0

    def test_safety_net_comment(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            try_except("except Exception as e:  # safety-net: narrowing in progress"),
        )
        assert len(violations) == 0

    def test_marker_inside_wrapped_clause_honored(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = (
            "try:\n"
            "    x()\n"
            "except (\n"
            "    Exception\n"
            ") as e:  # intentional-broad: monadic boundary\n"
            "    pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL017"])
        violations = lint_content(
            linter,
            try_except(
                "except Exception as e:  # skuel-lint: disable=SKUEL017 -- top-level handler"
            ),
        )
        assert len(violations) == 0

    def test_suppression_on_wrapped_clause_end_honored(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = (
            "try:\n"
            "    x()\n"
            "except (\n"
            "    Exception\n"
            ") as e:  # skuel-lint: disable=SKUEL017 -- top-level handler\n"
            "    pass"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_prev_line_suppression(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = try_except("except Exception as e:", prefix="# intentional-broad: event bus\n")
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL017"])
        content = "# skuel-lint: disable-file=SKUEL017 -- boundary module\n" + try_except(
            "except Exception as e:"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_scripts_dir_exempt(self) -> None:
        linter = make_linter(["SKUEL017"])
        fp = Path("/fake/root/scripts/migrate.py")
        rel = Path("scripts/migrate.py")
        content = try_except("except Exception as e:")
        lines = content.split("\n")
        linter._check_broad_exception_catches(fp, rel, content, lines, ast.parse(content))
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

    def test_relative_sibling_named_adapters_not_flagged(self) -> None:
        """`from .adapters import x` — a sibling module that happens to be named
        `adapters` has `node.module == "adapters"` but `level == 1`; only top-level
        (`level == 0`) imports target the adapters/ package (Codex P2 on #656)."""
        linter = make_linter(["SKUEL022"])
        content = "from .adapters import convert\nfrom ..adapters.helpers import thing\n"
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

    def test_aliased_import_flagged_at_both_sites(self) -> None:
        """`from adapters... import XBackend as _XBackend` — under Tier 4, the
        import-site rule fires on the alias itself; the annotation-site check
        also fires because `_XBackend` ends in `Backend`. Two violations total."""
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
        assert len(violations) == 2
        import_v = [v for v in violations if v.line_number == 4]
        assert len(import_v) == 1
        assert "aliases adapter import" in import_v[0].message

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
    # Tier 2: module-style imports (`import adapters.x [as xb]`).
    # Tier 4 closed this structurally at the import site: any module-style
    # adapter import in core/ is banned regardless of alias. The annotation-
    # walker Attribute logic remains as defense in depth.
    # -------------------------------------------------------------------------

    def test_flags_module_style_alias_attribute_annotation(self) -> None:
        """`import adapters.x as xb` + `self.backend: xb.XBackend` — two
        violations: import-site (module-style banned) + annotation (Attribute
        walk catches the concrete-adapter reference)."""
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
        assert len(violations) == 2
        import_v = [v for v in violations if v.line_number == 4]
        assert len(import_v) == 1
        assert "module-style adapter import" in import_v[0].message
        annotation_v = [v for v in violations if v.line_number != 4]
        assert "XBackend" in annotation_v[0].message

    def test_flags_module_style_alias_forward_ref(self) -> None:
        """Same shape via a string forward-ref. Still two violations (import
        site + annotation site)."""
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
        assert len(violations) == 2

    def test_module_style_import_flagged_even_when_annotation_is_clean(self) -> None:
        """`import adapters.x as xb` + `xb.SomeConfig` — the annotation walks
        cleanly (non-backend suffix), but the import itself is now a violation
        because module-style adapter imports are structurally banned. One
        violation, at the import site."""
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
        assert len(violations) == 1
        assert violations[0].line_number == 4
        assert "module-style adapter import" in violations[0].message

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

    # -------------------------------------------------------------------------
    # Tier 4: import-site rule — adapter-import aliasing in core/ is banned.
    # Closes the bypass class structurally rather than patching the suffix
    # check. The hostile-alias case (annotation-only check could not catch)
    # and the safe-alias case (annotation check happens to catch) both now
    # fire at the import line regardless of the local name.
    # -------------------------------------------------------------------------

    def test_flags_hostile_alias_to_non_backend_name(self) -> None:
        """`from adapters... import XBackend as XB` + `backend: XB` — the
        local name `XB` does NOT end in a backend suffix, so the annotation-
        level check alone would silently miss it. The import-site rule fires.
        Codex Tier-4 finding."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend as XB\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "XB") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        # Only the import-site rule fires — the annotation suffix check
        # correctly skips `XB` (doesn't end in any backend suffix).
        assert len(violations) == 1
        assert violations[0].line_number == 4
        assert "aliases adapter import" in violations[0].message
        assert "XBackend" in violations[0].message
        assert "XB" in violations[0].message

    def test_unaliased_import_unaffected(self) -> None:
        """`from adapters... import XBackend` (no alias) — the import-site
        rule passes; only the annotation-level check fires. Single violation."""
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
        # The annotation site, not the import site.
        assert violations[0].line_number != 4

    def test_aliased_import_line_suppression_silences_both_sites(self) -> None:
        """Line-level `# skuel-lint: disable=SKUEL023` on the import line
        suppresses the import-site rule but does not affect the annotation-
        site check that fires on a different line."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.x_backend import XBackend as _XBackend  # skuel-lint: disable=SKUEL023 -- test\n"
            "\n"
            "class XService:\n"
            '    def __init__(self, backend: "_XBackend") -> None:  # skuel-lint: disable=SKUEL023 -- test\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/x_service.py")
        assert violations == []

    def test_module_style_import_in_facade_allowlist_not_flagged(self) -> None:
        """Facade allowlist short-circuits before the import-site rule too."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    import adapters.persistence.neo4j.backends.curriculum_backends as cb\n"
            "\n"
            "class KuService:\n"
            "    def __init__(self, backend: object) -> None:\n"
            "        self.backend: cb.KuBackend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/ku_service.py")
        assert violations == []


class TestSKUEL024:
    UI_FILE = "ui/text.py"

    def test_detects_hardcoded_cls_with_kwargs_splat(self) -> None:
        linter = make_linter(["SKUEL024"])
        content = (
            "def SmallText(text: str, **kwargs: Any) -> Span:\n"
            '    return Span(text, cls="text-sm", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"
        assert violations[0].severity == Severity.ERROR
        assert "SmallText" in violations[0].message
        assert "Span" in violations[0].message

    def test_detects_cls_as_variable_not_just_literal(self) -> None:
        """The hardcoded cls= can be a variable (StatusBadge: cls=badge_cls)."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def StatusBadge(status: str, **kwargs: Any) -> Any:\n"
            "    badge_cls = compute(status)\n"
            "    return Badge(status, variant=None, cls=badge_cls, **kwargs)\n"
        )
        violations = lint_content(linter, content, file_path="ui/feedback.py")
        assert len(violations) == 1
        assert "StatusBadge" in violations[0].message

    def test_detects_with_alternate_kwarg_name(self) -> None:
        """The **var need not be named `kwargs`."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def Helper(text: str, **attrs: Any) -> Div:\n"
            '    return Div(text, cls="base", **attrs)\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert len(violations) == 1

    def test_explicit_cls_param_clean(self) -> None:
        """An explicit cls parameter absorbs a caller-supplied cls= — no collision."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def SmallText(text: str, cls: str = '', **kwargs: Any) -> Span:\n"
            '    return Span(text, cls=f"text-sm {cls}".strip(), **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert violations == []

    def test_keyword_only_cls_param_clean(self) -> None:
        """cls declared keyword-only (after *children) still absorbs the collision."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def DashboardSection(title: str, *children: Any, cls: str = '', **kwargs: Any) -> Div:\n"
            '    return Div(title, *children, cls=f"mt-8 {cls}".strip(), **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/layouts/dashboard.py")
        assert violations == []

    def test_kwargs_pop_not_exempt_use_explicit_param(self) -> None:
        """No pop exemption: pop-based helpers are flagged too (use explicit cls=).

        Proving a pop defuses the splat needs control-flow domination; the rule does
        not attempt it. The contract is the explicit `cls: str = ""` parameter.
        """
        linter = make_linter(["SKUEL024"])
        content = (
            "def EmptyState(title: str, **kwargs: Any) -> Div:\n"
            '    extra = kwargs.pop("cls", "")\n'
            '    return Div(title, cls=f"base {extra}".strip(), **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/patterns/empty_state.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_conditional_pop_flagged(self) -> None:
        """A conditional pop does not run on every path — still flagged."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def Helper(title: str, flag: bool, **kwargs: Any) -> Div:\n"
            "    if flag:\n"
            '        kwargs.pop("cls", "")\n'
            '    return Div(title, cls="base", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_nested_helper_with_own_cls_not_attributed_to_outer(self) -> None:
        """An inner factory with its own cls param is safe — don't flag it against
        the outer **kwargs (the ast.walk-crosses-scope false positive)."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def outer(**kwargs: Any) -> Div:\n"
            "    def row(cls: str = '', **kwargs: Any) -> Div:\n"
            "        return Div(cls=f'r {cls}'.strip(), **kwargs)\n"
            "    return Div(row(), **kwargs)\n"
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert violations == []

    def test_nested_helper_own_collision_still_flagged(self) -> None:
        """A nested helper with its OWN collision is still caught (checked on its own)."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def outer(x: int) -> Span:\n"
            "    def bad(text: str, **kwargs: Any) -> Span:\n"
            "        return Span(text, cls='text-sm', **kwargs)\n"
            "    return bad('hi')\n"
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert "bad" in violations[0].message

    def test_lambda_closing_over_kwargs_flagged(self) -> None:
        """A lambda that closes over the enclosing **kwargs still collides — lambdas
        are not independently checked, so the enclosing scan must catch it."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def outer(**kwargs: Any) -> Any:\n"
            '    make = lambda: Div(cls="base", **kwargs)\n'
            "    return make()\n"
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_nested_def_closing_over_kwargs_flagged(self) -> None:
        """A nested def that closes over the outer **kwargs (no own **kwargs) still
        crashes; scope resolution attributes the splat to the outer binder."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def outer(**kwargs: Any) -> Any:\n"
            "    def make() -> Div:\n"
            '        return Div(cls="base", **kwargs)\n'
            "    return make()\n"
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"
        # Attributed to the binding scope (outer), which owns the colliding **kwargs.
        assert "outer" in violations[0].message

    def test_nested_local_rebinding_shadows_outer_clean(self) -> None:
        """A nested helper that locally assigns the kwargs name splats a LOCAL dict,
        not the outer closure — no caller cls= can collide, so don't flag."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def outer(**kwargs: Any) -> Any:\n"
            "    def make() -> Div:\n"
            '        kwargs = {"id": "local"}\n'
            '        return Div(cls="base", **kwargs)\n'
            "    return make()\n"
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert violations == []

    def test_same_scope_kwargs_reassignment_flagged(self) -> None:
        """Reassigning an OWNED **kwargs is not treated as clearing the collision:
        proving it sanitizes every path needs control-flow domination (mirror of the
        no-pop-exemption decision). Conservative — flagged; use an explicit cls param."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def Helper(**kwargs: Any) -> Div:\n"
            '    kwargs = {"id": "x"}\n'
            '    return Div(cls="base", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_conditional_kwargs_reassignment_flagged(self) -> None:
        """A conditional reassignment leaves the false path splatting the caller's
        original kwargs — still collides, must flag."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def Helper(flag: bool, **kwargs: Any) -> Div:\n"
            "    if flag:\n"
            "        kwargs = {}\n"
            '    return Div(cls="base", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_classmethod_cls_receiver_does_not_absorb_flagged(self) -> None:
        """A @classmethod's `cls` is the bound class receiver, not a style arg — it
        cannot absorb a keyword `cls=`, so the collision must still be flagged."""
        linter = make_linter(["SKUEL024"])
        content = (
            "class C:\n"
            "    @classmethod\n"
            "    def SmallText(cls, text: str, **kwargs: Any) -> Span:\n"
            '        return Span(text, cls="text-sm", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_regular_function_cls_param_still_absorbs_clean(self) -> None:
        """A plain function's `cls` parameter IS keyword-passable (no classmethod
        receiver) and absorbs a caller cls= — not flagged."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def Helper(cls: str, **kwargs: Any) -> Span:\n"
            '    return Span(cls=f"base {cls}".strip(), **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert violations == []

    def test_value_flow_not_tracked_documented_boundary(self) -> None:
        """DOCUMENTED BOUNDARY: the rule resolves a splat NAME's scope, not a variable's
        VALUE. Aliases (`attrs = kwargs`) and copies (`dict(kwargs)`) are not chased —
        sound detection needs control-flow analysis (flow-insensitive alias tracking
        gives both false negatives and false positives); the explicit cls param is the
        contract. These pin the intended boundary, not an endorsement of such helpers."""
        linter = make_linter(["SKUEL024"])
        # Simple alias — `attrs` is a plain local, not the **kwargs param.
        alias = (
            "def SmallText(text: str, **kwargs: Any) -> Span:\n"
            "    attrs = kwargs\n"
            '    return Span(text, cls="text-sm", **attrs)\n'
        )
        assert lint_content(linter, alias, file_path=self.UI_FILE) == []
        # Copy/transform.
        copy = (
            "def Helper(**kwargs: Any) -> Div:\n"
            "    attrs = dict(kwargs)\n"
            '    return Div(cls="base", **attrs)\n'
        )
        assert lint_content(make_linter(["SKUEL024"]), copy, file_path="ui/patterns/x.py") == []

    def test_positional_only_cls_still_flagged(self) -> None:
        """A positional-only `cls` cannot absorb a keyword `cls=` — still collides."""
        linter = make_linter(["SKUEL024"])
        content = "def Helper(cls, /, **kwargs: Any) -> Div:\n    return Div(cls=cls, **kwargs)\n"
        violations = lint_content(linter, content, file_path="ui/patterns/x.py")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_spaced_cls_keyword_flagged(self) -> None:
        """`cls = "x"` (spaces around =) is the same collision — the prefilter must
        not depend on the exact `cls=` spelling."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def SmallText(text: str, **kwargs: Any) -> Span:\n"
            '    return Span(text, cls = "text-sm", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL024"

    def test_no_kwargs_splat_clean(self) -> None:
        """A hardcoded cls= with no **kwargs to collide with is fine."""
        linter = make_linter(["SKUEL024"])
        content = "def Caption(text: str) -> Span:\n    return Span(text, cls='text-xs')\n"
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert violations == []

    def test_kwargs_without_cls_clean(self) -> None:
        """Splatting **kwargs without a hardcoded cls= is fine."""
        linter = make_linter(["SKUEL024"])
        content = "def Wrapper(text: str, **kwargs: Any) -> Div:\n    return Div(text, **kwargs)\n"
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert violations == []

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL024"])
        content = (
            "def SmallText(text: str, **kwargs: Any) -> Span:\n"
            '    return Span(text, cls="text-sm", **kwargs)  # skuel-lint: disable=SKUEL024 -- legacy\n'
        )
        violations = lint_content(linter, content, file_path=self.UI_FILE)
        assert violations == []

    def test_not_run_on_tests(self) -> None:
        """SKUEL024 is skipped on test files (mirrors the _lint_file gate)."""
        linter = make_linter(["SKUEL024"])
        content = (
            "def SmallText(text: str, **kwargs: Any) -> Span:\n"
            '    return Span(text, cls="text-sm", **kwargs)\n'
        )
        violations = lint_content(linter, content, file_path="tests/unit/ui/test_x.py")
        assert violations == []


class TestSKUEL025:
    """No reference to a deleted Activity Domain *UpdatePayload (ADR-066 Phase 7a)."""

    def test_detects_import_of_deleted_payload(self) -> None:
        linter = make_linter(["SKUEL025"])
        content = "from core.ports.query_types import TaskUpdatePayload\n"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL025"
        assert violations[0].severity == Severity.ERROR
        assert "TaskUpdatePayload" in violations[0].message
        assert "TaskUpdateIntent" in violations[0].message  # points at the replacement

    def test_detects_annotation_name(self) -> None:
        linter = make_linter(["SKUEL025"])
        content = 'updates: GoalUpdatePayload = {"status": "active"}\n'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL025"

    def test_detects_attribute_access(self) -> None:
        linter = make_linter(["SKUEL025"])
        content = "x = query_types.PrincipleUpdatePayload\n"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL025"

    def test_all_six_activity_names_flagged(self) -> None:
        linter = make_linter(["SKUEL025"])
        names = [
            "TaskUpdatePayload",
            "GoalUpdatePayload",
            "HabitUpdatePayload",
            "EventUpdatePayload",
            "ChoiceUpdatePayload",
            "PrincipleUpdatePayload",
        ]
        content = "".join(f"v{i}: {n} = {{}}\n" for i, n in enumerate(names))
        violations = lint_content(linter, content)
        assert len(violations) == len(names)

    def test_curriculum_finance_report_payloads_not_flagged(self) -> None:
        """Ku/Ps/Lp/Finance/Report payloads survive for non-activity domains — never flagged."""
        linter = make_linter(["SKUEL025"])
        content = (
            "from core.ports.query_types import (\n"
            "    KuUpdatePayload, PsUpdatePayload, LpUpdatePayload,\n"
            "    FinanceUpdatePayload, ReportUpdatePayload, BaseUpdatePayload,\n"
            ")\n"
            "a: KuUpdatePayload = {}\n"
        )
        violations = lint_content(linter, content)
        assert violations == []

    def test_string_literal_not_flagged(self) -> None:
        """A string naming a deleted type (e.g. a removal-assertion) is not a Name node."""
        linter = make_linter(["SKUEL025"])
        content = 'banned = "TaskUpdatePayload"  # asserting it stays gone\n'
        violations = lint_content(linter, content)
        assert violations == []

    def test_intent_path_not_flagged(self) -> None:
        linter = make_linter(["SKUEL025"])
        content = (
            "from core.models.task import TaskUpdateIntent\n"
            'intent = TaskUpdateIntent(status="in_progress")\n'
        )
        violations = lint_content(linter, content)
        assert violations == []

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL025"])
        content = "from core.ports.query_types import TaskUpdatePayload  # skuel-lint: disable=SKUEL025 -- legacy\n"
        violations = lint_content(linter, content)
        assert violations == []

    def test_parenthesized_import_reports_alias_line(self) -> None:
        """In a multi-line import the violation lands on the alias line, not `import (`."""
        linter = make_linter(["SKUEL025"])
        content = (
            "from core.ports.query_types import (\n    CypherParams,\n    TaskUpdatePayload,\n)\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 3  # the alias line, not line 1

    def test_parenthesized_import_alias_suppression(self) -> None:
        """An inline suppression on the alias line works (alias-location lookup)."""
        linter = make_linter(["SKUEL025"])
        content = (
            "from core.ports.query_types import (\n"
            "    CypherParams,\n"
            "    TaskUpdatePayload,  # skuel-lint: disable=SKUEL025 -- legacy\n"
            ")\n"
        )
        violations = lint_content(linter, content)
        assert violations == []

    def test_not_run_on_tests(self) -> None:
        """SKUEL025 is skipped on test files (mirrors the _lint_file gate)."""
        linter = make_linter(["SKUEL025"])
        content = "updates: TaskUpdatePayload = {}\n"
        violations = lint_content(linter, content, file_path="tests/unit/test_x.py")
        assert violations == []


class TestSKUEL026:
    """SKUEL026 — suppression audit: flag comments that suppress nothing.

    These tests use real files (tmp_path): the audit re-reads files from disk
    to tokenize genuine comments and shadow-lint with suppressions ignored.
    """

    def _lint_tree(
        self,
        tmp_path: Path,
        files: dict[str, str],
        rules_filter: list[str] | None = None,
    ) -> SkuelLinter:
        for rel, content in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        linter = SkuelLinter(root_dir=tmp_path, rules_filter=rules_filter)
        linter.lint()
        return linter

    def test_used_line_suppression_not_flagged(self, tmp_path: Path) -> None:
        """A suppression whose rule fires at its line is used — no SKUEL026."""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": (
                    'ok = hasattr(app, "routes")  # skuel-lint: disable=SKUEL011 -- boundary check\n'
                )
            },
        )
        assert linter.result.violations == []
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is True

    def test_unused_line_suppression_flagged(self, tmp_path: Path) -> None:
        """A suppression on a line where the rule would not fire is rot."""
        linter = self._lint_tree(
            tmp_path,
            {"core/services/x.py": "value = 1  # skuel-lint: disable=SKUEL011 -- stale\n"},
        )
        flagged = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(flagged) == 1
        assert flagged[0].line_number == 1
        assert "would not fire at this line" in flagged[0].message
        assert linter.result.suppressions[0].used is False

    def test_used_file_level_suppression_not_flagged(self, tmp_path: Path) -> None:
        linter = self._lint_tree(
            tmp_path,
            {
                "core/app.py": (
                    '# skuel-lint: disable-file=SKUEL015 -- CLI report\nprint("hello")\n'
                )
            },
        )
        assert linter.result.violations == []
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is True
        assert linter.result.suppressions[0].file_level is True

    def test_unused_file_level_suppression_flagged(self, tmp_path: Path) -> None:
        linter = self._lint_tree(
            tmp_path,
            {"core/app.py": "# skuel-lint: disable-file=SKUEL015 -- stale\nvalue = 1\n"},
        )
        flagged = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(flagged) == 1
        assert "would not fire in this file" in flagged[0].message

    def test_non_suppressible_rule_comment_flagged(self, tmp_path: Path) -> None:
        """disable=SKUEL003 does nothing — SKUEL003 still fires AND the comment is flagged."""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": "if result.is_err:  # skuel-lint: disable=SKUEL003 -- nope\n    pass\n"
            },
        )
        rule_ids = {v.rule_id for v in linter.result.violations}
        assert "SKUEL003" in rule_ids  # the violation is NOT suppressed
        flagged = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(flagged) == 1
        assert "does not support inline suppression" in flagged[0].message
        assert linter.result.suppressions[0].used is False

    def test_unknown_rule_comment_flagged(self, tmp_path: Path) -> None:
        linter = self._lint_tree(
            tmp_path,
            {"core/services/x.py": "value = 1  # skuel-lint: disable=SKUEL099 -- typo\n"},
        )
        flagged = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(flagged) == 1
        assert "not a SKUEL rule" in flagged[0].message

    def test_malformed_comment_flagged_as_not_suppressed(self, tmp_path: Path) -> None:
        """Missing space: discovered by the loose regex, but the checker's exact
        substring match means it suppresses nothing — rule fires + comment flagged."""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": 'ok = hasattr(app, "routes")  #skuel-lint:disable=SKUEL011 -- oops\n'
            },
        )
        rule_ids = {v.rule_id for v in linter.result.violations}
        assert "SKUEL011" in rule_ids
        flagged = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(flagged) == 1
        assert "was not suppressed" in flagged[0].message

    def test_suppression_text_in_string_literal_ignored(self, tmp_path: Path) -> None:
        """Suppression examples inside strings/docstrings are not genuine comments."""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": (
                    'EXAMPLE = """\nvalue = 1  # skuel-lint: disable=SKUEL011 -- doc example\n"""\n'
                )
            },
        )
        assert linter.result.suppressions == []
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL026"] == []

    def test_rule_filter_excluding_skuel026_skips_audit(self, tmp_path: Path) -> None:
        linter = self._lint_tree(
            tmp_path,
            {"core/services/x.py": "value = 1  # skuel-lint: disable=SKUEL011 -- stale\n"},
            rules_filter=["SKUEL011"],
        )
        assert linter.result.suppressions == []
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL026"] == []

    def test_span_suppression_on_wrapped_signature_counts_as_used(self, tmp_path: Path) -> None:
        """The formatter strands a long trailing suppression on the final
        `) -> X:` line of a wrapped signature (the #590 class). The checker
        honors any def-header line; the audit must read the SAME span and mark
        the comment USED, not rot."""
        content = (
            "class S:\n"
            "    async def publish(\n"
            "        self,\n"
            "        msg: str,\n"
            "    ) -> None:  # skuel-lint: disable=SKUEL005 -- fire-and-forget\n"
            "        pass\n"
        )
        linter = self._lint_tree(tmp_path, {"core/services/x.py": content})
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL005"] == []
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL026"] == []
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is True

    def test_span_suppression_on_wrapped_except_counts_as_used(self, tmp_path: Path) -> None:
        content = (
            "try:\n"
            "    x()\n"
            "except (\n"
            "    Exception\n"
            ") as e:  # skuel-lint: disable=SKUEL017 -- top-level handler\n"
            "    pass\n"
        )
        linter = self._lint_tree(tmp_path, {"core/services/x.py": content})
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL017"] == []
        assert [v for v in linter.result.violations if v.rule_id == "SKUEL026"] == []
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is True


# ============================================================================
# SKUEL027 — ui/ Must Not Import adapters/
# ============================================================================


class TestSKUEL027:
    """Import-direction enforcement for the ui/ layer: presentation renders what
    routes hand it, so a runtime `adapters` import inside ui/ inverts the layering.
    SKUEL022's sibling — same scan (shared `_collect_runtime_adapter_imports`),
    different layer scope. Replaced the tests/unit/test_ui_layer_boundary.py guard
    (one enforcement point; lint fires in ./dev quality, not only under pytest)."""

    def test_detects_module_level_from_import(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = "from adapters.inbound.auth import require_authenticated_user\n"
        violations = lint_content(
            linter, content, file_path="ui/layouts/base_page.py", is_service=False
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL027"
        assert violations[0].severity == Severity.ERROR
        assert "adapters.inbound.auth" in violations[0].message

    def test_detects_plain_import(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = "import adapters.inbound.csrf\n"
        violations = lint_content(
            linter, content, file_path="ui/patterns/csrf.py", is_service=False
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL027"

    def test_detects_function_local_import(self) -> None:
        """Function-local imports are where the last real violations hid
        (BasePage/navbar's `adapters.inbound.auth` session readers, cleared in #655)."""
        linter = make_linter(["SKUEL027"])
        content = (
            "def Navbar(request):\n"
            "    from adapters.inbound.auth import get_session_user\n"
            "    return get_session_user(request)\n"
        )
        violations = lint_content(
            linter, content, file_path="ui/layouts/navbar.py", is_service=False
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL027"
        assert violations[0].line_number == 2

    def test_type_checking_import_exempt(self) -> None:
        """The sanctioned shape: type-only `fasthtml_types.Request` annotations."""
        linter = make_linter(["SKUEL027"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.inbound.fasthtml_types import Request\n"
        )
        violations = lint_content(
            linter, content, file_path="ui/layouts/base_page.py", is_service=False
        )
        assert len(violations) == 0

    def test_typing_dot_type_checking_exempt(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = (
            "import typing\n"
            "\n"
            "if typing.TYPE_CHECKING:\n"
            "    from adapters.inbound.fasthtml_types import Request\n"
        )
        violations = lint_content(linter, content, file_path="ui/explore/nav.py", is_service=False)
        assert len(violations) == 0

    def test_else_branch_of_type_checking_not_exempt(self) -> None:
        """The `else:` of `if TYPE_CHECKING:` is the runtime branch — flagged."""
        linter = make_linter(["SKUEL027"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.inbound.fasthtml_types import Request\n"
            "else:\n"
            "    from adapters.inbound.auth import get_session_user\n"
        )
        violations = lint_content(
            linter, content, file_path="ui/layouts/navbar.py", is_service=False
        )
        assert len(violations) == 1
        assert violations[0].line_number == 6

    def test_adapter_path_in_docstring_not_flagged(self) -> None:
        """AST-based: adapter paths named in docstrings/strings are prose, not imports
        (many real ui/ modules cite their consuming route file, e.g. tasks_form.py)."""
        linter = make_linter(["SKUEL027"])
        content = (
            '"""Form used by ``adapters/inbound/tasks_ui.py`` (GET /tasks/create)."""\n'
            "\n"
            "PATH = 'adapters.inbound.tasks_ui'\n"
        )
        violations = lint_content(
            linter, content, file_path="ui/activities/tasks_form.py", is_service=False
        )
        assert len(violations) == 0

    def test_relative_and_inward_imports_clean(self) -> None:
        """ui/ importing core/ and its own siblings is the correct direction."""
        linter = make_linter(["SKUEL027"])
        content = (
            "from core.models.task import Task\n"
            "from ui.components import Button\n"
            "from .helpers import thing\n"
        )
        violations = lint_content(
            linter, content, file_path="ui/activities/tasks_form.py", is_service=False
        )
        assert len(violations) == 0

    def test_relative_sibling_named_adapters_not_flagged(self) -> None:
        """`from .adapters import x` is a sibling ui/ module named `adapters`
        (`level == 1`), not the top-level adapters/ package (Codex P2 on #656)."""
        linter = make_linter(["SKUEL027"])
        content = "from .adapters import to_chart_config\n"
        violations = lint_content(
            linter, content, file_path="ui/visualization/formats.py", is_service=False
        )
        assert len(violations) == 0

    def test_core_file_not_checked_by_this_rule(self) -> None:
        """core/ is SKUEL022's territory — SKUEL027 only scans ui/."""
        linter = make_linter(["SKUEL027"])
        content = "from adapters.inbound.auth import require_authenticated_user\n"
        violations = lint_content(
            linter, content, file_path="core/services/example_service.py", is_service=False
        )
        assert len(violations) == 0

    def test_route_file_not_flagged(self) -> None:
        """adapters/inbound routes composing adapters is the correct direction."""
        linter = make_linter(["SKUEL027"])
        content = "from adapters.inbound.auth import require_authenticated_user\n"
        violations = lint_content(
            linter, content, file_path="adapters/inbound/tasks_ui.py", is_service=False
        )
        assert len(violations) == 0

    def test_skips_test_files(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = "from adapters.inbound.auth import require_authenticated_user\n"
        violations = lint_content(linter, content, file_path="ui/test_example.py", is_service=False)
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = (
            "from adapters.inbound.x import Y  "
            "# skuel-lint: disable=SKUEL027 -- documented boundary exception\n"
        )
        violations = lint_content(linter, content, file_path="ui/x.py", is_service=False)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL027"])
        content = (
            "# skuel-lint: disable-file=SKUEL027 -- documented boundary exception\n"
            "from adapters.inbound.x import Y\n"
        )
        violations = lint_content(linter, content, file_path="ui/x.py", is_service=False)
        assert len(violations) == 0

    def test_try_and_except_bodies_both_flagged(self) -> None:
        """Runtime-branch coverage rides the shared scan — same guarantee as SKUEL022."""
        linter = make_linter(["SKUEL027"])
        content = (
            "try:\n"
            "    from adapters.inbound.fast import Fast\n"
            "except ImportError:\n"
            "    from adapters.inbound.slow import Slow\n"
        )
        violations = lint_content(linter, content, file_path="ui/x.py", is_service=False)
        assert len(violations) == 2
        assert {v.line_number for v in violations} == {2, 4}


class TestSuppressibleRulesDrift:
    """SUPPRESSIBLE_RULES must equal the set of rules whose checkers actually
    call the suppression helpers — SKUEL026's messaging depends on it."""

    def test_suppressible_rules_match_helper_call_sites(self) -> None:
        import re

        source = (Path(__file__).resolve().parents[3] / "scripts" / "lint_skuel.py").read_text(
            encoding="utf-8"
        )
        called = set(re.findall(r'_is_(?:line|file)_suppressed\([^)]*"(SKUEL\d{3})"\)', source))
        assert called == set(SkuelLinter.SUPPRESSIBLE_RULES)


class TestGitChangedFiles:
    """--staged / --changed path resolution.

    Git prints diff paths relative to the REPO ROOT, but the linter's root_dir
    is app/ — a subdirectory of the real repo. Without `--relative` in the git
    command, every path failed the `.exists()` join and both modes silently
    linted nothing (0 files, exit 0). These tests run against a real temp repo
    with the same repo-root/app-subdir layout.
    """

    def test_staged_files_resolve_from_subdirectory_root(self, tmp_path: Path) -> None:
        import subprocess

        app = tmp_path / "app"
        (app / "core").mkdir(parents=True)
        target = app / "core" / "thing.py"
        target.write_text("x = 1\n", encoding="utf-8")
        # A staged .py OUTSIDE app/ must not appear in the result.
        (tmp_path / "top_level.py").write_text("y = 2\n", encoding="utf-8")

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

        git("init")
        git("config", "user.email", "test@test")
        git("config", "user.name", "test")
        git("add", ".")

        files = SkuelLinter._git_changed_files(app, staged_only=True)
        assert files == [target]
