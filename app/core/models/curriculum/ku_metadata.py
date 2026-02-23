"""
Knowledge Metadata Model
========================

Analytics and search optimization metadata for knowledge content.
This is computed metadata that can be regenerated from the content.

Useful for search indexing, content analytics, and learning recommendations.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .ku_content import KuContent


@dataclass(frozen=True)
class KuMetadata:
    """
    Immutable metadata for content analysis and search optimization.

    This metadata is derived from content and can be regenerated.
    Provides rich analytics for search, recommendations, and learning paths.
    """

    # Identity
    unit_uid: str  # Links to KnowledgeUnit.uid

    # Text statistics
    word_count: int = 0
    character_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    reading_time_minutes: float = 0.0  # Estimated reading time

    # Content structure analysis
    headings: tuple[str, ...] = ()  # Extracted headings
    heading_levels: tuple[int, ...] = ()  # Heading hierarchy levels
    code_blocks: int = 0  # Number of code blocks
    code_languages: tuple[str, ...] = ()  # Programming languages used

    # Link analysis
    internal_links: tuple[str, ...] = ()  # Links to other knowledge units
    external_links: tuple[str, ...] = ()  # External URLs
    link_count: int = 0

    # Media analysis
    images: tuple[str, ...] = ()  # Image references
    videos: tuple[str, ...] = ()  # Video references
    has_media: bool = False

    # Content richness
    has_code: bool = False
    has_examples: bool = False
    has_exercises: bool = False
    has_definitions: bool = False

    # Search metadata
    keywords: tuple[str, ...] = ()  # Extracted keywords
    key_concepts: tuple[str, ...] = ()  # Important concepts
    technical_terms: tuple[str, ...] = ()  # Technical terminology

    # Quality indicators
    complexity_indicators: tuple[str, ...] = ()  # Complex terms/concepts
    readability_score: float | None = None  # Flesch reading ease or similar

    # Generated summaries (to be filled by AI service)
    summary_generated: str | None = None  # AI-generated summary
    summary_timestamp: datetime | None = None  # type: ignore[assignment]

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def from_content(cls, content: KuContent) -> "KuMetadata":
        """
        Generate comprehensive metadata from KuContent.

        Analyzes content structure, extracts key information, and computes
        statistics for search and analytics.
        """
        # Basic text statistics
        word_count = content.word_count
        character_count = len(content.body)
        sentences = re.split(r"[.!?]+", content.body)
        sentence_count = len([s for s in sentences if s.strip()])
        paragraphs = content.body.split("\n\n")
        paragraph_count = len([p for p in paragraphs if p.strip()])

        # Reading time (200 words/min for text, 100 for code)
        reading_time = content.estimated_reading_time()

        # Initialize collections
        headings = []
        heading_levels = []
        code_languages = set()
        internal_links = []
        external_links = []
        images = []
        videos = []
        keywords = set()
        key_concepts = set()
        technical_terms = set()
        complexity_indicators = set()

        # Analyze markdown content
        if content.is_markdown:
            # Extract headings
            heading_pattern = r"^(#{1,6})\s+(.+)$"
            for match in re.finditer(heading_pattern, content.body, re.MULTILINE):
                level = len(match.group(1))
                heading_text = match.group(2)
                headings.append(heading_text)
                heading_levels.append(level)

                # Add heading words as potential keywords
                heading_words = [
                    w.lower()
                    for w in heading_text.split()
                    if len(w) > 3 and not cls._is_common_word(w.lower())
                ]
                keywords.update(heading_words)

            # Count code blocks and extract languages
            code_fence_pattern = r"```(\w+)?[\s\S]*?```"
            code_matches = list(re.finditer(code_fence_pattern, content.body))
            for match in code_matches:
                if match.group(1):  # Language specified
                    code_languages.add(match.group(1).lower())
            code_block_count = len(code_matches)

            # Extract links
            # Markdown links: [text](url)
            md_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
            for match in re.finditer(md_link_pattern, content.body):
                url = match.group(2)
                if url.startswith(("http://", "https://", "www.")):
                    external_links.append(url)
                elif url.startswith("#") or url.endswith(".md"):
                    internal_links.append(url)

            # Bare URLs
            bare_url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            for match in re.finditer(bare_url_pattern, content.body):
                url = match.group(0)
                if url not in external_links:
                    external_links.append(url)

            # Extract images and videos
            image_pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
            for match in re.finditer(image_pattern, content.body):
                url = match.group(2)
                if any(url.lower().endswith(ext) for ext in [".mp4", ".webm", ".mov", ".avi"]):
                    videos.append(url)
                else:
                    images.append(url)

            # Extract technical terms and concepts
            cls._extract_technical_terms(content.body, technical_terms, key_concepts)

            # Find complexity indicators
            complex_patterns = [
                r"\b(?:algorithm|implementation|architecture|infrastructure)\b",
                r"\b(?:asynchronous|concurrent|parallel|distributed)\b",
                r"\b(?:optimization|performance|scalability)\b",
                r"\b(?:abstraction|polymorphism|inheritance)\b",
            ]
            for pattern in complex_patterns:
                for match in re.finditer(pattern, content.body, re.IGNORECASE):
                    complexity_indicators.add(match.group(0).lower())

        else:
            code_block_count = 0

        # Check content richness from chunks
        has_code = len(content.get_code_blocks()) > 0
        has_examples = len(content.get_examples()) > 0
        has_exercises = len(content.get_exercises()) > 0
        has_definitions = len(content.get_definitions()) > 0

        # Calculate link count
        link_count = len(internal_links) + len(external_links)

        # Has media
        has_media = len(images) > 0 or len(videos) > 0

        # Limit and convert to tuples
        return cls(
            unit_uid=content.unit_uid,
            word_count=word_count,
            character_count=character_count,
            sentence_count=sentence_count,
            paragraph_count=paragraph_count,
            reading_time_minutes=reading_time,
            headings=tuple(headings[:50]),  # Limit to 50 headings
            heading_levels=tuple(heading_levels[:50]),
            code_blocks=code_block_count,
            code_languages=tuple(sorted(code_languages)[:10]),
            internal_links=tuple(internal_links[:100]),
            external_links=tuple(external_links[:100]),
            link_count=link_count,
            images=tuple(images[:50]),
            videos=tuple(videos[:20]),
            has_media=has_media,
            has_code=has_code,
            has_examples=has_examples,
            has_exercises=has_exercises,
            has_definitions=has_definitions,
            keywords=tuple(sorted(keywords)[:50]),
            key_concepts=tuple(sorted(key_concepts)[:30]),
            technical_terms=tuple(sorted(technical_terms)[:30]),
            complexity_indicators=tuple(sorted(complexity_indicators)[:20]),
        )

    @staticmethod
    def _is_common_word(word: str) -> bool:
        """Check if a word is too common to be a keyword"""
        common_words = {
            "the",
            "this",
            "that",
            "with",
            "from",
            "have",
            "been",
            "were",
            "their",
            "what",
            "when",
            "where",
            "which",
            "while",
            "who",
            "will",
            "would",
            "there",
            "these",
            "those",
            "they",
            "them",
            "then",
            "than",
            "into",
            "about",
            "after",
            "before",
            "between",
            "under",
            "over",
            "through",
        }
        return word in common_words

    @staticmethod
    def _extract_technical_terms(
        text: str, technical_terms: set[str], key_concepts: set[str]
    ) -> None:
        """Extract technical terms and key concepts from text"""
        # Common technical patterns
        tech_patterns = [
            # CamelCase terms (classes, interfaces)
            r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b",
            # snake_case terms
            r"\b[a-z]+(?:_[a-z]+)+\b",
            # CONSTANT_CASE
            r"\b[A-Z]+(?:_[A-Z]+)+\b",
            # Function calls
            r"\b\w+\(\)",
            # File extensions
            r"\.\w{2,4}\b",
            # Version numbers
            r"\bv?\d+\.\d+(?:\.\d+)?\b",
        ]

        for pattern in tech_patterns:
            for match in re.finditer(pattern, text):
                term = match.group(0)
                if len(term) > 2:  # Skip very short terms
                    technical_terms.add(term)

        # Extract quoted concepts
        quote_pattern = r'["\']([^"\']{3,50})["\']'
        for match in re.finditer(quote_pattern, text):
            concept = match.group(1)
            if not concept.isupper():  # Skip all-caps quotes
                key_concepts.add(concept)

        # Extract defined terms (e.g., "X is...", "X means...")
        definition_pattern = r"\b([A-Z][a-zA-Z\s]{2,30})\s+(?:is|are|means|refers to)\b"
        for match in re.finditer(definition_pattern, text):
            key_concepts.add(match.group(1).strip())

    # ==========================================================================
    # BUSINESS LOGIC METHODS
    # ==========================================================================

    def is_comprehensive(self) -> bool:
        """Check if content is comprehensive (has various elements)"""
        return (
            self.has_code and self.has_examples and len(self.headings) > 3 and self.word_count > 500
        )

    def is_interactive(self) -> bool:
        """Check if content has interactive elements"""
        return self.has_exercises or self.has_code

    def is_well_structured(self) -> bool:
        """Check if content has good structure"""
        return (
            len(self.headings) > 2
            and self.paragraph_count > 3
            and self.sentence_count / max(1, self.paragraph_count) > 2
        )

    def is_reference_rich(self) -> bool:
        """Check if content has many references"""
        return self.link_count > 5 or len(self.internal_links) > 3

    def is_visual(self) -> bool:
        """Check if content has visual elements"""
        return self.has_media or len(self.images) > 0

    def complexity_level(self) -> str:
        """Estimate complexity level based on indicators"""
        if len(self.complexity_indicators) > 10:
            return "advanced"
        elif len(self.complexity_indicators) > 3:
            return "intermediate"
        else:
            return "basic"

    def content_type_profile(self) -> dict[str, bool]:
        """Get a profile of content types present"""
        return {
            "has_theory": len(self.headings) > 0 and not self.has_exercises,
            "has_practice": self.has_exercises,
            "has_examples": self.has_examples,
            "has_reference": self.has_definitions,
            "has_code": self.has_code,
            "has_media": self.has_media,
            "is_comprehensive": self.is_comprehensive(),
            "is_interactive": self.is_interactive(),
        }

    # ==========================================================================
    # CONVERSION METHODS
    # ==========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization"""
        return {
            "unit_uid": self.unit_uid,
            "word_count": self.word_count,
            "character_count": self.character_count,
            "sentence_count": self.sentence_count,
            "paragraph_count": self.paragraph_count,
            "reading_time_minutes": self.reading_time_minutes,
            "headings": list(self.headings),
            "heading_levels": list(self.heading_levels),
            "code_blocks": self.code_blocks,
            "code_languages": list(self.code_languages),
            "internal_links": list(self.internal_links),
            "external_links": list(self.external_links),
            "link_count": self.link_count,
            "images": list(self.images),
            "videos": list(self.videos),
            "has_media": self.has_media,
            "has_code": self.has_code,
            "has_examples": self.has_examples,
            "has_exercises": self.has_exercises,
            "has_definitions": self.has_definitions,
            "keywords": list(self.keywords),
            "key_concepts": list(self.key_concepts),
            "technical_terms": list(self.technical_terms),
            "complexity_indicators": list(self.complexity_indicators),
            "readability_score": self.readability_score,
            "summary_generated": self.summary_generated,
            "summary_timestamp": self.summary_timestamp.isoformat()
            if self.summary_timestamp
            else None,
        }

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Export properties for Neo4j node (with size limits)"""
        return {
            "unit_uid": self.unit_uid,
            "word_count": self.word_count,
            "character_count": self.character_count,
            "reading_time_minutes": self.reading_time_minutes,
            "heading_count": len(self.headings),
            "headings": list(self.headings[:10]),  # Limit for Neo4j
            "code_blocks": self.code_blocks,
            "code_languages": list(self.code_languages),
            "link_count": self.link_count,
            "internal_link_count": len(self.internal_links),
            "external_link_count": len(self.external_links),
            "image_count": len(self.images),
            "video_count": len(self.videos),
            "has_media": self.has_media,
            "has_code": self.has_code,
            "has_examples": self.has_examples,
            "has_exercises": self.has_exercises,
            "has_definitions": self.has_definitions,
            "keywords": list(self.keywords[:20]),  # Limit for Neo4j
            "key_concepts": list(self.key_concepts[:10]),
            "complexity_level": self.complexity_level(),
            "is_comprehensive": self.is_comprehensive(),
            "is_interactive": self.is_interactive(),
            "summary_generated": self.summary_generated[:500] if self.summary_generated else None,
        }

    def search_relevance_score(self, query: str) -> float:
        """
        Calculate relevance score for a search query.

        Returns a score between 0 and 1 based on keyword matches.
        """
        query_words = set(query.lower().split())
        score = 0.0

        # Check keywords (highest weight)
        keyword_matches = sum(
            1 for kw in self.keywords if any(qw in kw.lower() for qw in query_words)
        )
        score += keyword_matches * 0.3

        # Check headings (high weight)
        heading_text = " ".join(self.headings).lower()
        heading_matches = sum(1 for qw in query_words if qw in heading_text)
        score += heading_matches * 0.2

        # Check key concepts (medium weight)
        concept_matches = sum(
            1 for concept in self.key_concepts if any(qw in concept.lower() for qw in query_words)
        )
        score += concept_matches * 0.15

        # Check technical terms (medium weight)
        term_matches = sum(
            1 for term in self.technical_terms if any(qw in term.lower() for qw in query_words)
        )
        score += term_matches * 0.15

        # Normalize to 0-1 range
        return min(1.0, score / max(1, len(query_words)))

    def __str__(self) -> str:
        """String representation"""
        return (
            f"ContentMetadata(unit_uid={self.unit_uid}, "
            f"words={self.word_count}, complexity={self.complexity_level()})"
        )

    def __repr__(self) -> str:
        """Developer representation"""
        return (
            f"ContentMetadata(unit_uid='{self.unit_uid}', "
            f"word_count={self.word_count}, headings={len(self.headings)}, "
            f"links={self.link_count}, has_code={self.has_code}, "
            f"complexity='{self.complexity_level()}')"
        )
