"""
Entity Chunking Service
=======================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY SubmissionsCoreService for content processing, not a duplicate.

Service for processing curriculum entity content with automatic chunking,
metadata extraction, and search optimization.

Handles the separation of concerns:
- Curriculum: Lean graph metadata (the domain model)
- CurriculumContent: Rich content with chunks (content for curriculum entities)
- ContentMetadata: Analytics and search optimization (metadata for curriculum entities)

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into SubmissionsCoreService for content create/update operations
- Specialized utility for RAG content chunking
- See `/core/services/ps/` for architecture overview
"""

from typing import TypedDict

from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import DEFAULT_CHUNKING_PARAMS, ChunkingParams
from core.models.ps_content.content_metadata import ContentMetadata
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.knowledge_chunking")


# TypedDict for content statistics (fixes MyPy index errors)
class ComplexityDistribution(TypedDict):
    """Distribution of complexity levels."""

    basic: int
    intermediate: int
    advanced: int


class ContentFeatures(TypedDict):
    """Content feature flags and counts."""

    with_code: int
    with_examples: int
    with_exercises: int
    with_media: int
    comprehensive: int


class ContentStatistics(TypedDict):
    """Aggregated content statistics for multiple knowledge units."""

    total_units: int
    total_words: int
    total_chunks: int
    total_reading_time: float
    chunk_type_distribution: dict[str, int]  # Dynamic chunk types
    complexity_distribution: ComplexityDistribution
    content_features: ContentFeatures
    average_words_per_unit: float  # Computed field
    average_chunks_per_unit: float  # Computed field
    average_reading_time: float  # Computed field


class EntityChunkingService:
    """
    Service for processing curriculum entity content into chunks and metadata.

    This service handles:
    1. Creating CurriculumContent with automatic chunking
    2. Generating ContentMetadata for search and analytics
    3. Managing the relationship between Curriculum, Content, and Metadata
    4. Providing search and retrieval operations on chunks

    This is a pure in-memory processing service — it does not query Neo4j directly.
    All graph persistence is handled by the calling service (SubmissionsCoreService).
    """

    def __init__(self) -> None:
        """Initialize the chunking service"""
        self.logger = logger
        self._content_cache: dict[str, CurriculumContent] = {}
        self._metadata_cache: dict[str, ContentMetadata] = {}

    # ==========================================================================
    # CONTENT PROCESSING
    # ==========================================================================

    def process_content_for_ingestion(
        self,
        parent_uid: str,
        content_body: str,
        format: str = "markdown",
        source_path: str | None = None,
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> Result[tuple[CurriculumContent, ContentMetadata]]:
        """
        Process knowledge content during ingestion (simplified interface).

        This method is designed for use during ingestion when we have raw
        entity data but not a full PathStep domain model yet. It creates chunks
        and metadata directly from the UID and content.

        Args:
            parent_uid: UID of the knowledge unit (e.g., "ku.python_basics")
            content_body: The raw content text
            format: Content format (markdown/html/text)
            source_path: Original file path if imported
            params: Per-domain chunk-size knobs (defaults to DEFAULT_CHUNKING_PARAMS)

        Returns:
            Result containing tuple of (CurriculumContent, ContentMetadata)
        """
        try:
            # Create CurriculumContent with automatic chunking
            content = CurriculumContent.create(
                unit_uid=parent_uid,
                body=content_body,
                format=format,
                source_path=source_path,
                chunking_params=params,
            )

            # Generate metadata from content
            metadata = ContentMetadata.from_content(content)

            # Cache for quick retrieval
            self._content_cache[parent_uid] = content
            self._metadata_cache[parent_uid] = metadata

            self.logger.info(
                f"Processed content for {parent_uid}: "
                f"{content.word_count} words, {content.chunk_count} chunks"
            )

            return Result.ok((content, metadata))

        except ValueError as e:
            return Result.fail(Errors.validation(f"Invalid content: {e!s}", field="content_body"))
        except (TypeError, AttributeError, KeyError) as e:
            self.logger.error(f"Failed to process content: {e}")
            return Result.fail(
                Errors.system(
                    f"Content processing failed: {e!s}", operation="process_content_for_ingestion"
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Failed to process content: {e}")
            return Result.fail(
                Errors.system(
                    f"Content processing failed: {e!s}", operation="process_content_for_ingestion"
                )
            )

    # ==========================================================================
    # METADATA OPERATIONS
    # ==========================================================================

    def get_metadata(self, knowledge_uid: str) -> Result[ContentMetadata]:
        """
        Get metadata for a knowledge unit.

        Args:
            knowledge_uid: UID of the knowledge unit

        Returns:
            Result containing ContentMetadata
        """
        metadata = self._metadata_cache.get(knowledge_uid)
        if not metadata:
            return Result.fail(
                Errors.not_found(f"Metadata not found for knowledge: {knowledge_uid}")
            )

        return Result.ok(metadata)

    # ==========================================================================
    # CACHE MANAGEMENT
    # ==========================================================================

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about cached content"""
        return {
            "cached_content": len(self._content_cache),
            "cached_metadata": len(self._metadata_cache),
            "total_chunks": sum(content.chunk_count for content in self._content_cache.values()),
            "total_words": sum(content.word_count for content in self._content_cache.values()),
        }

    def __str__(self) -> str:
        """String representation"""
        cache_stats = self.get_cache_stats()
        return (
            f"EntityChunkingService("
            f"cached={cache_stats['cached_content']}, "
            f"chunks={cache_stats['total_chunks']})"
        )
