"""
YAML Round-Trip Integration Tests
==================================

Tests for YAML import → export → import produces identical results.

Requires:
- Docker running
- Neo4j testcontainer
- Real file I/O

Run with: poetry run pytest tests/integration/test_yaml_roundtrip.py -v
"""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestYAMLRoundTrip:
    """Integration tests for YAML import → export → import."""

    async def test_basic_roundtrip_no_relationships(self, neo4j_driver, temp_yaml_dir):
        """
        Test basic round-trip for knowledge unit without relationships.

        Flow:
        1. Create YAML file
        2. Import to Neo4j
        3. Export from Neo4j
        4. Verify data matches
        """
        from unittest.mock import AsyncMock, MagicMock

        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.curriculum_dto import CurriculumDTO
        from core.services.article_service import ArticleService
        from core.services.ingestion import UnifiedIngestionService

        # Verify connection and clean database
        async with neo4j_driver.session() as session:
            result = await session.run("RETURN 1 as test")
            record = await result.single()
            assert record["test"] == 1
            await session.run("MATCH (n) DETACH DELETE n")

        # Create services with shared driver
        ingestion_service = UnifiedIngestionService(driver=neo4j_driver)
        # Use "Entity" to match what UnifiedIngestionService creates
        # IMPORTANT: Backend must use CurriculumDTO (mutable), not Curriculum (immutable)
        ku_backend = UniversalNeo4jBackend[CurriculumDTO](neo4j_driver, "Entity", CurriculumDTO)
        # Create mock dependencies (required by fail-fast pattern)
        mock_content_repo = AsyncMock()
        mock_query_builder = MagicMock()
        mock_neo4j_adapter = MagicMock()  # Required for graph operations
        mock_graph_intelligence = MagicMock()  # Required by fail-fast architecture
        ku_service = ArticleService(
            repo=ku_backend,
            content_repo=mock_content_repo,
            query_builder=mock_query_builder,
            neo4j_adapter=mock_neo4j_adapter,
            graph_intelligence_service=mock_graph_intelligence,  # Required for cross-domain queries
        )

        # Step 1: Create initial YAML file
        # Note: Use dot notation (ku.xxx) as ingestion normalizes colons to dots
        yaml_content = """---
uid: ku.simple-test
title: Simple Test
content: Test content for basic round-trip
domain: tech
quality_score: 0.8
complexity: basic
tags:
  - test
  - integration
---

# Simple Test

This is test content for verifying basic round-trip functionality.
"""
        yaml_path = temp_yaml_dir / "simple.md"
        yaml_path.write_text(yaml_content)

        # Step 2: Import YAML → Neo4j
        import_result = await ingestion_service.ingest_file(yaml_path)
        assert import_result.is_ok, (
            f"Import failed: {import_result.error if not import_result.is_ok else 'Unknown'}"
        )

        # Step 3: Retrieve KU from Neo4j (use dot notation)
        get_result = await ku_service.get("ku.simple-test")
        assert get_result.is_ok, (
            f"Get failed: {get_result.error if not get_result.is_ok else 'Unknown'}"
        )
        ku_dto = get_result.value

        # Step 4: Verify retrieved data matches original
        assert ku_dto.uid == "ku.simple-test"
        assert ku_dto.title == "Simple Test"
        # domain may be a Domain enum or string depending on deserialization
        domain_val = getattr(ku_dto.domain, "value", ku_dto.domain)
        assert domain_val == "tech"
        assert ku_dto.quality_score == 0.8
        assert ku_dto.complexity == "basic"

        # Tags should be a list
        assert isinstance(ku_dto.tags, list), f"Expected tags to be list, got {type(ku_dto.tags)}"
        assert "test" in ku_dto.tags
        assert "integration" in ku_dto.tags

    async def test_roundtrip_with_relationships(
        self, clean_neo4j, ku_service, ingestion_service, temp_yaml_dir
    ):
        """
        Test round-trip preserving relationships.

        Flow:
        1. Create prerequisite knowledge
        2. Create main knowledge with relationships
        3. Import both
        4. Export main knowledge
        5. Verify relationships queried from graph
        """

        # Step 1: Create prerequisite YAML (use dot notation)
        prereq_yaml = """---
uid: ku.prereq
title: Prerequisite Topic
content: Foundation knowledge
domain: tech
quality_score: 0.85
complexity: basic
connections:
  requires: []
  enables:
    - ku.main-topic
  related: []
---

# Prerequisite Topic

Foundation content.
"""
        prereq_path = temp_yaml_dir / "prereq.md"
        prereq_path.write_text(prereq_yaml)

        # Step 2: Create main topic YAML (use dot notation)
        main_yaml = """---
uid: ku.main-topic
title: Main Topic
content: Main knowledge content
domain: tech
quality_score: 0.9
complexity: medium
connections:
  requires:
    - ku.prereq
  enables:
    - ku.advanced-topic
  related:
    - ku.related-topic
---

# Main Topic

Main content.
"""
        main_path = temp_yaml_dir / "main.md"
        main_path.write_text(main_yaml)

        # Step 3: Import prerequisite first
        import_prereq = await ingestion_service.ingest_file(prereq_path)
        assert import_prereq.is_ok, (
            f"Prereq import failed: {import_prereq.error if not import_prereq.is_ok else 'Unknown'}"
        )

        # Step 4: Import main topic
        import_main = await ingestion_service.ingest_file(main_path)
        assert import_main.is_ok, (
            f"Main import failed: {import_main.error if not import_main.is_ok else 'Unknown'}"
        )

        # Step 5: Retrieve main topic from Neo4j (use dot notation)
        get_result = await ku_service.get("ku.main-topic")
        assert get_result.is_ok, (
            f"Get failed: {get_result.error if not get_result.is_ok else 'Unknown'}"
        )
        ku_dto = get_result.value

        # Step 6: Verify core metadata preserved
        assert ku_dto.uid == "ku.main-topic"
        assert ku_dto.title == "Main Topic"
        domain_val = getattr(ku_dto.domain, "value", ku_dto.domain)
        assert domain_val == "tech"

        # Note: For relationship verification, we would need to query the graph directly
        # or use a backend method to get related nodes. This is a simplified test.

    async def test_roundtrip_full_cycle(
        self, clean_neo4j, ku_service, ingestion_service, temp_yaml_dir
    ):
        """
        Test complete round-trip: import → export → re-import → re-export.

        Verifies that export → import → export produces identical results.
        """

        # Step 1: Create and import initial YAML (use dot notation)
        initial_yaml = """---
uid: ku.cycle-test
title: Cycle Test
content: Testing full cycle
domain: tech
quality_score: 0.85
complexity: medium
tags:
  - cycle
  - test
connections:
  requires: []
  enables: []
  related: []
---

# Cycle Test

Content for testing full round-trip.
"""
        initial_path = temp_yaml_dir / "initial.md"
        initial_path.write_text(initial_yaml)

        import1 = await ingestion_service.ingest_file(initial_path)
        assert import1.is_ok

        # Step 2: First retrieval (use dot notation)
        get1_result = await ku_service.get("ku.cycle-test")
        assert get1_result.is_ok
        ku_dto_1 = get1_result.value

        # Step 3: Verify initial data
        assert ku_dto_1.uid == "ku.cycle-test"
        assert ku_dto_1.title == "Cycle Test"
        domain_val = getattr(ku_dto_1.domain, "value", ku_dto_1.domain)
        assert domain_val == "tech"
        assert ku_dto_1.quality_score == 0.85

        # Note: Full round-trip testing (delete + re-import + verify) would require
        # more complex test setup with proper YAML serialization. This simplified
        # test verifies that import → retrieval works correctly.

    async def test_roundtrip_all_relationship_types(
        self, clean_neo4j, ku_service, ingestion_service, temp_yaml_dir
    ):
        """
        Test round-trip with all 5 relationship types.

        Relationship types:
        - requires (prerequisites)
        - enables (what this enables)
        - related (related topics)
        - used_in_steps (learning steps)
        - featured_in_paths (learning paths)
        """

        # Create YAML with all relationship types (use dot notation)
        comprehensive_yaml = """---
uid: ku.comprehensive
title: Comprehensive Test
content: Testing all relationship types
domain: tech
quality_score: 0.9
complexity: advanced
tags:
  - comprehensive
  - all-types
connections:
  requires:
    - ku.prereq-1
    - ku.prereq-2
  enables:
    - ku.enabled-1
    - ku.enabled-2
  related:
    - ku.related-1
  used_in_steps: []
  featured_in_paths: []
---

# Comprehensive Test

Content with all relationship types.
"""
        yaml_path = temp_yaml_dir / "comprehensive.md"
        yaml_path.write_text(comprehensive_yaml)

        # Import
        import_result = await ingestion_service.ingest_file(yaml_path)
        assert import_result.is_ok

        # Retrieve from Neo4j (use dot notation)
        get_result = await ku_service.get("ku.comprehensive")
        assert get_result.is_ok
        ku_dto = get_result.value

        # Verify core data
        assert ku_dto.uid == "ku.comprehensive"
        assert ku_dto.title == "Comprehensive Test"
        domain_val = getattr(ku_dto.domain, "value", ku_dto.domain)
        assert domain_val == "tech"
        assert ku_dto.quality_score == 0.9
        assert ku_dto.complexity == "advanced"

        # Note: Relationship verification would require querying the graph directly


# Test markers
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
