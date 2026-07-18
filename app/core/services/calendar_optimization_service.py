"""
Calendar Optimization Service
=========================================

Knowledge-aware calendar scheduling with cognitive load balancing.
Optimizes task scheduling based on knowledge requirements and learning patterns.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from operator import attrgetter
from typing import Any

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain, Priority
from core.models.event.event_dto import EventDTO
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import UserUID
from core.services.calendar_optimization_types import (
    CognitiveBalancedStrategy,
    DeadlineDrivenStrategy,
    EnergyAlignedStrategy,
    KnowledgeFocusedStrategy,
    OptimalLoadDistribution,
    SchedulingStrategyResult,
    SpacedRepetitionStrategy,
)

# NOTE (November 2025): Removed Has* protocol imports - TaskDTO is well-typed
# - TaskDTO.knowledge_mastery_check: bool (direct access)
# - TaskDTO.project: str | None (direct access)
# - TaskDTO.applies_knowledge_uids: REMOVED (graph-native migration)
# Use TaskRelationships.fetch() for relationship data
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import coerce_float
from core.utils.result_simplified import Errors, Result

# Type alias for clarity
KnowledgeUnitDTO = CurriculumDTO


class CognitiveLoadType(Enum):
    """Types of cognitive load in learning and task execution."""

    INTRINSIC = "intrinsic"  # Inherent complexity of the content
    EXTRANEOUS = "extraneous"  # Poor design/presentation factors
    GERMANE = "germane"  # Building schemas and understanding


class EnergyLevel(Enum):
    """User energy levels throughout the day."""

    PEAK = "peak"  # 90-100% capacity
    HIGH = "high"  # 70-89% capacity
    MEDIUM = "medium"  # 50-69% capacity
    LOW = "low"  # 30-49% capacity
    DEPLETED = "depleted"  # 0-29% capacity


class SchedulingStrategy(Enum):
    """Calendar optimization strategies."""

    KNOWLEDGE_FOCUSED = "knowledge_focused"  # Optimize for learning outcomes
    DEADLINE_DRIVEN = "deadline_driven"  # Prioritize urgent deadlines
    ENERGY_ALIGNED = "energy_aligned"  # Match tasks to energy levels
    COGNITIVE_BALANCED = "cognitive_balanced"  # Balance cognitive load
    SPACED_REPETITION = "spaced_repetition"  # Optimize knowledge retention


@dataclass
class CognitiveLoadAnalysis:
    """Analysis of cognitive load for a task or learning session."""

    intrinsic_load: float  # 0.0-1.0: Content complexity
    extraneous_load: float  # 0.0-1.0: Environmental/design factors
    germane_load: float  # 0.0-1.0: Schema building requirement
    total_load: float  # Combined cognitive load
    domain_complexity: float  # Domain-specific complexity
    prerequisite_load: float  # Load from missing prerequisites

    def is_overload_risk(self) -> bool:
        """Check if cognitive load risks overload."""
        return self.total_load > 0.8

    def get_load_category(self) -> str:
        """Categorize cognitive load level."""
        if self.total_load <= 0.3:
            return "light"
        elif self.total_load <= 0.6:
            return "moderate"
        elif self.total_load <= 0.8:
            return "heavy"
        else:
            return "overload"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization, including derived fields."""
        return {
            "intrinsic_load": self.intrinsic_load,
            "extraneous_load": self.extraneous_load,
            "germane_load": self.germane_load,
            "total_load": self.total_load,
            "domain_complexity": self.domain_complexity,
            "prerequisite_load": self.prerequisite_load,
            "is_overload_risk": self.is_overload_risk(),
            "load_category": self.get_load_category(),
        }


@dataclass
class EnergyProfile:
    """User's energy patterns throughout the day."""

    peak_hours: list[int]  # Hours when energy is highest (0-23)
    high_hours: list[int]  # Hours with high energy
    medium_hours: list[int]  # Hours with medium energy
    low_hours: list[int]  # Hours with low energy
    depleted_hours: list[int]  # Hours when energy is depleted
    chronotype: str  # "morning", "evening", "neutral"
    focus_duration_minutes: int  # Maximum sustained focus time


@dataclass
class OptimizedTimeSlot:
    """An optimized time slot for scheduling."""

    start_time: datetime
    end_time: datetime
    energy_level: EnergyLevel
    cognitive_capacity: float  # Available cognitive capacity (0.0-1.0)
    domain_affinity: Domain | None  # Best domain for this slot
    interruption_risk: float  # Risk of interruptions (0.0-1.0)
    learning_effectiveness: float  # Effectiveness for learning (0.0-1.0)
    productivity_score: float  # Overall productivity potential

    def duration_minutes(self) -> int:
        """Get slot duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class LearningSession:
    """Optimized learning session with multiple knowledge units."""

    session_id: str
    start_time: datetime
    end_time: datetime
    knowledge_units: list[str]  # UIDs of knowledge units
    primary_domain: Domain
    session_type: str  # "deep_focus", "review", "practice", "exploration"
    cognitive_load: CognitiveLoadAnalysis
    prerequisites_covered: list[str]
    learning_objectives: list[str]
    recommended_breaks: list[int]  # Minutes into session for breaks
    spaced_repetition_items: list[str]  # Items for spaced repetition

    def duration_minutes(self) -> int:
        """Get session duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class KnowledgeSchedulingRecommendation:
    """Recommendation for scheduling knowledge-related activities."""

    activity_type: str  # "learning", "application", "review", "practice"
    recommended_time: datetime
    duration_minutes: int
    energy_requirement: EnergyLevel
    cognitive_load: CognitiveLoadAnalysis
    knowledge_units: list[str]
    reasoning: str  # Why this timing is recommended
    prerequisites: list[str]  # Required prior knowledge
    follow_up_activities: list[str]
    confidence_score: float  # 0.0-1.0: Confidence in recommendation


@dataclass
class CalendarOptimization:
    """Complete calendar optimization with scheduling recommendations."""

    optimization_date: date
    strategy: SchedulingStrategy
    total_cognitive_load: float
    load_distribution: dict[str, float]  # Hour -> cognitive load
    optimized_slots: list[OptimizedTimeSlot]
    learning_sessions: list[LearningSession]
    scheduling_recommendations: list[KnowledgeSchedulingRecommendation]
    energy_alignment_score: float  # How well tasks align with energy
    knowledge_progression_score: float  # Learning progression quality
    cognitive_balance_score: float  # How well cognitive load is balanced


@dataclass(frozen=True)
class DomainLoadInfo:
    """Cognitive load information for a specific domain."""

    total_load: float
    average_load: float
    task_count: int


@dataclass(frozen=True)
class CognitiveLoadBalance:
    """Cognitive load balancing analysis and recommendations."""

    date: str
    total_cognitive_load: float
    domain_load_distribution: dict[str, DomainLoadInfo]
    optimal_distribution: OptimalLoadDistribution
    balancing_recommendations: list[dict[str, Any]]  # Keep as list[dict] for flexibility
    hourly_cognitive_capacity: dict[int, float]
    overload_risk_hours: list[int]
    peak_performance_hours: list[int]


class CalendarOptimizationService:
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

    def _determine_energy_level(self, hour: int, energy_profile: EnergyProfile) -> EnergyLevel:
        """Determine energy level for a given hour."""
        if hour in energy_profile.peak_hours:
            return EnergyLevel.PEAK
        elif hour in energy_profile.high_hours:
            return EnergyLevel.HIGH
        elif hour in energy_profile.medium_hours:
            return EnergyLevel.MEDIUM
        elif hour in energy_profile.low_hours:
            return EnergyLevel.LOW
        else:
            return EnergyLevel.DEPLETED

    def _calculate_cognitive_capacity(self, hour: int, energy_profile: EnergyProfile) -> float:
        """Calculate cognitive capacity for a given hour."""
        energy = self._determine_energy_level(hour, energy_profile)

        base_capacity = {
            EnergyLevel.PEAK: 0.95,
            EnergyLevel.HIGH: 0.80,
            EnergyLevel.MEDIUM: 0.60,
            EnergyLevel.LOW: 0.40,
            EnergyLevel.DEPLETED: 0.20,
        }

        return base_capacity[energy]

    def _determine_domain_affinity(self, hour: int, energy: EnergyLevel) -> Domain | None:
        """Determine which domain is best suited for this time slot."""
        if energy in [EnergyLevel.PEAK, EnergyLevel.HIGH]:
            # High energy times are good for complex domains
            if 9 <= hour <= 11:
                return Domain.TECH  # Technical work in morning
            elif 14 <= hour <= 16:
                return Domain.CREATIVE  # Creative work in afternoon
        elif energy == EnergyLevel.MEDIUM:
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

    def _calculate_learning_effectiveness(self, hour: int, energy: EnergyLevel) -> float:
        """Calculate learning effectiveness for a given hour and energy level."""
        energy_factor = {
            EnergyLevel.PEAK: 0.95,
            EnergyLevel.HIGH: 0.85,
            EnergyLevel.MEDIUM: 0.65,
            EnergyLevel.LOW: 0.40,
            EnergyLevel.DEPLETED: 0.20,
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
        self, hour: int, energy: EnergyLevel, cognitive_capacity: float
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

        if task.priority == Priority.HIGH:
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

        # Categorize tasks by energy requirements
        high_energy_tasks = [
            t for t in tasks if t.priority == Priority.HIGH or t.knowledge_mastery_check
        ]
        medium_energy_tasks = [t for t in tasks if t.priority == Priority.MEDIUM]
        low_energy_tasks = [t for t in tasks if t.priority == Priority.LOW]

        schedule = {}

        # Assign high-energy tasks to peak/high energy slots
        peak_slots = [s for s in slots if s.energy_level in [EnergyLevel.PEAK, EnergyLevel.HIGH]]
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
                        if slot.energy_level == EnergyLevel.PEAK
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
        peak_slots = [s for s in available_slots if s.energy_level == EnergyLevel.PEAK]
        high_slots = [s for s in available_slots if s.energy_level == EnergyLevel.HIGH]

        if peak_slots:
            # Deep learning recommendation
            recommendations.append(
                KnowledgeSchedulingRecommendation(
                    activity_type="deep_learning",
                    recommended_time=peak_slots[0].start_time,
                    duration_minutes=90,
                    energy_requirement=EnergyLevel.PEAK,
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
                    energy_requirement=EnergyLevel.HIGH,
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
    ) -> dict[str, float]:
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
                if energy_level == EnergyLevel.PEAK:
                    alignment_scores.append(1.0)
                elif energy_level == EnergyLevel.HIGH:
                    alignment_scores.append(0.8)
                elif energy_level == EnergyLevel.MEDIUM:
                    alignment_scores.append(0.6)
                elif energy_level == EnergyLevel.LOW:
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
