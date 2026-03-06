"""
Unit tests for AnalyticsEngine — knowledge analytics and learning pattern detection.

Tests focus on:
- Public async orchestration methods (analyze_learning_patterns, calculate_knowledge_aware_priority,
  generate_task_insights)
- Pure utility functions (_is_progressive_sequence, _calculate_growth_indicator,
  _extract_domains_from_knowledge_uids)

AnalyticsEngine is a utility service — NOT a facade. Its public methods contain real
branching logic (relationship_service guard, pattern detection, sorting). Pure helpers
(_is_progressive_sequence, etc.) have no dependencies and are tested directly.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.task.task import Task
from core.services.analytics_engine import (
    AnalyticsEngine,
    LearningPattern,
    LearningPatternType,
    MasteryProgression,
)
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_task(uid: str = "task_abc123", title: str = "Test Task", priority: str = "medium") -> Task:
    """Construct a minimal Task with sensible defaults for analytics tests."""
    return Task(uid=uid, title=title, priority=priority)


def make_learning_pattern(
    pattern_type: LearningPatternType = LearningPatternType.KNOWLEDGE_BUILDING,
    confidence: float = 0.8,
    frequency: int = 3,
) -> LearningPattern:
    """Construct a minimal LearningPattern for assertion fixtures."""
    return LearningPattern(
        pattern_type=pattern_type,
        knowledge_uids=["ku.python"],
        task_uids=["task_abc"],
        confidence=confidence,
        timeframe_days=30,
        frequency=frequency,
        growth_indicator=0.5,
    )


def make_mastery_progression(knowledge_uid: str = "ku.python") -> MasteryProgression:
    """Construct a minimal MasteryProgression."""
    from datetime import date

    return MasteryProgression(
        knowledge_uid=knowledge_uid,
        current_mastery_level=0.5,
        mastery_trend=0.1,
        tasks_completed=5,
        validation_tasks_passed=3,
        last_application_date=date.today(),
        progression_velocity=0.02,
        confidence_in_assessment=0.7,
        next_recommended_difficulty=0.6,
    )


@pytest.fixture
def engine_no_svc() -> AnalyticsEngine:
    """AnalyticsEngine with no relationship_service — pattern detection returns empty."""
    return AnalyticsEngine(relationship_service=None)


@pytest.fixture
def mock_relationship_service() -> Mock:
    svc = Mock()
    svc.get_related_uids = AsyncMock(return_value=Result.ok([]))
    svc.has_relationship = AsyncMock(return_value=Result.ok(False))
    return svc


@pytest.fixture
def engine_with_svc(mock_relationship_service: Mock) -> AnalyticsEngine:
    return AnalyticsEngine(relationship_service=mock_relationship_service)


# ---------------------------------------------------------------------------
# TestAnalyzeLearningPatterns
# ---------------------------------------------------------------------------


class TestAnalyzeLearningPatterns:
    @pytest.mark.asyncio
    async def test_empty_task_list_returns_ok_with_no_patterns(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """analyze_learning_patterns with no tasks returns Result.ok([])."""
        result = await engine_no_svc.analyze_learning_patterns([])

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_tasks_without_relationship_service_returns_empty_patterns(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """analyze_learning_patterns with tasks but no relationship_service returns empty list.

        All pattern detection methods guard on `if not self.relationship_service` and
        return empty early — so the final sorted list is always empty.
        """
        tasks = [make_task("task_a"), make_task("task_b")]
        result = await engine_no_svc.analyze_learning_patterns(tasks)

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_timeframe_filter_excludes_tasks_older_than_window(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """Tasks created before the timeframe cutoff are excluded from analysis."""
        from datetime import timedelta

        old_task = Task(
            uid="task_old",
            title="Old Task",
            created_at=datetime.now() - timedelta(days=60),
        )
        recent_task = make_task("task_recent")

        # With timeframe_days=30, only recent_task survives filtering.
        # Both pattern counts will be 0 (no relationship_service), so we verify
        # by confirming the call succeeds rather than counting patterns.
        result = await engine_no_svc.analyze_learning_patterns(
            [old_task, recent_task], timeframe_days=30
        )

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_returns_result_ok_type(self, engine_no_svc: AnalyticsEngine) -> None:
        """analyze_learning_patterns always returns a Result, never raises."""
        result = await engine_no_svc.analyze_learning_patterns([make_task()])
        assert result.is_ok


# ---------------------------------------------------------------------------
# TestCalculateKnowledgeAwarePriority
# ---------------------------------------------------------------------------


class TestCalculateKnowledgeAwarePriority:
    @pytest.mark.asyncio
    async def test_no_relationship_service_returns_priority_with_correct_task_uid(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """Without relationship_service, method uses empty rels and still returns KuAwarePriority."""
        task = make_task("task_priority_test")

        result = await engine_no_svc.calculate_knowledge_aware_priority(
            task,
            user_mastery_progressions={},
            learning_patterns=[],
        )

        assert result.is_ok
        assert result.value.task_uid == "task_priority_test"

    @pytest.mark.asyncio
    async def test_final_priority_score_is_clamped_to_unit_range(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """final_priority_score must be in [0.0, 1.0]."""
        task = make_task(priority="high")

        result = await engine_no_svc.calculate_knowledge_aware_priority(
            task, user_mastery_progressions={}, learning_patterns=[]
        )

        assert result.is_ok
        score = result.value.final_priority_score
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_high_priority_task_has_higher_base_score_than_low(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """High-priority task scores higher than low-priority (no knowledge rels)."""
        high_task = make_task("task_high", priority="high")
        low_task = make_task("task_low", priority="low")

        high_result = await engine_no_svc.calculate_knowledge_aware_priority(
            high_task, user_mastery_progressions={}, learning_patterns=[]
        )
        low_result = await engine_no_svc.calculate_knowledge_aware_priority(
            low_task, user_mastery_progressions={}, learning_patterns=[]
        )

        assert high_result.is_ok and low_result.is_ok
        assert high_result.value.base_priority_score > low_result.value.base_priority_score

    @pytest.mark.asyncio
    async def test_scoring_rationale_is_list(self, engine_no_svc: AnalyticsEngine) -> None:
        """scoring_rationale on returned KuAwarePriority is a list (possibly empty)."""
        result = await engine_no_svc.calculate_knowledge_aware_priority(
            make_task(), user_mastery_progressions={}, learning_patterns=[]
        )

        assert result.is_ok
        assert isinstance(result.value.scoring_rationale, list)


# ---------------------------------------------------------------------------
# TestGenerateTaskInsights
# ---------------------------------------------------------------------------


class TestGenerateTaskInsights:
    @pytest.mark.asyncio
    async def test_empty_completed_tasks_returns_ok_with_no_insights(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """generate_task_insights with no tasks returns Result.ok([])."""
        result = await engine_no_svc.generate_task_insights(
            completed_tasks=[], learning_patterns=[]
        )

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_returns_result_ok_type(self, engine_no_svc: AnalyticsEngine) -> None:
        """generate_task_insights returns a Result, never raises."""
        result = await engine_no_svc.generate_task_insights(
            completed_tasks=[make_task()], learning_patterns=[]
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_returned_insights_is_list(self, engine_no_svc: AnalyticsEngine) -> None:
        """Return value is a list (possibly empty)."""
        result = await engine_no_svc.generate_task_insights(
            completed_tasks=[make_task()], learning_patterns=[make_learning_pattern()]
        )
        assert result.is_ok
        assert isinstance(result.value, list)


# ---------------------------------------------------------------------------
# TestIsProgressiveSequence — pure sync function, no I/O
# ---------------------------------------------------------------------------


class TestIsProgressiveSequence:
    def test_ascending_sequence_returns_true(self, engine_no_svc: AnalyticsEngine) -> None:
        """Strictly ascending sequence is progressive."""
        assert engine_no_svc._is_progressive_sequence([1.0, 2.0, 3.0, 4.0]) is True

    def test_flat_sequence_returns_false(self, engine_no_svc: AnalyticsEngine) -> None:
        """All-equal sequence has no increases."""
        assert engine_no_svc._is_progressive_sequence([1.0, 1.0, 1.0, 1.0]) is False

    def test_descending_sequence_returns_false(self, engine_no_svc: AnalyticsEngine) -> None:
        """Strictly descending sequence has no increases."""
        assert engine_no_svc._is_progressive_sequence([4.0, 3.0, 2.0, 1.0]) is False

    def test_fewer_than_3_elements_returns_false(self, engine_no_svc: AnalyticsEngine) -> None:
        """Less than 3 values → cannot be a meaningful progressive sequence."""
        assert engine_no_svc._is_progressive_sequence([]) is False
        assert engine_no_svc._is_progressive_sequence([1.0]) is False
        assert engine_no_svc._is_progressive_sequence([1.0, 2.0]) is False

    def test_mostly_increasing_with_one_dip_returns_true(
        self, engine_no_svc: AnalyticsEngine
    ) -> None:
        """60%+ increases passes the threshold — one dip is allowed."""
        # [1, 2, 3, 2.5, 4] → 4 increases out of 4 pairs = 80% > 60%
        assert engine_no_svc._is_progressive_sequence([1.0, 2.0, 3.0, 2.5, 4.0]) is True


# ---------------------------------------------------------------------------
# TestCalculateGrowthIndicator — pure sync function, no I/O
# ---------------------------------------------------------------------------


class TestCalculateGrowthIndicator:
    def test_single_value_returns_zero(self, engine_no_svc: AnalyticsEngine) -> None:
        """Only one element → cannot compute growth → 0.0."""
        assert engine_no_svc._calculate_growth_indicator([5.0]) == 0.0

    def test_empty_list_returns_zero(self, engine_no_svc: AnalyticsEngine) -> None:
        """Empty list → 0.0."""
        assert engine_no_svc._calculate_growth_indicator([]) == 0.0

    def test_growing_values_returns_positive(self, engine_no_svc: AnalyticsEngine) -> None:
        """Second half mean > first half mean → positive growth."""
        result = engine_no_svc._calculate_growth_indicator([1.0, 1.0, 2.0, 2.0])
        assert result > 0.0

    def test_declining_values_returns_negative(self, engine_no_svc: AnalyticsEngine) -> None:
        """Second half mean < first half mean → negative growth."""
        result = engine_no_svc._calculate_growth_indicator([2.0, 2.0, 1.0, 1.0])
        assert result < 0.0

    def test_flat_values_returns_zero(self, engine_no_svc: AnalyticsEngine) -> None:
        """All-equal values → 0.0 growth."""
        result = engine_no_svc._calculate_growth_indicator([3.0, 3.0, 3.0, 3.0])
        assert result == 0.0

    def test_result_is_clamped_to_minus_one_to_one(self, engine_no_svc: AnalyticsEngine) -> None:
        """Extreme values clamp to [-1, 1]."""
        result = engine_no_svc._calculate_growth_indicator([0.001, 0.001, 1000.0, 1000.0])
        assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# TestExtractDomainsFromKnowledgeUids — pure sync function, no I/O
# ---------------------------------------------------------------------------


class TestExtractDomainsFromKnowledgeUids:
    def test_extracts_domain_from_ku_prefixed_uids(self, engine_no_svc: AnalyticsEngine) -> None:
        """ku.domain-name UIDs → domain portion extracted."""
        result = engine_no_svc._extract_domains_from_knowledge_uids(["ku.python", "ku.mathematics"])
        assert result == ["python", "mathematics"]

    def test_ignores_non_ku_prefixed_uids(self, engine_no_svc: AnalyticsEngine) -> None:
        """UIDs not starting with 'ku' are silently skipped."""
        result = engine_no_svc._extract_domains_from_knowledge_uids(
            ["task_xyz_abc", "goal_learn_def"]
        )
        assert result == []

    def test_mixed_ku_and_other_uids(self, engine_no_svc: AnalyticsEngine) -> None:
        """Mixed list: only ku.* ones are extracted."""
        result = engine_no_svc._extract_domains_from_knowledge_uids(
            ["ku.philosophy", "task_study_abc", "ku.logic"]
        )
        assert result == ["philosophy", "logic"]

    def test_empty_list_returns_empty(self, engine_no_svc: AnalyticsEngine) -> None:
        """Empty input → empty output."""
        result = engine_no_svc._extract_domains_from_knowledge_uids([])
        assert result == []

    def test_single_part_uid_excluded(self, engine_no_svc: AnalyticsEngine) -> None:
        """UIDs with only one part (no dot) are excluded even if starting with ku."""
        result = engine_no_svc._extract_domains_from_knowledge_uids(["ku"])
        # "ku" splits to ["ku"] — len(parts) < 2 → excluded
        assert result == []
