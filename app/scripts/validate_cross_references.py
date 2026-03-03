#!/usr/bin/env python3
"""
Cross-Reference Validation Script

Validates bidirectional consistency between skills and documentation:
1. Detects broken links (references to non-existent files/skills)
2. Finds missing reverse links (A→B exists but B→A missing)
3. Reports orphaned links
4. Suggests missing cross-references
5. Detects stale skills (primary docs updated after last_reviewed date)

Usage:
    poetry run python scripts/validate_cross_references.py [--fix-suggestions]
"""

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationIssue:
    """Represents a validation issue."""

    severity: str  # "error" | "warning" | "info"
    category: str  # "broken_link" | "missing_reverse" | "orphaned" | "suggestion" | "stale_skill"
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
    stale_skills: int = 0


def load_skills_metadata(base_path: Path) -> dict[str, Any]:
    """Load skills metadata from YAML."""
    metadata_file = base_path / ".claude" / "skills" / "skills_metadata.yaml"
    with open(metadata_file) as f:
        return yaml.safe_load(f)


def get_valid_skills(skills_data: dict[str, Any]) -> set[str]:
    """Derive valid skill names dynamically from loaded metadata."""
    return {skill["name"] for skill in skills_data["skills"]}


def find_skill_references_in_file(file_path: Path, valid_skills: set[str]) -> set[str]:
    """Find all @skill-name references in a file."""
    content = file_path.read_text()
    # Find @skill-name patterns (but not in code blocks)
    matches = re.findall(r"@([a-z0-9-]+)", content)
    # Validate against known skills
    return {m for m in matches if m in valid_skills}


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
    valid_skills: set[str],
) -> tuple[dict[str, set[str]], set[Path]]:
    """
    Scan all docs and find which skills they reference.

    Returns: ({doc_path: set of skills}, set of scanned files)
    """
    doc_to_skills: dict[str, set[str]] = {}
    scanned_files: set[Path] = set()

    # Scan ALL markdown files in docs/ recursively
    docs_dir = base_path / "docs"
    if docs_dir.exists():
        for file_path in docs_dir.rglob("*.md"):
            # Skip archive directory
            if "archive" in file_path.parts:
                continue

            skills = find_skill_references_in_file(file_path, valid_skills)
            # Store with path relative to base (e.g., /docs/development/GENAI_SETUP.md)
            rel_path = f"/{file_path.relative_to(base_path)}"
            doc_to_skills[rel_path] = skills
            scanned_files.add(file_path)

    # Also scan root-level markdown files
    for file_path in base_path.glob("*.md"):
        skills = find_skill_references_in_file(file_path, valid_skills)
        rel_path = f"/{file_path.relative_to(base_path)}"
        doc_to_skills[rel_path] = skills
        scanned_files.add(file_path)

    # Scan monitoring/ directory
    monitoring_dir = base_path / "monitoring"
    if monitoring_dir.exists():
        for file_path in monitoring_dir.rglob("*.md"):
            skills = find_skill_references_in_file(file_path, valid_skills)
            rel_path = f"/{file_path.relative_to(base_path)}"
            doc_to_skills[rel_path] = skills
            scanned_files.add(file_path)

    return doc_to_skills, scanned_files


def get_doc_last_modified(doc_path: str, base_path: Path) -> str | None:
    """
    Get the last git commit date for a doc file (YYYY-MM-DD).

    Returns None if the file has no git history or git fails.
    """
    full_path = base_path / doc_path.lstrip("/")
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%Y-%m-%d", "--", str(full_path)],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(base_path),
        )
        date = result.stdout.strip()
        return date if date else None
    except Exception:
        return None


def check_skill_staleness(
    skill: dict[str, Any],
    base_path: Path,
) -> list[ValidationIssue]:
    """
    Check if a skill's primary docs have been updated since last_reviewed.

    Only checks primary_docs (the docs the skill directly teaches from).
    Skips docs that don't exist — those are caught as broken links.
    """
    last_reviewed = skill.get("last_reviewed")
    if not last_reviewed:
        return []

    last_reviewed_str = str(last_reviewed)
    stale_docs: list[tuple[str, str]] = []

    for doc_path in skill.get("primary_docs", []):
        doc_file = base_path / doc_path.lstrip("/")
        if not doc_file.exists():
            continue  # Already caught as broken link

        last_modified = get_doc_last_modified(doc_path, base_path)
        if last_modified and last_modified > last_reviewed_str:
            stale_docs.append((doc_path, last_modified))

    if not stale_docs:
        return []

    doc_summary = "; ".join(f"{Path(p).name} (modified {d})" for p, d in stale_docs[:3])
    return [
        ValidationIssue(
            severity="warning",
            category="stale_skill",
            source=f"@{skill['name']}",
            message=f"Primary docs updated since last review ({last_reviewed_str}): {doc_summary}",
            suggestion=f"Review @{skill['name']} SKILL.md, then update last_reviewed in skills_metadata.yaml",
        )
    ]


def validate_cross_references(base_path: Path) -> tuple[list[ValidationIssue], CrossRefStats]:
    """
    Validate all cross-references.

    Returns: (list of issues, statistics)
    """
    issues: list[ValidationIssue] = []
    stats = CrossRefStats()

    # Load data
    skills_data = load_skills_metadata(base_path)
    valid_skills = get_valid_skills(skills_data)
    adr_map = find_actual_adr_files(base_path)
    skill_to_docs = find_doc_references_in_skills(skills_data, adr_map)
    doc_to_skills, scanned_files = collect_doc_to_skills_mapping(base_path, valid_skills)

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

    # Check skill staleness — primary docs updated after last_reviewed
    for skill in skills_data["skills"]:
        stale_issues = check_skill_staleness(skill, base_path)
        issues.extend(stale_issues)
        stats.stale_skills += len(stale_issues)

    return issues, stats


def print_report(
    issues: list[ValidationIssue], stats: CrossRefStats, verbose: bool = False
) -> None:
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
    print(f"🔵 Stale Skills: {stats.stale_skills}")
    print()

    # Issues by category
    errors = [i for i in issues if i.severity == "error"]
    stale = [i for i in issues if i.category == "stale_skill"]
    warnings = [i for i in issues if i.severity == "warning" and i.category != "stale_skill"]
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

    if stale:
        print(f"🔵 STALE SKILLS — primary docs updated since last review ({len(stale)}):")
        print()
        for issue in stale:
            print(f"  {issue.source}")
            print(f"    {issue.message}")
            print(f"    💡 {issue.suggestion}")
            print()

    if warnings:
        print(f"🟡 WARNINGS (Should Fix) ({len(warnings)}):")
        print()
        for issue in warnings[: 10 if not verbose else None]:  # Limit to 10 unless verbose
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
    elif stale:
        print(f"🔵 PASSED WITH STALE SKILLS: {len(stale)} skill(s) may need review")
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
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all issues including info"
    )
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

        # Exit code based on errors only (staleness is informational)
        errors = [i for i in issues if i.severity == "error"]
        exit(1 if errors else 0)


if __name__ == "__main__":
    main()
