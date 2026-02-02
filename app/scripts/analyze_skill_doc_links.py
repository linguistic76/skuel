#!/usr/bin/env python3
"""
Analyze bidirectional links between skills and docs.

This script helps gather information for enhancing skills_metadata.yaml by:
1. Finding which pattern docs reference each skill
2. Finding which ADRs should be linked to each skill
3. Identifying missing reverse links
"""

import re
from pathlib import Path
from typing import Any

import yaml


def load_doc_frontmatter(doc_path: Path) -> dict[str, Any] | None:
    """Load frontmatter from a markdown doc."""
    content = doc_path.read_text()
    if not content.startswith("---\n"):
        return None

    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return None

    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def find_skill_references_in_body(doc_path: Path) -> list[str]:
    """Find @skill-name references in doc body."""
    content = doc_path.read_text()
    return re.findall(r"@([a-z0-9-]+)", content)


def main() -> None:
    """Main entry point."""
    base_path = Path(__file__).parent.parent

    # Map: skill_name -> {pattern_docs: [], adrs: [], architecture_docs: []}
    skill_to_docs: dict[str, dict[str, list[str]]] = {}

    # Analyze pattern docs
    patterns_dir = base_path / "docs" / "patterns"
    for doc_path in patterns_dir.glob("*.md"):
        frontmatter = load_doc_frontmatter(doc_path)
        if not frontmatter:
            continue

        related_skills = frontmatter.get("related_skills", [])
        doc_rel_path = f"/docs/patterns/{doc_path.name}"

        for skill in related_skills:
            if skill not in skill_to_docs:
                skill_to_docs[skill] = {
                    "pattern_docs": [],
                    "adrs": [],
                    "architecture_docs": [],
                }
            skill_to_docs[skill]["pattern_docs"].append(doc_rel_path)

    # Analyze ADRs
    adrs_dir = base_path / "docs" / "decisions"
    for doc_path in adrs_dir.glob("ADR-*.md"):
        # Extract ADR references from content (look for skill references)
        body_skills = find_skill_references_in_body(doc_path)
        adr_name = doc_path.stem  # e.g., "ADR-035-tier-selection-guidelines"
        adr_number = adr_name.split("-")[1]  # e.g., "035"

        for skill in body_skills:
            if skill not in skill_to_docs:
                skill_to_docs[skill] = {
                    "pattern_docs": [],
                    "adrs": [],
                    "architecture_docs": [],
                }
            if adr_number not in skill_to_docs[skill]["adrs"]:
                skill_to_docs[skill]["adrs"].append(adr_number)

    # Analyze architecture docs
    arch_dir = base_path / "docs" / "architecture"
    for doc_path in arch_dir.glob("*.md"):
        body_skills = find_skill_references_in_body(doc_path)
        doc_rel_path = f"/docs/architecture/{doc_path.name}"

        for skill in body_skills:
            if skill not in skill_to_docs:
                skill_to_docs[skill] = {
                    "pattern_docs": [],
                    "adrs": [],
                    "architecture_docs": [],
                }
            skill_to_docs[skill]["architecture_docs"].append(doc_rel_path)

    # Print results organized by skill
    all_skills = sorted(skill_to_docs.keys())
    print("# Skill → Documentation Mapping\n")

    for skill in all_skills:
        docs = skill_to_docs[skill]
        print(f"## {skill}")

        if docs["pattern_docs"]:
            print("\n**Pattern Docs:**")
            for doc in sorted(docs["pattern_docs"]):
                print(f"  - {doc}")

        if docs["architecture_docs"]:
            print("\n**Architecture Docs:**")
            for doc in sorted(docs["architecture_docs"]):
                print(f"  - {doc}")

        if docs["adrs"]:
            print("\n**Related ADRs:**")
            for adr in sorted(docs["adrs"], key=lambda x: int(x)):
                print(f"  - ADR-{adr}")

        print()

    # Print summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(
        f"  Skills with pattern doc links: {len([s for s in skill_to_docs if skill_to_docs[s]['pattern_docs']])}"
    )
    print(f"  Skills with ADR links: {len([s for s in skill_to_docs if skill_to_docs[s]['adrs']])}")
    print(
        f"  Skills with architecture doc links: {len([s for s in skill_to_docs if skill_to_docs[s]['architecture_docs']])}"
    )
    print(f"  Total unique skills referenced: {len(all_skills)}")


if __name__ == "__main__":
    main()
