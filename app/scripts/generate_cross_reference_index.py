#!/usr/bin/env python3
"""
Generate CROSS_REFERENCE_INDEX.md from skills metadata and pattern frontmatter.

This script creates a comprehensive bidirectional mapping between skills and docs.
"""

import re
from operator import itemgetter
from pathlib import Path
from typing import Any

import yaml


def _parse_adr_number(adr_id: str) -> int:
    """Extract numeric part from ADR identifier for sorting."""
    return int(adr_id.replace("ADR-", ""))


def load_skills_metadata(base_path: Path) -> dict[str, Any]:
    """Load skills metadata from YAML."""
    metadata_file = base_path / ".claude" / "skills" / "skills_metadata.yaml"
    with open(metadata_file) as f:
        return yaml.safe_load(f)


def load_pattern_frontmatter(base_path: Path) -> dict[str, dict[str, Any]]:
    """Load frontmatter from all pattern docs."""
    patterns_dir = base_path / "docs" / "patterns"
    pattern_data = {}

    for doc_path in patterns_dir.glob("*.md"):
        content = doc_path.read_text()
        if not content.startswith("---\n"):
            continue

        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if not match:
            continue

        try:
            frontmatter = yaml.safe_load(match.group(1))
            pattern_data[doc_path.name] = frontmatter
        except yaml.YAMLError:
            pass

    return pattern_data


def generate_index_content(base_path: Path) -> str:
    """Generate the cross-reference index content."""
    skills_data = load_skills_metadata(base_path)
    pattern_data = load_pattern_frontmatter(base_path)

    content = ["# Cross-Reference Index: Skills ↔ Documentation"]
    content.append("")
    content.append(
        "**Purpose:** Single source of truth for bidirectional skill-documentation mapping."
    )
    content.append("")
    content.append(
        "**Generated:** This file is auto-generated from `skills_metadata.yaml` and pattern doc frontmatter."
    )
    content.append(
        "**Regenerate:** Run `uv run python scripts/generate_cross_reference_index.py`"
    )
    content.append("")
    content.append("---")
    content.append("")

    # Part 1: By Skill
    content.append("## By Skill")
    content.append("")
    content.append(
        "For each skill, this section shows all related documentation (architecture docs, patterns, ADRs)."
    )
    content.append("")

    for skill in sorted(skills_data["skills"], key=itemgetter("name")):
        name = skill["name"]
        description = skill.get("description", "")
        primary_docs = skill.get("primary_docs", [])
        patterns = skill.get("patterns", [])
        related_adrs = skill.get("related_adrs", [])

        content.append(f"### @{name}")
        content.append("")
        content.append(f"**Description:** {description}")
        content.append("")

        if primary_docs:
            # Categorize primary docs
            arch_docs = [d for d in primary_docs if "/docs/architecture/" in d]
            pattern_docs = [d for d in primary_docs if "/docs/patterns/" in d]
            guide_docs = [d for d in primary_docs if "/docs/guides/" in d]
            intel_docs = [d for d in primary_docs if "/docs/intelligence/" in d]
            domain_docs = [d for d in primary_docs if "/docs/domains/" in d]
            other_docs = [
                d
                for d in primary_docs
                if d not in arch_docs + pattern_docs + guide_docs + intel_docs + domain_docs
            ]

            if arch_docs:
                content.append("**Architecture:**")
                for doc in arch_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

            if intel_docs:
                content.append("**Intelligence:**")
                for doc in intel_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

            if pattern_docs:
                content.append("**Patterns (Primary):**")
                for doc in pattern_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

            if guide_docs:
                content.append("**Guides:**")
                for doc in guide_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

            if domain_docs:
                content.append("**Domain Docs:**")
                for doc in domain_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

            if other_docs:
                content.append("**Other:**")
                for doc in other_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc})")
                content.append("")

        if patterns:
            content.append("**Patterns (Additional):**")
            for doc in patterns:
                doc_name = doc.split("/")[-1]
                content.append(f"- [{doc_name}]({doc})")
            content.append("")

        if related_adrs:
            content.append("**ADRs:**")
            for adr in related_adrs:
                adr_file = f"ADR-{adr}.md" if not adr.startswith("ADR-") else f"{adr}.md"
                content.append(f"- [{adr}](/docs/decisions/{adr_file})")
            content.append("")

        if not primary_docs and not patterns and not related_adrs:
            content.append("*No documentation links yet.*")
            content.append("")

    # Part 2: By Document Category
    content.append("---")
    content.append("")
    content.append("## By Document Category")
    content.append("")
    content.append("For each documentation category, this section shows which skills are relevant.")
    content.append("")

    # 2.1: Architecture Docs
    content.append("### Architecture Docs")
    content.append("")

    arch_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []):
            if "/docs/architecture/" in doc:
                doc_name = doc.split("/")[-1]
                if doc_name not in arch_to_skills:
                    arch_to_skills[doc_name] = []
                arch_to_skills[doc_name].append(skill["name"])

    for doc_name in sorted(arch_to_skills.keys()):
        skills = sorted(set(arch_to_skills[doc_name]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/architecture/{doc_name}"
        content.append(f"- [{doc_name}]({doc_path}) → {skills_str}")

    content.append("")

    # 2.2: Intelligence Docs
    content.append("### Intelligence Docs")
    content.append("")

    intel_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []):
            if "/docs/intelligence/" in doc:
                doc_name = doc.split("/")[-1]
                if doc_name not in intel_to_skills:
                    intel_to_skills[doc_name] = []
                intel_to_skills[doc_name].append(skill["name"])

    for doc_name in sorted(intel_to_skills.keys()):
        skills = sorted(set(intel_to_skills[doc_name]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/intelligence/{doc_name}"
        content.append(f"- [{doc_name}]({doc_path}) → {skills_str}")

    content.append("")

    # 2.3: Pattern Docs
    content.append("### Pattern Docs")
    content.append("")

    pattern_to_skills: dict[str, list[str]] = {}

    # From skills metadata (primary_docs + patterns)
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []) + skill.get("patterns", []):
            if "/docs/patterns/" in doc:
                doc_name = doc.split("/")[-1]
                if doc_name not in pattern_to_skills:
                    pattern_to_skills[doc_name] = []
                pattern_to_skills[doc_name].append(skill["name"])

    # From pattern frontmatter
    for doc_name, frontmatter in pattern_data.items():
        related_skills = frontmatter.get("related_skills", [])
        if doc_name not in pattern_to_skills:
            pattern_to_skills[doc_name] = []
        pattern_to_skills[doc_name].extend(related_skills)

    for doc_name in sorted(pattern_to_skills.keys()):
        skills = sorted(set(pattern_to_skills[doc_name]))
        if not skills:
            continue
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/patterns/{doc_name}"
        content.append(f"- [{doc_name}]({doc_path}) → {skills_str}")

    content.append("")

    # 2.4: ADRs
    content.append("### ADRs (Architecture Decision Records)")
    content.append("")

    adr_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for adr in skill.get("related_adrs", []):
            if adr not in adr_to_skills:
                adr_to_skills[adr] = []
            adr_to_skills[adr].append(skill["name"])

    for adr in sorted(adr_to_skills.keys(), key=_parse_adr_number):
        skills = sorted(set(adr_to_skills[adr]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        adr_file = f"ADR-{adr}.md" if not adr.startswith("ADR-") else f"{adr}.md"
        adr_path = f"/docs/decisions/{adr_file}"
        content.append(f"- [{adr}]({adr_path}) → {skills_str}")

    content.append("")

    # Statistics
    content.append("---")
    content.append("")
    content.append("## Statistics")
    content.append("")
    content.append(f"- **Total skills:** {len(skills_data['skills'])}")
    content.append(f"- **Architecture docs:** {len(arch_to_skills)} docs linked to skills")
    content.append(f"- **Intelligence docs:** {len(intel_to_skills)} docs linked to skills")
    content.append(
        f"- **Pattern docs:** {len([d for d in pattern_to_skills if pattern_to_skills[d]])} docs linked to skills"
    )
    content.append(f"- **ADRs:** {len(adr_to_skills)} ADRs linked to skills")
    content.append("")

    # Footer
    content.append("---")
    content.append("")
    content.append("## Maintenance")
    content.append("")
    content.append("**When to Update:**")
    content.append("- After adding a new skill")
    content.append("- After creating a new pattern doc")
    content.append("- After writing a new ADR")
    content.append("- After updating skills_metadata.yaml")
    content.append("")
    content.append("**How to Update:**")
    content.append("```bash\nuv run python scripts/generate_cross_reference_index.py\n```")
    content.append("")
    content.append("**Related Files:**")
    content.append("- `.claude/skills/skills_metadata.yaml` - Machine-readable metadata")
    content.append("- `docs/patterns/*.md` - Pattern doc frontmatter")
    content.append("- `scripts/generate_cross_reference_index.py` - This generator script")
    content.append("")

    return "\n".join(content)


def main() -> None:
    """Main entry point."""
    base_path = Path(__file__).parent.parent
    output_file = base_path / "docs" / "CROSS_REFERENCE_INDEX.md"

    print("Generating cross-reference index...")
    content = generate_index_content(base_path)

    output_file.write_text(content)
    print(f"✅ Generated: {output_file}")
    print(f"   Lines: {len(content.splitlines())}")


if __name__ == "__main__":
    main()
