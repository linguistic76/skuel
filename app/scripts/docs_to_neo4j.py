#!/usr/bin/env python3
"""
Load documentation metadata into Neo4j graph database.

Creates Document nodes with relationships for:
- REFINES (doc improves/extends another)
- DEPENDS_ON (doc requires understanding of another)
- COMPLEMENTS (docs are related but independent)
- IN_CATEGORY (doc belongs to category)

Usage:
    python scripts/docs_to_neo4j.py                    # Preview queries
    python scripts/docs_to_neo4j.py --apply            # Execute in Neo4j
    python scripts/docs_to_neo4j.py --clear --apply    # Clear and reload

Requires:
    NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD environment variables
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class DocNode:
    """Document node for Neo4j."""

    uid: str
    title: str
    path: str
    category: str
    updated: str
    status: str
    tags: list[str]
    size_lines: int


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter."""
    if not content.startswith("---\n"):
        return {}

    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return {}

    frontmatter_text = content[4:end_idx]
    result = {}

    for line in frontmatter_text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                value = [item.strip() for item in items if item.strip()]

            result[key] = value

    return result


def path_to_uid(path: str) -> str:
    """Convert file path to UID."""
    # Remove .md extension and convert to uid format
    uid = path.replace(".md", "").replace("/", ":").replace("_", "-").lower()
    return f"doc:{uid}"


def extract_related_docs(content: str, fm: dict) -> list[str]:
    """Extract related document references."""
    related = []

    # From frontmatter
    fm_related = fm.get("related", [])
    if isinstance(fm_related, str):
        fm_related = [fm_related]
    for rel in fm_related:
        if rel and rel != "[]":
            related.append(rel)

    # From **See:** pointers
    see_pattern = r"\*\*See:\*\*\s*`?([^`\n]+)`?"
    for match in re.finditer(see_pattern, content):
        path = match.group(1).strip()
        if path.endswith(".md"):
            related.append(path)

    # From markdown links to .md files
    link_pattern = r"\[([^\]]+)\]\(([^)]+\.md)\)"
    for match in re.finditer(link_pattern, content):
        related.append(match.group(2))

    return list(set(related))


def analyze_doc(filepath: Path, docs_dir: Path) -> tuple[DocNode, list[str]]:
    """Analyze a document and extract node data and relationships."""
    content = filepath.read_text(encoding="utf-8")
    rel_path = str(filepath.relative_to(docs_dir))

    fm = extract_frontmatter(content)

    # Build node
    node = DocNode(
        uid=path_to_uid(rel_path),
        title=fm.get("title", filepath.stem.replace("_", " ").title()),
        path=rel_path,
        category=fm.get("category", "general"),
        updated=fm.get(
            "updated", datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d")
        ),
        status=fm.get("status", "current"),
        tags=fm.get("tags", []) if isinstance(fm.get("tags", []), list) else [fm.get("tags", "")],
        size_lines=len(content.split("\n")),
    )

    # Extract relationships
    related = extract_related_docs(content, fm)

    return node, related


def generate_cypher(docs_dir: Path) -> tuple[list[str], list[str]]:
    """Generate Cypher queries for all docs."""
    node_queries = []
    rel_queries = []

    # Collect all docs
    all_docs = {}
    all_relationships = []

    for filepath in docs_dir.rglob("*.md"):
        try:
            node, related = analyze_doc(filepath, docs_dir)
            all_docs[node.path] = node

            for rel_path in related:
                # Normalize path
                if rel_path.startswith("/docs/"):
                    rel_path = rel_path[6:]
                elif rel_path.startswith("./"):
                    # Relative path
                    base_dir = Path(node.path).parent
                    rel_path = str(base_dir / rel_path[2:])

                all_relationships.append((node.path, rel_path))

        except Exception as e:
            print(f"Warning: Failed to process {filepath}: {e}", file=sys.stderr)

    # Generate node creation queries
    for node in all_docs.values():
        tags_str = json.dumps(node.tags)
        query = f"""
MERGE (d:Document {{uid: '{node.uid}'}})
SET d.title = '{node.title.replace("'", "\\'")}',
    d.path = '{node.path}',
    d.category = '{node.category}',
    d.updated = date('{node.updated}'),
    d.status = '{node.status}',
    d.tags = {tags_str},
    d.size_lines = {node.size_lines}
"""
        node_queries.append(query.strip())

    # Generate category nodes and relationships
    categories = set(node.category for node in all_docs.values())
    for category in categories:
        query = f"""
MERGE (c:DocumentCategory {{name: '{category}'}})
"""
        node_queries.append(query.strip())

    # Category relationships
    for node in all_docs.values():
        query = f"""
MATCH (d:Document {{uid: '{node.uid}'}}), (c:DocumentCategory {{name: '{node.category}'}})
MERGE (d)-[:IN_CATEGORY]->(c)
"""
        rel_queries.append(query.strip())

    # Document relationships
    for source_path, target_path in all_relationships:
        source_uid = path_to_uid(source_path)
        target_uid = path_to_uid(target_path)

        # Check if target exists
        if target_path in all_docs or target_path.lstrip("./") in all_docs:
            query = f"""
MATCH (s:Document {{uid: '{source_uid}'}}), (t:Document {{uid: '{target_uid}'}})
MERGE (s)-[:RELATES_TO]->(t)
"""
            rel_queries.append(query.strip())

    return node_queries, rel_queries


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    clear = "--clear" in args

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Generate queries
    node_queries, rel_queries = generate_cypher(docs_dir)

    print(f"Generated {len(node_queries)} node queries and {len(rel_queries)} relationship queries")
    print()

    if not apply:
        # Preview mode
        print("=== Node Queries (first 5) ===")
        for q in node_queries[:5]:
            print(q)
            print()

        print("=== Relationship Queries (first 5) ===")
        for q in rel_queries[:5]:
            print(q)
            print()

        print("Run with --apply to execute in Neo4j")
        return

    # Apply mode - execute queries
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("Error: neo4j package not installed. Run: pip install neo4j", file=sys.stderr)
        sys.exit(1)

    # Get connection info - use SKUEL's credential store
    try:
        from core.config.credential_store import get_credential

        password = get_credential("NEO4J_PASSWORD")
    except ImportError:
        password = os.getenv("NEO4J_PASSWORD")

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")

    if not password:
        print("Error: NEO4J_PASSWORD not found in credential store or environment", file=sys.stderr)
        print("  Set with: poetry run python scripts/set_neo4j_password.py", file=sys.stderr)
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        with driver.session() as session:
            # Clear existing if requested
            if clear:
                print("Clearing existing Document nodes...")
                session.run("MATCH (d:Document) DETACH DELETE d")
                session.run("MATCH (c:DocumentCategory) DETACH DELETE c")

            # Execute node queries
            print("Creating Document nodes...")
            for i, query in enumerate(node_queries):
                session.run(query)
                if (i + 1) % 20 == 0:
                    print(f"  Created {i + 1}/{len(node_queries)} nodes")

            # Execute relationship queries
            print("Creating relationships...")
            for i, query in enumerate(rel_queries):
                try:
                    session.run(query)
                except Exception as e:
                    print(f"Warning: Relationship failed: {e}", file=sys.stderr)

            print(f"\nComplete! Created {len(node_queries)} nodes and relationships")

            # Verify
            result = session.run("MATCH (d:Document) RETURN count(d) as count")
            count = result.single()["count"]
            print(f"Verified: {count} Document nodes in database")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
