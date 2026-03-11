#!/usr/bin/env python3
"""
Auto-Generate Cross-Reference Sections

Automatically generates "Related Skills" sections in docs based on frontmatter metadata.

Features:
1. Reads related_skills from frontmatter
2. Generates standardized markdown section
3. Inserts at appropriate location (after title/overview)
4. Preserves manual customizations (won't overwrite Quick Start sections)

Usage:
    # Dry run (no changes)
    uv run python scripts/sync_cross_references.py --dry-run

    # Apply to specific file
    uv run python scripts/sync_cross_references.py docs/patterns/ERROR_HANDLING.md

    # Apply to all pattern docs
    uv run python scripts/sync_cross_references.py --category patterns

    # Apply to all docs (patterns + architecture + ADRs)
    uv run python scripts/sync_cross_references.py --all
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.utils.frontmatter import split_frontmatter


@dataclass
class DocUpdate:
    """Represents a document update."""

    file_path: Path
    original_content: str
    new_content: str
    has_changes: bool
    status: str  # "updated" | "skipped" | "error"
    message: str


def extract_frontmatter(content: str) -> tuple[dict[str, Any] | None, str, str]:
    """
    Extract YAML frontmatter and body from markdown content.

    Returns: (frontmatter dict, frontmatter text, body)
    """
    raw, body = split_frontmatter(content)
    if raw is None:
        return None, "", content

    try:
        frontmatter = yaml.safe_load(raw)
        return frontmatter, raw, body
    except yaml.YAMLError:
        return None, "", content


def has_quick_start_section(body: str) -> bool:
    """Check if document has a Quick Start section."""
    return bool(re.search(r"^##\s+Quick Start", body, re.MULTILINE))


def has_related_skills_section(body: str) -> bool:
    """Check if document has a Related Skills section."""
    return bool(re.search(r"^##\s+Related Skills", body, re.MULTILINE))


def generate_related_skills_section(skills: list[str]) -> str:
    """
    Generate standardized Related Skills markdown section.

    Format:
    ## Related Skills

    For implementation guidance, see:
    - [@skill-name](../../.claude/skills/skill-name/SKILL.md) - Description
    - [@skill-name-2](../../.claude/skills/skill-name-2/SKILL.md) - Description
    """
    if not skills:
        return ""

    lines = ["## Related Skills", ""]
    lines.append("For implementation guidance, see:")

    for skill in sorted(skills):
        # Build relative path (assumes doc is in /docs/{category}/)
        skill_path = f"../../.claude/skills/{skill}/SKILL.md"
        lines.append(f"- [@{skill}]({skill_path})")

    lines.append("")
    return "\n".join(lines)


def find_insertion_point(body: str) -> int:
    """
    Find the best location to insert Related Skills section.

    Strategy:
    1. After first heading (title) + any intro paragraph
    2. Before "Quick Start" if it exists
    3. Before "Core Principle" if it exists
    4. Before second ## heading if no special sections
    5. At start if no headings found
    """
    lines = body.split("\n")

    # Find first # heading (title)
    title_idx = None
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title_idx = i
            break

    if title_idx is None:
        # No title found, insert at start
        return 0

    # Look for Quick Start, Core Principle, or second ## heading
    for i in range(title_idx + 1, len(lines)):
        line = lines[i].strip()

        # Found Quick Start or Core Principle - insert before it
        if line.startswith("## Quick Start") or line.startswith("## Core Principle"):
            # Skip back over any blank lines
            insert_idx = i
            while insert_idx > 0 and not lines[insert_idx - 1].strip():
                insert_idx -= 1
            return sum(len(lines[j]) + 1 for j in range(insert_idx))  # +1 for newline

        # Found second ## heading - insert before it
        if line.startswith("## ") and i > title_idx + 1:
            # Skip back over any blank lines
            insert_idx = i
            while insert_idx > 0 and not lines[insert_idx - 1].strip():
                insert_idx -= 1
            return sum(len(lines[j]) + 1 for j in range(insert_idx))

    # No special sections found, insert after title + blank line
    # Skip title and any immediate content (like status, last updated, etc.)
    insert_idx = title_idx + 1

    # Skip status lines, last updated, etc.
    while insert_idx < len(lines):
        line = lines[insert_idx].strip()
        if not line or line.startswith("**") or line.startswith("*Last updated"):
            insert_idx += 1
        else:
            break

    # Add a blank line before the section
    return sum(len(lines[j]) + 1 for j in range(insert_idx))


def sync_doc_cross_references(file_path: Path, dry_run: bool = True) -> DocUpdate:
    """
    Sync cross-references for a single document.

    Returns: DocUpdate with status and changes
    """
    original_content = file_path.read_text()
    frontmatter, frontmatter_text, body = extract_frontmatter(original_content)

    # Skip if no frontmatter
    if frontmatter is None:
        return DocUpdate(
            file_path=file_path,
            original_content=original_content,
            new_content=original_content,
            has_changes=False,
            status="skipped",
            message="No frontmatter found",
        )

    # Get related skills from frontmatter
    related_skills = frontmatter.get("related_skills", [])
    if not related_skills:
        return DocUpdate(
            file_path=file_path,
            original_content=original_content,
            new_content=original_content,
            has_changes=False,
            status="skipped",
            message="No related_skills in frontmatter",
        )

    # Skip if doc has Quick Start (assume it's manually curated)
    if has_quick_start_section(body):
        return DocUpdate(
            file_path=file_path,
            original_content=original_content,
            new_content=original_content,
            has_changes=False,
            status="skipped",
            message="Has Quick Start section (manual)",
        )

    # Check if Related Skills section already exists
    if has_related_skills_section(body):
        # TODO(deferred): Could update existing section in future
        return DocUpdate(
            file_path=file_path,
            original_content=original_content,
            new_content=original_content,
            has_changes=False,
            status="skipped",
            message="Already has Related Skills section",
        )

    # Generate Related Skills section
    skills_section = generate_related_skills_section(related_skills)

    # Find insertion point
    insert_pos = find_insertion_point(body)

    # Insert section
    new_body = body[:insert_pos] + skills_section + "\n" + body[insert_pos:]
    new_content = f"---\n{frontmatter_text}\n---\n{new_body}"

    # Write if not dry-run
    if not dry_run:
        file_path.write_text(new_content)

    return DocUpdate(
        file_path=file_path,
        original_content=original_content,
        new_content=new_content,
        has_changes=True,
        status="updated",
        message=f"Added Related Skills section ({len(related_skills)} skills)",
    )


def get_docs_to_process(base_path: Path, category: str | None, file_path: str | None) -> list[Path]:
    """
    Get list of documents to process based on arguments.

    Args:
        category: "patterns", "architecture", "decisions", or None for all
        file_path: Specific file to process, or None
    """
    if file_path:
        # Process single file
        doc_path = base_path / file_path
        if not doc_path.exists():
            print(f"❌ File not found: {file_path}")
            return []
        return [doc_path]

    # Process by category
    docs = []

    if category in ("patterns", None):
        patterns_dir = base_path / "docs" / "patterns"
        docs.extend(patterns_dir.glob("*.md"))

    if category in ("architecture", None):
        arch_dir = base_path / "docs" / "architecture"
        docs.extend(arch_dir.glob("*.md"))

    if category in ("decisions", None):
        decisions_dir = base_path / "docs" / "decisions"
        docs.extend(decisions_dir.glob("ADR-*.md"))

    if category in ("intelligence", None):
        intel_dir = base_path / "docs" / "intelligence"
        if intel_dir.exists():
            docs.extend(intel_dir.glob("*.md"))

    return sorted(docs)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Auto-generate Related Skills sections in documentation"
    )
    parser.add_argument("file", nargs="?", help="Specific file to process")
    parser.add_argument(
        "--category",
        choices=["patterns", "architecture", "decisions", "intelligence"],
        help="Process all docs in category",
    )
    parser.add_argument(
        "--all", action="store_true", help="Process all docs (patterns + architecture + ADRs)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    args = parser.parse_args()

    base_path = Path(__file__).parent.parent

    # Determine what to process
    if args.all:
        category = None
        file_path = None
    elif args.file:
        category = None
        file_path = args.file
    elif args.category:
        category = args.category
        file_path = None
    else:
        print("❌ Must specify --file, --category, or --all")
        parser.print_help()
        exit(1)

    docs = get_docs_to_process(base_path, category, file_path)

    if not docs:
        print("No documents to process")
        exit(0)

    print(f"{'DRY RUN - ' if args.dry_run else ''}Processing {len(docs)} documents...\n")

    # Process each doc
    updates = []
    for doc_path in docs:
        update = sync_doc_cross_references(doc_path, dry_run=args.dry_run)
        updates.append(update)

        # Print status
        if update.status == "updated":
            symbol = "✓"
        elif update.status == "skipped":
            symbol = "○"
        else:
            symbol = "✗"

        print(f"{symbol} {doc_path.relative_to(base_path)} - {update.message}")

    # Summary
    updated = [u for u in updates if u.status == "updated"]
    skipped = [u for u in updates if u.status == "skipped"]
    errors = [u for u in updates if u.status == "error"]

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Total docs: {len(docs)}")
    print(f"  Updated: {len(updated)}")
    print(f"  Skipped: {len(skipped)}")
    print(f"  Errors: {len(errors)}")

    if args.dry_run:
        print("\n✓ Dry run complete - no files modified")
        print("  Run without --dry-run to apply changes")
    elif updated:
        print(f"\n✅ Successfully updated {len(updated)} document(s)!")
    else:
        print("\nℹ️  No documents needed updates")


if __name__ == "__main__":
    main()
