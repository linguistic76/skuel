#!/usr/bin/env python3
"""
Add YAML frontmatter to all markdown documentation files.

Usage:
    python scripts/add_frontmatter.py           # Preview changes
    python scripts/add_frontmatter.py --apply   # Apply changes

Features:
- Detects existing frontmatter and skips files that have it
- Extracts title from first heading or filename
- Sets updated date from file modification time
- Infers category from directory path
- Generates initial tags from filename
"""

import re
import sys
from datetime import datetime
from pathlib import Path


def has_frontmatter(content: str) -> bool:
    """Check if content already has YAML frontmatter."""
    return content.startswith("---\n")


def extract_title(content: str, filename: str) -> str:
    """Extract title from first heading or generate from filename."""
    # Try to find first H1 heading
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Fall back to filename
    title = filename.replace(".md", "").replace("_", " ").replace("-", " ")
    # Capitalize words but keep acronyms
    words = title.split()
    capitalized = []
    for word in words:
        if word.isupper():
            capitalized.append(word)
        else:
            capitalized.append(word.capitalize())
    return " ".join(capitalized)


def infer_category(filepath: Path) -> str:
    """Infer category from directory structure."""
    parts = filepath.parts

    # Find docs directory and get relative path
    if "docs" in parts:
        idx = parts.index("docs")
        if len(parts) > idx + 1:
            subdir = parts[idx + 1]
            category_map = {
                "patterns": "patterns",
                "architecture": "architecture",
                "decisions": "decisions",
                "dsl": "dsl",
                "guides": "guides",
                "intelligence": "intelligence",
                "reference": "reference",
                "migrations": "migrations",
                "technical_debt": "technical-debt",
                "archive": "archive",
            }
            return category_map.get(subdir, "general")

    return "general"


def generate_tags(filepath: Path, title: str) -> list[str]:
    """Generate initial tags from filename and title."""
    tags = set()

    # From filename
    filename = filepath.stem.lower()
    for word in re.split(r"[_\-\s]+", filename):
        if len(word) > 2 and word not in ["the", "and", "for", "with"]:
            tags.add(word)

    # From category
    category = infer_category(filepath)
    if category != "general":
        tags.add(category)

    return sorted(list(tags))[:5]  # Limit to 5 tags


def infer_status(filepath: Path) -> str:
    """Infer document status from path and content."""
    filename = filepath.stem.lower()

    if "archive" in str(filepath):
        return "archived"
    if "draft" in filename or "wip" in filename:
        return "draft"
    if "deprecated" in filename:
        return "archived"

    return "current"


def create_frontmatter(filepath: Path, content: str) -> str:
    """Create YAML frontmatter for a document."""
    title = extract_title(content, filepath.name)
    updated = datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d")
    status = infer_status(filepath)
    category = infer_category(filepath)
    tags = generate_tags(filepath, title)

    frontmatter = f"""---
title: {title}
updated: {updated}
status: {status}
category: {category}
tags: [{", ".join(tags)}]
related: []
---

"""
    return frontmatter


def process_file(filepath: Path, apply: bool = False) -> dict:
    """Process a single markdown file."""
    result = {
        "path": str(filepath),
        "action": None,
        "title": None,
        "error": None,
    }

    try:
        content = filepath.read_text(encoding="utf-8")

        if has_frontmatter(content):
            result["action"] = "skipped"
            result["title"] = "(has frontmatter)"
            return result

        frontmatter = create_frontmatter(filepath, content)
        new_content = frontmatter + content

        # Extract title for reporting
        title_match = re.search(r"^title:\s*(.+)$", frontmatter, re.MULTILINE)
        result["title"] = title_match.group(1) if title_match else "?"

        if apply:
            filepath.write_text(new_content, encoding="utf-8")
            result["action"] = "updated"
        else:
            result["action"] = "preview"

    except Exception as e:
        result["action"] = "error"
        result["error"] = str(e)

    return result


def find_markdown_files(docs_dir: Path) -> list[Path]:
    """Find all markdown files in docs directory."""
    files = []
    for path in docs_dir.rglob("*.md"):
        # Skip archive directory for preview, but include in apply
        files.append(path)
    return sorted(files)


def main():
    apply = "--apply" in sys.argv

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}")
        sys.exit(1)

    print(f"{'APPLYING' if apply else 'PREVIEWING'} frontmatter changes")
    print(f"Docs directory: {docs_dir}")
    print("-" * 60)

    files = find_markdown_files(docs_dir)
    print(f"Found {len(files)} markdown files\n")

    stats = {"updated": 0, "skipped": 0, "error": 0, "preview": 0}

    for filepath in files:
        result = process_file(filepath, apply)
        stats[result["action"]] += 1

        # Format output
        rel_path = filepath.relative_to(docs_dir)
        action_symbol = {
            "updated": "+",
            "skipped": ".",
            "preview": "?",
            "error": "!",
        }[result["action"]]

        if result["action"] == "error":
            print(f"  {action_symbol} {rel_path}: ERROR - {result['error']}")
        elif result["action"] != "skipped":
            print(f"  {action_symbol} {rel_path}: {result['title']}")

    print("-" * 60)
    print("Summary:")
    print(f"  {'Updated' if apply else 'Would update'}: {stats['updated'] + stats['preview']}")
    print(f"  Skipped (has frontmatter): {stats['skipped']}")
    print(f"  Errors: {stats['error']}")

    if not apply and (stats["preview"] > 0):
        print("\nRun with --apply to make changes")


if __name__ == "__main__":
    main()
