"""
Calendar Optimization Service
=========================================

Knowledge-aware calendar scheduling with cognitive load balancing.
Optimizes task scheduling based on knowledge requirements and learning patterns.

Decomposition (July 2026): domain models live in
core/models/calendar_optimization.py; the five scheduling strategies live in
calendar_optimization_strategies.py (_SchedulingStrategiesMixin).
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from core.models.calendar_optimization import (
    CalendarOptimization,
    CognitiveLoadAnalysis,
    EnergyProfile,
    KnowledgeSchedulingRecommendation,
    KnowledgeUnitDTO,
    LearningSession,
    OptimizedTimeSlot,
    SchedulingStrategy,
    SlotEnergyLevel,
)
from core.models.enums import Domain, Priority
from core.models.event.event_dto import EventDTO
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import UserUID
from core.services.calendar_optimization_strategies import _SchedulingStrategiesMixin
from core.services.calendar_optimization_types import SchedulingStrategyResult

# NOTE (November 2025): Removed Has* protocol imports - TaskDTO is well-typed
# - TaskDTO.knowledge_mastery_check: bool (direct access)
# - TaskDTO.project: str | None (direct access)
# - TaskDTO.applies_knowledge_uids: REMOVED (graph-native migration)
# Use TaskRelationships.fetch() for relationship data
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class CalendarOptimizationService(_SchedulingStrategiesMixin):
    """
    Service for knowledge-aware calendar optimization and cognitive load balancing.
    """

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def optimize_knowledge_scheduling(
        self,
        user_uid: UserUID,
        target_date: date,
        tasks: list[TaskDTO],
        events: list[EventDTO],
        knowledge_units: list[KnowledgeUnitDTO],
        strategy: SchedulingStrategy = SchedulingStrategy.COGNITIVE_BALANCED,
    ) -> Result[CalendarOptimization]:
        """
        Optimize calendar scheduling with knowledge-aware algorithms.

        Args:
            user_uid: User identifier,
            target_date: Date to optimize,
            tasks: Available tasks to schedule,
            events: Fixed events/commitments,
            knowledge_units: Available knowledge units,
            strategy: Optimization strategy to use

        Returns:
            Complete calendar optimization with recommendations
        """
        try:
            # Get user's energy profile
            energy_profile = self._get_user_energy_profile(user_uid)

            # Analyze existing commitments
            existing_slots = self._analyze_existing_commitments(events, target_date)

            # Generate available time slots
            available_slots = self._generate_available_slots(
                target_date, existing_slots, energy_profile
            )

            # Analyze cognitive load requirements
            task_loads = {}
            for task in tasks:
                task_loads[task.uid] = self._analyze_task_cognitive_load(task, knowledge_units)

            # Apply optimization strategy
            optimization = self._apply_optimization_strategy(
                strategy, available_slots, tasks, task_loads, knowledge_units, energy_profile
            )

            # Generate learning sessions
            learning_sessions = self._plan_learning_sessions(
                user_uid, available_slots, knowledge_units, energy_profile
            )

            # Create knowledge scheduling recommendations
            recommendations = self._generate_scheduling_recommendations(
                user_uid, tasks, knowledge_units, available_slots, energy_profile
            )

            # Calculate optimization scores
            energy_score = self._calculate_energy_alignment_score(optimization, energy_profile)
            progression_score = self._calculate_knowledge_progression_score(learning_sessions)
            balance_score = self._calculate_cognitive_balance_score(task_loads, optimization)

            result = CalendarOptimization(
                optimization_date=target_date,
                strategy=strategy,
                total_cognitive_load=sum(load.total_load for load in task_loads.values()),
                load_distribution=self._calculate_load_distribution(optimization, task_loads),
                optimized_slots=available_slots,
                learning_sessions=learning_sessions,
                scheduling_recommendations=recommendations,
                energy_alignment_score=energy_score,
                knowledge_progression_score=progression_score,
                cognitive_balance_score=balance_score,
            )

            self.logger.info(f"Calendar optimization completed for {user_uid} on {target_date}")
            return Result.ok(result)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(f"Calendar optimization failed: {e!s}")
            return Result.fail(
                Errors.system(
                    message="Calendar optimization failed",
                    exception=e,
                    operation="optimize_knowledge_scheduling",
                    user_uid=user_uid,
                    target_date=target_date.isoformat(),
                    strategy=strategy.value,
                )
            )

    # Private helper methods

    def _get_user_energy_profile(self, _user_uid: UserUID) -> EnergyProfile:
        """Get user's energy profile - for demo, return realistic pattern."""
        return EnergyProfile(
            peak_hours=[9, 10, 11],  # Morning peak
            high_hours=[8, 12, 14, 15],  # High energy periods
            medium_hours=[7, 13, 16, 17],  # Medium energy
            low_hours=[18, 19, 20],  # Evening low
            depleted_hours=[21, 22, 23, 0, 1, 2, 3, 4, 5, 6],  # Night/early morning
            chronotype="morning",  # Morning person
            focus_duration_minutes=90,  # 90-minute focus blocks
        )

    def _analyze_existing_commitments(
        self, events: list[EventDTO], target_date: date
    ) -> list[tuple[datetime, datetime]]:
        """Analyze existing calendar commitments."""
        commitments = []
        for event in events:
            if event.event_date == target_date:
                start = datetime.combine(target_date, event.start_time or time(9, 0))
                # Calculate duration from start_time and end_time
                if event.end_time:
                    end = datetime.combine(target_date, event.end_time)
                else:
                    # Default to 1 hour if no end time
                    end = start + timedelta(hours=1)
                commitments.append((start, end))
        return commitments

    def _generate_available_slots(
        self,
        target_date: date,
        existing_slots: list[tuple[datetime, datetime]],
        energy_profile: EnergyProfile,
    ) -> list[OptimizedTimeSlot]:
        """Generate available time slots with energy and cognitive capacity analysis."""
        slots = []

        # Generate hourly slots from 7 AM to 10 PM
        for hour in range(7, 23):
            slot_start = datetime.combine(target_date, time(hour, 0))
            slot_end = slot_start + timedelta(hours=1)

            # Check if slot conflicts with existing commitments
            conflicts = any(
                not (slot_end <= start or slot_start >= end) for start, end in existing_slots
            )

            if not conflicts:
                # Determine energy level for this hour
                energy = self._determine_energy_level(hour, energy_profile)

                # Calculate cognitive capacity
                cognitive_capacity = self._calculate_cognitive_capacity(hour, energy_profile)

                slot = OptimizedTimeSlot(
                    start_time=slot_start,
                    end_time=slot_end,
                    energy_level=energy,
                    cognitive_capacity=cognitive_capacity,
                    domain_affinity=self._determine_domain_affinity(hour, energy),
                    interruption_risk=self._calculate_interruption_risk(hour),
                    learning_effectiveness=self._calculate_learning_effectiveness(hour, energy),
                    productivity_score=self._calculate_productivity_score(
                        hour, energy, cognitive_capacity
                    ),
                )
                slots.append(slot)

        return slots

    def _determine_energy_level(self, hour: int, energy_profile: EnergyProfile) -> SlotEnergyLevel:
        """Determine energy level for a given hour."""
        if hour in energy_profile.peak_hours:
            return SlotEnergyLevel.PEAK
        elif hour in energy_profile.high_hours:
            return SlotEnergyLevel.HIGH
        elif hour in energy_profile.medium_hours:
            return SlotEnergyLevel.MEDIUM
        elif hour in energy_profile.low_hours:
            return SlotEnergyLevel.LOW
        else:
            return SlotEnergyLevel.DEPLETED

    def _calculate_cognitive_capacity(self, hour: int, energy_profile: EnergyProfile) -> float:
        """Calculate cognitive capacity for a given hour."""
        energy = self._determine_energy_level(hour, energy_profile)

        base_capacity = {
            SlotEnergyLevel.PEAK: 0.95,
            SlotEnergyLevel.HIGH: 0.80,
            SlotEnergyLevel.MEDIUM: 0.60,
            SlotEnergyLevel.LOW: 0.40,
            SlotEnergyLevel.DEPLETED: 0.20,
        }

        return base_capacity[energy]

    def _determine_domain_affinity(self, hour: int, energy: SlotEnergyLevel) -> Domain | None:
        """Determine which domain is best suited for this time slot."""
        if energy in [SlotEnergyLevel.PEAK, SlotEnergyLevel.HIGH]:
            # High energy times are good for complex domains
            if 9 <= hour <= 11:
                return Domain.TECH  # Technical work in morning
            elif 14 <= hour <= 16:
                return Domain.CREATIVE  # Creative work in afternoon
        elif energy == SlotEnergyLevel.MEDIUM:
            return Domain.BUSINESS  # Business tasks for medium energy
        else:
            return Domain.PERSONAL  # Personal tasks for low energy

        return None

    def _calculate_interruption_risk(self, hour: int) -> float:
        """Calculate risk of interruptions for a given hour."""
        # Higher risk during business hours
        if 9 <= hour <= 17:
            return 0.6
        elif 7 <= hour <= 9 or 17 <= hour <= 19:
            return 0.3
        else:
            return 0.1

    def _calculate_learning_effectiveness(self, hour: int, energy: SlotEnergyLevel) -> float:
        """Calculate learning effectiveness for a given hour and energy level."""
        energy_factor = {
            SlotEnergyLevel.PEAK: 0.95,
            SlotEnergyLevel.HIGH: 0.85,
            SlotEnergyLevel.MEDIUM: 0.65,
            SlotEnergyLevel.LOW: 0.40,
            SlotEnergyLevel.DEPLETED: 0.20,
        }[energy]

        # Time-of-day factor
        if 9 <= hour <= 11:  # Morning peak
            time_factor = 0.95
        elif 14 <= hour <= 16:  # Afternoon good
            time_factor = 0.80
        elif 7 <= hour <= 9 or 16 <= hour <= 18:  # Decent times
            time_factor = 0.70
        else:  # Evening/night
            time_factor = 0.50

        return energy_factor * time_factor

    def _calculate_productivity_score(
        self, hour: int, energy: SlotEnergyLevel, cognitive_capacity: float
    ) -> float:
        """Calculate overall productivity score for a time slot."""
        interruption_factor = 1.0 - self._calculate_interruption_risk(hour)
        learning_factor = self._calculate_learning_effectiveness(hour, energy)

        return cognitive_capacity * 0.4 + interruption_factor * 0.3 + learning_factor * 0.3

    def _analyze_task_cognitive_load(
        self, task: TaskDTO, _knowledge_units: list[KnowledgeUnitDTO]
    ) -> CognitiveLoadAnalysis:
        """
        Analyze cognitive load requirements for a task.

        Note: Knowledge relationship data (applies_knowledge_uids, prerequisite_knowledge_uids)
        was removed from TaskDTO during graph-native migration. Cognitive load calculation
        now relies on task attributes and domain complexity.
        """

        # Base intrinsic load from task complexity
        intrinsic_load = 0.3  # Default base load

        # GRAPH-NATIVE MIGRATION: applies_knowledge_uids removed from TaskDTO
        # Previously: if task.applies_knowledge_uids: intrinsic_load += len(...) * 0.1
        # For learning tasks, add estimated knowledge complexity
        if task.knowledge_mastery_check:
            intrinsic_load += 0.2  # Estimate for knowledge application tasks

        if task.priority in (Priority.HIGH, Priority.CRITICAL):
            intrinsic_load += 0.2

        # Extraneous load (environmental factors)
        extraneous_load = 0.1  # Base environmental load

        # Adjust based on task characteristics
        if task.project:
            extraneous_load += 0.1  # Context switching

        # Germane load (schema building)
        germane_load = 0.2  # Base learning load

        if task.knowledge_mastery_check:
            germane_load += 0.3

        # GRAPH-NATIVE MIGRATION: prerequisite_knowledge_uids removed from TaskDTO
        # Previously: if task.prerequisite_knowledge_uids: prerequisite_load = len(...) * 0.05
        # Prerequisite load calculation removed - requires relationship service access
        prerequisite_load = 0.0

        # Domain complexity
        domain_complexity = self._calculate_domain_complexity(getattr(task, "domain", Domain.TASKS))

        total_load = min(1.0, intrinsic_load + extraneous_load + germane_load + prerequisite_load)

        return CognitiveLoadAnalysis(
            intrinsic_load=intrinsic_load,
            extraneous_load=extraneous_load,
            germane_load=germane_load,
            total_load=total_load,
            domain_complexity=domain_complexity,
            prerequisite_load=prerequisite_load,
        )

    def _calculate_domain_complexity(self, domain: Domain) -> float:
        """Calculate complexity factor for different domains."""
        complexity_map = {
            Domain.TECH: 0.8,
            Domain.CREATIVE: 0.6,
            Domain.BUSINESS: 0.5,
            Domain.HEALTH: 0.4,
            Domain.PERSONAL: 0.3,
        }
        return complexity_map.get(domain, 0.5)

    def _plan_learning_sessions(
        self,
        _user_uid: UserUID,
        available_slots: list[OptimizedTimeSlot],
        knowledge_units: list[KnowledgeUnitDTO],
        _energy_profile: EnergyProfile,
    ) -> list[LearningSession]:
        """Plan optimized learning sessions."""

        sessions = []

        # Find high-effectiveness slots for learning
        learning_slots = [slot for slot in available_slots if slot.learning_effectiveness > 0.7]

        if learning_slots and knowledge_units:
            # Group knowledge units by domain
            domain_groups: dict[Domain, list[Any]] = {}
            for ku in knowledge_units[:6]:  # Limit for demo
                domain = getattr(ku, "domain", Domain.KNOWLEDGE)
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(ku)

            # Create sessions for each domain
            for i, (domain, units) in enumerate(domain_groups.items()):
                if i < len(learning_slots):
                    slot = learning_slots[i]

                    session = LearningSession(
                        session_id=f"session_{domain.value}_{i}",
                        start_time=slot.start_time,
                        end_time=slot.end_time,
                        knowledge_units=[ku.uid for ku in units],
                        primary_domain=domain,
                        session_type="deep_focus"
                        if slot.energy_level == SlotEnergyLevel.PEAK
                        else "review",
                        cognitive_load=CognitiveLoadAnalysis(0.6, 0.2, 0.4, 0.7, 0.5, 0.1),
                        prerequisites_covered=[],
                        learning_objectives=[f"Master {unit.title}" for unit in units],
                        recommended_breaks=[25, 55] if slot.duration_minutes() >= 90 else [30],
                        spaced_repetition_items=[],
                    )
                    sessions.append(session)

        return sessions

    def _generate_scheduling_recommendations(
        self,
        _user_uid: UserUID,
        _tasks: list[TaskDTO],
        knowledge_units: list[KnowledgeUnitDTO],
        available_slots: list[OptimizedTimeSlot],
        _energy_profile: EnergyProfile,
    ) -> list[KnowledgeSchedulingRecommendation]:
        """Generate knowledge scheduling recommendations."""

        recommendations = []

        # Recommend optimal times for different types of knowledge work
        peak_slots = [s for s in available_slots if s.energy_level == SlotEnergyLevel.PEAK]
        high_slots = [s for s in available_slots if s.energy_level == SlotEnergyLevel.HIGH]

        if peak_slots:
            # Deep learning recommendation
            recommendations.append(
                KnowledgeSchedulingRecommendation(
                    activity_type="deep_learning",
                    recommended_time=peak_slots[0].start_time,
                    duration_minutes=90,
                    energy_requirement=SlotEnergyLevel.PEAK,
                    cognitive_load=CognitiveLoadAnalysis(0.7, 0.2, 0.5, 0.8, 0.6, 0.1),
                    knowledge_units=[ku.uid for ku in knowledge_units[:3]],
                    reasoning="Peak energy period optimal for complex learning tasks",
                    prerequisites=[],
                    follow_up_activities=["practice", "application"],
                    confidence_score=0.9,
                )
            )

        if high_slots:
            # Application practice recommendation
            recommendations.append(
                KnowledgeSchedulingRecommendation(
                    activity_type="application_practice",
                    recommended_time=high_slots[0].start_time,
                    duration_minutes=60,
                    energy_requirement=SlotEnergyLevel.HIGH,
                    cognitive_load=CognitiveLoadAnalysis(0.5, 0.2, 0.3, 0.6, 0.4, 0.1),
                    knowledge_units=[ku.uid for ku in knowledge_units[3:6]],
                    reasoning="High energy suitable for applying learned concepts",
                    prerequisites=[knowledge_units[0].uid if knowledge_units else ""],
                    follow_up_activities=["review", "teach_others"],
                    confidence_score=0.8,
                )
            )

        return recommendations

    def _calculate_load_distribution(
        self, optimization: SchedulingStrategyResult, task_loads: dict[str, CognitiveLoadAnalysis]
    ) -> dict[int, float]:
        """Calculate cognitive load distribution by hour."""
        distribution = {}

        schedule = optimization.get("schedule", {})
        for task_uid, task_schedule in schedule.items():
            slot = task_schedule.get("slot")
            load = task_loads.get(task_uid)

            if slot and load:
                hour = slot.start_time.hour
                if hour not in distribution:
                    distribution[hour] = 0.0
                distribution[hour] += load.total_load

        return distribution

    def _calculate_energy_alignment_score(
        self, optimization: SchedulingStrategyResult, energy_profile: EnergyProfile
    ) -> float:
        """Calculate how well the optimization aligns with user's energy patterns."""
        schedule = optimization.get("schedule", {})
        if not schedule:
            return 0.0

        alignment_scores = []
        for task_schedule in schedule.values():
            slot = task_schedule.get("slot")
            if slot:
                hour = slot.start_time.hour
                energy_level = self._determine_energy_level(hour, energy_profile)

                # Higher score for better energy alignment
                if energy_level == SlotEnergyLevel.PEAK:
                    alignment_scores.append(1.0)
                elif energy_level == SlotEnergyLevel.HIGH:
                    alignment_scores.append(0.8)
                elif energy_level == SlotEnergyLevel.MEDIUM:
                    alignment_scores.append(0.6)
                elif energy_level == SlotEnergyLevel.LOW:
                    alignment_scores.append(0.4)
                else:  # DEPLETED
                    alignment_scores.append(0.2)

        return sum(alignment_scores) / len(alignment_scores) if alignment_scores else 0.0

    def _calculate_knowledge_progression_score(
        self, learning_sessions: list[LearningSession]
    ) -> float:
        """Calculate the quality of knowledge progression in learning sessions."""
        if not learning_sessions:
            return 0.0

        # Score based on session distribution, domain coverage, and timing
        domain_coverage = len(set(session.primary_domain for session in learning_sessions))
        max_domains = 5  # Reasonable maximum

        progression_factors = [
            domain_coverage / max_domains,  # Domain diversity
            min(1.0, len(learning_sessions) / 3),  # Session frequency
            sum(1 for session in learning_sessions if session.session_type == "deep_focus")
            / len(learning_sessions),  # Deep learning ratio
        ]

        return sum(progression_factors) / len(progression_factors)

    def _calculate_cognitive_balance_score(
        self, task_loads: dict[str, CognitiveLoadAnalysis], optimization: SchedulingStrategyResult
    ) -> float:
        """Calculate how well cognitive load is balanced throughout the day."""
        distribution = self._calculate_load_distribution(optimization, task_loads)
        if not distribution:
            return 0.0

        # Calculate variance in cognitive load across hours
        loads = list(distribution.values())
        mean_load = sum(loads) / len(loads)
        variance = sum((load - mean_load) ** 2 for load in loads) / len(loads)

        # Lower variance = better balance (inverse score)
        return max(0.0, 1.0 - variance)
