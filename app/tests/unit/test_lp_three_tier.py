"""
LP Three-Tier Round-Trip Tests
==============================

Validates that all 14 business fields survive the LpDTO <-> Lp round-trip,
and that from_dict/to_dict handle enum/datetime serialization correctly.

Follows test_ku_three_tier.py pattern.
"""

from datetime import datetime

from core.models.enums import Domain
from core.models.lp.lp import Lp, LpType
from core.models.lp.lp_dto import LpDTO

# =========================================================================
# Round-trip: LpDTO -> Lp.from_dto() -> Lp.to_dto() -> all fields preserved
# =========================================================================


class TestLpThreeTierRoundTrip:
    """Test lossless LpDTO <-> Lp conversion."""

    def _make_full_dto(self) -> LpDTO:
        """Create an LpDTO with all fields populated."""
        now = datetime.now()
        return LpDTO(
            uid="lp:test_abc123",
            name="Test Learning Path",
            goal="Master Python fundamentals",
            domain=Domain.LEARNING,
            path_type=LpType.ADAPTIVE,
            difficulty="advanced",
            created_at=now,
            updated_at=now,
            created_by="user_admin",
            outcomes=["Understand OOP", "Write clean code"],
            estimated_hours=40.0,
            checkpoint_week_intervals=[2, 4, 6],
            user_uid="user_test",
            source="ingestion",
            tags=["python", "fundamentals"],
            metadata={"origin": "curriculum_builder"},
        )

    def test_dto_to_lp_preserves_all_fields(self):
        """LpDTO -> Lp.from_dto() must carry all 14 fields."""
        dto = self._make_full_dto()
        lp = Lp.from_dto(dto)

        assert lp.uid == dto.uid
        assert lp.name == dto.name
        assert lp.goal == dto.goal
        assert lp.domain == dto.domain
        assert lp.path_type == LpType.ADAPTIVE
        assert lp.difficulty == "advanced"
        assert lp.steps == ()  # Steps not transferred from DTO
        assert lp.created_at == dto.created_at
        assert lp.updated_at == dto.updated_at
        assert lp.created_by == "user_admin"
        assert lp.outcomes == ("Understand OOP", "Write clean code")
        assert lp.estimated_hours == 40.0
        assert lp.checkpoint_week_intervals == (2, 4, 6)
        assert lp.metadata == {"origin": "curriculum_builder"}

    def test_lp_to_dto_preserves_all_fields(self):
        """Lp.to_dto() must carry all fields back to LpDTO."""
        dto = self._make_full_dto()
        lp = Lp.from_dto(dto)
        dto2 = lp.to_dto()

        assert dto2.uid == dto.uid
        assert dto2.name == dto.name
        assert dto2.goal == dto.goal
        assert dto2.domain == dto.domain
        assert dto2.path_type == dto.path_type
        assert dto2.difficulty == dto.difficulty
        assert dto2.created_at == dto.created_at
        assert dto2.updated_at == dto.updated_at
        assert dto2.created_by == dto.created_by
        assert dto2.outcomes == dto.outcomes
        assert dto2.estimated_hours == dto.estimated_hours
        assert dto2.checkpoint_week_intervals == dto.checkpoint_week_intervals
        assert dto2.metadata == dto.metadata

    def test_none_created_by_preserved(self):
        """created_by=None must survive round-trip."""
        dto = LpDTO(
            uid="lp:test_none",
            name="No Creator",
            goal="Test goal",
            domain=Domain.LEARNING,
            created_by=None,
        )
        lp = Lp.from_dto(dto)
        assert lp.created_by is None

        dto2 = lp.to_dto()
        assert dto2.created_by is None


# =========================================================================
# from_dict: Dict -> LpDTO with enum/datetime parsing
# =========================================================================


class TestLpDTOFromDict:
    """Test LpDTO.from_dict() handles all fields correctly."""

    def test_from_dict_parses_enums(self):
        """from_dict must parse Domain and LpType from strings."""
        data = {
            "uid": "lp:test_enum",
            "name": "Enum Test",
            "goal": "Test goal",
            "domain": "learning",
            "path_type": "adaptive",
        }
        dto = LpDTO.from_dict(data)
        assert dto.domain == Domain.LEARNING
        assert dto.path_type == LpType.ADAPTIVE

    def test_from_dict_parses_datetimes(self):
        """from_dict must parse ISO datetime strings."""
        now = datetime.now()
        data = {
            "uid": "lp:test_dt",
            "name": "DateTime Test",
            "goal": "Test goal",
            "domain": "learning",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        dto = LpDTO.from_dict(data)
        assert isinstance(dto.created_at, datetime)
        assert isinstance(dto.updated_at, datetime)

    def test_from_dict_handles_missing_optional_fields(self):
        """from_dict must handle minimal dict (only required fields)."""
        data = {
            "uid": "lp:minimal",
            "name": "Minimal",
            "goal": "A goal",
            "domain": "learning",
        }
        dto = LpDTO.from_dict(data)
        assert dto.path_type == LpType.STRUCTURED  # default
        assert dto.difficulty == "intermediate"  # default
        assert dto.created_by is None
        assert dto.outcomes == []
        assert dto.estimated_hours == 0.0
        assert dto.checkpoint_week_intervals == []
        assert dto.tags == []
        assert dto.metadata == {}

    def test_from_dict_filters_embedding_fields(self):
        """Embedding infrastructure fields must NOT appear on LpDTO (ADR-037)."""
        data = {
            "uid": "lp:embed",
            "name": "With Embedding",
            "goal": "Test goal",
            "domain": "learning",
            "embedding": [0.1] * 1536,
            "embedding_model": "text-embedding-3-small",
            "embedding_updated_at": datetime.now().isoformat(),
        }
        dto = LpDTO.from_dict(data)
        assert "embedding" not in dto.__dict__
        assert "embedding_model" not in dto.__dict__

    def test_from_dict_ignores_deprecated_prerequisites(self):
        """Deprecated prerequisites field must not cause errors."""
        data = {
            "uid": "lp:deprecated",
            "name": "Deprecated Fields",
            "goal": "Test goal",
            "domain": "learning",
            "prerequisites": ["ku_prereq_1", "ku_prereq_2"],
        }
        dto = LpDTO.from_dict(data)
        assert dto.uid == "lp:deprecated"
        assert "prerequisites" not in dto.__dict__


# =========================================================================
# to_dict: LpDTO -> dict with enum serialization and datetime ISO
# =========================================================================


class TestLpDTOToDict:
    """Test LpDTO.to_dict() serializes fields correctly."""

    def test_to_dict_serializes_enums(self):
        """to_dict must serialize Domain and LpType to strings."""
        dto = LpDTO(
            uid="lp:test_ser",
            name="Serialize Test",
            goal="Test goal",
            domain=Domain.LEARNING,
            path_type=LpType.EXPLORATORY,
        )
        d = dto.to_dict()
        assert d["domain"] == "learning"
        assert d["path_type"] == "exploratory"

    def test_to_dict_serializes_datetimes(self):
        """to_dict must serialize datetimes to ISO strings."""
        now = datetime.now()
        dto = LpDTO(
            uid="lp:test_dt",
            name="DateTime Test",
            goal="Test goal",
            domain=Domain.LEARNING,
            created_at=now,
            updated_at=now,
        )
        d = dto.to_dict()
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)

    def test_to_dict_includes_checkpoint_intervals(self):
        """to_dict must include checkpoint_week_intervals."""
        dto = LpDTO(
            uid="lp:test_ck",
            name="Checkpoint Test",
            goal="Test goal",
            domain=Domain.LEARNING,
            checkpoint_week_intervals=[2, 4, 8],
        )
        d = dto.to_dict()
        assert d["checkpoint_week_intervals"] == [2, 4, 8]

    def test_to_dict_includes_outcomes(self):
        """to_dict must include outcomes list."""
        dto = LpDTO(
            uid="lp:test_out",
            name="Outcomes Test",
            goal="Test goal",
            domain=Domain.LEARNING,
            outcomes=["Learn X", "Master Y"],
        )
        d = dto.to_dict()
        assert d["outcomes"] == ["Learn X", "Master Y"]
