#!/usr/bin/env python3
"""
Ingest nous files to Neo4j using direct Cypher queries.

Bypasses the UnifiedIngestionService to work around the dataclass bug.
"""

import asyncio
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

# Load .env file from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE, override=True)

NOUS_PATH = Path("/home/mike/0bsidian/skuel/nous")


def parse_markdown_file(file_path: Path) -> dict | None:
    """Parse a markdown file with YAML frontmatter."""
    content = file_path.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
        body = parts[2].strip()
    except yaml.YAMLError:
        return None

    if not frontmatter:
        return None

    # Extract key fields
    data = {
        "uid": frontmatter.get("uid", ""),
        "title": frontmatter.get("title", ""),
        "description": frontmatter.get("description", ""),
        "icon": frontmatter.get("icon", ""),  # Emoji icon for sections
        "content": body,
        "parent_uid": frontmatter.get("parent_uid"),
        "section_uid": frontmatter.get("section_uid"),
        "moc_uid": frontmatter.get("moc_uid", "moc_nous"),
        "heading_level": frontmatter.get("heading_level"),
        "item_type": frontmatter.get("item_type", "heading"),
        "tags": frontmatter.get("tags", []),
    }

    return data


async def create_ku_node(session, data: dict) -> bool:
    """Create a KU node in Neo4j."""
    query = """
    MERGE (k:Ku {uid: $uid})
    SET k.title = $title,
        k.description = $description,
        k.icon = $icon,
        k.content = $content,
        k.parent_uid = $parent_uid,
        k.section_uid = $section_uid,
        k.moc_uid = $moc_uid,
        k.heading_level = $heading_level,
        k.item_type = $item_type,
        k.tags = $tags,
        k.created_at = datetime(),
        k.updated_at = datetime()
    RETURN k.uid as uid
    """

    try:
        result = await session.run(
            query,
            uid=data["uid"],
            title=data["title"],
            description=data["description"] or "",
            icon=data["icon"] or "",
            content=data["content"] or "tbd",
            parent_uid=data["parent_uid"],
            section_uid=data["section_uid"],
            moc_uid=data["moc_uid"],
            heading_level=data["heading_level"],
            item_type=data["item_type"],
            tags=data["tags"] or [],
        )
        await result.consume()
        return True
    except Exception as e:
        print(f"    Error creating {data['uid']}: {e}")
        return False


async def create_parent_relationships(session) -> int:
    """Create HAS_NARROWER relationships based on parent_uid."""
    query = """
    MATCH (child:Ku)
    WHERE child.parent_uid IS NOT NULL
    MATCH (parent:Ku {uid: child.parent_uid})
    MERGE (parent)-[r:HAS_NARROWER]->(child)
    RETURN count(r) as count
    """

    result = await session.run(query)
    record = await result.single()
    return record["count"] if record else 0


async def main():
    """Ingest nous files to Neo4j."""
    print(f"Ingesting nous files from: {NOUS_PATH}")

    # Get Neo4j config from environment
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    # Create Neo4j driver
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password),
    )
    print(f"Connecting to Neo4j at {neo4j_uri}")

    try:
        # Verify connection
        async with driver.session() as session:
            result = await session.run("RETURN 1 as n")
            await result.consume()
        print("✅ Neo4j connection verified")

        # Get all markdown files
        md_files = list(NOUS_PATH.glob("*.md"))
        print(f"Found {len(md_files)} markdown files")

        # Ingest files
        print("\nStarting ingestion...")
        successful = 0
        failed = 0

        async with driver.session() as session:
            for i, file_path in enumerate(md_files):
                if file_path.name == "moc_nous.md":
                    # Handle MOC file specially if needed
                    continue

                data = parse_markdown_file(file_path)
                if not data or not data.get("uid"):
                    failed += 1
                    continue

                if await create_ku_node(session, data):
                    successful += 1
                    if successful <= 5:
                        print(f"  ✓ {data['uid']}")
                    elif successful == 6:
                        print("  ... (continuing)")
                else:
                    failed += 1

                # Progress indicator every 50 files
                if (i + 1) % 50 == 0:
                    print(f"  Progress: {i + 1}/{len(md_files)} files")

            # Create parent relationships
            print("\nCreating parent relationships...")
            rel_count = await create_parent_relationships(session)
            print(f"  Created {rel_count} HAS_NARROWER relationships")

        print("\n✅ Ingestion complete!")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")

    finally:
        await driver.close()
        print("\n✅ Neo4j connection closed")


if __name__ == "__main__":
    asyncio.run(main())
