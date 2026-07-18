#!/usr/bin/env python3
"""
Legacy Code Detector
====================

Scans codebase for common legacy patterns and missing attributes.
Uses MyPy output to identify attr-defined errors and categorize them.

Usage:
    uv run python scripts/detect_legacy_code.py

Output:
    - Summary of legacy patterns found
    - Files needing attention (delete obsolete code or update to current path)
    - Suggested removal timeline
"""

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_METHODS = {
    "get_domain_context_raw",
    "aflat_map",
    "from_domain_model",
    "discovery_ops",
    "graph_intel",
}
IMPORT_ATTRS = {"Errors", "EventType", "EntityStatus"}
MODEL_ATTRS = {
    "habit_weights",
    "completion_rate",
    "required_habit_consistency",
    "knowledge_patterns_detected",
    "password_hash",
}
TYPE_NARROWING_ATTRS = {"__iter__", "__getitem__", "__len__"}
WRONG_METHODS = {"update", "sort", "get", "create", "backend"}
SEVERITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}


@dataclass(frozen=True)
class LegacyPattern:
    """Represents a detected legacy code pattern."""

    file_path: str
    line_number: int
    pattern_type: str
    attribute: str
    severity: str


class LegacyCodeDetector:
    """Detect and categorize legacy code patterns."""

    def __init__(self, root_path: Path = ROOT) -> None:
        self.root_path = root_path
        self.patterns: list[LegacyPattern] = []

    def run_mypy(self) -> str:
        """Run MyPy and return output."""
        result = subprocess.run(
            ["uv", "run", "mypy", "core/", "adapters/", "--show-error-codes"],
            cwd=self.root_path,
            capture_output=True,
            text=True,
        )
        return result.stdout + result.stderr

    def parse_mypy_output(self, mypy_output: str) -> None:
        """Parse MyPy output and extract attr-defined errors."""
        lines = mypy_output.split("\n")

        for i, line in enumerate(lines):
            # Look for attr-defined errors (multi-line format: [attr-defined] is on message line)
            if "[attr-defined]" not in line:
                continue

            file_path = None
            line_number = None
            message = None

            # Try single-line format first
            match = re.match(r"^([^:]+):(\d+):\d+: error: (.+) \[attr-defined\]", line)
            if match:
                file_path = match.group(1)
                line_number = int(match.group(2))
                message = match.group(3)
            # Try multi-line format (error: on previous line)
            elif i > 0:
                prev_line = lines[i - 1]
                match = re.match(r"^([^:]+):(\d+):\d+: error:", prev_line)
                if match:
                    file_path = match.group(1)
                    line_number = int(match.group(2))
                    message = line.strip()

            # Skip if we couldn't parse
            if not file_path or not message:
                continue

            # Extract attribute name
            attr_match = re.search(r'has no attribute "([^"]*)"', message)
            attribute = attr_match.group(1) if attr_match else "unknown"

            # Categorize by pattern
            pattern_type, severity = self._categorize_pattern(attribute, file_path)

            pattern = LegacyPattern(
                file_path=file_path,
                line_number=line_number,
                pattern_type=pattern_type,
                attribute=attribute,
                severity=severity,
            )
            self.patterns.append(pattern)

    def _categorize_pattern(self, attribute: str, file_path: str) -> tuple[str, str]:
        """Categorize pattern and determine severity."""
        if attribute in PROTOCOL_METHODS:
            return ("missing_protocol", "high")
        if attribute in IMPORT_ATTRS:
            return ("import_error", "low")
        if attribute in MODEL_ATTRS:
            return ("missing_attribute", "medium")
        if attribute in TYPE_NARROWING_ATTRS:
            return ("type_narrowing", "low")
        if attribute in WRONG_METHODS:
            return ("coding_error", "high")
        return ("unknown", "medium")

    def group_by_pattern(self) -> dict[str, list[LegacyPattern]]:
        """Group patterns by type."""
        grouped = defaultdict(list)
        for pattern in self.patterns:
            grouped[pattern.pattern_type].append(pattern)
        return grouped

    def group_by_attribute(self) -> dict[str, list[LegacyPattern]]:
        """Group patterns by attribute name."""
        grouped = defaultdict(list)
        for pattern in self.patterns:
            grouped[pattern.attribute].append(pattern)
        return grouped

    def print_report(self) -> None:
        """Print comprehensive legacy code report."""
        print("=" * 100)
        print("LEGACY CODE DETECTION REPORT")
        print("=" * 100)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total patterns detected: {len(self.patterns)}")
        print()

        # Group by pattern type
        by_pattern = self.group_by_pattern()

        # Summary by severity
        high = sum(1 for p in self.patterns if p.severity == "high")
        medium = sum(1 for p in self.patterns if p.severity == "medium")
        low = sum(1 for p in self.patterns if p.severity == "low")

        print("SEVERITY BREAKDOWN:")
        print(f"  🔴 High Priority:   {high}")
        print(f"  🟡 Medium Priority: {medium}")
        print(f"  🟢 Low Priority:    {low}")
        print()

        # Category breakdown
        print("CATEGORY BREAKDOWN:")
        for pattern_type, patterns in sorted(by_pattern.items()):
            print(f"  {pattern_type}: {len(patterns)}")
        print()

        # Top missing attributes
        by_attribute = self.group_by_attribute()
        print("TOP MISSING ATTRIBUTES:")
        print("-" * 100)

        def get_pattern_count(item: tuple[str, list]) -> int:
            return len(item[1])

        sorted_attrs = sorted(by_attribute.items(), key=get_pattern_count, reverse=True)
        for attribute, patterns in sorted_attrs[:15]:
            severity = patterns[0].severity
            severity_icon = SEVERITY_ICONS[severity]
            print(f"  {severity_icon} {attribute}: {len(patterns)} occurrences")
        print()

        # Detailed breakdown by category
        print("=" * 100)
        print("DETAILED BREAKDOWN")
        print("=" * 100)
        print()

        # High priority - Missing protocol methods
        if "missing_protocol" in by_pattern:
            print("🔴 HIGH PRIORITY: Missing Protocol Methods")
            print("-" * 100)
            protocol_by_attr = defaultdict(list)
            for pattern in by_pattern["missing_protocol"]:
                protocol_by_attr[pattern.attribute].append(pattern)

            for attribute, patterns in sorted(protocol_by_attr.items()):
                print(f"\n  Method: {attribute} ({len(patterns)} occurrences)")
                files = set(p.file_path for p in patterns)
                for file_path in sorted(files):
                    lines = [p.line_number for p in patterns if p.file_path == file_path]
                    print(f"    - {file_path}:{lines[0]}")

                print("\n  ACTION REQUIRED:")
                print(f"    - Add '{attribute}' to relevant protocol OR")
                print("    - Refactor code to use existing protocol methods")
                print(
                    f"    - Target: {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')} (7 days)"
                )
            print()

        # Medium priority - Missing model attributes
        if "missing_attribute" in by_pattern:
            print("🟡 MEDIUM PRIORITY: Missing Model Attributes")
            print("-" * 100)
            attr_by_name = defaultdict(list)
            for pattern in by_pattern["missing_attribute"]:
                attr_by_name[pattern.attribute].append(pattern)

            for attribute, patterns in sorted(attr_by_name.items()):
                print(f"\n  Attribute: {attribute} ({len(patterns)} occurrences)")
                files = set(p.file_path for p in patterns)
                for file_path in sorted(files):
                    lines = [p.line_number for p in patterns if p.file_path == file_path]
                    print(f"    - {file_path}:{','.join(map(str, lines))}")

                print("\n  DECISION NEEDED:")
                print("    [ ] Add to model (if still needed)")
                print("    [ ] Remove from code (if obsolete)")
                print("    [ ] Move to metadata field")
                print(
                    f"    - Target: {(datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')} (14 days)"
                )
            print()

        # High priority - Coding errors
        if "coding_error" in by_pattern:
            print("🔴 HIGH PRIORITY: Coding Errors (Actual Bugs)")
            print("-" * 100)
            error_by_attr = defaultdict(list)
            for pattern in by_pattern["coding_error"]:
                error_by_attr[pattern.attribute].append(pattern)

            for attribute, patterns in sorted(error_by_attr.items()):
                print(f"\n  Error: {attribute} ({len(patterns)} occurrences)")
                files = set(p.file_path for p in patterns)
                for file_path in sorted(files):
                    lines = [p.line_number for p in patterns if p.file_path == file_path]
                    print(f"    - {file_path}:{','.join(map(str, lines))}")

                print("\n  ACTION REQUIRED:")
                print("    - Review code and fix incorrect method calls")
                print(
                    f"    - Target: {(datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')} (3 days)"
                )
            print()

        # Low priority - Import/module issues
        if "import_error" in by_pattern:
            print("🟢 LOW PRIORITY: Import/Module Issues")
            print("-" * 100)
            for pattern in by_pattern["import_error"]:
                print(f"  - {pattern.file_path}:{pattern.line_number}")
                print(f"    Missing: {pattern.attribute}")
                print("    Fix: Update import statement (5 min)")
            print(f"  Target: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')} (1 day)")
            print()

        # Low priority - Type narrowing issues
        if "type_narrowing" in by_pattern:
            print("🟢 LOW PRIORITY: Type Narrowing Issues (MyPy Limitations)")
            print("-" * 100)
            print(f"  Total occurrences: {len(by_pattern['type_narrowing'])}")
            print("  These are MyPy type inference limitations, not code bugs")
            print("  Can be suppressed with: # type: ignore[attr-defined]")
            print("  Target: Review case-by-case (optional)")
            print()

        # Removal timeline
        print("=" * 100)
        print("SUGGESTED REMOVAL TIMELINE")
        print("=" * 100)
        print()
        print(f"Week 1 ({datetime.now().strftime('%b %d')}):")
        print("  - Fix import issues (Category: import_error)")
        print("  - Remove obsolete missing-attribute references")
        print()
        print(f"Week 2 ({(datetime.now() + timedelta(days=7)).strftime('%b %d')}):")
        print("  - Fix or remove missing protocol methods")
        print("  - Decide fate of deprecated model attributes")
        print()
        print(f"Week 3 ({(datetime.now() + timedelta(days=14)).strftime('%b %d')}):")
        print("  - Remove deprecated attributes from codebase")
        print("  - Update tests")
        print()
        print(f"Week 4 ({(datetime.now() + timedelta(days=21)).strftime('%b %d')}):")
        print("  - Final cleanup")
        print("  - Target: < 50 attr-defined errors")
        print()

        # Next steps
        print("=" * 100)
        print("NEXT STEPS")
        print("=" * 100)
        print()
        print("1. Review this report and prioritize issues")
        print("2. Delete obsolete code or update it to the current path forward")
        print("3. Update docs/LEGACY_CODE_CLEANUP.md with decisions")
        print("4. Run this script weekly to track progress")
        print()


def main() -> None:
    """Run legacy code detection."""
    detector = LegacyCodeDetector()

    print("Running MyPy to detect legacy patterns...")
    mypy_output = detector.run_mypy()

    print("Parsing MyPy output...")
    detector.parse_mypy_output(mypy_output)

    print()
    detector.print_report()


if __name__ == "__main__":
    main()
