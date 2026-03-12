#!/usr/bin/env python3
"""
Migration: Neo4j GenAI (OpenAI) → HuggingFace Embeddings
=========================================================

Drops old vector indexes (1536 dims) and clears old embeddings.
After running, recreate indexes with dim=1024 and re-embed via generate_embeddings_batch.py.

Steps:
  1. Drop old vector indexes
  2. Clear old embedding data from Entity and ContentChunk nodes
  3. Print instructions for recreating indexes and re-embedding

Usage:
    uv run python scripts/migrations/migrate_to_huggingface_embeddings.py [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

import os

from neo4j import AsyncGraphDatabase


async def run_migration(dry_run: bool = False) -> None:
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    try:
        async with driver.session() as session:
            # Step 1: Drop old vector indexes
            print("Step 1: Dropping old vector indexes...")
            drop_queries = [
                "DROP INDEX entity_embedding_idx IF EXISTS",
                "DROP INDEX contentchunk_embedding_idx IF EXISTS",
            ]
            for query in drop_queries:
                if dry_run:
                    print(f"  [DRY RUN] {query}")
                else:
                    await session.run(query)
                    print(f"  Executed: {query}")

            # Step 2: Clear old embeddings from Entity nodes
            print("\nStep 2: Clearing old embeddings from Entity nodes...")
            clear_entity_query = """
            MATCH (n:Entity) WHERE n.embedding IS NOT NULL
            SET n.embedding = null,
                n.embedding_version = null,
                n.embedding_model = null,
                n.embedding_updated_at = null,
                n.embedding_source_text = null
            RETURN count(n) as cleared
            """
            if dry_run:
                count_query = """
                MATCH (n:Entity) WHERE n.embedding IS NOT NULL
                RETURN count(n) as count
                """
                result = await session.run(count_query)
                record = await result.single()
                count = record["count"] if record else 0
                print(f"  [DRY RUN] Would clear embeddings from {count} Entity nodes")
            else:
                result = await session.run(clear_entity_query)
                record = await result.single()
                cleared = record["cleared"] if record else 0
                print(f"  Cleared embeddings from {cleared} Entity nodes")

            # Step 3: Clear old embeddings from ContentChunk nodes
            print("\nStep 3: Clearing old embeddings from ContentChunk nodes...")
            clear_chunk_query = """
            MATCH (n:ContentChunk) WHERE n.embedding IS NOT NULL
            SET n.embedding = null,
                n.embedding_version = null,
                n.embedding_model = null
            RETURN count(n) as cleared
            """
            if dry_run:
                count_query = """
                MATCH (n:ContentChunk) WHERE n.embedding IS NOT NULL
                RETURN count(n) as count
                """
                result = await session.run(count_query)
                record = await result.single()
                count = record["count"] if record else 0
                print(f"  [DRY RUN] Would clear embeddings from {count} ContentChunk nodes")
            else:
                result = await session.run(clear_chunk_query)
                record = await result.single()
                cleared = record["cleared"] if record else 0
                print(f"  Cleared embeddings from {cleared} ContentChunk nodes")

        print("\n" + "=" * 60)
        print("Migration complete!" if not dry_run else "Dry run complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Ensure HF_API_TOKEN is set in .env")
        print("  2. Restart the app (indexes are auto-created with dim=1024)")
        print("  3. Re-embed all entities:")
        print("     uv run python scripts/generate_embeddings_batch.py")

    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate embeddings to HuggingFace")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
