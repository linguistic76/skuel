"""
Curriculum Hierarchy Tests
=============================

Tests for the Curriculum intermediate class introduced in Phase 2
of the Ku decomposition. Verifies:

1. Curriculum field inheritance from Entity
2. LearningStep and LearningPath inherit from Curriculum (not Entity)
3. Substance methods work with real data (not stubs)
4. Learning methods (complexity, SEL, level) work correctly
5. DTO round-trip for Curriculum subclasses
"""

from datetime import datetime, timedelta

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.ku_enums import EntityType
from core.models.ku.curriculum import Curriculum
from core.models.ku.entity import Entity
from core.models.ku.ku_dto import KuDTO
from core.models.ku.learning_path import LearningPath
from core.models.ku.learning_step import LearningStep

# =========================================================================
# Curriculum creation and field defaults
# =========================================================================


class TestCurriculumKuCreation:
    """Test Curriculum instantiation and defaults."""

    def test_basic_creation(self):
        """Curriculum can be created with minimal fields."""
        cu = Curriculum(uid="ku_test_abc", title="Test Curriculum")
        assert cu.uid == "ku_test_abc"
        assert cu.title == "Test Curriculum"
        assert cu.ku_type == EntityType.CURRICULUM

    def test_forces_ku_type_curriculum(self):
        """__post_init__ forces ku_type=CURRICULUM."""
        cu = Curriculum(uid="ku_test", title="Test", ku_type=EntityType.TASK)
        assert cu.ku_type == EntityType.CURRICULUM

    def test_learning_field_defaults(self):
        """Learning metadata fields have correct defaults."""
        cu = Curriculum(uid="ku_test", title="Test")
        assert cu.complexity == KuComplexity.MEDIUM
        assert cu.learning_level == LearningLevel.BEGINNER
        assert cu.sel_category is None
        assert cu.quality_score == 0.0
        assert cu.estimated_time_minutes == 15
        assert cu.difficulty_rating == 0.5
        assert cu.semantic_links == ()
        assert cu.target_age_range is None
        assert cu.learning_objectives == ()

    def test_substance_counter_defaults(self):
        """Substance counters default to 0, dates to None."""
        cu = Curriculum(uid="ku_test", title="Test")
        assert cu.times_applied_in_tasks == 0
        assert cu.times_practiced_in_events == 0
        assert cu.times_built_into_habits == 0
        assert cu.journal_reflections_count == 0
        assert cu.choices_informed_count == 0
        assert cu.last_applied_date is None
        assert cu.last_practiced_date is None
        assert cu.last_built_into_habit_date is None
        assert cu.last_reflected_date is None
        assert cu.last_choice_informed_date is None

    def test_inherits_entity_fields(self):
        """Curriculum inherits Entity identity/content/status fields (no user_uid)."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            domain=Domain.TECH,
            content="Some content",
            tags=("python", "testing"),
        )
        # Curriculum is a shared type — user_uid property returns None
        assert cu.user_uid is None
        assert cu.domain == Domain.TECH
        assert cu.content == "Some content"
        assert cu.tags == ("python", "testing")
        assert cu.word_count == 2  # "Some content"


# =========================================================================
# Hierarchy: LearningStep and LearningPath inherit Curriculum
# =========================================================================


class TestCurriculumKuHierarchy:
    """Verify LearningStep and LearningPath inherit from Curriculum."""

    def test_learning_step_is_curriculum_ku(self):
        """LearningStep IS a Curriculum."""
        ls = LearningStep(uid="ls_test", title="Step 1")
        assert isinstance(ls, Curriculum)
        assert isinstance(ls, Entity)

    def test_learning_path_is_curriculum_ku(self):
        """LearningPath IS a Curriculum."""
        lp = LearningPath(uid="lp_test", title="Path 1")
        assert isinstance(lp, Curriculum)
        assert isinstance(lp, Entity)

    def test_learning_step_inherits_curriculum_fields(self):
        """LearningStep has all Curriculum fields via inheritance."""
        ls = LearningStep(
            uid="ls_test",
            title="Step",
            complexity=KuComplexity.ADVANCED,
            learning_level=LearningLevel.EXPERT,
            difficulty_rating=0.9,
            times_applied_in_tasks=3,
        )
        assert ls.complexity == KuComplexity.ADVANCED
        assert ls.learning_level == LearningLevel.EXPERT
        assert ls.difficulty_rating == 0.9
        assert ls.times_applied_in_tasks == 3

    def test_learning_path_inherits_curriculum_fields(self):
        """LearningPath has all Curriculum fields via inheritance."""
        lp = LearningPath(
            uid="lp_test",
            title="Path",
            complexity=KuComplexity.BASIC,
            estimated_time_minutes=60,
            semantic_links=("ku_a", "ku_b"),
        )
        assert lp.complexity == KuComplexity.BASIC
        assert lp.estimated_time_minutes == 60
        assert lp.semantic_links == ("ku_a", "ku_b")

    def test_learning_step_substance_score_overrides_stub(self):
        """LearningStep substance_score comes from Curriculum, not Entity stub."""
        ls = LearningStep(
            uid="ls_test",
            title="Step",
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            last_applied_date=datetime.now(),
            last_practiced_date=datetime.now(),
        )
        score = ls.substance_score()
        assert score > 0.0, "LearningStep should use Curriculum substance, not stub"


# =========================================================================
# Curriculum learning methods
# =========================================================================


class TestCurriculumKuLearningMethods:
    """Test curriculum-specific learning methods."""

    def test_is_advanced(self):
        cu = Curriculum(uid="ku_test", title="Test", complexity=KuComplexity.ADVANCED)
        assert cu.is_advanced() is True
        assert cu.is_basic() is False

    def test_is_basic(self):
        cu = Curriculum(uid="ku_test", title="Test", complexity=KuComplexity.BASIC)
        assert cu.is_basic() is True
        assert cu.is_advanced() is False

    def test_complexity_score(self):
        basic = Curriculum(uid="ku_b", title="B", complexity=KuComplexity.BASIC)
        medium = Curriculum(uid="ku_m", title="M", complexity=KuComplexity.MEDIUM)
        advanced = Curriculum(uid="ku_a", title="A", complexity=KuComplexity.ADVANCED)
        assert basic.complexity_score() == 1
        assert medium.complexity_score() == 2
        assert advanced.complexity_score() == 3

    def test_requires_prerequisites(self):
        """Advanced TECH knowledge requires prerequisites."""
        cu = Curriculum(
            uid="ku_test", title="Test", domain=Domain.TECH, complexity=KuComplexity.ADVANCED
        )
        assert cu.requires_prerequisites() is True

        # Non-TECH advanced doesn't require prerequisites
        cu2 = Curriculum(
            uid="ku_test2", title="Test2", domain=Domain.HEALTH, complexity=KuComplexity.ADVANCED
        )
        assert cu2.requires_prerequisites() is False

    def test_is_quick_win(self):
        """Short duration + low difficulty = quick win."""
        cu = Curriculum(
            uid="ku_test", title="Test", estimated_time_minutes=5, difficulty_rating=0.2
        )
        assert cu.is_quick_win() is True

        cu2 = Curriculum(
            uid="ku_test2", title="Test2", estimated_time_minutes=30, difficulty_rating=0.8
        )
        assert cu2.is_quick_win() is False

    def test_is_challenging(self):
        cu = Curriculum(uid="ku_test", title="Test", difficulty_rating=0.8)
        assert cu.is_challenging() is True

    def test_matches_time_available(self):
        cu = Curriculum(uid="ku_test", title="Test", estimated_time_minutes=15)
        assert cu.matches_time_available(20) is True
        assert cu.matches_time_available(10) is False

    def test_is_appropriate_for_level(self):
        beginner = Curriculum(uid="ku_test", title="Test", learning_level=LearningLevel.BEGINNER)
        assert beginner.is_appropriate_for_level(LearningLevel.BEGINNER) is True
        assert beginner.is_appropriate_for_level(LearningLevel.EXPERT) is True

        expert = Curriculum(uid="ku_test2", title="Test2", learning_level=LearningLevel.EXPERT)
        assert expert.is_appropriate_for_level(LearningLevel.BEGINNER) is False
        assert expert.is_appropriate_for_level(LearningLevel.EXPERT) is True


# =========================================================================
# Curriculum substance tracking
# =========================================================================


class TestCurriculumKuSubstance:
    """Test substance score calculation on Curriculum."""

    def test_zero_substance_when_no_activity(self):
        """No activity means substance score = 0."""
        cu = Curriculum(uid="ku_test", title="Test")
        assert cu.substance_score() == 0.0

    def test_substance_increases_with_activity(self):
        """Activity counters increase substance score."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=3,
            times_practiced_in_events=2,
            times_built_into_habits=1,
            last_applied_date=datetime.now(),
            last_practiced_date=datetime.now(),
            last_built_into_habit_date=datetime.now(),
        )
        score = cu.substance_score()
        assert score > 0.0

    def test_substance_capped_at_1(self):
        """Substance score cannot exceed 1.0."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=100,
            times_practiced_in_events=100,
            times_built_into_habits=100,
            journal_reflections_count=100,
            choices_informed_count=100,
            last_applied_date=datetime.now(),
            last_practiced_date=datetime.now(),
            last_built_into_habit_date=datetime.now(),
            last_reflected_date=datetime.now(),
            last_choice_informed_date=datetime.now(),
        )
        assert cu.substance_score() <= 1.0

    def test_needs_review_for_decayed_substance(self):
        """Once-substantiated knowledge with old dates needs review."""
        old_date = datetime.now() - timedelta(days=90)
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            times_built_into_habits=1,
            last_applied_date=old_date,
            last_practiced_date=old_date,
            last_built_into_habit_date=old_date,
        )
        assert cu.needs_review() is True

    def test_no_review_needed_for_fresh_substance(self):
        """Recently practiced knowledge doesn't need review."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            times_built_into_habits=1,
            last_applied_date=datetime.now(),
            last_practiced_date=datetime.now(),
            last_built_into_habit_date=datetime.now(),
        )
        assert cu.needs_review() is False

    def test_get_substantiation_gaps(self):
        """Gaps identify missing substantiation types."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=3,
            # Everything else is 0
        )
        gaps = cu.get_substantiation_gaps()
        assert "No tasks apply this knowledge" not in gaps  # tasks > 0
        assert "No events practice this knowledge" in gaps
        assert "Not built into any habits" in gaps
        assert "No journal reflections" in gaps
        assert "Has not informed any choices/decisions" in gaps

    def test_is_theoretical_only(self):
        """Substance < 0.2 = theoretical only."""
        cu = Curriculum(uid="ku_test", title="Test")
        assert cu.is_theoretical_only() is True

    def test_substance_cache_used(self):
        """Substance score uses cache on second call."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=3,
            last_applied_date=datetime.now(),
        )
        score1 = cu.substance_score()
        score2 = cu.substance_score()
        assert score1 == score2


# =========================================================================
# SEL framework integration
# =========================================================================


class TestCurriculumKuSEL:
    """Test SEL framework methods on Curriculum."""

    def test_get_sel_context_with_category(self):
        """get_sel_context returns SEL category details."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            sel_category=SELCategory.SELF_AWARENESS,
            learning_level=LearningLevel.INTERMEDIATE,
        )
        ctx = cu.get_sel_context()
        assert ctx["sel_category"] == "self_awareness"
        assert ctx["learning_level"] == "intermediate"
        assert ctx["sel_category_icon"] != ""

    def test_get_sel_context_without_category(self):
        """get_sel_context handles None sel_category."""
        cu = Curriculum(uid="ku_test", title="Test")
        ctx = cu.get_sel_context()
        assert ctx["sel_category"] is None
        assert ctx["sel_category_icon"] == ""


# =========================================================================
# DTO round-trip for Curriculum subclasses
# =========================================================================


class TestCurriculumKuSubclassDTORoundTrip:
    """Test DTO round-trip for LearningStep and LearningPath."""

    def test_learning_step_dto_round_trip(self):
        """LearningStep DTO round-trip preserves curriculum + step fields."""
        dto = KuDTO(
            uid="ls_test_abc",
            title="Learn Python Basics",
            ku_type=EntityType.LEARNING_STEP,
            complexity="advanced",
            learning_level=LearningLevel.INTERMEDIATE,
            difficulty_rating=0.7,
            times_applied_in_tasks=3,
            semantic_links=["ku_python"],
        )
        ku = Entity.from_dto(dto)
        assert isinstance(ku, LearningStep)
        assert isinstance(ku, Curriculum)
        assert ku.complexity == KuComplexity.ADVANCED
        assert ku.learning_level == LearningLevel.INTERMEDIATE
        assert ku.difficulty_rating == 0.7
        assert ku.times_applied_in_tasks == 3
        assert ku.semantic_links == ("ku_python",)

        # Round-trip back
        dto2 = ku.to_dto()
        assert dto2.complexity == "advanced"
        assert dto2.times_applied_in_tasks == 3
        assert dto2.semantic_links == ["ku_python"]

    def test_learning_path_dto_round_trip(self):
        """LearningPath DTO round-trip preserves curriculum + path fields."""
        dto = KuDTO(
            uid="lp_test_abc",
            title="Python Learning Path",
            ku_type=EntityType.LEARNING_PATH,
            complexity="basic",
            estimated_time_minutes=120,
            quality_score=0.85,
        )
        ku = Entity.from_dto(dto)
        assert isinstance(ku, LearningPath)
        assert isinstance(ku, Curriculum)
        assert ku.complexity == KuComplexity.BASIC
        assert ku.estimated_time_minutes == 120
        assert ku.quality_score == 0.85

        # Round-trip back
        dto2 = ku.to_dto()
        assert dto2.complexity == "basic"
        assert dto2.estimated_time_minutes == 120
        assert dto2.quality_score == 0.85
