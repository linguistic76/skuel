#!/usr/bin/env python3
"""
Generate CLAUDE.md section summaries from detailed documentation.

This script reads detailed docs with frontmatter and generates
summary sections with **See:** pointers for CLAUDE.md.

Usage:
    python scripts/generate_claude_summary.py                    # Preview summaries
    python scripts/generate_claude_summary.py --output FILE      # Write to file
    python scripts/generate_claude_summary.py --category NAME    # Specific category

Features:
- Extracts title and first paragraph from each doc
- Groups by category
- Generates **See:** pointers
- Maintains CLAUDE.md format
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from core.utils.frontmatter import parse_frontmatter


@dataclass
class DocSummary:
    """Summary of a documentation file."""

    path: str
    title: str
    category: str
    summary: str
    tags: list[str]
    updated: str


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from content."""
    return parse_frontmatter(content)[0]


def extract_first_paragraph(content: str) -> str:
    """Extract first meaningful paragraph after frontmatter and title."""
    # Remove frontmatter
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            content = content[end_idx + 5 :]

    lines = content.strip().split("\n")

    # Skip title and empty lines
    paragraph_lines = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()

        # Skip headings
        if stripped.startswith("#"):
            if in_paragraph:
                break
            continue

        # Skip empty lines before paragraph
        if not stripped:
            if in_paragraph:
                break
            continue

        # Skip metadata-like lines
        if stripped.startswith("*") and stripped.endswith("*"):
            continue

        # Skip code blocks
        if stripped.startswith("```"):
            if in_paragraph:
                break
            continue

        # Found paragraph content
        in_paragraph = True
        paragraph_lines.append(stripped)

        # Limit length
        if len(" ".join(paragraph_lines)) > 200:
            break

    summary = " ".join(paragraph_lines)

    # Truncate if too long
    if len(summary) > 200:
        summary = summary[:197] + "..."

    return summary


def get_doc_summary(filepath: Path, docs_dir: Path) -> DocSummary | None:
    """Get summary for a documentation file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        rel_path = filepath.relative_to(docs_dir)

        # Skip INDEX.md
        if filepath.name == "INDEX.md":
            return None

        fm = extract_frontmatter(content)

        # Get metadata
        title = fm.get("title", filepath.stem.replace("_", " ").title())
        category = fm.get("category", "general")
        tags = fm.get("tags", [])
        updated = fm.get("updated", "unknown")

        if isinstance(tags, str):
            tags = [tags]

        # Get summary
        summary = extract_first_paragraph(content)

        return DocSummary(
            path=str(rel_path),
            title=title,
            category=category,
            summary=summary,
            tags=tags,
            updated=updated,
        )
    except Exception as e:
        print(f"Warning: Failed to process {filepath}: {e}", file=sys.stderr)
        return None


def generate_category_section(category: str, docs: list[DocSummary]) -> str:
    """Generate a CLAUDE.md section for a category."""
    # Category display name
    display_name = category.replace("_", " ").title()

    lines = [
        f"## {display_name}",
        "",
    ]

    # Add docs as bullet points with summaries
    def get_doc_title(doc: DocSummary) -> str:
        return doc.title

    for doc in sorted(docs, key=get_doc_title):
        lines.append(f"### {doc.title}")
        if doc.summary:
            lines.append(f"{doc.summary}")
        lines.append(f"**See:** `/docs/{doc.path}`")
        lines.append("")

    return "\n".join(lines)


def generate_quick_reference(docs: list[DocSummary]) -> str:
    """Generate quick reference table."""
    lines = [
        "## Documentation Quick Reference",
        "",
        "| Category | Doc Count | Key Topics |",
        "|----------|-----------|------------|",
    ]

    # Group by category
    by_category = {}
    for doc in docs:
        if doc.category not in by_category:
            by_category[doc.category] = []
        by_category[doc.category].append(doc)

    for category in sorted(by_category.keys()):
        cat_docs = by_category[category]
        # Collect unique tags
        all_tags = set()
        for doc in cat_docs:
            all_tags.update(doc.tags[:2])  # First 2 tags per doc
        tags_str = ", ".join(sorted(all_tags)[:4])  # Max 4 tags
        lines.append(f"| {category} | {len(cat_docs)} | {tags_str} |")

    lines.append("")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Filter by category if specified
    filter_category = None
    if "--category" in args:
        idx = args.index("--category")
        if idx + 1 < len(args):
            filter_category = args[idx + 1]

    # Output file
    output_file = None
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_file = Path(args[idx + 1])

    # Collect docs
    docs = []
    for filepath in docs_dir.rglob("*.md"):
        # Skip archived docs
        if "archive" in str(filepath):
            continue

        summary = get_doc_summary(filepath, docs_dir)
        if summary:
            if filter_category and summary.category != filter_category:
                continue
            docs.append(summary)

    # Group by category
    by_category = {}
    for doc in docs:
        if doc.category not in by_category:
            by_category[doc.category] = []
        by_category[doc.category].append(doc)

    # Generate output
    output_lines = [
        "# SKUEL Documentation Summaries",
        "",
        f"*Auto-generated from {len(docs)} documentation files*",
        "",
        "---",
        "",
    ]

    # Quick reference table
    output_lines.append(generate_quick_reference(docs))
    output_lines.append("---\n")

    # Priority categories first
    priority_order = ["architecture", "patterns", "dsl", "guides", "reference", "decisions"]

    for category in priority_order:
        if category in by_category:
            output_lines.append(generate_category_section(category, by_category[category]))

    # Remaining categories
    for category in sorted(by_category.keys()):
        if category not in priority_order:
            output_lines.append(generate_category_section(category, by_category[category]))

    output = "\n".join(output_lines)

    # Output
    if output_file:
        output_file.write_text(output, encoding="utf-8")
        print(f"Generated {output_file}")
        print(f"Summarized {len(docs)} documents in {len(by_category)} categories")
    else:
        print(output)


if __name__ == "__main__":
    main()
