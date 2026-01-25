#!/usr/bin/env python3
"""
Ingest nous files to Neo4j.

Directly calls the UnifiedIngestionService to ingest all generated
KU files from /home/mike/0bsidian/skuel/nous/ to Neo4j.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from core.services.ingestion import UnifiedIngestionService
from core.utils.logging import get_logger

# Load .env file from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE, override=True)

logger = get_logger("skuel.ingest_nous")

NOUS_PATH = Path("/home/mike/0bsidian/skuel/nous")


async def main():
    """Ingest nous files to Neo4j."""
    print(f"Ingesting nous files from: {NOUS_PATH}")

    # Get Neo4j config from environment
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    print(f"Loaded from .env: {ENV_FILE}")
    print(f"User: {neo4j_user}, Password: {neo4j_password[:5] if neo4j_password else 'NOT SET'}...")

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

        # Create ingestion service
        ingestion_service = UnifiedIngestionService(driver)
        print("✅ Ingestion service created")

        # Count files first
        md_files = list(NOUS_PATH.glob("*.md"))
        print(f"Found {len(md_files)} markdown files")

        # Ingest files one by one (more reliable than batch)
        print("\nStarting ingestion (file-by-file)...")
        successful = 0
        failed = 0
        errors = []

        for i, file_path in enumerate(md_files):
            if file_path.name == "moc_nous.md":
                # Skip the MOC file itself for now
                continue

            result = await ingestion_service.ingest_file(file_path)

            if result.is_ok:
                successful += 1
                if successful <= 5:  # Show first 5
                    print(f"  ✓ {file_path.name}")
                elif successful == 6:
                    print("  ... (continuing)")
            else:
                failed += 1
                errors.append({"file": file_path.name, "error": str(result.error)})
                if failed <= 3:
                    print(f"  ✗ {file_path.name}: {result.error}")

            # Progress indicator every 50 files
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i + 1}/{len(md_files)} files")

        print("\n✅ Ingestion complete!")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        if errors:
            print("\n   Sample errors:")
            for err in errors[:5]:
                print(f"     - {err['file']}: {err['error']}")

    finally:
        await driver.close()
        print("\n✅ Neo4j connection closed")


if __name__ == "__main__":
    asyncio.run(main())
