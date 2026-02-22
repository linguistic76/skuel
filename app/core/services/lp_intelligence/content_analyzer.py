"""
Content Analyzer - Content Metadata and Feature Extraction
===========================================================

Focused service for analyzing content characteristics and extracting metadata.

Responsibilities:
- Extract content metadata (keywords, complexity, features)
- Calculate reading time and complexity scores
- Detect content features (code, images, links, exercises)
- Calculate educational metrics (concept density, examples, definitions)
- Generate content embeddings (optional)
- Categorize content by topic

This service is part of the refactored LpIntelligenceService architecture:
- LearningStateAnalyzer: Learning state assessment
- LearningRecommendationEngine: Personalized recommendations
- ContentAnalyzer: Content analysis and metadata (THIS FILE)
- ContentQualityAssessor: Quality assessment and similarity
- LpIntelligenceService: Facade coordinating all sub-services

Architecture:
- Optional embeddings_service for vector generation
- Returns ContentMetadata frozen dataclass
- Protocol-based content input (ContentAdapter)
"""

import re
from collections import Counter

from core.ports.content_protocols import ContentAdapter
from core.services.lp_intelligence.types import ContentMetadata
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


class ContentAnalyzer:
    """
    Analyze content characteristics and extract metadata.

    This service handles content analysis:
    - Metadata extraction (keywords, summary, reading time)
    - Complexity calculation (readability metrics)
    - Feature detection (code, images, links, exercises)
    - Educational metrics (concept density, examples, definitions)
    - Embedding generation (optional vector representation)
    - Topic categorization

    Architecture:
    - Optional embeddings_service for vector generation
    - Protocol-based content input (ContentAdapter)
    - Returns frozen dataclass ContentMetadata
    """

    def __init__(self, embeddings_service: Neo4jGenAIEmbeddingsService | None = None) -> None:
        """
        Initialize content analyzer.

        Args:
            embeddings_service: Embeddings service for vector generation (optional)
        """
        self.embeddings = embeddings_service
        logger.info("ContentAnalyzer initialized")

    # ========================================================================
    # PUBLIC API - METADATA EXTRACTION
    # ========================================================================

    @with_error_handling("extract_content_metadata", error_type="system")
    async def extract_content_metadata(self, content: ContentAdapter) -> Result[ContentMetadata]:
        """
        Extract comprehensive metadata from content.

        Args:
            content: Content to analyze (ContentAdapter protocol)

        Returns:
            Result[ContentMetadata] with extracted features and metrics
        """
        # Get content body if available
        body = getattr(content, "body", "") or getattr(content, "description", "") or str(content)

        # Extract keywords (simple implementation - could use NLP library)
        keywords = self._extract_keywords(body)

        # Calculate reading time (average 200 words per minute)
        word_count = len(body.split())
        reading_time = max(1, word_count // 200)

        # Detect content features
        has_code = "```" in body or "def " in body or "function " in body or "class " in body
        has_images = "![" in body or "<img" in body
        has_links = "http" in body or "[" in body
        has_exercises = any(
            marker in body.lower() for marker in ["exercise", "practice", "try it", "your turn"]
        )

        # Calculate complexity (simple heuristic)
        complexity = self._calculate_complexity(body, word_count)

        # Calculate educational metrics
        concept_density = self._calculate_concept_density(body, word_count)
        example_count = body.lower().count("example") + body.lower().count("for instance")
        definition_count = body.lower().count("is defined as") + body.lower().count("means")

        # Generate embedding if available
        # Note: create_embedding returns list[float] | None, not Result[T]
        embedding = None
        if self.embeddings:
            try:
                embedding = await self.embeddings.create_embedding(
                    body[:1000]
                )  # First 1000 chars, returns list[float] | None directly
            except Exception as e:
                logger.warning(f"Failed to create embedding: {e}")

        # Determine topic categories
        categories = self._determine_topic_categories(keywords, content.tags)

        metadata = ContentMetadata(
            content_uid=content.uid,
            keywords=keywords[:10],  # Top 10 keywords
            summary=body[:200] + "..." if len(body) > 200 else body,
            reading_time_minutes=reading_time,
            complexity_score=complexity,
            has_code=has_code,
            has_images=has_images,
            has_links=has_links,
            has_exercises=has_exercises,
            concept_density=concept_density,
            example_count=example_count,
            definition_count=definition_count,
            embedding_vector=embedding,
            topic_categories=categories,
        )

        return Result.ok(metadata)

    # ========================================================================
    # KEYWORD EXTRACTION (Private)
    # ========================================================================

    def _extract_keywords(self, text: str) -> list[str]:
        """
        Extract keywords from text (simple implementation).

        Args:
            text: Text to analyze

        Returns:
            List of extracted keywords (top 20)
        """
        # Remove common words
        stop_words = {
            "the",
            "is",
            "at",
            "which",
            "on",
            "a",
            "an",
            "as",
            "are",
            "was",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "who",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "in",
            "of",
            "to",
            "for",
            "with",
            "from",
            "up",
            "out",
            "if",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
        }

        # Extract words
        words = re.findall(r"\b[a-z]+\b", text.lower())
        words = [w for w in words if len(w) > 3 and w not in stop_words]

        # Count frequency
        word_freq = Counter(words)

        # Return most common
        return [word for word, _ in word_freq.most_common(20)]

    # ========================================================================
    # COMPLEXITY CALCULATION (Private)
    # ========================================================================

    def _calculate_complexity(self, text: str, word_count: int) -> float:
        """
        Calculate text complexity (0-1).

        Uses simple heuristics:
        - Average word length (longer words = more complex)
        - Average sentence length (longer sentences = more complex)

        Args:
            text: Text to analyze
            word_count: Total word count

        Returns:
            Complexity score (0-1)
        """
        if word_count == 0:
            return 0.5

        # Simple heuristics
        avg_word_length = sum(len(w) for w in text.split()) / max(1, word_count)
        sentence_count = text.count(".") + text.count("!") + text.count("?")
        avg_sentence_length = word_count / max(1, sentence_count)

        # Normalize to 0-1
        complexity = min(
            1.0, (avg_word_length - 4) / 4 * 0.5 + (avg_sentence_length - 10) / 20 * 0.5
        )

        return max(0.0, complexity)

    # ========================================================================
    # CONCEPT DENSITY CALCULATION (Private)
    # ========================================================================

    def _calculate_concept_density(self, text: str, word_count: int) -> float:
        """
        Calculate concepts per 100 words.

        Looks for concept indicator words like "concept", "principle", "theory", etc.

        Args:
            text: Text to analyze
            word_count: Total word count

        Returns:
            Concept density (concepts per 100 words)
        """
        if word_count == 0:
            return 0.0

        # Look for concept indicators
        concept_markers = [
            "concept",
            "principle",
            "theory",
            "method",
            "approach",
            "technique",
            "pattern",
            "framework",
            "model",
            "paradigm",
        ]

        concept_count = sum(text.lower().count(marker) for marker in concept_markers)

        return (concept_count / word_count) * 100

    # ========================================================================
    # TOPIC CATEGORIZATION (Private)
    # ========================================================================

    def _determine_topic_categories(self, keywords: list[str], tags: list[str]) -> list[str]:
        """
        Determine topic categories from keywords and tags.

        Args:
            keywords: Extracted keywords
            tags: Content tags

        Returns:
            List of topic categories (max 3)
        """
        categories = []

        # Programming categories
        prog_keywords = {
            "python",
            "javascript",
            "programming",
            "code",
            "function",
            "class",
            "algorithm",
        }
        if any(kw in keywords + tags for kw in prog_keywords):
            categories.append("programming")

        # Data science categories
        data_keywords = {"data", "analysis", "statistics", "machine", "learning", "model"}
        if any(kw in keywords + tags for kw in data_keywords):
            categories.append("data_science")

        # Math categories
        math_keywords = {"math", "mathematics", "equation", "formula", "calculus", "algebra"}
        if any(kw in keywords + tags for kw in math_keywords):
            categories.append("mathematics")

        # Web development categories
        web_keywords = {"html", "css", "web", "frontend", "backend", "api", "http"}
        if any(kw in keywords + tags for kw in web_keywords):
            categories.append("web_development")

        # Systems categories
        sys_keywords = {"system", "architecture", "design", "infrastructure", "network"}
        if any(kw in keywords + tags for kw in sys_keywords):
            categories.append("systems")

        # Business categories
        business_keywords = {"business", "management", "strategy", "marketing", "finance"}
        if any(kw in keywords + tags for kw in business_keywords):
            categories.append("business")

        return categories[:3]  # Limit to top 3
