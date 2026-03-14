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
- See `/core/services/lesson/README.md` for architecture overview
"""

from operator import itemgetter
from typing import Any, TypedDict

from core.models.lesson.lesson import Lesson
from core.models.article_content.content import CurriculumContent
from core.models.article_content.content_chunks import ContentChunk, ContentChunkType
from core.models.article_content.content_metadata import ContentMetadata
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

    async def process_content_for_ingestion(
        self,
        parent_uid: str,
        content_body: str,
        format: str = "markdown",
        source_path: str | None = None,
    ) -> Result[tuple[CurriculumContent, ContentMetadata]]:
        """
        Process knowledge content during ingestion (simplified interface).

        This method is designed for use during ingestion when we have raw
        entity data but not a full Lesson domain model yet. It creates chunks
        and metadata directly from the UID and content.

        Args:
            parent_uid: UID of the knowledge unit (e.g., "ku.python_basics")
            content_body: The raw content text
            format: Content format (markdown/html/text)
            source_path: Original file path if imported

        Returns:
            Result containing tuple of (CurriculumContent, ContentMetadata)
        """
        try:
            # Create CurriculumContent with automatic chunking
            content = CurriculumContent.create(
                unit_uid=parent_uid, body=content_body, format=format, source_path=source_path
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
        except Exception as e:
            self.logger.error(f"Failed to process content: {e}")
            return Result.fail(
                Errors.system(
                    f"Content processing failed: {e!s}", operation="process_content_for_ingestion"
                )
            )

    async def process_ku_content(
        self,
        knowledge: Lesson,
        content_body: str,
        format: str = "markdown",
        source_path: str | None = None,
    ) -> Result[tuple[CurriculumContent, ContentMetadata]]:
        """
        Process knowledge content to create rich content and metadata.

        Args:
            knowledge: The Knowledge domain model,
            content_body: The raw content text,
            format: Content format (markdown/html/text),
            source_path: Original file path if imported

        Returns:
            Result containing tuple of (CurriculumContent, ContentMetadata)
        """
        try:
            # Create CurriculumContent with automatic chunking
            content = CurriculumContent.create(
                unit_uid=knowledge.uid, body=content_body, format=format, source_path=source_path
            )

            # Generate metadata from content
            metadata = ContentMetadata.from_content(content)

            # Cache for quick retrieval
            self._content_cache[knowledge.uid] = content
            self._metadata_cache[knowledge.uid] = metadata

            self.logger.info(
                f"Processed content for {knowledge.uid}: "
                f"{content.word_count} words, {content.chunk_count} chunks"
            )

            return Result.ok((content, metadata))

        except ValueError as e:
            return Result.fail(Errors.validation(f"Invalid content: {e!s}", field="content_body"))
        except Exception as e:
            self.logger.error(f"Failed to process content: {e}")
            return Result.fail(
                Errors.system(f"Content processing failed: {e!s}", operation="process_ku_content")
            )

    async def update_article_content(
        self, knowledge: Lesson, new_content_body: str
    ) -> Result[tuple[CurriculumContent, ContentMetadata]]:
        """
        Update existing article content with new text.

        This will:
        1. Create new CurriculumContent with fresh chunks
        2. Regenerate metadata
        3. Update caches

        Args:
            knowledge: The Knowledge domain model,
            new_content_body: The new content text

        Returns:
            Result containing updated (CurriculumContent, ContentMetadata)
        """
        # Get existing content to preserve format and source
        existing = self._content_cache.get(knowledge.uid)
        format = existing.format if existing else "markdown"
        source_path = existing.source_path if existing else None

        return await self.process_ku_content(
            knowledge=knowledge,
            content_body=new_content_body,
            format=format,
            source_path=source_path,
        )

    # ==========================================================================
    # CHUNK OPERATIONS
    # ==========================================================================

    async def get_chunks_for_knowledge(
        self, knowledge_uid: str, chunk_type: ContentChunkType | None = None
    ) -> Result[list[ContentChunk]]:
        """
        Get chunks for a knowledge unit, optionally filtered by type.

        Args:
            knowledge_uid: UID of the knowledge unit,
            chunk_type: Optional chunk type filter

        Returns:
            Result containing list of ContentChunk objects
        """
        content = self._content_cache.get(knowledge_uid)
        if not content:
            return Result.fail(
                Errors.not_found(f"Content not found for knowledge: {knowledge_uid}")
            )

        if chunk_type:
            chunks = list(content.get_chunks_by_type(chunk_type))
        else:
            chunks = list(content.chunks)

        return Result.ok(chunks)

    async def search_chunks(
        self,
        query: str,
        knowledge_uids: list[str] | None = None,
        chunk_types: list[ContentChunkType] | None = None,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """
        Search across chunks with optional filters.

        Args:
            query: Search query,
            knowledge_uids: Optional list of knowledge UIDs to search within,
            chunk_types: Optional chunk types to filter,
            limit: Maximum number of results

        Returns:
            Result containing list of matching chunks with metadata
        """
        results = []

        # Determine which knowledge units to search
        uids_to_search = knowledge_uids if knowledge_uids else list(self._content_cache.keys())

        for uid in uids_to_search:
            content = self._content_cache.get(uid)
            if not content:
                continue

            # Search within chunks
            matching_chunks = content.search_chunks(query)

            for chunk in matching_chunks:
                # Apply chunk type filter if specified
                if chunk_types and chunk.chunk_type not in chunk_types:
                    continue

                # Calculate relevance score
                metadata = self._metadata_cache.get(uid)
                relevance = metadata.search_relevance_score(query) if metadata else 0.5

                results.append(
                    {
                        "knowledge_uid": uid,
                        "chunk": chunk.to_dict(),
                        "relevance_score": relevance,
                        "context_window": chunk.context_window,
                    }
                )

                if len(results) >= limit:
                    break

            if len(results) >= limit:
                break

        # Sort by relevance using operator.itemgetter
        results.sort(key=itemgetter("relevance_score"), reverse=True)

        return Result.ok(results[:limit])

    async def get_learning_chunks(
        self, knowledge_uid: str
    ) -> Result[dict[str, list[ContentChunk]]]:
        """
        Get chunks organized by learning type.

        Returns chunks categorized for learning purposes:
        - definitions: For understanding concepts
        - explanations: For deeper understanding
        - examples: For practical understanding
        - exercises: For practice
        - code: For implementation reference

        Args:
            knowledge_uid: UID of the knowledge unit

        Returns:
            Result containing categorized chunks
        """
        content = self._content_cache.get(knowledge_uid)
        if not content:
            return Result.fail(
                Errors.not_found(f"Content not found for knowledge: {knowledge_uid}")
            )

        categorized = {
            "definitions": list(content.get_definitions()),
            "explanations": list(content.get_chunks_by_type(ContentChunkType.EXPLANATION)),
            "examples": list(content.get_examples()),
            "exercises": list(content.get_exercises()),
            "code": list(content.get_code_blocks()),
            "summaries": list(content.get_chunks_by_type(ContentChunkType.SUMMARY)),
        }

        return Result.ok(categorized)

    # ==========================================================================
    # METADATA OPERATIONS
    # ==========================================================================

    async def get_metadata(self, knowledge_uid: str) -> Result[ContentMetadata]:
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

    async def get_content_statistics(self, knowledge_uids: list[str]) -> Result[ContentStatistics]:
        """
        Get aggregated statistics for multiple knowledge units.

        Args:
            knowledge_uids: List of knowledge UIDs

        Returns:
            Result containing aggregated statistics (typed structure)
        """
        # Initialize with ContentStatistics type (fixes MyPy index errors)
        stats: ContentStatistics = {
            "total_units": len(knowledge_uids),
            "total_words": 0,
            "total_chunks": 0,
            "total_reading_time": 0.0,
            "chunk_type_distribution": {},
            "complexity_distribution": {"basic": 0, "intermediate": 0, "advanced": 0},
            "content_features": {
                "with_code": 0,
                "with_examples": 0,
                "with_exercises": 0,
                "with_media": 0,
                "comprehensive": 0,
            },
            "average_words_per_unit": 0.0,
            "average_chunks_per_unit": 0.0,
            "average_reading_time": 0.0,
        }

        for uid in knowledge_uids:
            content = self._content_cache.get(uid)
            metadata = self._metadata_cache.get(uid)

            if content:
                stats["total_words"] += content.word_count
                stats["total_chunks"] += content.chunk_count

                # Count chunk types
                for chunk in content.chunks:
                    chunk_type = chunk.chunk_type.value
                    stats["chunk_type_distribution"][chunk_type] = (
                        stats["chunk_type_distribution"].get(chunk_type, 0) + 1
                    )

            if metadata:
                stats["total_reading_time"] += metadata.reading_time_minutes

                # Complexity distribution
                complexity = metadata.complexity_level()
                complexity_dist = stats["complexity_distribution"]
                if complexity in complexity_dist:
                    complexity_dist[complexity] += 1  # type: ignore[literal-required]

                # Content features
                if metadata.has_code:
                    stats["content_features"]["with_code"] += 1
                if metadata.has_examples:
                    stats["content_features"]["with_examples"] += 1
                if metadata.has_exercises:
                    stats["content_features"]["with_exercises"] += 1
                if metadata.has_media:
                    stats["content_features"]["with_media"] += 1
                if metadata.is_comprehensive():
                    stats["content_features"]["comprehensive"] += 1

        # Calculate averages
        if stats["total_units"] > 0:
            stats["average_words_per_unit"] = stats["total_words"] / stats["total_units"]
            stats["average_chunks_per_unit"] = stats["total_chunks"] / stats["total_units"]
            stats["average_reading_time"] = stats["total_reading_time"] / stats["total_units"]

        return Result.ok(stats)

    # ==========================================================================
    # CACHE MANAGEMENT
    # ==========================================================================

    def clear_cache(self, knowledge_uid: str | None = None) -> None:
        """
        Clear cached content and metadata.

        Args:
            knowledge_uid: Optional specific UID to clear, otherwise clear all
        """
        if knowledge_uid:
            self._content_cache.pop(knowledge_uid, None)
            self._metadata_cache.pop(knowledge_uid, None)
            self.logger.debug(f"Cleared cache for {knowledge_uid}")
        else:
            self._content_cache.clear()
            self._metadata_cache.clear()
            self.logger.debug("Cleared all content caches")

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about cached content"""
        return {
            "cached_content": len(self._content_cache),
            "cached_metadata": len(self._metadata_cache),
            "total_chunks": sum(content.chunk_count for content in self._content_cache.values()),
            "total_words": sum(content.word_count for content in self._content_cache.values()),
        }

    # ==========================================================================
    # BATCH OPERATIONS
    # ==========================================================================

    async def process_batch(
        self, knowledge_items: list[tuple[Lesson, str]], format: str = "markdown"
    ) -> Result[dict[str, Any]]:
        """
        Process multiple knowledge items in batch.

        Args:
            knowledge_items: List of (Lesson, content_body) tuples,
            format: Content format for all items

        Returns:
            Result containing processing statistics and any errors
        """
        processed = 0
        errors = []
        total_chunks = 0
        total_words = 0

        for knowledge, content_body in knowledge_items:
            result = await self.process_ku_content(
                knowledge=knowledge, content_body=content_body, format=format
            )

            if result.is_ok:
                content, _metadata = result.value
                processed += 1
                total_chunks += content.chunk_count
                total_words += content.word_count
            else:
                error = result.expect_error()
                errors.append({"knowledge_uid": knowledge.uid, "error": error.message})

        return Result.ok(
            {
                "processed": processed,
                "failed": len(errors),
                "total_chunks": total_chunks,
                "total_words": total_words,
                "errors": errors,
            }
        )

    def __str__(self) -> str:
        """String representation"""
        cache_stats = self.get_cache_stats()
        return (
            f"EntityChunkingService("
            f"cached={cache_stats['cached_content']}, "
            f"chunks={cache_stats['total_chunks']})"
        )
