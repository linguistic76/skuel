"""
Lesson Content Model
======================

Rich content storage with automatic chunking for RAG.
Separated from curriculum entities to keep the graph lean while maintaining
rich content for learning and retrieval.

Following three-tier architecture with immutable domain models.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .content_chunks import ContentChunk, ContentChunkType, chunk_content


@dataclass(frozen=True)
class CurriculumContent:
    """
    Immutable content facet for a curriculum entity.

    Stores the actual learning content separately from the lean
    curriculum entity metadata. This enables efficient graph traversal
    while maintaining rich content for the RAG system.

    Connected to curriculum entity via HAS_CONTENT relationship.
    """

    # Identity
    unit_uid: str  # Links to parent curriculum entity uid

    # Content
    body: str  # Full markdown content
    format: str = "markdown"  # Content format (markdown, html, text)
    language: str = "en"  # ISO language code

    # Metadata
    source_path: str | None = None  # Original file path if imported
    body_sha256: str | None = None  # Content hash for integrity
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Chunks - automatically created, not optional
    chunks: tuple[ContentChunk, ...] = ()  # Immutable tuple of chunks

    def __post_init__(self) -> None:
        """Validate, calculate content hash, and create chunks"""
        # Validation
        if not self.unit_uid:
            raise ValueError("unit_uid cannot be empty")
        if not self.body:
            raise ValueError("Content body cannot be empty")

        # Calculate hash if not provided
        if not self.body_sha256:
            content_hash = hashlib.sha256(self.body.encode()).hexdigest()
            object.__setattr__(self, "body_sha256", content_hash)

        # Always create chunks - this is not optional
        if not self.chunks:
            chunk_list = chunk_content(
                content=self.body, parent_uid=self.unit_uid, format=self.format
            )
            # Convert to immutable tuple
            object.__setattr__(self, "chunks", tuple(chunk_list))

    # ==========================================================================
    # BUSINESS LOGIC METHODS
    # ==========================================================================

    @property
    def word_count(self) -> int:
        """Calculate total word count of the content"""
        return len(self.body.split())

    @property
    def chunk_count(self) -> int:
        """Get the number of chunks"""
        return len(self.chunks)

    @property
    def is_markdown(self) -> bool:
        """Check if content is in markdown format"""
        return self.format.lower() == "markdown"

    @property
    def is_chunked(self) -> bool:
        """Verify content has been chunked (always true)"""
        return len(self.chunks) > 0

    def verify_integrity(self) -> bool:
        """Verify content integrity via hash"""
        current_hash = hashlib.sha256(self.body.encode()).hexdigest()
        return current_hash == self.body_sha256

    def get_chunks_by_type(self, chunk_type: ContentChunkType) -> tuple[ContentChunk, ...]:
        """Get all chunks of a specific type"""
        return tuple(c for c in self.chunks if c.chunk_type == chunk_type)

    def search_chunks(self, query: str) -> tuple[ContentChunk, ...]:
        """Simple text search within chunks"""
        query_lower = query.lower()
        return tuple(c for c in self.chunks if query_lower in c.text.lower())

    def get_chunk(self, chunk_index: int) -> ContentChunk | None:
        """Get a specific chunk by index"""
        if 0 <= chunk_index < len(self.chunks):
            return self.chunks[chunk_index]
        return None

    def get_definitions(self) -> tuple[ContentChunk, ...]:
        """Get all definition chunks"""
        return self.get_chunks_by_type(ContentChunkType.DEFINITION)

    def get_examples(self) -> tuple[ContentChunk, ...]:
        """Get all example chunks"""
        return self.get_chunks_by_type(ContentChunkType.EXAMPLE)

    def get_exercises(self) -> tuple[ContentChunk, ...]:
        """Get all exercise chunks"""
        return self.get_chunks_by_type(ContentChunkType.EXERCISE)

    def get_code_blocks(self) -> tuple[ContentChunk, ...]:
        """Get all code chunks"""
        return self.get_chunks_by_type(ContentChunkType.CODE)

    def has_code(self) -> bool:
        """Check if content contains code blocks"""
        return len(self.get_code_blocks()) > 0

    def has_exercises(self) -> bool:
        """Check if content contains exercises"""
        return len(self.get_exercises()) > 0

    def estimated_reading_time(self) -> float:
        """
        Estimate reading time in minutes.
        Assumes 200 words per minute for regular text, 100 for code.
        """
        regular_words = 0
        code_words = 0

        for chunk in self.chunks:
            if chunk.chunk_type == ContentChunkType.CODE:
                code_words += chunk.word_count
            else:
                regular_words += chunk.word_count

        regular_time = regular_words / 200.0
        code_time = code_words / 100.0
        return max(1.0, regular_time + code_time)

    def chunk_statistics(self) -> dict[str, Any]:
        """Get statistics about chunk distribution"""
        # Type-safe chunk type counting
        chunk_types: dict[str, int] = {}

        stats = {
            "total_chunks": len(self.chunks),
            "chunk_types": chunk_types,
            "average_chunk_size": 0,
            "min_chunk_size": 0,
            "max_chunk_size": 0,
        }

        if self.chunks:
            # Count by type
            for chunk in self.chunks:
                chunk_type_value = chunk.chunk_type.value
                chunk_types[chunk_type_value] = chunk_types.get(chunk_type_value, 0) + 1

            # Size statistics
            sizes = [chunk.word_count for chunk in self.chunks]
            stats["average_chunk_size"] = sum(sizes) / len(sizes)
            stats["min_chunk_size"] = min(sizes)
            stats["max_chunk_size"] = max(sizes)

        return stats

    # ==========================================================================
    # CONVERSION METHODS
    # ==========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization"""
        return {
            "unit_uid": self.unit_uid,
            "body": self.body,
            "format": self.format,
            "language": self.language,
            "source_path": self.source_path,
            "body_sha256": self.body_sha256,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "updated_at": self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else self.updated_at,
            "word_count": self.word_count,
            "chunk_count": self.chunk_count,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Export properties for Neo4j node creation"""
        return {
            "unit_uid": self.unit_uid,
            "body": self.body[:5000],  # Limit for Neo4j
            "format": self.format,
            "language": self.language,
            "source_path": self.source_path,
            "body_sha256": self.body_sha256,
            "word_count": self.word_count,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "updated_at": self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CurriculumContent":
        """Create from dictionary (e.g., from database)"""
        # Handle datetime conversion
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Handle chunks conversion
        if "chunks" in data and isinstance(data["chunks"], list):
            chunk_objects = [
                ContentChunk(
                    parent_uid=chunk_data["parent_uid"],
                    chunk_index=chunk_data["chunk_index"],
                    chunk_type=ContentChunkType(chunk_data["chunk_type"]),
                    text=chunk_data["text"],
                    context_before=chunk_data.get("context_before", ""),
                    context_after=chunk_data.get("context_after", ""),
                    heading=chunk_data.get("heading"),
                    metadata=chunk_data.get("metadata", {}),
                )
                for chunk_data in data["chunks"]
                if isinstance(chunk_data, dict)
            ]
            data["chunks"] = tuple(chunk_objects)

        return cls(**data)

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def create(
        cls,
        unit_uid: str,
        body: str,
        format: str = "markdown",
        language: str = "en",
        source_path: str | None = None,
    ) -> "CurriculumContent":
        """
        Factory method to create new CurriculumContent with automatic chunking.

        Args:
            unit_uid: The parent curriculum entity UID,
            body: The content text,
            format: Content format (markdown/html/text),
            language: ISO language code,
            source_path: Original file path if imported

        Returns:
            New CurriculumContent instance with chunks
        """
        return cls(
            unit_uid=unit_uid, body=body, format=format, language=language, source_path=source_path
        )

    def __str__(self) -> str:
        """String representation"""
        return (
            f"CurriculumContent(unit_uid={self.unit_uid}, "
            f"words={self.word_count}, chunks={self.chunk_count})"
        )

    def __repr__(self) -> str:
        """Developer representation"""
        sha_preview = self.body_sha256[:8] if self.body_sha256 else "None"
        return (
            f"CurriculumContent(unit_uid='{self.unit_uid}', "
            f"format='{self.format}', word_count={self.word_count}, "
            f"chunk_count={self.chunk_count}, sha256='{sha_preview}...')"
        )
