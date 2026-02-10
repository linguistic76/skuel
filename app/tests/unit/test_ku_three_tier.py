"""
KU Three-Tier Round-Trip Tests
==============================

Validates that all 26 business fields survive the KuDTO ↔ Ku round-trip,
and that from_dict/to_dict handle enum/datetime serialization correctly.
"""

from datetime import datetime, timedelta

from core.models.enums import Domain, LearningLevel, SELCategory
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO

# =========================================================================
# Round-trip: KuDTO → Ku.from_dto() → Ku.to_dto() → all fields preserved
# =========================================================================


class TestKuThreeTierRoundTrip:
    """Test lossless KuDTO ↔ Ku conversion."""

    def _make_full_dto(self) -> KuDTO:
        """Create a KuDTO with all fields populated."""
        now = datetime.now()
        return KuDTO(
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
        """KuDTO → Ku.from_dto() must carry all 26 fields."""
        dto = self._make_full_dto()
        ku = Ku.from_dto(dto)

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
        """Ku.to_dto() must carry all 26 fields back to KuDTO."""
        dto = self._make_full_dto()
        ku = Ku.from_dto(dto)
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
        dto = KuDTO(
            uid="ku_test_none",
            title="No SEL",
            domain=Domain.TECH,
            sel_category=None,
        )
        ku = Ku.from_dto(dto)
        assert ku.sel_category is None

        dto2 = ku.to_dto()
        assert dto2.sel_category is None


# =========================================================================
# from_dict: Dict → KuDTO with enum/datetime parsing
# =========================================================================


class TestKuDTOFromDict:
    """Test KuDTO.from_dict() handles new fields correctly."""

    def test_from_dict_parses_enums(self):
        """from_dict must parse sel_category and learning_level from strings."""
        data = {
            "uid": "ku_test_abc",
            "title": "Test",
            "domain": "knowledge",  # enum value is lowercase
            "sel_category": "self_awareness",
            "learning_level": "intermediate",
        }
        dto = KuDTO.from_dict(data)
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
        dto = KuDTO.from_dict(data)
        assert isinstance(dto.last_applied_date, datetime)
        assert isinstance(dto.last_practiced_date, datetime)

    def test_from_dict_handles_missing_optional_fields(self):
        """from_dict must handle minimal dict (only required fields)."""
        data = {
            "uid": "ku_minimal",
            "title": "Minimal",
            "domain": "knowledge",
        }
        dto = KuDTO.from_dict(data)
        assert dto.sel_category is None
        assert dto.learning_level == LearningLevel.BEGINNER  # default
        assert dto.times_applied_in_tasks == 0
        assert dto.last_applied_date is None

    def test_from_dict_filters_embedding_fields(self):
        """Embedding infrastructure fields must NOT appear on KuDTO (ADR-037)."""
        data = {
            "uid": "ku_embed",
            "title": "With Embedding",
            "domain": "knowledge",
            "embedding": [0.1] * 1536,
            "embedding_model": "text-embedding-3-small",
            "embedding_updated_at": datetime.now().isoformat(),
        }
        dto = KuDTO.from_dict(data)
        # dto_from_dict filters out fields not in the dataclass
        assert "embedding" not in dto.__dict__
        assert "embedding_model" not in dto.__dict__


# =========================================================================
# to_dict: KuDTO → dict with enum serialization and datetime ISO
# =========================================================================


class TestKuDTOToDict:
    """Test KuDTO.to_dict() serializes new fields correctly."""

    def test_to_dict_serializes_enums(self):
        """to_dict must serialize sel_category and learning_level to strings."""
        dto = KuDTO(
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
        dto = KuDTO(
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
        dto = KuDTO(
            uid="ku_test_none",
            title="Test",
            domain=Domain.KNOWLEDGE,
        )
        d = dto.to_dict()
        assert d["sel_category"] is None

    def test_to_dict_includes_substance_counters(self):
        """to_dict must include all 5 substance counter fields."""
        dto = KuDTO(
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
