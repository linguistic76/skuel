#!/usr/bin/env python3
"""
Create Neo4j Indices for Knowledge Architecture
================================================
This script creates the necessary indices for the new separated
KnowledgeUnit and Content node architecture.
"""

__version__ = "1.0"

import asyncio
import sys
import traceback
from pathlib import Path

from adapters.persistence.neo4j.neo4j_connection import get_connection
from core.utils.logging import get_logger

project_root = Path(__file__).parent.parent
logger = get_logger("index_creation")


async def create_constraint_indices(connection):
    """
    Create unique constraints that also create indices.
    """
    logger.info("Creating constraint indices...")
    constraints = [
        (
            "Ku",
            "uid",
            "CREATE CONSTRAINT ku_uid_unique IF NOT EXISTS FOR (n:Ku) REQUIRE n.uid IS UNIQUE",
        ),
        (
            "Content",
            "unit_uid",
            "CREATE CONSTRAINT content_uid_unique IF NOT EXISTS FOR (n:Content) REQUIRE n.unit_uid IS UNIQUE",
        ),
        (
            "KnowledgeDomain",
            "uid",
            "CREATE CONSTRAINT domain_uid_unique IF NOT EXISTS FOR (n:KnowledgeDomain) REQUIRE n.uid IS UNIQUE",
        ),
    ]
    for label, property, query in constraints:
        try:
            await connection.execute_query(query)
            logger.info(f"  ✓ Created constraint on {label}.{property}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.info(f"  - Constraint on {label}.{property} already exists")
            else:
                logger.warning(f"  ⚠ Failed to create constraint on {label}.{property}: {e}")


async def create_lookup_indices(connection):
    """
    Create standard indices for lookups.
    """
    logger.info("Creating lookup indices...")
    indices = [
        (
            "Ku",
            "title",
            "CREATE INDEX ku_title IF NOT EXISTS FOR (n:Ku) ON (n.title)",
        ),
        (
            "Ku",
            "status",
            "CREATE INDEX ku_status IF NOT EXISTS FOR (n:Ku) ON (n.status)",
        ),
        (
            "Ku",
            "parent_uid",
            "CREATE INDEX ku_parent IF NOT EXISTS FOR (n:Ku) ON (n.parent_uid)",
        ),
        (
            "Ku",
            "content_type",
            "CREATE INDEX ku_content_type IF NOT EXISTS FOR (n:Ku) ON (n.content_type)",
        ),
        (
            "Ku",
            "practice_level",
            "CREATE INDEX ku_practice_level IF NOT EXISTS FOR (n:Ku) ON (n.practice_level)",
        ),
        (
            "Ku",
            "category",
            "CREATE INDEX ku_category IF NOT EXISTS FOR (n:Ku) ON (n.category)",
        ),
        (
            "Ku",
            "domain_uid",
            "CREATE INDEX ku_domain_uid IF NOT EXISTS FOR (n:Ku) ON (n.domain_uid)",
        ),
        (
            "Content",
            "format",
            "CREATE INDEX content_format IF NOT EXISTS FOR (n:Content) ON (n.format)",
        ),
        (
            "Content",
            "language",
            "CREATE INDEX content_language IF NOT EXISTS FOR (n:Content) ON (n.language)",
        ),
        (
            "Content",
            "body_sha256",
            "CREATE INDEX content_sha256 IF NOT EXISTS FOR (n:Content) ON (n.body_sha256)",
        ),
        (
            "KnowledgeDomain",
            "name",
            "CREATE INDEX domain_name IF NOT EXISTS FOR (n:KnowledgeDomain) ON (n.name)",
        ),
        (
            "KnowledgeDomain",
            "status",
            "CREATE INDEX domain_status IF NOT EXISTS FOR (n:KnowledgeDomain) ON (n.status)",
        ),
        (
            "KnowledgeDomain",
            "parent_uid",
            "CREATE INDEX domain_parent IF NOT EXISTS FOR (n:KnowledgeDomain) ON (n.parent_uid)",
        ),
    ]
    for label, property, query in indices:
        try:
            await connection.execute_query(query)
            logger.info(f"  ✓ Created index on {label}.{property}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.info(f"  - Index on {label}.{property} already exists")
            else:
                logger.warning(f"  ⚠ Failed to create index on {label}.{property}: {e}")


async def create_fulltext_indices(connection):
    """
    Create fulltext indices for search.
    Neo4j 5.x only supports single property TEXT indices,
    so we create separate indices for each property.
    """
    logger.info("Creating fulltext indices...")
    fulltext_indices = [
        {
            "name": "ku_title_fulltext",
            "query": """
            CREATE TEXT INDEX ku_title_fulltext IF NOT EXISTS
            FOR (n:Ku)
            ON (n.title)
            """,
            "description": "KnowledgeUnit title",
        },
        {
            "name": "ku_summary_fulltext",
            "query": """
            CREATE TEXT INDEX ku_summary_fulltext IF NOT EXISTS
            FOR (n:Ku)
            ON (n.summary)
            """,
            "description": "KnowledgeUnit summary",
        },
        {
            "name": "content_fulltext",
            "query": """
            CREATE TEXT INDEX content_fulltext IF NOT EXISTS
            FOR (n:Content)
            ON (n.body)
            """,
            "description": "Content body text",
        },
        {
            "name": "ku_tags_fulltext",
            "query": """
            CREATE TEXT INDEX ku_tags_fulltext IF NOT EXISTS
            FOR (n:Ku)
            ON (n.tags)
            """,
            "description": "KnowledgeUnit tags",
        },
        {
            "name": "domain_aliases_fulltext",
            "query": """
            CREATE TEXT INDEX domain_aliases_fulltext IF NOT EXISTS
            FOR (n:KnowledgeDomain)
            ON (n.aliases)
            """,
            "description": "Domain aliases for backward compatibility",
        },
    ]
    for index in fulltext_indices:
        try:
            await connection.execute_query(index["query"])
            logger.info(f"  ✓ Created fulltext index '{index['name']}' for {index['description']}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.info(f"  - Fulltext index '{index['name']}' already exists")
            else:
                logger.warning(f"  ⚠ Failed to create fulltext index '{index['name']}': {e}")


async def create_composite_indices(connection):
    """
    Create composite indices for complex queries.
    """
    logger.info("Creating composite indices...")
    composite_indices = [
        {
            "name": "ku_domain_status",
            "query": "CREATE INDEX ku_domain_status IF NOT EXISTS FOR (n:Ku) ON (n.domain_uid, n.status)",
            "description": "Domain + Status lookups",
        },
        {
            "name": "ku_practice_status",
            "query": "CREATE INDEX ku_practice_status IF NOT EXISTS FOR (n:Ku) ON (n.practice_level, n.status)",
            "description": "Practice Level + Status lookups",
        },
        {
            "name": "ku_type_category",
            "query": "CREATE INDEX ku_type_category IF NOT EXISTS FOR (n:Ku) ON (n.content_type, n.category)",
            "description": "Content Type + Category lookups",
        },
        {
            "name": "content_unit_format",
            "query": "CREATE INDEX content_unit_format IF NOT EXISTS FOR (n:Content) ON (n.unit_uid, n.format)",
            "description": "Unit + Format lookups",
        },
    ]
    for index in composite_indices:
        try:
            await connection.execute_query(index["query"])
            logger.info(f"  ✓ Created composite index '{index['name']}' for {index['description']}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.info(f"  - Composite index '{index['name']}' already exists")
            else:
                logger.warning(f"  ⚠ Failed to create composite index '{index['name']}': {e}")


async def verify_indices(connection):
    """
    Verify all indices are created and active.
    """
    logger.info("Verifying indices...")
    query = """
    SHOW INDEXES
    YIELD name, type, labelsOrTypes, properties, state
    WHERE state = 'ONLINE'
    RETURN name, type, labelsOrTypes[0] as label, properties, state
    ORDER BY label, name
    """
    result = await connection.execute_query(query)
    if result:
        logger.info(f"  Found {len(result)} active indices:")
        by_label = {}
        for index in result:
            label = index.get("label")
            if label is None:
                label = "FULLTEXT"
            if label not in by_label:
                by_label[label] = []
            by_label[label].append(index)
        for label in sorted([k for k in by_label if k is not None]):
            logger.info(f"\n  {label}:")
            for index in by_label[label]:
                props = index.get("properties", [])
                if isinstance(props, list):
                    properties = ", ".join(props)
                else:
                    properties = str(props) if props else "N/A"
                logger.info(f"    - {index['name']}: {properties} ({index['type']})")


async def main():
    """Create all indices."""
    logger.info("=" * 60)
    logger.info("Creating Knowledge Architecture Indices")
    logger.info("=" * 60)
    connection = await get_connection()
    if not await connection.test_connection():
        logger.error("Cannot connect to Neo4j database!")
        return 1
    try:
        await create_constraint_indices(connection)
        await create_lookup_indices(connection)
        await create_fulltext_indices(connection)
        await create_composite_indices(connection)
        await verify_indices(connection)
        logger.info("=" * 60)
        logger.info("✅ Index creation completed successfully!")
        logger.info("=" * 60)
        return 0
    except Exception as e:
        logger.error(f"Index creation failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
