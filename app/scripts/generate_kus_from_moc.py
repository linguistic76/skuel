#!/usr/bin/env python3
"""
Generate KU Files from MOC Headings
====================================

Parses the Worldview MOC and generates KU markdown files in the
Obsidian vault for each heading (H3-H6).

Usage:
    poetry run python scripts/generate_kus_from_moc.py
    poetry run python scripts/generate_kus_from_moc.py --dry-run
    poetry run python scripts/generate_kus_from_moc.py --section stories
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.moc_parser import (
    HeadingNode,
    MOCStructure,
    generate_ku_yaml_from_heading,
    parse_moc_file,
)

# Configuration
MOC_FILE_PATH = Path("/home/mike/0bsidian/skuel/0skg - taxonomy - short.md")
OUTPUT_BASE_PATH = Path("/home/mike/0bsidian/skuel/docs")


def generate_ku_file(
    heading: HeadingNode,
    moc: MOCStructure,
    section_slug: str,
    output_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """
    Generate a KU markdown file from a MOC heading.

    Args:
        heading: The heading node to convert
        moc: Parent MOC structure
        section_slug: Section (H2) slug this belongs to
        output_dir: Directory to write the file
        dry_run: If True, don't actually write files

    Returns:
        Path to created file, or None if skipped
    """
    # Generate YAML content
    yaml_content = generate_ku_yaml_from_heading(
        heading=heading,
        moc_uid=moc.uid,
        section_slug=section_slug,
        domain=moc.domain,
    )

    # Create filename
    filename = f"{heading.slug}.md"
    file_path = output_dir / filename

    if dry_run:
        print(f"  [DRY RUN] Would create: {file_path}")
        return file_path

    # Write file
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(yaml_content, encoding="utf-8")
    print(f"  Created: {file_path}")
    return file_path


def process_headings_recursive(
    headings: list[HeadingNode],
    moc: MOCStructure,
    section_slug: str,
    output_dir: Path,
    dry_run: bool = False,
    stats: dict | None = None,
) -> dict:
    """
    Recursively process headings and generate KU files.

    Args:
        headings: List of heading nodes to process
        moc: Parent MOC structure
        section_slug: Section (H2) slug
        output_dir: Base output directory
        dry_run: If True, don't write files
        stats: Statistics dict (modified in place)

    Returns:
        Updated statistics dict
    """
    if stats is None:
        stats = {"created": 0, "skipped": 0, "errors": 0}

    for heading in headings:
        try:
            # Generate KU file for this heading
            result = generate_ku_file(
                heading=heading,
                moc=moc,
                section_slug=section_slug,
                output_dir=output_dir,
                dry_run=dry_run,
            )

            if result:
                stats["created"] += 1
            else:
                stats["skipped"] += 1

            # Process children recursively
            if heading.children:
                process_headings_recursive(
                    headings=heading.children,
                    moc=moc,
                    section_slug=section_slug,
                    output_dir=output_dir,
                    dry_run=dry_run,
                    stats=stats,
                )

        except Exception as e:
            print(f"  ERROR: {heading.title}: {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate KU files from MOC headings")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually writing files",
    )
    parser.add_argument(
        "--section",
        type=str,
        help="Only process a specific section (by slug)",
    )
    parser.add_argument(
        "--moc-path",
        type=str,
        default=str(MOC_FILE_PATH),
        help="Path to the MOC file",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(OUTPUT_BASE_PATH),
        help="Base output directory for KU files",
    )

    args = parser.parse_args()

    # Parse MOC
    moc_path = Path(args.moc_path)
    output_base = Path(args.output_path)

    print(f"Parsing MOC: {moc_path}")
    moc = parse_moc_file(moc_path)

    print(f"MOC: {moc.title}")
    print(f"UID: {moc.uid}")
    print(f"Sections: {len(moc.sections)}")
    print(f"Total headings: {len(moc.get_all_headings())}")
    print()

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        print()

    # Process each section
    total_stats = {"created": 0, "skipped": 0, "errors": 0}

    for section in moc.sections:
        # Filter by section if specified
        if args.section and section.slug != args.section:
            continue

        print(f"Section: {section.title} ({section.slug})")

        # Output directory for this section
        section_dir = output_base / section.slug

        # Process all children of this section
        stats = process_headings_recursive(
            headings=section.children,
            moc=moc,
            section_slug=section.slug,
            output_dir=section_dir,
            dry_run=args.dry_run,
        )

        total_stats["created"] += stats["created"]
        total_stats["skipped"] += stats["skipped"]
        total_stats["errors"] += stats["errors"]

        print(f"  Section stats: {stats}")
        print()

    # Summary
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Files created: {total_stats['created']}")
    print(f"Files skipped: {total_stats['skipped']}")
    print(f"Errors: {total_stats['errors']}")

    if args.dry_run:
        print()
        print("(Dry run - no files were actually created)")


if __name__ == "__main__":
    main()
