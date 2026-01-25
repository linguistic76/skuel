#!/usr/bin/env python3
"""
Generate individual KU files from moc_nous.md.

Parses the MOC file and generates:
- Individual .md files for each heading (H2-H6)
- Individual .md files for each bullet point
- Placeholder files for Obsidian links with "tbd" content

Each file includes proper YAML frontmatter with:
- uid: ku.{filename}
- icon: (for H2 section headings)
- parent relationships (HAS_NARROWER)
- MOC membership (PART_OF_MOC)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

# Icon mapping for section headings (H2)
SECTION_ICONS: dict[str, str] = {
    "stories": "📖",
    "environment-sustainability-weather": "🌍",
    "intelligence-education": "🧠",
    "investment": "📈",
    "words-meaning": "💬",
    "relationships-communication": "🤝",
    "social-awareness": "👥",
    "body-nervous-system": "🧬",
    "exercises-sm-metrics": "🏃",
    "self-management": "⚙️",
    "who-are-u-self-awareness": "🪞",
}

# Paths
MOC_FILE = Path("/home/mike/0bsidian/skuel/nous/moc_nous.md")
OUTPUT_DIR = Path("/home/mike/0bsidian/skuel/nous")


@dataclass
class ContentItem:
    """Represents a heading, bullet point, or link to generate a file for."""

    title: str
    slug: str
    level: int  # Heading level (2-6) or bullet depth (7+)
    item_type: str  # "heading", "bullet", "link"
    content: str = ""
    parent_slug: str | None = None
    section_slug: str | None = None  # H2 section this belongs to
    icon: str = ""  # Emoji icon (primarily for H2 sections)
    children: list["ContentItem"] = field(default_factory=list)
    source_line: int = 0


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    # Remove markdown links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r"[^\w\s-]", "", text.lower())
    # Replace spaces with hyphens
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text


def extract_obsidian_links(content: str) -> list[tuple[str, str]]:
    """Extract Obsidian links from content.

    Returns list of (display_text, filename) tuples.
    """
    # Pattern for [display text](filename.md) or [display text](filename%20with%20spaces.md)
    pattern = r"\[([^\]]+)\]\(([^)]+\.md)\)"
    matches = re.findall(pattern, content)

    result = []
    for display_text, filename in matches:
        # URL-decode the filename
        decoded = unquote(filename)
        result.append((display_text, decoded))

    return result


def parse_moc_file(file_path: Path) -> tuple[dict, list[ContentItem]]:
    """Parse the MOC file and extract all content items.

    Returns:
        (frontmatter_dict, list_of_content_items)
    """
    content = file_path.read_text(encoding="utf-8")

    # Split frontmatter and body
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml

            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2]

    lines = body.split("\n")
    items: list[ContentItem] = []

    # Track current context
    current_section: ContentItem | None = None  # Current H2
    parent_stack: list[ContentItem] = []  # Stack for building hierarchy

    # Collected links to create placeholder files
    links_to_create: list[tuple[str, str]] = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        # Skip blockquotes - these are content, not separate items
        if stripped.startswith(">"):
            continue

        # Check for heading
        heading_match = re.match(r"^(#{2,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            slug = slugify(title)

            item = ContentItem(
                title=title,
                slug=slug,
                level=level,
                item_type="heading",
                source_line=line_num,
            )

            # Set section for H2 and assign icon
            if level == 2:
                current_section = item
                item.section_slug = slug
                item.icon = SECTION_ICONS.get(slug, "📄")  # Default icon
            elif current_section:
                item.section_slug = current_section.slug

            # Build parent relationship
            while parent_stack and parent_stack[-1].level >= level:
                parent_stack.pop()

            if parent_stack:
                item.parent_slug = parent_stack[-1].slug

            parent_stack.append(item)
            items.append(item)

            # Extract links from the title
            title_links = extract_obsidian_links(title)
            links_to_create.extend(title_links)
            continue

        # Check for bullet point
        bullet_match = re.match(
            r"^(\s*)[-*]\s+(.+)$",
            stripped if stripped.startswith("-") or stripped.startswith("*") else line,
        )
        if not bullet_match and (line.lstrip().startswith("-") or line.lstrip().startswith("*")):
            # Handle indented bullets
            indent = len(line) - len(line.lstrip())
            bullet_content = line.lstrip()[2:].strip()  # Remove "- " or "* "
            if bullet_content:
                bullet_match = True
                indent // 2  # Approximate nesting level

        if bullet_match or (line.lstrip().startswith("-") or line.lstrip().startswith("*")):
            # Calculate indent
            indent = len(line) - len(line.lstrip())
            bullet_text = line.lstrip()
            if bullet_text.startswith("-"):
                bullet_content = bullet_text[1:].strip()
            elif bullet_text.startswith("*"):
                bullet_content = bullet_text[1:].strip()
            else:
                continue

            if not bullet_content or len(bullet_content) < 3:
                continue

            # Bullet level starts at 7 (after H6)
            bullet_level = 7 + (indent // 2)
            slug = slugify(bullet_content)

            if not slug:  # Skip if slug is empty
                continue

            item = ContentItem(
                title=bullet_content,
                slug=slug,
                level=bullet_level,
                item_type="bullet",
                source_line=line_num,
            )

            if current_section:
                item.section_slug = current_section.slug

            # Find parent - could be a heading or another bullet
            if parent_stack:
                # Find appropriate parent based on level
                while parent_stack and parent_stack[-1].level >= bullet_level:
                    parent_stack.pop()
                if parent_stack:
                    item.parent_slug = parent_stack[-1].slug

            parent_stack.append(item)
            items.append(item)

            # Extract links from bullet content
            bullet_links = extract_obsidian_links(bullet_content)
            links_to_create.extend(bullet_links)
            continue

        # Check for standalone links not in headings/bullets
        if "[" in stripped and "](" in stripped:
            line_links = extract_obsidian_links(stripped)
            links_to_create.extend(line_links)

    # Create items for links
    for display_text, filename in links_to_create:
        # Extract slug from filename (remove .md extension)
        link_slug = slugify(filename.replace(".md", ""))
        if not link_slug:
            continue

        # Check if we already have an item with this slug
        existing_slugs = {item.slug for item in items}
        if link_slug in existing_slugs:
            continue

        item = ContentItem(
            title=display_text,
            slug=link_slug,
            level=99,  # Links are leaf nodes
            item_type="link",
            content="tbd",
            source_line=0,
        )
        items.append(item)

    return frontmatter, items


def build_filename(item: ContentItem) -> str:
    """Build the filename for a content item.

    Uses section--parent--item format for hierarchy.
    """
    parts = []

    if item.section_slug and item.section_slug != item.slug:
        parts.append(item.section_slug)

    if item.parent_slug and item.parent_slug != item.section_slug:
        parts.append(item.parent_slug)

    parts.append(item.slug)

    # Deduplicate while preserving order
    seen = set()
    unique_parts = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique_parts.append(p)

    return "--".join(unique_parts)


def generate_yaml_frontmatter(item: ContentItem, filename: str, moc_uid: str = "moc_nous") -> str:
    """Generate YAML frontmatter for a content item."""
    uid = f"ku.{filename}"

    # Build relationships
    relationships = []

    # HAS_NARROWER from parent
    if item.parent_slug:
        parent_filename = item.parent_slug
        if item.section_slug and item.section_slug != item.parent_slug:
            parent_filename = f"{item.section_slug}--{item.parent_slug}"
        relationships.append(
            {
                "type": "HAS_NARROWER",
                "from_uid": f"ku.{parent_filename}",
            }
        )

    # PART_OF_MOC
    relationships.append(
        {
            "type": "PART_OF_MOC",
            "target_uid": moc_uid,
            "section": item.section_slug or "root",
        }
    )

    # Build tags
    tags = ["nous"]
    if item.section_slug:
        tags.append(item.section_slug)
    if item.item_type == "link":
        tags.append("external-reference")

    # Determine heading level for non-bullets
    heading_level = item.level if item.level <= 6 else None

    # Escape title for YAML
    safe_title = item.title.replace('"', "'")

    yaml_parts = [
        "---",
        f"uid: {uid}",
        f'title: "{safe_title}"',
        'description: ""',
    ]

    # Add icon for section headings (H2)
    if item.icon:
        yaml_parts.append(f"icon: {item.icon}")

    if item.parent_slug:
        parent_filename = item.parent_slug
        if item.section_slug and item.section_slug != item.parent_slug:
            parent_filename = f"{item.section_slug}--{item.parent_slug}"
        yaml_parts.append(f"parent_uid: ku.{parent_filename}")

    if item.section_slug:
        yaml_parts.append(f"section_uid: ku.{item.section_slug}")

    yaml_parts.append(f"moc_uid: {moc_uid}")

    if heading_level:
        yaml_parts.append(f"heading_level: {heading_level}")

    yaml_parts.append(f"item_type: {item.item_type}")

    # Relationships section
    yaml_parts.append("relationships:")
    for rel in relationships:
        if rel["type"] == "HAS_NARROWER":
            yaml_parts.append("  - type: HAS_NARROWER")
            yaml_parts.append(f"    from_uid: {rel['from_uid']}")
        elif rel["type"] == "PART_OF_MOC":
            yaml_parts.append("  - type: PART_OF_MOC")
            yaml_parts.append(f"    target_uid: {rel['target_uid']}")
            yaml_parts.append(f"    section: {rel['section']}")

    # Tags
    yaml_parts.append("tags:")
    for tag in tags:
        yaml_parts.append(f"  - {tag}")

    yaml_parts.append("---")

    return "\n".join(yaml_parts)


def generate_file_content(item: ContentItem, filename: str) -> str:
    """Generate full file content with frontmatter and body.

    Note: Title is stored in frontmatter, not repeated as markdown heading.
    The UI displays the title from metadata, so we avoid duplication.
    """
    frontmatter = generate_yaml_frontmatter(item, filename)

    # Body content - title comes from frontmatter, not markdown heading
    body = item.content if item.content else "tbd"

    return f"{frontmatter}\n\n{body}\n"


def main():
    """Main entry point."""
    print(f"Parsing MOC file: {MOC_FILE}")

    if not MOC_FILE.exists():
        print(f"ERROR: MOC file not found: {MOC_FILE}")
        return

    frontmatter, items = parse_moc_file(MOC_FILE)

    print(f"\nFound {len(items)} content items:")
    headings = [i for i in items if i.item_type == "heading"]
    bullets = [i for i in items if i.item_type == "bullet"]
    links = [i for i in items if i.item_type == "link"]

    print(f"  - {len(headings)} headings")
    print(f"  - {len(bullets)} bullet points")
    print(f"  - {len(links)} external links")

    # Generate files
    print(f"\nGenerating files in: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0

    for item in items:
        filename = build_filename(item)
        file_path = OUTPUT_DIR / f"{filename}.md"

        # Skip if file already exists (don't overwrite moc_nous.md)
        if file_path.name == "moc_nous.md":
            print(f"  SKIP: {file_path.name} (MOC source file)")
            skipped += 1
            continue

        content = generate_file_content(item, filename)

        # Write file
        file_path.write_text(content, encoding="utf-8")
        generated += 1

        if generated <= 10:  # Show first 10
            print(f"  CREATE: {file_path.name}")

    if generated > 10:
        print(f"  ... and {generated - 10} more files")

    print("\nSummary:")
    print(f"  Generated: {generated} files")
    print(f"  Skipped: {skipped} files")
    print(f"  Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
