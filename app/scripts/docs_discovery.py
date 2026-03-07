#!/usr/bin/env python3
"""
Documentation Discovery & Analysis Tool

Features:
- Extracts YAML frontmatter from all docs
- Generates machine-readable index (JSON/YAML)
- Detects stale docs (>90 days since update)
- Validates cross-references
- Checks for broken internal links
- Reports documentation health metrics

Usage:
    python scripts/docs_discovery.py                    # Full report
    python scripts/docs_discovery.py --json             # JSON output
    python scripts/docs_discovery.py --stale            # Only stale docs
    python scripts/docs_discovery.py --broken-links     # Only broken links
    python scripts/docs_discovery.py --dashboard        # Status dashboard
"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.utils.frontmatter import parse_frontmatter


@dataclass
class DocMetadata:
    """Complete metadata for a documentation file."""

    path: str
    title: str
    category: str
    updated: str
    status: str
    tags: list[str]
    related: list[str]
    size_lines: int
    size_bytes: int

    # Analysis fields
    days_since_update: int = 0
    is_stale: bool = False
    internal_links: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)
    has_frontmatter: bool = True
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class DocsReport:
    """Complete documentation analysis report."""

    generated_at: str
    total_docs: int
    total_lines: int
    total_bytes: int

    # By status
    by_status: dict[str, int] = field(default_factory=dict)

    # By category
    by_category: dict[str, int] = field(default_factory=dict)

    # Health metrics
    stale_count: int = 0
    missing_frontmatter: int = 0
    broken_link_count: int = 0

    # Document list
    documents: list[DocMetadata] = field(default_factory=list)

    # Problem lists
    stale_docs: list[str] = field(default_factory=list)
    docs_with_broken_links: list[dict] = field(default_factory=list)
    docs_missing_frontmatter: list[str] = field(default_factory=list)


def extract_frontmatter(content: str) -> tuple[dict, bool]:
    """Extract YAML frontmatter from content. Returns (data, has_frontmatter)."""
    result = parse_frontmatter(content)[0]
    return result, bool(result)


def extract_internal_links(content: str) -> list[str]:
    """Extract internal markdown links from content."""
    # Match [text](path) where path doesn't start with http
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    links = []

    for match in re.finditer(pattern, content):
        path = match.group(2)
        # Skip external links and anchors
        if not path.startswith(("http://", "https://", "#", "mailto:")):
            links.append(path)

    return links


def check_link_exists(link: str, doc_path: Path, docs_dir: Path) -> bool:
    """Check if an internal link target exists."""
    # Handle relative paths
    if link.startswith("/"):
        # Absolute from project root
        target = docs_dir.parent / link.lstrip("/")
    else:
        # Relative to current doc
        target = doc_path.parent / link

    # Remove anchor if present
    target_str = str(target).split("#")[0]
    target = Path(target_str)

    return target.exists()


def parse_date(date_str: str) -> datetime | None:
    """Parse date string to datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def analyze_doc(filepath: Path, docs_dir: Path, all_docs: set[str]) -> DocMetadata:
    """Analyze a single documentation file."""
    content = filepath.read_text(encoding="utf-8")
    rel_path = str(filepath.relative_to(docs_dir))

    # Get frontmatter
    fm, has_fm = extract_frontmatter(content)

    # Extract or infer values
    title = fm.get("title", filepath.stem.replace("_", " ").title())
    updated_str = fm.get("updated", "")
    status = fm.get("status", "unknown")
    tags = fm.get("tags", [])
    related = fm.get("related", [])

    if isinstance(tags, str):
        tags = [tags]
    if isinstance(related, str):
        related = [related]

    # Infer category from path
    parts = filepath.relative_to(docs_dir).parts
    category = parts[0] if len(parts) > 1 else "top-level"

    # Calculate staleness
    updated_date = parse_date(updated_str)
    if updated_date:
        days_since = (datetime.now() - updated_date).days
    else:
        # Use file modification time
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        days_since = (datetime.now() - mtime).days
        updated_str = mtime.strftime("%Y-%m-%d")

    is_stale = days_since > 90

    # Check internal links
    internal_links = extract_internal_links(content)
    broken_links = []
    for link in internal_links:
        if not check_link_exists(link, filepath, docs_dir):
            broken_links.append(link)

    # Check missing frontmatter fields
    required_fields = ["title", "updated", "status", "category", "tags"]
    missing_fields = [f for f in required_fields if f not in fm]

    return DocMetadata(
        path=rel_path,
        title=title,
        category=category,
        updated=updated_str,
        status=status,
        tags=tags,
        related=related,
        size_lines=len(content.split("\n")),
        size_bytes=len(content.encode("utf-8")),
        days_since_update=days_since,
        is_stale=is_stale,
        internal_links=internal_links,
        broken_links=broken_links,
        has_frontmatter=has_fm,
        missing_fields=missing_fields,
    )


def analyze_docs(docs_dir: Path) -> DocsReport:
    """Analyze all documentation files."""
    # Find all docs
    doc_files = list(docs_dir.rglob("*.md"))
    all_doc_paths = {str(f.relative_to(docs_dir)) for f in doc_files}

    documents = []
    for filepath in sorted(doc_files):
        try:
            doc = analyze_doc(filepath, docs_dir, all_doc_paths)
            documents.append(doc)
        except Exception as e:
            print(f"Warning: Failed to analyze {filepath}: {e}", file=sys.stderr)

    # Build report
    report = DocsReport(
        generated_at=datetime.now().isoformat(),
        total_docs=len(documents),
        total_lines=sum(d.size_lines for d in documents),
        total_bytes=sum(d.size_bytes for d in documents),
        documents=documents,
    )

    # Aggregate stats
    for doc in documents:
        # By status
        report.by_status[doc.status] = report.by_status.get(doc.status, 0) + 1

        # By category
        report.by_category[doc.category] = report.by_category.get(doc.category, 0) + 1

        # Stale docs
        if doc.is_stale:
            report.stale_count += 1
            report.stale_docs.append(doc.path)

        # Missing frontmatter
        if not doc.has_frontmatter:
            report.missing_frontmatter += 1
            report.docs_missing_frontmatter.append(doc.path)

        # Broken links
        if doc.broken_links:
            report.broken_link_count += len(doc.broken_links)
            report.docs_with_broken_links.append(
                {"path": doc.path, "broken_links": doc.broken_links}
            )

    return report


def print_dashboard(report: DocsReport):
    """Print a human-readable dashboard."""
    print("=" * 60)
    print("SKUEL Documentation Health Dashboard")
    print(f"Generated: {report.generated_at}")
    print("=" * 60)
    print()

    # Summary
    print("## Summary")
    print(f"  Total documents: {report.total_docs}")
    print(f"  Total lines: {report.total_lines:,}")
    print(f"  Total size: {report.total_bytes / 1024:.1f} KB")
    print()

    # Health Score
    health_issues = report.stale_count + report.missing_frontmatter + report.broken_link_count
    health_score = max(0, 100 - (health_issues * 2))
    print(f"## Health Score: {health_score}/100")
    print(f"  - Stale docs (>90 days): {report.stale_count}")
    print(f"  - Missing frontmatter: {report.missing_frontmatter}")
    print(f"  - Broken links: {report.broken_link_count}")
    print()

    # By Status
    print("## By Status")
    for status, count in sorted(report.by_status.items()):
        print(f"  {status}: {count}")
    print()

    # By Category
    print("## By Category")

    def get_category_count_desc(item: tuple[str, int]) -> int:
        return -item[1]

    for category, count in sorted(report.by_category.items(), key=get_category_count_desc):
        print(f"  {category}: {count}")
    print()

    # Stale Docs
    if report.stale_docs:
        print("## Stale Documents (>90 days)")
        for path in report.stale_docs[:10]:
            doc = next(d for d in report.documents if d.path == path)
            print(f"  - {path} ({doc.days_since_update} days)")
        if len(report.stale_docs) > 10:
            print(f"  ... and {len(report.stale_docs) - 10} more")
        print()

    # Broken Links
    if report.docs_with_broken_links:
        print("## Broken Links")
        for item in report.docs_with_broken_links[:5]:
            print(f"  {item['path']}:")
            for link in item["broken_links"][:3]:
                print(f"    - {link}")
            if len(item["broken_links"]) > 3:
                print(f"    ... and {len(item['broken_links']) - 3} more")
        if len(report.docs_with_broken_links) > 5:
            print(f"  ... and {len(report.docs_with_broken_links) - 5} more files")
        print()

    print("=" * 60)


def main():
    args = sys.argv[1:]

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Analyze docs
    report = analyze_docs(docs_dir)

    # Output based on flags
    if "--json" in args:
        # Full JSON output
        output = asdict(report)
        print(json.dumps(output, indent=2, default=str))

    elif "--stale" in args:
        # Only stale docs
        print("Stale Documents (>90 days since update):")
        print("-" * 40)
        for doc in report.documents:
            if doc.is_stale:
                print(f"{doc.path}")
                print(f"  Last updated: {doc.updated} ({doc.days_since_update} days ago)")
        print(f"\nTotal: {report.stale_count} stale documents")

    elif "--broken-links" in args:
        # Only broken links
        print("Broken Internal Links:")
        print("-" * 40)
        for item in report.docs_with_broken_links:
            print(f"\n{item['path']}:")
            for link in item["broken_links"]:
                print(f"  - {link}")
        print(
            f"\nTotal: {report.broken_link_count} broken links in {len(report.docs_with_broken_links)} files"
        )

    elif "--dashboard" in args or len(args) == 0:
        # Dashboard view (default)
        print_dashboard(report)

    else:
        print("Usage: python scripts/docs_discovery.py [--json|--stale|--broken-links|--dashboard]")
        sys.exit(1)


if __name__ == "__main__":
    main()
