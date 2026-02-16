"""
Hierarchy Parser - Extract hierarchical heading structure from Markdown.

Parses hierarchical markdown files to extract:
- H2 = Domain/Section
- H3 = Category
- H4 = Topic
- H5 = Subtopic
- H6 = Detail

This hierarchy becomes the basis for:
1. Navigation in /docs
2. KU generation with ORGANIZES relationships
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HeadingNode:
    """A single heading in the hierarchy."""

    level: int  # 2-6
    title: str
    slug: str
    content: str = ""  # Text content after heading until next heading
    children: list["HeadingNode"] = field(default_factory=list)
    parent_slug: str | None = None  # For building relationships

    @property
    def has_children(self) -> bool:
        return len(self.children) > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "content": self.content,
            "parent_slug": self.parent_slug,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class HierarchyStructure:
    """Complete hierarchy structure with metadata and heading tree."""

    uid: str
    title: str
    description: str
    domain: str
    sections: list[HeadingNode]  # H2 sections (top-level)

    def get_all_headings(self) -> list[HeadingNode]:
        """Flatten all headings for iteration."""
        result = []

        def collect(nodes: list[HeadingNode]) -> None:
            for node in nodes:
                result.append(node)
                collect(node.children)

        collect(self.sections)
        return result

    def get_section(self, slug: str) -> HeadingNode | None:
        """Get a section by slug."""
        for section in self.sections:
            if section.slug == slug:
                return section
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "sections": [s.to_dict() for s in self.sections],
        }


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    # Remove markdown links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r"[^\w\s-]", "", text.lower())
    # Replace spaces with hyphens
    return re.sub(r"[-\s]+", "-", text).strip("-")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body."""
    import yaml

    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = pattern.match(content)

    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
            body = content[match.end() :]
            return frontmatter, body
        except yaml.YAMLError:
            return {}, content
    return {}, content


def parse_hierarchy_markdown(content: str) -> HierarchyStructure:
    """
    Parse a hierarchical markdown file into a structured tree.

    Args:
        content: Raw markdown content

    Returns:
        HierarchyStructure with parsed hierarchy
    """
    frontmatter, body = parse_frontmatter(content)

    # Extract metadata
    uid = frontmatter.get("uid", "ku:unknown")
    title = frontmatter.get("title", "Unknown")
    description = frontmatter.get("description", "")
    domain = frontmatter.get("domain", "LEARNING")

    # Parse headings
    heading_pattern = re.compile(r"^(#{2,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(body))

    # Build heading nodes with content
    nodes: list[HeadingNode] = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title_text = match.group(2).strip()
        slug = slugify(title_text)

        # Get content between this heading and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content_text = body[start:end].strip()

        # Remove markdown links from content, just get text
        content_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content_text)

        nodes.append(
            HeadingNode(
                level=level,
                title=title_text,
                slug=slug,
                content=content_text[:500] if content_text else "",  # Limit content length
            )
        )

    # Build tree structure
    sections = build_heading_tree(nodes)

    return HierarchyStructure(
        uid=uid,
        title=title,
        description=description,
        domain=domain,
        sections=sections,
    )


def build_heading_tree(nodes: list[HeadingNode]) -> list[HeadingNode]:
    """
    Build a tree from a flat list of heading nodes.

    H2 -> H3 -> H4 -> H5 -> H6

    Returns:
        List of top-level (H2) nodes with children nested
    """
    if not nodes:
        return []

    root_nodes: list[HeadingNode] = []
    stack: list[HeadingNode] = []

    for node in nodes:
        # Pop stack until we find a parent with lower level
        while stack and stack[-1].level >= node.level:
            stack.pop()

        if stack:
            # This node is a child of the top of the stack
            node.parent_slug = stack[-1].slug
            stack[-1].children.append(node)
        else:
            # This is a root node (H2)
            root_nodes.append(node)

        stack.append(node)

    return root_nodes


def parse_hierarchy_file(file_path: Path | str) -> HierarchyStructure:
    """
    Parse a hierarchical markdown file.

    Args:
        file_path: Path to the markdown file

    Returns:
        HierarchyStructure with parsed hierarchy
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")
    return parse_hierarchy_markdown(content)


def generate_ku_yaml_from_heading(
    heading: HeadingNode,
    organizer_uid: str,
    section_slug: str,
    domain: str = "LEARNING",
) -> str:
    """
    Generate KU YAML frontmatter from a heading.

    Args:
        heading: The heading node
        organizer_uid: Parent organizer KU UID
        section_slug: Section (H2) slug this belongs to
        domain: Content domain

    Returns:
        YAML frontmatter string
    """
    # Build hierarchical UID
    uid = f"ku:{organizer_uid.replace('ku:', '').replace('moc:', '')}.{section_slug}.{heading.slug}"

    # Determine complexity based on heading level
    complexity_map = {2: "medium", 3: "medium", 4: "easy", 5: "easy", 6: "trivial"}
    complexity = complexity_map.get(heading.level, "medium")

    # Build path
    parent_path = f"{section_slug}/{heading.parent_slug}" if heading.parent_slug else section_slug

    return f"""---
uid: {uid}
domain: KNOWLEDGE
title: "{heading.title}"

content_domain: {domain}
sel_category: cognitive
learning_level: intermediate
complexity: {complexity}

tags:
  - worldview
  - {section_slug}

# Organization - indicates where this KU lives in the hierarchy
organizer:
  uid: {organizer_uid}
  section: {section_slug}
  path: {parent_path}
  heading_level: {heading.level}

metadata:
  source_type: hierarchy-derived
  source_organizer: {organizer_uid}
  auto_generated: true
---

# {heading.title}

{heading.content if heading.content else "Content to be written..."}
"""


__all__ = [
    "HeadingNode",
    "HierarchyStructure",
    "generate_ku_yaml_from_heading",
    "parse_hierarchy_file",
    "parse_hierarchy_markdown",
    "slugify",
]
