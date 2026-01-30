#!/usr/bin/env python3
"""
Backfill embedding_version for existing Activity domain embeddings.

This migration adds the embedding_version field to all existing Activity domain
entities that have embeddings but are missing version tracking.

Usage:
    poetry run python scripts/migrations/backfill_activity_embedding_versions.py --dry-run
    poetry run python scripts/migrations/backfill_activity_embedding_versions.py

Context:
    - Activity domains (Tasks, Goals, Habits, Events, Choices, Principles) now track embedding versions
    - KUs already had version tracking via Neo4jGenAIEmbeddingsService
    - This migration ensures Activity embeddings can be identified for model upgrades
    - Safe to run multiple times (idempotent)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from neo4j import AsyncGraphDatabase

from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.backfill_versions")


async def backfill_versions(driver: Any, dry_run: bool = False) -> dict[str, int]:
    """
    Add embedding_version to existing Activity embeddings.

    Args:
        driver: Neo4j AsyncDriver instance
        dry_run: If True, only count entities without modifying

    Returns:
        Dictionary with counts per domain: {"task": 150, "goal": 42, ...}
    """
    # Activity domain labels
    labels = ["Task", "Goal", "Habit", "Event", "Choice", "Principle"]

    results = {}

    for label in labels:
        if dry_run:
            # Count entities that need version
            query = f"""
            MATCH (n:{label})
            WHERE n.embedding IS NOT NULL
              AND n.embedding_version IS NULL
            RETURN count(n) as count
            """

            result = await driver.execute_query(query)
            count = result[0][0]["count"] if result and result[0] else 0
            results[label.lower()] = count

            if count > 0:
                logger.info(f"[DRY-RUN] Would update {count} {label} nodes")
            else:
                logger.info(f"[DRY-RUN] No {label} nodes need updating")

        else:
            # Update entities with version
            query = f"""
            MATCH (n:{label})
            WHERE n.embedding IS NOT NULL
              AND n.embedding_version IS NULL
            SET n.embedding_version = $version
            RETURN count(n) as updated
            """

            result = await driver.execute_query(query, version="v1")
            updated = result[0][0]["updated"] if result and result[0] else 0
            results[label.lower()] = updated

            if updated > 0:
                logger.info(f"✅ Updated {updated} {label} nodes with version=v1")
            else:
                logger.info(f"✓ No {label} nodes needed updating")

    return results


async def main() -> None:
    """Main migration function"""
    parser = argparse.ArgumentParser(description="Backfill Activity embedding versions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database",
    )
    args = parser.parse_args()

    # Get Neo4j credentials using credential store (same as config)
    try:
        from core.config.credential_store import get_credential
        neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
    except Exception:
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")

    if not neo4j_password:
        logger.error("❌ NEO4J_PASSWORD not found in credential store or environment")
        return

    # Connect to database
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_username, neo4j_password),
    )

    try:
        # Verify connection
        await driver.verify_connectivity()
        logger.info(f"✅ Connected to Neo4j at {neo4j_uri}")

        if args.dry_run:
            logger.info("🔍 DRY-RUN MODE: No changes will be made")
        else:
            logger.info("⚙️  LIVE MODE: Database will be updated")

        # Run migration
        results = await backfill_versions(driver, dry_run=args.dry_run)

        # Summary
        total = sum(results.values())
        logger.info("")
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)

        for domain, count in results.items():
            logger.info(f"{domain.capitalize():12s}: {count:5d} entities")

        logger.info("-" * 60)
        logger.info(f"{'TOTAL':12s}: {total:5d} entities")
        logger.info("=" * 60)

        if args.dry_run:
            logger.info("")
            logger.info("✅ Dry-run complete. Run without --dry-run to apply changes.")
        else:
            logger.info("")
            logger.info("✅ Migration complete. All Activity embeddings now have version tracking.")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        await driver.close()
        logger.info("🔌 Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
