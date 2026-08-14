"""
TaskKnowledgeAnalyzer — Task-specific knowledge pattern analytics.

Extends the generic five-pattern KnowledgePatternAnalyzer with:

- MASTERY_VALIDATION pattern detection  (task.knowledge_mastery_check / validates_knowledge_mastery)
- Knowledge-aware priority scoring       (task.priority / due_date / learning_opportunities_count)
- Ku-focused insight generation          (completion rate, velocity, mastery validation)
- Knowledge mastery progression tracking (task.calculate_knowledge_complexity)

Relationship graph access goes through self.relationship_service;
KnowledgePatternAnalyzer receives a domain-agnostic ``fetch_rels`` callable.

Was: core/services/analytics_engine.py  (class AnalyticsEngine / KuAnalyticsEngine)
See: core/services/knowledge/knowledge_pattern_analyzer.py  (generic 5-pattern base)
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, cast

from core.constants import (
    ConfidenceLevel,
    CrossDomainImpactScore,
    InsightThreshold,
    KnowledgeEnhancementScore,
    PriorityScoringWeight,
)
from core.models.enums import EntityStatus
from core.models.task.task import Task as Task
from core.services.knowledge.knowledge_pattern_analyzer import (
    ActivityInsight,
    KnowledgePatternAnalyzer,
    LearningPattern,
    LearningPatternType,
    MasteryProgression,
    _by_confidence_and_frequency,
)
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.entity import Entity
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )
    from core.services.relationships import UnifiedRelationshipService


def _task_complexity_score(entity: Entity) -> float:
    """Return Task.calculate_knowledge_complexity() for the KNOWLEDGE_BUILDING detector."""
    return cast("Task", entity).calculate_knowledge_complexity()


@dataclass
class KuAwarePriority:
    """Knowledge-aware priority scoring for tasks."""

    task_uid: str
    base_priority_score: float  # 0-1 from original priority
    knowledge_enhancement_score: float  # 0-1
    learning_opportunity_score: float  # 0-1
    mastery_progression_score: float  # 0-1
    cross_domain_impact_score: float  # 0-1
    final_priority_score: float  # 0-1
    scoring_rationale: list[str]


class TaskKnowledgeAnalyzer:
    """
    Task-specific knowledge analytics. Composes KnowledgePatternAnalyzer for the five
    generic patterns and adds MASTERY_VALIDATION and priority scoring.

    GRAPH-NATIVE: Requires UnifiedRelationshipService for relationship fetching.
    All four public methods match the API of the former AnalyticsEngine.
    """

    def __init__(
        self,
        relationship_service: UnifiedRelationshipService | None = None,
        graph_intel: GraphIntelligenceService | None = None,
    ) -> None:
        self.logger = get_logger("skuel.analytics.knowledge")
        self.relationship_service = relationship_service
        self._generic_analyzer = KnowledgePatternAnalyzer(graph_intel=graph_intel)

    # =========================================================================
    # Public methods (same API as former AnalyticsEngine)
    # =========================================================================

    async def analyze_learning_patterns(
        self, tasks: list[Task], timeframe_days: int = 30
    ) -> Result[list[LearningPattern]]:
        """
        Detect knowledge-learning patterns across user tasks.

        Delegates the five generic patterns to KnowledgePatternAnalyzer, then
        appends Task-specific MASTERY_VALIDATION patterns.

        Returns:
            Result[list[LearningPattern]] sorted by (confidence, frequency) desc.
        """
        try:
            service = self.relationship_service

            async def _fetch_task_rels(uid: str) -> TaskRelationships:
                if service:
                    return await TaskRelationships.fetch(uid, service)
                return TaskRelationships.empty()

            generic_result = await self._generic_analyzer.analyze_learning_patterns(
                tasks, _fetch_task_rels, timeframe_days, complexity_fn=_task_complexity_score
            )
            if generic_result.is_error:
                return generic_result

            cutoff = date.today() - timedelta(days=timeframe_days)
            recent_tasks = [t for t in tasks if t.created_at.date() >= cutoff]
            mastery_patterns = await self._detect_mastery_validation_patterns(recent_tasks)

            all_patterns = generic_result.value + mastery_patterns
            all_patterns.sort(key=_by_confidence_and_frequency, reverse=True)

            self.logger.info(
                "Analyzed learning patterns: %d patterns across %d tasks in %d days",
                len(all_patterns),
                len(recent_tasks),
                timeframe_days,
            )
            return Result.ok(all_patterns)

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.error("Learning pattern analysis failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Learning pattern analysis failed",
                    exception=e,
                    operation="analyze_learning_patterns",
                    task_count=len(tasks),
                    timeframe_days=timeframe_days,
                )
            )
        except Exception as e:  # safety-net: unexpected errors in analytics pipeline
            self.logger.error(
                "Unexpected error in learning pattern analysis: %s: %s", type(e).__name__, e
            )
            return Result.fail(
                Errors.system(
                    message="Learning pattern analysis failed",
                    exception=e,
                    operation="analyze_learning_patterns",
                    task_count=len(tasks),
                    timeframe_days=timeframe_days,
                )
            )

    async def resolve_ku_categories(
        self, knowledge_uids: Sequence[str]
    ) -> dict[
        str, str
    ]:  # skuel-lint: disable=SKUEL005 -- deliberate degrade-to-{}, mirrors KnowledgePatternAnalyzer.resolve_categories
        """Batch-map knowledge UIDs to their ``sel_category`` field.

        Public passthrough to the composed generic analyzer so batch callers
        (calculate_knowledge_aware_priorities) can resolve once for a whole
        task set instead of once per task.
        """
        return await self._generic_analyzer.resolve_categories(knowledge_uids)

    async def calculate_knowledge_aware_priority(
        self,
        task: Task,
        user_mastery_progressions: dict[str, MasteryProgression],
        learning_patterns: list[LearningPattern],
        ku_categories: dict[str, str] | None = None,
    ) -> Result[KuAwarePriority]:
        """
        Calculate knowledge-aware priority scoring for a task.

        Args:
            ku_categories: Optional pre-resolved uid→sel_category map. Batch
                callers pass one map for the whole task set (one query);
                when None, this task's linked uids are resolved here.

        Returns:
            Result[KuAwarePriority] with weighted composite score.
        """
        try:
            if self.relationship_service:
                rels = await TaskRelationships.fetch(task.uid, self.relationship_service)
            else:
                rels = TaskRelationships.empty()

            base_priority = self._calculate_base_priority_score(task)
            knowledge_enhancement = self._calculate_knowledge_enhancement_score(
                task, rels, user_mastery_progressions
            )
            learning_opportunity = self._calculate_learning_opportunity_score(
                task, rels, learning_patterns
            )
            mastery_progression = self._calculate_mastery_progression_score(
                task, rels, user_mastery_progressions
            )
            if ku_categories is None:
                ku_categories = await self._generic_analyzer.resolve_categories(
                    rels.applies_knowledge_uids + rels.inferred_knowledge_uids
                )
            cross_domain_impact = self._calculate_cross_domain_impact_score(
                task, rels, learning_patterns, ku_categories
            )

            final_score = (
                base_priority * PriorityScoringWeight.BASE
                + knowledge_enhancement * PriorityScoringWeight.KNOWLEDGE
                + learning_opportunity * PriorityScoringWeight.LEARNING
                + mastery_progression * PriorityScoringWeight.MASTERY
                + cross_domain_impact * PriorityScoringWeight.CROSS_DOMAIN
            )

            rationale = self._generate_priority_rationale(
                task,
                base_priority,
                knowledge_enhancement,
                learning_opportunity,
                mastery_progression,
                cross_domain_impact,
            )

            return Result.ok(
                KuAwarePriority(
                    task_uid=task.uid,
                    base_priority_score=base_priority,
                    knowledge_enhancement_score=knowledge_enhancement,
                    learning_opportunity_score=learning_opportunity,
                    mastery_progression_score=mastery_progression,
                    cross_domain_impact_score=cross_domain_impact,
                    final_priority_score=final_score,
                    scoring_rationale=rationale,
                )
            )

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.error("Knowledge-aware priority calculation failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Knowledge-aware priority calculation failed",
                    exception=e,
                    operation="calculate_knowledge_aware_priority",
                    task_uid=task.uid,
                )
            )
        except Exception as e:  # safety-net: unexpected errors in priority scoring
            self.logger.error(
                "Unexpected error in priority calculation: %s: %s", type(e).__name__, e
            )
            return Result.fail(
                Errors.system(
                    message="Knowledge-aware priority calculation failed",
                    exception=e,
                    operation="calculate_knowledge_aware_priority",
                    task_uid=task.uid,
                )
            )

    async def generate_task_insights(
        self,
        completed_tasks: list[Task],
        learning_patterns: list[LearningPattern],
    ) -> Result[list[ActivityInsight]]:
        """
        Generate insights from completed tasks.

        Returns:
            Result[list[ActivityInsight]] sorted by (impact_score, confidence) desc.
        """
        try:
            insights: list[ActivityInsight] = []
            insights.extend(await self._generate_knowledge_area_insights(completed_tasks))
            insights.extend(
                self._generate_learning_velocity_insights(completed_tasks, learning_patterns)
            )
            insights.extend(self._generate_application_effectiveness_insights(completed_tasks))
            insights.extend(self._generate_mastery_validation_insights(completed_tasks))
            insights.extend(
                self._generate_cross_domain_insights(completed_tasks, learning_patterns)
            )

            def _by_impact_and_confidence(insight: ActivityInsight) -> tuple[float, float]:
                return (insight.impact_score, insight.confidence)

            insights.sort(key=_by_impact_and_confidence, reverse=True)

            self.logger.info(
                "Generated task insights: %d insights from %d completed tasks",
                len(insights),
                len(completed_tasks),
            )
            return Result.ok(insights)

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.error("Task insight generation failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Task insight generation failed",
                    exception=e,
                    operation="generate_task_insights",
                    completed_task_count=len(completed_tasks),
                    learning_pattern_count=len(learning_patterns),
                )
            )
        except Exception as e:  # safety-net: unexpected errors in insight generation
            self.logger.error(
                "Unexpected error in task insight generation: %s: %s", type(e).__name__, e
            )
            return Result.fail(
                Errors.system(
                    message="Task insight generation failed",
                    exception=e,
                    operation="generate_task_insights",
                    completed_task_count=len(completed_tasks),
                    learning_pattern_count=len(learning_patterns),
                )
            )

    async def track_knowledge_mastery_progression(
        self, tasks: list[Task], knowledge_uids: list[str]
    ) -> Result[dict[str, MasteryProgression]]:
        """
        Track knowledge mastery progression across specified knowledge areas.

        Returns:
            Result[dict[knowledge_uid, MasteryProgression]]
        """
        try:
            if not tasks or not self.relationship_service:
                return Result.ok({})

            rels_list: list[TaskRelationships] = list(
                await asyncio.gather(
                    *[TaskRelationships.fetch(t.uid, self.relationship_service) for t in tasks]
                )
            )
            progressions: dict[str, MasteryProgression] = {}

            for knowledge_uid in knowledge_uids:
                relevant_tasks = [
                    task
                    for task, rels in zip(tasks, rels_list, strict=False)
                    if (
                        knowledge_uid in rels.applies_knowledge_uids
                        or knowledge_uid in rels.prerequisite_knowledge_uids
                        or knowledge_uid in rels.inferred_knowledge_uids
                    )
                ]
                if not relevant_tasks:
                    continue
                progressions[knowledge_uid] = self._calculate_mastery_progression(
                    knowledge_uid, relevant_tasks
                )

            self.logger.info(
                "Tracked mastery progressions: %d knowledge areas analyzed", len(progressions)
            )
            return Result.ok(progressions)

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.error("Mastery progression tracking failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Mastery progression tracking failed",
                    exception=e,
                    operation="track_knowledge_mastery_progression",
                    task_count=len(tasks),
                    knowledge_uid_count=len(knowledge_uids),
                )
            )
        except Exception as e:  # safety-net: unexpected errors in mastery tracking
            self.logger.error("Unexpected error in mastery tracking: %s: %s", type(e).__name__, e)
            return Result.fail(
                Errors.system(
                    message="Mastery progression tracking failed",
                    exception=e,
                    operation="track_knowledge_mastery_progression",
                    task_count=len(tasks),
                    knowledge_uid_count=len(knowledge_uids),
                )
            )

    # =========================================================================
    # Task-specific private helpers
    # =========================================================================

    async def _detect_mastery_validation_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """Detect tasks that explicitly validate knowledge mastery."""
        patterns: list[LearningPattern] = []
        if not tasks or not self.relationship_service:
            return patterns

        rels_list: list[TaskRelationships] = list(
            await asyncio.gather(
                *[TaskRelationships.fetch(t.uid, self.relationship_service) for t in tasks]
            )
        )

        validation_pairs = [
            (task, rels)
            for task, rels in zip(tasks, rels_list, strict=False)
            if task.knowledge_mastery_check or task.validates_knowledge_mastery()
        ]
        if len(validation_pairs) < 2:
            return patterns

        knowledge_validations: dict[str, list[Task]] = {}
        for task, rels in validation_pairs:
            all_ku_uids = rels.applies_knowledge_uids + rels.prerequisite_knowledge_uids
            for ku_uid in all_ku_uids:
                knowledge_validations.setdefault(ku_uid, []).append(task)

        for ku_uid, ku_tasks in knowledge_validations.items():
            if len(ku_tasks) < 2:
                continue
            completed_count = sum(1 for t in ku_tasks if t.status == EntityStatus.COMPLETED)
            success_rate = completed_count / len(ku_tasks) if ku_tasks else 0.0
            patterns.append(
                LearningPattern(
                    pattern_type=LearningPatternType.MASTERY_VALIDATION,
                    knowledge_uids=[ku_uid],
                    entity_uids=[t.uid for t in ku_tasks],
                    confidence=ConfidenceLevel.HIGH,
                    timeframe_days=(ku_tasks[-1].created_at - ku_tasks[0].created_at).days,
                    frequency=len(ku_tasks),
                    growth_indicator=success_rate * 2 - 1,
                    metadata={"success_rate": success_rate, "validations": len(ku_tasks)},
                )
            )
        return patterns

    def _calculate_mastery_progression(
        self, knowledge_uid: str, tasks: list[Task]
    ) -> MasteryProgression:
        """Calculate mastery progression for a knowledge area."""
        completed_tasks = [t for t in tasks if t.status == EntityStatus.COMPLETED]
        validation_tasks = [t for t in completed_tasks if t.knowledge_mastery_check]

        if completed_tasks:
            complexities = [t.calculate_knowledge_complexity() for t in completed_tasks]
            avg_complexity = statistics.mean(complexities)
            completion_rate = len(completed_tasks) / len(tasks)
            current_mastery = min(1.0, avg_complexity * completion_rate * 1.2)
        else:
            current_mastery = 0.0

        if len(completed_tasks) >= 4:
            mid = len(completed_tasks) // 2
            recent_avg = statistics.mean(
                [t.calculate_knowledge_complexity() for t in completed_tasks[mid:]]
            )
            older_avg = statistics.mean(
                [t.calculate_knowledge_complexity() for t in completed_tasks[:mid]]
            )
            trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0.0
        else:
            trend = 0.0

        if len(completed_tasks) >= 2:
            timespan = (completed_tasks[-1].created_at - completed_tasks[0].created_at).days
            velocity = current_mastery / max(1, timespan) if timespan > 0 else 0.0
        else:
            velocity = 0.0

        last_date = completed_tasks[-1].created_at.date() if completed_tasks else None
        confidence = min(1.0, len(completed_tasks) / 10.0)
        next_difficulty = (
            min(1.0, current_mastery + KnowledgeEnhancementScore.DIFFICULTY_STEP)
            if current_mastery > 0
            else KnowledgeEnhancementScore.INITIAL_DIFFICULTY
        )

        return MasteryProgression(
            knowledge_uid=knowledge_uid,
            current_mastery_level=current_mastery,
            mastery_trend=max(-1.0, min(1.0, trend)),
            activities_completed=len(completed_tasks),
            validation_activities_passed=len(validation_tasks),
            last_application_date=last_date,
            progression_velocity=velocity,
            confidence_in_assessment=confidence,
            next_recommended_difficulty=next_difficulty,
        )

    def _calculate_base_priority_score(self, task: Task) -> float:
        return PriorityScoringWeight.PRIORITY_LEVEL.get(
            task.priority.upper() if task.priority else "MEDIUM",
            PriorityScoringWeight.DEFAULT_PRIORITY,
        )

    def _calculate_knowledge_enhancement_score(
        self, task: Task, rels: TaskRelationships, progressions: dict[str, MasteryProgression]
    ) -> float:
        if not rels.applies_knowledge_uids:
            return KnowledgeEnhancementScore.NO_KNOWLEDGE_BASELINE

        enhancement_scores = []
        for ku_uid in rels.applies_knowledge_uids:
            if ku_uid in progressions:
                enhancement_scores.append(1.0 - progressions[ku_uid].current_mastery_level)
            else:
                enhancement_scores.append(KnowledgeEnhancementScore.NEW_KNOWLEDGE_POTENTIAL)

        base_score = (
            statistics.mean(enhancement_scores)
            if enhancement_scores
            else KnowledgeEnhancementScore.DEFAULT_ENHANCEMENT
        )

        priority_boost = 0.0
        if task.priority == "critical":
            priority_boost = KnowledgeEnhancementScore.CRITICAL_PRIORITY_BOOST
        elif task.priority == "high":
            priority_boost = KnowledgeEnhancementScore.HIGH_PRIORITY_BOOST

        return min(1.0, base_score + priority_boost)

    def _calculate_learning_opportunity_score(
        self, task: Task, rels: TaskRelationships, patterns: list[LearningPattern]
    ) -> float:
        base_score = task.learning_opportunities_count / 10.0

        pattern_boost = 0.0
        task_knowledge = set(rels.applies_knowledge_uids + rels.inferred_knowledge_uids)
        for pattern in patterns:
            overlap = task_knowledge.intersection(set(pattern.knowledge_uids))
            if overlap:
                pattern_boost += 0.1 * len(overlap) * pattern.confidence

        return min(1.0, base_score + pattern_boost)

    def _calculate_mastery_progression_score(
        self, task: Task, rels: TaskRelationships, progressions: dict[str, MasteryProgression]
    ) -> float:
        if not (rels.applies_knowledge_uids or rels.prerequisite_knowledge_uids):
            return KnowledgeEnhancementScore.NO_KNOWLEDGE_BASELINE

        progression_scores = []
        for ku_uid in rels.applies_knowledge_uids + rels.prerequisite_knowledge_uids:
            if ku_uid in progressions:
                prog = progressions[ku_uid]
                velocity_factor = max(0, prog.progression_velocity)
                mastery_factor = 1.0 - prog.current_mastery_level
                progression_scores.append(
                    velocity_factor * KnowledgeEnhancementScore.VELOCITY_WEIGHT
                    + mastery_factor * KnowledgeEnhancementScore.MASTERY_ROOM_WEIGHT
                )
            else:
                progression_scores.append(KnowledgeEnhancementScore.NEW_AREA_PROGRESSION)

        base_score = (
            statistics.mean(progression_scores)
            if progression_scores
            else KnowledgeEnhancementScore.NO_PROGRESSION_FALLBACK
        )

        urgency_boost = 0.0
        if task.due_date:
            days_until_due = (task.due_date - date.today()).days
            if days_until_due <= 3:
                urgency_boost = KnowledgeEnhancementScore.VERY_URGENT_BOOST
            elif days_until_due <= 7:
                urgency_boost = KnowledgeEnhancementScore.URGENT_BOOST

        return min(1.0, base_score + urgency_boost)

    def _calculate_cross_domain_impact_score(
        self,
        task: Task,
        rels: TaskRelationships,
        patterns: list[LearningPattern],
        ku_categories: dict[str, str],
    ) -> float:
        """Score cross-domain reach from the linked entities' ``sel_category``
        field (``ku_categories``, resolved by the async caller) — uid strings
        are opaque and carry no category (ADR-013 never-sniff)."""
        all_knowledge_uids = rels.applies_knowledge_uids + rels.inferred_knowledge_uids
        task_domains = set(
            self._generic_analyzer._categories_for(all_knowledge_uids, ku_categories)
        )

        if len(task_domains) <= 1:
            return CrossDomainImpactScore.SINGLE_DOMAIN_SCORE

        cross_domain_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.CROSS_DOMAIN_APPLICATION
        ]
        alignment_score = 0.0
        for pattern in cross_domain_patterns:
            # CROSS_DOMAIN patterns carry their category set in metadata —
            # written by the generic detector from the same field lookup.
            pattern_domains = set(pattern.metadata.get("sel_categories", []))
            overlap = task_domains.intersection(pattern_domains)
            if overlap:
                alignment_score += (
                    CrossDomainImpactScore.ALIGNMENT_PER_OVERLAP * len(overlap) * pattern.confidence
                )

        base_score = min(
            CrossDomainImpactScore.MAX_DOMAIN_SCORE,
            len(task_domains) * CrossDomainImpactScore.PER_DOMAIN_SCORE,
        )

        priority_boost = 0.0
        if task.priority in ["high", "critical"]:
            priority_boost = CrossDomainImpactScore.CROSS_DOMAIN_PRIORITY_BOOST

        tag_boost = 0.0
        cross_domain_tags = {"integration", "synthesis", "multidisciplinary", "interdisciplinary"}
        if any(tag in cross_domain_tags for tag in task.tags):
            tag_boost = CrossDomainImpactScore.CROSS_DOMAIN_TAG_BOOST

        return min(1.0, base_score + alignment_score + priority_boost + tag_boost)

    def _generate_priority_rationale(
        self,
        task: Task,
        base: float,
        knowledge: float,
        learning: float,
        mastery: float,
        cross_domain: float,
    ) -> list[str]:
        rationale = []
        if base > InsightThreshold.HIGH_SCORE:
            rationale.append(f"High base priority ({task.priority}) increases importance")
        elif base < InsightThreshold.LOW_SCORE:
            rationale.append(f"Low base priority ({task.priority}) reduces urgency")
        if knowledge > InsightThreshold.HIGH_SCORE:
            rationale.append("Strong knowledge enhancement potential detected")
        if learning > InsightThreshold.HIGH_SCORE:
            rationale.append("High learning opportunity value identified")
        if mastery > InsightThreshold.HIGH_SCORE:
            rationale.append("Significant mastery progression impact expected")
        if cross_domain > InsightThreshold.HIGH_SCORE:
            rationale.append("Notable cross-domain knowledge application potential")
        if not rationale:
            rationale.append("Standard priority scoring applied")
        return rationale

    async def _generate_knowledge_area_insights(self, tasks: list[Task]) -> list[ActivityInsight]:
        insights: list[ActivityInsight] = []
        if not tasks or not self.relationship_service:
            return insights

        rels_list: list[TaskRelationships] = list(
            await asyncio.gather(
                *[TaskRelationships.fetch(t.uid, self.relationship_service) for t in tasks]
            )
        )

        knowledge_usage: dict[str, dict[str, Any]] = {}
        for task, rels in zip(tasks, rels_list, strict=False):
            all_ku_uids = rels.applies_knowledge_uids + rels.inferred_knowledge_uids
            for ku_uid in all_ku_uids:
                ku_data = knowledge_usage.setdefault(ku_uid, {"count": 0, "complexity_sum": 0.0})
                ku_data["count"] += 1
                ku_data["complexity_sum"] += task.calculate_knowledge_complexity()

        if not knowledge_usage:
            return insights

        def _usage_count_key(item: tuple[str, dict[str, Any]]) -> int:
            return int(item[1]["count"])

        sorted_usage = sorted(knowledge_usage.items(), key=_usage_count_key, reverse=True)
        top_ku, top_data = sorted_usage[0]
        avg_complexity = top_data["complexity_sum"] / top_data["count"]

        insights.append(
            ActivityInsight(
                insight_type="knowledge_focus",
                title=f"Primary Knowledge Focus: {top_ku}",
                description=(
                    f"You've applied {top_ku} in {top_data['count']} tasks "
                    f"with average complexity {avg_complexity:.2f}"
                ),
                knowledge_areas_involved=[top_ku],
                supporting_evidence=[
                    f"{top_data['count']} task applications",
                    f"Average complexity: {avg_complexity:.2f}",
                ],
                confidence=ConfidenceLevel.HIGH,
                actionable_recommendations=[
                    f"Consider advanced applications of {top_ku}",
                    f"Explore related knowledge areas to expand {top_ku} application",
                ],
                impact_score=0.8,
            )
        )

        if len(sorted_usage) > 3:
            bottom_ku, bottom_data = sorted_usage[-1]
            insights.append(
                ActivityInsight(
                    insight_type="knowledge_gap",
                    title=f"Underutilized Knowledge: {bottom_ku}",
                    description=(
                        f"Limited application of {bottom_ku} — only {bottom_data['count']} tasks"
                    ),
                    knowledge_areas_involved=[bottom_ku],
                    supporting_evidence=[
                        f"Only {bottom_data['count']} applications",
                        "Opportunity for growth",
                    ],
                    confidence=ConfidenceLevel.MEDIUM,
                    actionable_recommendations=[
                        f"Create tasks that specifically apply {bottom_ku}",
                        f"Look for opportunities to combine {bottom_ku} with other knowledge areas",
                    ],
                    impact_score=0.6,
                )
            )

        return insights

    def _generate_learning_velocity_insights(
        self, _tasks: list[Task], patterns: list[LearningPattern]
    ) -> list[ActivityInsight]:
        insights: list[ActivityInsight] = []
        building_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.KNOWLEDGE_BUILDING
        ]
        if not building_patterns:
            return insights

        avg_growth = statistics.mean([p.growth_indicator for p in building_patterns])
        if avg_growth > InsightThreshold.STRONG_GROWTH:
            insights.append(
                ActivityInsight(
                    insight_type="learning_velocity",
                    title="Strong Learning Progression Detected",
                    description=f"Your knowledge building shows positive growth (average {avg_growth:.2f})",
                    knowledge_areas_involved=[
                        ku for p in building_patterns for ku in p.knowledge_uids
                    ],
                    supporting_evidence=[
                        f"{len(building_patterns)} knowledge building patterns detected",
                        f"Average growth indicator: {avg_growth:.2f}",
                    ],
                    confidence=ConfidenceLevel.STANDARD,
                    actionable_recommendations=[
                        "Maintain current learning momentum",
                        "Consider tackling more complex challenges in strong areas",
                    ],
                    impact_score=0.9,
                )
            )
        elif avg_growth < InsightThreshold.NEGATIVE_GROWTH:
            insights.append(
                ActivityInsight(
                    insight_type="learning_challenge",
                    title="Learning Velocity Slowdown Detected",
                    description=f"Recent learning progression shows some challenges (growth {avg_growth:.2f})",
                    knowledge_areas_involved=[
                        ku for p in building_patterns for ku in p.knowledge_uids
                    ],
                    supporting_evidence=[
                        f"Negative growth in {len(building_patterns)} areas",
                        f"Average growth indicator: {avg_growth:.2f}",
                    ],
                    confidence=ConfidenceLevel.MEDIUM,
                    actionable_recommendations=[
                        "Review fundamentals in challenging areas",
                        "Break down complex tasks into smaller steps",
                        "Seek additional resources or guidance",
                    ],
                    impact_score=0.8,
                )
            )
        return insights

    def _generate_application_effectiveness_insights(
        self, tasks: list[Task]
    ) -> list[ActivityInsight]:
        insights: list[ActivityInsight] = []
        if not tasks or not self.relationship_service:
            return insights

        completed_tasks = [t for t in tasks if t.status == EntityStatus.COMPLETED]
        if len(completed_tasks) < 5:
            return insights

        complexities = [t.calculate_knowledge_complexity() for t in completed_tasks]
        completion_rate = len(completed_tasks) / len(tasks)
        avg_complexity = statistics.mean(complexities)

        if (
            completion_rate > InsightThreshold.HIGH_COMPLETION_RATE
            and avg_complexity > InsightThreshold.HIGH_COMPLEXITY
        ):
            insights.append(
                ActivityInsight(
                    insight_type="application_effectiveness",
                    title="High Knowledge Application Effectiveness",
                    description=f"Excellent completion rate ({completion_rate:.1%}) for complex knowledge tasks",
                    knowledge_areas_involved=[],
                    supporting_evidence=[
                        f"Completion rate: {completion_rate:.1%}",
                        f"Average task complexity: {avg_complexity:.2f}",
                    ],
                    confidence=ConfidenceLevel.HIGH,
                    actionable_recommendations=[
                        "Continue current approach to complex tasks",
                        "Consider mentoring others or sharing knowledge",
                    ],
                    impact_score=0.8,
                )
            )
        return insights

    def _generate_mastery_validation_insights(self, tasks: list[Task]) -> list[ActivityInsight]:
        insights: list[ActivityInsight] = []
        validation_tasks = [t for t in tasks if t.knowledge_mastery_check]
        if not validation_tasks:
            return insights

        completed_validations = [t for t in validation_tasks if t.status == EntityStatus.COMPLETED]
        validation_rate = len(completed_validations) / len(validation_tasks)

        if validation_rate > InsightThreshold.STRONG_VALIDATION_RATE:
            insights.append(
                ActivityInsight(
                    insight_type="mastery_validation",
                    title="Strong Knowledge Mastery Validation",
                    description=f"High success rate ({validation_rate:.1%}) in knowledge validation tasks",
                    knowledge_areas_involved=[],
                    supporting_evidence=[
                        f"Validation success rate: {validation_rate:.1%}",
                        f"Total validation tasks: {len(validation_tasks)}",
                    ],
                    confidence=ConfidenceLevel.STANDARD,
                    actionable_recommendations=[
                        "Continue regular knowledge validation",
                        "Explore advanced applications of validated knowledge",
                    ],
                    impact_score=0.7,
                )
            )
        elif validation_rate < InsightThreshold.WEAK_VALIDATION_RATE:
            insights.append(
                ActivityInsight(
                    insight_type="mastery_challenge",
                    title="Knowledge Validation Challenges",
                    description=f"Lower success rate ({validation_rate:.1%}) in validation tasks suggests need for reinforcement",
                    knowledge_areas_involved=[],
                    supporting_evidence=[
                        f"Validation success rate: {validation_rate:.1%}",
                        "Opportunities for improvement identified",
                    ],
                    confidence=ConfidenceLevel.MEDIUM,
                    actionable_recommendations=[
                        "Review and strengthen foundational knowledge",
                        "Practice more before attempting validation tasks",
                        "Seek additional learning resources",
                    ],
                    impact_score=0.8,
                )
            )
        return insights

    def _generate_cross_domain_insights(
        self, _tasks: list[Task], patterns: list[LearningPattern]
    ) -> list[ActivityInsight]:
        insights: list[ActivityInsight] = []
        cross_domain_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.CROSS_DOMAIN_APPLICATION
        ]
        if not cross_domain_patterns:
            return insights

        total_domains: set[str] = set()
        for pattern in cross_domain_patterns:
            # Category sets ride on the patterns' metadata (field-derived by
            # the generic detector) — never re-parsed from uid strings.
            total_domains.update(pattern.metadata.get("sel_categories", []))

        insights.append(
            ActivityInsight(
                insight_type="cross_domain_integration",
                title="Cross-Domain Knowledge Integration",
                description=f"Successfully integrating knowledge across {len(total_domains)} knowledge areas",
                knowledge_areas_involved=[
                    ku for p in cross_domain_patterns for ku in p.knowledge_uids
                ],
                supporting_evidence=[
                    f"{len(cross_domain_patterns)} cross-domain patterns detected",
                    f"Domains involved: {', '.join(sorted(total_domains))}",
                ],
                confidence=ConfidenceLevel.STANDARD,
                actionable_recommendations=[
                    "Continue exploring connections between different knowledge areas",
                    "Look for opportunities to apply integrated knowledge to complex problems",
                ],
                impact_score=0.9,
            )
        )
        return insights
