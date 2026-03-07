#!/usr/bin/env python3
"""
Skills Metadata Validator

Validates the skills metadata registry and skill directory structure:
1. All skills in metadata exist as directories
2. Required files present (SKILL.md, QUICK_REFERENCE.md, PATTERNS.md)
3. No circular dependencies in dependency graph
4. All primary_docs exist
5. Documentation has backlinks (related_skills field)

Usage:
    poetry run python scripts/skills_validator.py           # Full validation
    poetry run python scripts/skills_validator.py --json    # JSON output
    poetry run python scripts/skills_validator.py --fix     # Auto-fix backlinks (future)
"""

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.utils.frontmatter import parse_frontmatter as _parse_frontmatter


@dataclass
class ValidationError:
    """A validation error found during checks."""

    check: str
    severity: str  # error | warning
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report."""

    total_skills: int
    passed_checks: int
    failed_checks: int
    warnings: int
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len([e for e in self.errors if e.severity == "error"]) > 0

    @property
    def has_warnings(self) -> bool:
        return len([e for e in self.errors if e.severity == "warning"]) > 0


def load_skills_metadata(metadata_path: Path) -> dict:
    """Load and parse the skills metadata YAML file."""
    if not metadata_path.exists():
        print(f"Error: Skills metadata not found at {metadata_path}", file=sys.stderr)
        sys.exit(1)

    try:
        content = metadata_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return data
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse skills metadata: {e}", file=sys.stderr)
        sys.exit(1)


def validate_skill_directories(skills: list[dict], skills_dir: Path) -> list[ValidationError]:
    """Check that all skills in metadata exist as directories."""
    errors = []

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            errors.append(
                ValidationError(
                    check="skill_directories",
                    severity="error",
                    message="Skill missing 'name' field in metadata",
                    context={"skill": skill},
                )
            )
            continue

        skill_dir = skills_dir / skill_name
        if not skill_dir.exists():
            errors.append(
                ValidationError(
                    check="skill_directories",
                    severity="error",
                    message=f"Skill directory not found: {skill_name}",
                    context={"skill": skill_name, "expected_path": str(skill_dir)},
                )
            )
        elif not skill_dir.is_dir():
            errors.append(
                ValidationError(
                    check="skill_directories",
                    severity="error",
                    message=f"Skill path is not a directory: {skill_name}",
                    context={"skill": skill_name, "path": str(skill_dir)},
                )
            )

    return errors


def validate_required_files(skills: list[dict], skills_dir: Path) -> list[ValidationError]:
    """Check that required files exist for each skill."""
    required_files = ["SKILL.md", "QUICK_REFERENCE.md", "PATTERNS.md"]
    errors = []

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            continue

        skill_dir = skills_dir / skill_name
        if not skill_dir.exists():
            # Already reported in validate_skill_directories
            continue

        for required_file in required_files:
            file_path = skill_dir / required_file
            if not file_path.exists():
                errors.append(
                    ValidationError(
                        check="required_files",
                        severity="error",
                        message=f"Missing required file: {skill_name}/{required_file}",
                        context={
                            "skill": skill_name,
                            "missing_file": required_file,
                            "expected_path": str(file_path),
                        },
                    )
                )

    return errors


def build_dependency_graph(skills: list[dict]) -> dict[str, list[str]]:
    """Build dependency graph from skills metadata."""
    graph: dict[str, list[str]] = {}

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            continue

        dependencies = skill.get("dependencies", [])
        graph[skill_name] = dependencies

    return graph


def detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """
    Detect cycles in dependency graph using DFS.

    Returns list of cycles (each cycle is a list of skill names).
    """
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path.copy())
            elif neighbor in rec_stack:
                # Cycle detected
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


def validate_no_cycles(skills: list[dict]) -> list[ValidationError]:
    """Check that dependency graph has no circular dependencies."""
    errors = []
    graph = build_dependency_graph(skills)
    cycles = detect_cycles(graph)

    for cycle in cycles:
        cycle_str = " → ".join(cycle)
        errors.append(
            ValidationError(
                check="no_cycles",
                severity="error",
                message=f"Circular dependency detected: {cycle_str}",
                context={"cycle": cycle},
            )
        )

    return errors


def validate_primary_docs(skills: list[dict], project_root: Path) -> list[ValidationError]:
    """Check that all primary_docs referenced in metadata exist."""
    errors = []

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            continue

        primary_docs = skill.get("primary_docs", [])
        for doc_path_str in primary_docs:
            # Convert to absolute path
            if doc_path_str.startswith("/"):
                doc_path = project_root / doc_path_str.lstrip("/")
            else:
                doc_path = project_root / doc_path_str

            if not doc_path.exists():
                errors.append(
                    ValidationError(
                        check="primary_docs",
                        severity="error",
                        message=f"Primary doc not found for skill '{skill_name}': {doc_path_str}",
                        context={
                            "skill": skill_name,
                            "doc": doc_path_str,
                            "resolved_path": str(doc_path),
                        },
                    )
                )

    return errors


def parse_frontmatter(doc_path: Path) -> dict:
    """
    Parse YAML frontmatter from a markdown file.

    Returns empty dict if no frontmatter found.
    """
    content = doc_path.read_text(encoding="utf-8")
    return _parse_frontmatter(content)[0]


def validate_backlinks(skills: list[dict], project_root: Path) -> list[ValidationError]:
    """
    Check that docs referenced in primary_docs have backlinks to skills.

    Docs should have 'related_skills' field in frontmatter.
    """
    errors = []

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            continue

        primary_docs = skill.get("primary_docs", [])
        for doc_path_str in primary_docs:
            # Convert to absolute path
            if doc_path_str.startswith("/"):
                doc_path = project_root / doc_path_str.lstrip("/")
            else:
                doc_path = project_root / doc_path_str

            if not doc_path.exists():
                # Already reported in validate_primary_docs
                continue

            # Parse frontmatter
            frontmatter = parse_frontmatter(doc_path)
            related_skills = frontmatter.get("related_skills", [])

            if not related_skills:
                errors.append(
                    ValidationError(
                        check="backlinks",
                        severity="warning",
                        message=f"Doc missing 'related_skills' field: {doc_path_str}",
                        context={
                            "skill": skill_name,
                            "doc": doc_path_str,
                            "suggestion": f"Add 'related_skills: [{skill_name}]' to frontmatter",
                        },
                    )
                )
            elif skill_name not in related_skills:
                errors.append(
                    ValidationError(
                        check="backlinks",
                        severity="warning",
                        message=f"Doc missing backlink to skill '{skill_name}': {doc_path_str}",
                        context={
                            "skill": skill_name,
                            "doc": doc_path_str,
                            "current_skills": related_skills,
                            "suggestion": f"Add '{skill_name}' to related_skills list",
                        },
                    )
                )

    return errors


def run_validation(project_root: Path) -> ValidationReport:
    """Run all validation checks and generate report."""
    skills_dir = project_root / ".claude" / "skills"
    metadata_path = skills_dir / "skills_metadata.yaml"

    # Load metadata
    metadata = load_skills_metadata(metadata_path)
    skills = metadata.get("skills", [])

    if not skills:
        print("Error: No skills found in metadata", file=sys.stderr)
        sys.exit(1)

    # Run all validation checks
    all_errors: list[ValidationError] = []

    print("Running validation checks...")
    print()

    # Check 1: Skill directories exist
    print("1. Checking skill directories...")
    errors = validate_skill_directories(skills, skills_dir)
    all_errors.extend(errors)
    if errors:
        print(f"   ❌ Found {len(errors)} error(s)")
    else:
        print("   ✅ All skill directories exist")

    # Check 2: Required files present
    print("2. Checking required files...")
    errors = validate_required_files(skills, skills_dir)
    all_errors.extend(errors)
    if errors:
        print(f"   ❌ Found {len(errors)} error(s)")
    else:
        print("   ✅ All required files present")

    # Check 3: No circular dependencies
    print("3. Checking for circular dependencies...")
    errors = validate_no_cycles(skills)
    all_errors.extend(errors)
    if errors:
        print(f"   ❌ Found {len(errors)} cycle(s)")
    else:
        print("   ✅ No circular dependencies")

    # Check 4: Primary docs exist
    print("4. Checking primary documentation...")
    errors = validate_primary_docs(skills, project_root)
    all_errors.extend(errors)
    if errors:
        print(f"   ❌ Found {len(errors)} error(s)")
    else:
        print("   ✅ All primary docs exist")

    # Check 5: Documentation backlinks
    print("5. Checking documentation backlinks...")
    errors = validate_backlinks(skills, project_root)
    all_errors.extend(errors)
    if errors:
        print(f"   ⚠️  Found {len(errors)} warning(s)")
    else:
        print("   ✅ All backlinks present")

    print()

    # Generate report
    error_count = len([e for e in all_errors if e.severity == "error"])
    warning_count = len([e for e in all_errors if e.severity == "warning"])
    passed_count = 5 - (1 if error_count > 0 else 0) - (1 if warning_count > 0 else 0)

    return ValidationReport(
        total_skills=len(skills),
        passed_checks=passed_count,
        failed_checks=len(all_errors),
        warnings=warning_count,
        errors=all_errors,
    )


def print_detailed_errors(report: ValidationReport) -> None:
    """Print detailed error messages."""
    if not report.errors:
        return

    print("Detailed Validation Results:")
    print("=" * 60)
    print()

    # Group by check type
    by_check: dict[str, list[ValidationError]] = {}
    for error in report.errors:
        if error.check not in by_check:
            by_check[error.check] = []
        by_check[error.check].append(error)

    for check, errors in by_check.items():
        print(f"{check.upper().replace('_', ' ')}:")
        for error in errors:
            severity_marker = "❌" if error.severity == "error" else "⚠️"
            print(f"  {severity_marker} {error.message}")

            # Print context if helpful
            if error.check == "backlinks" and "suggestion" in error.context:
                print(f"      💡 {error.context['suggestion']}")

        print()


def print_summary(report: ValidationReport) -> None:
    """Print validation summary."""
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total skills: {report.total_skills}")
    print(f"Checks passed: {report.passed_checks}/5")
    print(f"Errors: {len([e for e in report.errors if e.severity == 'error'])}")
    print(f"Warnings: {report.warnings}")
    print()

    if not report.has_errors and not report.has_warnings:
        print("✅ All validation checks passed!")
    elif not report.has_errors:
        print("⚠️  Validation passed with warnings")
    else:
        print("❌ Validation failed - please fix errors above")

    print("=" * 60)


def main() -> None:
    args = sys.argv[1:]

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Run validation
    report = run_validation(project_root)

    # Output based on flags
    if "--json" in args:
        import json

        output = asdict(report)
        print(json.dumps(output, indent=2, default=str))
    else:
        if report.errors:
            print_detailed_errors(report)
        print_summary(report)

    # Exit with error code if validation failed
    if report.has_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
