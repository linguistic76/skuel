#!/usr/bin/env python3
"""
Migrate Embeddings to New Version
==================================

Regenerates embeddings for nodes with outdated embedding versions.

Use this script when:
- Upgrading to a new embedding model
- Changing embedding parameters
- Fixing corrupted embeddings

CAUTION: This script makes API calls to regenerate embeddings.
Costs apply based on the number of nodes needing updates.

Usage:
    uv run python scripts/migrate_embeddings_version.py --dry-run
    uv run python scripts/migrate_embeddings_version.py --label Ku
    uv run python scripts/migrate_embeddings_version.py --limit 100

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

import argparse
import asyncio
import sys

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.services.neo4j_genai_embeddings_service import (
    EMBEDDING_VERSION,
    Neo4jGenAIEmbeddingsService,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.embedding_migration")


async def get_stale_nodes(
    driver, current_version: str, label: str | None = None, limit: int | None = None
) -> list[dict]:
    """
    Get nodes with outdated embeddings.

    Args:
        driver: Neo4j driver instance
        current_version: Current embedding version
        label: Optional label filter
        limit: Optional limit on results

    Returns:
        List of nodes needing migration
    """
    # Build query based on filters
    label_clause = f":{label}" if label else ""
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
    MATCH (n{label_clause})
    WHERE n.embedding IS NOT NULL
      AND (n.embedding_version IS NULL OR n.embedding_version <> $current_version)
    RETURN labels(n)[0] as label,
           n.uid as uid,
           n.embedding_version as old_version,
           n.embedding_model as old_model,
           coalesce(n.title, n.name, n.statement, '') as title,
           coalesce(n.content, n.description, '') as content
    ORDER BY labels(n)[0], n.uid
    {limit_clause}
    """

    try:
        result = await driver.execute_query(query, {"current_version": current_version})
        return [dict(record) for record in result]
    except Exception as e:
        logger.error(f"Failed to query stale nodes: {e}")
        return []


def get_text_for_embedding(node: dict) -> str:
    """
    Extract text to embed from node data.

    Combines title and content fields intelligently.

    Args:
        node: Node record

    Returns:
        Text to embed
    """
    title = node.get("title", "").strip()
    content = node.get("content", "").strip()

    if title and content:
        return f"{title}\n\n{content}"
    elif title:
        return title
    elif content:
        return content
    else:
        # Fallback to UID if no text available
        return node.get("uid", "")


async def migrate_node(
    service: Neo4jGenAIEmbeddingsService,
    node: dict,
    dry_run: bool = False,
) -> dict:
    """
    Migrate a single node's embedding.

    Args:
        service: Embeddings service
        node: Node to migrate
        dry_run: If True, don't actually update

    Returns:
        Migration result dict
    """
    uid = node["uid"]
    label = node["label"]
    text = get_text_for_embedding(node)

    if dry_run:
        return {
            "uid": uid,
            "label": label,
            "success": True,
            "skipped": True,
            "message": "Dry run - no changes made",
        }

    try:
        # Generate new embedding
        embedding_result = await service.create_embedding(text)

        if embedding_result.is_error:
            return {
                "uid": uid,
                "label": label,
                "success": False,
                "error": str(embedding_result.error),
            }

        embedding = embedding_result.value

        # Store with new version metadata
        store_result = await service.store_embedding_with_metadata(
            uid=uid,
            label=label,
            embedding=embedding,
            text=text[:1000],  # Store first 1000 chars
        )

        if store_result.is_error:
            return {
                "uid": uid,
                "label": label,
                "success": False,
                "error": str(store_result.error),
            }

        return {
            "uid": uid,
            "label": label,
            "success": True,
            "old_version": node.get("old_version"),
            "new_version": EMBEDDING_VERSION,
        }

    except Exception as e:
        return {
            "uid": uid,
            "label": label,
            "success": False,
            "error": str(e),
        }


async def migrate_embeddings(
    driver,
    service: Neo4jGenAIEmbeddingsService,
    label: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 10,
) -> dict:
    """
    Migrate embeddings to new version.

    Args:
        driver: Neo4j driver
        service: Embeddings service
        label: Optional label filter
        limit: Optional limit
        dry_run: If True, don't make changes
        batch_size: Number of nodes to process in parallel

    Returns:
        Migration summary dict
    """
    # Get stale nodes
    logger.info("Finding nodes with outdated embeddings...")
    stale_nodes = await get_stale_nodes(driver, EMBEDDING_VERSION, label, limit)

    if not stale_nodes:
        logger.info("✅ No nodes need migration")
        return {"total": 0, "migrated": 0, "failed": 0, "skipped": 0}

    total = len(stale_nodes)
    logger.info(f"Found {total} nodes needing migration")

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")

    # Migrate in batches
    results = []
    for i in range(0, total, batch_size):
        batch = stale_nodes[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} nodes)...")

        # Process batch in parallel
        batch_results = await asyncio.gather(
            *[migrate_node(service, node, dry_run) for node in batch]
        )
        results.extend(batch_results)

        # Show progress
        migrated = sum(1 for r in results if r.get("success") and not r.get("skipped"))
        failed = sum(1 for r in results if not r.get("success"))
        logger.info(f"Progress: {len(results)}/{total} (✅ {migrated}, ❌ {failed})")

    # Summarize results
    summary = {
        "total": total,
        "migrated": sum(1 for r in results if r.get("success") and not r.get("skipped")),
        "failed": sum(1 for r in results if not r.get("success")),
        "skipped": sum(1 for r in results if r.get("skipped")),
        "results": results,
    }

    return summary


def print_summary(summary: dict, dry_run: bool):
    """
    Print migration summary.

    Args:
        summary: Migration results
        dry_run: Whether this was a dry run
    """
    print()
    print("=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print()

    if dry_run:
        print("🔍 DRY RUN MODE - No actual changes made")
        print()

    print(f"Total nodes processed: {summary['total']}")
    print(f"✅ Successfully migrated: {summary['migrated']}")
    print(f"❌ Failed: {summary['failed']}")

    if summary["skipped"] > 0:
        print(f"⏭️  Skipped (dry run): {summary['skipped']}")

    # Show failures
    failures = [r for r in summary.get("results", []) if not r.get("success")]
    if failures:
        print()
        print("-" * 80)
        print(f"FAILURES ({len(failures)})")
        print("-" * 80)
        for failure in failures[:10]:  # Show first 10
            print(f"❌ {failure['label']}:{failure['uid']}")
            print(f"   Error: {failure.get('error', 'Unknown error')}")

        if len(failures) > 10:
            print(f"   ... and {len(failures) - 10} more failures")

    print()
    print("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate embeddings to new version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be updated
  uv run python scripts/migrate_embeddings_version.py --dry-run

  # Migrate specific entity type
  uv run python scripts/migrate_embeddings_version.py --label Ku

  # Limit number of migrations (for testing)
  uv run python scripts/migrate_embeddings_version.py --limit 10

  # Migrate with smaller batches (if hitting rate limits)
  uv run python scripts/migrate_embeddings_version.py --batch-size 5

CAUTION: This makes API calls to regenerate embeddings. Costs apply.
        """,
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )
    parser.add_argument("--label", help="Filter by entity label (e.g., Ku, Task, Goal)")
    parser.add_argument("--limit", type=int, help="Limit number of nodes to migrate")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for parallel processing (default: 10)",
    )

    args = parser.parse_args()

    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    try:
        await driver.verify_connectivity()
        logger.info("✅ Connected to Neo4j")

        # Create embeddings service
        service = Neo4jGenAIEmbeddingsService(driver)

        # Check plugin availability
        plugin_available = await service._check_plugin_availability()
        if not plugin_available and not args.dry_run:
            logger.error("❌ Neo4j GenAI plugin not available")
            logger.error("   Configure plugin in AuraDB console")
            return 1

        # Run migration
        summary = await migrate_embeddings(
            driver=driver,
            service=service,
            label=args.label,
            limit=args.limit,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )

        # Print summary
        print_summary(summary, args.dry_run)

        # Return exit code
        if summary["failed"] > 0:
            return 1  # Indicate failures
        else:
            return 0  # Success

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        await conn.close()
        logger.info("✅ Disconnected from Neo4j")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
