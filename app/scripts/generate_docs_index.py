#!/usr/bin/env python3
"""
Generate docs/INDEX.md - a central index of all documentation files.

Usage:
    python scripts/generate_docs_index.py           # Generate index
    python scripts/generate_docs_index.py --json    # Output JSON metadata

Features:
- Lists all markdown files organized by category
- Extracts title from frontmatter or first heading
- Shows last updated date
- Generates category-based navigation
"""

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.utils.frontmatter import parse_frontmatter


@dataclass
class DocMeta:
    """Metadata for a documentation file."""

    path: str
    title: str
    category: str
    updated: str
    status: str
    tags: list[str]
    size_lines: int


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from content."""
    return parse_frontmatter(content)[0]


def extract_title_from_content(content: str, filename: str) -> str:
    """Extract title from first heading or filename."""
    # Try first H1 heading
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Fall back to filename
    title = filename.replace(".md", "").replace("_", " ").replace("-", " ")
    return title.title()


def get_doc_metadata(filepath: Path, docs_dir: Path) -> DocMeta:
    """Extract metadata from a documentation file."""
    content = filepath.read_text(encoding="utf-8")
    rel_path = filepath.relative_to(docs_dir)

    # Get frontmatter
    fm = extract_frontmatter(content)

    # Extract or infer values
    title = fm.get("title") or extract_title_from_content(content, filepath.name)
    updated = fm.get("updated") or datetime.fromtimestamp(filepath.stat().st_mtime).strftime(
        "%Y-%m-%d"
    )
    status = fm.get("status", "current")
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    # Infer category from path
    parts = rel_path.parts
    if len(parts) > 1:
        category = parts[0]
    else:
        category = "top-level"

    # Count lines
    size_lines = len(content.split("\n"))

    return DocMeta(
        path=str(rel_path),
        title=title,
        category=category,
        updated=updated,
        status=status,
        tags=tags,
        size_lines=size_lines,
    )


def find_docs(docs_dir: Path) -> list[DocMeta]:
    """Find all markdown files and extract metadata."""
    docs = []
    for filepath in docs_dir.rglob("*.md"):
        # Skip INDEX.md itself
        if filepath.name == "INDEX.md":
            continue
        try:
            meta = get_doc_metadata(filepath, docs_dir)
            docs.append(meta)
        except Exception as e:
            print(f"Warning: Failed to process {filepath}: {e}", file=sys.stderr)

    def get_doc_sort_key(doc: DocMeta) -> tuple[str, str]:
        return (doc.category, doc.title)

    return sorted(docs, key=get_doc_sort_key)


def generate_index_markdown(docs: list[DocMeta]) -> str:
    """Generate INDEX.md content."""
    lines = [
        "---",
        "title: Documentation Index",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "status: current",
        "category: index",
        "tags: [index, navigation, documentation]",
        "related: []",
        "---",
        "",
        "# SKUEL Documentation Index",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Total: {len(docs)} documents*",
        "",
        "## Quick Links",
        "",
        "- [Architecture](#architecture) - System design and domain structure",
        "- [Patterns](#patterns) - Implementation patterns and coding standards",
        "- [DSL](#dsl) - Activity DSL specification and usage",
        "- [Decisions](#decisions) - Architecture Decision Records",
        "- [Guides](#guides) - Step-by-step implementation guides",
        "- [Reference](#reference) - Templates and checklists",
        "",
        "---",
        "",
    ]

    # Group by category
    categories = {}
    for doc in docs:
        cat = doc.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(doc)

    # Category descriptions
    cat_descriptions = {
        "architecture": "System architecture, domain structure, and design decisions",
        "patterns": "Implementation patterns, coding standards, and best practices",
        "dsl": "Activity DSL grammar, usage, and implementation",
        "decisions": "Architecture Decision Records (ADRs)",
        "guides": "Step-by-step implementation and migration guides",
        "reference": "Templates, checklists, and reference materials",
        "intelligence": "AI features, roadmaps, and vision documents",
        "migrations": "Database and code migration guides",
        "technical_debt": "Known limitations and technical debt",
        "archive": "Archived and deprecated documentation",
        "top-level": "Top-level documentation files",
    }

    # Order categories
    category_order = [
        "architecture",
        "patterns",
        "dsl",
        "decisions",
        "guides",
        "reference",
        "intelligence",
        "migrations",
        "technical_debt",
        "archive",
        "top-level",
    ]

    for cat in category_order:
        if cat not in categories:
            continue

        cat_docs = categories[cat]
        cat_title = cat.replace("_", " ").title()
        cat_desc = cat_descriptions.get(cat, "")

        lines.append(f"## {cat_title}")
        lines.append("")
        if cat_desc:
            lines.append(f"*{cat_desc}*")
            lines.append("")

        lines.append("| Document | Updated | Lines |")
        lines.append("|----------|---------|-------|")

        for doc in cat_docs:
            status_icon = ""
            if doc.status == "archived":
                status_icon = " (archived)"
            elif doc.status == "draft":
                status_icon = " (draft)"

            title_display = doc.title[:50] + "..." if len(doc.title) > 50 else doc.title
            lines.append(
                f"| [{title_display}]({doc.path}){status_icon} | {doc.updated} | {doc.size_lines} |"
            )

        lines.append("")

    # Add remaining categories
    remaining = set(categories.keys()) - set(category_order)
    for cat in sorted(remaining):
        cat_docs = categories[cat]
        cat_title = cat.replace("_", " ").title()

        lines.append(f"## {cat_title}")
        lines.append("")
        lines.append("| Document | Updated | Lines |")
        lines.append("|----------|---------|-------|")

        for doc in cat_docs:
            title_display = doc.title[:50] + "..." if len(doc.title) > 50 else doc.title
            lines.append(f"| [{title_display}]({doc.path}) | {doc.updated} | {doc.size_lines} |")

        lines.append("")

    # Statistics
    lines.append("---")
    lines.append("")
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- **Total documents:** {len(docs)}")
    lines.append(f"- **Total lines:** {sum(d.size_lines for d in docs):,}")
    lines.append(f"- **Categories:** {len(categories)}")
    lines.append("")

    # By status
    status_counts = {}
    for doc in docs:
        status_counts[doc.status] = status_counts.get(doc.status, 0) + 1

    lines.append("**By status:**")
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")

    return "\n".join(lines)


def main():
    output_json = "--json" in sys.argv

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Find and process docs
    docs = find_docs(docs_dir)

    if output_json:
        # Output JSON metadata
        print(json.dumps([asdict(d) for d in docs], indent=2))
    else:
        # Generate and write INDEX.md
        content = generate_index_markdown(docs)
        index_path = docs_dir / "INDEX.md"
        index_path.write_text(content, encoding="utf-8")
        print(f"Generated {index_path}")
        print(f"Indexed {len(docs)} documents")


if __name__ == "__main__":
    main()
