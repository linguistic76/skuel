"""
Tests for Calendar Optimization Service
=========================================

Mock-free unit tests for CalendarOptimizationService — pure, synchronous
scheduling algorithms exercised with real DTOs (testing-gap roadmap item 4:
pure-algorithm units; this service previously had ZERO coverage).

Covers:
- Dataclass predicates (CognitiveLoadAnalysis, OptimizedTimeSlot, LearningSession)
- Energy profile, commitment analysis, and available-slot generation
- Hourly heuristics (energy level, capacity, interruption risk, effectiveness)
- Task cognitive-load analysis and domain complexity
- All five scheduling strategies plus the unknown-strategy fallback
- Score calculations (efficiency, distribution, alignment, progression, balance)
- One end-to-end optimize_knowledge_scheduling run

Version: 1.0.0
Date: 2026-07-18
"""

from datetime import date, datetime, time, timedelta

import pytest

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain, EntityType, Priority
from core.models.event.event_dto import EventDTO
from core.models.task.task_dto import TaskDTO
from core.services.calendar_optimization_service import (
    CalendarOptimizationService,
    CognitiveLoadAnalysis,
    EnergyLevel,
    LearningSession,
    OptimizedTimeSlot,
    SchedulingStrategy,
)

TARGET_DATE = date(2026, 7, 20)
USER_UID = "user_test"


@pytest.fixture
def service() -> CalendarOptimizationService:
    """Real service — constructor takes no dependencies."""
    return CalendarOptimizationService()


def make_task(uid: str, **kwargs) -> TaskDTO:
    """Build a real TaskDTO with a unique uid (empty uids collide in schedules)."""
    return TaskDTO(uid=uid, title=f"Task {uid}", user_uid=USER_UID, **kwargs)


def make_event(uid: str, **kwargs) -> EventDTO:
    """Build a real EventDTO."""
    return EventDTO(uid=uid, title=f"Event {uid}", user_uid=USER_UID, **kwargs)


def make_slot(
    hour: int,
    cognitive_capacity: float = 0.80,
    energy_level: EnergyLevel = EnergyLevel.HIGH,
    learning_effectiveness: float = 0.70,
    productivity_score: float = 0.70,
) -> OptimizedTimeSlot:
    """Build a real one-hour OptimizedTimeSlot on TARGET_DATE."""
    start = datetime.combine(TARGET_DATE, time(hour, 0))
    return OptimizedTimeSlot(
        start_time=start,
        end_time=start + timedelta(hours=1),
        energy_level=energy_level,
        cognitive_capacity=cognitive_capacity,
        domain_affinity=None,
        interruption_risk=0.3,
        learning_effectiveness=learning_effectiveness,
        productivity_score=productivity_score,
    )


def make_load(total_load: float) -> CognitiveLoadAnalysis:
    """Build a CognitiveLoadAnalysis with an explicit total load."""
    return CognitiveLoadAnalysis(
        intrinsic_load=0.3,
        extraneous_load=0.1,
        germane_load=0.2,
        total_load=total_load,
        domain_complexity=0.5,
        prerequisite_load=0.0,
    )


class TestCognitiveLoadAnalysisPredicates:
    """Dataclass predicates on CognitiveLoadAnalysis."""

    def test_is_overload_risk_boundary_exactly_08_is_false(self) -> None:
        assert make_load(0.8).is_overload_risk() is False

    def test_is_overload_risk_above_boundary_is_true(self) -> None:
        assert make_load(0.81).is_overload_risk() is True

    def test_load_category_boundaries_are_inclusive_lower_bucket(self) -> None:
        assert make_load(0.0).get_load_category() == "light"
        assert make_load(0.3).get_load_category() == "light"
        assert make_load(0.31).get_load_category() == "moderate"
        assert make_load(0.6).get_load_category() == "moderate"
        assert make_load(0.61).get_load_category() == "heavy"
        assert make_load(0.8).get_load_category() == "heavy"
        assert make_load(0.81).get_load_category() == "overload"

    def test_to_dict_includes_raw_and_derived_fields(self) -> None:
        analysis = make_load(0.9)
        payload = analysis.to_dict()
        assert payload["intrinsic_load"] == pytest.approx(0.3)
        assert payload["extraneous_load"] == pytest.approx(0.1)
        assert payload["germane_load"] == pytest.approx(0.2)
        assert payload["total_load"] == pytest.approx(0.9)
        assert payload["domain_complexity"] == pytest.approx(0.5)
        assert payload["prerequisite_load"] == pytest.approx(0.0)
        assert payload["is_overload_risk"] is True
        assert payload["load_category"] == "overload"


class TestDurationHelpers:
    """duration_minutes on OptimizedTimeSlot and LearningSession."""

    def test_time_slot_duration_minutes(self) -> None:
        slot = make_slot(9)
        assert slot.duration_minutes() == 60

    def test_learning_session_duration_minutes(self) -> None:
        start = datetime.combine(TARGET_DATE, time(9, 0))
        session = LearningSession(
            session_id="session_test_0",
            start_time=start,
            end_time=start + timedelta(minutes=90),
            knowledge_units=["ku_alpha_1"],
            primary_domain=Domain.TECH,
            session_type="deep_focus",
            cognitive_load=make_load(0.6),
            prerequisites_covered=[],
            learning_objectives=["Master alpha"],
            recommended_breaks=[25, 55],
            spaced_repetition_items=[],
        )
        assert session.duration_minutes() == 90


class TestUserEnergyProfile:
    """_get_user_energy_profile returns the deterministic hardcoded profile."""

    def test_profile_is_deterministic_morning_chronotype(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        assert profile.peak_hours == [9, 10, 11]
        assert profile.high_hours == [8, 12, 14, 15]
        assert profile.medium_hours == [7, 13, 16, 17]
        assert profile.low_hours == [18, 19, 20]
        assert profile.depleted_hours == [21, 22, 23, 0, 1, 2, 3, 4, 5, 6]
        assert profile.chronotype == "morning"
        assert profile.focus_duration_minutes == 90


class TestAnalyzeExistingCommitments:
    """_analyze_existing_commitments filtering and defaulting."""

    def test_event_on_target_date_produces_commitment(
        self, service: CalendarOptimizationService
    ) -> None:
        event = make_event(
            "event_meeting_1",
            event_date=TARGET_DATE,
            start_time=time(10, 0),
            end_time=time(11, 30),
        )
        commitments = service._analyze_existing_commitments([event], TARGET_DATE)
        assert commitments == [
            (
                datetime.combine(TARGET_DATE, time(10, 0)),
                datetime.combine(TARGET_DATE, time(11, 30)),
            )
        ]

    def test_missing_start_time_defaults_to_nine_am(
        self, service: CalendarOptimizationService
    ) -> None:
        event = make_event("event_no_start_1", event_date=TARGET_DATE, end_time=time(10, 0))
        commitments = service._analyze_existing_commitments([event], TARGET_DATE)
        assert commitments[0][0] == datetime.combine(TARGET_DATE, time(9, 0))
        assert commitments[0][1] == datetime.combine(TARGET_DATE, time(10, 0))

    def test_missing_end_time_defaults_to_one_hour_duration(
        self, service: CalendarOptimizationService
    ) -> None:
        event = make_event("event_no_end_1", event_date=TARGET_DATE, start_time=time(14, 0))
        commitments = service._analyze_existing_commitments([event], TARGET_DATE)
        assert commitments[0][1] - commitments[0][0] == timedelta(hours=1)

    def test_events_on_other_dates_are_excluded(self, service: CalendarOptimizationService) -> None:
        event = make_event(
            "event_other_day_1",
            event_date=TARGET_DATE + timedelta(days=1),
            start_time=time(10, 0),
        )
        assert service._analyze_existing_commitments([event], TARGET_DATE) == []

    def test_no_events_yields_empty_list(self, service: CalendarOptimizationService) -> None:
        assert service._analyze_existing_commitments([], TARGET_DATE) == []


class TestGenerateAvailableSlots:
    """_generate_available_slots slot layout and conflict removal."""

    def test_no_commitments_yields_sixteen_hourly_slots(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        assert len(slots) == 16
        assert [slot.start_time.hour for slot in slots] == list(range(7, 23))
        for slot in slots:
            assert slot.duration_minutes() == 60

    def test_overlapping_commitment_removes_only_its_slot(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        commitment = (
            datetime.combine(TARGET_DATE, time(10, 0)),
            datetime.combine(TARGET_DATE, time(11, 0)),
        )
        slots = service._generate_available_slots(TARGET_DATE, [commitment], profile)
        hours = [slot.start_time.hour for slot in slots]
        assert len(slots) == 15
        assert 10 not in hours
        assert 9 in hours
        assert 11 in hours

    def test_back_to_back_commitments_do_not_over_remove(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        commitments = [
            (
                datetime.combine(TARGET_DATE, time(9, 0)),
                datetime.combine(TARGET_DATE, time(10, 0)),
            ),
            (
                datetime.combine(TARGET_DATE, time(10, 0)),
                datetime.combine(TARGET_DATE, time(11, 0)),
            ),
        ]
        slots = service._generate_available_slots(TARGET_DATE, commitments, profile)
        hours = [slot.start_time.hour for slot in slots]
        assert len(slots) == 14
        assert 9 not in hours
        assert 10 not in hours
        assert 8 in hours
        assert 11 in hours


class TestHourlyHeuristics:
    """Energy level, capacity, interruption risk, effectiveness, productivity."""

    def test_determine_energy_level_membership(self, service: CalendarOptimizationService) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        assert service._determine_energy_level(9, profile) == EnergyLevel.PEAK
        assert service._determine_energy_level(8, profile) == EnergyLevel.HIGH
        assert service._determine_energy_level(13, profile) == EnergyLevel.MEDIUM
        assert service._determine_energy_level(19, profile) == EnergyLevel.LOW

    def test_determine_energy_level_depleted_fallthrough(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        assert service._determine_energy_level(23, profile) == EnergyLevel.DEPLETED
        assert service._determine_energy_level(3, profile) == EnergyLevel.DEPLETED

    def test_cognitive_capacity_map(self, service: CalendarOptimizationService) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        assert service._calculate_cognitive_capacity(9, profile) == pytest.approx(0.95)
        assert service._calculate_cognitive_capacity(8, profile) == pytest.approx(0.80)
        assert service._calculate_cognitive_capacity(13, profile) == pytest.approx(0.60)
        assert service._calculate_cognitive_capacity(19, profile) == pytest.approx(0.40)
        assert service._calculate_cognitive_capacity(23, profile) == pytest.approx(0.20)

    def test_interruption_risk_business_hours_branch_wins(
        self, service: CalendarOptimizationService
    ) -> None:
        # Hours 9 and 17 satisfy both the 9-17 branch and the shoulder
        # branch; the 9-17 branch is checked first, so both return 0.6.
        assert service._calculate_interruption_risk(9) == pytest.approx(0.6)
        assert service._calculate_interruption_risk(17) == pytest.approx(0.6)
        assert service._calculate_interruption_risk(8) == pytest.approx(0.3)
        assert service._calculate_interruption_risk(18) == pytest.approx(0.3)
        assert service._calculate_interruption_risk(22) == pytest.approx(0.1)

    def test_learning_effectiveness_is_energy_times_time_factor(
        self, service: CalendarOptimizationService
    ) -> None:
        # Hour 9 at PEAK: 0.95 energy factor x 0.95 time factor.
        peak_morning = service._calculate_learning_effectiveness(9, EnergyLevel.PEAK)
        assert peak_morning == pytest.approx(0.95 * 0.95)
        # Hour 16 at MEDIUM: 0.65 energy factor x 0.80 afternoon time factor.
        medium_afternoon = service._calculate_learning_effectiveness(16, EnergyLevel.MEDIUM)
        assert medium_afternoon == pytest.approx(0.65 * 0.80)

    def test_productivity_score_weights(self, service: CalendarOptimizationService) -> None:
        # Hour 10, PEAK, capacity 0.95:
        # 0.95*0.4 + (1 - 0.6)*0.3 + (0.95*0.95)*0.3
        score = service._calculate_productivity_score(10, EnergyLevel.PEAK, 0.95)
        expected = 0.95 * 0.4 + 0.4 * 0.3 + (0.95 * 0.95) * 0.3
        assert score == pytest.approx(expected)


class TestTaskCognitiveLoadAnalysis:
    """_analyze_task_cognitive_load components and clamping."""

    def test_default_task_baseline_loads(self, service: CalendarOptimizationService) -> None:
        task = make_task("task_plain_1")
        analysis = service._analyze_task_cognitive_load(task, [])
        assert analysis.intrinsic_load == pytest.approx(0.3)
        assert analysis.extraneous_load == pytest.approx(0.1)
        assert analysis.germane_load == pytest.approx(0.2)
        assert analysis.prerequisite_load == pytest.approx(0.0)
        assert analysis.total_load == pytest.approx(0.6)

    def test_maxed_task_components_and_total_clamped_at_one(
        self, service: CalendarOptimizationService
    ) -> None:
        task = make_task(
            "task_maxed_1",
            knowledge_mastery_check=True,
            priority=Priority.HIGH,
            project="skuel",
        )
        analysis = service._analyze_task_cognitive_load(task, [])
        assert analysis.intrinsic_load == pytest.approx(0.7)  # 0.3 + 0.2 + 0.2
        assert analysis.extraneous_load == pytest.approx(0.2)  # 0.1 + 0.1
        assert analysis.germane_load == pytest.approx(0.5)  # 0.2 + 0.3
        # Raw sum is 1.4 — clamped to 1.0.
        assert analysis.total_load == pytest.approx(1.0)

    def test_critical_priority_gets_same_intrinsic_boost_as_high(
        self, service: CalendarOptimizationService
    ) -> None:
        task = make_task("task_critical_load_1", priority=Priority.CRITICAL)
        analysis = service._analyze_task_cognitive_load(task, [])
        assert analysis.intrinsic_load == pytest.approx(0.5)  # 0.3 + 0.2

    def test_domain_complexity_map_and_default(self, service: CalendarOptimizationService) -> None:
        assert service._calculate_domain_complexity(Domain.TECH) == pytest.approx(0.8)
        assert service._calculate_domain_complexity(Domain.CREATIVE) == pytest.approx(0.6)
        assert service._calculate_domain_complexity(Domain.BUSINESS) == pytest.approx(0.5)
        assert service._calculate_domain_complexity(Domain.HEALTH) == pytest.approx(0.4)
        assert service._calculate_domain_complexity(Domain.PERSONAL) == pytest.approx(0.3)
        # Unmapped domains fall back to 0.5.
        assert service._calculate_domain_complexity(Domain.TASKS) == pytest.approx(0.5)

    def test_domain_complexity_flows_from_task_domain(
        self, service: CalendarOptimizationService
    ) -> None:
        task = make_task("task_tech_1", domain=Domain.TECH)
        analysis = service._analyze_task_cognitive_load(task, [])
        assert analysis.domain_complexity == pytest.approx(0.8)


class TestCognitiveMatchScore:
    """_calculate_cognitive_match_score buffer branches."""

    def test_sweet_spot_buffer(self, service: CalendarOptimizationService) -> None:
        slot = make_slot(9, cognitive_capacity=0.8)
        assert service._calculate_cognitive_match_score(slot, make_load(0.6)) == pytest.approx(0.9)

    def test_good_match_buffer(self, service: CalendarOptimizationService) -> None:
        # Buffer 0.45 falls outside the 0.1-0.3 sweet spot but inside 0-0.5.
        slot = make_slot(9, cognitive_capacity=0.95)
        assert service._calculate_cognitive_match_score(slot, make_load(0.5)) == pytest.approx(0.7)

    def test_underutilized_buffer(self, service: CalendarOptimizationService) -> None:
        slot = make_slot(9, cognitive_capacity=0.95)
        assert service._calculate_cognitive_match_score(slot, make_load(0.1)) == pytest.approx(0.5)

    def test_overloaded_negative_buffer(self, service: CalendarOptimizationService) -> None:
        slot = make_slot(9, cognitive_capacity=0.4)
        assert service._calculate_cognitive_match_score(slot, make_load(0.9)) == pytest.approx(0.2)

    def test_missing_load_returns_neutral_score(self, service: CalendarOptimizationService) -> None:
        slot = make_slot(9)
        assert service._calculate_cognitive_match_score(slot, None) == pytest.approx(0.5)


class TestCognitiveBalancedStrategy:
    """_apply_cognitive_balanced_strategy assignment and metrics."""

    def test_highest_load_task_gets_highest_capacity_slot(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        heavy = make_task(
            "task_heavy_1",
            knowledge_mastery_check=True,
            priority=Priority.HIGH,
            project="skuel",
        )
        light = make_task("task_light_1")
        task_loads = {
            heavy.uid: service._analyze_task_cognitive_load(heavy, []),
            light.uid: service._analyze_task_cognitive_load(light, []),
        }
        result = service._apply_cognitive_balanced_strategy(slots, [heavy, light], task_loads)

        assert result["strategy"] == "cognitive_balanced"
        # First PEAK slot (hour 9, capacity 0.95) goes to the heaviest task.
        heavy_slot = result["schedule"][heavy.uid]["slot"]
        assert heavy_slot.start_time.hour == 9
        assert heavy_slot.cognitive_capacity == pytest.approx(0.95)
        assert result["utilization"] == pytest.approx(2 / 16)
        # Heavy: buffer 0.95-1.0 < 0 -> 0.2; light: buffer 0.35 -> 0.7.
        assert result["schedule"][heavy.uid]["match_score"] == pytest.approx(0.2)
        assert result["schedule"][light.uid]["match_score"] == pytest.approx(0.7)
        assert result["average_match_score"] == pytest.approx(0.45)

    def test_empty_slots_yield_zero_utilization(self, service: CalendarOptimizationService) -> None:
        task = make_task("task_unschedulable_1")
        result = service._apply_cognitive_balanced_strategy([], [task], {})
        assert result["schedule"] == {}
        assert result["utilization"] == 0
        assert result["average_match_score"] == pytest.approx(0.0)


class TestEnergyAlignedStrategy:
    """_apply_energy_aligned_strategy bucket assignment."""

    def test_priority_buckets_land_in_matching_energy_slots(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        high = make_task("task_high_1", priority=Priority.HIGH)
        mastery = make_task("task_mastery_1", knowledge_mastery_check=True)
        medium = make_task("task_medium_1", priority=Priority.MEDIUM)
        low = make_task("task_low_1", priority=Priority.LOW)
        tasks = [high, mastery, medium, low]

        result = service._apply_energy_aligned_strategy(slots, tasks, profile)
        schedule = result["schedule"]

        assert result["strategy"] == "energy_aligned"
        # HIGH-priority and mastery tasks land in PEAK/HIGH slots.
        for uid in (high.uid, mastery.uid):
            assert schedule[uid]["energy_match"] == "optimal"
            assert schedule[uid]["slot"].energy_level in (EnergyLevel.PEAK, EnergyLevel.HIGH)
        assert schedule[medium.uid]["energy_match"] == "good"
        assert schedule[medium.uid]["slot"].energy_level == EnergyLevel.MEDIUM
        assert schedule[low.uid]["energy_match"] == "adequate"
        assert schedule[low.uid]["slot"].energy_level == EnergyLevel.LOW
        # 2 optimal out of 4 scheduled.
        assert result["energy_efficiency"] == pytest.approx(0.5)

    def test_critical_priority_tasks_get_peak_slots_ahead_of_high(
        self, service: CalendarOptimizationService
    ) -> None:
        # CRITICAL joins the high-energy bucket and is seated before HIGH,
        # so the most urgent task claims the first peak slot.
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        high = make_task("task_high_1", priority=Priority.HIGH)
        critical = make_task("task_critical_1", priority=Priority.CRITICAL)

        result = service._apply_energy_aligned_strategy(slots, [high, critical], profile)
        schedule = result["schedule"]

        for uid in (critical.uid, high.uid):
            assert schedule[uid]["energy_match"] == "optimal"
            assert schedule[uid]["slot"].energy_level in (EnergyLevel.PEAK, EnergyLevel.HIGH)
        # CRITICAL is seated first even though it was listed after HIGH.
        assert schedule[critical.uid]["slot"].start_time < schedule[high.uid]["slot"].start_time
        assert result["energy_efficiency"] == pytest.approx(1.0)


class TestKnowledgeFocusedStrategy:
    """_apply_knowledge_focused_strategy learning-first assignment."""

    def test_mastery_tasks_get_top_learning_effectiveness_slots(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        learner = make_task("task_learner_1", knowledge_mastery_check=True)
        chore = make_task("task_chore_1")

        result = service._apply_knowledge_focused_strategy(slots, [learner, chore], [])
        schedule = result["schedule"]

        assert result["strategy"] == "knowledge_focused"
        assert schedule[learner.uid]["task_type"] == "learning"
        assert schedule[chore.uid]["task_type"] == "other"
        # Best slot is a PEAK morning hour: 0.95 * 0.95 effectiveness.
        assert schedule[learner.uid]["learning_effectiveness"] == pytest.approx(0.95 * 0.95)
        best_effectiveness = max(slot.learning_effectiveness for slot in slots)
        assert schedule[learner.uid]["learning_effectiveness"] == pytest.approx(best_effectiveness)
        # The other task gets a remaining slot, never a better one.
        assert (
            schedule[chore.uid]["learning_effectiveness"]
            <= schedule[learner.uid]["learning_effectiveness"]
        )


class TestDeadlineDrivenStrategy:
    """_apply_deadline_driven_strategy urgency ordering."""

    def test_earliest_due_date_scheduled_first_none_sorts_last(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        urgent = make_task("task_urgent_1", due_date=TARGET_DATE + timedelta(days=1))
        later = make_task("task_later_1", due_date=TARGET_DATE + timedelta(days=7))
        undated = make_task("task_undated_1")

        result = service._apply_deadline_driven_strategy(slots, [undated, later, urgent])
        schedule = result["schedule"]

        assert result["strategy"] == "deadline_driven"
        assert schedule[urgent.uid]["urgency_rank"] == 1
        assert schedule[later.uid]["urgency_rank"] == 2
        assert schedule[undated.uid]["urgency_rank"] == 3
        # Most urgent task gets the most productive slot.
        best_productivity = max(slot.productivity_score for slot in slots)
        assert schedule[urgent.uid]["productivity_score"] == pytest.approx(best_productivity)
        assert result["deadline_coverage"] == pytest.approx(2 / 3)

    def test_empty_tasks_yield_zero_coverage(self, service: CalendarOptimizationService) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        result = service._apply_deadline_driven_strategy(slots, [])
        assert result["schedule"] == {}
        assert result["deadline_coverage"] == 0


class TestSpacedRepetitionStrategy:
    """_apply_spaced_repetition_strategy spacing behavior."""

    def test_review_tasks_are_spaced_across_slots(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        reviews = [
            make_task("task_review_1", knowledge_mastery_check=True),
            make_task("task_review_2", knowledge_mastery_check=True),
            make_task("task_review_3", knowledge_mastery_check=True),
        ]

        result = service._apply_spaced_repetition_strategy(slots, reviews, [])
        schedule = result["schedule"]

        assert result["strategy"] == "spaced_repetition"
        # 16 slots / 3 tasks -> interval 5; slots[::5] = hours 7, 12, 17, 22.
        assert len(schedule) == 3
        scheduled_hours = [schedule[task.uid]["slot"].start_time.hour for task in reviews]
        assert scheduled_hours == [7, 12, 17]
        for task in reviews:
            assert schedule[task.uid]["spacing_interval"] == 5
            assert schedule[task.uid]["task_type"] == "spaced_repetition"
        assert result["spacing_quality"] == pytest.approx(5 / 16)

    def test_no_review_tasks_yields_empty_schedule(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        non_review = make_task("task_non_review_1")
        result = service._apply_spaced_repetition_strategy(slots, [non_review], [])
        assert result == {"strategy": "spaced_repetition", "schedule": {}, "spacing_quality": 0}

    def test_no_slots_yields_empty_schedule(self, service: CalendarOptimizationService) -> None:
        review = make_task("task_review_slotless_1", knowledge_mastery_check=True)
        result = service._apply_spaced_repetition_strategy([], [review], [])
        assert result == {"strategy": "spaced_repetition", "schedule": {}, "spacing_quality": 0}


class TestStrategyDispatch:
    """_apply_optimization_strategy routing and fallback."""

    def test_each_strategy_dispatches_to_matching_result(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        task = make_task("task_dispatch_1", priority=Priority.HIGH)
        task_loads = {task.uid: service._analyze_task_cognitive_load(task, [])}
        expected = {
            SchedulingStrategy.COGNITIVE_BALANCED: "cognitive_balanced",
            SchedulingStrategy.ENERGY_ALIGNED: "energy_aligned",
            SchedulingStrategy.KNOWLEDGE_FOCUSED: "knowledge_focused",
            SchedulingStrategy.DEADLINE_DRIVEN: "deadline_driven",
            SchedulingStrategy.SPACED_REPETITION: "spaced_repetition",
        }
        for strategy, name in expected.items():
            result = service._apply_optimization_strategy(
                strategy, slots, [task], task_loads, [], profile
            )
            assert result["strategy"] == name

    def test_unknown_strategy_falls_back_to_cognitive_balanced(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        slots = service._generate_available_slots(TARGET_DATE, [], profile)
        task = make_task("task_fallback_1")
        task_loads = {task.uid: service._analyze_task_cognitive_load(task, [])}
        # A value outside the enum exercises the defensive else branch.
        result = service._apply_optimization_strategy(
            "not_a_strategy",  # type: ignore[arg-type]
            slots,
            [task],
            task_loads,
            [],
            profile,
        )
        assert result["strategy"] == "cognitive_balanced"


class TestScoreCalculations:
    """Score helpers: efficiency, distribution, alignment, progression, balance."""

    def test_energy_efficiency_empty_schedule_is_zero(
        self, service: CalendarOptimizationService
    ) -> None:
        assert service._calculate_energy_efficiency({}) == pytest.approx(0.0)

    def test_energy_efficiency_counts_optimal_matches(
        self, service: CalendarOptimizationService
    ) -> None:
        schedule = {
            "task_a_1": {"slot": make_slot(9), "energy_match": "optimal"},
            "task_b_1": {"slot": make_slot(13), "energy_match": "good"},
        }
        assert service._calculate_energy_efficiency(schedule) == pytest.approx(0.5)

    def test_load_distribution_empty_schedule_is_empty(
        self, service: CalendarOptimizationService
    ) -> None:
        optimization = {
            "strategy": "cognitive_balanced",
            "schedule": {},
            "utilization": 0,
            "average_match_score": 0.0,
        }
        assert service._calculate_load_distribution(optimization, {}) == {}

    def test_load_distribution_sums_loads_per_hour(
        self, service: CalendarOptimizationService
    ) -> None:
        slot_nine = make_slot(9)
        optimization = {
            "strategy": "cognitive_balanced",
            "schedule": {
                "task_a_1": {"slot": slot_nine},
                "task_b_1": {"slot": slot_nine},
                "task_c_1": {"slot": make_slot(14)},
            },
            "utilization": 0.2,
            "average_match_score": 0.5,
        }
        task_loads = {
            "task_a_1": make_load(0.6),
            "task_b_1": make_load(0.4),
            "task_c_1": make_load(0.5),
        }
        distribution = service._calculate_load_distribution(optimization, task_loads)
        assert distribution[9] == pytest.approx(1.0)
        assert distribution[14] == pytest.approx(0.5)

    def test_energy_alignment_empty_schedule_is_zero(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        optimization = {"strategy": "energy_aligned", "schedule": {}, "energy_efficiency": 0.0}
        assert service._calculate_energy_alignment_score(optimization, profile) == pytest.approx(
            0.0
        )

    def test_energy_alignment_scores_by_energy_level(
        self, service: CalendarOptimizationService
    ) -> None:
        profile = service._get_user_energy_profile(USER_UID)
        # Hour 9 is PEAK (1.0), hour 19 is LOW (0.4) -> mean 0.7.
        optimization = {
            "strategy": "energy_aligned",
            "schedule": {
                "task_peak_1": {"slot": make_slot(9)},
                "task_low_1": {"slot": make_slot(19)},
            },
            "energy_efficiency": 0.5,
        }
        score = service._calculate_energy_alignment_score(optimization, profile)
        assert score == pytest.approx(0.7)

    def test_knowledge_progression_empty_sessions_is_zero(
        self, service: CalendarOptimizationService
    ) -> None:
        assert service._calculate_knowledge_progression_score([]) == pytest.approx(0.0)

    def test_knowledge_progression_single_deep_focus_session(
        self, service: CalendarOptimizationService
    ) -> None:
        start = datetime.combine(TARGET_DATE, time(9, 0))
        session = LearningSession(
            session_id="session_tech_0",
            start_time=start,
            end_time=start + timedelta(hours=1),
            knowledge_units=["ku_alpha_1"],
            primary_domain=Domain.TECH,
            session_type="deep_focus",
            cognitive_load=make_load(0.6),
            prerequisites_covered=[],
            learning_objectives=[],
            recommended_breaks=[30],
            spaced_repetition_items=[],
        )
        # (1/5 domain diversity + 1/3 frequency + 1.0 deep ratio) / 3
        score = service._calculate_knowledge_progression_score([session])
        assert score == pytest.approx((1 / 5 + 1 / 3 + 1.0) / 3)

    def test_cognitive_balance_empty_distribution_is_zero(
        self, service: CalendarOptimizationService
    ) -> None:
        optimization = {
            "strategy": "cognitive_balanced",
            "schedule": {},
            "utilization": 0,
            "average_match_score": 0.0,
        }
        assert service._calculate_cognitive_balance_score({}, optimization) == pytest.approx(0.0)

    def test_cognitive_balance_perfectly_even_load_is_one(
        self, service: CalendarOptimizationService
    ) -> None:
        optimization = {
            "strategy": "cognitive_balanced",
            "schedule": {
                "task_a_1": {"slot": make_slot(9)},
                "task_b_1": {"slot": make_slot(14)},
            },
            "utilization": 0.125,
            "average_match_score": 0.7,
        }
        task_loads = {"task_a_1": make_load(0.5), "task_b_1": make_load(0.5)}
        score = service._calculate_cognitive_balance_score(task_loads, optimization)
        assert score == pytest.approx(1.0)

    def test_cognitive_balance_is_clamped_at_zero_for_high_variance(
        self, service: CalendarOptimizationService
    ) -> None:
        slot_nine = make_slot(9)
        optimization = {
            "strategy": "cognitive_balanced",
            "schedule": {
                "task_a_1": {"slot": slot_nine},
                "task_b_1": {"slot": slot_nine},
                "task_c_1": {"slot": slot_nine},
                "task_d_1": {"slot": make_slot(14)},
            },
            "utilization": 0.25,
            "average_match_score": 0.5,
        }
        # Hour 9 accumulates 3.0 load, hour 14 gets 0.01:
        # variance ~2.235 -> 1 - variance < 0 -> clamped to 0.0.
        task_loads = {
            "task_a_1": make_load(1.0),
            "task_b_1": make_load(1.0),
            "task_c_1": make_load(1.0),
            "task_d_1": make_load(0.01),
        }
        score = service._calculate_cognitive_balance_score(task_loads, optimization)
        assert score == pytest.approx(0.0)


class TestOptimizeKnowledgeSchedulingEndToEnd:
    """Full optimize_knowledge_scheduling run with real DTOs."""

    def test_end_to_end_returns_complete_optimization(
        self, service: CalendarOptimizationService
    ) -> None:
        tasks = [
            make_task(
                "task_e2e_learn_1",
                knowledge_mastery_check=True,
                priority=Priority.HIGH,
                due_date=TARGET_DATE + timedelta(days=2),
            ),
            make_task("task_e2e_admin_1", priority=Priority.MEDIUM, project="skuel"),
            make_task("task_e2e_errand_1", priority=Priority.LOW),
        ]
        events = [
            make_event(
                "event_e2e_standup_1",
                event_date=TARGET_DATE,
                start_time=time(10, 0),
                end_time=time(11, 0),
            )
        ]
        knowledge_units = [
            CurriculumDTO(
                uid="ps_e2e_graphs_1",
                title="Graph Theory Basics",
                entity_type=EntityType.PATH_STEP,
            ),
            CurriculumDTO(
                uid="ps_e2e_cypher_1",
                title="Cypher Fundamentals",
                entity_type=EntityType.PATH_STEP,
            ),
        ]

        result = service.optimize_knowledge_scheduling(
            user_uid=USER_UID,
            target_date=TARGET_DATE,
            tasks=tasks,
            events=events,
            knowledge_units=knowledge_units,
            strategy=SchedulingStrategy.COGNITIVE_BALANCED,
        )

        assert result.is_ok
        optimization = result.value
        assert optimization.optimization_date == TARGET_DATE
        assert optimization.strategy == SchedulingStrategy.COGNITIVE_BALANCED
        # The 10:00 standup removes exactly one of the 16 hourly slots.
        assert len(optimization.optimized_slots) == 15
        # All three tasks contribute load and land in the distribution.
        assert optimization.total_cognitive_load > 0
        assert optimization.load_distribution
        assert optimization.learning_sessions
        assert optimization.scheduling_recommendations
        for score in (
            optimization.energy_alignment_score,
            optimization.knowledge_progression_score,
            optimization.cognitive_balance_score,
        ):
            assert 0.0 <= score <= 1.0
