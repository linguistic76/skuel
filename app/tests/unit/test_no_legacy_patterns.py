"""
No Legacy Patterns Test Suite
==============================

Automated guardrail that fails CI if legacy code patterns re-appear.

SKUEL follows "One Path Forward" — no backward compatibility, no legacy wrappers.
This test suite catches legacy drift before it accumulates.

Run: poetry run pytest tests/unit/test_no_legacy_patterns.py -v

See: /docs/patterns/linter_rules.md
"""

import ast
import pathlib

import pytest

# ============================================================================
# PATHS
# ============================================================================

APP_ROOT = pathlib.Path(__file__).parent.parent.parent
CORE_DIR = APP_ROOT / "core"
ADAPTERS_DIR = APP_ROOT / "adapters"
ENUMS_DIR = CORE_DIR / "models" / "enums"

# Directories to scan for linter violations
PRODUCTION_DIRS = [CORE_DIR, ADAPTERS_DIR]

# Directories/files to exclude from scanning (tests, scripts, docstrings)
EXCLUDED_PATHS = {"tests", "scripts", "__pycache__", ".pyc"}


# ============================================================================
# HELPERS
# ============================================================================


def _iter_python_files(*dirs: pathlib.Path) -> list[pathlib.Path]:
    """Yield all .py files under given directories, excluding test/script files."""
    files = []
    for directory in dirs:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            parts = py_file.parts
            if any(excluded in parts for excluded in EXCLUDED_PATHS):
                continue
            files.append(py_file)
    return files


def _find_ast_nodes(filepath: pathlib.Path, node_type: type) -> list[tuple[int, ast.AST]]:
    """Parse a file and return all AST nodes of a given type with line numbers."""
    try:
        source = filepath.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    return [
        (getattr(node, "lineno", 0), node) for node in ast.walk(tree) if isinstance(node, node_type)
    ]


def _find_hasattr_calls(filepath: pathlib.Path) -> list[int]:
    """Find hasattr() calls in production code (not in docstrings/comments)."""
    violations = []
    for lineno, node in _find_ast_nodes(filepath, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "hasattr":
            violations.append(lineno)
    return violations


def _find_lambda_expressions(filepath: pathlib.Path) -> list[int]:
    """Find lambda expressions in production code."""
    violations = []
    for lineno, _node in _find_ast_nodes(filepath, ast.Lambda):
        violations.append(lineno)
    return violations


# ============================================================================
# TESTS: DEAD CODE GUARDRAILS
# ============================================================================


class TestNoDeadFiles:
    """Ensure deleted dead code stays deleted."""

    def test_no_repository_pattern_files(self) -> None:
        """core/patterns/ was superseded by UniversalNeo4jBackend[T] — must not exist."""
        patterns_dir = CORE_DIR / "patterns"
        assert not patterns_dir.exists(), (
            f"Dead directory still exists: {patterns_dir}\n"
            "The repository pattern was superseded by UniversalNeo4jBackend[T]. Delete it."
        )

    def test_no_personalized_discovery_adapter(self) -> None:
        """PersonalizedKnowledgeDiscoveryAdapter was dead code — must not exist."""
        adapter = ADAPTERS_DIR / "personalized_knowledge_discovery_adapter.py"
        assert not adapter.exists(), (
            f"Dead file still exists: {adapter}\n"
            "PersonalizedKnowledgeDiscoveryAdapter had zero route references. Delete it."
        )

    def test_no_dead_relationship_files(self) -> None:
        """Dead relationship infrastructure files must not exist."""
        rel_dir = CORE_DIR / "infrastructure" / "relationships"
        dead_files = [
            "relationships.py",
            "relationship_base.py",
            "relationship_graph_native.py",
            "relationship_validation.py",
        ]
        for filename in dead_files:
            filepath = rel_dir / filename
            assert not filepath.exists(), (
                f"Dead file still exists: {filepath}\n"
                "This relationship infrastructure file had zero production imports. Delete it."
            )


# ============================================================================
# TESTS: DEAD ENUM VALUES
# ============================================================================


class TestNoLegacyEnumValues:
    """Ensure removed legacy enum values stay removed."""

    def test_no_legacy_neo_labels(self) -> None:
        """NeoLabel.JOURNAL_PROJECT was migrated to Report — must not exist.

        Note: NeoLabel.JOURNAL is legitimate — it's the domain-specific label
        for :Ku nodes with ku_type='journal' (content processing domain).
        """
        from core.models.enums.neo_labels import NeoLabel

        members = [m.name for m in NeoLabel]
        # JOURNAL is legitimate (EntityType.JOURNAL maps to NeoLabel.JOURNAL)
        assert "JOURNAL_PROJECT" not in members, (
            "NeoLabel.JOURNAL_PROJECT is legacy — use REPORT_PROJECT"
        )

    def test_no_legacy_relationship_name_learning(self) -> None:
        """RelationshipName.LEARNING was replaced by IN_PROGRESS — must not exist."""
        from core.models.relationship_names import RelationshipName

        members = [m.name for m in RelationshipName]
        assert "LEARNING" not in members, "RelationshipName.LEARNING is legacy — use IN_PROGRESS"

    def test_no_legacy_relationship_type_aliases(self) -> None:
        """Legacy RelationshipType aliases must not exist — use canonical names."""
        from core.models.enums.metadata_enums import RelationshipType

        members = [m.name for m in RelationshipType]
        legacy_aliases = {
            "PARENT_CHILD": "PARENT_OF",
            "RELATED": "RELATED_TO",
            "CONFLICTS": "CONFLICTS_WITH",
            "PREREQUISITE": "PREREQUISITE_FOR",
        }
        for alias, canonical in legacy_aliases.items():
            assert alias not in members, (
                f"RelationshipType.{alias} is a legacy alias — use {canonical}"
            )


# ============================================================================
# TESTS: LINTER RULE ENFORCEMENT (AST-based)
# ============================================================================


class TestNoLinterViolations:
    """AST-based enforcement of SKUEL linter rules in production code.

    Uses ratchet pattern: known baseline counts prevent NEW violations from being
    introduced. As violations are fixed, lower the baseline to lock in progress.
    """

    # Ratchet baselines — lower these as violations are fixed
    # Last updated: 2026-02-23
    HASATTR_BASELINE = 0  # All hasattr() violations eliminated
    LAMBDA_BASELINE = 4  # Known lambda expressions across codebase

    def test_no_hasattr_in_core_services(self) -> None:
        """SKUEL011: Zero hasattr() in core/services/ — the strict zone."""
        violations = [
            f"  {py_file.relative_to(APP_ROOT)}:{lineno}"
            for py_file in _iter_python_files(CORE_DIR / "services")
            for lineno in _find_hasattr_calls(py_file)
        ]

        assert not violations, (
            f"SKUEL011: Found {len(violations)} hasattr() call(s) in core/services/.\n"
            "Use getattr(obj, attr, sentinel) instead.\n" + "\n".join(violations)
        )

    def test_hasattr_ratchet(self) -> None:
        """SKUEL011: hasattr() count must not increase. Lower baseline as you fix them."""
        violations = [
            f"  {py_file.relative_to(APP_ROOT)}:{lineno}"
            for py_file in _iter_python_files(*PRODUCTION_DIRS)
            for lineno in _find_hasattr_calls(py_file)
        ]

        count = len(violations)
        assert count <= self.HASATTR_BASELINE, (
            f"SKUEL011: hasattr() count increased! {count} > baseline {self.HASATTR_BASELINE}.\n"
            "Fix the new violations or (if justified) increase HASATTR_BASELINE.\n"
            + "\n".join(violations)
        )
        if count < self.HASATTR_BASELINE:
            pytest.skip(
                f"Ratchet opportunity: {count} < {self.HASATTR_BASELINE}. "
                f"Lower HASATTR_BASELINE to {count} to lock in progress."
            )

    def test_lambda_ratchet(self) -> None:
        """SKUEL012: lambda count must not increase. Lower baseline as you fix them."""
        violations = [
            f"  {py_file.relative_to(APP_ROOT)}:{lineno}"
            for py_file in _iter_python_files(*PRODUCTION_DIRS)
            for lineno in _find_lambda_expressions(py_file)
        ]

        count = len(violations)
        assert count <= self.LAMBDA_BASELINE, (
            f"SKUEL012: lambda count increased! {count} > baseline {self.LAMBDA_BASELINE}.\n"
            "Fix the new violations or (if justified) increase LAMBDA_BASELINE.\n"
            + "\n".join(violations)
        )
        if count < self.LAMBDA_BASELINE:
            pytest.skip(
                f"Ratchet opportunity: {count} < {self.LAMBDA_BASELINE}. "
                f"Lower LAMBDA_BASELINE to {count} to lock in progress."
            )


# ============================================================================
# TESTS: NO STALE LEGACY MARKERS IN ENUMS
# ============================================================================


class TestNoLegacyMarkers:
    """Ensure enum files don't accumulate 'Legacy' comments."""

    def test_no_legacy_comments_in_enums(self) -> None:
        """Enum files should not contain 'Legacy' comments — aliases should be deleted, not marked.

        Exceptions:
        - neo_labels.py: Legacy comments describe labels retained for backward compat
          during the multi-label migration (Phase 0). These are intentional markers
          for the migration plan, not stale aliases.
        """
        # Files allowed to have "Legacy" comments (migration infrastructure)
        allowed_files = {"neo_labels.py"}

        violations = []
        for py_file in ENUMS_DIR.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            if py_file.name in allowed_files:
                continue
            for i, line in enumerate(py_file.read_text().splitlines(), start=1):
                stripped = line.strip()
                # Only flag inline comments (not docstrings or regular code)
                if "#" in stripped and "legacy" in stripped.lower().split("#", 1)[1].lower():
                    violations.append(f"  {py_file.relative_to(APP_ROOT)}:{i}: {stripped}")

        assert not violations, (
            f"Found {len(violations)} 'Legacy' comment(s) in enum files.\n"
            "One Path Forward: delete legacy aliases, don't mark them.\n" + "\n".join(violations)
        )
