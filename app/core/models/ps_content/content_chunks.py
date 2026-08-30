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

# Bumped whenever ContentChunkingStrategy logic changes in a way that produces
# different chunk boundaries or types for the same input. Stored on every chunk
# so BatchChunkingService can identify stale chunks (chunking_version < current).
#   v1 — structural split (headers → paragraphs → code fences), keyword typing.
#   v2 — fragment floor (2026-08-30): sub-sentence prose fragments fold into a
#        prose neighbour; horizontal rules and bare list markers are dropped.
CHUNKING_ALGORITHM_VERSION = "v2"

# The fragment floor, in WORDS (the unit every chunk knob is in; a chunk's
# persisted ``word_count`` is ``len(text.split())``). A chunk under it is a
# sub-sentence fragment — a ``---`` rule, a bare list marker, a link-only or
# label-only line (``Ask:``, ``**5-4-3-2-1:**``) — and can only ever be noise
# in retrieval. Measured 2026-08-28 on the live corpus: 83 of 998 chunks were
# under 5 words (75 of them vault notes) against a 27-word median. Re-based
# from THAT measurement, deliberately not from ``ChunkingParams.min_chunk_size``
# (50, inert): that knob sits above the corpus median, so enforcing it is a
# tuning decision, not this defect fix — see
# docs/roadmap/deferred-work.md § Per-Domain Chunking Knobs.
FRAGMENT_FLOOR_WORDS = 5

# Structural noise that carries no content of its own: a markdown thematic
# break (``---`` / ``***`` / ``___``, spaces allowed) or a list marker that a
# blank line separated from its item. Dropped, never folded — folding would
# only push the noise into a neighbour's embedding text.
_THEMATIC_BREAK = re.compile(r"^(?:[-*_]\s*){3,}$")
_BARE_LIST_MARKER = re.compile(r"^(?:[-*+]|\d+[.)])$")


def _is_structural_noise(text: str) -> bool:
    """True for a paragraph that is a thematic break or a bare list marker."""
    stripped = text.strip()
    return bool(_THEMATIC_BREAK.match(stripped) or _BARE_LIST_MARKER.match(stripped))


def _is_fragment(text: str) -> bool:
    """True when ``text`` is under the fragment floor (whitespace word count)."""
    return len(text.split()) < FRAGMENT_FLOOR_WORDS


@dataclass(frozen=True)
class ChunkingParams:
    """Per-domain chunk-size knobs for the chunking strategy.

    Ingest-time production parameters (NOT retrieval-side). Carried on
    ``EntityIngestionConfig`` so a domain (Ku, PathStep) can later diverge its
    grain without a code change; the default is shared by every domain today so
    this ships zero behavior change. See ``chunk_version_tag`` for how a diverged
    domain gets an isolated staleness tag.
    """

    min_chunk_size: int = (
        50  # Minimum words per chunk — 0 refs in the strategy today; carried for future use
    )
    max_chunk_size: int = 500  # Maximum words per chunk before a large paragraph is split
    context_size: int = 100  # Chars of neighbouring text preserved as chunk context


DEFAULT_CHUNKING_PARAMS = ChunkingParams()


def chunk_version_tag(params: ChunkingParams) -> str:
    """Staleness tag stamped on chunks produced with ``params``.

    Default params → the bare ``CHUNKING_ALGORITHM_VERSION`` (zero churn: existing
    chunks and every ``== CHUNKING_ALGORITHM_VERSION`` test keep matching). A
    diverged domain → a ``"<version>:<max>-<context>"`` suffix so its chunks read
    as stale only against *their own* params, never against the default corpus.
    Only the two boundary-affecting knobs go in the fingerprint; ``min_chunk_size``
    is inert (unused by the strategy) and excluded.
    """
    if params == DEFAULT_CHUNKING_PARAMS:
        return CHUNKING_ALGORITHM_VERSION
    return f"{CHUNKING_ALGORITHM_VERSION}:{params.max_chunk_size}-{params.context_size}"


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
    # Ancestor-heading breadcrumb (shallow→deep, excluding this chunk's own
    # heading) — the chapter/section trail above the chunk, used for citation
    # ("Part > Chapter > Section"). None when the chunk has no heading ancestors.
    section_path: str | None = None
    word_count: int = 0  # Word count of chunk
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional metadata
    embedding: tuple[float, ...] | None = None  # Vector embedding (immutable tuple)
    chunking_version: str = CHUNKING_ALGORITHM_VERSION  # Algorithm version that produced this chunk

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

    @classmethod
    def chunk_markdown(
        cls,
        content: str,
        parent_uid: str,
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> list[ContentChunk]:
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
        version = chunk_version_tag(params)

        # Split by headers while preserving them
        sections = cls._split_by_headers(content)

        for section in sections:
            heading = section.get("heading")
            text = section.get("text", "").strip()
            breadcrumb = section.get("breadcrumb") or []
            section_path = " > ".join(breadcrumb) or None

            if not text:
                continue

            # Further split large sections
            sub_chunks = cls._split_section(text, heading, params)

            for i, sub_chunk in enumerate(sub_chunks):
                # Determine context
                context_before = ""
                context_after = ""

                # Get context from previous chunk
                if chunks:
                    context_before = chunks[-1].text[-params.context_size :]

                # Get context from next sub-chunk (if available)
                if i < len(sub_chunks) - 1:
                    context_after = sub_chunks[i + 1]["text"][: params.context_size]

                chunk = ContentChunk(
                    parent_uid=parent_uid,
                    chunk_index=chunk_index,
                    chunk_type=sub_chunk["type"],
                    text=sub_chunk["text"],
                    context_before=context_before,
                    context_after=context_after,
                    heading=heading,
                    section_path=section_path,
                    metadata=sub_chunk.get("metadata", {}),
                    chunking_version=version,
                )

                chunks.append(chunk)
                chunk_index += 1

        # Update context_after for the last chunk of each group
        cls._update_chunk_contexts(chunks, params)

        return chunks

    @classmethod
    def chunk_plain_text(
        cls,
        content: str,
        parent_uid: str,
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> list[ContentChunk]:
        """
        Chunk plain text by paragraphs and size limits.
        """
        chunks: list[ContentChunk] = []
        version = chunk_version_tag(params)

        # Same paragraph → sub-chunk shape as the markdown path (uniform SECTION
        # type, large paragraphs split), then the same fragment floor.
        sub_chunks: list[dict[str, Any]] = []
        for para in content.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            pieces = (
                cls._split_large_text(para, params)
                if len(para.split()) > params.max_chunk_size
                else [para]
            )
            sub_chunks.extend(
                {"text": piece, "type": ContentChunkType.SECTION, "metadata": {}}
                for piece in pieces
            )
        sub_chunks = cls._fold_fragments(sub_chunks, None, retype=False)

        for chunk_index, sub_chunk in enumerate(sub_chunks):
            context_before = chunks[-1].text[-params.context_size :] if chunks else ""
            context_after = (
                sub_chunks[chunk_index + 1]["text"][: params.context_size]
                if chunk_index < len(sub_chunks) - 1
                else ""
            )
            chunks.append(
                ContentChunk(
                    parent_uid=parent_uid,
                    chunk_index=chunk_index,
                    chunk_type=ContentChunkType.SECTION,
                    text=sub_chunk["text"],
                    context_before=context_before,
                    context_after=context_after,
                    heading=None,
                    chunking_version=version,
                )
            )

        return chunks

    @classmethod
    def _split_by_headers(cls, content: str) -> list[dict[str, Any]]:
        """Split markdown by headers while preserving structure.

        Each section carries a ``breadcrumb`` — the chain of shallower headings
        in scope (shallow→deep, excluding the section's own heading) — so a
        chunk can cite its location (chapter/section trail). The trail is tracked
        across ALL heading lines, including headings whose body is empty (e.g. a
        Part divider immediately followed by its first chapter), so no ancestor
        is dropped.
        """
        sections = []

        # Pattern for markdown headers
        header_pattern = r"^(#{1,6})\s+(.+)$"

        # Split content by headers
        lines = content.split("\n")
        current_section: dict[str, Any] = {
            "heading": None,
            "text": "",
            "level": 0,
            "breadcrumb": [],
        }
        # Ancestor stack (level, heading), shallow→deep — the headings in scope.
        trail: list[tuple[int, str]] = []

        for line in lines:
            header_match = re.match(header_pattern, line)
            if header_match:
                # Save previous section if it has content
                text = current_section["text"]
                if isinstance(text, str) and text.strip():
                    sections.append(current_section)

                # Start new section — pop siblings/deeper, capture ancestors.
                level = len(header_match.group(1))
                heading = header_match.group(2)
                while trail and trail[-1][0] >= level:
                    trail.pop()
                breadcrumb = [h for _, h in trail]
                trail.append((level, heading))
                current_section = {
                    "heading": heading,
                    "text": "",
                    "level": level,
                    "breadcrumb": breadcrumb,
                }
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
            sections.append({"heading": None, "text": content, "level": 0, "breadcrumb": []})

        return sections

    @classmethod
    def _split_section(
        cls,
        text: str,
        heading: str | None,
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> list[dict[str, Any]]:
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
                if len(para.split()) > params.max_chunk_size:
                    splits = cls._split_large_text(para, params)
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

        return cls._fold_fragments(sub_chunks, heading)

    @classmethod
    def _fold_fragments(
        cls,
        sub_chunks: list[dict[str, Any]],
        heading: str | None,
        *,
        retype: bool = True,
    ) -> list[dict[str, Any]]:
        """Apply the fragment floor to one section's sub-chunks (algorithm v2).

        Structural noise (``_is_structural_noise``) is dropped. A prose
        sub-chunk under ``FRAGMENT_FLOOR_WORDS`` is folded into the NEXT prose
        sub-chunk (a label such as ``Ask:`` introduces what follows); trailing
        fragments fold into the last prose sub-chunk; a section made only of
        fragments becomes one joined chunk. Code fences are never merged into
        and never fold — their text is the verbatim fence. A merged chunk is
        re-typed from its final text when ``retype`` is set (markdown path);
        the plain-text path keeps its uniform ``SECTION`` type.
        """

        def merged(base: dict[str, Any], parts: list[str]) -> dict[str, Any]:
            text = "\n\n".join(parts)
            chunk_type = cls._detect_chunk_type(text, heading) if retype else base["type"]
            return {**base, "text": text, "type": chunk_type}

        folded: list[dict[str, Any]] = []
        pending: list[str] = []
        for chunk in sub_chunks:
            if chunk["type"] is ContentChunkType.CODE:
                folded.append(chunk)
                continue
            text = chunk["text"]
            if _is_structural_noise(text):
                continue
            if _is_fragment(text):
                pending.append(text)
                continue
            if pending:
                chunk = merged(chunk, [*pending, text])
                pending = []
            folded.append(chunk)

        if pending:
            for i in range(len(folded) - 1, -1, -1):
                if folded[i]["type"] is not ContentChunkType.CODE:
                    folded[i] = merged(folded[i], [folded[i]["text"], *pending])
                    break
            else:
                template = {
                    "type": ContentChunkType.EXPLANATION,
                    "metadata": {"section_heading": heading},
                }
                if not retype:
                    template["type"] = ContentChunkType.SECTION
                folded.append(merged(template, pending))
        return folded

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
    def _split_large_text(
        cls,
        text: str,
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> list[str]:
        """Split large text into smaller chunks at sentence boundaries"""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence.split())

            if current_size + sentence_size > params.max_chunk_size and current_chunk:
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
    def _update_chunk_contexts(
        cls,
        chunks: list[ContentChunk],
        params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
    ) -> None:
        """Update context_after for all chunks based on their neighbors"""
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]

            # Update context_after to point to next chunk
            if not current_chunk.context_after and next_chunk:
                object.__setattr__(
                    current_chunk, "context_after", next_chunk.text[: params.context_size]
                )


def chunk_content(
    content: str,
    parent_uid: str,
    format: str = "markdown",
    params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
) -> list[ContentChunk]:
    """
    Main entry point for content chunking.

    Args:
        content: The text content to chunk,
        parent_uid: UID of the parent curriculum entity,
        format: Content format (markdown or plain),
        params: Per-domain chunk-size knobs (defaults to DEFAULT_CHUNKING_PARAMS)

    Returns:
        List of ContentChunk objects
    """
    if format.lower() == "markdown":
        return ContentChunkingStrategy.chunk_markdown(content, parent_uid, params)
    else:
        return ContentChunkingStrategy.chunk_plain_text(content, parent_uid, params)


def get_chunks_by_type(
    chunks: list[ContentChunk], chunk_type: ContentChunkType
) -> list[ContentChunk]:
    """Filter chunks by type"""
    return [c for c in chunks if c.chunk_type == chunk_type]
