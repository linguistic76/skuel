"""
Scheduling Strategies Mixin — CalendarOptimizationService
=========================================================

The five scheduling strategies behind ``_apply_optimization_strategy`` plus
the two match-quality scorers only they consume.

Part of calendar_optimization_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from datetime import date
from operator import attrgetter
from typing import Any

from core.models.calendar_optimization import (
    CognitiveLoadAnalysis,
    EnergyLevel,
    EnergyProfile,
    KnowledgeUnitDTO,
    OptimizedTimeSlot,
    SchedulingStrategy,
)
from core.models.enums import Priority
from core.models.task.task_dto import TaskDTO
from core.services.calendar_optimization_types import (
    CognitiveBalancedStrategy,
    DeadlineDrivenStrategy,
    EnergyAlignedStrategy,
    KnowledgeFocusedStrategy,
    SchedulingStrategyResult,
    SpacedRepetitionStrategy,
)
from core.utils.neo4j_props import coerce_float


class _SchedulingStrategiesMixin:
    """
    Scheduling strategies for CalendarOptimizationService.

    Self-contained: every dependency arrives as an argument, so no host
    attributes need declaring for mypy.
    """

    def _apply_optimization_strategy(
        self,
        strategy: SchedulingStrategy,
        available_slots: list[OptimizedTimeSlot],
        tasks: list[TaskDTO],
        task_loads: dict[str, CognitiveLoadAnalysis],
        knowledge_units: list[KnowledgeUnitDTO],
        energy_profile: EnergyProfile,
    ) -> SchedulingStrategyResult:
        """Apply the specified optimization strategy."""

        if strategy == SchedulingStrategy.COGNITIVE_BALANCED:
            return self._apply_cognitive_balanced_strategy(available_slots, tasks, task_loads)
        elif strategy == SchedulingStrategy.ENERGY_ALIGNED:
            return self._apply_energy_aligned_strategy(available_slots, tasks, energy_profile)
        elif strategy == SchedulingStrategy.KNOWLEDGE_FOCUSED:
            return self._apply_knowledge_focused_strategy(available_slots, tasks, knowledge_units)
        elif strategy == SchedulingStrategy.DEADLINE_DRIVEN:
            return self._apply_deadline_driven_strategy(available_slots, tasks)
        elif strategy == SchedulingStrategy.SPACED_REPETITION:
            return self._apply_spaced_repetition_strategy(available_slots, tasks, knowledge_units)
        else:
            return self._apply_cognitive_balanced_strategy(available_slots, tasks, task_loads)

    def _apply_cognitive_balanced_strategy(
        self,
        slots: list[OptimizedTimeSlot],
        tasks: list[TaskDTO],
        task_loads: dict[str, CognitiveLoadAnalysis],
    ) -> CognitiveBalancedStrategy:
        """Apply cognitive load balancing strategy."""

        # Sort slots by cognitive capacity (highest first)
        sorted_slots = sorted(slots, key=attrgetter("cognitive_capacity"), reverse=True)

        # Sort tasks by cognitive load (distribute heavy tasks to high-capacity slots)
        def _task_load_key(task) -> Any:
            return task_loads.get(task.uid, CognitiveLoadAnalysis(0, 0, 0, 0, 0, 0)).total_load

        sorted_tasks = sorted(tasks, key=_task_load_key, reverse=True)

        schedule = {}
        for i, task in enumerate(sorted_tasks):
            if i < len(sorted_slots):
                slot = sorted_slots[i]
                schedule[task.uid] = {
                    "slot": slot,
                    "cognitive_load": task_loads.get(task.uid),
                    "match_score": self._calculate_cognitive_match_score(
                        slot, task_loads.get(task.uid)
                    ),
                }

        avg_match: float = 0.0
        if schedule:
            scores = [coerce_float(s["match_score"]) for s in schedule.values()]
            avg_match = sum(scores) / len(schedule)
        return {
            "strategy": "cognitive_balanced",
            "schedule": schedule,
            "utilization": len(schedule) / len(slots) if slots else 0,
            "average_match_score": avg_match,
        }

    def _apply_energy_aligned_strategy(
        self, slots: list[OptimizedTimeSlot], tasks: list[TaskDTO], _energy_profile: EnergyProfile
    ) -> EnergyAlignedStrategy:
        """Apply energy-aligned scheduling strategy."""

        # Categorize tasks by energy requirements — CRITICAL and HIGH both
        # demand peak energy; CRITICAL is seated first.
        def _priority_rank(task) -> int:
            return Priority.from_value(task.priority).sort_order()

        high_energy_tasks = sorted(
            (
                t
                for t in tasks
                if t.priority in (Priority.CRITICAL, Priority.HIGH) or t.knowledge_mastery_check
            ),
            key=_priority_rank,
        )
        medium_energy_tasks = [t for t in tasks if t.priority == Priority.MEDIUM]
        low_energy_tasks = [t for t in tasks if t.priority == Priority.LOW]

        schedule = {}

        # Assign high-energy tasks to peak/high energy slots, best capacity
        # first so CRITICAL is seated into PEAK before HIGH slots.
        peak_slots = sorted(
            (s for s in slots if s.energy_level in [EnergyLevel.PEAK, EnergyLevel.HIGH]),
            key=attrgetter("cognitive_capacity"),
            reverse=True,
        )
        for i, task in enumerate(high_energy_tasks):
            if i < len(peak_slots):
                schedule[task.uid] = {"slot": peak_slots[i], "energy_match": "optimal"}

        # Assign medium-energy tasks to medium energy slots
        medium_slots = [s for s in slots if s.energy_level == EnergyLevel.MEDIUM]
        for i, task in enumerate(medium_energy_tasks):
            if i < len(medium_slots):
                schedule[task.uid] = {"slot": medium_slots[i], "energy_match": "good"}

        # Assign low-energy tasks to low energy slots
        low_slots = [s for s in slots if s.energy_level == EnergyLevel.LOW]
        for i, task in enumerate(low_energy_tasks):
            if i < len(low_slots):
                schedule[task.uid] = {"slot": low_slots[i], "energy_match": "adequate"}

        return {
            "strategy": "energy_aligned",
            "schedule": schedule,
            "energy_efficiency": self._calculate_energy_efficiency(schedule),
        }

    def _apply_knowledge_focused_strategy(
        self,
        slots: list[OptimizedTimeSlot],
        tasks: list[TaskDTO],
        _knowledge_units: list[KnowledgeUnitDTO],
    ) -> KnowledgeFocusedStrategy:
        """Apply knowledge-focused scheduling strategy."""

        # Prioritize learning and knowledge application tasks
        # NOTE: applies_knowledge_uids was removed in graph-native migration
        # Using knowledge_mastery_check as proxy for learning-focused tasks
        # For full knowledge relationships, use TaskRelationships.fetch()
        learning_tasks = [t for t in tasks if t.knowledge_mastery_check]
        other_tasks = [t for t in tasks if not t.knowledge_mastery_check]

        # Use high learning effectiveness slots for learning tasks
        learning_slots = sorted(slots, key=attrgetter("learning_effectiveness"), reverse=True)

        schedule = {}

        # Schedule learning tasks first
        for i, task in enumerate(learning_tasks):
            if i < len(learning_slots):
                schedule[task.uid] = {
                    "slot": learning_slots[i],
                    "learning_effectiveness": learning_slots[i].learning_effectiveness,
                    "task_type": "learning",
                }

        # Schedule other tasks in remaining slots
        remaining_slots = learning_slots[len(learning_tasks) :]
        for i, task in enumerate(other_tasks):
            if i < len(remaining_slots):
                schedule[task.uid] = {
                    "slot": remaining_slots[i],
                    "learning_effectiveness": remaining_slots[i].learning_effectiveness,
                    "task_type": "other",
                }

        learning_opt: float = 0.0
        if schedule:
            effectiveness = [coerce_float(s["learning_effectiveness"]) for s in schedule.values()]
            learning_opt = sum(effectiveness) / len(schedule)
        return {
            "strategy": "knowledge_focused",
            "schedule": schedule,
            "learning_optimization": learning_opt,
        }

    def _apply_deadline_driven_strategy(
        self, slots: list[OptimizedTimeSlot], tasks: list[TaskDTO]
    ) -> DeadlineDrivenStrategy:
        """Apply deadline-driven scheduling strategy."""

        # Sort tasks by urgency (due date)
        def _due_date_key(task) -> Any:
            return task.due_date or date.max

        sorted_tasks = sorted(tasks, key=_due_date_key)

        # Sort slots by productivity score
        sorted_slots = sorted(slots, key=attrgetter("productivity_score"), reverse=True)

        schedule = {}
        for i, task in enumerate(sorted_tasks):
            if i < len(sorted_slots):
                schedule[task.uid] = {
                    "slot": sorted_slots[i],
                    "urgency_rank": i + 1,
                    "productivity_score": sorted_slots[i].productivity_score,
                }

        return {
            "strategy": "deadline_driven",
            "schedule": schedule,
            "deadline_coverage": len([t for t in sorted_tasks if t.due_date]) / len(tasks)
            if tasks
            else 0,
        }

    def _apply_spaced_repetition_strategy(
        self,
        slots: list[OptimizedTimeSlot],
        tasks: list[TaskDTO],
        _knowledge_units: list[KnowledgeUnitDTO],
    ) -> SpacedRepetitionStrategy:
        """Apply spaced repetition optimization strategy."""

        # Identify review/repetition tasks
        review_tasks = [t for t in tasks if t.knowledge_mastery_check]

        # Space out review tasks across available slots
        if review_tasks and slots:
            spacing_interval = max(1, len(slots) // len(review_tasks))
            spaced_slots = slots[::spacing_interval]

            schedule = {}
            for i, task in enumerate(review_tasks):
                if i < len(spaced_slots):
                    schedule[task.uid] = {
                        "slot": spaced_slots[i],
                        "spacing_interval": spacing_interval,
                        "task_type": "spaced_repetition",
                    }

            return {
                "strategy": "spaced_repetition",
                "schedule": schedule,
                "spacing_quality": spacing_interval / len(slots) if slots else 0,
            }

        return {"strategy": "spaced_repetition", "schedule": {}, "spacing_quality": 0}

    def _calculate_cognitive_match_score(
        self, slot: OptimizedTimeSlot, load: CognitiveLoadAnalysis | None
    ) -> float:
        """Calculate how well a slot matches a task's cognitive load."""
        if not load:
            return 0.5

        # Ideal match is when cognitive capacity slightly exceeds required load
        capacity_buffer = slot.cognitive_capacity - load.total_load

        if 0.1 <= capacity_buffer <= 0.3:  # Sweet spot
            return 0.9
        elif 0 <= capacity_buffer <= 0.5:  # Good match
            return 0.7
        elif capacity_buffer > 0.5:  # Underutilized
            return 0.5
        else:  # Overloaded
            return 0.2

    def _calculate_energy_efficiency(self, schedule: dict[str, Any]) -> float:
        """Calculate energy efficiency of the schedule."""
        if not schedule:
            return 0.0

        optimal_matches = sum(1 for s in schedule.values() if s.get("energy_match") == "optimal")
        return optimal_matches / len(schedule)
