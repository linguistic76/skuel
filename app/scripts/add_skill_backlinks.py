#!/usr/bin/env python3
"""
Add Skill Backlinks to Documentation

Automatically adds 'related_skills' field to documentation frontmatter
based on the skills_metadata.yaml registry.

Usage:
    poetry run python scripts/add_skill_backlinks.py           # Dry run
    poetry run python scripts/add_skill_backlinks.py --apply   # Apply changes
"""

import re
import sys
from pathlib import Path

import yaml


def load_skills_metadata(metadata_path: Path) -> list[dict]:
    """Load skills from metadata."""
    content = metadata_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    return data.get("skills", [])


def build_doc_to_skills_map(skills: list[dict]) -> dict[str, set[str]]:
    """
    Build a mapping of doc path -> set of skill names.

    Each doc can be referenced by multiple skills.
    """
    doc_to_skills: dict[str, set[str]] = {}

    for skill in skills:
        skill_name = skill.get("name")
        if not skill_name:
            continue

        primary_docs = skill.get("primary_docs", [])
        for doc_path in primary_docs:
            if doc_path not in doc_to_skills:
                doc_to_skills[doc_path] = set()
            doc_to_skills[doc_path].add(skill_name)

    return doc_to_skills


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body_content).
    If no frontmatter, returns (empty_dict, full_content).
    """
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end_match = re.search(r"\n---\n", content[3:])
    if not end_match:
        return {}, content

    frontmatter_text = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return {}, content

    return frontmatter, body


def serialize_frontmatter(frontmatter: dict) -> str:
    """Serialize frontmatter dict to YAML."""
    return yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)


def add_related_skills(
    content: str, skill_names: set[str]
) -> tuple[str, bool]:
    """
    Add or update related_skills field in frontmatter.

    Returns (new_content, was_modified).
    """
    frontmatter, body = parse_frontmatter(content)

    # Get existing related_skills
    existing_skills = set(frontmatter.get("related_skills", []))

    # Merge with new skills
    all_skills = existing_skills | skill_names

    # Check if we're adding anything new
    if all_skills == existing_skills:
        return content, False

    # Update frontmatter
    frontmatter["related_skills"] = sorted(all_skills)

    # Reconstruct content
    new_content = "---\n" + serialize_frontmatter(frontmatter) + "---\n" + body

    return new_content, True


def process_docs(
    doc_to_skills: dict[str, set[str]], project_root: Path, dry_run: bool = True
) -> None:
    """Process all docs and add related_skills field."""
    modified_files = []
    skipped_files = []
    missing_files = []

    for doc_path_str, skill_names in doc_to_skills.items():
        # Convert to absolute path
        if doc_path_str.startswith("/"):
            doc_path = project_root / doc_path_str.lstrip("/")
        else:
            doc_path = project_root / doc_path_str

        if not doc_path.exists():
            missing_files.append(doc_path_str)
            continue

        # Read content
        content = doc_path.read_text(encoding="utf-8")

        # Add related_skills
        new_content, was_modified = add_related_skills(content, skill_names)

        if was_modified:
            rel_path = str(doc_path.relative_to(project_root))

            if not dry_run:
                doc_path.write_text(new_content, encoding="utf-8")
                modified_files.append((rel_path, sorted(skill_names)))
            else:
                print(f"Would update: {rel_path}")
                print(f"  Adding skills: {sorted(skill_names)}")
                modified_files.append((rel_path, sorted(skill_names)))
        else:
            skipped_files.append(doc_path_str)

    # Print summary
    print()
    print("=" * 60)
    if dry_run:
        print("DRY RUN SUMMARY")
        print("=" * 60)
        print(f"Would modify {len(modified_files)} file(s)")
        print(f"Would skip {len(skipped_files)} file(s) (already up-to-date)")
        if missing_files:
            print(f"Missing {len(missing_files)} file(s)")
        print()
        print("Run with --apply to actually modify files")
    else:
        print("UPDATE SUMMARY")
        print("=" * 60)
        print(f"Modified {len(modified_files)} file(s)")
        print(f"Skipped {len(skipped_files)} file(s) (already up-to-date)")
        if missing_files:
            print(f"Missing {len(missing_files)} file(s)")
        print()
        if modified_files:
            print("Modified files:")
            for file_path, skills in modified_files:
                print(f"  ✅ {file_path}")
                print(f"     Skills: {', '.join(skills)}")
    print("=" * 60)


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--apply" not in args

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Load skills metadata
    skills_dir = project_root / ".claude" / "skills"
    metadata_path = skills_dir / "skills_metadata.yaml"
    skills = load_skills_metadata(metadata_path)

    # Build doc-to-skills mapping
    doc_to_skills = build_doc_to_skills_map(skills)

    if dry_run:
        print("Running in DRY RUN mode...")
        print()

    print(f"Found {len(doc_to_skills)} unique docs referenced by skills")
    print()

    process_docs(doc_to_skills, project_root, dry_run=dry_run)


if __name__ == "__main__":
    main()
