#!/usr/bin/env python3
"""
Example ingestion script for Obsidian vault using the new bulk operations.

This demonstrates the power of the generic programming evolution:
- Bulk ingestion of thousands of files
- Automatic relationship creation
- Vector modeling for learning paths
- 100x faster than individual saves
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from neo4j import AsyncGraphDatabase

from core.ingestion.bulk_ingestion import BulkIngestionEngine
from core.ingestion.vector_manager import Vector, VectorManager, VectorSpace
from core.models.curriculum.curriculum import Curriculum as KnowledgeUnit
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

# Primary aliases
KnowledgeUnitPure = KnowledgeUnit
LifePrinciplePure = KnowledgeUnit

logger = get_logger(__name__)


class VaultIngester:
    """
    Ingests Obsidian vault content into Neo4j using bulk operations.

    This class demonstrates:
    - Generic bulk ingestion patterns
    - Automatic relationship handling
    - Vector creation for learning trajectories
    - Efficient batch processing
    """

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> None:
        """Initialize with Neo4j connection."""
        self.driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.vector_manager = VectorManager(self.driver)

    async def close(self):
        """Close database connection."""
        await self.driver.close()

    def collect_knowledge_units(self, vault_path: Path) -> list[dict[str, Any]]:
        """
        Collect all KnowledgeUnit YAML files from vault.

        Args:
            vault_path: Path to Obsidian vault

        Returns:
            List of KnowledgeUnit data dictionaries
        """
        items = []
        ku_path = vault_path / "knowledge_units"

        if not ku_path.exists():
            logger.warning(f"Knowledge units directory not found: {ku_path}")
            return items

        for yaml_file in ku_path.glob("**/*.yml"):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                ku = data.get("Ku")
                if ku:
                    # Normalize connections
                    conn = ku.get("connections", {}) or {}
                    ku["connections"] = {
                        "related": conn.get("related", []) or [],
                        "supports": conn.get("supports", []) or [],
                        "enables": conn.get("enables", []) or [],
                        "requires": conn.get("requires", []) or [],
                        "mentions_in": conn.get("mentions_in", []) or [],
                    }
                    items.append(ku)
                    logger.debug(f"Collected KnowledgeUnit: {ku['uid']}")
            except Exception as e:
                logger.error(f"Failed to parse {yaml_file}: {e}")

        logger.info(f"Collected {len(items)} KnowledgeUnits")
        return items

    def collect_life_principles(self, vault_path: Path) -> list[dict[str, Any]]:
        """
        Collect all LifePrinciple YAML files from vault.

        Args:
            vault_path: Path to Obsidian vault

        Returns:
            List of LifePrinciple data dictionaries
        """
        items = []
        lp_path = vault_path / "principles"

        if not lp_path.exists():
            logger.warning(f"Principles directory not found: {lp_path}")
            return items

        for yaml_file in lp_path.glob("**/*.yml"):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                lp = data.get("LifePrinciple")
                if lp:
                    # Normalize connections
                    conn = lp.get("connections", {}) or {}
                    lp["connections"] = {
                        "related": conn.get("related", []) or [],
                        "supports": conn.get("supports", []) or [],
                        "mentions_in": conn.get("mentions_in", []) or [],
                    }
                    items.append(lp)
                    logger.debug(f"Collected LifePrinciple: {lp['uid']}")
            except Exception as e:
                logger.error(f"Failed to parse {yaml_file}: {e}")

        logger.info(f"Collected {len(items)} LifePrinciples")
        return items

    async def ingest_knowledge_units(
        self, vault_path: Path, batch_size: int = 500
    ) -> Result[dict[str, Any]]:
        """
        Bulk ingest KnowledgeUnits with relationships.

        Args:
            vault_path: Path to Obsidian vault,
            batch_size: Number of items per transaction

        Returns:
            Result with ingestion statistics
        """
        items = self.collect_knowledge_units(vault_path)
        if not items:
            return Result.ok({"message": "No KnowledgeUnits found"})

        # Create bulk ingestion engine
        engine = BulkIngestionEngine(
            driver=self.driver, entity_type=KnowledgeUnitPure, entity_label="Ku"
        )

        # Ensure constraints exist
        await engine.ensure_constraints()

        # Define relationship configuration
        rel_config = {
            "domains": {"rel_type": "IN_DOMAIN", "target_label": "KnowledgeDomain"},
            "related": {"rel_type": "RELATED_TO", "target_label": "Ku"},
            "supports": {"rel_type": "SUPPORTS", "target_label": "Ku"},
            "enables": {"rel_type": "ENABLES", "target_label": "Ku"},
            "requires": {"rel_type": "REQUIRES", "target_label": "Ku"},
            "mentions_in": {"rel_type": "MENTIONS_IN", "target_label": "JournalEntry"},
        }

        # Convert to domain objects
        entities = []
        for item in items:
            try:
                # Create KnowledgeUnitPure instance
                entity = KnowledgeUnitPure(
                    uid=item["uid"],
                    title=item["title"],
                    type=item.get("type", "concept"),
                    status=item.get("status", "draft"),
                    description=item.get("description", ""),
                    content=item.get("content", ""),
                    domains=item.get("domains", []),
                    tags=item.get("tags", []),
                    metadata=item.get("metadata", {}),
                )
                entities.append(entity)
            except Exception as e:
                logger.error(f"Failed to create entity for {item['uid']}: {e}")

        # Perform bulk ingestion with relationships
        logger.info(f"Starting bulk ingestion of {len(entities)} KnowledgeUnits")
        result = await engine.upsert_with_relationships(
            entities=entities, relationship_config=rel_config, batch_size=batch_size
        )

        if result.is_ok():
            stats = result.unwrap()
            logger.info(f"Ingestion complete: {stats}")
            return Result.ok(stats)
        else:
            return result

    async def ingest_life_principles(
        self, vault_path: Path, batch_size: int = 500
    ) -> Result[dict[str, Any]]:
        """
        Bulk ingest LifePrinciples with relationships.

        Args:
            vault_path: Path to Obsidian vault,
            batch_size: Number of items per transaction

        Returns:
            Result with ingestion statistics
        """
        items = self.collect_life_principles(vault_path)
        if not items:
            return Result.ok({"message": "No LifePrinciples found"})

        # Create bulk ingestion engine
        engine = BulkIngestionEngine(
            driver=self.driver, entity_type=LifePrinciplePure, entity_label="LifePrinciple"
        )

        # Ensure constraints exist
        await engine.ensure_constraints()

        # Define relationship configuration

        # Perform bulk ingestion
        logger.info(f"Starting bulk ingestion of {len(items)} LifePrinciples")
        result = await engine.upsert_batch(
            entities=items, batch_size=batch_size, template_name="bulk_life_principles"
        )

        if result.is_ok():
            stats = result.unwrap()
            logger.info(f"Ingestion complete: {stats}")
            return Result.ok(stats)
        else:
            return result

    async def create_learning_vectors(self, vault_path: Path) -> Result[list[str]]:
        """
        Create vectors for learning paths and trajectories.

        Args:
            vault_path: Path to Obsidian vault

        Returns:
            Result with created vector UIDs
        """
        vectors_path = vault_path / "vectors"
        if not vectors_path.exists():
            logger.info("No vectors directory found")
            return Result.ok([])

        created_uids = []

        for yaml_file in vectors_path.glob("**/*.yml"):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                vec_data = data.get("Vector")
                if vec_data:
                    # Create Vector instance
                    vector = Vector(
                        uid=vec_data["uid"],
                        title=vec_data["title"],
                        space=VectorSpace(vec_data["space"]),
                        components=vec_data["components"],
                        magnitude=vec_data.get("magnitude"),
                        origin=vec_data.get("origin"),
                        target=vec_data.get("target"),
                        notes=vec_data.get("notes"),
                        connections=vec_data.get("connections", {}),
                    )

                    # Create in Neo4j
                    result = await self.vector_manager.create_vector(vector)
                    if result.is_ok():
                        created_uids.append(result.unwrap())
                        (logger.info(f"Created vector: {vector.uid}"),)
                    else:
                        logger.error(f"Failed to create vector {vector.uid}: {result.error}")

            except Exception as e:
                logger.error(f"Failed to process {yaml_file}: {e}")

        logger.info(f"Created {len(created_uids)} vectors")
        return Result.ok(created_uids)

    async def run_full_ingestion(self, vault_path: Path) -> Result[dict[str, Any]]:
        """
        Run complete vault ingestion.

        This demonstrates the power of bulk operations:
        - Thousands of entities in seconds
        - Automatic relationship creation
        - Vector modeling for trajectories
        """
        start_time = datetime.now()
        results = {}

        # Ingest KnowledgeUnits
        logger.info("=" * 60)
        logger.info("PHASE 1: Ingesting KnowledgeUnits")
        logger.info("=" * 60)
        ku_result = await self.ingest_knowledge_units(vault_path)
        if ku_result.is_ok():
            results["knowledge_units"] = ku_result.unwrap()

        # Ingest LifePrinciples
        logger.info("=" * 60)
        logger.info("PHASE 2: Ingesting LifePrinciples")
        logger.info("=" * 60)
        lp_result = await self.ingest_life_principles(vault_path)
        if lp_result.is_ok():
            results["life_principles"] = lp_result.unwrap()

        # Create Vectors
        logger.info("=" * 60)
        logger.info("PHASE 3: Creating Learning Vectors")
        logger.info("=" * 60)
        vec_result = await self.create_learning_vectors(vault_path)
        if vec_result.is_ok():
            results["vectors"] = len(vec_result.unwrap())

        duration = (datetime.now() - start_time).total_seconds()
        results["total_duration_seconds"] = duration

        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info(f"Total time: {duration:.2f} seconds")
        logger.info("=" * 60)

        return Result.ok(results)


async def main():
    """Run example ingestion."""
    import os

    # Get configuration from environment or use defaults
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
    vault_path = Path(os.getenv("VAULT_PATH", "/home/mike/vault"))

    logger.info("Starting vault ingestion")
    logger.info(f"Vault path: {vault_path}")
    logger.info(f"Neo4j URI: {neo4j_uri}")

    ingester = VaultIngester(neo4j_uri, neo4j_user, neo4j_password)

    try:
        result = await ingester.run_full_ingestion(vault_path)
        if result.is_ok():
            stats = result.unwrap()
            print("\n✅ INGESTION SUCCESS")
            print(f"Total duration: {stats['total_duration_seconds']:.2f} seconds")

            if "knowledge_units" in stats:
                ku = stats["knowledge_units"]
                print("\nKnowledgeUnits:")
                print(f"  - Processed: {ku.get('total_processed', 0)}")
                print(f"  - Created: {ku.get('nodes_created', 0)}")
                print(f"  - Updated: {ku.get('nodes_updated', 0)}")
                print(f"  - Relationships: {ku.get('relationships_created', 0)}")

            if "life_principles" in stats:
                lp = stats["life_principles"]
                print("\nLifePrinciples:")
                print(f"  - Processed: {lp.get('total_processed', 0)}")
                print(f"  - Created: {lp.get('nodes_created', 0)}")
                print(f"  - Updated: {lp.get('nodes_updated', 0)}")

            if "vectors" in stats:
                print(f"\nVectors created: {stats['vectors']}")
        else:
            print(f"\n❌ INGESTION FAILED: {result.error}")

    finally:
        await ingester.close()


if __name__ == "__main__":
    asyncio.run(main())
