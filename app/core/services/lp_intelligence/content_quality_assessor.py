"""
Content Quality Assessor - Quality Scoring and Similarity
==========================================================

Focused service for assessing content quality and finding similar content.

Responsibilities:
- Calculate content quality scores (structure, examples, exercises)
- Assess completeness (summary, keywords, definitions)
- Determine educational value (high, medium, low)
- Suggest content improvements
- Find similar content based on multiple similarity metrics
- Search content by specific features

This service is part of the refactored LpIntelligenceService architecture:
- LearningStateAnalyzer: Learning state assessment
- LearningRecommendationEngine: Personalized recommendations
- ContentAnalyzer: Content analysis and metadata
- ContentQualityAssessor: Quality assessment and similarity (THIS FILE)
- LpIntelligenceService: Facade coordinating all sub-services

Architecture:
- Depends on ContentAnalyzer for metadata extraction
- Returns Result[T] for error handling
- Protocol-based content input (ContentAdapter)
"""

from core.ports.content_protocols import ContentAdapter
from core.services.lp_intelligence.content_analyzer import ContentAnalyzer
from core.services.lp_intelligence.types import ContentAnalysisResult, ContentMetadata
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_second_item

logger = get_logger(__name__)


class ContentQualityAssessor:
    """
    Assess content quality and find similar content.

    This service handles quality assessment:
    - Quality scoring (structure, examples, exercises, timing)
    - Completeness scoring (summary, keywords, examples, definitions)
    - Educational value assessment (high, medium, low)
    - Improvement suggestions (actionable feedback)
    - Content similarity (keyword, category, complexity, feature matching)
    - Feature-based search (code, images, exercises, reading time)

    Architecture:
    - Requires ContentAnalyzer for metadata extraction
    - Protocol-based content input (ContentAdapter)
    - Returns frozen dataclasses for analysis results
    """

    def __init__(self, content_analyzer: ContentAnalyzer) -> None:
        """
        Initialize content quality assessor.

        Args:
            content_analyzer: ContentAnalyzer for metadata extraction

        Raises:
            ValueError: If content_analyzer is None
        """
        if not content_analyzer:
            raise ValueError("ContentAnalyzer is required")

        self.content_analyzer = content_analyzer
        logger.info("ContentQualityAssessor initialized")

    # ========================================================================
    # PUBLIC API - CONTENT ANALYSIS
    # ========================================================================

    @with_error_handling("analyze_content", error_type="system")
    async def analyze_content(self, content: ContentAdapter) -> Result[ContentAnalysisResult]:
        """
        Perform comprehensive content analysis.

        Replaces ContentAnalysisService.analyze_content()

        Args:
            content: Content to analyze (wrapped in ContentAdapter)

        Returns:
            Result[ContentAnalysisResult]: Complete content analysis with quality metrics
        """
        # Extract metadata
        metadata_result = await self.content_analyzer.extract_content_metadata(content)

        # Return error if metadata extraction failed
        if metadata_result.is_error:
            return Result.fail(metadata_result.expect_error())

        metadata = metadata_result.value

        # Calculate quality metrics
        quality_score = self._calculate_content_quality(content, metadata)
        completeness_score = self._calculate_completeness(content, metadata)

        # Determine educational value
        educational_value = self._assess_educational_value(
            metadata, quality_score, completeness_score
        )

        # Generate improvement suggestions
        improvements = self._suggest_improvements(
            content, metadata, quality_score, completeness_score
        )

        result = ContentAnalysisResult(
            metadata=metadata,
            quality_score=quality_score,
            completeness_score=completeness_score,
            educational_value=educational_value,
            recommended_improvements=improvements,
        )

        logger.info(f"Content analysis complete for {content.uid}")
        return Result.ok(result)

    # ========================================================================
    # PUBLIC API - SIMILARITY SEARCH
    # ========================================================================

    @with_error_handling("find_similar_content", error_type="system")
    async def find_similar_content(
        self, content: ContentAdapter, content_pool: list[ContentAdapter], limit: int = 5
    ) -> Result[list[tuple[ContentAdapter, float]]]:
        """
        Find similar content based on various similarity metrics.

        Args:
            content: Reference content
            content_pool: Pool of content to search
            limit: Maximum results

        Returns:
            Result[list[tuple[ContentAdapter, float]]]: List of (content, similarity_score) tuples
        """
        # Get metadata for reference content
        ref_metadata_result = await self.content_analyzer.extract_content_metadata(content)

        # Return error if metadata extraction failed
        if ref_metadata_result.is_error:
            return Result.fail(ref_metadata_result.expect_error())

        ref_metadata = ref_metadata_result.value

        similarities = []

        for candidate in content_pool:
            if candidate.uid == content.uid:
                continue

            # Calculate similarity score
            score = await self._calculate_content_similarity(ref_metadata, candidate)

            similarities.append((candidate, score))

        # Sort by similarity (using centralized sort function)
        similarities.sort(key=get_second_item, reverse=True)

        return Result.ok(similarities[:limit])

    @with_error_handling("search_by_content_features", error_type="system")
    async def search_by_content_features(
        self,
        has_code: bool | None = None,
        has_images: bool | None = None,
        has_links: bool | None = None,
        has_exercises: bool | None = None,
        min_reading_time: int | None = None,
        max_reading_time: int | None = None,
        keywords: list[str] | None = None,
        content_pool: list[ContentAdapter] | None = None,
    ) -> Result[list[ContentAdapter]]:
        """
        Search content by specific features.

        Args:
            has_code: Filter by code presence
            has_images: Filter by image presence
            has_links: Filter by link presence
            has_exercises: Filter by exercise presence
            min_reading_time: Minimum reading time (minutes)
            max_reading_time: Maximum reading time (minutes)
            keywords: Required keywords
            content_pool: Pool to search in

        Returns:
            Result[list[ContentAdapter]]: Matching content
        """
        if not content_pool:
            return Result.ok([])

        matches = []

        for content in content_pool:
            # Extract metadata
            metadata_result = await self.content_analyzer.extract_content_metadata(content)

            # Skip if metadata extraction failed
            if metadata_result.is_error:
                logger.warning(
                    f"Failed to extract metadata for content, skipping: {metadata_result.error}"
                )
                continue

            metadata = metadata_result.value

            # Check filters
            if has_code is not None and metadata.has_code != has_code:
                continue
            if has_images is not None and metadata.has_images != has_images:
                continue
            if has_links is not None and metadata.has_links != has_links:
                continue
            if has_exercises is not None and metadata.has_exercises != has_exercises:
                continue

            if min_reading_time and metadata.reading_time_minutes < min_reading_time:
                continue
            if max_reading_time and metadata.reading_time_minutes > max_reading_time:
                continue

            if keywords and not any(kw.lower() in metadata.keywords for kw in keywords):
                # Check if any keyword matches
                continue

            matches.append(content)

        return Result.ok(matches)

    # ========================================================================
    # QUALITY SCORING (Private)
    # ========================================================================

    def _calculate_content_quality(
        self, content: ContentAdapter, metadata: ContentMetadata
    ) -> float:
        """
        Calculate content quality score.

        Analyzes both content structure and metadata for comprehensive quality assessment.

        Args:
            content: Content to assess
            metadata: Extracted metadata

        Returns:
            Quality score (0-1)
        """
        quality = 0.5

        # Content structure indicators (from ContentAdapter)
        # Well-tagged content shows organization
        if len(content.tags) >= 3:
            quality += 0.1

        # Appropriate difficulty labeling
        if content.difficulty in ["beginner", "intermediate", "advanced"]:
            quality += 0.05

        # Realistic time estimates (content.estimated_time is in minutes)
        if 5 <= content.estimated_time <= 60:
            quality += 0.05

        # Metadata indicators
        # Has examples
        if metadata.example_count > 0:
            quality += 0.2

        # Has exercises
        if metadata.has_exercises:
            quality += 0.15

        # Good reading length
        if 5 <= metadata.reading_time_minutes <= 20:
            quality += 0.15

        return min(1.0, quality)

    def _calculate_completeness(self, _content: ContentAdapter, metadata: ContentMetadata) -> float:
        """
        Calculate content completeness.

        Args:
            _content: Content to assess (unused - for future use)
            metadata: Extracted metadata

        Returns:
            Completeness score (0-1)
        """
        completeness = 0.0

        # Check required components
        if metadata.summary:
            completeness += 0.2
        if metadata.keywords:
            completeness += 0.2
        if metadata.example_count > 0:
            completeness += 0.2
        if metadata.has_exercises:
            completeness += 0.2
        if metadata.definition_count > 0:
            completeness += 0.2

        return completeness

    def _assess_educational_value(
        self, _metadata: ContentMetadata, quality: float, completeness: float
    ) -> str:
        """
        Assess educational value.

        Args:
            _metadata: Content metadata (unused - for future use)
            quality: Quality score
            completeness: Completeness score

        Returns:
            Educational value ("high", "medium", "low")
        """
        score = (quality + completeness) / 2

        if score >= 0.7:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"

    def _suggest_improvements(
        self,
        _content: ContentAdapter,
        metadata: ContentMetadata,
        quality: float,
        _completeness: float,
    ) -> list[str]:
        """
        Suggest content improvements.

        Args:
            _content: Content to assess (unused - for future use)
            metadata: Content metadata
            quality: Quality score
            _completeness: Completeness score (unused - for future use)

        Returns:
            List of actionable improvement suggestions
        """
        suggestions = []

        if metadata.example_count == 0:
            suggestions.append("Add examples to illustrate concepts")

        if not metadata.has_exercises:
            suggestions.append("Include practice exercises")

        if metadata.reading_time_minutes < 3:
            suggestions.append("Expand content with more detail")

        if metadata.reading_time_minutes > 30:
            suggestions.append("Consider breaking into smaller sections")

        if quality < 0.5:
            suggestions.append("Improve content structure and clarity")

        return suggestions

    # ========================================================================
    # SIMILARITY CALCULATION (Private)
    # ========================================================================

    async def _calculate_content_similarity(
        self, ref_metadata: ContentMetadata, candidate: ContentAdapter
    ) -> float:
        """
        Calculate similarity between content items.

        Uses multiple similarity metrics:
        - Keyword overlap (30%)
        - Category overlap (20%)
        - Complexity similarity (20%)
        - Feature similarity (30%)

        Args:
            ref_metadata: Reference content metadata
            candidate: Candidate content to compare

        Returns:
            Similarity score (0-1)
        """
        cand_metadata_result = await self.content_analyzer.extract_content_metadata(candidate)

        # Return 0 similarity if metadata extraction failed
        if cand_metadata_result.is_error:
            logger.warning(
                f"Failed to extract candidate metadata, returning 0 similarity: {cand_metadata_result.error}"
            )
            return 0.0

        cand_metadata = cand_metadata_result.value

        similarity = 0.0

        # Keyword overlap
        ref_keywords = set(ref_metadata.keywords)
        cand_keywords = set(cand_metadata.keywords)
        if ref_keywords and cand_keywords:
            keyword_overlap = len(ref_keywords & cand_keywords) / len(ref_keywords | cand_keywords)
            similarity += keyword_overlap * 0.3

        # Category overlap
        ref_categories = set(ref_metadata.topic_categories or [])
        cand_categories = set(cand_metadata.topic_categories or [])
        if ref_categories and cand_categories:
            category_overlap = len(ref_categories & cand_categories) / len(
                ref_categories | cand_categories
            )
            similarity += category_overlap * 0.2

        # Complexity similarity
        complexity_diff = abs(ref_metadata.complexity_score - cand_metadata.complexity_score)
        similarity += (1 - complexity_diff) * 0.2

        # Feature similarity
        feature_match = 0
        if ref_metadata.has_code == cand_metadata.has_code:
            feature_match += 0.25
        if ref_metadata.has_exercises == cand_metadata.has_exercises:
            feature_match += 0.25
        if ref_metadata.has_images == cand_metadata.has_images:
            feature_match += 0.25
        if abs(ref_metadata.reading_time_minutes - cand_metadata.reading_time_minutes) <= 5:
            feature_match += 0.25
        similarity += feature_match * 0.3

        return similarity
