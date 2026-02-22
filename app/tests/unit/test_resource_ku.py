"""
Resource Unit Tests
======================

Tests for Resource creation, field defaults, DTO round-trip,
and dispatch from Entity.from_dto().
"""

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.ku.curriculum import Curriculum
from core.models.ku.entity import Entity
from core.models.ku.ku_dto import KuDTO
from core.models.ku.resource import Resource


class TestResourceKuCreation:
    """Test Resource instantiation and defaults."""

    def test_basic_creation(self):
        """Resource can be created with minimal fields."""
        r = Resource(uid="ku_yoga-book_abc123", title="Yoga for Beginners")
        assert r.uid == "ku_yoga-book_abc123"
        assert r.title == "Yoga for Beginners"
        assert r.ku_type == EntityType.RESOURCE

    def test_forces_ku_type_resource(self):
        """__post_init__ forces ku_type=RESOURCE regardless of input."""
        r = Resource(uid="ku_test", title="Test", ku_type=EntityType.CURRICULUM)
        assert r.ku_type == EntityType.RESOURCE

    def test_resource_specific_fields_default_none(self):
        """All 7 resource-specific fields default to None."""
        r = Resource(uid="ku_test", title="Test")
        assert r.source_url is None
        assert r.author is None
        assert r.publisher is None
        assert r.publication_year is None
        assert r.isbn is None
        assert r.media_type is None
        assert r.resource_duration_minutes is None

    def test_resource_with_all_fields(self):
        """Resource preserves all 7 resource-specific field values."""
        r = Resource(
            uid="ku_meditations_abc123",
            title="Meditations",
            author="Marcus Aurelius",
            publisher="Penguin Classics",
            publication_year=180,
            isbn="978-0140449334",
            source_url="https://example.com/meditations",
            media_type="book",
            resource_duration_minutes=None,
        )
        assert r.author == "Marcus Aurelius"
        assert r.publisher == "Penguin Classics"
        assert r.publication_year == 180
        assert r.isbn == "978-0140449334"
        assert r.source_url == "https://example.com/meditations"
        assert r.media_type == "book"

    def test_visibility_defaults_public(self):
        """Resources default to PUBLIC visibility (shared type, Entity.__post_init__)."""
        r = Resource(uid="ku_test", title="Test")
        assert r.visibility == Visibility.PUBLIC

    def test_is_time_based_property(self):
        """is_time_based returns True when resource_duration_minutes is set."""
        r_no_time = Resource(uid="ku_book", title="A Book")
        assert r_no_time.is_time_based is False

        r_with_time = Resource(uid="ku_talk", title="A Talk", resource_duration_minutes=45)
        assert r_with_time.is_time_based is True


class TestResourceKuIsNotCurriculumKu:
    """Verify Resource is separate from Curriculum."""

    def test_resource_is_not_curriculum_instance(self):
        """Resource is NOT a Curriculum (different inheritance path)."""
        r = Resource(uid="ku_test", title="Test")
        assert not isinstance(r, Curriculum)

    def test_resource_is_kubase_instance(self):
        """Resource IS a Entity."""
        r = Resource(uid="ku_test", title="Test")
        assert isinstance(r, Entity)


class TestResourceKuDTORoundTrip:
    """Test Resource ↔ KuDTO lossless conversion."""

    def test_dto_to_resource_ku(self):
        """KuDTO with ku_type=RESOURCE dispatches to Resource."""
        dto = KuDTO(
            uid="ku_yoga-book_abc123",
            title="Yoga for Beginners",
            ku_type=EntityType.RESOURCE,
            domain=Domain.KNOWLEDGE,
            author="BKS Iyengar",
            publisher="Schocken Books",
            publication_year=1966,
            media_type="book",
            isbn="978-0805210316",
        )
        ku = Entity.from_dto(dto)
        assert isinstance(ku, Resource)
        assert ku.uid == dto.uid
        assert ku.author == "BKS Iyengar"
        assert ku.publisher == "Schocken Books"
        assert ku.publication_year == 1966
        assert ku.media_type == "book"
        assert ku.isbn == "978-0805210316"

    def test_resource_ku_to_dto_preserves_fields(self):
        """Resource.to_dto() preserves all resource-specific fields."""
        r = Resource(
            uid="ku_talk_abc123",
            title="TED Talk on Mindfulness",
            author="Jon Kabat-Zinn",
            source_url="https://example.com/talk",
            media_type="talk",
            resource_duration_minutes=20,
        )
        dto = r.to_dto()
        assert dto.uid == r.uid
        assert dto.author == "Jon Kabat-Zinn"
        assert dto.source_url == "https://example.com/talk"
        assert dto.media_type == "talk"
        assert dto.resource_duration_minutes == 20

    def test_full_round_trip(self):
        """KuDTO → Resource → KuDTO preserves all fields."""
        dto1 = KuDTO(
            uid="ku_film_abc123",
            title="Jiro Dreams of Sushi",
            ku_type=EntityType.RESOURCE,
            domain=Domain.KNOWLEDGE,
            author="David Gelb",
            publisher="Magnolia Pictures",
            publication_year=2011,
            media_type="film",
            resource_duration_minutes=81,
            source_url="https://example.com/jiro",
            isbn=None,
        )
        ku = Entity.from_dto(dto1)
        assert isinstance(ku, Resource)
        dto2 = ku.to_dto()

        assert dto2.uid == dto1.uid
        assert dto2.title == dto1.title
        assert dto2.ku_type == dto1.ku_type
        assert dto2.author == dto1.author
        assert dto2.publisher == dto1.publisher
        assert dto2.publication_year == dto1.publication_year
        assert dto2.media_type == dto1.media_type
        assert dto2.resource_duration_minutes == dto1.resource_duration_minutes
        assert dto2.source_url == dto1.source_url


class TestResourceKuMethods:
    """Test resource-specific methods."""

    def test_explain_existence_with_author(self):
        """explain_existence includes author attribution."""
        r = Resource(uid="ku_test", title="The Alchemist", author="Paulo Coelho")
        explanation = r.explain_existence()
        assert "The Alchemist" in explanation
        assert "Paulo Coelho" in explanation

    def test_explain_existence_minimal(self):
        """explain_existence works with just title."""
        r = Resource(uid="ku_test", title="Anonymous Work")
        assert r.explain_existence() == "Anonymous Work"

    def test_get_summary_short(self):
        """get_summary returns full text when short."""
        r = Resource(uid="ku_test", title="Test", description="Short desc")
        assert r.get_summary() == "Short desc"

    def test_get_summary_truncates(self):
        """get_summary truncates long text."""
        long_text = "x" * 300
        r = Resource(uid="ku_test", title="Test", description=long_text)
        summary = r.get_summary(max_length=100)
        assert len(summary) == 100
        assert summary.endswith("...")
