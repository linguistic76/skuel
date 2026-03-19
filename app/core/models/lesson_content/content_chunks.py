"""
Content Chunking System
========================

Semantic chunking for RAG (Retrieval Augmented Generation) operations.
All curriculum content is automatically chunked for optimal retrieval.

SKUEL Principle: Chunking is not optional - all content is chunked for retrieval.
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentChunkType(Enum):
    """Types of content chunks for semantic categorization"""

    DEFINITION = "definition"
    EXPLANATION = "explanation"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    CODE = "code"
    SUMMARY = "summary"
    SECTION = "section"
    INTRODUCTION = "introduction"
    CONCLUSION = "conclusion"


@dataclass(frozen=True)
class ContentChunk:
    """
    A semantic chunk of content for optimal retrieval.

    Immutable representation of a content segment with context preservation.
    All content is automatically chunked - this is not optional.
    """

    # Identity
    parent_uid: str  # Parent curriculum entity uid
    chunk_index: int  # Position in document
    chunk_type: ContentChunkType  # Semantic type of content

    # Content
    text: str  # The actual chunk text
    context_before: str  # Text before this chunk (for context)
    context_after: str  # Text after this chunk (for context)

    # Metadata
    heading: str | None = None  # Section heading if applicable
    word_count: int = 0  # Word count of chunk
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional metadata
    embedding: tuple[float, ...] | None = None  # Vector embedding (immutable tuple)

    def __post_init__(self) -> None:
        """Calculate word count after initialization"""
        if not self.word_count:
            object.__setattr__(self, "word_count", len(self.text.split()))

    @property
    def chunk_id(self) -> str:
        """Unique identifier for this chunk"""
        return f"{self.parent_uid}:chunk:{self.chunk_index}"

    @property
    def full_context(self) -> str:
        """Get chunk with surrounding context for RAG"""
        parts = []
        if self.context_before:
            parts.append(self.context_before)
        parts.append(self.text)
        if self.context_after:
            parts.append(self.context_after)
        return "\n".join(parts)

    @property
    def context_window(self) -> str:
        """Get a focused context window for embeddings"""
        # Limit context to avoid diluting the embedding
        before = self.context_before[-200:] if self.context_before else ""
        after = self.context_after[:200] if self.context_after else ""
        return f"{before}\n{self.text}\n{after}".strip()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "chunk_id": self.chunk_id,
            "parent_uid": self.parent_uid,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type.value,
            "text": self.text,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "heading": self.heading,
            "word_count": self.word_count,
            "metadata": self.metadata,
            "has_embedding": self.embedding is not None,
        }

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Export properties for Neo4j storage (with size limits)"""
        return {
            "chunk_id": self.chunk_id,
            "parent_uid": self.parent_uid,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type.value,
            "text": self.text[:1000],  # Limit for Neo4j property size
            "context_before": self.context_before[:200] if self.context_before else "",
            "context_after": self.context_after[:200] if self.context_after else "",
            "heading": self.heading,
            "word_count": self.word_count,
        }

    def similarity_key(self) -> str:
        """Generate a key for similarity comparisons"""
        # Use first 100 chars of text for quick similarity checks
        text_preview = self.text[:100].lower().strip()
        return hashlib.md5(text_preview.encode()).hexdigest()[:8]


class ContentChunkingStrategy:
    """
    Strategy for chunking content into semantic segments.

    This is THE chunking strategy - designed for optimal RAG retrieval.
    """

    # Configuration
    MIN_CHUNK_SIZE = 50  # Minimum words per chunk
    MAX_CHUNK_SIZE = 500  # Maximum words per chunk
    CONTEXT_SIZE = 100  # Words of context to preserve

    @classmethod
    def chunk_markdown(cls, content: str, parent_uid: str) -> list[ContentChunk]:
        """
        Chunk markdown content semantically.

        Strategy:
        1. Split by sections (headers)
        2. Identify chunk types from content patterns
        3. Maintain context between chunks
        4. Optimize for retrieval size
        """
        chunks: list[ContentChunk] = []
        chunk_index = 0

        # Split by headers while preserving them
        sections = cls._split_by_headers(content)

        for section in sections:
            heading = section.get("heading")
            text = section.get("text", "").strip()

            if not text:
                continue

            # Further split large sections
            sub_chunks = cls._split_section(text, heading)

            for i, sub_chunk in enumerate(sub_chunks):
                # Determine context
                context_before = ""
                context_after = ""

                # Get context from previous chunk
                if chunks:
                    context_before = chunks[-1].text[-cls.CONTEXT_SIZE :]

                # Get context from next sub-chunk (if available)
                if i < len(sub_chunks) - 1:
                    context_after = sub_chunks[i + 1]["text"][: cls.CONTEXT_SIZE]

                chunk = ContentChunk(
                    parent_uid=parent_uid,
                    chunk_index=chunk_index,
                    chunk_type=sub_chunk["type"],
                    text=sub_chunk["text"],
                    context_before=context_before,
                    context_after=context_after,
                    heading=heading,
                    metadata=sub_chunk.get("metadata", {}),
                )

                chunks.append(chunk)
                chunk_index += 1

        # Update context_after for the last chunk of each group
        cls._update_chunk_contexts(chunks)

        return chunks

    @classmethod
    def chunk_plain_text(cls, content: str, parent_uid: str) -> list[ContentChunk]:
        """
        Chunk plain text by paragraphs and size limits.
        """
        chunks: list[ContentChunk] = []
        paragraphs = content.split("\n\n")
        chunk_index = 0

        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue

            # Split large paragraphs
            if len(para.split()) > cls.MAX_CHUNK_SIZE:
                sub_paras = cls._split_large_text(para)
                for sub_para in sub_paras:
                    context_before = chunks[-1].text[-cls.CONTEXT_SIZE :] if chunks else ""
                    context_after = ""  # Will be updated

                    chunk = ContentChunk(
                        parent_uid=parent_uid,
                        chunk_index=chunk_index,
                        chunk_type=ContentChunkType.SECTION,
                        text=sub_para,
                        context_before=context_before,
                        context_after=context_after,
                        heading=None,
                    )
                    chunks.append(chunk)
                    chunk_index += 1
            else:
                context_before = chunks[-1].text[-cls.CONTEXT_SIZE :] if chunks else ""
                context_after = (
                    paragraphs[i + 1][: cls.CONTEXT_SIZE] if i < len(paragraphs) - 1 else ""
                )

                chunk = ContentChunk(
                    parent_uid=parent_uid,
                    chunk_index=chunk_index,
                    chunk_type=ContentChunkType.SECTION,
                    text=para.strip(),
                    context_before=context_before,
                    context_after=context_after,
                    heading=None,
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    @classmethod
    def _split_by_headers(cls, content: str) -> list[dict[str, Any]]:
        """Split markdown by headers while preserving structure"""
        sections = []

        # Pattern for markdown headers
        header_pattern = r"^(#{1,6})\s+(.+)$"

        # Split content by headers
        lines = content.split("\n")
        current_section = {"heading": None, "text": "", "level": 0}

        for line in lines:
            header_match = re.match(header_pattern, line)
            if header_match:
                # Save previous section if it has content
                text = current_section["text"]
                if isinstance(text, str) and text.strip():
                    sections.append(current_section)

                # Start new section
                level = len(header_match.group(1))
                heading = header_match.group(2)
                current_section = {"heading": heading, "text": "", "level": level}
            else:
                # Append line to current section text
                text = current_section.get("text", "")
                current_section["text"] = (
                    text + line + "\n" if isinstance(text, str) else line + "\n"
                )

        # Don't forget the last section
        text = current_section["text"]
        if isinstance(text, str) and text.strip():
            sections.append(current_section)

        # If no headers found, treat entire content as one section
        if not sections:
            sections.append({"heading": None, "text": content, "level": 0})

        return sections

    @classmethod
    def _split_section(cls, text: str, heading: str | None) -> list[dict[str, Any]]:
        """Split a section into semantic sub-chunks"""
        sub_chunks = []

        # First, extract code blocks
        code_blocks = []
        code_pattern = r"```[\s\S]*?```"

        def replace_code(match) -> str:
            code_blocks.append(match.group(0))
            return f"<CODE_BLOCK_{len(code_blocks) - 1}>"

        text_no_code = re.sub(code_pattern, replace_code, text)

        # Split remaining text into paragraphs
        paragraphs = text_no_code.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if this is a code block placeholder
            if para.startswith("<CODE_BLOCK_"):
                match = re.search(r"<CODE_BLOCK_(\d+)>", para)
                if match:
                    idx = int(match.group(1))
                    sub_chunks.append(
                        {
                            "text": code_blocks[idx],
                            "type": ContentChunkType.CODE,
                            "metadata": {"section_heading": heading},
                        }
                    )
            else:
                # Detect chunk type from content
                chunk_type = cls._detect_chunk_type(para, heading)

                # Split large paragraphs if needed
                if len(para.split()) > cls.MAX_CHUNK_SIZE:
                    splits = cls._split_large_text(para)
                    sub_chunks.extend(
                        [
                            {
                                "text": split_text,
                                "type": chunk_type,
                                "metadata": {"section_heading": heading},
                            }
                            for split_text in splits
                        ]
                    )
                else:
                    sub_chunks.append(
                        {"text": para, "type": chunk_type, "metadata": {"section_heading": heading}}
                    )

        return sub_chunks

    @classmethod
    def _detect_chunk_type(cls, text: str, heading: str | None) -> ContentChunkType:
        """Detect the semantic type of a chunk based on content patterns"""
        text_lower = text.lower()

        # Check heading hints first
        if heading:
            heading_lower = heading.lower()
            if "introduction" in heading_lower or "overview" in heading_lower:
                return ContentChunkType.INTRODUCTION
            elif "example" in heading_lower:
                return ContentChunkType.EXAMPLE
            elif "exercise" in heading_lower or "practice" in heading_lower:
                return ContentChunkType.EXERCISE
            elif "summary" in heading_lower or "conclusion" in heading_lower:
                return ContentChunkType.SUMMARY
            elif "definition" in heading_lower:
                return ContentChunkType.DEFINITION

        # Content-based detection
        if text_lower.startswith(("definition:", "define:", "what is", "a ", "an ", "the term")):
            return ContentChunkType.DEFINITION
        elif "for example" in text_lower or "example:" in text_lower or "e.g." in text_lower:
            return ContentChunkType.EXAMPLE
        elif "exercise" in text_lower or "try this" in text_lower or "practice:" in text_lower:
            return ContentChunkType.EXERCISE
        elif text_lower.startswith(("in summary", "to summarize", "in conclusion")):
            return ContentChunkType.SUMMARY
        elif len(text) < 200 and text.endswith(".") and ":" in text:
            return ContentChunkType.DEFINITION
        else:
            return ContentChunkType.EXPLANATION

    @classmethod
    def _split_large_text(cls, text: str) -> list[str]:
        """Split large text into smaller chunks at sentence boundaries"""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence.split())

            if current_size + sentence_size > cls.MAX_CHUNK_SIZE and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_size = sentence_size
            else:
                current_chunk.append(sentence)
                current_size += sentence_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    @classmethod
    def _update_chunk_contexts(cls, chunks: list[ContentChunk]) -> None:
        """Update context_after for all chunks based on their neighbors"""
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]

            # Update context_after to point to next chunk
            if not current_chunk.context_after and next_chunk:
                object.__setattr__(
                    current_chunk, "context_after", next_chunk.text[: cls.CONTEXT_SIZE]
                )


def chunk_content(content: str, parent_uid: str, format: str = "markdown") -> list[ContentChunk]:
    """
    Main entry point for content chunking.

    Args:
        content: The text content to chunk,
        parent_uid: UID of the parent curriculum entity,
        format: Content format (markdown or plain)

    Returns:
        List of ContentChunk objects
    """
    if format.lower() == "markdown":
        return ContentChunkingStrategy.chunk_markdown(content, parent_uid)
    else:
        return ContentChunkingStrategy.chunk_plain_text(content, parent_uid)


def get_chunks_by_type(
    chunks: list[ContentChunk], chunk_type: ContentChunkType
) -> list[ContentChunk]:
    """Filter chunks by type"""
    return [c for c in chunks if c.chunk_type == chunk_type]


def search_chunks(chunks: list[ContentChunk], query: str) -> list[ContentChunk]:
    """Simple text search within chunks"""
    query_lower = query.lower()
    return [c for c in chunks if query_lower in c.text.lower()]
