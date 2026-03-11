#!/usr/bin/env python3
"""
Generate Stub Files for Skills

Creates missing QUICK_REFERENCE.md and PATTERNS.md files for all skills
using the templates in .claude/skills/_templates/

Usage:
    uv run python scripts/generate_skill_stubs.py          # Dry run
    uv run python scripts/generate_skill_stubs.py --apply  # Actually create files
"""

import sys
from pathlib import Path

import yaml


def load_skills_metadata(metadata_path: Path) -> list[dict]:
    """Load skills from metadata."""
    content = metadata_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    return data.get("skills", [])


def load_template(template_path: Path) -> str:
    """Load a template file."""
    return template_path.read_text(encoding="utf-8")


def customize_template(template: str, skill_name: str, skill_desc: str) -> str:
    """Customize template for a specific skill."""
    # Replace placeholders
    content = template.replace("[Skill Name]", skill_name.replace("-", " ").title())
    content = content.replace("[skill-name]", skill_name)

    # Add skill description if it's the first occurrence
    if "[One-sentence description" in content:
        content = content.replace(
            "[One-sentence description of what this skill helps with]", skill_desc
        )

    return content


def generate_stubs(project_root: Path, dry_run: bool = True) -> None:
    """Generate stub files for all skills missing required files."""
    skills_dir = project_root / ".claude" / "skills"
    templates_dir = skills_dir / "_templates"
    metadata_path = skills_dir / "skills_metadata.yaml"

    # Load metadata and templates
    skills = load_skills_metadata(metadata_path)
    quick_ref_template = load_template(templates_dir / "QUICK_REFERENCE_TEMPLATE.md")
    patterns_template = load_template(templates_dir / "PATTERNS_TEMPLATE.md")

    created_files = []
    skipped_files = []

    for skill in skills:
        skill_name = skill.get("name")
        skill_desc = skill.get("description", "")

        if not skill_name:
            continue

        skill_dir = skills_dir / skill_name
        if not skill_dir.exists():
            print(f"⚠️  Skill directory not found: {skill_name} (skipping)")
            continue

        # Check for missing files
        quick_ref_path = skill_dir / "QUICK_REFERENCE.md"
        patterns_path = skill_dir / "PATTERNS.md"

        # Generate QUICK_REFERENCE.md if missing
        if not quick_ref_path.exists():
            content = customize_template(quick_ref_template, skill_name, skill_desc)
            file_path = str(quick_ref_path.relative_to(project_root))

            if not dry_run:
                quick_ref_path.write_text(content, encoding="utf-8")
                created_files.append(file_path)
            else:
                print(f"Would create: {file_path}")
                created_files.append(file_path)  # Count in dry run too
        else:
            skipped_files.append(str(quick_ref_path.relative_to(project_root)))

        # Generate PATTERNS.md if missing
        if not patterns_path.exists():
            content = customize_template(patterns_template, skill_name, skill_desc)
            file_path = str(patterns_path.relative_to(project_root))

            if not dry_run:
                patterns_path.write_text(content, encoding="utf-8")
                created_files.append(file_path)
            else:
                print(f"Would create: {file_path}")
                created_files.append(file_path)  # Count in dry run too
        else:
            skipped_files.append(str(patterns_path.relative_to(project_root)))

    # Print summary
    print()
    print("=" * 60)
    if dry_run:
        print("DRY RUN SUMMARY")
        print("=" * 60)
        print(f"Would create {len(created_files)} file(s)")
        print(f"Would skip {len(skipped_files)} existing file(s)")
        print()
        print("Run with --apply to actually create files")
    else:
        print("GENERATION SUMMARY")
        print("=" * 60)
        print(f"Created {len(created_files)} file(s)")
        print(f"Skipped {len(skipped_files)} existing file(s)")
        print()
        if created_files:
            print("Created files:")
            for f in created_files:
                print(f"  ✅ {f}")
    print("=" * 60)


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--apply" not in args

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    if dry_run:
        print("Running in DRY RUN mode...")
        print()

    generate_stubs(project_root, dry_run=dry_run)


if __name__ == "__main__":
    main()
