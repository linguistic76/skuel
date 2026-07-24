"""
Quality Curation Mixin — InsightGenerationService
=================================================

Knowledge quality scoring (six metric scorers + composite), curation into
publication categories, and insight-to-knowledge-unit conversion.

Part of insight_generation_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain, EntityType
from core.models.insight import GeneratedInsight, KuQualityMetrics
from core.ports import HasMetadata, HasSummary
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.models.type_hints import UserUID


class _QualityCurationMixin:
    """
    Knowledge quality scoring and curation for InsightGenerationService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by InsightGenerationService.__init__
    logger: Any
    auto_publish_threshold: float

    @with_error_handling("score_knowledge_quality", error_type="system")
    def score_knowledge_quality(
        self, knowledge_dto: CurriculumDTO, supporting_evidence: list[str] | None = None
    ) -> Result[KuQualityMetrics]:
        """
        Score the quality of generated knowledge using multiple metrics.

        Args:
            knowledge_dto: The knowledge unit to score,
            supporting_evidence: Evidence supporting the knowledge

        Returns:
            Result containing KuQualityMetrics
        """
        metrics = KuQualityMetrics(
            completeness_score=self._score_completeness(knowledge_dto),
            accuracy_score=self._score_accuracy(knowledge_dto, supporting_evidence),
            relevance_score=self._score_relevance(knowledge_dto),
            timeliness_score=self._score_timeliness(knowledge_dto),
            actionability_score=self._score_actionability(knowledge_dto),
            evidence_strength=self._score_evidence_strength(supporting_evidence),
            overall_quality=0.0,  # Will be computed
        )

        metrics.compute_overall_quality()

        self.logger.debug(
            f"Knowledge quality score for {knowledge_dto.uid}: {metrics.overall_quality:.2f}"
        )

        return Result.ok(metrics)

    def _score_completeness(self, knowledge_dto: CurriculumDTO) -> float:
        """Score how complete the knowledge content is."""
        score = 0.0

        # Check for essential components
        if knowledge_dto.title and len(knowledge_dto.title.strip()) > 5:
            score += 0.2

        if knowledge_dto.content and len(knowledge_dto.content.strip()) > 50:
            score += 0.3

        if knowledge_dto.tags:
            score += 0.2

        if isinstance(knowledge_dto, HasSummary) and knowledge_dto.summary:
            score += 0.15

        # Check content depth
        if knowledge_dto.content:
            word_count = len(knowledge_dto.content.split())
            if word_count > 100:
                score += 0.15
            elif word_count > 50:
                score += 0.1

        return min(score, 1.0)

    def _score_accuracy(
        self, knowledge_dto: CurriculumDTO, evidence: list[str] | None = None
    ) -> float:
        """Score the accuracy of the knowledge content."""
        # Since this is generated from actual task completion data, base accuracy is high
        base_score = 0.8

        # Boost for evidence
        if evidence and len(evidence) > 0:
            evidence_boost = min(len(evidence) * 0.05, 0.2)
            base_score += evidence_boost

        # Check for specific claims or metrics
        if knowledge_dto.content:
            # Look for quantified claims (more reliable)
            import re

            if re.search(r"\d+%|\d+\.\d+|\d+ minutes|\d+ tasks", knowledge_dto.content):
                base_score += 0.1

        return min(base_score, 1.0)

    def _score_relevance(self, knowledge_dto: CurriculumDTO) -> float:
        """Score how relevant the knowledge is to users."""
        score = 0.7  # Base relevance for task-derived knowledge

        # Check for actionable content
        actionable_keywords = [
            "should",
            "can",
            "will",
            "recommend",
            "consider",
            "try",
            "use",
            "apply",
        ]
        if knowledge_dto.content:
            content_lower = knowledge_dto.content.lower()
            actionable_count = sum(1 for keyword in actionable_keywords if keyword in content_lower)
            score += min(actionable_count * 0.05, 0.2)

        # Domain-specific relevance
        if knowledge_dto.domain:
            score += 0.1  # Domain-specific knowledge is more relevant

        return min(score, 1.0)

    def _score_timeliness(self, knowledge_dto: CurriculumDTO) -> float:
        """Score how timely/current the knowledge is."""
        # Generated knowledge is inherently timely (based on recent tasks)
        base_score = 0.9

        # Check if content mentions recent technologies or practices
        if knowledge_dto.content:
            current_keywords = ["2024", "2025", "latest", "new", "modern", "current", "recent"]
            content_lower = knowledge_dto.content.lower()
            if any(keyword in content_lower for keyword in current_keywords):
                base_score += 0.1

        return min(base_score, 1.0)

    def _score_actionability(self, knowledge_dto: CurriculumDTO) -> float:
        """Score how actionable the knowledge is."""
        score = 0.0

        if knowledge_dto.content:
            content_lower = knowledge_dto.content.lower()

            # Look for action words
            action_words = [
                "implement",
                "use",
                "apply",
                "try",
                "consider",
                "start",
                "begin",
                "create",
            ]
            action_count = sum(1 for word in action_words if word in content_lower)
            score += min(action_count * 0.1, 0.4)

            # Look for specific instructions
            if "step" in content_lower or "how to" in content_lower:
                score += 0.3

            # Look for recommendations
            if "recommend" in content_lower or "suggestion" in content_lower:
                score += 0.2

            # Check for concrete examples
            if "example" in content_lower or "for instance" in content_lower:
                score += 0.1

        return min(score, 1.0)

    def _score_evidence_strength(self, evidence: list[str] | None = None) -> float:
        """Score the strength of supporting evidence."""
        if not evidence:
            return 0.3  # Low score for no evidence

        score = 0.5  # Base score for having some evidence

        # More evidence = higher score
        evidence_boost = min(len(evidence) * 0.1, 0.3)
        score += evidence_boost

        # Quality of evidence (look for quantified claims)
        quantified_evidence = sum(1 for e in evidence if any(char.isdigit() for char in e))

        if quantified_evidence > 0:
            score += min(quantified_evidence * 0.1, 0.2)

        return min(score, 1.0)

    @with_error_handling("curate_generated_knowledge", error_type="system")
    def curate_generated_knowledge(
        self, knowledge_units: list[CurriculumDTO], auto_publish_threshold: float | None = None
    ) -> Result[dict[str, list[CurriculumDTO]]]:
        """
        Curate generated knowledge by quality, organizing into publication categories.

        Args:
            knowledge_units: List of generated knowledge units,
            auto_publish_threshold: Threshold for automatic publication

        Returns:
            Result containing categorized knowledge units
        """
        if auto_publish_threshold is None:
            auto_publish_threshold = self.auto_publish_threshold

        categorized: dict[str, list[Any]] = {
            "auto_publish": [],
            "review_recommended": [],
            "needs_improvement": [],
            "low_quality": [],
        }

        for knowledge_dto in knowledge_units:
            quality_result = self.score_knowledge_quality(knowledge_dto)
            if quality_result.is_error:
                continue

            quality_metrics = quality_result.value

            # Add quality score to metadata
            if not isinstance(knowledge_dto, HasMetadata):
                knowledge_dto.metadata = {}
            knowledge_dto.metadata["quality_score"] = quality_metrics.overall_quality
            knowledge_dto.metadata["quality_metrics"] = quality_metrics.__dict__

            # Categorize by quality
            if quality_metrics.overall_quality >= auto_publish_threshold:
                categorized["auto_publish"].append(knowledge_dto)
            elif quality_metrics.overall_quality >= 0.7:
                categorized["review_recommended"].append(knowledge_dto)
            elif quality_metrics.overall_quality >= 0.5:
                categorized["needs_improvement"].append(knowledge_dto)
            else:
                categorized["low_quality"].append(knowledge_dto)

        self.logger.info(
            f"Curated {len(knowledge_units)} knowledge units: "
            f"auto_publish={len(categorized['auto_publish'])}, "
            f"review={len(categorized['review_recommended'])}, "
            f"improve={len(categorized['needs_improvement'])}, "
            f"low_quality={len(categorized['low_quality'])}"
        )

        return Result.ok(categorized)

    def _convert_insight_to_knowledge(
        self, insight: GeneratedInsight, user_uid: UserUID
    ) -> CurriculumDTO | None:
        """Convert a generated insight into a knowledge unit."""
        try:
            # Generate knowledge content from insight
            content = self._format_insight_as_ku_content(insight)

            # Create knowledge DTO
            return CurriculumDTO(
                uid=UIDGenerator.generate_knowledge_uid(title=insight.title),
                entity_type=EntityType.KU,
                title=insight.title,
                content=content,
                domain=Domain.KNOWLEDGE,
                tags=[*insight.tags, "auto-generated", "task-insights"],
                metadata={
                    "generated_from_insight": insight.insight_id,
                    "insight_category": insight.category.value,
                    "confidence_score": insight.confidence_score,
                    "impact_score": insight.impact_score,
                    "generated_at": insight.generated_at.isoformat(),
                    "generated_by": "ku_generation_service",
                    "source_user": user_uid,
                },
            )

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.warning(f"Failed to convert insight to knowledge: {e}")
            return None
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.warning(
                f"Unexpected error converting insight to knowledge: {type(e).__name__}: {e}"
            )
            return None

    def _format_insight_as_ku_content(self, insight: GeneratedInsight) -> str:
        """Format an insight as structured knowledge content."""
        content_parts = [
            f"# {insight.title}\n",
            f"**Category:** {insight.category.value.title()}\n",
            f"**Description:**\n{insight.description}\n",
            f"**Actionable Recommendation:**\n{insight.actionable_recommendation}\n",
        ]

        if insight.supporting_patterns:
            content_parts.append("**Supporting Evidence:**\n")
            content_parts.append(
                f"- Based on analysis of {len(insight.supporting_patterns)} task completion patterns"
            )
            content_parts.append(f"- Confidence score: {insight.confidence_score:.1%}")
            content_parts.append(f"- Impact score: {insight.impact_score:.1%}\n")

        if insight.tags:
            content_parts.append(f"**Tags:** {', '.join(insight.tags)}\n")

        content_parts.append(
            f"*Generated on {insight.generated_at.strftime('%Y-%m-%d %H:%M')} from task completion analysis.*"
        )

        return "\n".join(content_parts)
