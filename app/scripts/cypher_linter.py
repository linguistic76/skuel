#!/usr/bin/env python3
"""
Cypher Query Linter - Static Analysis for Neo4j Queries
========================================================

Validates Cypher queries against SKUEL best practices, catching common errors
before they reach runtime.

**Validation Rules:**
- CYP001: Nested aggregate functions (ERROR)
- CYP002: DELETE without DETACH (ERROR)
- CYP003: String interpolation instead of parameters (WARNING)
- CYP004: Unbounded relationship traversal (WARNING)
- CYP005: Missing depth limit on multi-hop traversal (WARNING)
- CYP006: Large result set without LIMIT (INFO)
- CYP007: Duplicate variable names (ERROR) - DISABLED
- CYP008: WITH clause without DISTINCT (WARNING) - DISABLED
- CYP009: Query complexity too high (WARNING)
- CYP010: Missing index hint for large dataset (INFO)

**Usage:**
    poetry run python scripts/cypher_linter.py                    # Lint all files (warnings-only mode)
    poetry run python scripts/cypher_linter.py path/to/file.py   # Lint specific file
    poetry run python scripts/cypher_linter.py --errors-only     # Show only errors
    poetry run python scripts/cypher_linter.py --strict          # Fail on errors (exit code 1)

**Modes:**
    - Default (warnings-only): Reports violations but always exits 0 (success)
    - Strict mode (--strict): Exits 1 if any ERROR severity violations found

**Integration:**
    Called by `./dev quality` in warnings-only mode for visibility without blocking
"""

import argparse
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    """Violation severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Violation:
    """Represents a Cypher validation violation."""

    rule_code: str
    severity: Severity
    message: str
    file_path: Path
    line_number: int
    line_content: str
    suggestion: str

    def __str__(self) -> str:
        """Format violation for display."""
        severity_emoji = {
            Severity.ERROR: "❌",
            Severity.WARNING: "⚠️",
            Severity.INFO: "ℹ️",
        }
        emoji = severity_emoji.get(self.severity, "•")

        return f"""
{emoji} {self.severity.value} [{self.rule_code}] {self.file_path}:{self.line_number}
   {self.message}

   Line {self.line_number}: {self.line_content.strip()}

   💡 Suggestion: {self.suggestion}
"""


class CypherLinter:
    """Static analysis tool for Cypher queries."""

    def __init__(self, errors_only: bool = False):
        """
        Initialize Cypher linter.

        Args:
            errors_only: If True, only report ERROR severity violations
        """
        self.errors_only = errors_only
        self.violations: list[Violation] = []

    def lint_file(self, file_path: Path) -> list[Violation]:
        """
        Lint a Python file for Cypher query issues.

        Args:
            file_path: Path to Python file

        Returns:
            List of violations found
        """
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return []

        content = file_path.read_text()
        content.split("\n")

        violations: list[Violation] = []

        # Find all Cypher queries in the file
        queries = self._extract_cypher_queries(content, file_path)

        for query, start_line in queries:
            # Run all validation rules
            violations.extend(self._check_nested_aggregates(query, file_path, start_line))
            violations.extend(self._check_delete_without_detach(query, file_path, start_line))
            violations.extend(self._check_string_interpolation(query, file_path, start_line))
            violations.extend(self._check_unbounded_traversal(query, file_path, start_line))
            violations.extend(self._check_missing_depth_limit(query, file_path, start_line))
            violations.extend(self._check_missing_limit(query, file_path, start_line))
            violations.extend(self._check_duplicate_variables(query, file_path, start_line))

            # Advanced features (Week 5-6)
            violations.extend(self._check_query_complexity(query, file_path, start_line))
            violations.extend(self._check_missing_index_hints(query, file_path, start_line))
            violations.extend(self._check_with_without_distinct(query, file_path, start_line))

        return violations

    def _extract_cypher_queries(self, content: str, file_path: Path) -> list[tuple[str, int]]:
        """
        Extract Cypher queries from Python file.

        Looks for:
        1. Multi-line triple-quoted strings containing MATCH
        2. session.run() calls with Cypher
        3. Raw Cypher string assignments

        Returns:
            List of (query, line_number) tuples
        """
        queries: list[tuple[str, int]] = []
        seen_queries: set[str] = set()

        # Pattern 1: Multi-line triple-quoted strings with Cypher keywords
        triple_quote_pattern = r'"""([\s\S]*?)"""'
        for match in re.finditer(triple_quote_pattern, content):
            query = match.group(1)
            # Only process actual Cypher queries (must have MATCH or CREATE)
            if self._is_actual_cypher(query):
                # Avoid duplicate queries
                query_key = query.strip()
                if query_key not in seen_queries:
                    seen_queries.add(query_key)
                    line_num = content[: match.start()].count("\n") + 1
                    queries.append((query, line_num))

        # Pattern 2: session.run() calls with multi-line strings
        session_run_pattern = r'session\.run\(\s*"""([\s\S]*?)"""'
        for match in re.finditer(session_run_pattern, content):
            query = match.group(1)
            if self._is_actual_cypher(query):
                query_key = query.strip()
                if query_key not in seen_queries:
                    seen_queries.add(query_key)
                    line_num = content[: match.start()].count("\n") + 1
                    queries.append((query, line_num))

        return queries

    def _is_actual_cypher(self, text: str) -> bool:
        """
        Check if text is actual Cypher query (not just documentation).

        Actual Cypher queries have structured syntax like:
        - MATCH (n:Label) WHERE ...
        - CREATE (n:Label {prop: value})
        - MERGE (n)-[r:TYPE]->(m)

        Documentation just mentions keywords in natural language.
        """
        text_upper = text.upper()

        # 1. Must start with a Cypher command (not documentation)
        first_line = text.strip().split("\n")[0].strip()
        if not any(
            first_line.upper().startswith(cmd)
            for cmd in ["MATCH", "CREATE", "MERGE", "WITH", "UNWIND", "CALL", "RETURN"]
        ):
            return False

        # 2. Check for Cypher syntax patterns (not just keywords)
        # Actual Cypher has patterns like (n:Label), [r:TYPE], {prop: value}
        has_node_pattern = bool(re.search(r"\([a-z_][a-z0-9_]*:[A-Z]", text))  # (n:Label)
        has_rel_pattern = bool(re.search(r"-\[[a-z_][a-z0-9_]*:[A-Z]", text))  # [r:TYPE]
        has_property_map = bool(re.search(r"\{[a-z_][a-z0-9_]*:", text))  # {prop:
        has_cypher_syntax = has_node_pattern or has_rel_pattern or has_property_map

        # 3. Count Cypher keywords
        cypher_count = sum(
            1
            for kw in ["MATCH", "CREATE", "MERGE", "DELETE", "RETURN", "WHERE", "WITH"]
            if kw in text_upper
        )

        # 4. Check for natural language indicators (documentation)
        natural_language_indicators = [
            "the ",
            "a ",
            "an ",
            " is ",
            " are ",
            " for ",
            " to ",
            " this ",
            "removes",
            "creates",
            "updates",
            "deletes",
            "retrieves",
        ]
        has_natural_language = any(
            indicator in text.lower() for indicator in natural_language_indicators
        )

        # Actual Cypher: structured syntax + multiple keywords + minimal natural language
        # Documentation: natural language + maybe one keyword + no structured syntax
        if has_natural_language and not has_cypher_syntax:
            return False  # This is documentation, not Cypher

        return cypher_count >= 2 and has_cypher_syntax

    def _looks_like_cypher(self, text: str) -> bool:
        """Check if text looks like a Cypher query."""
        cypher_keywords = ["MATCH", "CREATE", "MERGE", "DELETE", "RETURN", "WITH", "WHERE"]
        text_upper = text.upper()
        return any(keyword in text_upper for keyword in cypher_keywords)

    # ========================================================================
    # VALIDATION RULES
    # ========================================================================

    def _check_nested_aggregates(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP001: Check for nested aggregate functions.

        Example violation:
            collect({uid: n.uid, count: count(r)})  # Nested aggregate!

        Correct pattern:
            WITH n, count(r) as r_count
            RETURN collect({uid: n.uid, count: r_count})
        """
        violations: list[Violation] = []

        # Aggregate functions: count, collect, sum, avg, min, max
        aggregate_pattern = r"(count|collect|sum|avg|min|max)\s*\("

        # Find all aggregate function calls
        aggregates = list(re.finditer(aggregate_pattern, query, re.IGNORECASE))

        for outer_agg in aggregates:
            # Check if there's another aggregate inside this one
            # Get the content inside the outer aggregate's parentheses
            start_pos = outer_agg.end()

            # Find matching closing parenthesis
            depth = 1
            end_pos = start_pos
            for i in range(start_pos, len(query)):
                if query[i] == "(":
                    depth += 1
                elif query[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end_pos = i
                        break

            inner_content = query[start_pos:end_pos]

            # Check if inner content has another aggregate
            if re.search(aggregate_pattern, inner_content, re.IGNORECASE):
                line_num = start_line + query[: outer_agg.start()].count("\n")
                line_content = self._get_line_at_position(query, outer_agg.start())

                violations.append(
                    Violation(
                        rule_code="CYP001",
                        severity=Severity.ERROR,
                        message="Nested aggregate functions detected",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Use WITH clause to stage aggregations: "
                        "WITH n, count(r) as r_count RETURN collect(...)",
                    )
                )

        return violations

    def _check_delete_without_detach(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP002: Check for DELETE without DETACH on nodes.

        DELETE without DETACH fails if node has relationships.
        Relationships (edges) don't need DETACH - only nodes do.

        This distinguishes between:
        - DELETE n (node) - needs DETACH check
        - DELETE r (relationship) - correct as-is
        """
        violations: list[Violation] = []

        # First, identify relationship variables from MATCH clauses
        # Pattern: -[var:TYPE]-> or -[var]->
        relationship_vars = set()
        rel_pattern = r"-\[([a-z_][a-z0-9_]*)[:\]]"
        for match in re.finditer(rel_pattern, query, re.IGNORECASE):
            relationship_vars.add(match.group(1).lower())

        # Find DELETE statements that aren't DETACH DELETE
        delete_pattern = r"\bDELETE\s+([a-z_][a-z0-9_]*)\b"

        for match in re.finditer(delete_pattern, query, re.IGNORECASE):
            deleted_var = match.group(1).lower()

            # Check if this DELETE is preceded by DETACH
            context_start = max(0, match.start() - 20)
            context = query[context_start : match.end()]

            # Skip if DETACH DELETE
            if re.search(r"\bDETACH\s+DELETE\b", context, re.IGNORECASE):
                continue

            # Skip if deleting a relationship (relationships don't need DETACH)
            if deleted_var in relationship_vars:
                continue

            # This is a node deletion without DETACH - flag it
            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            # Skip if line has noqa suppression for this rule
            if re.search(r"noqa:\s*CYP002", line_content):
                continue

            violations.append(
                Violation(
                    rule_code="CYP002",
                    severity=Severity.ERROR,
                    message=f"DELETE without DETACH on node '{deleted_var}' may fail if node has relationships",
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion="Use DETACH DELETE for nodes. Note: Relationships don't need DETACH, only nodes do.",
                )
            )

        return violations

    def _check_string_interpolation(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP003: Check for string interpolation instead of parameters.

        String interpolation can lead to Cypher injection vulnerabilities.
        Always use $param syntax.
        """
        violations: list[Violation] = []

        # Check for f-strings or .format() in the query context
        # This is tricky because we're analyzing extracted queries
        # Look for {variable_name} patterns that aren't Cypher syntax

        # Pattern: {some_var} that's not part of Cypher map syntax
        interpolation_pattern = r"\{[a-zA-Z_][a-zA-Z0-9_]*\}"

        for match in re.finditer(interpolation_pattern, query):
            # Check if this is actual Cypher map syntax
            # Cypher maps look like: {key: value, key2: value2}
            # Interpolation looks like: {variable_name}

            context_start = max(0, match.start() - 5)
            context_end = min(len(query), match.end() + 5)
            context = query[context_start:context_end]

            # If there's a colon nearby, it's probably Cypher map syntax
            if ":" not in context:
                line_num = start_line + query[: match.start()].count("\n")
                line_content = self._get_line_at_position(query, match.start())

                violations.append(
                    Violation(
                        rule_code="CYP003",
                        severity=Severity.WARNING,
                        message="Possible string interpolation detected",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Use parameterized queries: $param instead of {variable}",
                    )
                )

        return violations

    def _check_unbounded_traversal(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP004: Check for unbounded relationship traversal.

        Pattern: -[:REL*]-> (no depth limit)
        Should be: -[:REL*1..5]-> (with depth limit)
        """
        violations: list[Violation] = []

        # Pattern: Relationship with * but no depth limit
        unbounded_pattern = r"-\[:[A-Z_]+\*\]-"

        for match in re.finditer(unbounded_pattern, query):
            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            violations.append(
                Violation(
                    rule_code="CYP004",
                    severity=Severity.WARNING,
                    message="Unbounded relationship traversal detected",
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion="Add depth limit: -[:REL*1..5]-> to prevent graph explosion",
                )
            )

        return violations

    def _check_missing_depth_limit(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP005: Check for multi-hop traversal without reasonable depth limit.

        Pattern: -[:REL*1..100]-> (excessive depth)
        Recommended: -[:REL*1..5]-> (reasonable depth)
        """
        violations: list[Violation] = []

        # Pattern: Relationship with depth > 10
        deep_traversal_pattern = r"-\[:[A-Z_]+\*\d+\.\.(\d+)\]-"

        for match in re.finditer(deep_traversal_pattern, query):
            max_depth = int(match.group(1))

            if max_depth > 10:
                line_num = start_line + query[: match.start()].count("\n")
                line_content = self._get_line_at_position(query, match.start())

                violations.append(
                    Violation(
                        rule_code="CYP005",
                        severity=Severity.WARNING,
                        message=f"Excessive traversal depth: {max_depth} (recommended: ≤10)",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Consider reducing depth limit to avoid performance issues",
                    )
                )

        return violations

    def _check_missing_limit(self, query: str, file_path: Path, start_line: int) -> list[Violation]:
        """
        CYP006: Check for large result set without LIMIT.

        Queries that return nodes without LIMIT can cause performance issues.
        """
        violations: list[Violation] = []

        # Check if query has MATCH and RETURN but no LIMIT
        has_match = bool(re.search(r"\bMATCH\b", query, re.IGNORECASE))
        has_return = bool(re.search(r"\bRETURN\b", query, re.IGNORECASE))
        has_limit = bool(re.search(r"\bLIMIT\b", query, re.IGNORECASE))

        # Also check for aggregation (count, collect, etc.) which doesn't need LIMIT
        has_aggregation = bool(
            re.search(r"\b(count|collect|sum|avg|min|max)\s*\(", query, re.IGNORECASE)
        )

        if has_match and has_return and not has_limit and not has_aggregation:
            # Find RETURN statement line
            return_match = re.search(r"\bRETURN\b", query, re.IGNORECASE)
            if return_match:
                line_num = start_line + query[: return_match.start()].count("\n")
                line_content = self._get_line_at_position(query, return_match.start())

                violations.append(
                    Violation(
                        rule_code="CYP006",
                        severity=Severity.INFO,
                        message="Query returns results without LIMIT clause",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Consider adding LIMIT clause to prevent large result sets",
                    )
                )

        return violations

    def _check_duplicate_variables(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP007: Check for duplicate variable names in query.

        Using the same variable name in different MATCH clauses can cause issues
        UNLESS it's intentional reuse (common pattern in Cypher).

        We only flag as error if:
        - Same variable appears in DIFFERENT MATCH statements
        - AND those MATCH statements are at different nesting levels
        """
        violations: list[Violation] = []

        # Split query into MATCH clauses
        match_clauses = re.split(r"\b(MATCH|OPTIONAL MATCH)\b", query, flags=re.IGNORECASE)

        # Track variables per MATCH clause
        match_variables: list[set[str]] = []

        for _i, clause in enumerate(match_clauses):
            if clause.strip().upper() not in ["MATCH", "OPTIONAL MATCH", ""]:
                # Extract variables from this clause
                variable_pattern = r"\(([a-z_][a-z0-9_]*)[:\{]"
                variables = set(
                    match.group(1) for match in re.finditer(variable_pattern, clause, re.IGNORECASE)
                )

                if variables:
                    match_variables.append(variables)

        # Check for duplicates across different MATCH clauses
        # This is often intentional in Cypher (reusing variables to connect patterns)
        # So we only warn if it seems unintentional (no relationship between matches)

        # For now, disable this check as it's too noisy for valid Cypher patterns
        # Cypher ALLOWS and ENCOURAGES variable reuse across MATCH clauses

        return violations

    def _check_with_without_distinct(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP008: Check for WITH clause without DISTINCT.

        WITH clauses CAN create duplicate rows, but this is often intentional.
        This is an informational check, not an error.

        Note: Disabled for now as it's too noisy. WITH without DISTINCT is
        a common and valid pattern in Cypher.
        """
        violations: list[Violation] = []

        # Disabled - too many false positives
        # WITH without DISTINCT is often intentional in Cypher

        return violations

    def _check_query_complexity(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP009: Check for overly complex queries.

        Complexity scoring based on:
        - Number of MATCH clauses (2 points each)
        - Number of WITH clauses (3 points each)
        - Traversal depth in relationships (1 point per hop)
        - Number of WHERE conditions (1 point each)
        - Aggregations (2 points each)
        - Subqueries (5 points each)

        Complexity > 20: Warning (query should be refactored)
        Complexity > 30: Strong warning (architecture review recommended)
        """
        violations: list[Violation] = []

        query_upper = query.upper()

        # Calculate complexity score
        complexity = 0

        # MATCH clauses (2 points each)
        match_count = len(re.findall(r"\bMATCH\b", query_upper))
        complexity += match_count * 2

        # WITH clauses (3 points each) - staging adds complexity
        with_count = len(re.findall(r"\bWITH\b", query_upper))
        complexity += with_count * 3

        # Relationship traversal depth
        # Pattern: -[:REL*1..5]-> gives depth
        traversal_patterns = re.findall(r"-\[.*?\*(\d+)\.\.(\d+)\]->", query)
        for _start, end in traversal_patterns:
            max_depth = int(end)
            complexity += max_depth

        # WHERE conditions (1 point each)
        where_count = len(re.findall(r"\bWHERE\b", query_upper))
        complexity += where_count

        # Aggregations (2 points each)
        agg_pattern = r"\b(COUNT|COLLECT|SUM|AVG|MIN|MAX)\s*\("
        agg_count = len(re.findall(agg_pattern, query_upper))
        complexity += agg_count * 2

        # Subqueries (5 points each) - CALL { ... }
        subquery_count = len(re.findall(r"\bCALL\s*\{", query_upper))
        complexity += subquery_count * 5

        # Report warnings based on complexity score
        if complexity > 30:
            violations.append(
                Violation(
                    rule_code="CYP009",
                    severity=Severity.WARNING,
                    message=f"Very high query complexity (score: {complexity}) - architecture review recommended",
                    file_path=file_path,
                    line_number=start_line,
                    line_content=self._get_line_at_position(query, 0),
                    suggestion=f"Consider refactoring into multiple simpler queries or using stored procedures. "
                    f"Breakdown: {match_count} MATCH ({match_count * 2}pts), {with_count} WITH ({with_count * 3}pts), "
                    f"{where_count} WHERE ({where_count}pts), {agg_count} aggregations ({agg_count * 2}pts)",
                )
            )
        elif complexity > 20:
            violations.append(
                Violation(
                    rule_code="CYP009",
                    severity=Severity.WARNING,
                    message=f"High query complexity (score: {complexity}) - consider refactoring",
                    file_path=file_path,
                    line_number=start_line,
                    line_content=self._get_line_at_position(query, 0),
                    suggestion=f"Break into smaller queries or simplify logic. "
                    f"Breakdown: {match_count} MATCH, {with_count} WITH, {where_count} WHERE, {agg_count} aggregations",
                )
            )

        return violations

    def _check_missing_index_hints(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP010: Check for missing index hints on large dataset queries.

        NOTE: Disabled for now - most queries in SKUEL are already well-optimized,
        and Neo4j's query planner automatically uses indexes when available.

        This check would be useful if we had queries that weren't using existing indexes,
        but in practice, explicit USING INDEX is rarely needed in modern Neo4j.

        Keep this as a placeholder for future performance optimization work.
        """
        violations: list[Violation] = []

        # Disabled - Neo4j query planner handles this automatically
        # Most SKUEL queries are already well-optimized

        return violations

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_line_at_position(self, text: str, position: int) -> str:
        """Get the line of text at a specific character position."""
        # Find the line containing this position
        lines = text.split("\n")
        current_pos = 0

        for line in lines:
            if current_pos <= position < current_pos + len(line):
                return line
            current_pos += len(line) + 1  # +1 for newline

        return ""


def find_python_files_with_cypher(root_dir: Path) -> list[Path]:
    """
    Find Python files that likely contain Cypher queries.

    Looks in:
    - core/services/
    - adapters/persistence/neo4j/
    - core/models/query/
    """
    patterns = [
        "core/services/**/*.py",
        "adapters/persistence/neo4j/**/*.py",
        "core/models/query/**/*.py",
        "tests/integration/**/*.py",
    ]

    files: list[Path] = []
    for pattern in patterns:
        files.extend(root_dir.glob(pattern))

    return files


def main() -> int:
    """Main entry point for Cypher linter."""
    parser = argparse.ArgumentParser(
        description="Cypher Query Linter - Static analysis for Neo4j queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("files", nargs="*", help="Files to lint (default: auto-discover)")
    parser.add_argument(
        "--errors-only", action="store_true", help="Show only ERROR severity violations"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on errors (non-zero exit code). Default: warnings-only mode (always exit 0)",
    )

    args = parser.parse_args()

    # Find files to lint
    if args.files:
        files_to_lint = [Path(f) for f in args.files]
    else:
        root_dir = Path("/home/mike/skuel/app")
        files_to_lint = find_python_files_with_cypher(root_dir)
        print(f"🔍 Auto-discovered {len(files_to_lint)} files with potential Cypher queries\n")

    # Run linter
    linter = CypherLinter(errors_only=args.errors_only)
    all_violations: list[Violation] = []

    for file_path in files_to_lint:
        violations = linter.lint_file(file_path)
        all_violations.extend(violations)

    # Filter by severity if needed
    if args.errors_only:
        all_violations = [v for v in all_violations if v.severity == Severity.ERROR]

    # Report results
    if args.format == "text":
        print("=" * 80)
        print("Cypher Query Linter Results")
        print("=" * 80)
        print()

        if not all_violations:
            print("✅ No violations found!")
            print()
            print("All Cypher queries pass validation.")
            return 0

        # Group by severity
        errors = [v for v in all_violations if v.severity == Severity.ERROR]
        warnings = [v for v in all_violations if v.severity == Severity.WARNING]
        info = [v for v in all_violations if v.severity == Severity.INFO]

        print(f"Found {len(all_violations)} violations:")
        print(f"  - Errors: {len(errors)}")
        print(f"  - Warnings: {len(warnings)}")
        print(f"  - Info: {len(info)}")
        print()

        # Print violations
        for violation in all_violations:
            print(violation)

        print("=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Files scanned: {len(files_to_lint)}")
        print(f"Total violations: {len(all_violations)}")
        print()

        # Exit with error if there are ERROR severity violations AND --strict mode
        if args.strict:
            if errors:
                print("⚠️  STRICT MODE: Failing due to ERROR severity violations")
                return 1
            else:
                print("✅ STRICT MODE: No ERROR violations, passing")
                return 0
        else:
            # Warnings-only mode: always return 0 (success)
            if errors:
                print(
                    "ℹ️  Warnings-only mode: Violations reported but not blocking (use --strict to fail on errors)"
                )
            return 0

    else:  # JSON format
        import json

        output = {
            "files_scanned": len(files_to_lint),
            "total_violations": len(all_violations),
            "violations": [
                {
                    "rule_code": v.rule_code,
                    "severity": v.severity.value,
                    "message": v.message,
                    "file": str(v.file_path),
                    "line": v.line_number,
                    "suggestion": v.suggestion,
                }
                for v in all_violations
            ],
        }
        print(json.dumps(output, indent=2))
        # Exit with error only in strict mode
        if args.strict:
            return 1 if any(v.severity == Severity.ERROR for v in all_violations) else 0
        else:
            return 0  # Warnings-only mode


if __name__ == "__main__":
    sys.exit(main())
