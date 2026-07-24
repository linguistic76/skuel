"""
Insight Synthesis Mixin — InsightGenerationService
==================================================

Turns detected TaskPatterns into actionable GeneratedInsights: per-type
generators, cross-pattern correlation, and impact scoring/ranking.

Part of insight_generation_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from operator import attrgetter
from typing import Any

from core.models.insight import GeneratedInsight, InsightCategory, PatternType, TaskPattern
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result


class _InsightSynthesisMixin:
    """
    Insight generation from task-completion patterns for InsightGenerationService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by InsightGenerationService.__init__
    logger: Any

    @with_error_handling("generate_insights_from_patterns", error_type="system")
    def generate_insights_from_patterns(
        self, patterns: list[TaskPattern]
    ) -> Result[list[GeneratedInsight]]:
        """
        Generate actionable insights from detected task completion patterns.

        Args:
            patterns: List of TaskPattern objects to analyze

        Returns:
            Result containing GeneratedInsight objects
        """
        if not patterns:
            return Result.ok([])

        insights = []

        # Group patterns by type for insight generation
        pattern_groups = defaultdict(list)
        for pattern in patterns:
            pattern_groups[pattern.pattern_type].append(pattern)

        # Generate insights for each pattern type
        for pattern_type, type_patterns in pattern_groups.items():
            type_insights = self._generate_insights_for_pattern_type(pattern_type, type_patterns)
            insights.extend(type_insights)

        # Generate cross-pattern insights
        cross_insights = self._generate_cross_pattern_insights(patterns)
        insights.extend(cross_insights)

        # Score and rank insights
        scored_insights = self._score_insights(insights)

        self.logger.info(f"Generated {len(scored_insights)} insights from {len(patterns)} patterns")

        return Result.ok(scored_insights)

    def _generate_insights_for_pattern_type(
        self, pattern_type: PatternType, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights for a specific pattern type."""
        insights = []

        if pattern_type == PatternType.BEST_PRACTICE:
            insights.extend(self._generate_best_practice_insights(patterns))
        elif pattern_type == PatternType.KNOWLEDGE_APPLICATION:
            insights.extend(self._generate_knowledge_application_insights(patterns))
        elif pattern_type == PatternType.WORKFLOW_OPTIMIZATION:
            insights.extend(self._generate_workflow_insights(patterns))
        elif pattern_type == PatternType.TIME_MANAGEMENT:
            insights.extend(self._generate_time_management_insights(patterns))

        return insights

    def _generate_knowledge_application_insights(
        self, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate LEARNING insights from knowledge-application efficiency patterns.

        Emitted by :meth:`_analyze_knowledge_application_patterns` — the signal that
        explicitly applying knowledge (``APPLIES_KNOWLEDGE`` edges) drives efficiency,
        which is the heart of SKUEL as a semantic knowledge graph.
        """
        return [
            GeneratedInsight(
                insight_id=f"insight_knowledge_application_{datetime.now().strftime('%Y%m%d_%H%M')}",
                category=InsightCategory.LEARNING,
                title="Knowledge Application Drives Efficiency",
                description=(
                    "Tasks that explicitly apply existing knowledge consistently show "
                    "higher efficiency and success rates."
                ),
                actionable_recommendation=(
                    "When creating new tasks, actively identify and link relevant "
                    "knowledge units to improve execution efficiency."
                ),
                supporting_patterns=[pattern.pattern_id],
                confidence_score=pattern.confidence_score,
                impact_score=0.8,
                generated_at=datetime.now(),
                tags=["knowledge-application", "efficiency", "best-practice"],
                metadata={
                    "pattern_type": "knowledge_application",
                    "efficiency_improvement": pattern.metadata.get("knowledge_benefit", 0),
                    "knowledge_uids_involved": pattern.knowledge_uids_involved,
                },
            )
            for pattern in patterns
        ]

    def _generate_best_practice_insights(
        self, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights from best practice patterns."""
        return [
            GeneratedInsight(
                insight_id=f"insight_time_estimation_{datetime.now().strftime('%Y%m%d_%H%M')}",
                category=InsightCategory.EFFICIENCY,
                title="Accurate Time Estimation Pattern",
                description="Consistently accurate time estimation leads to better planning and reduced stress.",
                actionable_recommendation="Continue using current estimation methods and consider sharing techniques with team members.",
                supporting_patterns=[pattern.pattern_id],
                confidence_score=pattern.confidence_score,
                impact_score=0.7,
                generated_at=datetime.now(),
                tags=["time-estimation", "planning", "best-practice"],
                metadata={"estimation_accuracy": pattern.metadata.get("avg_accuracy", 0)},
            )
            for pattern in patterns
            if "time_estimation" in pattern.pattern_id
        ]

    def _generate_workflow_insights(self, patterns: list[TaskPattern]) -> list[GeneratedInsight]:
        """Generate insights from workflow optimization patterns."""
        insights = []

        for pattern in patterns:
            if "project_efficiency" in pattern.pattern_id:
                project = pattern.metadata.get("project", "Unknown")
                insights.append(
                    GeneratedInsight(
                        insight_id=f"insight_project_workflow_{project}_{datetime.now().strftime('%Y%m%d_%H%M')}",
                        category=InsightCategory.PROCESS,
                        title=f"Optimized Workflow for {project} Project",
                        description=f"The {project} project shows consistently high task completion efficiency, indicating an effective workflow.",
                        actionable_recommendation=f"Document and replicate the {project} project workflow for other similar projects.",
                        supporting_patterns=[pattern.pattern_id],
                        confidence_score=pattern.confidence_score,
                        impact_score=0.75,
                        generated_at=datetime.now(),
                        tags=["workflow", "project-management", "efficiency"],
                        metadata={
                            "project": project,
                            "efficiency": pattern.metadata.get("efficiency", 0),
                        },
                    )
                )

        return insights

    def _generate_time_management_insights(
        self, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights from time management patterns."""
        insights = []

        for pattern in patterns:
            if "early_completion" in pattern.pattern_id:
                time_saved = pattern.time_saved_minutes or 0
                insights.append(
                    GeneratedInsight(
                        insight_id=f"insight_time_management_{datetime.now().strftime('%Y%m%d_%H%M')}",
                        category=InsightCategory.EFFICIENCY,
                        title="Early Task Completion Pattern",
                        description=f"Consistently finishing tasks early with average time savings of {time_saved} minutes per task.",
                        actionable_recommendation="Consider taking on additional tasks or increasing task complexity to maximize productivity gains.",
                        supporting_patterns=[pattern.pattern_id],
                        confidence_score=pattern.confidence_score,
                        impact_score=0.6,
                        generated_at=datetime.now(),
                        tags=["time-management", "efficiency", "optimization"],
                        metadata={"avg_time_saved": time_saved},
                    )
                )

        return insights

    def _generate_cross_pattern_insights(
        self, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights from relationships between multiple patterns."""
        insights = []

        # Look for correlations between different pattern types
        best_practices = [p for p in patterns if p.pattern_type == PatternType.BEST_PRACTICE]
        optimizations = [p for p in patterns if p.pattern_type == PatternType.WORKFLOW_OPTIMIZATION]

        if best_practices and optimizations:
            insights.append(
                GeneratedInsight(
                    insight_id=f"insight_combined_effectiveness_{datetime.now().strftime('%Y%m%d_%H%M')}",
                    category=InsightCategory.STRATEGIC,
                    title="Combined Best Practices and Workflow Optimization",
                    description="The combination of applying best practices with workflow optimizations creates compounding efficiency gains.",
                    actionable_recommendation="Focus on implementing both process improvements and best practice adherence simultaneously for maximum impact.",
                    supporting_patterns=[p.pattern_id for p in best_practices + optimizations],
                    confidence_score=0.8,
                    impact_score=0.9,
                    generated_at=datetime.now(),
                    tags=["strategic", "combined-approach", "efficiency"],
                    metadata={"pattern_count": len(best_practices) + len(optimizations)},
                )
            )

        return insights

    def _score_insights(self, insights: list[GeneratedInsight]) -> list[GeneratedInsight]:
        """Score and rank insights by impact and confidence."""
        # Calculate impact scores based on multiple factors
        for insight in insights:
            # Base impact from pattern strength
            base_impact = insight.confidence_score

            # Category multipliers
            category_multipliers = {
                InsightCategory.STRATEGIC: 1.2,
                InsightCategory.LEARNING: 1.1,
                InsightCategory.EFFICIENCY: 1.0,
                InsightCategory.PROCESS: 0.9,
                InsightCategory.QUALITY: 0.8,
            }

            category_multiplier = category_multipliers.get(insight.category, 1.0)

            # Pattern count bonus (more supporting patterns = higher confidence)
            pattern_bonus = min(len(insight.supporting_patterns) * 0.1, 0.3)

            # Final impact score
            insight.impact_score = min((base_impact + pattern_bonus) * category_multiplier, 1.0)

        # Sort by impact score
        insights.sort(key=attrgetter("impact_score"), reverse=True)

        return insights
