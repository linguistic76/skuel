#!/usr/bin/env python3
"""
Add missing skill references to document frontmatter based on validation warnings.

This script addresses MISSING_REVERSE warnings by adding skill references
to the related_skills field in YAML frontmatter.
"""

import re
from pathlib import Path

# Mapping from validation warnings: {file_path: [skills_to_add]}
MISSING_REVERSE_LINKS: dict[str, list[str]] = {
    "/docs/patterns/UI_COMPONENT_PATTERNS.md": [
        "html-htmx",
        "html-navigation",
        "js-alpine",
        "accessibility-guide",
        "custom-sidebar-patterns",
        "skuel-component-composition",
    ],
    "/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md": [
        "html-htmx",
        "accessibility-guide",
    ],
    "/docs/architecture/ALPINE_JS_ARCHITECTURE.md": ["js-alpine"],
    "/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md": ["chartjs"],
    "/docs/guides/HTMX_VERSION_STANDARDIZATION.md": ["html-htmx"],
    "/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md": ["skuel-component-composition"],
    "/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md": ["neo4j-cypher-patterns"],
    "/docs/patterns/SKUEL_QUERY_USAGE_GUIDE.md": ["neo4j-cypher-patterns"],
    "/docs/deployment/AURADB_MIGRATION_GUIDE.md": ["neo4j-genai-plugin"],
    "/docs/development/GENAI_SETUP.md": ["neo4j-genai-plugin"],
    "/monitoring/README.md": ["prometheus-grafana"],
    "/docs/patterns/PERFORMANCE_MONITORING.md": ["prometheus-grafana"],
    "/OBSERVABILITY_PHASE1_COMPLETE.md": ["prometheus-grafana"],
    "/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md": [
        "base-analytics-service",
        "base-ai-service",
    ],
    "/docs/domains/goals.md": ["activity-domains"],
    "/docs/domains/habits.md": ["activity-domains"],
    "/docs/domains/tasks.md": ["activity-domains"],
    "/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md": ["activity-domains"],
    "/docs/domains/ls.md": ["curriculum-domains"],
    "/docs/domains/moc.md": ["curriculum-domains"],
    "/docs/domains/ku.md": ["curriculum-domains"],
    "/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md": ["curriculum-domains"],
    "/docs/domains/lp.md": ["curriculum-domains"],
    "/docs/architecture/SEARCH_ARCHITECTURE.md": ["skuel-search-architecture"],
    "/docs/reference/SEARCH_SERVICE_METHODS.md": ["skuel-search-architecture"],
    "/docs/architecture/UNIFIED_USER_ARCHITECTURE.md": ["user-context-intelligence"],
    "/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md": ["user-context-intelligence"],
    "/TESTING.md": ["pytest"],
}


def extract_frontmatter(content: str) -> tuple[str | None, str]:
    """Extract YAML frontmatter and body from markdown content."""
    if not content.startswith("---"):
        return None, content

    # Find the closing ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    return parts[1], parts[2]


def parse_related_skills(frontmatter: str) -> set[str]:
    """Extract existing related_skills from frontmatter."""
    skills = set()
    in_related_skills = False

    for line in frontmatter.split("\n"):
        if line.strip().startswith("related_skills:"):
            in_related_skills = True
            # Check for inline array: related_skills: [skill1, skill2]
            inline_match = re.search(r"\[(.*?)\]", line)
            if inline_match:
                skill_str = inline_match.group(1)
                skills.update(s.strip() for s in skill_str.split(",") if s.strip())
                in_related_skills = False
        elif in_related_skills:
            if line.strip().startswith("-"):
                skill = line.strip().lstrip("-").strip()
                if skill:
                    skills.add(skill)
            elif line.strip() and not line.startswith(" "):
                # Hit next field
                in_related_skills = False

    return skills


def update_frontmatter(frontmatter: str, new_skills: list[str]) -> str:
    """Add new skills to related_skills field in frontmatter."""
    existing_skills = parse_related_skills(frontmatter)
    all_skills = sorted(existing_skills.union(new_skills))

    # Check if related_skills field exists
    has_related_skills = "related_skills:" in frontmatter

    if not has_related_skills:
        # Add related_skills field before closing
        lines = frontmatter.rstrip().split("\n")
        lines.append("related_skills:")
        for skill in all_skills:
            lines.append(f"  - {skill}")
        return "\n".join(lines) + "\n"

    # Update existing related_skills field
    lines = frontmatter.split("\n")
    new_lines = []
    in_related_skills = False

    for line in lines:
        if line.strip().startswith("related_skills:"):
            in_related_skills = True
            # Check for inline array
            if "[" in line:
                # Replace inline array with multiline
                new_lines.append("related_skills:")
                for skill in all_skills:
                    new_lines.append(f"  - {skill}")
                in_related_skills = False
            else:
                new_lines.append(line)
        elif in_related_skills:
            if line.strip().startswith("-"):
                # Skip existing skill lines, we'll replace them all
                continue
            if line.strip() == "" or (line.startswith("  ") and not line.strip().startswith("-")):
                # Empty line or continuation, skip
                continue
            # Hit next field, insert all skills now
            for skill in all_skills:
                new_lines.append(f"  - {skill}")
            in_related_skills = False
            new_lines.append(line)
        else:
            new_lines.append(line)

    # If we were still in related_skills at end, add skills now
    if in_related_skills:
        for skill in all_skills:
            new_lines.append(f"  - {skill}")

    return "\n".join(new_lines)


def process_file(file_path: Path, skills_to_add: list[str]) -> bool:
    """Add missing skills to file's frontmatter. Returns True if modified."""
    if not file_path.exists():
        print(f"⚠️  File not found: {file_path}")
        return False

    content = file_path.read_text()
    frontmatter, body = extract_frontmatter(content)

    if frontmatter is None:
        print(f"⚠️  No frontmatter in: {file_path}")
        # Add frontmatter
        frontmatter_lines = [
            "---",
            f"title: {file_path.stem.replace('_', ' ').replace('-', ' ').title()}",
            "related_skills:",
        ]
        for skill in sorted(skills_to_add):
            frontmatter_lines.append(f"  - {skill}")
        frontmatter_lines.append("---")
        new_content = "\n".join(frontmatter_lines) + "\n" + content
        file_path.write_text(new_content)
        print(f"✅ Added frontmatter with {len(skills_to_add)} skill(s): {file_path}")
        return True

    # Update existing frontmatter
    existing_skills = parse_related_skills(frontmatter)
    skills_to_actually_add = [s for s in skills_to_add if s not in existing_skills]

    if not skills_to_actually_add:
        print(f"⏭️  Already has all skills: {file_path}")
        return False

    updated_frontmatter = update_frontmatter(frontmatter, skills_to_actually_add)
    new_content = f"---{updated_frontmatter}---{body}"

    file_path.write_text(new_content)
    print(f"✅ Added {len(skills_to_actually_add)} skill(s) to: {file_path}")
    return True


def main():
    """Process all files with missing reverse links."""
    base_path = Path(__file__).parent.parent
    print("🔧 Adding missing skill references to frontmatter...\n")

    modified_count = 0
    skipped_count = 0

    for rel_path, skills in MISSING_REVERSE_LINKS.items():
        # Remove leading slash for Path construction
        file_path = base_path / rel_path.lstrip("/")

        if process_file(file_path, skills):
            modified_count += 1
        else:
            skipped_count += 1

    print("\n📊 Summary:")
    print(f"   Modified: {modified_count} files")
    print(f"   Skipped: {skipped_count} files")
    print("\nNext step: Run sync_cross_references.py to regenerate 'Related Skills' sections")


if __name__ == "__main__":
    main()
