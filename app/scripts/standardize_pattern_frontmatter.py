#!/usr/bin/env python3
"""
Standardize frontmatter across all pattern docs.

This script:
1. Analyzes current frontmatter state
2. Standardizes to minimal required fields
3. Preserves related_skills and converts 'related' to 'related_docs'
"""

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from core.utils.frontmatter import parse_frontmatter as _parse_frontmatter

# Valid SKUEL skills (authoritative list from .claude/skills/)
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


def extract_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Extract YAML frontmatter and body from markdown content."""
    frontmatter, body = _parse_frontmatter(content)
    if not frontmatter:
        return None, content
    return frontmatter, body


def extract_title_from_body(body: str) -> str:
    """Extract title from first # heading in body."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled Pattern"


def infer_related_skills(file_path: Path, body: str) -> list[str]:
    """Infer related skills based on file name and explicit @skill-name references."""
    name = file_path.stem.lower()

    # Extract skills from @skill-name references in the body and validate
    extracted_skills = re.findall(r"@([a-z0-9-]+)", body)
    valid_extracted = [s for s in extracted_skills if s in VALID_SKILLS]

    # Only infer from filename (not from content to avoid over-matching)
    skills_map = {
        "error": ["result-pattern", "ui-error-handling"],
        "validation": ["pydantic", "skuel-form-patterns"],
        "three_tier": ["python", "pydantic"],
        "ui_component": ["base-page-architecture", "daisyui", "tailwind-css"],
        "fasthtml": ["fasthtml", "html-htmx"],
        "service": ["base-analytics-service"],
        "protocol": ["python"],
        "query": ["neo4j-cypher-patterns"],
        "event": ["python", "result-pattern"],
        "ownership": ["activity-domains", "curriculum-domains"],
        "route": ["fasthtml"],
        "linter": ["python"],
        "async": ["python"],
        "neo4j": ["neo4j-cypher-patterns"],
        "cypher": ["neo4j-cypher-patterns"],
        "relationship": ["neo4j-cypher-patterns"],
        "search": ["skuel-search-architecture", "neo4j-genai-plugin"],
        "form": ["skuel-form-patterns", "pydantic"],
        "alpine": ["js-alpine"],
        "htmx": ["html-htmx"],
        "accessibility": ["accessibility-guide"],
        "prometheus": ["prometheus-grafana"],
        "grafana": ["prometheus-grafana"],
        "genai": ["neo4j-genai-plugin"],
        "component": ["skuel-component-composition"],
        "sidebar": ["custom-sidebar-patterns"],
        "page": ["base-page-architecture"],
        "chart": ["chartjs"],
        "test": ["pytest"],
    }

    inferred = list(valid_extracted)  # Start with valid extracted skills
    for keyword, skills in skills_map.items():
        # Only match against filename, not content (conservative approach)
        if keyword in name:
            inferred.extend(skills)

    return list(set(inferred))  # Remove duplicates


def convert_related_to_docs(related: list[str]) -> list[str]:
    """Convert 'related' field entries to full paths."""
    docs = []
    for item in related:
        if item.startswith("/"):
            docs.append(item)
        elif item.startswith("ADR-"):
            docs.append(f"/docs/decisions/{item}")
        elif item.endswith(".md"):
            # Try to infer the category
            if "ADR-" in item:
                docs.append(f"/docs/decisions/{item}")
            else:
                # Assume it's a pattern doc
                docs.append(f"/docs/patterns/{item}")
        else:
            # Unknown format, skip
            pass
    return docs


def standardize_frontmatter(
    file_path: Path, content: str, dry_run: bool = True
) -> tuple[str, dict[str, Any]]:
    """Standardize frontmatter for a single file."""
    frontmatter, body = extract_frontmatter(content)

    # Extract or infer required fields
    if frontmatter:
        title = frontmatter.get("title", extract_title_from_body(body))
        updated = frontmatter.get("updated", str(date.today()))
        existing_skills = frontmatter.get("related_skills", [])
        related = frontmatter.get("related", [])
        related_docs = frontmatter.get("related_docs", [])
    else:
        title = extract_title_from_body(body)
        updated = str(date.today())
        existing_skills = []
        related = []
        related_docs = []

    # Convert old 'related' to 'related_docs'
    if related and not related_docs:
        related_docs = convert_related_to_docs(related)

    # Always infer skills from body and merge with existing
    inferred_skills = infer_related_skills(file_path, body)
    related_skills = list(set(existing_skills + inferred_skills))  # Merge and deduplicate

    # Build standardized frontmatter
    new_frontmatter = {
        "title": title,
        "updated": updated,
        "category": "patterns",
        "related_skills": related_skills,
        "related_docs": related_docs,
    }

    # Build new content
    frontmatter_yaml = yaml.dump(new_frontmatter, default_flow_style=False, sort_keys=False)
    new_content = f"---\n{frontmatter_yaml}---\n{body}"

    stats = {
        "had_frontmatter": frontmatter is not None,
        "had_related_skills": bool(frontmatter and frontmatter.get("related_skills")),
        "inferred_skills": not bool(frontmatter and frontmatter.get("related_skills")),
        "skills_count": len(related_skills),
        "docs_count": len(related_docs),
    }

    if not dry_run:
        file_path.write_text(new_content)

    return new_content, stats


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Standardize frontmatter for pattern docs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files, just show what would change",
    )
    parser.add_argument("--file", type=str, help="Process single file instead of all pattern docs")
    args = parser.parse_args()

    patterns_dir = Path(__file__).parent.parent / "docs" / "patterns"

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(patterns_dir.glob("*.md"))

    print(f"{'DRY RUN - ' if args.dry_run else ''}Processing {len(files)} files...\n")

    total_stats = {
        "total": 0,
        "had_frontmatter": 0,
        "had_related_skills": 0,
        "inferred_skills": 0,
        "total_skills": 0,
        "total_docs": 0,
    }

    for file_path in files:
        content = file_path.read_text()
        new_content, stats = standardize_frontmatter(file_path, content, args.dry_run)

        total_stats["total"] += 1
        total_stats["had_frontmatter"] += int(stats["had_frontmatter"])
        total_stats["had_related_skills"] += int(stats["had_related_skills"])
        total_stats["inferred_skills"] += int(stats["inferred_skills"])
        total_stats["total_skills"] += stats["skills_count"]
        total_stats["total_docs"] += stats["docs_count"]

        status = "✓" if stats["had_frontmatter"] else "+"
        skills_note = (
            f"({stats['skills_count']} skills)" if stats["skills_count"] else "(no skills)"
        )

        print(f"{status} {file_path.name:50} {skills_note}")

        if args.file and args.dry_run:
            print("\nNew content preview:")
            print("=" * 80)
            print(new_content[:500])
            print("...")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Total files: {total_stats['total']}")
    print(f"  Had frontmatter: {total_stats['had_frontmatter']}")
    print(f"  Had related_skills: {total_stats['had_related_skills']}")
    print(f"  Inferred skills: {total_stats['inferred_skills']}")
    print(f"  Total skills added: {total_stats['total_skills']}")
    print(f"  Total docs linked: {total_stats['total_docs']}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes")
    else:
        print("\n✅ All files updated!")


if __name__ == "__main__":
    main()
