"""
Pattern Analysis Mixin — InsightGenerationService
=================================================

Pattern recognition over completed tasks: time, priority, project,
knowledge-application, and workflow detectors plus the shared efficiency
scorer they feed.

Part of insight_generation_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, Priority
from core.models.insight import PatternType, TaskPattern
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.task.task import Task
    from core.models.type_hints import UserUID


class _PatternAnalysisMixin:
    """
    Task-completion pattern recognition for InsightGenerationService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by InsightGenerationService.__init__
    tasks_service: Any
    logger: Any
    min_pattern_frequency: int
    min_confidence_score: float

    async def _get_completed_tasks_since(
        self, user_uid: UserUID, since_date: datetime
    ) -> list[Task]:
        """Get completed tasks for a user since a specific date."""
        if not self.tasks_service:
            msg = "tasks_service is required for task analysis but was not injected"
            raise RuntimeError(msg)

        try:
            user_tasks_result = await self.tasks_service.get_user_tasks(user_uid)
            if user_tasks_result.is_error:
                return []

            return [
                task
                for task in user_tasks_result.value
                if (
                    task.status == EntityStatus.COMPLETED
                    and task.completion_date
                    and datetime.combine(task.completion_date, datetime.min.time()) >= since_date
                )
            ]

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.warning(f"Failed to get completed tasks: {e}")
            return []
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.warning(
                f"Unexpected error getting completed tasks: {type(e).__name__}: {e}"
            )
            return []

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
        patterns.extend(self._analyze_time_patterns(completed_tasks))
        patterns.extend(self._analyze_priority_patterns(completed_tasks))
        patterns.extend(self._analyze_project_patterns(completed_tasks))
        patterns.extend(await self._analyze_knowledge_application_patterns(completed_tasks))
        patterns.extend(self._analyze_workflow_patterns(completed_tasks))

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

    def _analyze_time_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
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

    def _analyze_priority_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
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

    def _analyze_project_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
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
        Detect whether tasks that apply knowledge complete more efficiently.

        Knowledge application is graph-native: the linkage lives on
        ``(Task)-[:APPLIES_KNOWLEDGE]->(Ku)`` edges, not as a property on the Task
        model (removed in the ADR-035/ADR-065 graph-native migration). This detector
        fetches those edges in a single batched query, partitions completed tasks into
        the knowledge-applying cohort vs. the whole, and emits a
        ``KNOWLEDGE_APPLICATION`` pattern when the knowledge cohort is meaningfully
        (>10%) more efficient — the core "applied knowledge compounds" signal.

        Backend: UnifiedRelationshipService.batch_get_related_uids (APPLIES_KNOWLEDGE) —
        one query for all tasks, reading only the knowledge key (avoids the
        N-times-all-specs fan-out of a per-task relationship fetch on large histories).

        Args:
            tasks: Completed tasks to analyze.

        Returns:
            A single-element list with the detected pattern, or an empty list when
            there is no relationship service wired, too few knowledge-applying tasks,
            or no efficiency benefit (graceful — other pattern detectors still run).

        See: /docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md
        """
        # The relationship service is reached through the injected tasks facade
        # (facade.relationships is the UnifiedRelationshipService). Production wires
        # this at bootstrap (services_bootstrap/compose.py — late back-reference, since
        # the generator is built before TasksService). This guard is the safety net for
        # that true-circular-dependency window and for tests; if it ever trips in
        # production the bootstrap wiring regressed.
        relationship_service = getattr(self.tasks_service, "relationships", None)
        if relationship_service is None:
            self.logger.debug(
                "Skipping knowledge-application pattern: no relationship service wired"
            )
            return []

        # Fetch APPLIES_KNOWLEDGE edges for all tasks in ONE query (knowledge key only).
        knowledge_result = await relationship_service.batch_get_related_uids(
            "knowledge", [task.uid for task in tasks]
        )
        if knowledge_result.is_error:
            self.logger.debug("Skipping knowledge-application pattern: knowledge edge fetch failed")
            return []
        knowledge_by_task = knowledge_result.value

        knowledge_tasks = [task for task in tasks if knowledge_by_task.get(task.uid)]
        if len(knowledge_tasks) < self.min_pattern_frequency:
            return []

        knowledge_efficiency = self._calculate_task_efficiency(knowledge_tasks)
        overall_efficiency = self._calculate_task_efficiency(tasks)

        # Require a real (>10%) lift over the baseline before claiming a benefit.
        if overall_efficiency <= 0 or knowledge_efficiency <= overall_efficiency * 1.1:
            return []

        applied_knowledge_uids = sorted(
            {uid for uids in knowledge_by_task.values() for uid in uids}
        )
        benefit_ratio = knowledge_efficiency / overall_efficiency

        return [
            TaskPattern(
                pattern_id=f"knowledge_application_benefit_{datetime.now().strftime('%Y%m%d')}",
                pattern_type=PatternType.KNOWLEDGE_APPLICATION,
                confidence_score=min(benefit_ratio, 1.0),
                supporting_tasks=[task.uid for task in knowledge_tasks],
                description="Tasks that apply knowledge complete more efficiently",
                evidence=[
                    f"Knowledge-applying tasks efficiency: {knowledge_efficiency:.1%}",
                    f"Overall efficiency: {overall_efficiency:.1%}",
                    f"Improvement: {(benefit_ratio - 1):.1%}",
                ],
                frequency=len(knowledge_tasks),
                success_rate=knowledge_efficiency,
                knowledge_uids_involved=applied_knowledge_uids,
                metadata={"knowledge_benefit": benefit_ratio},
            )
        ]

    def _analyze_workflow_patterns(self, tasks: list[Task]) -> list[TaskPattern]:
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
