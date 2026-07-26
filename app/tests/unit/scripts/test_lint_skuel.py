"""
Tests for SKUEL Unified Linter
===============================

Tests all SKUEL lint rules, LintResult dataclass, and suppression logic.
Uses synthetic string content — no filesystem access needed.
"""

import ast
import sys
from pathlib import Path

import pytest

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
    if linter._should_run_rule("SKUEL028") and not is_test:
        linter._check_result_fail_expect_error(fp, rel, content, lines, tree)
    if linter._should_run_rule("SKUEL006"):
        linter._check_todo_comments(fp, rel, content, lines)

    if linter._should_run_rule("SKUEL029") and not is_test:
        linter._check_async_without_await(fp, rel, content, lines, tree)

    # Graph-vocabulary rule — mirrors _lint_file's persistence gate.
    is_persistence = "/adapters/persistence/" in str(fp)
    if (
        is_persistence
        and not is_test
        and not rel.as_posix().startswith(linter.SKUEL030_EXCLUDED_PREFIXES)
        and linter._should_run_rule("SKUEL030")
    ):
        linter._check_cypher_vocabulary(fp, rel, content, lines, tree)

    # Inbound/presentation layers — mirror _lint_file, reading the SAME tuple the
    # production gate reads so the two cannot drift.
    is_inbound_layer = rel.as_posix().startswith(SkuelLinter.INBOUND_LAYER_PREFIXES)

    # Boundary rules (ADR-044): SKUEL001 (APOC) + SKUEL021 (raw Cypher) run on all of
    # core/, any /services/ path, AND the inbound/presentation layers — mirror
    # _lint_file's is_above_boundary.
    is_above_boundary = is_core or is_service or is_inbound_layer
    if is_above_boundary and not is_test:
        if linter._should_run_rule("SKUEL001"):
            linter._check_apoc_in_services(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL021"):
            linter._check_raw_cypher_in_services(fp, rel, content, lines, tree)

    if is_service and not is_test:
        if linter._should_run_rule("SKUEL002"):
            linter._check_semantic_type_strings(fp, rel, content, lines, tree)
        if linter._should_run_rule("SKUEL005"):
            linter._check_result_return_types(fp, rel, content, lines, tree)

    # SKUEL007 + SKUEL013 + SKUEL014 also cover the inbound/presentation
    # layers — mirror _lint_file (is_inbound_layer computed above).
    if (is_service or is_inbound_layer) and not is_test:
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

    def test_matches_the_whole_apoc_namespace(self) -> None:
        """The rule matches `apoc.` + its dotted path, not a curated prefix list.
        A nine-prefix list silently passed apoc.convert/coll/text/periodic and every
        new APOC release — a lagging approximation of "no APOC above the boundary"."""
        for proc in (
            "apoc.convert.fromJsonMap($json)",
            "apoc.coll.toSet(items)",
            "apoc.text.join(parts, ',')",
            "apoc.periodic.iterate(q1, q2, {})",
            "apoc.create.node(labels, props)",
        ):
            violations = lint_content(make_linter(["SKUEL001"]), f'q = "RETURN {proc} AS x"')
            assert len(violations) == 1, proc
            assert violations[0].severity == Severity.CRITICAL

    def test_message_names_the_procedure_found(self) -> None:
        """Namespace matching must not cost message specificity — the violation
        reports the procedure it actually matched, not the namespace prefix."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'q = "RETURN apoc.convert.fromJsonMap($j) AS d"')
        assert violations[0].message == (
            "APOC procedure 'apoc.convert.fromJsonMap' authored above the boundary"
        )

    def test_bare_apoc_word_is_not_a_procedure(self) -> None:
        """A used string naming APOC without a dotted procedure path is prose, not a
        call — the pattern requires at least one `.segment`."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(linter, 'msg = "APOC is banned above the boundary"')
        assert len(violations) == 0

    def test_mention_without_invocation_is_not_flagged(self) -> None:
        """Invocation, not mention. This rule is CRITICAL and unsuppressable, so a
        false positive on diagnostic/help text would be unfixable except by rewording
        the string. Cypher invokes APOC only as `CALL apoc.x.y(...)` or bare
        `apoc.x.y(...)` — prose naming a procedure has neither anchor."""
        for prose in (
            "apoc.convert.fromJsonMap is unavailable on this server",
            "Schema introspection needs apoc.meta.stats — ask an admin",
            "Migrated off apoc.path.subgraphAll in PR #75",
        ):
            violations = lint_content(make_linter(["SKUEL001"]), f"logger.warning({prose!r})")
            assert violations == [], prose

    def test_detects_name_assembled_into_query_elsewhere(self) -> None:
        """`proc = "apoc.path.subgraphAll"` then `f"CALL {proc}(n)"` — the CALL and
        the paren live in a different AST node than the name, so neither invocation
        anchor is present on the node carrying it, and SKUEL021 does not cover it
        either (`CALL apoc.` is not a CYPHER_MARKER). A used string whose ENTIRE
        value is a dotted apoc path is the third recognised form."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(
            linter, 'proc = "apoc.path.subgraphAll"\nq = f"CALL {proc}(n)"\nrun(q)'
        )
        assert len(violations) == 1
        assert violations[0].severity == Severity.CRITICAL
        assert "apoc.path.subgraphAll" in violations[0].message

    def test_call_form_survives_interpolated_arguments(self) -> None:
        """Why the CALL branch is kept rather than requiring the paren alone: an
        f-string that interpolates the argument list has no literal `(` after the
        procedure path, but `CALL apoc...` is still an invocation."""
        linter = make_linter(["SKUEL001"])
        violations = lint_content(
            linter, 'args = "{}"\nq = f"CALL apoc.periodic.iterate{args}"\nrun(q)'
        )
        assert len(violations) == 1
        assert "apoc.periodic.iterate" in violations[0].message

    def test_fires_in_inbound_layer(self) -> None:
        """Shares SKUEL021's gate: a ``CALL apoc...`` is Cypher, so the layers that
        may not author Cypher may not author APOC either. Without this, extending
        only SKUEL021 would leave a hole — ``CALL apoc.`` is not a CYPHER_MARKER."""
        for path in ("adapters/inbound/system_api.py", "ui/explore/cards.py"):
            violations = lint_content(
                make_linter(["SKUEL001"]),
                'q = "CALL apoc.path.subgraphAll(n, {maxLevel: 3})"',
                file_path=path,
                is_service=False,
            )
            assert len(violations) == 1, path
            assert violations[0].rule_id == "SKUEL001"

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
            linter, content, file_path="core/utils/neo4j_props.py", is_service=False
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

    def test_detects_str_wrapped_exception(self) -> None:
        # str(...) wraps dodge the literal-only pattern — the shape that hid
        # six real violations in ingestion_tracker.py.
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, "return Result.fail(str(e))")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL007"

    def test_detects_str_wrapped_result_error(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, "return Result.fail(str(result.error))")
        assert len(violations) == 1

    def test_detects_multiline_string_fail(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, 'return Result.fail(\n    "Task not found"\n)')
        assert len(violations) == 1

    def test_errors_factory_clean(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, 'return Result.fail(Errors.not_found("Task", uid))')
        assert len(violations) == 0

    def test_result_propagation_clean(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(linter, "return Result.fail(result)")
        assert len(violations) == 0

    def test_errors_factory_with_str_detail_clean(self) -> None:
        # str(...) inside a factory call is fine — only a str(...) FIRST
        # argument to Result.fail() is the violation shape.
        linter = make_linter(["SKUEL007"])
        violations = lint_content(
            linter, 'return Result.fail(Errors.system("Stat failed", exception=e))'
        )
        assert len(violations) == 0

    def test_fires_in_inbound_adapters(self) -> None:
        # Widened scope: routes/handlers under adapters/inbound/ are covered.
        linter = make_linter(["SKUEL007"])
        violations = lint_content(
            linter,
            'return Result.fail("Invalid date format")',
            file_path="adapters/inbound/analytics_summary_api.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL007"

    def test_fires_in_ui(self) -> None:
        linter = make_linter(["SKUEL007"])
        violations = lint_content(
            linter,
            'return Result.fail(f"Render failed: {e}")',
            file_path="ui/components/fragment_renderer.py",
            is_service=False,
        )
        assert len(violations) == 1

    def test_silent_outside_scope(self) -> None:
        # scripts/ and non-service core/ modules stay out of SKUEL007's scope.
        linter = make_linter(["SKUEL007"])
        for path in ("scripts/some_tool.py", "core/utils/neo4j_props.py"):
            violations = lint_content(
                linter,
                'return Result.fail("boom")',
                file_path=path,
                is_service=False,
            )
            assert violations == [], path


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
            linter, 'await backend.add_relationship(uid1, "SUPPORTS_GOAL", uid2)'
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL013"

    def test_enum_usage_clean(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter,
            "await backend.add_relationship(uid1, RelationshipName.SUPPORTS_GOAL, uid2)",
        )
        assert len(violations) == 0

    def test_cypher_query_exempt(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(linter, 'query = "MATCH (a)-[:SUPPORTS_GOAL]->(b) RETURN b"')
        assert len(violations) == 0

    def test_skips_docstrings(self) -> None:
        linter = make_linter(["SKUEL013"])
        content = '"""\nUses "SUPPORTS_GOAL" relationship.\n"""'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_skips_comments(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(linter, 'x = 1  # pass "SUPPORTS_GOAL" here')
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
            '    "SUPPORTS_GOAL",\n'
            "    uid2,\n"
            ")"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 4

    def test_fires_in_inbound_adapters(self) -> None:
        # Widened scope: routes/handlers under adapters/inbound/ are covered.
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter,
            'edges.append(DependencyEdge(relationship_type="ENABLES"))',
            file_path="adapters/inbound/graphql/schema.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL013"

    def test_fires_in_ui(self) -> None:
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter,
            'badge = rel_badge("SUPPORTS_GOAL")',
            file_path="ui/components/relationship_badge.py",
            is_service=False,
        )
        assert len(violations) == 1

    def test_silent_outside_scope(self) -> None:
        # scripts/ and non-service core/ modules stay out of SKUEL013's scope.
        linter = make_linter(["SKUEL013"])
        for path in ("scripts/some_tool.py", "core/utils/neo4j_props.py"):
            violations = lint_content(
                linter,
                'rel = "SUPPORTS_GOAL"',
                file_path=path,
                is_service=False,
            )
            assert violations == [], path

    def test_line_suppression(self) -> None:
        # Boundary-shaped literal: an external system's status string that merely
        # collides with a relationship name.
        linter = make_linter(["SKUEL013"])
        violations = lint_content(
            linter,
            'status_map = {"IN_PROGRESS": EntityStatus.ACTIVE}'
            "  # skuel-lint: disable=SKUEL013 -- external status literal",
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL013"])
        content = (
            "# skuel-lint: disable-file=SKUEL013 -- external status mapping module\n"
            'a = "SUPPORTS_GOAL"\n'
            'b = "BLOCKS"\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0


class TestRelationshipNamesDrift:
    """The linter's vocabulary must equal the FULL RelationshipName enum.

    If they diverge, SKUEL013 silently under-enforces (new relationship values
    pass as raw strings) or gives broken advice (suggesting enum members that no
    longer exist — the pre-2026-07 hand-mirror carried four stale names).

    The mirror is gone as of 2026-07-19: `SkuelLinter.RELATIONSHIP_NAMES` now
    AST-parses the enum declaration site via `cypher_vocabulary.load_vocabulary`.
    This test therefore pins the PARSER, not a copy — it fails if the parser
    stops recovering members (e.g. someone converts the enum to a functional
    `StrEnum("RelationshipName", [...])` call, which has no Assign nodes to read).
    """

    def test_parsed_vocabulary_matches_relationship_name_enum(self) -> None:
        # Import inside the test so collection still works in environments
        # where core/ isn't importable (e.g. minimal CI lint runners).
        from core.models.relationship_names import RelationshipName

        actual = {member.value for member in RelationshipName}
        parsed = set(make_linter(["SKUEL013"]).RELATIONSHIP_NAMES)

        assert parsed == actual, (
            "The AST-parsed RelationshipName vocabulary diverged from the enum. "
            f"Missing: {sorted(actual - parsed)}. Extra: {sorted(parsed - actual)}. "
            "See scripts/cypher_vocabulary.py::_enum_member_values."
        )

    def test_parsed_labels_match_neo_label_enum(self) -> None:
        """Same contract for the label half, which SKUEL030/CYP011 read."""
        from cypher_vocabulary import load_vocabulary  # type: ignore[import-not-found]

        from core.models.enums.neo_labels import NeoLabel

        actual = {member.value for member in NeoLabel}
        parsed = set(load_vocabulary().labels)

        assert parsed == actual, (
            "The AST-parsed NeoLabel vocabulary diverged from the enum. "
            f"Missing: {sorted(actual - parsed)}. Extra: {sorted(parsed - actual)}."
        )


# ============================================================================
# SKUEL030: persistence Cypher vocabulary must be registered
# ============================================================================

PERSISTENCE_FILE = "adapters/persistence/neo4j/example_backend.py"


def lint_cypher(content: str, *, file_path: str = PERSISTENCE_FILE) -> list[Violation]:
    """Run SKUEL030 over persistence-layer content."""
    return lint_content(
        make_linter(["SKUEL030"]),
        content,
        file_path=file_path,
        is_service=False,
        is_adapter=True,
    )


class TestSKUEL030:
    def test_detects_unregistered_relationship(self) -> None:
        violations = lint_cypher('q = "MATCH (u:User)-[:OWNS_ENTITY]->(t:Task) RETURN t"')
        assert [v.rule_id for v in violations] == ["SKUEL030"]
        assert "OWNS_ENTITY" in violations[0].message

    def test_detects_unregistered_label(self) -> None:
        violations = lint_cypher('q = "MATCH (u:User)-[:OWNS]->(t:Taskk) RETURN t"')
        assert [v.rule_id for v in violations] == ["SKUEL030"]
        assert "Taskk" in violations[0].message

    def test_allows_registered_vocabulary(self) -> None:
        assert lint_cypher('q = "MATCH (u:User)-[:OWNS]->(t:Task) RETURN t"') == []

    def test_multi_label_pattern_checks_each_part(self) -> None:
        """`(n:Entity:Ku)` is two labels; a typo in either half must be caught."""
        assert lint_cypher('q = "MATCH (n:Entity:Ku) RETURN n"') == []
        violations = lint_cypher('q = "MATCH (n:Entity:Kuu) RETURN n"')
        assert len(violations) == 1
        assert "Kuu" in violations[0].message

    def test_alternation_checks_each_branch(self) -> None:
        """`[:A|B]` is two edge types."""
        assert lint_cypher('q = "MATCH ()-[:OWNS|MASTERED]->() RETURN 1"') == []
        violations = lint_cypher('q = "MATCH ()-[:OWNS|MASTERD]->() RETURN 1"')
        assert len(violations) == 1
        assert "MASTERD" in violations[0].message

    def test_var_length_bound_is_stripped(self) -> None:
        assert lint_cypher('q = "MATCH ()-[:OWNS*1..3]->() RETURN 1"') == []

    def test_interpolated_depth_still_validates_static_type(self) -> None:
        """`[:BAD*1..{depth}]` interpolates only the BOUND — the name is static.

        Testing for the sentinel before stripping the bound skipped the whole
        relationship and hid every `*1..{depth}` traversal (Codex P2 on #732).
        """
        violations = lint_cypher('q = f"MATCH (a)-[:BAD_EDGE*1..{depth}]->(b) RETURN b"')
        assert len(violations) == 1
        assert "BAD_EDGE" in violations[0].message

    def test_interpolated_type_with_interpolated_depth_is_skipped(self) -> None:
        """Both halves dynamic — still nothing static to validate."""
        assert lint_cypher('q = f"MATCH (a)-[:{rel}*1..{depth}]->(b) RETURN b"') == []

    @pytest.mark.parametrize(
        "ddl",
        [
            "CREATE CONSTRAINT c IF NOT EXISTS FOR (n:Bogus) REQUIRE n.uid IS UNIQUE",
            "CREATE INDEX i IF NOT EXISTS FOR (n:Bogus) ON (n.uid)",
            "CREATE RANGE INDEX i IF NOT EXISTS FOR (n:Bogus) ON (n.uid)",
            "CREATE TEXT INDEX i IF NOT EXISTS FOR (n:Bogus) ON (n.uid)",
            "CREATE POINT INDEX i IF NOT EXISTS FOR (n:Bogus) ON (n.loc)",
            "CREATE FULLTEXT INDEX i IF NOT EXISTS FOR (n:Bogus) ON EACH [n.title]",
            "CREATE VECTOR INDEX i IF NOT EXISTS FOR (n:Bogus) ON (n.embedding)",
        ],
    )
    def test_typed_index_ddl_is_scanned(self, ddl: str) -> None:
        """Neo4j 5 puts an index-type keyword between CREATE and INDEX.

        An anchor requiring INDEX to follow CREATE immediately skipped every
        typed form, including live fulltext DDL (Codex P2 on #732).
        """
        violations = lint_cypher(f'q = "{ddl}"')
        assert len(violations) == 1, f"not scanned: {ddl}"
        assert "Bogus" in violations[0].message

    def test_procedure_call_query_is_scanned(self) -> None:
        """Vector/fulltext search opens with `CALL db.` and filters after.

        A clause-keyword-only anchor left every search builder unscanned
        (Codex P2 on #732).
        """
        content = (
            'q = """CALL db.index.fulltext.queryNodes($idx, $q) YIELD node\n'
            "WHERE EXISTS((node)-[:BAD_EDGE]->(:Task))\n"
            'RETURN node"""'
        )
        violations = lint_cypher(content)
        assert len(violations) == 1
        assert "BAD_EDGE" in violations[0].message

    def test_type_predicate_equality_is_scanned(self) -> None:
        """`type(r) = 'X'` names an edge type as load-bearingly as `[:X]` does."""
        violations = lint_cypher("q = \"MATCH ()-[r]->() WHERE type(r) = 'BAD_EDGE'\"")
        assert len(violations) == 1
        assert "BAD_EDGE" in violations[0].message

    def test_type_predicate_in_list_is_scanned(self) -> None:
        """Each element of `type(r) IN [...]` is checked (Codex P2 on #732)."""
        violations = lint_cypher(
            "q = \"MATCH ()-[r]->() WHERE type(r) IN ['OWNS', 'BAD_A', 'BAD_B']\""
        )
        assert sorted(v.message.split("'")[1] for v in violations) == ["BAD_A", "BAD_B"]

    def test_parameterized_type_predicate_is_skipped(self) -> None:
        """`type(r) = $rel_type` has no static name to validate."""
        assert lint_cypher('q = "MATCH ()-[r]->() WHERE type(r) = $rel_type"') == []

    def test_label_predicate_is_scanned(self) -> None:
        """`WHERE n:Label` / `AND NOT n:Label` are label positions too."""
        assert lint_cypher('q = "MATCH (n) WHERE NOT n:Content RETURN n"') == []
        violations = lint_cypher('q = "MATCH (n) WHERE NOT n:Contnet RETURN n"')
        assert len(violations) == 1
        assert "Contnet" in violations[0].message

    def test_map_keys_are_not_label_predicates(self) -> None:
        """The label-predicate anchor must not swallow Cypher map syntax."""
        assert lint_cypher('q = "MATCH (n:Task {uid: $uid}) WHERE n.x = 1 RETURN n"') == []

    def test_interpolated_name_is_skipped(self) -> None:
        """`[:HAS_{domain}]` composes its type at runtime — nothing to validate."""
        content = 'q = f"MATCH (u:User)-[:HAS_{domain.upper()}]->(e:Task) RETURN e"'
        assert lint_cypher(content) == []

    def test_fstring_literal_parts_still_checked(self) -> None:
        """Interpolation elsewhere must not blind the rule to a literal typo."""
        content = 'q = f"MATCH (u:User {{uid: {uid}}})-[:OWNZ]->(t:Task) RETURN t"'
        violations = lint_cypher(content)
        assert len(violations) == 1
        assert "OWNZ" in violations[0].message

    def test_docstring_cypher_is_ignored(self) -> None:
        """Illustrative Cypher in prose is not executable — same model as SKUEL021."""
        content = '"""Example: MATCH (u:User)-[:MADE_UP_EDGE]->(x:Bogus)."""\nq = 1'
        assert lint_cypher(content) == []

    def test_non_cypher_string_is_ignored(self) -> None:
        """A bracketed non-query string must not be parsed as a pattern."""
        assert lint_cypher('label = "[:NOT_CYPHER]"') == []

    def test_baseline_suppresses_only_the_known_file(self) -> None:
        """The baseline is (file, name)-scoped, not name-scoped.

        A name-keyed baseline would wave the name through everywhere and re-open
        the hole the rule exists to close (Codex P2 on #732).

        SKUEL030_BASELINE is EMPTY since the semantic-relationship-layer roadmap
        Phase 1 closed §9 (the last real pairs). Rather than couple this fixture
        to whatever the next real finding happens to be — it has been
        invalidated by a repoint twice — inject a SYNTHETIC (file, name) entry
        and prove the scoping mechanism directly. `MADE_UP_EDGE` is unregistered,
        so absent the baseline it fires everywhere.
        """
        query = 'q = "MATCH (a)-[:MADE_UP_EDGE]->(b) RETURN b"'
        known = "adapters/persistence/neo4j/example_backend.py"
        other = "adapters/persistence/neo4j/some_new_backend.py"

        # Sanity: with an empty baseline the name fires in the known file too.
        assert len(lint_cypher(query, file_path=known)) == 1

        linter = make_linter(["SKUEL030"])
        linter.SKUEL030_BASELINE = frozenset({(known, "MADE_UP_EDGE")})

        assert lint_content(linter, query, file_path=known, is_service=False, is_adapter=True) == []

        elsewhere = lint_content(linter, query, file_path=other, is_service=False, is_adapter=True)
        assert len(elsewhere) == 1
        assert "MADE_UP_EDGE" in elsewhere[0].message

    def test_migrations_are_excluded(self) -> None:
        """A rename migration must be able to name what it renames away."""
        assert (
            lint_cypher(
                'q = "MATCH (n:RetiredLabel) REMOVE n:RetiredLabel"',
                file_path="scripts/migrations/rename_2026.py",
            )
            == []
        )

    def test_line_suppression(self) -> None:
        content = (
            'q = "MATCH (u:User)-[:OWNS_ENTITY]->(t:Task)"'
            "  # skuel-lint: disable=SKUEL030 -- external schema\n"
        )
        assert lint_cypher(content) == []

    def test_file_suppression(self) -> None:
        content = (
            "# skuel-lint: disable-file=SKUEL030 -- mirrors an external graph\n"
            'q = "MATCH (u:User)-[:OWNS_ENTITY]->(t:Task)"\n'
        )
        assert lint_cypher(content) == []

    def test_reports_the_offending_line_not_the_string_start(self) -> None:
        """Multi-line queries must point at the bad name, not the opening quote."""
        content = 'q = """\nMATCH (u:User)\nMATCH (u)-[:BAD_EDGE]->(t:Task)\n"""'
        violations = lint_cypher(content)
        assert len(violations) == 1
        assert violations[0].line_number == 3


class TestSKUEL030PythonEdgeLists:
    """SKUEL030's second scanner: edge names held in Python, not in Cypher.

    An alternation is as often assembled from a Python list as written inline.
    Those names never sit inside a Cypher fragment, so the Cypher scanner cannot
    see them — while the alternation they build silently matches only its live
    arms. Three such sites surfaced in three consecutive tranches.
    """

    def test_detects_dead_name_in_a_corroborated_list(self) -> None:
        """The tranche-3 `"practice"` site's original shape."""
        violations = lint_cypher(
            'EDGES = {"practice": ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"]}'
        )
        assert {v.rule_id for v in violations} == {"SKUEL030"}
        assert {"PRACTICES", "REINFORCES"} == {
            name for v in violations for name in ("PRACTICES", "REINFORCES") if name in v.message
        }

    def test_detects_dead_name_in_a_bare_alternation_string(self) -> None:
        """The tranche-4 `rel_types` site's original shape."""
        violations = lint_cypher('spec = {"rel_types": "PARENT_OF|CHILD_OF|HAS_STEP"}')
        assert {v.rule_id for v in violations} == {"SKUEL030"}
        assert len(violations) == 2

    def test_allows_a_fully_registered_list(self) -> None:
        assert lint_cypher('EDGES = ["OWNS", "HAS_STEP", "ORGANIZES"]') == []

    def test_allows_a_fully_registered_alternation(self) -> None:
        assert lint_cypher('spec = {"rel_types": "HAS_STEP|ORGANIZES"}') == []

    def test_uncorroborated_upper_snake_lists_are_ignored(self) -> None:
        """The false-positive guard: no registered sibling means not an edge list.

        Without this, every list of UPPER_SNAKE constants in the persistence
        layer — status codes, env-var names, header names — would be read as
        graph vocabulary.
        """
        assert lint_cypher('LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]') == []

    def test_single_element_lists_are_ignored(self) -> None:
        """One string is not a list of vocabulary; corroboration needs a sibling."""
        assert lint_cypher('X = ["NOT_AN_EDGE"]') == []

    def test_lowercase_and_mixed_case_strings_are_ignored(self) -> None:
        """Edge names are UPPER_SNAKE; anything else is not vocabulary."""
        assert lint_cypher('X = ["HAS_STEP", "some prose", "MixedCase"]') == []

    def test_docstring_alternations_are_inert(self) -> None:
        """Prose describing an alternation must not be linted as one."""
        assert lint_cypher('def f():\n    """PARENT_OF|CHILD_OF|HAS_STEP"""\n    return 1') == []

    def test_respects_line_suppression(self) -> None:
        content = 'EDGES = ["PARENT_OF", "HAS_STEP"]  # skuel-lint: disable=SKUEL030 -- external\n'
        assert lint_cypher(content) == []

    def test_respects_the_baseline(self) -> None:
        """Same (file, name) baseline as the Cypher half — one rule, two scanners.

        SKUEL030_BASELINE is empty since roadmap Phase 1 closed §9, so inject a
        synthetic entry (as the Cypher-half test does) and prove the Python
        edge-list scanner honors it. HAS_STEP is registered, so the corroboration
        rule treats the group as vocabulary and MADE_UP_EDGE fires absent the
        baseline.
        """
        known = "adapters/persistence/neo4j/example_backend.py"
        other = "adapters/persistence/neo4j/some_new_backend.py"
        content = 'EDGES = ["MADE_UP_EDGE", "HAS_STEP"]'

        # Sanity: with an empty baseline, the name fires in the known file too.
        assert lint_cypher(content, file_path=known) != []

        linter = make_linter(["SKUEL030"])
        linter.SKUEL030_BASELINE = frozenset({(known, "MADE_UP_EDGE")})

        assert (
            lint_content(linter, content, file_path=known, is_service=False, is_adapter=True) == []
        )
        # Same names in a DIFFERENT file are still reported.
        assert (
            lint_content(linter, content, file_path=other, is_service=False, is_adapter=True) != []
        )

    def test_non_persistence_files_are_out_of_scope(self) -> None:
        """Scope is unchanged: this scanner rides the existing SKUEL030 gate."""
        assert (
            lint_cypher(
                'EDGES = ["PARENT_OF", "HAS_STEP"]',
                file_path="core/services/example_service.py",
            )
            == []
        )


class TestSKUEL030Registration:
    """SKUEL030 must be wired into every registry the linter consults."""

    def test_is_suppressible(self) -> None:
        assert "SKUEL030" in SkuelLinter.SUPPRESSIBLE_RULES

    def test_consumes_the_shared_ast(self) -> None:
        assert "SKUEL030" in SkuelLinter.AST_RULE_IDS

    def test_has_rule_docs(self) -> None:
        from lint_skuel import RULE_DOCS  # type: ignore[import-not-found]

        assert "SKUEL030" in RULE_DOCS
        assert RULE_DOCS["SKUEL030"]["severity"] == "WARNING"

    def test_baseline_names_are_all_currently_unregistered(self) -> None:
        """A baselined name that got registered is stale — delete it from the set.

        The baseline is a shrinking list of known findings. Once a name is
        genuinely registered, keeping it here would mask a future regression of
        that same name.
        """
        from cypher_vocabulary import load_vocabulary  # type: ignore[import-not-found]

        vocabulary = load_vocabulary()
        registered = vocabulary.relationships | vocabulary.labels
        stale = sorted(name for _, name in SkuelLinter.SKUEL030_BASELINE if name in registered)
        assert not stale, (
            f"SKUEL030_BASELINE entries are now registered and must be removed: {stale}"
        )

    def test_baseline_files_all_exist(self) -> None:
        """A baselined path that no longer exists is dead weight — delete the entry.

        Without this, deleting or renaming a flagged backend leaves a stale
        exemption behind that would silently cover a future file of the same name.
        """
        from cypher_vocabulary import app_root  # type: ignore[import-not-found]

        root = app_root()
        missing = sorted(
            {path for path, _ in SkuelLinter.SKUEL030_BASELINE if not (root / path).exists()}
        )
        assert not missing, f"SKUEL030_BASELINE references files that no longer exist: {missing}"


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

    def test_flags_template_and_nonku_domain_values(self) -> None:
        # Catalog completeness: template types and NonKuDomain values are covered.
        for value in ("task_template", "user_entry", "group", "calendar", "learning"):
            linter = make_linter(["SKUEL014"])
            violations = lint_content(linter, f'if entity_type == "{value}":\n    pass')
            assert len(violations) == 1, value

    def test_domain_enum_comparison_exempt(self) -> None:
        # Domain's values overlap the catalog ("learning", "finance") — a
        # comparison already routed through Domain is enum-safe.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(linter, 'ok = Domain.LEARNING.value == "learning"')
        assert len(violations) == 0

    def test_fires_in_inbound_adapters(self) -> None:
        # Widened scope: routes/handlers under adapters/inbound/ are covered.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(
            linter,
            'if req.link_type == "goal":\n    pass',
            file_path="adapters/inbound/principles_api.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL014"

    def test_fires_in_ui(self) -> None:
        linter = make_linter(["SKUEL014"])
        violations = lint_content(
            linter,
            'is_ku = item.get("_domain") == "ku"',
            file_path="ui/explore/cards.py",
            is_service=False,
        )
        assert len(violations) == 1

    def test_silent_outside_scope(self) -> None:
        # scripts/ and non-service core/ modules stay out of SKUEL014's scope.
        linter = make_linter(["SKUEL014"])
        for path in ("scripts/some_tool.py", "core/utils/neo4j_props.py"):
            violations = lint_content(
                linter,
                'if entity_type == "task":\n    pass',
                file_path=path,
                is_service=False,
            )
            assert violations == [], path

    def test_line_suppression(self) -> None:
        # Boundary-shaped comparison: a local taxonomy value that merely
        # collides with an entity-type name.
        linter = make_linter(["SKUEL014"])
        violations = lint_content(
            linter,
            'if state == "learning":'
            "  # skuel-lint: disable=SKUEL014 -- progress-state form protocol\n"
            "    pass",
        )
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL014"])
        content = (
            "# skuel-lint: disable-file=SKUEL014 -- local taxonomy module\n"
            'if kind == "ku":\n    pass\n'
            'if state == "learning":\n    pass\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0


class TestEntityTypeCatalogDrift:
    """The linter mirrors the FULL EntityType + NonKuDomain value sets.

    If those drift, SKUEL014 silently under-enforces — the pre-2026-07 catalog
    was missing 10 of 29 values (all six *_template types, user_entry, and the
    group/calendar/learning NonKuDomain values).
    """

    def test_linter_catalog_matches_entity_enums(self) -> None:
        # Import inside the test so collection still works in environments
        # where core/ isn't importable (e.g. minimal CI lint runners).
        from core.models.enums.entity_enums import EntityType, NonKuDomain

        actual = {m.value for m in EntityType} | {m.value for m in NonKuDomain}
        mirrored = set(SkuelLinter.ENTITY_TYPE_ENUM_VALUES)

        missing = actual - mirrored
        extra = mirrored - actual
        assert not missing, (
            f"SkuelLinter.ENTITY_TYPE_ENUM_VALUES is missing values present in "
            f"EntityType/NonKuDomain: {sorted(missing)}. "
            f"Add them to scripts/lint_skuel.py::SkuelLinter.ENTITY_TYPE_ENUM_VALUES."
        )
        assert not extra, (
            f"SkuelLinter.ENTITY_TYPE_ENUM_VALUES has values not in "
            f"EntityType/NonKuDomain: {sorted(extra)}. Move them to "
            f"LEGACY_ENTITY_TYPE_ALIASES if they are stale identifiers worth "
            f"catching, else remove them."
        )

    def test_legacy_aliases_disjoint_from_enum_values(self) -> None:
        # A name can't be both current and legacy — when an alias becomes a real
        # enum value (or vice versa), the catalogs must be updated.
        from core.models.enums.entity_enums import EntityType, NonKuDomain

        actual = {m.value for m in EntityType} | {m.value for m in NonKuDomain}
        overlap = set(SkuelLinter.LEGACY_ENTITY_TYPE_ALIASES) & actual
        assert not overlap, (
            f"LEGACY_ENTITY_TYPE_ALIASES contains current enum values: "
            f"{sorted(overlap)}. Remove them from the legacy set — "
            f"ENTITY_TYPE_ENUM_VALUES already covers them."
        )


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
            linter, content, file_path="core/utils/neo4j_props.py", is_service=False
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

    # --- Inbound/presentation scope (routes orchestrate, ui/ renders) ---

    def test_fires_in_inbound_adapters(self) -> None:
        """A route is above the boundary for the same reason core/ is (ADR-044)."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter,
            'rows = await adapter.execute_query("MATCH (u:User) RETURN u", {})',
            file_path="adapters/inbound/system_api.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"
        assert violations[0].severity == Severity.ERROR

    def test_fires_in_ui(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter,
            'q = "MERGE (n:Tag {name: $name})"',
            file_path="ui/explore/cards.py",
            is_service=False,
        )
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_skips_inbound_docstring_cypher(self) -> None:
        """The docstring-aware core still holds on the widened gate — a route may
        document the query its backend runs without authoring it."""
        linter = make_linter(["SKUEL021"])
        content = (
            "def route():\n"
            '    """Lists users.\n\n'
            "    Backend: UserBackend.list_users — MATCH (u:User) RETURN u\n"
            '    """\n'
            "    return None\n"
        )
        violations = lint_content(
            linter, content, file_path="adapters/inbound/user_api.py", is_service=False
        )
        assert len(violations) == 0

    def test_english_ui_strings_are_not_cypher(self) -> None:
        """Why CYPHER_MARKERS are clause+paren anchored rather than bare clause
        heads: the presentation layer is full of button labels and prose that open
        with a word that is also a Cypher clause. A bare-head matcher flags ~80 of
        these across adapters/inbound/ + ui/ and zero real queries."""
        linter = make_linter(["SKUEL021"])
        content = (
            'a = Button("Create Invoice")\n'
            'b = Button("Delete")\n'
            'c = Span("Show All")\n'
            'd = Li("Set your goals")\n'
            'e = dict(hx_confirm="Remove this relationship?")\n'
            'f = dict(methods=["DELETE"])\n'
            'g = Div("Use the filters above to refine your results")\n'
        )
        violations = lint_content(
            linter, content, file_path="ui/finance/invoice_views.py", is_service=False
        )
        assert len(violations) == 0

    def test_silent_outside_scope(self) -> None:
        """scripts/ authors Cypher legitimately (audits, migrations, benchmarks) and
        stays out of the gate — as does adapters/persistence/, which owns it."""
        for path in ("scripts/audit_graph_hygiene.py", "adapters/persistence/neo4j/backend.py"):
            violations = lint_content(
                make_linter(["SKUEL021"]),
                'q = "MATCH (n:Entity) RETURN n"',
                file_path=path,
                is_service=False,
            )
            assert violations == [], path


# ============================================================================
# SKUEL021: statement-head clause anchor
#
# CYPHER_MARKERS matches a substring ANYWHERE, so every marker has to be
# paren/sigil-anchored to stay out of prose — which left whole statement
# families with nothing to match on. The regression that proved it: for a long
# time `core/services/system_service_init.py` ran
# `await session.run("RETURN 1 as ping")` on a raw driver session, fully in
# SKUEL021's scope, with no suppression comment, and the rule never fired.
# (That module has since moved to services_bootstrap/_system_health.py, so
# core/ is clean of the class today — these tests exist so it stays that way.)
# ============================================================================


class TestSKUEL021LeadingClauseAnchor:
    # --- Families the anywhere-substring anchor could not see ---

    def test_detects_return_only_query(self) -> None:
        """The historical leak, verbatim: no paren, no sigil, still Cypher."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'await session.run("RETURN 1 as ping")')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"
        assert violations[0].severity == Severity.ERROR

    def test_detects_show_indexes(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "SHOW INDEXES YIELD name, state"')
        assert len(violations) == 1

    def test_detects_show_constraints(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "SHOW CONSTRAINTS YIELD name"')
        assert len(violations) == 1

    def test_detects_profile_prefixed_query(self) -> None:
        """`MATCH p=(a)` has no `MATCH (` substring — only the head anchor sees this."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "PROFILE MATCH p=(a)-[:USES_KU]->(b) RETURN p"')
        assert len(violations) == 1

    def test_detects_explain_prefixed_query(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "EXPLAIN MATCH p=(a)-[:USES_KU]->(b) RETURN p"')
        assert len(violations) == 1

    def test_detects_detach_delete_statement(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "DETACH DELETE n"')
        assert len(violations) == 1

    def test_detects_delete_statement(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "DELETE r"')
        assert len(violations) == 1

    def test_detects_set_statement(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "SET n.updated_at = $now"')
        assert len(violations) == 1

    def test_detects_remove_statement(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "REMOVE n.legacy_namespace"')
        assert len(violations) == 1

    def test_detects_load_csv_statement(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "LOAD CSV FROM $url AS row RETURN row"')
        assert len(violations) == 1

    def test_detects_non_db_call_procedure(self) -> None:
        """`CALL db.` was the only procedure namespace with a marker."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "CALL gds.graph.project($name, $nodes, $rels)"')
        assert len(violations) == 1

    def test_reports_the_clause_actually_written(self) -> None:
        """Longest-first matching: `DETACH DELETE`, not the `DELETE` prefix."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "DETACH DELETE n"')
        assert "DETACH DELETE" in violations[0].message

    def test_anchors_past_leading_comment_and_blank_lines(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = 'q = """\n// planner hint\nRETURN 1 as ping\n"""\nrun(q)'
        violations = lint_content(linter, content)
        assert len(violations) == 1

    # --- Prose must stay quiet: each guard, exercised ---

    def test_ignores_detach_delete_named_mid_sentence(self) -> None:
        """The head anchor, not the docstring carve-out: this string is *used*.

        `DETACH DELETE` is written mid-sentence ~30 times across core/ as a
        synonym for "delete". Only a statement that LEADS with it is Cypher.
        """
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'help_text = "cascade DETACH DELETE (default False)"')
        assert len(violations) == 0

    def test_ignores_bare_http_verb(self) -> None:
        """A clause keyword with no operand is not a statement."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'method = "DELETE"')
        assert len(violations) == 0

    def test_ignores_hyphenated_header_name(self) -> None:
        """Whitespace after the keyword is required — `SET-COOKIE` is not `SET`."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'header = "SET-COOKIE"')
        assert len(violations) == 0

    def test_ignores_words_that_merely_start_with_a_clause_name(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = (
            'a = "RETURNS the caller\'s uid"\n'
            'b = "CREATED at ingestion time"\n'
            'c = "WITHOUT a parent entity"\n'
            'd = "USER facing label"\n'
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_ignores_lowercase_prose_leading_with_a_clause_word(self) -> None:
        """Uppercase-only is the prose defence — and it is what makes it safe."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'msg = "set the value and return the result"')
        assert len(violations) == 0

    def test_ignores_docstring_leading_with_a_clause_keyword(self) -> None:
        """`core/ports/` docstrings open with "DETACH DELETE a user ..." — inert."""
        linter = make_linter(["SKUEL021"])
        content = (
            "def delete_user(uid):\n"
            '    """DETACH DELETE a user + every OWNS-linked entity (GDPR erasure)."""\n'
            "    return None\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    # --- f-strings: the head anchor reads the whole, never a torn part ---

    def test_detects_fstring_whose_operand_is_interpolated(self) -> None:
        """`f"RETURN {value}"` splits into the Constant "RETURN " — an operand short.

        Anchoring on the rendered whole (interpolation → sentinel) restores it.
        """
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'value = 1\nq = f"RETURN {value}"\nrun(q)')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_detects_fstring_delete_with_interpolated_operand(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'uid = 1\nq = f"DELETE {uid}"\nrun(q)')
        assert len(violations) == 1

    def test_ignores_prose_fstring_whose_fragment_leads_with_a_clause(self) -> None:
        """`f"cascade {mode} DETACH DELETE (...)"` tears into a fragment that
        falsely LEADS with the clause. The whole string plainly does not."""
        linter = make_linter(["SKUEL021"])
        content = 'mode = "x"\nmsg = f"cascade {mode} DETACH DELETE (default False)"'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_fstring_head_anchor_reports_once(self) -> None:
        """The JoinedStr and its parts must not both report."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'a = 1\nb = 2\nq = f"RETURN {a} AS x, {b} AS y"\nrun(q)')
        assert len(violations) == 1

    def test_fstring_anywhere_marker_still_reports_once(self) -> None:
        """The pre-existing anywhere-marker path keeps its per-part granularity."""
        linter = make_linter(["SKUEL021"])
        violations = lint_content(
            linter, 'uid = 1\nq = f"MATCH (n) WHERE n.id = {uid} RETURN n"\nrun(q)'
        )
        assert len(violations) == 1

    # --- `+` concatenation is a composite too, judged as a whole ---

    def test_detects_concatenated_head_only_query(self) -> None:
        """`"RETURN " + projection` tears the same way an f-string does."""
        linter = make_linter(["SKUEL021"])
        content = 'projection = "n.uid"\nquery = "RETURN " + projection\nrun(query)'
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_ignores_prose_built_by_concatenation(self) -> None:
        linter = make_linter(["SKUEL021"])
        content = 'mode = "x"\nmsg = "cascade " + mode + " DETACH DELETE (default False)"'
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_concatenated_query_reports_once(self) -> None:
        """A nested `+` chain resolves to its outermost root, not once per link."""
        linter = make_linter(["SKUEL021"])
        content = 'a = "1"\nb = "2"\nq = "RETURN " + a + " AS x, " + b + " AS y"\nrun(q)'
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_detects_marker_spanning_two_concatenated_literals(self) -> None:
        """`"MATCH " + "(n) RETURN n"` — the marker exists only in the whole.

        Two literal operands concatenate with NOTHING between them, so no single
        piece carries `MATCH (`. Suppressing the whole-report on "the rendered
        text matched" (rather than "a piece matched") made this invisible.
        """
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "MATCH " + "(n) RETURN n"\nrun(q)')
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL021"

    def test_concatenated_marker_still_reports_once(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, 'q = "MATCH (n)" + " RETURN n"\nrun(q)')
        assert len(violations) == 1

    def test_ignores_non_string_concatenation(self) -> None:
        linter = make_linter(["SKUEL021"])
        violations = lint_content(linter, "total = count + offset")
        assert len(violations) == 0

    def test_flatten_concat_walks_only_the_add_spine(self) -> None:
        """A `+` inside an operand's own expression is not part of the chain.

        Otherwise a string literal buried in an interpolated call argument would
        be spliced into the query text being reconstructed.
        """
        tree = ast.parse('x = "a " + helper(1 + 2) + " b"')
        root = tree.body[0].value  # type: ignore[attr-defined]
        leaves, nested = SkuelLinter._flatten_concat(root)
        assert [type(leaf).__name__ for leaf in leaves] == ["Constant", "Call", "Constant"]
        assert len(nested) == 1  # the inner spine link — NOT the `1 + 2` inside the call

    # --- Regression guard bound to the real files, not a hand-written stand-in ---

    def test_core_ports_docstring_prose_stays_clean(self) -> None:
        """The six `core/ports/` docstrings that name DETACH DELETE, linted for real.

        A synthetic equivalent would only prove the equivalent is clean. This
        runs the actual rule over the actual files, so a future widening cannot
        regress them silently.
        """
        ports = Path(__file__).resolve().parents[3] / "core" / "ports"
        prose_files = [
            "infrastructure_protocols.py",
            "domain_protocols.py",
            "conversation_protocols.py",
            "curriculum_protocols.py",
        ]
        checked = 0
        for name in prose_files:
            path = ports / name
            content = path.read_text(encoding="utf-8")
            assert "DETACH DELETE" in content, f"{name} no longer exercises this guard"
            checked += 1

            linter = make_linter(["SKUEL021"])
            tree = ast.parse(content)
            linter._check_raw_cypher_in_services(
                path, Path("core/ports") / name, content, content.split("\n"), tree
            )
            assert linter.result.violations == [], (
                f"SKUEL021 fired on docstring prose in core/ports/{name}"
            )
        assert checked == len(prose_files)


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
            "    from adapters.persistence.neo4j.insight_backend import InsightBackend\n"
            "\n"
            "class InsightStore:\n"
            '    def __init__(self, backend: "InsightBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(
            linter, content, file_path="core/services/insight/insight_store.py"
        )
        assert len(violations) == 0

    def test_facade_allowlist_explicit_file(self) -> None:
        """The standalone facade file (user_service.py) is explicitly
        allowlisted. The KU/PS/LP entries were removed by SoC arc PR 6 once
        those sites were retyped against core/ports protocols."""
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.user_context_query_executor import (\n"
            "        UserContextQueryExecutor,\n"
            "    )\n"
            "\n"
            "class UserService:\n"
            '    def __init__(self, backend: "UserContextQueryExecutor") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/user_service.py")
        assert len(violations) == 0

    @pytest.mark.parametrize(
        "file_path",
        [
            "core/services/ku_service.py",
            "core/services/ku/ku_core_service.py",
            "core/services/ps/ps_progress_service.py",
            "core/services/lp/lp_progress_service.py",
        ],
    )
    def test_ku_ps_lp_no_longer_allowlisted(self, file_path: str) -> None:
        """SoC arc PR 6 removed the KU / PS / LP allowlist entries.

        Every site they covered now types against a core/ports protocol, so the
        rule must actually fire on these paths. Pinned because a silent
        re-addition of the prefix would re-park the debt invisibly — the entries
        were the only reason SKUEL023 was quiet on 5 real violations.
        """
        linter = make_linter(["SKUEL023"])
        content = (
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend\n"
            "\n"
            "class SomeService:\n"
            '    def __init__(self, backend: "PsBackend") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path=file_path)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL023"

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
            "class UserService:\n"
            '    def __init__(self, backend: "adapters.persistence.neo4j.user_context_query_executor.UserContextQueryExecutor") -> None:\n'
            "        self.backend = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/user_service.py")
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
            "    import adapters.persistence.neo4j.user_context_query_executor as uq\n"
            "\n"
            "class UserService:\n"
            "    def __init__(self, backend: object) -> None:\n"
            "        self.backend: uq.UserContextQueryExecutor = backend\n"
        )
        violations = lint_content(linter, content, file_path="core/services/user_service.py")
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

    def test_opt_in_suppressible_rule_credited(self, tmp_path: Path) -> None:
        """A suppressed SKUEL029 finding is credited as used in the default sweep.
        Historically this exercised the opt-in shadow-lint path (#679); since the
        2026-07-18 promotion the rule runs in the main pass, so the normal
        suppression-honored accounting covers it — the assertion is unchanged."""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": (
                    "async def score(items):  # skuel-lint: disable=SKUEL029 -- uniform iface\n"
                    "    return sorted(items)\n"
                )
            },
        )
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is True
        skuel026 = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert skuel026 == []

    def test_malformed_opt_in_suppression_still_flagged(self, tmp_path: Path) -> None:
        """A MALFORMED suppression (loosely discovered, not strictly matched by
        `_is_line_suppressed`) is flagged as SKUEL026 rot — it does not actually
        suppress, so since promotion the main sweep also emits the SKUEL029
        violation itself. (Pre-promotion this needed the opt-in shadow lint —
        Codex P2, #679; the shadow path remains for future opt-in rules.)"""
        linter = self._lint_tree(
            tmp_path,
            {
                "core/services/x.py": (
                    "async def score(items):  #skuel-lint:disable=SKUEL029 -- malformed\n"
                    "    return sorted(items)\n"
                )
            },
        )
        assert len(linter.result.suppressions) == 1
        assert linter.result.suppressions[0].used is False
        skuel026 = [v for v in linter.result.violations if v.rule_id == "SKUEL026"]
        assert len(skuel026) == 1
        assert "malformed comment" in skuel026[0].message

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
            linter, content, file_path="ui/analytics/formats.py", is_service=False
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


class TestSKUEL028:
    """Result.fail(result.expect_error()) — use Result.fail(result) to propagate."""

    def test_detects_direct_unwrap_rewrap(self) -> None:
        linter = make_linter(["SKUEL028"])
        violations = lint_content(linter, "x = Result.fail(result.expect_error())")
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL028"

    def test_detects_conditional_expression_form(self) -> None:
        # The lp_service shape: expect_error() inside an IfExp argument.
        linter = make_linter(["SKUEL028"])
        content = (
            "x = Result.fail(\n"
            "    r.expect_error() if r.is_error else Errors.not_found('LP', uid)\n"
            ")"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].line_number == 2

    def test_detects_str_wrapped_flattening(self) -> None:
        # The category-flattening family: a NEW error built from the old one.
        linter = make_linter(["SKUEL028"])
        content = "x = Result.fail(Errors.database('op', str(r.expect_error())))"
        violations = lint_content(linter, content)
        assert len(violations) == 1

    def test_detects_keyword_argument_form(self) -> None:
        # Result.fail(error=r.expect_error()) is the same bypass (Codex P2, #678).
        linter = make_linter(["SKUEL028"])
        violations = lint_content(linter, "x = Result.fail(error=r.expect_error())")
        assert len(violations) == 1

    def test_propagation_clean(self) -> None:
        linter = make_linter(["SKUEL028"])
        violations = lint_content(linter, "x = Result.fail(result)")
        assert len(violations) == 0

    def test_read_use_clean(self) -> None:
        # .expect_error() outside Result.fail() is the sanctioned READ use.
        linter = make_linter(["SKUEL028"])
        content = "logger.warning(f'failed: {result.expect_error().message}')"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_fires_in_inbound_layer(self) -> None:
        linter = make_linter(["SKUEL028"])
        violations = lint_content(
            linter,
            "x = Result.fail(r.expect_error())",
            file_path="adapters/inbound/system_api.py",
            is_service=False,
        )
        assert len(violations) == 1

    def test_silent_in_tests(self) -> None:
        linter = make_linter(["SKUEL028"])
        violations = lint_content(
            linter,
            "x = Result.fail(r.expect_error())",
            file_path="tests/unit/test_x.py",
            is_service=False,
        )
        assert len(violations) == 0

    def test_line_suppression(self) -> None:
        linter = make_linter(["SKUEL028"])
        content = (
            "x = Result.fail(r.expect_error())  # skuel-lint: disable=SKUEL028 -- boundary re-wrap"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_file_suppression(self) -> None:
        linter = make_linter(["SKUEL028"])
        content = (
            "# skuel-lint: disable-file=SKUEL028 -- legacy propagation shim\n"
            "x = Result.fail(r.expect_error())"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0


class TestSKUEL029:
    """async def without await — opt-in audit rule."""

    def test_detects_awaitless_async_def(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = "async def score(items):\n    return sorted(items)"
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert violations[0].rule_id == "SKUEL029"

    def test_awaiting_function_clean(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = "async def fetch(uid):\n    return await backend.get(uid)"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_async_for_clean(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = "async def drain(q):\n    async for item in q:\n        handle(item)"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_async_with_clean(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = "async def tx(db):\n    async with db.session() as s:\n        s.ping()"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_trivial_bodies_exempt(self) -> None:
        # Protocol methods / stubs are declarations, not offenders.
        linter = make_linter(["SKUEL029"])
        content = (
            "class Ops(Protocol):\n"
            "    async def get(self, uid: str) -> Result:\n"
            "        ...\n"
            "\n"
            "async def docstring_only():\n"
            '    """Stub."""\n'
            "\n"
            "async def not_impl():\n"
            "    raise NotImplementedError\n"
            "\n"
            "async def passer():\n"
            "    pass\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_async_comprehension_exempt(self) -> None:
        # `[x async for x in ...]` is ast.comprehension(is_async=1), not
        # ast.AsyncFor — still genuine async work (Codex P3, #678 round 2).
        linter = make_linter(["SKUEL029"])
        content = "async def collect(stream):\n    return [x async for x in stream]"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_async_generator_exempt(self) -> None:
        # A yield-only async def is an ASYNC GENERATOR — async is load-bearing
        # without awaits; sync-ifying breaks `async for` callers (Codex P3, #678).
        linter = make_linter(["SKUEL029"])
        content = "async def stream(items):\n    for item in items:\n        yield item"
        violations = lint_content(linter, content)
        assert len(violations) == 0

    def test_nested_def_await_does_not_count(self) -> None:
        # An await inside a NESTED function belongs to the nested function.
        linter = make_linter(["SKUEL029"])
        content = (
            "async def outer():\n"
            "    async def inner():\n"
            "        return await thing()\n"
            "    return inner\n"
        )
        violations = lint_content(linter, content)
        assert len(violations) == 1
        assert "outer" in violations[0].message

    def test_promoted_rule_runs_in_default_sweep(self) -> None:
        # Promoted 2026-07-18 (OPT_IN_RULES no longer gates it): the default
        # sweep runs SKUEL029, and explicit --rule selection still works.
        linter = make_linter(None)
        assert linter._should_run_rule("SKUEL029") is True
        assert make_linter(["SKUEL029"])._should_run_rule("SKUEL029") is True

    def test_severity_is_error(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = "async def score(items):\n    return sorted(items)"
        violations = lint_content(linter, content)
        assert violations[0].severity == Severity.ERROR

    def test_line_suppression_honored(self) -> None:
        # SKUEL029 is suppressible: protocol-required async that never awaits is
        # a legitimate keep-async-and-suppress case.
        linter = make_linter(["SKUEL029"])
        content = (
            "async def score(items):  # skuel-lint: disable=SKUEL029 -- Protocol contract\n"
            "    return sorted(items)"
        )
        violations = lint_content(linter, content)
        assert violations == []

    def test_file_suppression_honored(self) -> None:
        linter = make_linter(["SKUEL029"])
        content = (
            "# skuel-lint: disable-file=SKUEL029 -- all handlers match a framework contract\n"
            "async def score(items):\n"
            "    return sorted(items)"
        )
        violations = lint_content(linter, content)
        assert violations == []

    def test_suppression_on_wrapped_signature_end_honored(self) -> None:
        # The span covers the full (ruff-wrapped) async-def header, so a comment
        # on the closing signature line is honored (mirrors SKUEL005).
        linter = make_linter(["SKUEL029"])
        content = (
            "async def score(\n"
            "    items: list[int],\n"
            ") -> list[int]:  # skuel-lint: disable=SKUEL029 -- Protocol contract\n"
            "    return sorted(items)"
        )
        violations = lint_content(linter, content)
        assert violations == []


class TestOptInRulesDrift:
    """Every OPT_IN_RULES member must be a real, documented rule — a typo'd id
    here would silently disable nothing while claiming to gate something."""

    def test_opt_in_rules_are_documented(self) -> None:
        from lint_skuel import RULE_DOCS

        assert set(RULE_DOCS) >= SkuelLinter.OPT_IN_RULES


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
