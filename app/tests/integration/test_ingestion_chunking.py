"""
Integration Test: Automatic Chunking During Ingestion
=======================================================

Tests that KU entities automatically generate chunks during ingestion
without requiring explicit chunking calls.

Phase 1 Implementation (January 2026) - Automatic Chunking
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from core.services.ingestion import UnifiedIngestionService
from core.services.ku_chunking_service import KuChunkingService


@pytest.mark.asyncio
async def test_ingest_file_creates_chunks(neo4j_driver):
    """Test that ingesting a KU file automatically creates chunks"""
    # Given: A markdown file with KU content
    ku_content = """---
type: knowledge
title: Python Basics
domain: technology
---

# Introduction to Python

Python is a high-level programming language.

## Variables

Variables store data values. You can create a variable like this:

```python
x = 5
name = "John"
```

## Functions

Functions are reusable blocks of code:

```python
def greet(name):
    return f"Hello, {name}!"
```

## Summary

Python is easy to learn and powerful.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled
        chunking_service = KuChunkingService()
        ingestion_service = UnifiedIngestionService(
            driver=neo4j_driver,
            chunking_service=chunking_service,
        )

        # When: Ingesting the file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, (
            f"Ingestion failed: {result.expect_error() if result.is_error else 'unknown'}"
        )
        ingestion_data = result.value

        # Then: Chunks were generated
        assert ingestion_data["chunks_generated"] is True, "Chunks should be generated for KU"
        assert ingestion_data["entity_type"] == "curriculum", "Entity type should be curriculum"

        # Then: Chunks are in the chunking service cache
        ku_uid = ingestion_data["uid"]
        chunks_result = await chunking_service.get_chunks_for_knowledge(ku_uid)

        assert chunks_result.is_ok, "Should be able to retrieve chunks"
        chunks = chunks_result.value
        assert len(chunks) > 0, "Should have at least one chunk"

        # Verify chunk types detected
        chunk_types = {chunk.chunk_type for chunk in chunks}
        assert len(chunk_types) > 0, "Should have detected chunk types"

        # Verify content was chunked (should have multiple chunks for this content)
        assert len(chunks) >= 3, f"Expected at least 3 chunks, got {len(chunks)}"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_chunking_failure_does_not_fail_ingestion(neo4j_driver):
    """Test that chunking failure doesn't prevent successful ingestion"""
    # Given: A KU file
    ku_content = """---
type: knowledge
title: Short KU
domain: technology
---

Just a short piece of content.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService WITHOUT chunking service (None)
        ingestion_service = UnifiedIngestionService(
            driver=neo4j_driver,
            chunking_service=None,  # No chunking service
        )

        # When: Ingesting the file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion still succeeds
        assert result.is_ok, "Ingestion should succeed even without chunking"
        ingestion_data = result.value

        # Then: Chunks were NOT generated (graceful degradation)
        assert ingestion_data["chunks_generated"] is False, "No chunks should be generated"
        assert ingestion_data["success"] is True, "Ingestion itself should succeed"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_non_ku_entities_skip_chunking(neo4j_driver):
    """Test that non-KU entities don't attempt chunking"""
    # Given: A Task file (not KU)
    task_content = """---
type: task
title: Complete project
status: active
---

This is a task description.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(task_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled
        chunking_service = KuChunkingService()
        ingestion_service = UnifiedIngestionService(
            driver=neo4j_driver,
            chunking_service=chunking_service,
        )

        # When: Ingesting a non-KU file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, "Ingestion should succeed"
        ingestion_data = result.value

        # Then: Chunks were NOT generated (only for KU entities)
        assert ingestion_data["chunks_generated"] is False, "Tasks should not be chunked"
        assert ingestion_data["entity_type"] == "task", "Entity type should be task"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_ku_with_minimal_content_generates_chunks(neo4j_driver):
    """Test that KU with minimal content still generates chunks"""
    # Given: A KU file with minimal content (just one sentence)
    ku_content = """---
type: knowledge
title: Minimal KU
domain: technology
---

Python is a programming language.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled
        chunking_service = KuChunkingService()
        ingestion_service = UnifiedIngestionService(
            driver=neo4j_driver,
            chunking_service=chunking_service,
        )

        # When: Ingesting a KU with minimal content
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, "Ingestion should succeed"
        ingestion_data = result.value

        # Then: Chunks were generated even for minimal content
        assert ingestion_data["chunks_generated"] is True, (
            "Should generate chunks for minimal content"
        )

        # Verify at least one chunk exists
        ku_uid = ingestion_data["uid"]
        chunks_result = await chunking_service.get_chunks_for_knowledge(ku_uid)
        assert chunks_result.is_ok, "Should be able to retrieve chunks"
        chunks = chunks_result.value
        assert len(chunks) >= 1, "Should have at least one chunk for minimal content"

    finally:
        # Cleanup
        temp_path.unlink()
