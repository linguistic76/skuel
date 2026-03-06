"""
Knowledge Analytics Engine
======================================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY ArticleService and TasksService, not a duplicate.

Advanced analytics and insights for knowledge-aware learning patterns.
Provides learning pattern recognition, knowledge-aware priority scoring,
insight generation, and knowledge mastery progression tracking.

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into TasksService for knowledge-aware task analysis
- Specialized utility, not part of core KU CRUD operations
- See `/core/services/article/README.md` for architecture overview
"""

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.models.enums import EntityStatus, EntityType
from core.models.task.task import Task as Task
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.relationships import UnifiedRelationshipService


class LearningPatternType(Enum):
    """Types of learning patterns detected in user activities."""

    KNOWLEDGE_BUILDING = "knowledge_building"  # Progressive skill building
    CROSS_DOMAIN_APPLICATION = "cross_domain_application"  # Applying knowledge across domains
    MASTERY_VALIDATION = "mastery_validation"  # Tasks that validate knowledge mastery
    LEARNING_SPIRAL = "learning_spiral"  # Returning to concepts with increased complexity
    SKILL_SPECIALIZATION = "skill_specialization"  # Deep focus on specific areas
    KNOWLEDGE_BRIDGING = "knowledge_bridging"  # Connecting different knowledge areas


@dataclass
class LearningPattern:
    """Represents a detected learning pattern."""

    pattern_type: LearningPatternType
    knowledge_uids: list[str]
    task_uids: list[str]
    confidence: float  # 0-1
    timeframe_days: int
    frequency: int  # Number of occurrences
    growth_indicator: float  # -1 to 1, negative = decline, positive = growth
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MasteryProgression:
    """Tracks mastery progression for a specific knowledge area."""

    knowledge_uid: str
    current_mastery_level: float  # 0-1
    mastery_trend: float  # -1 to 1
    tasks_completed: int
    validation_tasks_passed: int
    last_application_date: date | None
    progression_velocity: float  # Mastery gain per day
    confidence_in_assessment: float  # 0-1
    next_recommended_difficulty: float  # 0-1


@dataclass
class TaskInsight:
    """Insights generated from completed tasks."""

    insight_type: str
    title: str
    description: str
    knowledge_areas_involved: list[str]
    supporting_evidence: list[str]
    confidence: float  # 0-1
    actionable_recommendations: list[str]
    impact_score: float  # 0-1


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


class AnalyticsEngine:
    """
    Advanced analytics engine for knowledge-aware learning insights.

    GRAPH-NATIVE: Requires UnifiedRelationshipService for fetching task relationships.

    Provides:
    - Learning pattern recognition across user activities
    - Knowledge-aware priority scoring algorithms
    - Insight generation from completed tasks
    - Knowledge mastery progression tracking
    """

    def __init__(self, relationship_service: "UnifiedRelationshipService | None" = None) -> None:
        """
        Initialize AnalyticsEngine.

        Args:
            relationship_service: Service for fetching task relationships from graph.
                                 Required for methods that analyze task knowledge complexity.
        """
        self.logger = get_logger("skuel.analytics.knowledge")
        self.relationship_service = relationship_service
        self._pattern_cache: dict[str, Any] = {}
        self._mastery_progressions: dict[str, MasteryProgression] = {}

    async def analyze_learning_patterns(
        self, tasks: list[Task], timeframe_days: int = 30
    ) -> Result[list[LearningPattern]]:
        """
        Analyze learning patterns across user activities.

        Args:
            tasks: List of tasks to analyze,
            timeframe_days: Analysis timeframe

        Returns:
            Result containing detected learning patterns
        """
        try:
            cutoff_date = date.today() - timedelta(days=timeframe_days)
            recent_tasks = [task for task in tasks if task.created_at.date() >= cutoff_date]

            patterns = []

            # Detect knowledge building patterns
            knowledge_building = await self._detect_knowledge_building_patterns(recent_tasks)
            patterns.extend(knowledge_building)

            # Detect cross-domain application patterns
            cross_domain = await self._detect_cross_domain_patterns(recent_tasks)
            patterns.extend(cross_domain)

            # Detect mastery validation patterns
            mastery_validation = await self._detect_mastery_validation_patterns(recent_tasks)
            patterns.extend(mastery_validation)

            # Detect learning spiral patterns
            learning_spirals = await self._detect_learning_spiral_patterns(recent_tasks)
            patterns.extend(learning_spirals)

            # Detect skill specialization patterns
            specialization = await self._detect_skill_specialization_patterns(recent_tasks)
            patterns.extend(specialization)

            # Detect knowledge bridging patterns
            bridging = await self._detect_knowledge_bridging_patterns(recent_tasks)
            patterns.extend(bridging)

            # Sort by confidence and significance
            def by_confidence_and_frequency(pattern: LearningPattern) -> tuple[float, int]:
                return (pattern.confidence, pattern.frequency)

            patterns.sort(key=by_confidence_and_frequency, reverse=True)

            self.logger.info(
                "Analyzed learning patterns: %d patterns detected across %d tasks in %d days",
                len(patterns),
                len(recent_tasks),
                timeframe_days,
            )

            return Result.ok(patterns)

        except Exception as e:
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

    async def calculate_knowledge_aware_priority(
        self,
        task: Task,
        user_mastery_progressions: dict[str, MasteryProgression],
        learning_patterns: list[LearningPattern],
    ) -> Result[KuAwarePriority]:
        """
        Calculate knowledge-aware priority scoring for a task.

        Args:
            task: Task to score,
            user_mastery_progressions: Current mastery progressions,
            learning_patterns: User's learning patterns

        Returns:
            Result containing knowledge-aware priority scoring
        """
        try:
            # GRAPH-NATIVE: Fetch task relationships once
            if self.relationship_service:
                rels = await TaskRelationships.fetch(task.uid, self.relationship_service)
            else:
                rels = TaskRelationships.empty()

            # Base priority from task priority enum
            base_priority = self._calculate_base_priority_score(task)

            # Knowledge enhancement potential
            knowledge_enhancement = await self._calculate_knowledge_enhancement_score(
                task, rels, user_mastery_progressions
            )

            # Learning opportunity value
            learning_opportunity = await self._calculate_learning_opportunity_score(
                task, rels, learning_patterns
            )

            # Mastery progression impact
            mastery_progression = await self._calculate_mastery_progression_score(
                task, rels, user_mastery_progressions
            )

            # Cross-domain impact potential
            cross_domain_impact = await self._calculate_cross_domain_impact_score(
                task, rels, learning_patterns
            )

            # Weighted final score
            weights = {
                "base": 0.3,
                "knowledge": 0.25,
                "learning": 0.2,
                "mastery": 0.15,
                "cross_domain": 0.1,
            }

            final_score = (
                base_priority * weights["base"]
                + knowledge_enhancement * weights["knowledge"]
                + learning_opportunity * weights["learning"]
                + mastery_progression * weights["mastery"]
                + cross_domain_impact * weights["cross_domain"]
            )

            # Generate scoring rationale
            rationale = self._generate_priority_rationale(
                task,
                base_priority,
                knowledge_enhancement,
                learning_opportunity,
                mastery_progression,
                cross_domain_impact,
            )

            priority_result = KuAwarePriority(
                task_uid=task.uid,
                base_priority_score=base_priority,
                knowledge_enhancement_score=knowledge_enhancement,
                learning_opportunity_score=learning_opportunity,
                mastery_progression_score=mastery_progression,
                cross_domain_impact_score=cross_domain_impact,
                final_priority_score=final_score,
                scoring_rationale=rationale,
            )

            return Result.ok(priority_result)

        except Exception as e:
            self.logger.error("Knowledge-aware priority calculation failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Knowledge-aware priority calculation failed",
                    exception=e,
                    operation="calculate_knowledge_aware_priority",
                    task_uid=task.uid,
                )
            )

    async def generate_task_insights(
        self, completed_tasks: list[Task], learning_patterns: list[LearningPattern]
    ) -> Result[list[TaskInsight]]:
        """
        Generate insights from completed tasks.

        Args:
            completed_tasks: List of completed tasks to analyze,
            learning_patterns: User's learning patterns

        Returns:
            Result containing generated insights
        """
        try:
            insights = []

            # Analyze completion patterns for knowledge areas
            knowledge_insights = await self._generate_knowledge_area_insights(completed_tasks)
            insights.extend(knowledge_insights)

            # Analyze learning velocity insights
            velocity_insights = await self._generate_learning_velocity_insights(
                completed_tasks, learning_patterns
            )
            insights.extend(velocity_insights)

            # Analyze knowledge application effectiveness
            application_insights = await self._generate_application_effectiveness_insights(
                completed_tasks
            )
            insights.extend(application_insights)

            # Analyze mastery validation insights
            mastery_insights = await self._generate_mastery_validation_insights(completed_tasks)
            insights.extend(mastery_insights)

            # Analyze cross-domain connection insights
            connection_insights = await self._generate_cross_domain_insights(
                completed_tasks, learning_patterns
            )
            insights.extend(connection_insights)

            # Sort by impact and confidence
            def by_impact_and_confidence(insight: TaskInsight) -> tuple[float, float]:
                return (insight.impact_score, insight.confidence)

            insights.sort(key=by_impact_and_confidence, reverse=True)

            self.logger.info(
                "Generated task insights: %d insights from %d completed tasks",
                len(insights),
                len(completed_tasks),
            )

            return Result.ok(insights)

        except Exception as e:
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

    async def track_knowledge_mastery_progression(
        self, tasks: list[Task], knowledge_uids: list[str]
    ) -> Result[dict[str, MasteryProgression]]:
        """
        Track knowledge mastery progression across specified knowledge areas.

        Args:
            tasks: All tasks to analyze,
            knowledge_uids: Knowledge UIDs to track

        Returns:
            Result containing mastery progressions by knowledge UID
        """
        try:
            if not tasks or not self.relationship_service:
                return Result.ok({})

            progressions = {}

            # GRAPH-NATIVE: Fetch all relationships in parallel
            rels_list = await asyncio.gather(
                *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
            )

            for knowledge_uid in knowledge_uids:
                # Find tasks that apply or validate this knowledge
                relevant_task_rels: list[tuple[Task, TaskRelationships]] = [
                    (task, rels)
                    for task, rels in zip(tasks, rels_list, strict=False)
                    if (
                        knowledge_uid in rels.applies_knowledge_uids
                        or knowledge_uid in rels.prerequisite_knowledge_uids
                        or knowledge_uid in rels.inferred_knowledge_uids
                    )
                ]
                relevant_tasks = [task for task, _ in relevant_task_rels]

                if not relevant_tasks:
                    continue

                progression = await self._calculate_mastery_progression(
                    knowledge_uid, relevant_tasks
                )
                progressions[knowledge_uid] = progression

            self.logger.info(
                "Tracked mastery progressions: %d knowledge areas analyzed", len(progressions)
            )

            return Result.ok(progressions)

        except Exception as e:
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

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    async def _detect_knowledge_building_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """
        Detect progressive knowledge building patterns.

        GRAPH-NATIVE: Fetches relationships from graph for all tasks in parallel.
        """
        patterns: list[LearningPattern] = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Group tasks by knowledge areas (with relationships)
        knowledge_groups: dict[str, list[tuple[Task, TaskRelationships]]] = {}
        for task, rels in zip(tasks, rels_list, strict=False):
            # Use relationship data instead of direct field access
            all_knowledge_uids = list(rels.applies_knowledge_uids) + list(
                rels.inferred_knowledge_uids
            )
            for ku_uid in all_knowledge_uids:
                if ku_uid not in knowledge_groups:
                    knowledge_groups[ku_uid] = []
                knowledge_groups[ku_uid].append((task, rels))

        # Analyze each knowledge area for building patterns
        for ku_uid, task_rel_pairs in knowledge_groups.items():
            if len(task_rel_pairs) >= 3:  # Need multiple tasks to detect pattern
                # Sort by date
                def by_created_at(pair: tuple[Task, TaskRelationships]) -> datetime:
                    return pair[0].created_at

                task_rel_pairs.sort(key=by_created_at)

                # Check for progressive complexity
                complexities = [
                    task.calculate_knowledge_complexity() for task, rels in task_rel_pairs
                ]
                if len(complexities) >= 3 and self._is_progressive_sequence(complexities):
                    patterns.append(
                        LearningPattern(
                            pattern_type=LearningPatternType.KNOWLEDGE_BUILDING,
                            knowledge_uids=[ku_uid],
                            task_uids=[task.uid for task, _ in task_rel_pairs],
                            confidence=ConfidenceLevel.STANDARD,
                            timeframe_days=(
                                task_rel_pairs[-1][0].created_at - task_rel_pairs[0][0].created_at
                            ).days,
                            frequency=len(task_rel_pairs),
                            growth_indicator=self._calculate_growth_indicator(complexities),
                            metadata={"complexity_progression": complexities},
                        )
                    )

        return patterns

    async def _detect_cross_domain_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """
        Detect cross-domain knowledge application patterns.

        GRAPH-NATIVE: Fetches relationships from graph for all tasks in parallel.
        """
        patterns = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Find tasks that apply multiple domains (using relationship data)
        cross_domain_tasks: list[tuple[Task, TaskRelationships]] = []
        for task, rels in zip(tasks, rels_list, strict=False):
            all_knowledge_uids = list(rels.applies_knowledge_uids) + list(
                rels.inferred_knowledge_uids
            )
            if len(set(self._extract_domains_from_knowledge_uids(all_knowledge_uids))) >= 2:
                cross_domain_tasks.append((task, rels))

        if len(cross_domain_tasks) >= 2:
            # Group by domain combinations
            domain_combinations: dict[tuple[str, ...], list[tuple[Task, TaskRelationships]]] = {}
            for task, rels in cross_domain_tasks:
                all_knowledge_uids = list(rels.applies_knowledge_uids) + list(
                    rels.inferred_knowledge_uids
                )
                domains = tuple(
                    sorted(set(self._extract_domains_from_knowledge_uids(all_knowledge_uids)))
                )
                if domains not in domain_combinations:
                    domain_combinations[domains] = []
                domain_combinations[domains].append((task, rels))

            # Detect patterns in combinations
            for domains, task_rel_pairs in domain_combinations.items():
                if len(task_rel_pairs) >= 2:
                    combined_knowledge_uids: set[str] = set()
                    for _, rels in task_rel_pairs:
                        combined_knowledge_uids.update(rels.applies_knowledge_uids)
                        combined_knowledge_uids.update(rels.inferred_knowledge_uids)

                    patterns.append(
                        LearningPattern(
                            pattern_type=LearningPatternType.CROSS_DOMAIN_APPLICATION,
                            knowledge_uids=list(combined_knowledge_uids),
                            task_uids=[task.uid for task, _ in task_rel_pairs],
                            confidence=ConfidenceLevel.MEDIUM,
                            timeframe_days=(
                                task_rel_pairs[-1][0].created_at - task_rel_pairs[0][0].created_at
                            ).days,
                            frequency=len(task_rel_pairs),
                            growth_indicator=0.5,  # Neutral growth for cross-domain
                            metadata={"domains": list(domains)},
                        )
                    )

        return patterns

    async def _detect_mastery_validation_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """Detect mastery validation patterns."""
        patterns = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Find tasks that validate knowledge mastery
        validation_task_rels: list[tuple[Task, TaskRelationships]] = [
            (task, rels)
            for task, rels in zip(tasks, rels_list, strict=False)
            if task.knowledge_mastery_check or task.validates_knowledge_mastery()
        ]

        if len(validation_task_rels) >= 2:
            # Group by knowledge areas being validated
            knowledge_validations: dict[str, list[Task]] = {}
            for task, rels in validation_task_rels:
                all_ku_uids = list(rels.applies_knowledge_uids) + list(
                    rels.prerequisite_knowledge_uids
                )
                for ku_uid in all_ku_uids:
                    if ku_uid not in knowledge_validations:
                        knowledge_validations[ku_uid] = []
                    knowledge_validations[ku_uid].append(task)

            for ku_uid, ku_tasks in knowledge_validations.items():
                if len(ku_tasks) >= 2:
                    # Calculate success rate (assume completed tasks are successful)
                    completed_count = sum(1 for t in ku_tasks if t.status == EntityStatus.COMPLETED)
                    success_rate = completed_count / len(ku_tasks) if ku_tasks else 0

                    patterns.append(
                        LearningPattern(
                            pattern_type=LearningPatternType.MASTERY_VALIDATION,
                            knowledge_uids=[ku_uid],
                            task_uids=[t.uid for t in ku_tasks],
                            confidence=ConfidenceLevel.HIGH,
                            timeframe_days=(ku_tasks[-1].created_at - ku_tasks[0].created_at).days,
                            frequency=len(ku_tasks),
                            growth_indicator=success_rate * 2 - 1,  # Convert 0-1 to -1 to 1
                            metadata={"success_rate": success_rate, "validations": len(ku_tasks)},
                        )
                    )

        return patterns

    async def _detect_learning_spiral_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """Detect learning spiral patterns (returning to concepts with increased complexity)."""
        patterns: list[LearningPattern] = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Group tasks by knowledge areas and sort by date
        knowledge_timelines: dict[str, list[tuple[datetime, Task]]] = {}
        for task, rels in zip(tasks, rels_list, strict=False):
            all_ku_uids = list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids)
            for ku_uid in all_ku_uids:
                if ku_uid not in knowledge_timelines:
                    knowledge_timelines[ku_uid] = []
                knowledge_timelines[ku_uid].append((task.created_at, task))

        # Analyze each knowledge area for spiral patterns
        for ku_uid, timeline in knowledge_timelines.items():
            if len(timeline) >= 4:  # Need multiple iterations
                timeline.sort(key=itemgetter(0))  # Sort by date

                # Check for gaps and returns (spiral pattern)
                gaps = self._find_learning_gaps(timeline)
                if len(gaps) >= 1:  # At least one return cycle
                    spiral_tasks = [item[1] for item in timeline]

                    patterns.append(
                        LearningPattern(
                            pattern_type=LearningPatternType.LEARNING_SPIRAL,
                            knowledge_uids=[ku_uid],
                            task_uids=[t.uid for t in spiral_tasks],
                            confidence=ConfidenceLevel.LOW,
                            timeframe_days=(timeline[-1][0] - timeline[0][0]).days,
                            frequency=len(gaps) + 1,  # Number of cycles
                            growth_indicator=0.3,  # Positive for reinforcement
                            metadata={"learning_cycles": len(gaps) + 1, "gaps_days": gaps},
                        )
                    )

        return patterns

    async def _detect_skill_specialization_patterns(
        self, tasks: list[Task]
    ) -> list[LearningPattern]:
        """Detect skill specialization patterns (deep focus on specific areas)."""
        patterns: list[LearningPattern] = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Count task frequency per knowledge area
        knowledge_counts: dict[str, int] = {}
        for _, rels in zip(tasks, rels_list, strict=False):
            all_ku_uids = list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids)
            for ku_uid in all_ku_uids:
                knowledge_counts[ku_uid] = knowledge_counts.get(ku_uid, 0) + 1

        # Find knowledge areas with high frequency (specialization)
        total_tasks = len(tasks)
        for ku_uid, count in knowledge_counts.items():
            specialization_ratio = count / total_tasks if total_tasks > 0 else 0

            if (
                specialization_ratio >= 0.3 and count >= 3
            ):  # At least 30% of tasks and minimum 3 tasks
                specialized_task_rels: list[tuple[Task, TaskRelationships]] = [
                    (task, rels)
                    for task, rels in zip(tasks, rels_list, strict=False)
                    if ku_uid
                    in (list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids))
                ]
                specialized_tasks = [task for task, _ in specialized_task_rels]

                patterns.append(
                    LearningPattern(
                        pattern_type=LearningPatternType.SKILL_SPECIALIZATION,
                        knowledge_uids=[ku_uid],
                        task_uids=[t.uid for t in specialized_tasks],
                        confidence=min(
                            0.9, specialization_ratio * 2
                        ),  # Higher ratio = higher confidence
                        timeframe_days=(
                            specialized_tasks[-1].created_at - specialized_tasks[0].created_at
                        ).days,
                        frequency=count,
                        growth_indicator=0.7,  # Specialization is generally positive
                        metadata={
                            "specialization_ratio": specialization_ratio,
                            "focus_intensity": count,
                        },
                    )
                )

        return patterns

    async def _detect_knowledge_bridging_patterns(self, tasks: list[Task]) -> list[LearningPattern]:
        """Detect knowledge bridging patterns (connecting different knowledge areas)."""
        patterns = []

        if not tasks or not self.relationship_service:
            return patterns

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Find tasks that bridge knowledge (have prerequisites and applications)
        bridging_task_rels: list[tuple[Task, TaskRelationships]] = [
            (task, rels)
            for task, rels in zip(tasks, rels_list, strict=False)
            if (
                rels.prerequisite_knowledge_uids
                and rels.applies_knowledge_uids
                and task.is_knowledge_bridge()
            )
        ]

        if len(bridging_task_rels) >= 2:
            # Group by bridge combinations
            bridge_combinations: dict[tuple[frozenset[str], frozenset[str]], list[Task]] = {}
            for task, rels in bridging_task_rels:
                prereq_set = frozenset(rels.prerequisite_knowledge_uids)
                applies_set = frozenset(rels.applies_knowledge_uids)
                bridge_key = (prereq_set, applies_set)

                if bridge_key not in bridge_combinations:
                    bridge_combinations[bridge_key] = []
                bridge_combinations[bridge_key].append(task)

            for (prereqs, applies), bridge_tasks in bridge_combinations.items():
                if len(bridge_tasks) >= 2:
                    all_knowledge_uids = list(prereqs.union(applies))

                    patterns.append(
                        LearningPattern(
                            pattern_type=LearningPatternType.KNOWLEDGE_BRIDGING,
                            knowledge_uids=all_knowledge_uids,
                            task_uids=[t.uid for t in bridge_tasks],
                            confidence=ConfidenceLevel.STANDARD,
                            timeframe_days=(
                                bridge_tasks[-1].created_at - bridge_tasks[0].created_at
                            ).days,
                            frequency=len(bridge_tasks),
                            growth_indicator=0.6,  # Bridging is positive for learning
                            metadata={
                                "prerequisite_knowledge": list(prereqs),
                                "applied_knowledge": list(applies),
                            },
                        )
                    )

        return patterns

    def _is_progressive_sequence(self, values: list[float]) -> bool:
        """Check if a sequence shows progressive increase."""
        if len(values) < 3:
            return False

        increases = sum(1 for i in range(1, len(values)) if values[i] > values[i - 1])
        return increases >= len(values) * 0.6  # At least 60% increases

    def _calculate_growth_indicator(self, values: list[float]) -> float:
        """Calculate growth indicator from -1 to 1."""
        if len(values) < 2:
            return 0.0

        first_half = values[: len(values) // 2]
        second_half = values[len(values) // 2 :]

        if not first_half or not second_half:
            return 0.0

        first_avg = statistics.mean(first_half)
        second_avg = statistics.mean(second_half)

        if first_avg == 0:
            return 1.0 if second_avg > 0 else 0.0

        growth_rate = (second_avg - first_avg) / first_avg
        return max(-1.0, min(1.0, growth_rate))  # Clamp to [-1, 1]

    def _extract_domains_from_knowledge_uids(self, knowledge_uids: list[str]) -> list[str]:
        """Extract domain names from knowledge UIDs."""
        domains = []
        for ku_uid in knowledge_uids:
            # Extract domain from ku.domain.specific format
            parts = ku_uid.split(".")
            if len(parts) >= 2 and parts[0] in (EntityType.ARTICLE.value, EntityType.KU.value, "a"):  # UID prefix, not Neo4j label
                domains.append(parts[1])
        return domains

    def _find_learning_gaps(self, timeline: list[tuple[datetime, Task]]) -> list[int]:
        """Find gaps in learning timeline (for spiral detection)."""
        gaps = []
        for i in range(1, len(timeline)):
            gap_days = (timeline[i][0] - timeline[i - 1][0]).days
            if gap_days > 7:  # Gap of more than a week
                gaps.append(gap_days)
        return gaps

    def _calculate_base_priority_score(self, task: Task) -> float:
        """Calculate base priority score from task priority."""
        priority_map = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8, "CRITICAL": 1.0}
        return priority_map.get(task.priority.upper() if task.priority else "MEDIUM", 0.5)

    async def _calculate_knowledge_enhancement_score(
        self, task: Task, rels: TaskRelationships, progressions: dict[str, MasteryProgression]
    ) -> float:
        """Calculate knowledge enhancement potential score."""
        if not rels.applies_knowledge_uids:
            return 0.1

        enhancement_scores = []
        for ku_uid in rels.applies_knowledge_uids:
            if ku_uid in progressions:
                # Higher score for knowledge areas with room for growth
                mastery_level = progressions[ku_uid].current_mastery_level
                enhancement_potential = 1.0 - mastery_level
                enhancement_scores.append(enhancement_potential)
            else:
                # New knowledge area has high enhancement potential
                enhancement_scores.append(0.8)

        base_score = statistics.mean(enhancement_scores) if enhancement_scores else 0.5

        # Boost score for high-priority tasks (priority indicates importance of knowledge gain)
        priority_boost = 0.0
        if task.priority == "critical":
            priority_boost = 0.2
        elif task.priority == "high":
            priority_boost = 0.1

        return min(1.0, base_score + priority_boost)

    async def _calculate_learning_opportunity_score(
        self, task: Task, rels: TaskRelationships, patterns: list[LearningPattern]
    ) -> float:
        """Calculate learning opportunity score based on patterns."""
        base_score = task.learning_opportunities_count / 10.0  # Normalize to 0-1

        # Boost score if task aligns with detected learning patterns
        pattern_boost = 0.0
        all_knowledge_uids = list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids)
        task_knowledge = set(all_knowledge_uids)

        for pattern in patterns:
            pattern_knowledge = set(pattern.knowledge_uids)
            overlap = task_knowledge.intersection(pattern_knowledge)
            if overlap:
                pattern_boost += 0.1 * len(overlap) * pattern.confidence

        return min(1.0, base_score + pattern_boost)

    async def _calculate_mastery_progression_score(
        self, task: Task, rels: TaskRelationships, progressions: dict[str, MasteryProgression]
    ) -> float:
        """Calculate mastery progression impact score."""
        if not (rels.applies_knowledge_uids or rels.prerequisite_knowledge_uids):
            return 0.1

        progression_scores = []
        all_knowledge = list(rels.applies_knowledge_uids) + list(rels.prerequisite_knowledge_uids)

        for ku_uid in all_knowledge:
            if ku_uid in progressions:
                progression = progressions[ku_uid]
                # Higher score for knowledge with positive velocity and room for growth
                velocity_factor = max(0, progression.progression_velocity)
                mastery_factor = 1.0 - progression.current_mastery_level
                score = velocity_factor * 0.6 + mastery_factor * 0.4
                progression_scores.append(score)
            else:
                # New knowledge area has medium progression potential
                progression_scores.append(0.6)

        base_score = statistics.mean(progression_scores) if progression_scores else 0.3

        # Boost score for tasks nearing deadline (urgency increases mastery value)
        urgency_boost = 0.0
        if task.due_date:
            days_until_due = (task.due_date - date.today()).days
            if days_until_due <= 3:
                urgency_boost = 0.15  # Very urgent
            elif days_until_due <= 7:
                urgency_boost = 0.10  # Urgent

        return min(1.0, base_score + urgency_boost)

    async def _calculate_cross_domain_impact_score(
        self, task: Task, rels: TaskRelationships, patterns: list[LearningPattern]
    ) -> float:
        """Calculate cross-domain impact potential score."""
        all_knowledge_uids = list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids)
        task_domains = set(self._extract_domains_from_knowledge_uids(all_knowledge_uids))

        if len(task_domains) <= 1:
            return 0.2  # Low cross-domain impact

        # Check alignment with cross-domain patterns
        cross_domain_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.CROSS_DOMAIN_APPLICATION
        ]

        alignment_score = 0.0
        for pattern in cross_domain_patterns:
            pattern_domains = set(self._extract_domains_from_knowledge_uids(pattern.knowledge_uids))
            overlap = task_domains.intersection(pattern_domains)
            if overlap:
                alignment_score += 0.2 * len(overlap) * pattern.confidence

        base_score = min(0.8, len(task_domains) * 0.2)  # More domains = higher score

        # Boost score for high-priority cross-domain tasks (strategic importance)
        priority_boost = 0.0
        if task.priority in ["high", "critical"]:
            priority_boost = 0.15  # Cross-domain learning in important tasks

        # Boost for tasks tagged with cross-domain indicators
        tag_boost = 0.0
        cross_domain_tags = {"integration", "synthesis", "multidisciplinary", "interdisciplinary"}
        if any(tag in cross_domain_tags for tag in task.tags):
            tag_boost = 0.1

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
        """Generate human-readable rationale for priority scoring."""
        rationale = []

        if base > 0.7:
            rationale.append(f"High base priority ({task.priority}) increases importance")
        elif base < 0.3:
            rationale.append(f"Low base priority ({task.priority}) reduces urgency")

        if knowledge > 0.7:
            rationale.append("Strong knowledge enhancement potential detected")

        if learning > 0.7:
            rationale.append("High learning opportunity value identified")

        if mastery > 0.7:
            rationale.append("Significant mastery progression impact expected")

        if cross_domain > 0.7:
            rationale.append("Notable cross-domain knowledge application potential")

        if not rationale:
            rationale.append("Standard priority scoring applied")

        return rationale

    async def _calculate_mastery_progression(
        self, knowledge_uid: str, tasks: list[Task]
    ) -> MasteryProgression:
        """Calculate mastery progression for a knowledge area."""
        completed_tasks = [t for t in tasks if t.status == EntityStatus.COMPLETED]
        validation_tasks = [t for t in completed_tasks if t.knowledge_mastery_check]

        # GRAPH-NATIVE: Fetch relationships for completed tasks only (optimization)
        if completed_tasks and self.relationship_service:
            completed_rels = await asyncio.gather(
                *[
                    TaskRelationships.fetch(task.uid, self.relationship_service)
                    for task in completed_tasks
                ]
            )
        else:
            # No completed tasks or no service - use empty relationships
            completed_rels = [TaskRelationships.empty() for _ in completed_tasks]

        # Calculate current mastery level based on task complexity and success
        if completed_tasks:
            complexities = [
                task.calculate_knowledge_complexity()
                for task, rels in zip(completed_tasks, completed_rels, strict=False)
            ]
            avg_complexity = statistics.mean(complexities)
            completion_rate = len(completed_tasks) / len(tasks)
            current_mastery = min(1.0, avg_complexity * completion_rate * 1.2)
        else:
            current_mastery = 0.0

        # Calculate trend from recent vs older tasks
        if len(completed_tasks) >= 4:
            mid_point = len(completed_tasks) // 2
            recent_half_tasks = completed_tasks[mid_point:]
            older_half_tasks = completed_tasks[:mid_point]
            recent_half_rels = completed_rels[mid_point:]
            older_half_rels = completed_rels[:mid_point]

            recent_avg = statistics.mean(
                [
                    t.calculate_knowledge_complexity()
                    for t, rels in zip(recent_half_tasks, recent_half_rels, strict=False)
                ]
            )
            older_avg = statistics.mean(
                [
                    t.calculate_knowledge_complexity()
                    for t, rels in zip(older_half_tasks, older_half_rels, strict=False)
                ]
            )

            trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0.0
        else:
            trend = 0.0

        # Calculate progression velocity
        if len(completed_tasks) >= 2:
            timespan = (completed_tasks[-1].created_at - completed_tasks[0].created_at).days
            velocity = current_mastery / max(1, timespan) if timespan > 0 else 0.0
        else:
            velocity = 0.0

        # Last application date
        last_date = completed_tasks[-1].created_at.date() if completed_tasks else None

        # Confidence in assessment
        confidence = min(1.0, len(completed_tasks) / 10.0)  # More tasks = higher confidence

        # Next recommended difficulty
        next_difficulty = min(1.0, current_mastery + 0.2) if current_mastery > 0 else 0.3

        return MasteryProgression(
            knowledge_uid=knowledge_uid,
            current_mastery_level=current_mastery,
            mastery_trend=max(-1.0, min(1.0, trend)),
            tasks_completed=len(completed_tasks),
            validation_tasks_passed=len(validation_tasks),
            last_application_date=last_date,
            progression_velocity=velocity,
            confidence_in_assessment=confidence,
            next_recommended_difficulty=next_difficulty,
        )

    async def _generate_knowledge_area_insights(self, tasks: list[Task]) -> list[TaskInsight]:
        """Generate insights about knowledge area usage patterns."""
        insights = []

        if not tasks or not self.relationship_service:
            return insights

        # GRAPH-NATIVE: Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationship_service) for task in tasks]
        )

        # Analyze knowledge area frequency
        knowledge_usage = {}
        for task, rels in zip(tasks, rels_list, strict=False):
            all_ku_uids = list(rels.applies_knowledge_uids) + list(rels.inferred_knowledge_uids)
            for ku_uid in all_ku_uids:
                if ku_uid not in knowledge_usage:
                    knowledge_usage[ku_uid] = {"count": 0, "complexity_sum": 0.0}
                knowledge_usage[ku_uid]["count"] += 1
                knowledge_usage[ku_uid]["complexity_sum"] += task.calculate_knowledge_complexity()

        # Find most and least used knowledge areas
        if knowledge_usage:

            def _usage_count_key(item) -> Any:
                return item[1]["count"]

            sorted_usage = sorted(knowledge_usage.items(), key=_usage_count_key, reverse=True)

            # Most used knowledge area insight
            top_ku, top_data = sorted_usage[0]
            avg_complexity = top_data["complexity_sum"] / top_data["count"]

            insights.append(
                TaskInsight(
                    insight_type="knowledge_focus",
                    title=f"Primary Knowledge Focus: {top_ku}",
                    description=f"You've applied {top_ku} in {top_data['count']} tasks with average complexity {avg_complexity:.2f}",
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

            # Underutilized knowledge area if there's variation
            if len(sorted_usage) > 3:
                bottom_ku, bottom_data = sorted_usage[-1]
                insights.append(
                    TaskInsight(
                        insight_type="knowledge_gap",
                        title=f"Underutilized Knowledge: {bottom_ku}",
                        description=f"Limited application of {bottom_ku} - only {bottom_data['count']} tasks",
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

    async def _generate_learning_velocity_insights(
        self, _tasks: list[Task], patterns: list[LearningPattern]
    ) -> list[TaskInsight]:
        """Generate insights about learning velocity and patterns."""
        insights = []

        # Analyze learning velocity from knowledge building patterns
        building_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.KNOWLEDGE_BUILDING
        ]

        if building_patterns:
            avg_growth = statistics.mean([p.growth_indicator for p in building_patterns])

            if avg_growth > 0.5:
                insights.append(
                    TaskInsight(
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
            elif avg_growth < -0.2:
                insights.append(
                    TaskInsight(
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

    async def _generate_application_effectiveness_insights(
        self, tasks: list[Task]
    ) -> list[TaskInsight]:
        """Generate insights about knowledge application effectiveness."""
        insights = []

        if not tasks or not self.relationship_service:
            return insights

        # Analyze completion rates by knowledge complexity
        completed_tasks = [t for t in tasks if t.status == EntityStatus.COMPLETED]
        if len(completed_tasks) >= 5:
            # GRAPH-NATIVE: Fetch relationships for completed tasks only
            completed_rels = await asyncio.gather(
                *[
                    TaskRelationships.fetch(task.uid, self.relationship_service)
                    for task in completed_tasks
                ]
            )

            complexities = [
                t.calculate_knowledge_complexity()
                for t, rels in zip(completed_tasks, completed_rels, strict=False)
            ]
            completion_rate = len(completed_tasks) / len(tasks)
            avg_complexity = statistics.mean(complexities)

            if completion_rate > 0.8 and avg_complexity > 0.6:
                insights.append(
                    TaskInsight(
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

    async def _generate_mastery_validation_insights(self, tasks: list[Task]) -> list[TaskInsight]:
        """Generate insights about mastery validation patterns."""
        insights = []

        validation_tasks = [t for t in tasks if t.knowledge_mastery_check]
        completed_validations = [t for t in validation_tasks if t.status == EntityStatus.COMPLETED]

        if validation_tasks:
            validation_rate = len(completed_validations) / len(validation_tasks)

            if validation_rate > 0.8:
                insights.append(
                    TaskInsight(
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
            elif validation_rate < 0.5:
                insights.append(
                    TaskInsight(
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

    async def _generate_cross_domain_insights(
        self, _tasks: list[Task], patterns: list[LearningPattern]
    ) -> list[TaskInsight]:
        """Generate insights about cross-domain knowledge connections."""
        insights = []

        cross_domain_patterns = [
            p for p in patterns if p.pattern_type == LearningPatternType.CROSS_DOMAIN_APPLICATION
        ]

        if cross_domain_patterns:
            total_domains = set()
            for pattern in cross_domain_patterns:
                domains = self._extract_domains_from_knowledge_uids(pattern.knowledge_uids)
                total_domains.update(domains)

            insights.append(
                TaskInsight(
                    insight_type="cross_domain_integration",
                    title="Cross-Domain Knowledge Integration",
                    description=f"Successfully integrating knowledge across {len(total_domains)} domains",
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
