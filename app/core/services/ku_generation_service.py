"""
Knowledge Generation Service (Phase 4.1)
==========================================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY TasksService for task-to-knowledge conversion, not a duplicate.

AI-powered automatic knowledge extraction from completed tasks with:
- Pattern recognition for best practices and anti-patterns
- Insight generation from successful task completion patterns
- Knowledge quality scoring and curation
- Automatic knowledge unit creation from task insights

Integrates with existing knowledge infrastructure while adding
advanced generative capabilities for task-based learning.

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into TasksService for automatic knowledge creation
- Specialized utility for AI-powered knowledge generation
- See `/core/services/ku/README.md` for architecture overview
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from operator import attrgetter
from typing import Any

from core.models.enums import ActivityStatus, Domain, Priority
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku import Ku as Task
from core.services.protocols import HasMetadata, HasSummary
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator


class PatternType(str, Enum):
    """Types of patterns that can be extracted from task completion."""

    BEST_PRACTICE = "best_practice"
    ANTI_PATTERN = "anti_pattern"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    TIME_MANAGEMENT = "time_management"
    SKILL_PROGRESSION = "skill_progression"
    KNOWLEDGE_APPLICATION = "knowledge_application"
    PROBLEM_SOLVING = "problem_solving"


class InsightCategory(str, Enum):
    """Categories of insights generated from task patterns."""

    EFFICIENCY = "efficiency"
    QUALITY = "quality"
    LEARNING = "learning"
    PROCESS = "process"
    STRATEGIC = "strategic"


@dataclass
class TaskPattern:
    """A detected pattern from task completion analysis."""

    pattern_id: str
    pattern_type: PatternType
    confidence_score: float
    supporting_tasks: list[str]
    description: str
    evidence: list[str]
    frequency: int
    success_rate: float
    time_saved_minutes: int | None = None
    quality_impact: float | None = None
    knowledge_uids_involved: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedInsight:
    """An insight generated from task completion patterns."""

    insight_id: str
    category: InsightCategory
    title: str
    description: str
    actionable_recommendation: str
    supporting_patterns: list[str]
    confidence_score: float
    impact_score: float
    generated_at: datetime
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KuQualityMetrics:
    """Quality metrics for generated knowledge."""

    completeness_score: float  # 0-1
    accuracy_score: float  # 0-1
    relevance_score: float  # 0-1
    timeliness_score: float  # 0-1
    actionability_score: float  # 0-1
    evidence_strength: float  # 0-1
    overall_quality: float  # computed weighted average

    def compute_overall_quality(self) -> float:
        """Compute weighted overall quality score."""
        weights = {
            "completeness": 0.2,
            "accuracy": 0.25,
            "relevance": 0.2,
            "timeliness": 0.1,
            "actionability": 0.15,
            "evidence_strength": 0.1,
        }

        self.overall_quality = (
            self.completeness_score * weights["completeness"]
            + self.accuracy_score * weights["accuracy"]
            + self.relevance_score * weights["relevance"]
            + self.timeliness_score * weights["timeliness"]
            + self.actionability_score * weights["actionability"]
            + self.evidence_strength * weights["evidence_strength"]
        )
        return self.overall_quality


class KuGenerationService:
    """
    Service for automatic knowledge generation from completed tasks.

    Core capabilities:
    1. Analyze completed task patterns to extract knowledge
    2. Recognize best practices and anti-patterns
    3. Generate actionable insights from successful completion patterns
    4. Score and curate generated knowledge for quality


    Source Tag: "ku_generation_service_explicit"
    - Format: "ku_generation_service_explicit" for user-created relationships
    - Format: "ku_generation_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from ku_generation metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, ku_service=None, tasks_service=None, analytics_engine=None) -> None:
        """
        Initialize the knowledge generation service.

        Args:
            ku_service: For creating new knowledge units,
            tasks_service: For accessing task completion data,
            analytics_engine: For advanced pattern analysis
        """
        self.ku_service = ku_service
        self.tasks_service = tasks_service
        self.analytics_engine = analytics_engine
        self.logger = get_logger("skuel.knowledge.generation")

        # Pattern detection thresholds
        self.min_pattern_frequency = 3
        self.min_confidence_score = 0.7
        self.min_success_rate = 0.8

        # Knowledge quality thresholds
        self.min_quality_score = 0.6
        self.auto_publish_threshold = 0.8

        # Cache for pattern analysis
        self._pattern_cache: dict[str, list[TaskPattern]] = {}
        self._cache_ttl = 3600  # 1 hour
        self._cache_timestamps: dict[str, datetime] = {}

    # ========================================================================
    # AUTOMATIC KNOWLEDGE EXTRACTION FROM COMPLETED TASKS
    # ========================================================================

    @with_error_handling("extract_knowledge_from_completed_tasks", error_type="system")
    async def extract_knowledge_from_completed_tasks(
        self, user_uid: str, days_back: int = 30, min_tasks: int = 5
    ) -> Result[list[KuDTO]]:
        """
        Extract knowledge from user's completed tasks over a time period.

        Args:
            user_uid: User to analyze tasks for,
            days_back: How many days back to analyze,
            min_tasks: Minimum completed tasks needed for analysis

        Returns:
            Result containing list of generated KuDTO objects
        """
        # Get completed tasks for analysis
        since_date = datetime.now() - timedelta(days=days_back)
        completed_tasks = await self._get_completed_tasks_since(user_uid, since_date)

        if len(completed_tasks) < min_tasks:
            return Result.ok([])  # Not enough data for meaningful analysis

        # Analyze patterns in completed tasks
        patterns_result = await self.analyze_task_completion_patterns(completed_tasks)
        if patterns_result.is_error:
            return Result.fail(patterns_result.expect_error())

        patterns = patterns_result.value

        # Generate insights from patterns
        insights_result = await self.generate_insights_from_patterns(patterns)
        if insights_result.is_error:
            return Result.fail(insights_result.expect_error())

        insights = insights_result.value

        # Convert high-quality insights to knowledge units
        knowledge_units = []
        for insight in insights:
            if insight.confidence_score >= self.min_confidence_score:
                knowledge_dto = await self._convert_insight_to_knowledge(insight, user_uid)
                if knowledge_dto:
                    knowledge_units.append(knowledge_dto)

        self.logger.info(
            f"Generated {len(knowledge_units)} knowledge units from {len(completed_tasks)} "
            f"completed tasks for user {user_uid}"
        )

        return Result.ok(knowledge_units)

    async def _get_completed_tasks_since(self, user_uid: str, since_date: datetime) -> list[Task]:
        """Get completed tasks for a user since a specific date."""
        if not self.tasks_service:
            return []

        try:
            user_tasks_result = await self.tasks_service.get_user_tasks(user_uid)
            if user_tasks_result.is_error:
                return []

            return [
                task
                for task in user_tasks_result.value
                if (
                    task.status == ActivityStatus.COMPLETED
                    and task.completion_date
                    and datetime.combine(task.completion_date, datetime.min.time()) >= since_date
                )
            ]

        except Exception as e:
            self.logger.warning(f"Failed to get completed tasks: {e}")
            return []

    # ========================================================================
    # PATTERN RECOGNITION FOR BEST PRACTICES AND ANTI-PATTERNS
    # ========================================================================

    @with_error_handling("analyze_task_completion_patterns", error_type="system")
    async def analyze_task_completion_patterns(
        self, completed_tasks: list[Task]
    ) -> Result[list[TaskPattern]]:
        """
        Analyze completed tasks to identify patterns, best practices, and anti-patterns.

        Args:
            completed_tasks: List of completed Task objects to analyze

        Returns:
            Result containing detected TaskPattern objects
        """
        if not completed_tasks:
            return Result.ok([])

        patterns = []

        # Group tasks by various dimensions for pattern analysis
        patterns.extend(await self._analyze_time_patterns(completed_tasks))
        patterns.extend(await self._analyze_priority_patterns(completed_tasks))
        patterns.extend(await self._analyze_project_patterns(completed_tasks))
        patterns.extend(await self._analyze_knowledge_application_patterns(completed_tasks))
        patterns.extend(await self._analyze_workflow_patterns(completed_tasks))

        # Filter patterns by confidence and frequency
        high_quality_patterns = [
            p
            for p in patterns
            if (
                p.confidence_score >= self.min_confidence_score
                and p.frequency >= self.min_pattern_frequency
            )
        ]

        self.logger.info(
            f"Detected {len(high_quality_patterns)} high-quality patterns "
            f"from {len(completed_tasks)} completed tasks"
        )

        return Result.ok(high_quality_patterns)

    async def _analyze_time_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
        """Analyze time-related patterns in task completion."""
        patterns = []

        # Pattern: Consistent estimation accuracy
        estimation_accuracy = []
        for task in tasks:
            if task.actual_minutes and task.duration_minutes:
                accuracy = min(task.actual_minutes, task.duration_minutes) / max(
                    task.actual_minutes, task.duration_minutes
                )
                estimation_accuracy.append((task.uid, accuracy))

        if estimation_accuracy:
            avg_accuracy = sum(acc for _, acc in estimation_accuracy) / len(estimation_accuracy)
            if avg_accuracy >= 0.8:  # 80% accuracy threshold
                patterns.append(
                    TaskPattern(
                        pattern_id=f"time_estimation_accuracy_{datetime.now().strftime('%Y%m%d')}",
                        pattern_type=PatternType.BEST_PRACTICE,
                        confidence_score=avg_accuracy,
                        supporting_tasks=[uid for uid, _ in estimation_accuracy],
                        description="Consistently accurate time estimation for tasks",
                        evidence=[f"Average estimation accuracy: {avg_accuracy:.1%}"],
                        frequency=len(estimation_accuracy),
                        success_rate=avg_accuracy,
                        metadata={"avg_accuracy": avg_accuracy, "type": "time_estimation"},
                    )
                )

        # Pattern: Efficient task completion (finishing early)
        early_completions = [
            task
            for task in tasks
            if (
                task.actual_minutes
                and task.duration_minutes
                and task.actual_minutes < task.duration_minutes * 0.9
            )
        ]

        if len(early_completions) >= self.min_pattern_frequency:
            # Type-safe: both values guaranteed non-None by filter above
            avg_time_saved = sum(
                (task.duration_minutes or 0) - (task.actual_minutes or 0)
                for task in early_completions
            ) / len(early_completions)

            patterns.append(
                TaskPattern(
                    pattern_id=f"early_completion_{datetime.now().strftime('%Y%m%d')}",
                    pattern_type=PatternType.WORKFLOW_OPTIMIZATION,
                    confidence_score=len(early_completions) / len(tasks),
                    supporting_tasks=[task.uid for task in early_completions],
                    description="Consistently finishing tasks ahead of estimated time",
                    evidence=[f"Average time saved: {avg_time_saved:.1f} minutes"],
                    frequency=len(early_completions),
                    success_rate=1.0,
                    time_saved_minutes=int(avg_time_saved),
                    metadata={"early_completion_rate": len(early_completions) / len(tasks)},
                )
            )

        return patterns

    async def _analyze_priority_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
        """Analyze priority-related patterns."""
        patterns = []

        # Group by priority
        priority_groups = defaultdict(list)
        for task in tasks:
            priority_groups[task.priority].append(task)

        # Pattern: High priority task completion efficiency
        if Priority.HIGH in priority_groups:
            high_priority_tasks = priority_groups[Priority.HIGH]
            success_rate = len(high_priority_tasks) / len(tasks)

            if success_rate >= 0.8 and len(high_priority_tasks) >= self.min_pattern_frequency:
                patterns.append(
                    TaskPattern(
                        pattern_id=f"high_priority_efficiency_{datetime.now().strftime('%Y%m%d')}",
                        pattern_type=PatternType.BEST_PRACTICE,
                        confidence_score=success_rate,
                        supporting_tasks=[task.uid for task in high_priority_tasks],
                        description="Excellent handling of high-priority tasks",
                        evidence=[f"High priority completion rate: {success_rate:.1%}"],
                        frequency=len(high_priority_tasks),
                        success_rate=success_rate,
                        metadata={"priority_focus": True},
                    )
                )

        return patterns

    async def _analyze_project_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
        """Analyze project-related patterns."""
        patterns = []

        # Group by project
        project_groups = defaultdict(list)
        for task in tasks:
            if task.project:
                project_groups[task.project].append(task)

        # Pattern: Project completion consistency
        for project, project_tasks in project_groups.items():
            if len(project_tasks) >= self.min_pattern_frequency:
                # Calculate average completion metrics for this project
                avg_efficiency = self._calculate_task_efficiency(project_tasks)

                if avg_efficiency >= 0.85:
                    patterns.append(
                        TaskPattern(
                            pattern_id=f"project_efficiency_{project}_{datetime.now().strftime('%Y%m%d')}",
                            pattern_type=PatternType.WORKFLOW_OPTIMIZATION,
                            confidence_score=avg_efficiency,
                            supporting_tasks=[task.uid for task in project_tasks],
                            description=f"High efficiency in {project} project tasks",
                            evidence=[f"Project efficiency: {avg_efficiency:.1%}"],
                            frequency=len(project_tasks),
                            success_rate=avg_efficiency,
                            metadata={"project": project, "efficiency": avg_efficiency},
                        )
                    )

        return patterns

    async def _analyze_knowledge_application_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
        """
        Analyze patterns in knowledge application efficiency.

        DEFERRED IMPLEMENTATION (Graph-Native):
        ==================================
        Parameter accepted but unused pending TasksRelationshipService wiring.

        Why Deferred:
        - Service already detects 4 other pattern types (time, priority, project, workflow)
        - This is 1 of 5 pattern detection methods - not critical path
        - Wiring TasksRelationshipService requires bootstrap changes
        - Better ROI focusing on other refactorings first

        Future Implementation (High Value):
        1. Wire TasksRelationshipService into this service's __init__
        2. Fetch TaskRelationships for each task (parallel with asyncio.gather)
        3. Filter tasks where rels.applies_knowledge_uids is not empty
        4. Calculate efficiency: knowledge-tasks vs. all tasks
        5. Detect pattern: "Tasks with applied knowledge show 10%+ higher efficiency"

        Args:
            tasks: User tasks (currently unused - see deferral note above)

        Returns:
            Empty list (graceful degradation - other pattern types still detected)
        """
        # DEFERRED: Knowledge application pattern analysis
        # For now, return empty - other pattern detection methods still functional

        # Original logic commented out until relationship fetching is implemented:
        # knowledge_tasks = [
        #     task for task in tasks
        #     if task.applies_knowledge_uids  # Field doesn't exist anymore
        # ]
        #
        # if len(knowledge_tasks) >= self.min_pattern_frequency:
        #     knowledge_efficiency = self._calculate_task_efficiency(knowledge_tasks)
        #     overall_efficiency = self._calculate_task_efficiency(tasks)
        #
        #     if knowledge_efficiency > overall_efficiency * 1.1:
        #         patterns.append(TaskPattern(
        #             pattern_id=f"knowledge_application_benefit_{datetime.now().strftime('%Y%m%d')}",
        #             pattern_type=PatternType.BEST_PRACTICE,
        #             confidence_score=knowledge_efficiency / overall_efficiency,
        #             supporting_tasks=[task.uid for task in knowledge_tasks],
        #             description="Tasks with applied knowledge show higher efficiency",
        #             evidence=[
        #                 f"Knowledge tasks efficiency: {knowledge_efficiency:.1%}",
        #                 f"Overall efficiency: {overall_efficiency:.1%}",
        #                 f"Improvement: {(knowledge_efficiency/overall_efficiency - 1):.1%}"
        #             ],
        #             frequency=len(knowledge_tasks),
        #             success_rate=knowledge_efficiency,
        #             knowledge_uids_involved=list(set().union(*[task.applies_knowledge_uids for task in knowledge_tasks])),
        #             metadata={'knowledge_benefit': knowledge_efficiency / overall_efficiency}
        #         ))

        return []

    async def _analyze_workflow_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
        """Analyze workflow and process patterns."""
        patterns = []

        # Pattern: Tag-based organization effectiveness
        tag_groups = defaultdict(list)
        for task in tasks:
            for tag in task.tags:
                tag_groups[tag].append(task)

        # Find tags associated with high-efficiency tasks
        for tag, tagged_tasks in tag_groups.items():
            if len(tagged_tasks) >= self.min_pattern_frequency:
                tag_efficiency = self._calculate_task_efficiency(tagged_tasks)

                if tag_efficiency >= 0.9:
                    patterns.append(
                        TaskPattern(
                            pattern_id=f"tag_efficiency_{tag}_{datetime.now().strftime('%Y%m%d')}",
                            pattern_type=PatternType.WORKFLOW_OPTIMIZATION,
                            confidence_score=tag_efficiency,
                            supporting_tasks=[task.uid for task in tagged_tasks],
                            description=f"High efficiency with '{tag}' tagged tasks",
                            evidence=[f"Tag '{tag}' efficiency: {tag_efficiency:.1%}"],
                            frequency=len(tagged_tasks),
                            success_rate=tag_efficiency,
                            metadata={"tag": tag, "efficiency": tag_efficiency},
                        )
                    )

        return patterns

    def _calculate_task_efficiency(self, tasks: list[Task]) -> float:
        """Calculate overall efficiency score for a group of tasks."""
        if not tasks:
            return 0.0

        efficiency_scores = []

        for task in tasks:
            # Factor 1: Time efficiency (actual vs estimated)
            time_efficiency = 1.0
            if task.actual_minutes and task.duration_minutes:
                if task.actual_minutes <= task.duration_minutes:
                    time_efficiency = 1.0
                else:
                    time_efficiency = task.duration_minutes / task.actual_minutes

            # Factor 2: Completion (all tasks in this list are completed, so 1.0)
            completion_score = 1.0

            # Factor 3: Priority handling (high priority gets bonus)
            priority_bonus = 1.0
            if task.priority == Priority.HIGH:
                priority_bonus = 1.1
            elif task.priority == Priority.LOW:
                priority_bonus = 0.95

            efficiency_scores.append(time_efficiency * completion_score * priority_bonus)

        return sum(efficiency_scores) / len(efficiency_scores)

    # ========================================================================
    # INSIGHT GENERATION FROM SUCCESSFUL TASK COMPLETION PATTERNS
    # ========================================================================

    @with_error_handling("generate_insights_from_patterns", error_type="system")
    async def generate_insights_from_patterns(
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
            type_insights = await self._generate_insights_for_pattern_type(
                pattern_type, type_patterns
            )
            insights.extend(type_insights)

        # Generate cross-pattern insights
        cross_insights = await self._generate_cross_pattern_insights(patterns)
        insights.extend(cross_insights)

        # Score and rank insights
        scored_insights = await self._score_insights(insights)

        self.logger.info(f"Generated {len(scored_insights)} insights from {len(patterns)} patterns")

        return Result.ok(scored_insights)

    async def _generate_insights_for_pattern_type(
        self, pattern_type: PatternType, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights for a specific pattern type."""
        insights = []

        if pattern_type == PatternType.BEST_PRACTICE:
            insights.extend(self._generate_best_practice_insights(patterns))
        elif pattern_type == PatternType.WORKFLOW_OPTIMIZATION:
            insights.extend(self._generate_workflow_insights(patterns))
        elif pattern_type == PatternType.TIME_MANAGEMENT:
            insights.extend(self._generate_time_management_insights(patterns))

        return insights

    def _generate_best_practice_insights(
        self, patterns: list[TaskPattern]
    ) -> list[GeneratedInsight]:
        """Generate insights from best practice patterns."""
        insights = []

        for pattern in patterns:
            if "knowledge_application" in pattern.pattern_id:
                insights.append(
                    GeneratedInsight(
                        insight_id=f"insight_knowledge_application_{datetime.now().strftime('%Y%m%d_%H%M')}",
                        category=InsightCategory.LEARNING,
                        title="Knowledge Application Drives Efficiency",
                        description="Tasks that explicitly apply existing knowledge consistently show higher efficiency and success rates.",
                        actionable_recommendation="When creating new tasks, actively identify and link relevant knowledge units to improve execution efficiency.",
                        supporting_patterns=[pattern.pattern_id],
                        confidence_score=pattern.confidence_score,
                        impact_score=0.8,
                        generated_at=datetime.now(),
                        tags=["knowledge-application", "efficiency", "best-practice"],
                        metadata={
                            "pattern_type": "knowledge_application",
                            "efficiency_improvement": pattern.metadata.get("knowledge_benefit", 0),
                        },
                    )
                )

            elif "time_estimation" in pattern.pattern_id:
                insights.append(
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
                )

        return insights

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

    async def _generate_cross_pattern_insights(
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

    async def _score_insights(self, insights: list[GeneratedInsight]) -> list[GeneratedInsight]:
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

    # ========================================================================
    # KNOWLEDGE QUALITY SCORING AND CURATION
    # ========================================================================

    @with_error_handling("score_knowledge_quality", error_type="system")
    async def score_knowledge_quality(
        self, knowledge_dto: KuDTO, supporting_evidence: list[str] | None = None
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

    def _score_completeness(self, knowledge_dto: KuDTO) -> float:
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

    def _score_accuracy(self, knowledge_dto: KuDTO, evidence: list[str] | None = None) -> float:
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

    def _score_relevance(self, knowledge_dto: KuDTO) -> float:
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

    def _score_timeliness(self, knowledge_dto: KuDTO) -> float:
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

    def _score_actionability(self, knowledge_dto: KuDTO) -> float:
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
    async def curate_generated_knowledge(
        self, knowledge_units: list[KuDTO], auto_publish_threshold: float | None = None
    ) -> Result[dict[str, list[KuDTO]]]:
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

        categorized = {
            "auto_publish": [],
            "review_recommended": [],
            "needs_improvement": [],
            "low_quality": [],
        }

        for knowledge_dto in knowledge_units:
            quality_result = await self.score_knowledge_quality(knowledge_dto)
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

    async def _convert_insight_to_knowledge(
        self, insight: GeneratedInsight, user_uid: str
    ) -> KuDTO | None:
        """Convert a generated insight into a knowledge unit."""
        try:
            # Generate knowledge content from insight
            content = self._format_insight_as_ku_content(insight)

            # Create knowledge DTO
            return KuDTO(
                uid=UIDGenerator.generate_knowledge_uid(title=insight.title),
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

        except Exception as e:
            self.logger.warning(f"Failed to convert insight to knowledge: {e}")
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
