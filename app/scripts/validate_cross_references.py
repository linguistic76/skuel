#!/usr/bin/env python3
"""
Cross-Reference Validation Script

Validates bidirectional consistency between skills and documentation:
1. Detects broken links (references to non-existent files/skills)
2. Finds missing reverse links (A→B exists but B→A missing)
3. Reports orphaned links
4. Suggests missing cross-references

Usage:
    poetry run python scripts/validate_cross_references.py [--fix-suggestions]
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationIssue:
    """Represents a validation issue."""

    severity: str  # "error" | "warning" | "info"
    category: str  # "broken_link" | "missing_reverse" | "orphaned" | "suggestion"
    source: str  # File or skill that has the issue
    message: str
    suggestion: str | None = None


@dataclass
class CrossRefStats:
    """Statistics about cross-references."""

    total_skills: int = 0
    total_docs: int = 0
    total_skill_refs_in_docs: int = 0
    total_doc_refs_in_skills: int = 0
    bidirectional_links: int = 0
    broken_links: int = 0
    missing_reverse_links: int = 0


# Valid skills (from directory)
VALID_SKILLS = {
    "accessibility-guide",
    "activity-domains",
    "base-ai-service",
    "base-analytics-service",
    "base-page-architecture",
    "chartjs",
    "curriculum-domains",
    "custom-sidebar-patterns",
    "daisyui",
    "fasthtml",
    "html-htmx",
    "html-navigation",
    "js-alpine",
    "neo4j-cypher-patterns",
    "neo4j-genai-plugin",
    "prometheus-grafana",
    "pydantic",
    "pytest",
    "python",
    "result-pattern",
    "skuel-component-composition",
    "skuel-form-patterns",
    "skuel-search-architecture",
    "tailwind-css",
    "ui-error-handling",
    "user-context-intelligence",
}


def load_skills_metadata(base_path: Path) -> dict[str, Any]:
    """Load skills metadata from YAML."""
    metadata_file = base_path / ".claude" / "skills" / "skills_metadata.yaml"
    with open(metadata_file) as f:
        return yaml.safe_load(f)


def find_skill_references_in_file(file_path: Path) -> set[str]:
    """Find all @skill-name references in a file."""
    content = file_path.read_text()
    # Find @skill-name patterns (but not in code blocks)
    matches = re.findall(r"@([a-z0-9-]+)", content)
    # Validate against known skills
    return {m for m in matches if m in VALID_SKILLS}


def find_actual_adr_files(base_path: Path) -> dict[str, str]:
    """
    Map ADR numbers to actual file names.

    Returns: {adr_number: filename} e.g. {"ADR-035": "ADR-035-tier-selection-guidelines.md"}
    """
    adrs_dir = base_path / "docs" / "decisions"
    adr_map = {}

    for file_path in adrs_dir.glob("ADR-*.md"):
        # Extract ADR number from filename (e.g., "ADR-035" from "ADR-035-tier-selection-guidelines.md")
        match = re.match(r"^(ADR-\d+)", file_path.name)
        if match:
            adr_number = match.group(1)
            adr_map[adr_number] = file_path.name

    return adr_map


def find_doc_references_in_skills(
    skills_data: dict[str, Any], adr_map: dict[str, str]
) -> dict[str, set[str]]:
    """
    Extract doc references from skills metadata.

    Returns: {skill_name: set of doc paths}
    """
    skill_to_docs: dict[str, set[str]] = {}

    for skill in skills_data["skills"]:
        name = skill["name"]
        docs = set()
        docs.update(skill.get("primary_docs", []))
        docs.update(skill.get("patterns", []))
        # Convert ADR references to actual file paths
        for adr in skill.get("related_adrs", []):
            adr_number = adr if adr.startswith("ADR-") else f"ADR-{adr}"
            if adr_number in adr_map:
                docs.add(f"/docs/decisions/{adr_map[adr_number]}")
            else:
                # Keep the reference even if file doesn't exist (will be caught as broken link)
                docs.add(f"/docs/decisions/{adr_number}.md")
        skill_to_docs[name] = docs

    return skill_to_docs


def collect_doc_to_skills_mapping(
    base_path: Path,
) -> tuple[dict[str, set[str]], set[Path]]:
    """
    Scan all docs and find which skills they reference.

    Returns: ({doc_path: set of skills}, set of scanned files)
    """
    doc_to_skills: dict[str, set[str]] = {}
    scanned_files: set[Path] = set()

    # Scan patterns
    patterns_dir = base_path / "docs" / "patterns"
    for file_path in patterns_dir.glob("*.md"):
        skills = find_skill_references_in_file(file_path)
        rel_path = f"/docs/patterns/{file_path.name}"
        doc_to_skills[rel_path] = skills
        scanned_files.add(file_path)

    # Scan ADRs
    adrs_dir = base_path / "docs" / "decisions"
    for file_path in adrs_dir.glob("ADR-*.md"):
        skills = find_skill_references_in_file(file_path)
        rel_path = f"/docs/decisions/{file_path.name}"
        doc_to_skills[rel_path] = skills
        scanned_files.add(file_path)

    # Scan architecture
    arch_dir = base_path / "docs" / "architecture"
    for file_path in arch_dir.glob("*.md"):
        skills = find_skill_references_in_file(file_path)
        rel_path = f"/docs/architecture/{file_path.name}"
        doc_to_skills[rel_path] = skills
        scanned_files.add(file_path)

    # Scan intelligence
    intel_dir = base_path / "docs" / "intelligence"
    if intel_dir.exists():
        for file_path in intel_dir.glob("*.md"):
            skills = find_skill_references_in_file(file_path)
            rel_path = f"/docs/intelligence/{file_path.name}"
            doc_to_skills[rel_path] = skills
            scanned_files.add(file_path)

    return doc_to_skills, scanned_files


def validate_cross_references(base_path: Path) -> tuple[list[ValidationIssue], CrossRefStats]:
    """
    Validate all cross-references.

    Returns: (list of issues, statistics)
    """
    issues: list[ValidationIssue] = []
    stats = CrossRefStats()

    # Load data
    skills_data = load_skills_metadata(base_path)
    adr_map = find_actual_adr_files(base_path)
    skill_to_docs = find_doc_references_in_skills(skills_data, adr_map)
    doc_to_skills, scanned_files = collect_doc_to_skills_mapping(base_path)

    stats.total_skills = len(skills_data["skills"])
    stats.total_docs = len(scanned_files)

    # Build bidirectional mapping
    # For each doc→skill link, check if skill→doc exists
    for doc_path, skills in doc_to_skills.items():
        for skill in skills:
            stats.total_skill_refs_in_docs += 1

            # Check if skill exists
            if skill not in skill_to_docs:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="broken_link",
                        source=doc_path,
                        message=f"References @{skill} but skill not found in metadata",
                        suggestion=f"Add {skill} to skills_metadata.yaml or remove reference",
                    )
                )
                stats.broken_links += 1
                continue

            # Check reverse link
            if doc_path not in skill_to_docs[skill]:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="missing_reverse",
                        source=doc_path,
                        message=f"References @{skill} but skill doesn't link back",
                        suggestion=f"Add {doc_path} to @{skill} in skills_metadata.yaml",
                    )
                )
                stats.missing_reverse_links += 1
            else:
                stats.bidirectional_links += 1

    # For each skill→doc link, check if doc exists and has reverse link
    for skill, docs in skill_to_docs.items():
        for doc_path in docs:
            stats.total_doc_refs_in_skills += 1

            # Check if doc exists
            doc_file = base_path / doc_path.lstrip("/")
            if not doc_file.exists():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="broken_link",
                        source=f"@{skill}",
                        message=f"References {doc_path} but file doesn't exist",
                        suggestion=f"Remove {doc_path} from @{skill} or create the file",
                    )
                )
                stats.broken_links += 1
                continue

            # Check reverse link
            if doc_path not in doc_to_skills or skill not in doc_to_skills[doc_path]:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="missing_reverse",
                        source=f"@{skill}",
                        message=f"Links to {doc_path} but doc doesn't reference @{skill}",
                        suggestion=f"Add @{skill} reference to {doc_path}",
                    )
                )
                stats.missing_reverse_links += 1

    # Check for docs with no skill references (potential orphans)
    for doc_path in doc_to_skills:
        if not doc_to_skills[doc_path]:
            # Skip certain docs that legitimately have no skills
            if any(
                x in doc_path
                for x in ["INDEX.md", "README.md", "TROUBLESHOOTING.md", "CROSS_REFERENCE"]
            ):
                continue

            issues.append(
                ValidationIssue(
                    severity="info",
                    category="orphaned",
                    source=doc_path,
                    message="No skill references found",
                    suggestion="Consider adding relevant @skill-name references",
                )
            )

    # Check for skills with no doc references (incomplete metadata)
    for skill in skill_to_docs:
        if not skill_to_docs[skill]:
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="suggestion",
                    source=f"@{skill}",
                    message="No documentation references in metadata",
                    suggestion="Add primary_docs, patterns, or related_adrs to metadata",
                )
            )

    return issues, stats


def print_report(issues: list[ValidationIssue], stats: CrossRefStats, verbose: bool = False) -> None:
    """Print validation report."""
    print("\nCross-Reference Validation Report")
    print("=" * 80)
    print()

    # Statistics
    print("📊 Statistics:")
    print(f"   Total skills: {stats.total_skills}")
    print(f"   Total docs scanned: {stats.total_docs}")
    print(f"   Skill references in docs: {stats.total_skill_refs_in_docs}")
    print(f"   Doc references in skills: {stats.total_doc_refs_in_skills}")
    print()

    # Calculate percentages
    total_links = stats.total_skill_refs_in_docs + stats.total_doc_refs_in_skills
    if total_links > 0:
        bidirectional_pct = (stats.bidirectional_links * 100.0) / stats.total_skill_refs_in_docs
        print(
            f"✅ Bidirectional Links: {stats.bidirectional_links}/{stats.total_skill_refs_in_docs} ({bidirectional_pct:.1f}%)"
        )
    else:
        print("✅ Bidirectional Links: 0/0 (0%)")

    print(f"❌ Broken Links: {stats.broken_links}")
    print(f"⚠️  Missing Reverse Links: {stats.missing_reverse_links}")
    print()

    # Issues by category
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    if errors:
        print("🔴 ERRORS (Must Fix):")
        print()
        for issue in errors:
            print(f"  [{issue.category.upper()}] {issue.source}")
            print(f"    {issue.message}")
            if issue.suggestion:
                print(f"    💡 {issue.suggestion}")
            print()

    if warnings:
        print("🟡 WARNINGS (Should Fix):")
        print()
        for issue in warnings[:10 if not verbose else None]:  # Limit to 10 unless verbose
            print(f"  [{issue.category.upper()}] {issue.source}")
            print(f"    {issue.message}")
            if issue.suggestion:
                print(f"    💡 {issue.suggestion}")
            print()

        if not verbose and len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more warnings (use --verbose to see all)")
            print()

    if verbose and infos:
        print("ℹ️  INFO (Optional Improvements):")
        print()
        for issue in infos[:20]:  # Limit to 20 even in verbose mode
            print(f"  [{issue.category.upper()}] {issue.source}")
            print(f"    {issue.message}")
            if issue.suggestion:
                print(f"    💡 {issue.suggestion}")
            print()

        if len(infos) > 20:
            print(f"  ... and {len(infos) - 20} more info items")
            print()

    # Summary
    print("=" * 80)
    if errors:
        print(f"❌ FAILED: {len(errors)} error(s) must be fixed")
    elif warnings:
        print(f"⚠️  PASSED WITH WARNINGS: {len(warnings)} warning(s) should be addressed")
    else:
        print("✅ PASSED: All cross-references are valid!")
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate cross-references between skills and documentation"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all issues including info")
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Only show errors (exit code 1 if errors found)",
    )
    args = parser.parse_args()

    base_path = Path(__file__).parent.parent

    print("🔍 Validating cross-references...")
    issues, stats = validate_cross_references(base_path)

    if args.errors_only:
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            print(f"\n❌ {len(errors)} error(s) found:")
            for issue in errors:
                print(f"  - {issue.source}: {issue.message}")
            exit(1)
        else:
            print("\n✅ No errors found")
            exit(0)
    else:
        print_report(issues, stats, verbose=args.verbose)

        # Exit code based on errors
        errors = [i for i in issues if i.severity == "error"]
        exit(1 if errors else 0)


if __name__ == "__main__":
    main()
