#!/usr/bin/env python3
"""
SKUEL Unified Linter
====================

Single linter enforcing all SKUEL architectural and code patterns.

RULES (by severity):

CRITICAL (blocks CI):
  SKUEL001: No APOC path procedures in domain services

ERROR (blocks CI):
  SKUEL002: Semantic type enums (not magic strings)
  SKUEL003: .is_err deprecated - use .is_error

WARNING (reported, doesn't block):
  SKUEL004: Confidence thresholds on semantic queries
  SKUEL005: Result[T] return types on service methods
  SKUEL007: String-based Result.fail() - use Errors factory
  SKUEL008: No wrapper classes around UniversalNeo4jBackend
  SKUEL011: hasattr() in production code - use Protocol/isinstance
  SKUEL012: Lambda expressions - use named functions
  SKUEL013: RelationshipName enum usage (not magic strings)
  SKUEL014: EntityType/NonKuDomain enum usage (not magic strings)
  SKUEL015: print() in production code - use logger instead

INFO (informational, visibility only):
  SKUEL006: TODO/FIXME comments - track technical debt

AUTO-FIXABLE:
  SKUEL003: .is_err → .is_error
  SKUEL009: Single-element tuple defaults (int = (0,) → int = 0)
  SKUEL010: Nested empty tuple defaults (((),) → ())

Usage:
    poetry run python scripts/lint_skuel.py           # Report violations
    poetry run python scripts/lint_skuel.py --fix    # Auto-fix where possible
    poetry run python scripts/lint_skuel.py --check  # Exit 1 if violations (for CI)
    poetry run python scripts/lint_skuel.py --strict # Treat warnings as errors
    poetry run python scripts/lint_skuel.py --file core/services/  # Lint specific path
    poetry run python scripts/lint_skuel.py --rule SKUEL003  # Run specific rule only
    poetry run python scripts/lint_skuel.py --explain SKUEL003  # Show rule documentation
    poetry run python scripts/lint_skuel.py --quiet  # Minimal output for CI
    poetry run python scripts/lint_skuel.py --context  # Show code context around violations

Last Updated: January 2026
"""

import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar


# ANSI color codes for terminal output
class Colors:
    """Terminal colors for better output readability."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


class Severity(Enum):
    """Violation severity levels."""

    CRITICAL = "CRITICAL"  # Blocks CI, must fix
    ERROR = "ERROR"  # Blocks CI, must fix
    WARNING = "WARNING"  # Reported, doesn't block
    INFO = "INFO"  # Informational only


# Rule documentation for --explain
RULE_DOCS: dict[str, dict[str, str]] = {
    "SKUEL001": {
        "title": "No APOC in Domain Services",
        "severity": "CRITICAL",
        "description": """APOC procedures are banned in domain services (core/services/*).
Use CypherGenerator or pure Cypher instead.

APOC is only allowed in adapter layer (adapters/persistence/*) for complex traversals.""",
        "good": """# Use CypherGenerator
query = CypherGenerator.build_prerequisite_chain(uid)
result = await backend.execute_query(query)""",
        "bad": """# Don't use APOC in services
query = "CALL apoc.path.subgraphAll(n, {...})"
result = await backend.execute_query(query)""",
    },
    "SKUEL002": {
        "title": "Use SemanticRelationshipType Enum",
        "severity": "ERROR",
        "description": """Use SemanticRelationshipType enum instead of magic strings
for semantic relationship types. This ensures type safety and autocomplete.""",
        "good": """from core.models.enums import SemanticRelationshipType
rel_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING""",
        "bad": """# Magic string - error prone
rel_type = "REQUIRES_THEORETICAL_UNDERSTANDING" """,
    },
    "SKUEL003": {
        "title": "Use .is_error Instead of .is_err",
        "severity": "ERROR",
        "description": """The .is_err property is deprecated. Use .is_error for better
readability and consistency with .is_ok/.is_error naming.""",
        "good": """if result.is_error:
    return result""",
        "bad": """if result.is_err:  # Deprecated
    return result""",
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL004": {
        "title": "Confidence Thresholds on Semantic Queries",
        "severity": "WARNING",
        "description": """Semantic relationship queries should include confidence thresholds
to filter out low-confidence relationships.""",
        "good": """MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
WHERE r.confidence >= $min_confidence
RETURN b""",
        "bad": """MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
RETURN b  -- No confidence filter!""",
    },
    "SKUEL005": {
        "title": "Service Methods Should Return Result[T]",
        "severity": "WARNING",
        "description": """Public async service methods should return Result[T] for
consistent error handling throughout the application.""",
        "good": """async def get_task(self, uid: str) -> Result[Task]:
    ...""",
        "bad": """async def get_task(self, uid: str) -> Task:  # Should be Result[Task]
    ...""",
    },
    "SKUEL006": {
        "title": "TODO/FIXME Comments",
        "severity": "INFO",
        "description": """Tracks TODO and FIXME comments for technical debt visibility.
These markers indicate incomplete implementations or planned improvements.

This rule is informational only - it doesn't block CI but makes
technical debt visible during code review.""",
        "good": """# Completed implementation with no TODOs""",
        "bad": """# TODO: Implement this feature later
# FIXME: This needs to be refactored""",
    },
    "SKUEL007": {
        "title": "Use Errors Factory for Result.fail()",
        "severity": "WARNING",
        "description": """Use the Errors factory (Errors.validation(), Errors.not_found(), etc.)
instead of string-based Result.fail() for structured error handling.""",
        "good": """return Result.fail(Errors.not_found("Task", uid))
return Result.fail(Errors.validation("Invalid input", field="email"))""",
        "bad": """return Result.fail("Task not found")  # String-based
return Result.fail(f"Error: {e}")  # String-based""",
    },
    "SKUEL008": {
        "title": "No Wrapper Classes Around UniversalNeo4jBackend",
        "severity": "WARNING",
        "description": """Use UniversalNeo4jBackend directly instead of creating wrapper classes.
The 100% dynamic pattern means no wrapper code is needed.""",
        "good": """tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)""",
        "bad": """class TasksBackend(UniversalNeo4jBackend[Task]):  # Wrapper not needed
    pass""",
    },
    "SKUEL009": {
        "title": "Single-Element Tuple Defaults Are Bugs",
        "severity": "WARNING",
        "description": """A single-element tuple like (0,) is usually a mistake. If you want
a scalar default, remove the parentheses and comma.""",
        "good": """count: int = 0
name: str = "" """,
        "bad": """count: int = (0,)  # Probably meant 0
name: str = ("",)  # Probably meant "" """,
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL010": {
        "title": "Nested Empty Tuples Can't Be Stored",
        "severity": "WARNING",
        "description": """Neo4j cannot store nested collections. Use () instead of ((),).""",
        "good": """items: tuple = ()""",
        "bad": """items: tuple = ((),)  # Neo4j can't store this""",
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL011": {
        "title": "No hasattr() in Production Code",
        "severity": "WARNING",
        "description": """Use explicit type checks (isinstance, Protocol) instead of hasattr().
hasattr() is error-prone and bypasses type safety.

Exceptions: tests/, sort_functions.py, mock utilities.""",
        "good": """# Use Protocol checking
if isinstance(obj, HasValue):
    return obj.value

# Use explicit attribute check
if user.preferences is not None:
    prefs = user.preferences

# Use helper for enums
from core.ports import get_enum_value
value = get_enum_value(obj)""",
        "bad": """# hasattr bypasses type safety
if hasattr(obj, 'value'):
    return obj.value

if hasattr(user, 'preferences'):
    prefs = user.preferences""",
    },
    "SKUEL012": {
        "title": "No Lambda Expressions",
        "severity": "WARNING",
        "description": """Use named functions instead of lambda expressions. Named functions
are self-documenting, testable, and reusable.

Exceptions: tests/, examples/, mock utilities.""",
        "good": """from core.utils.sort_functions import get_priority_value

def get_priority(item):
    \"\"\"Get numeric priority for sorting.\"\"\"
    return item.priority.to_numeric()

tasks.sort(key=get_priority_value)""",
        "bad": """tasks.sort(key=lambda t: t.priority.to_numeric())
get_priority = lambda item: item.priority.to_numeric()""",
    },
    "SKUEL013": {
        "title": "Use RelationshipName Enum",
        "severity": "WARNING",
        "description": """Use RelationshipName enum instead of magic strings for
relationship type parameters. Single source of truth in relationship_names.py.""",
        "good": """from core.models.relationship_names import RelationshipName
await backend.add_relationship(uid1, RelationshipName.SERVES_GOAL, uid2)""",
        "bad": """# Magic string - error prone
await backend.add_relationship(uid1, "SERVES_GOAL", uid2)""",
    },
    "SKUEL014": {
        "title": "Use EntityType/NonKuDomain Enum",
        "severity": "WARNING",
        "description": """Use EntityType or NonKuDomain enum instead of magic strings for entity type
identification. Provides type safety and compile-time verification.""",
        "good": """from core.models.enums.entity_enums import EntityType
if entity.ku_type == EntityType.TASK:
    ...
if EntityType.TASK in activity.contexts:
    ...""",
        "bad": """# String comparison - error prone
if entity_type == "task":
    ...
if "task" in contexts:
    ...""",
    },
    "SKUEL015": {
        "title": "No print() in Production Code",
        "severity": "WARNING",
        "description": """Use logger.*() instead of print() for production runtime output.
Print bypasses logging infrastructure, making debugging and monitoring harder.

Exceptions: CLI utilities, docstring examples, __main__ blocks.""",
        "good": """from core.utils.logging import get_logger
logger = get_logger("skuel.config")

def validate_config():
    if missing:
        logger.error("Missing config", missing=missing)
        return False""",
        "bad": """def validate_config():
    if missing:
        print(f"Missing: {missing}")  # Bypasses logging
        return False""",
    },
}


@dataclass
class Violation:
    """A linting violation."""

    file_path: Path
    line_number: int
    column: int
    severity: Severity
    rule_id: str
    message: str
    suggestion: str
    fix_available: bool = False
    original_text: str = ""
    fixed_text: str = ""
    line_content: str = ""  # The actual line of code


@dataclass
class LintResult:
    """Results from linting."""

    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    scan_time_ms: float = 0.0

    @property
    def has_critical(self) -> bool:
        return any(v.severity == Severity.CRITICAL for v in self.violations)

    @property
    def has_error(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    @property
    def has_warning(self) -> bool:
        return any(v.severity == Severity.WARNING for v in self.violations)

    def by_severity(self, severity: Severity) -> list[Violation]:
        return [v for v in self.violations if v.severity == severity]

    def by_file(self) -> dict[Path, list[Violation]]:
        """Group violations by file for easier reading."""
        result: dict[Path, list[Violation]] = {}
        for v in self.violations:
            if v.file_path not in result:
                result[v.file_path] = []
            result[v.file_path].append(v)
        return result

    def by_rule(self, rule_id: str) -> list[Violation]:
        return [v for v in self.violations if v.rule_id == rule_id]


class SkuelLinter:
    """
    Unified SKUEL linter combining architecture and pattern rules.

    Design principles:
    - High-value rules only (no pedantic checks)
    - Auto-fix where possible
    - Clear, actionable suggestions
    - Minimal false positives
    """

    # Directories to exclude
    EXCLUDED_PATHS: ClassVar[list[str]] = [
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "backup_archive",
        "z_archives",
        "zarchives",
        "scripts/migrations",  # Migration scripts document old patterns
        "scripts/lint_skuel",  # Linter files document patterns they check
        ".claude",  # Claude Code config/skills (documentation only)
    ]

    # Files where hasattr is allowed
    HASATTR_ALLOWED_FILES: ClassVar[list[str]] = [
        "sort_functions.py",
        "mock_decorators.py",
        "test_",
        "/tests/",
        "type_converters.py",  # Documents Protocol-based approach
        "graphql/protocols.py",  # Documents why hasattr not needed
        "graphql/schema.py",  # Uses Protocol guarantees
        "graphql/types.py",  # Documents Protocol benefits
        "context_first_mixin.py",  # Documents _get_attr as hasattr alternative
        "_ui.py",  # UI routes handle mixed types defensively
        "_components.py",  # UI components handle mixed types defensively
        "base_service.py",  # Generic service class handles dynamic config objects
        "ku_intelligence_service.py",  # Defensive checks for optional model methods
    ]

    # Files where lambda is allowed
    LAMBDA_ALLOWED_FILES: ClassVar[list[str]] = [
        "test_",
        "/tests/",
        "/examples/",
        "mock_decorators.py",
    ]

    # Files where print is allowed
    PRINT_ALLOWED_FILES: ClassVar[list[str]] = [
        "test_",
        "/tests/",
        "/examples/",
        "/scripts/",  # CLI utilities
        "credential_setup.py",  # CLI utility
        "lint_skuel.py",  # Linter itself uses print for output
        "dev",  # dev script
        "debug_",  # Debug scripts
        "version_manager.py",  # CLI utility
        "github_manager.py",  # CLI utility
        "config/validation.py",  # Has print_validation_report() for CLI output
    ]

    # Curriculum backends that legitimately extend UniversalNeo4jBackend
    CURRICULUM_BACKENDS: ClassVar[list[str]] = [
        "ls_backend.py",
        "lp_backend.py",
        "moc_backend.py",
        "ku_backend.py",
    ]

    def __init__(
        self,
        root_dir: Path,
        target_path: str | None = None,
        rules_filter: list[str] | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.target_path = target_path
        self.rules_filter = rules_filter
        self.result = LintResult()

    def lint(self) -> LintResult:
        """Run all linting rules."""
        start_time = time.time()
        python_files = self._find_python_files()
        self.result.files_scanned = len(python_files)

        for file_path in python_files:
            self._lint_file(file_path)

        self.result.scan_time_ms = (time.time() - start_time) * 1000
        return self.result

    def _should_run_rule(self, rule_id: str) -> bool:
        """Check if a rule should run based on filter."""
        if self.rules_filter is None:
            return True
        return rule_id in self.rules_filter

    def _find_python_files(self) -> list[Path]:
        """Find all Python files to lint."""
        python_files = []

        # Determine search path
        if self.target_path:
            search_root = self.root_dir / self.target_path
            if not search_root.exists():
                print(f"Error: Path not found: {search_root}", file=sys.stderr)
                return []
            if search_root.is_file():
                return [search_root] if search_root.suffix == ".py" else []
        else:
            search_root = self.root_dir

        for py_file in search_root.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir))

            # Skip excluded paths
            if any(excluded in rel_path for excluded in self.EXCLUDED_PATHS):
                continue

            python_files.append(py_file)

        return python_files

    def _lint_file(self, file_path: Path) -> None:
        """Lint a single file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel_path = file_path.relative_to(self.root_dir)
            is_test = "test_" in file_path.name or "/tests/" in str(file_path)
            is_service = "/services/" in str(file_path) and file_path.suffix == ".py"

            # Run applicable rules
            if self._should_run_rule("SKUEL003"):
                self._check_is_err_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL009"):
                self._check_tuple_defaults(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL010"):
                self._check_nested_tuple_defaults(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL011") and not is_test:
                self._check_hasattr_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL012") and not is_test:
                self._check_lambda_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL015") and not is_test:
                self._check_print_statements(file_path, rel_path, content, lines)

            # INFO rules (always run for visibility)
            if self._should_run_rule("SKUEL006"):
                self._check_todo_comments(file_path, rel_path, content, lines)

            if is_service and not is_test:
                if self._should_run_rule("SKUEL001"):
                    self._check_apoc_in_services(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL002"):
                    self._check_semantic_type_strings(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL004"):
                    self._check_confidence_thresholds(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL005"):
                    self._check_result_return_types(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL007"):
                    self._check_string_result_fail(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL013"):
                    self._check_relationship_name_strings(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL014"):
                    self._check_entity_type_strings(file_path, rel_path, content, lines)

            if "/adapters/persistence/" in str(file_path):
                if self._should_run_rule("SKUEL008"):
                    self._check_backend_wrappers(file_path, rel_path, content)

        except Exception as e:
            print(f"Error linting {file_path}: {e}", file=sys.stderr)

    # =========================================================================
    # CRITICAL RULES
    # =========================================================================

    def _check_apoc_in_services(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL001 [CRITICAL]: No APOC path procedures in domain services.
        """
        banned_apoc = [
            "apoc.path.subgraphNodes",
            "apoc.path.subgraphAll",
            "apoc.path.expandConfig",
            "apoc.path.spanningTree",
            "apoc.cypher.run",
            "apoc.cypher.runMany",
            "apoc.map.",
            "apoc.schema.",
            "apoc.meta.",
        ]

        for line_num, line in enumerate(lines, start=1):
            for apoc_proc in banned_apoc:
                if apoc_proc in line:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=line.find(apoc_proc),
                            severity=Severity.CRITICAL,
                            rule_id="SKUEL001",
                            message=f"APOC procedure '{apoc_proc}' in domain service",
                            suggestion="Use CypherGenerator or pure Cypher instead",
                            line_content=line.strip(),
                        )
                    )

    # =========================================================================
    # ERROR RULES
    # =========================================================================

    def _check_semantic_type_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL002 [ERROR]: Use SemanticRelationshipType enum, not magic strings.
        """
        semantic_types = [
            "REQUIRES_THEORETICAL_UNDERSTANDING",
            "REQUIRES_PRACTICAL_APPLICATION",
            "REQUIRES_CONCEPTUAL_FOUNDATION",
            "BUILDS_ON_FOUNDATION",
            "HAS_BROADER_CONCEPT",
            "HAS_NARROWER_CONCEPT",
            "SHARES_PRINCIPLE_WITH",
            "ANALOGOUS_TO",
        ]

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            for sem_type in semantic_types:
                if f'"{sem_type}"' in line or f"'{sem_type}'" in line:
                    if f"SemanticRelationshipType.{sem_type}" not in line:
                        self.result.violations.append(
                            Violation(
                                file_path=rel_path,
                                line_number=line_num,
                                column=line.find(sem_type),
                                severity=Severity.ERROR,
                                rule_id="SKUEL002",
                                message=f"Magic string '{sem_type}' - use enum instead",
                                suggestion=f"Use SemanticRelationshipType.{sem_type}",
                                line_content=line.strip(),
                            )
                        )

    def _check_is_err_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL003 [ERROR]: Use .is_error instead of deprecated .is_err.
        """
        if "lint_skuel" in str(file_path):
            return

        pattern = r"\.is_err\b"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]
            col = match.start() - content[: match.start()].rfind("\n") - 1

            if ".is_error" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=col,
                    severity=Severity.ERROR,
                    rule_id="SKUEL003",
                    message="Deprecated .is_err - use .is_error instead",
                    suggestion="Replace .is_err with .is_error",
                    fix_available=True,
                    original_text=".is_err",
                    fixed_text=".is_error",
                    line_content=line.strip(),
                )
            )

    # =========================================================================
    # WARNING RULES
    # =========================================================================

    def _check_confidence_thresholds(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL004 [WARNING]: Semantic queries should have confidence thresholds.
        """
        semantic_patterns = [
            "REQUIRES_THEORETICAL_UNDERSTANDING",
            "REQUIRES_PRACTICAL_APPLICATION",
            "REQUIRES_CONCEPTUAL_FOUNDATION",
            "BUILDS_ON_FOUNDATION",
            "SHARES_PRINCIPLE_WITH",
            "ANALOGOUS_TO",
        ]

        structural_patterns = [
            "APPLIES_KNOWLEDGE",
            "ENABLES",
            "PREREQUISITE",
            "HAS_STEP",
            "HAS_PATH",
            "CONTRIBUTES_TO",
        ]

        for line_num, line in enumerate(lines, start=1):
            if "MATCH" not in line:
                continue

            has_semantic = any(p in line for p in semantic_patterns)
            has_structural = any(p in line for p in structural_patterns)

            if has_semantic and not has_structural:
                context = "\n".join(lines[line_num : min(line_num + 5, len(lines))])
                if "confidence" not in context:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=0,
                            severity=Severity.WARNING,
                            rule_id="SKUEL004",
                            message="Semantic query without confidence threshold",
                            suggestion="Add: WHERE r.confidence >= $min_confidence",
                            line_content=line.strip(),
                        )
                    )

    def _check_result_return_types(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL005 [WARNING]: Service methods should return Result[T].
        """
        if "protocol" in str(file_path).lower():
            return

        utility_patterns = [
            "get(self, key:",
            "set(self, key:",
            "delete(self, key:",
            "clear(self)",
            "_get_",
            "get_hit_rate",
            "is_expired",
            "_evict",
            "_adaptive",
            "_update_access",
            "_remove_from",
            "handle_",
            "increment_",
            "ensure_",
        ]

        utility_files = [
            "performance_optimization_service.py",
            "base_service.py",
            "user_context_intelligence.py",
            "progress_report_worker.py",
        ]

        if any(uf in str(file_path) for uf in utility_files):
            return

        base_method_indent: int | None = None

        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                continue

            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if stripped.startswith(("def ", "async def ")):
                if base_method_indent is None:
                    base_method_indent = indent
                elif indent <= base_method_indent:
                    base_method_indent = indent

            if "async def" in line and "->" in line:
                if base_method_indent is not None and indent > base_method_indent:
                    continue

                if "def _" in line or "def __" in line:
                    continue

                if any(p in line for p in utility_patterns):
                    continue

                # Skip @classmethod methods (factory methods on dataclasses, not services)
                is_classmethod = False
                for prev_idx in range(line_num - 2, max(0, line_num - 5), -1):
                    prev_stripped = lines[prev_idx].strip()
                    if prev_stripped == "@classmethod":
                        is_classmethod = True
                        break
                    if not prev_stripped.startswith("@"):
                        break
                if is_classmethod:
                    continue

                if "Result[" not in line:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=0,
                            severity=Severity.WARNING,
                            rule_id="SKUEL005",
                            message="Service method should return Result[T]",
                            suggestion="Change return type to Result[T]",
                            line_content=line.strip(),
                        )
                    )

    def _check_string_result_fail(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL007 [WARNING]: Use Errors factory instead of string Result.fail().
        """
        pattern = r'Result\.fail\s*\(\s*[f]?["\']'

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            if "Errors." in line or "result.error" in line or ".error)" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL007",
                    message="String-based Result.fail() - use Errors factory",
                    suggestion="Use Errors.validation(), Errors.not_found(), etc.",
                    line_content=line.strip(),
                )
            )

    def _check_backend_wrappers(self, file_path: Path, rel_path: Path, content: str) -> None:
        """
        SKUEL008 [WARNING]: No wrapper classes around UniversalNeo4jBackend.

        Exception: Curriculum backends (ls, lp, moc, ku) legitimately extend
        UniversalNeo4jBackend to add domain-specific methods.
        """
        if "universal_backend" in str(file_path):
            return

        # Skip curriculum backends - these legitimately extend for domain methods
        if any(backend in str(file_path) for backend in self.CURRICULUM_BACKENDS):
            return

        if "UniversalNeo4jBackend" not in content:
            return

        pattern = r"class\s+(\w+Backend)\([^)]*UniversalNeo4jBackend"
        lines = content.split("\n")
        for match in re.finditer(pattern, content):
            class_name = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL008",
                    message=f"Wrapper class '{class_name}' around UniversalNeo4jBackend",
                    suggestion="Use UniversalNeo4jBackend directly (100% dynamic pattern)",
                    line_content=lines[line_num - 1].strip() if line_num <= len(lines) else "",
                )
            )

    def _check_hasattr_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL011 [WARNING]: No hasattr() in production code.
        """
        # Skip allowed files
        file_str = str(file_path)
        if any(allowed in file_str for allowed in self.HASATTR_ALLOWED_FILES):
            return

        pattern = r"\bhasattr\s*\("

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            # Skip comments
            if line.strip().startswith("#"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=match.start() - content[: match.start()].rfind("\n") - 1,
                    severity=Severity.WARNING,
                    rule_id="SKUEL011",
                    message="hasattr() usage - use Protocol/isinstance instead",
                    suggestion="Use isinstance(obj, Protocol) or explicit attribute checks",
                    line_content=line.strip(),
                )
            )

    def _check_lambda_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL012 [WARNING]: No lambda expressions - use named functions.
        """
        # Skip allowed files
        file_str = str(file_path)
        if any(allowed in file_str for allowed in self.LAMBDA_ALLOWED_FILES):
            return

        pattern = r"\blambda\s+\w*\s*:"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=match.start() - content[: match.start()].rfind("\n") - 1,
                    severity=Severity.WARNING,
                    rule_id="SKUEL012",
                    message="Lambda expression - use named function instead",
                    suggestion="Define a named function or use sort_functions helper",
                    line_content=line.strip(),
                )
            )

    def _check_relationship_name_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL013 [WARNING]: Use RelationshipName enum instead of magic strings.
        """
        # Common relationship names that should use enum
        relationship_names = [
            "SERVES_GOAL",
            "SERVES_LIFE_PATH",
            "APPLIES_KNOWLEDGE",
            "REQUIRES_KNOWLEDGE",
            "REINFORCES_KNOWLEDGE",
            "FULFILLS_GOAL",
            "SUPPORTS_GOAL",
            "ALIGNED_WITH_PRINCIPLE",
            "GUIDES_GOAL",
            "GUIDES_CHOICE",
            "HAS_STEP",
            "HAS_PATH",
            "CONTRIBUTES_TO",
            "ENABLES",
            "PREREQUISITE",
        ]

        # Track docstring context
        in_docstring = False
        docstring_delimiter = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring state
            if not in_docstring:
                for delim in ['"""', "'''"]:
                    if delim in stripped:
                        count = stripped.count(delim)
                        if count == 1:
                            in_docstring = True
                            docstring_delimiter = delim
                            break
                        # Single-line docstring - skip this line
                        if count >= 2 and stripped.startswith(delim):
                            continue
            else:
                if docstring_delimiter and docstring_delimiter in stripped:
                    in_docstring = False
                    docstring_delimiter = None
                continue  # Skip lines inside docstrings

            if stripped.startswith("#"):
                continue

            # Skip if already using enum
            if "RelationshipName." in line:
                continue

            for rel_name in relationship_names:
                # Check for quoted string usage in function calls
                if f'"{rel_name}"' in line or f"'{rel_name}'" in line:
                    # Skip if it's in a Cypher query string (those need literal strings)
                    if "MATCH" in line or "-[:" in line or "]->" in line or "CREATE" in line:
                        continue

                    # Skip if we're inside a multi-line Cypher query (check context)
                    # Look at surrounding lines for Cypher indicators
                    context_start = max(0, line_num - 10)
                    context_lines = lines[context_start:line_num]
                    in_cypher_context = any(
                        "MATCH" in l or "WHERE any(r in relationships" in l or "type(r) IN" in l
                        for l in context_lines
                    )
                    if in_cypher_context:
                        continue

                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=line.find(rel_name),
                            severity=Severity.WARNING,
                            rule_id="SKUEL013",
                            message=f"Magic string '{rel_name}' - use RelationshipName enum",
                            suggestion=f"Use RelationshipName.{rel_name}",
                            line_content=line.strip(),
                        )
                    )

    def _check_entity_type_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL014 [WARNING]: Use EntityType/NonKuDomain enum instead of magic strings.
        """
        # Entity types that should use enum
        entity_types = [
            "task",
            "habit",
            "goal",
            "event",
            "choice",
            "principle",
            "finance",
            "ku",
            "lp",
            "ls",
            "moc",
        ]

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            # Skip if already using enum
            if "EntityType." in line or "NonKuDomain." in line:
                continue

            # Skip imports and type hints
            if "import" in line or "EntityType" in line or "NonKuDomain" in line:
                continue

            for entity_type in entity_types:
                # Look for entity type comparisons like == "task" or in ["task", ...]
                patterns_to_check = [
                    f'== "{entity_type}"',
                    f"== '{entity_type}'",
                    f'"{entity_type}" in ',
                    f"'{entity_type}' in ",
                    f'entity_type == "{entity_type}"',
                    f"entity_type == '{entity_type}'",
                ]

                for pattern in patterns_to_check:
                    if pattern in line.lower():
                        self.result.violations.append(
                            Violation(
                                file_path=rel_path,
                                line_number=line_num,
                                column=0,
                                severity=Severity.WARNING,
                                rule_id="SKUEL014",
                                message=f"Magic string '{entity_type}' - use EntityType/NonKuDomain enum",
                                suggestion=f"Use EntityType.{entity_type.upper()} or NonKuDomain.{entity_type.upper()}",
                                line_content=line.strip(),
                            )
                        )
                        break  # Only report once per line

    def _check_print_statements(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL015 [WARNING]: No print() in production code - use logger.

        Exception: CLI utilities, scripts, tests, docstrings, __main__ blocks.
        """
        # Skip allowed files
        file_str = str(file_path)
        if any(allowed in file_str for allowed in self.PRINT_ALLOWED_FILES):
            return

        # Track context state
        in_docstring = False
        in_main_block = False
        docstring_delimiter = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring state (handles multi-line docstrings)
            if not in_docstring:
                # Check for docstring start
                for delim in ['"""', "'''"]:
                    if delim in stripped:
                        # Count occurrences to detect single-line vs multi-line
                        count = stripped.count(delim)
                        if count == 1:
                            # Multi-line docstring starts
                            in_docstring = True
                            docstring_delimiter = delim
                            break
                        if count >= 2:
                            # Single-line docstring or line with string literal
                            # Skip this line entirely if it looks like a docstring
                            if stripped.startswith(delim):
                                break
            else:
                # Check for docstring end
                if docstring_delimiter and docstring_delimiter in stripped:
                    in_docstring = False
                    docstring_delimiter = None
                continue  # Skip all lines inside docstrings

            # Track __main__ block
            if 'if __name__ == "__main__"' in line or "if __name__ == '__main__'" in line:
                in_main_block = True
                continue

            # Skip if in __main__ block (rest of file after that)
            if in_main_block:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Skip doctest examples (>>> prefix)
            if stripped.startswith(">>>"):
                continue

            # Check for print() calls
            pattern = r"\bprint\s*\("
            for match in re.finditer(pattern, line):
                # Skip if it's a comment on the same line before print
                before_print = line[: match.start()]
                if "#" in before_print:
                    continue

                # Skip if print is inside a string (rough heuristic)
                # Count quotes before the print to detect if we're in a string
                quote_count = before_print.count('"') + before_print.count("'")
                if quote_count % 2 == 1:
                    continue  # Odd number of quotes = likely inside a string

                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=match.start(),
                        severity=Severity.WARNING,
                        rule_id="SKUEL015",
                        message="print() in production code - use logger instead",
                        suggestion="Use logger.info(), logger.debug(), or logger.error()",
                        line_content=line.strip(),
                    )
                )

    # =========================================================================
    # INFO RULES (visibility only)
    # =========================================================================

    def _check_todo_comments(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL006 [INFO]: Track TODO/FIXME comments for technical debt visibility.

        This rule is informational only - it doesn't block CI but makes
        technical debt visible during code review.
        """
        pattern = r"#.*\b(TODO|FIXME)\b"

        for line_num, line in enumerate(lines, start=1):
            match = re.search(pattern, line)
            if match:
                marker = match.group(1)
                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=match.start(),
                        severity=Severity.INFO,
                        rule_id="SKUEL006",
                        message=f"{marker} comment - technical debt marker",
                        suggestion="Resolve or document this item in issue tracker",
                        line_content=line.strip(),
                    )
                )

    # =========================================================================
    # AUTO-FIXABLE RULES
    # =========================================================================

    def _check_tuple_defaults(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL009 [WARNING]: Single-element tuple defaults are usually bugs.
        """
        pattern = r":\s*\w+\s*=\s*\(([^)]+),\s*\)"

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if "→" in line:
                continue
            if "tuple[" in line.lower() or "Tuple[" in line:
                continue
            if "field(" in line and "default_factory" in line:
                continue

            match = re.search(pattern, line)
            if match:
                value = match.group(1).strip()
                original = f"({value},)"
                fixed = value

                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=line.find(original),
                        severity=Severity.WARNING,
                        rule_id="SKUEL009",
                        message="Single-element tuple default - likely a bug",
                        suggestion=f"Change = ({value},) to = {value}",
                        fix_available=True,
                        original_text=f"= {original}",
                        fixed_text=f"= {fixed}",
                        line_content=line.strip(),
                    )
                )

    def _check_nested_tuple_defaults(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL010 [WARNING]: Nested empty tuples can't be stored in Neo4j.
        """
        pattern = r"=\s*\(\(\s*\)\s*,\s*\)"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1].strip()

            if line.startswith("#") or line.startswith('"""') or line.startswith("'''"):
                continue
            if "→" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL010",
                    message="Nested empty tuple - Neo4j can't store nested collections",
                    suggestion="Change ((),) to ()",
                    fix_available=True,
                    original_text="((),)",
                    fixed_text="()",
                    line_content=line,
                )
            )

    # =========================================================================
    # AUTO-FIX
    # =========================================================================

    def apply_fixes(self) -> int:
        """Apply auto-fixes to violations that support it."""
        fixable = [v for v in self.result.violations if v.fix_available]

        if not fixable:
            print("No auto-fixable violations found.")
            return 0

        by_file: dict[Path, list[Violation]] = {}
        for v in fixable:
            full_path = self.root_dir / v.file_path
            if full_path not in by_file:
                by_file[full_path] = []
            by_file[full_path].append(v)

        fixed_count = 0
        for file_path, violations in by_file.items():
            content = file_path.read_text(encoding="utf-8")
            original = content

            for v in sorted(violations, key=lambda x: x.line_number, reverse=True):
                if v.original_text and v.fixed_text:
                    content = content.replace(v.original_text, v.fixed_text, 1)
                    fixed_count += 1

            if content != original:
                file_path.write_text(content, encoding="utf-8")
                rel_path = file_path.relative_to(self.root_dir)
                print(
                    f"{Colors.GREEN}✓{Colors.RESET} Fixed {len(violations)} violation(s) in {rel_path}"
                )

        print(
            f"\n{Colors.GREEN}✓{Colors.RESET} Applied {fixed_count} auto-fixes across {len(by_file)} files"
        )
        return fixed_count

    # =========================================================================
    # REPORTING
    # =========================================================================

    def print_report(
        self, strict: bool = False, quiet: bool = False, show_context: bool = False
    ) -> int:
        """
        Print violations report.

        Returns exit code:
            0 - No blocking violations
            1 - Warnings found (only in strict mode)
            2 - Errors or critical violations found
        """
        if not self.result.violations:
            if not quiet:
                print(
                    f"{Colors.GREEN}✅ No SKUEL violations found!{Colors.RESET} "
                    f"({self.result.files_scanned} files scanned in {self.result.scan_time_ms:.0f}ms)"
                )
            return 0

        if quiet:
            # Minimal output for CI
            critical = len(self.result.by_severity(Severity.CRITICAL))
            errors = len(self.result.by_severity(Severity.ERROR))
            warnings = len(self.result.by_severity(Severity.WARNING))
            print(f"SKUEL: {critical} critical, {errors} errors, {warnings} warnings")
            if critical or errors:
                return 2
            if strict and warnings:
                return 1
            return 0

        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}SKUEL LINTER{Colors.RESET}")
        print(f"{'=' * 80}")
        print(f"Scanned {self.result.files_scanned} files in {self.result.scan_time_ms:.0f}ms")
        print()

        # Group and print by severity
        for severity in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]:
            violations = self.result.by_severity(severity)
            if not violations:
                continue

            icon, color = {
                Severity.CRITICAL: ("🔴", Colors.RED),
                Severity.ERROR: ("❌", Colors.RED),
                Severity.WARNING: ("⚠️ ", Colors.YELLOW),
                Severity.INFO: ("ℹ️ ", Colors.BLUE),
            }[severity]

            print(
                f"{icon} {color}{Colors.BOLD}{severity.value}: {len(violations)} violation(s){Colors.RESET}"
            )
            print(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

            # Group by file for better readability
            by_file: dict[Path, list[Violation]] = {}
            for v in violations:
                if v.file_path not in by_file:
                    by_file[v.file_path] = []
                by_file[v.file_path].append(v)

            for file_path, file_violations in sorted(by_file.items()):
                print(f"\n  {Colors.CYAN}{file_path}{Colors.RESET}")
                for v in sorted(file_violations, key=lambda x: x.line_number):
                    fix_tag = f" {Colors.GREEN}[auto-fix]{Colors.RESET}" if v.fix_available else ""
                    print(
                        f"    {Colors.DIM}L{v.line_number}:{v.column}{Colors.RESET} [{v.rule_id}] {v.message}{fix_tag}"
                    )
                    print(f"    {Colors.DIM}💡{Colors.RESET} {v.suggestion}")

                    if show_context and v.line_content:
                        print(f"    {Colors.DIM}│{Colors.RESET} {v.line_content}")

            print()

        # Summary
        print(f"{'=' * 80}")
        print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
        print(f"{'-' * 80}")

        critical_count = len(self.result.by_severity(Severity.CRITICAL))
        error_count = len(self.result.by_severity(Severity.ERROR))
        warning_count = len(self.result.by_severity(Severity.WARNING))
        info_count = len(self.result.by_severity(Severity.INFO))

        if critical_count:
            print(f"  {Colors.RED}Critical: {critical_count}{Colors.RESET}")
        else:
            print(f"  Critical: {critical_count}")

        if error_count:
            print(f"  {Colors.RED}Errors:   {error_count}{Colors.RESET}")
        else:
            print(f"  Errors:   {error_count}")

        if warning_count:
            print(f"  {Colors.YELLOW}Warnings: {warning_count}{Colors.RESET}")
        else:
            print(f"  Warnings: {warning_count}")

        print(f"  Info:     {info_count}")
        print(f"  {Colors.BOLD}Total:    {len(self.result.violations)}{Colors.RESET}")

        fixable = len([v for v in self.result.violations if v.fix_available])
        if fixable:
            print(
                f"\n{Colors.GREEN}💡 {fixable} violation(s) can be auto-fixed with --fix{Colors.RESET}"
            )

        print(f"{'=' * 80}")

        # Determine exit code
        if self.result.has_critical or self.result.has_error:
            print(
                f"\n{Colors.RED}❌ Critical/Error violations found - must fix before merging{Colors.RESET}"
            )
            return 2

        if strict and self.result.has_warning:
            print(f"\n{Colors.YELLOW}⚠️ Warnings treated as errors (--strict mode){Colors.RESET}")
            return 1

        if self.result.has_warning:
            print(f"\n{Colors.YELLOW}⚠️ Warnings found - review before merging{Colors.RESET}")

        return 0


def explain_rule(rule_id: str) -> None:
    """Print detailed explanation of a rule."""
    rule_id = rule_id.upper()
    if rule_id not in RULE_DOCS:
        print(f"{Colors.RED}Unknown rule: {rule_id}{Colors.RESET}")
        print(f"\nAvailable rules: {', '.join(sorted(RULE_DOCS.keys()))}")
        sys.exit(1)

    doc = RULE_DOCS[rule_id]

    print(f"\n{Colors.BOLD}{Colors.CYAN}{rule_id}: {doc['title']}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"Severity: {doc['severity']}")

    if "autofix" in doc:
        print(f"{Colors.GREEN}Auto-fixable: {doc['autofix']}{Colors.RESET}")

    print(f"\n{doc['description']}")

    if "good" in doc:
        print(f"\n{Colors.GREEN}✅ Good:{Colors.RESET}")
        print(f"{Colors.DIM}{doc['good']}{Colors.RESET}")

    if "bad" in doc:
        print(f"\n{Colors.RED}❌ Bad:{Colors.RESET}")
        print(f"{Colors.DIM}{doc['bad']}{Colors.RESET}")

    print()


def list_rules() -> None:
    """List all available rules."""
    print(f"\n{Colors.BOLD}Available SKUEL Rules:{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    for rule_id in sorted(RULE_DOCS.keys()):
        doc = RULE_DOCS[rule_id]
        severity_color = {
            "CRITICAL": Colors.RED,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW,
            "INFO": Colors.BLUE,
        }.get(doc["severity"], "")
        autofix = " [auto-fix]" if "autofix" in doc else ""
        print(f"  {Colors.CYAN}{rule_id}{Colors.RESET}: {doc['title']}")
        print(
            f"         {severity_color}{doc['severity']}{Colors.RESET}{Colors.GREEN}{autofix}{Colors.RESET}"
        )
        print()


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SKUEL Unified Linter - architecture and pattern enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Lint entire project
  %(prog)s --file core/services/    # Lint specific directory
  %(prog)s --rule SKUEL003          # Run only specific rule
  %(prog)s --explain SKUEL003       # Show rule documentation
  %(prog)s --fix                    # Auto-fix violations
  %(prog)s --context                # Show code context
  %(prog)s --quiet --check          # CI mode
        """,
    )
    parser.add_argument(
        "--check", action="store_true", help="Exit with code 1 if any violations (for CI)"
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix violations where possible")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--json", action="store_true", help="Output violations as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output (for CI)")
    parser.add_argument(
        "--context", "-c", action="store_true", help="Show code context around violations"
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Lint specific file or directory (relative to project root)"
    )
    parser.add_argument(
        "--rule",
        "-r",
        type=str,
        action="append",
        help="Run only specific rule(s). Can be used multiple times.",
    )
    parser.add_argument(
        "--explain", "-e", type=str, help="Explain a specific rule (e.g., --explain SKUEL003)"
    )
    parser.add_argument("--list-rules", action="store_true", help="List all available rules")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    args = parser.parse_args()

    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Handle --explain
    if args.explain:
        explain_rule(args.explain)
        sys.exit(0)

    # Handle --list-rules
    if args.list_rules:
        list_rules()
        sys.exit(0)

    # Find project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # Run linter
    linter = SkuelLinter(
        project_root,
        target_path=args.file,
        rules_filter=[r.upper() for r in args.rule] if args.rule else None,
    )
    linter.lint()

    # Apply fixes if requested
    if args.fix:
        if not args.quiet:
            print()
            print(f"{'=' * 80}")
            print("APPLYING AUTO-FIXES")
            print(f"{'=' * 80}")
            print()
        linter.apply_fixes()

        if not args.quiet:
            print()

        # Re-run to show remaining violations
        linter = SkuelLinter(
            project_root,
            target_path=args.file,
            rules_filter=[r.upper() for r in args.rule] if args.rule else None,
        )
        linter.lint()

    # Output
    if args.json:
        import json

        output = {
            "files_scanned": linter.result.files_scanned,
            "scan_time_ms": linter.result.scan_time_ms,
            "violations": [
                {
                    "file": str(v.file_path),
                    "line": v.line_number,
                    "column": v.column,
                    "severity": v.severity.value,
                    "rule_id": v.rule_id,
                    "message": v.message,
                    "suggestion": v.suggestion,
                    "fix_available": v.fix_available,
                    "line_content": v.line_content,
                }
                for v in linter.result.violations
            ],
            "summary": {
                "critical": len(linter.result.by_severity(Severity.CRITICAL)),
                "error": len(linter.result.by_severity(Severity.ERROR)),
                "warning": len(linter.result.by_severity(Severity.WARNING)),
                "info": len(linter.result.by_severity(Severity.INFO)),
            },
        }
        print(json.dumps(output, indent=2))
        exit_code = 1 if linter.result.violations else 0
    else:
        exit_code = linter.print_report(
            strict=args.strict, quiet=args.quiet, show_context=args.context
        )

    # Exit
    if args.check:
        sys.exit(1 if linter.result.violations else 0)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
