"""
KU Three-Tier Round-Trip Tests
==============================

Validates that business fields survive the DTO ↔ Ku round-trip,
and that from_dict/to_dict handle enum/datetime serialization correctly.

After decomposition: curriculum-only fields (learning metadata,
substance tracking) live on Curriculum, not Entity. Tests verify
correct dispatch and field separation.
"""

from datetime import datetime, timedelta

from core.models.curriculum.curriculum import Curriculum
from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.models.entity import Entity
from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.entity_enums import EntityType
from core.models.resource.resource import Resource
from core.models.resource.resource_dto import ResourceDTO
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO

# =========================================================================
# Round-trip: DTO → Entity.from_dto() → Ku.to_dto() → all fields preserved
# =========================================================================


class TestKuThreeTierRoundTrip:
    """Test lossless DTO ↔ Ku conversion."""

    def _make_full_dto(self) -> CurriculumDTO:
        """Create a CurriculumDTO with all fields populated."""
        now = datetime.now()
        return CurriculumDTO(
            uid="ku_test_abc123",
            title="Test Knowledge",
            domain=Domain.KNOWLEDGE,
            word_count=42,
            quality_score=0.85,
            complexity="advanced",
            semantic_links=["ku_other_1", "ku_other_2"],
            created_at=now,
            updated_at=now,
            tags=["python", "testing"],
            sel_category=SELCategory.SELF_AWARENESS,
            summary="A brief summary",
            learning_level=LearningLevel.INTERMEDIATE,
            estimated_time_minutes=30,
            difficulty_rating=0.7,
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            times_built_into_habits=2,
            journal_reflections_count=4,
            choices_informed_count=1,
            last_applied_date=now - timedelta(days=2),
            last_practiced_date=now - timedelta(days=5),
            last_built_into_habit_date=now - timedelta(days=10),
            last_reflected_date=now - timedelta(days=1),
            last_choice_informed_date=now - timedelta(days=7),
        )

    def test_dto_to_ku_preserves_all_fields(self):
        """CurriculumDTO → Entity.from_dto() must carry all 26 fields."""
        dto = self._make_full_dto()
        ku = Entity.from_dto(dto)

        assert ku.uid == dto.uid
        assert ku.title == dto.title
        assert ku.domain == dto.domain
        assert ku.word_count == dto.word_count
        assert ku.quality_score == dto.quality_score
        assert ku.complexity == dto.complexity
        assert ku.semantic_links == tuple(dto.semantic_links)
        assert ku.created_at == dto.created_at
        assert ku.updated_at == dto.updated_at
        assert ku.tags == tuple(dto.tags)
        # Learning metadata
        assert ku.sel_category == SELCategory.SELF_AWARENESS
        assert ku.summary == "A brief summary"
        assert ku.learning_level == LearningLevel.INTERMEDIATE
        assert ku.estimated_time_minutes == 30
        assert ku.difficulty_rating == 0.7
        # Substance counters
        assert ku.times_applied_in_tasks == 5
        assert ku.times_practiced_in_events == 3
        assert ku.times_built_into_habits == 2
        assert ku.journal_reflections_count == 4
        assert ku.choices_informed_count == 1
        # Substance timestamps
        assert ku.last_applied_date == dto.last_applied_date
        assert ku.last_practiced_date == dto.last_practiced_date
        assert ku.last_built_into_habit_date == dto.last_built_into_habit_date
        assert ku.last_reflected_date == dto.last_reflected_date
        assert ku.last_choice_informed_date == dto.last_choice_informed_date

    def test_ku_to_dto_preserves_all_fields(self):
        """Ku.to_dto() must carry all 26 fields back to CurriculumDTO."""
        dto = self._make_full_dto()
        ku = Entity.from_dto(dto)
        dto2 = ku.to_dto()

        assert dto2.uid == dto.uid
        assert dto2.title == dto.title
        assert dto2.domain == dto.domain
        assert dto2.word_count == dto.word_count
        assert dto2.quality_score == dto.quality_score
        assert dto2.complexity == dto.complexity
        assert dto2.semantic_links == dto.semantic_links
        assert dto2.created_at == dto.created_at
        assert dto2.updated_at == dto.updated_at
        assert dto2.tags == dto.tags
        # Learning metadata
        assert dto2.sel_category == dto.sel_category
        assert dto2.summary == dto.summary
        assert dto2.learning_level == dto.learning_level
        assert dto2.estimated_time_minutes == dto.estimated_time_minutes
        assert dto2.difficulty_rating == dto.difficulty_rating
        # Substance counters
        assert dto2.times_applied_in_tasks == dto.times_applied_in_tasks
        assert dto2.times_practiced_in_events == dto.times_practiced_in_events
        assert dto2.times_built_into_habits == dto.times_built_into_habits
        assert dto2.journal_reflections_count == dto.journal_reflections_count
        assert dto2.choices_informed_count == dto.choices_informed_count
        # Substance timestamps
        assert dto2.last_applied_date == dto.last_applied_date
        assert dto2.last_practiced_date == dto.last_practiced_date
        assert dto2.last_built_into_habit_date == dto.last_built_into_habit_date
        assert dto2.last_reflected_date == dto.last_reflected_date
        assert dto2.last_choice_informed_date == dto.last_choice_informed_date

    def test_none_sel_category_preserved(self):
        """sel_category=None must survive round-trip (not default to SELF_AWARENESS)."""
        dto = CurriculumDTO(
            uid="ku_test_none",
            title="No SEL",
            domain=Domain.TECH,
            sel_category=None,
        )
        ku = Entity.from_dto(dto)
        assert ku.sel_category is None

        dto2 = ku.to_dto()
        assert dto2.sel_category is None


# =========================================================================
# from_dict: Dict → CurriculumDTO with enum/datetime parsing
# =========================================================================


class TestCurriculumDTOFromDict:
    """Test CurriculumDTO.from_dict() handles new fields correctly."""

    def test_from_dict_parses_enums(self):
        """from_dict must parse sel_category and learning_level from strings."""
        data = {
            "uid": "ku_test_abc",
            "title": "Test",
            "domain": "knowledge",  # enum value is lowercase
            "sel_category": "self_awareness",
            "learning_level": "intermediate",
        }
        dto = CurriculumDTO.from_dict(data)
        assert dto.sel_category == SELCategory.SELF_AWARENESS
        assert dto.learning_level == LearningLevel.INTERMEDIATE

    def test_from_dict_parses_substance_datetimes(self):
        """from_dict must parse substance timestamp strings to datetime."""
        now = datetime.now()
        data = {
            "uid": "ku_test_dt",
            "title": "Test",
            "domain": "knowledge",
            "last_applied_date": now.isoformat(),
            "last_practiced_date": now.isoformat(),
        }
        dto = CurriculumDTO.from_dict(data)
        assert isinstance(dto.last_applied_date, datetime)
        assert isinstance(dto.last_practiced_date, datetime)

    def test_from_dict_handles_missing_optional_fields(self):
        """from_dict must handle minimal dict (only required fields)."""
        data = {
            "uid": "ku_minimal",
            "title": "Minimal",
            "domain": "knowledge",
        }
        dto = CurriculumDTO.from_dict(data)
        assert dto.sel_category is None
        assert dto.learning_level == LearningLevel.BEGINNER  # default
        assert dto.times_applied_in_tasks == 0
        assert dto.last_applied_date is None

    def test_from_dict_filters_embedding_fields(self):
        """Embedding infrastructure fields must NOT appear on CurriculumDTO (ADR-037)."""
        data = {
            "uid": "ku_embed",
            "title": "With Embedding",
            "domain": "knowledge",
            "embedding": [0.1] * 1536,
            "embedding_model": "text-embedding-3-small",
            "embedding_updated_at": datetime.now().isoformat(),
        }
        dto = CurriculumDTO.from_dict(data)
        # dto_from_dict filters out fields not in the dataclass
        assert "embedding" not in dto.__dict__
        assert "embedding_model" not in dto.__dict__


# =========================================================================
# to_dict: CurriculumDTO → dict with enum serialization and datetime ISO
# =========================================================================


class TestCurriculumDTOToDict:
    """Test CurriculumDTO.to_dict() serializes new fields correctly."""

    def test_to_dict_serializes_enums(self):
        """to_dict must serialize sel_category and learning_level to strings."""
        dto = CurriculumDTO(
            uid="ku_test_ser",
            title="Test",
            domain=Domain.KNOWLEDGE,
            sel_category=SELCategory.SELF_MANAGEMENT,
            learning_level=LearningLevel.ADVANCED,
        )
        d = dto.to_dict()
        assert d["sel_category"] == "self_management"
        assert d["learning_level"] == "advanced"
        assert d["domain"] == "knowledge"  # get_enum_value returns .value

    def test_to_dict_serializes_substance_datetimes(self):
        """to_dict must serialize substance timestamps to ISO strings."""
        now = datetime.now()
        dto = CurriculumDTO(
            uid="ku_test_dt",
            title="Test",
            domain=Domain.KNOWLEDGE,
            last_applied_date=now,
            last_practiced_date=now,
        )
        d = dto.to_dict()
        assert isinstance(d["last_applied_date"], str)
        assert isinstance(d["last_practiced_date"], str)

    def test_to_dict_none_sel_category_stays_none(self):
        """to_dict with sel_category=None must produce None, not crash."""
        dto = CurriculumDTO(
            uid="ku_test_none",
            title="Test",
            domain=Domain.KNOWLEDGE,
        )
        d = dto.to_dict()
        assert d["sel_category"] is None

    def test_to_dict_includes_substance_counters(self):
        """to_dict must include all 5 substance counter fields."""
        dto = CurriculumDTO(
            uid="ku_test_sub",
            title="Test",
            domain=Domain.KNOWLEDGE,
            times_applied_in_tasks=3,
            times_practiced_in_events=2,
            times_built_into_habits=1,
            journal_reflections_count=5,
            choices_informed_count=4,
        )
        d = dto.to_dict()
        assert d["times_applied_in_tasks"] == 3
        assert d["times_practiced_in_events"] == 2
        assert d["times_built_into_habits"] == 1
        assert d["journal_reflections_count"] == 5
        assert d["choices_informed_count"] == 4


# =========================================================================
# Dispatch: EntityType → correct subclass
# =========================================================================


class TestKuTypeDispatch:
    """Verify Entity.from_dto() dispatches to correct subclass."""

    def test_resource_dispatches_to_resource_ku(self):
        """EntityType.RESOURCE dispatches to Resource, not Curriculum."""
        dto = ResourceDTO(uid="ku_test_res", title="Test Resource", ku_type=EntityType.RESOURCE)
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Resource)
        assert not isinstance(ku, Curriculum)

    def test_curriculum_dispatches_to_curriculum_ku(self):
        """EntityType.KU still dispatches to Curriculum."""
        dto = CurriculumDTO(uid="ku_test_cur", title="Test Curriculum", ku_type=EntityType.KU)
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Curriculum)

    def test_task_dispatches_to_task_ku(self):
        """EntityType.TASK dispatches to Task, not Curriculum."""
        dto = TaskDTO(uid="task_test_abc", title="Test Task", ku_type=EntityType.TASK)
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Task)
        assert not isinstance(ku, Curriculum)


# =========================================================================
# Curriculum field separation
# =========================================================================


class TestCurriculumFieldSeparation:
    """Verify curriculum-only fields live on Curriculum, not Entity/Task."""

    def test_task_ku_lacks_curriculum_fields(self):
        """Task must NOT have curriculum-only fields (complexity, substance, etc.)."""
        import dataclasses

        task_field_names = {f.name for f in dataclasses.fields(Task)}
        curriculum_only = {
            "complexity",
            "learning_level",
            "sel_category",
            "quality_score",
            "estimated_time_minutes",
            "difficulty_rating",
            "semantic_links",
            "target_age_range",
            "learning_objectives",
            "times_applied_in_tasks",
            "times_practiced_in_events",
            "times_built_into_habits",
            "journal_reflections_count",
            "choices_informed_count",
            "last_applied_date",
            "last_practiced_date",
            "last_built_into_habit_date",
            "last_reflected_date",
            "last_choice_informed_date",
        }
        overlap = task_field_names & curriculum_only
        assert overlap == set(), f"Task should NOT have curriculum fields: {overlap}"

    def test_curriculum_ku_has_all_curriculum_fields(self):
        """Curriculum must have all 19 curriculum-specific fields."""
        import dataclasses

        curriculum_field_names = {f.name for f in dataclasses.fields(Curriculum)}
        expected = {
            "complexity",
            "learning_level",
            "sel_category",
            "quality_score",
            "estimated_time_minutes",
            "difficulty_rating",
            "semantic_links",
            "target_age_range",
            "learning_objectives",
            "times_applied_in_tasks",
            "times_practiced_in_events",
            "times_built_into_habits",
            "journal_reflections_count",
            "choices_informed_count",
            "last_applied_date",
            "last_practiced_date",
            "last_built_into_habit_date",
            "last_reflected_date",
            "last_choice_informed_date",
        }
        missing = expected - curriculum_field_names
        assert missing == set(), f"Curriculum missing fields: {missing}"

    def test_kubase_stubs_return_defaults(self):
        """Entity stubs return 0.0 and False for non-curriculum types."""
        task = Task(uid="task_test", title="Test Task")
        assert task.substance_score() == 0.0
        assert task.needs_review() is False

    def test_curriculum_ku_overrides_stubs(self):
        """Curriculum overrides stubs with real implementations."""
        cu = Curriculum(
            uid="ku_test",
            title="Test",
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            times_built_into_habits=2,
            last_applied_date=datetime.now(),
            last_practiced_date=datetime.now(),
            last_built_into_habit_date=datetime.now(),
        )
        score = cu.substance_score()
        assert score > 0.0, "Curriculum with activity should have substance > 0"
        # needs_review depends on decay — just verify it returns bool
        assert isinstance(cu.needs_review(), bool)

    def test_task_dto_round_trip_ignores_curriculum_fields(self):
        """Task round-trip via DTO must not gain curriculum fields."""
        dto = TaskDTO(
            uid="task_test_rt",
            title="Task RT",
            ku_type=EntityType.TASK,
        )
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Task)
        # Task should NOT have these attributes from Curriculum
        assert not hasattr(ku, "complexity") or "complexity" not in {
            f.name for f in __import__("dataclasses").fields(ku)
        }

    def test_curriculum_dto_round_trip_preserves_all_fields(self):
        """Curriculum round-trip via DTO preserves all curriculum fields."""
        now = datetime.now()
        dto = CurriculumDTO(
            uid="ku_test_crt",
            title="Curriculum RT",
            ku_type=EntityType.KU,
            complexity=KuComplexity.ADVANCED,
            learning_level=LearningLevel.EXPERT,
            sel_category=SELCategory.SELF_AWARENESS,
            quality_score=0.9,
            estimated_time_minutes=45,
            difficulty_rating=0.8,
            semantic_links=["ku_a", "ku_b"],
            times_applied_in_tasks=5,
            times_practiced_in_events=3,
            last_applied_date=now,
            last_practiced_date=now,
        )
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Curriculum)
        assert ku.complexity == KuComplexity.ADVANCED
        assert ku.learning_level == LearningLevel.EXPERT
        assert ku.sel_category == SELCategory.SELF_AWARENESS
        assert ku.quality_score == 0.9
        assert ku.estimated_time_minutes == 45
        assert ku.difficulty_rating == 0.8
        assert ku.semantic_links == ("ku_a", "ku_b")
        assert ku.times_applied_in_tasks == 5
        assert ku.times_practiced_in_events == 3

        # Round-trip back to DTO
        dto2 = ku.to_dto()
        assert dto2.semantic_links == ["ku_a", "ku_b"]
        assert dto2.times_applied_in_tasks == 5
