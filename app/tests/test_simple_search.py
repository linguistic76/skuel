"""
Test Search Models
==================

Tests the search Pydantic models and enum dynamic methods:
- SearchRequest/SearchResponse models
- Faceted search capabilities
- Enum dynamic methods (get_icon, get_color, etc.)
"""

import pytest

from core.models.enums import (
    ContentType,
    Domain,
    EducationalLevel,
    LearningLevel,
    SELCategory,
)
from core.models.search_request import FacetCount, SearchRequest, SearchResponse


class TestSearchRequestModels:
    """Test SearchRequest and SearchResponse Pydantic models"""

    def test_search_request_basic(self):
        """Test basic SearchRequest creation"""
        request = SearchRequest(query_text="meditation")

        assert request.query_text == "meditation"
        assert request.domain is None
        assert request.limit == 20
        assert request.offset == 0
        assert request.include_facet_counts is True

    def test_search_request_with_domain(self):
        """Test SearchRequest with domain filter"""
        request = SearchRequest(query_text="task management", domain=Domain.TASKS)

        assert request.query_text == "task management"
        assert request.domain == Domain.TASKS

    def test_search_request_faceted(self):
        """Test SearchRequest with multiple facets"""
        request = SearchRequest(
            query_text="self-awareness practice",
            domain=Domain.KNOWLEDGE,
            sel_category=SELCategory.SELF_AWARENESS,
            learning_level=LearningLevel.BEGINNER,
            content_type=ContentType.PRACTICE,
            educational_level=EducationalLevel.HIGH_SCHOOL,
        )

        assert request.sel_category == SELCategory.SELF_AWARENESS
        assert request.learning_level == LearningLevel.BEGINNER
        assert request.content_type == ContentType.PRACTICE
        assert request.educational_level == EducationalLevel.HIGH_SCHOOL

    def test_search_request_validation_empty_query(self):
        """Test that empty query text is rejected"""
        with pytest.raises(ValueError):
            SearchRequest(query_text="")

    def test_search_request_to_property_filters(self):
        """Test conversion to property filters"""
        request = SearchRequest(
            query_text="test",
            sel_category=SELCategory.SELF_AWARENESS,
            learning_level=LearningLevel.BEGINNER,
            content_type=ContentType.PRACTICE,
        )

        filters = request.to_property_filters()

        assert filters["sel_category"] == "self_awareness"
        assert filters["learning_level"] == "beginner"
        assert filters["content_type"] == "practice"

    def test_search_request_get_graph_label(self):
        """Test graph label mapping"""
        # Knowledge domain
        request = SearchRequest(query_text="test", domain=Domain.KNOWLEDGE)
        assert request.get_graph_label() == "Entity"

        # Tasks domain
        request = SearchRequest(query_text="test", domain=Domain.TASKS)
        assert request.get_graph_label() == "Task"

        # No domain
        request = SearchRequest(query_text="test")
        assert request.get_graph_label() is None

    def test_facet_count_model(self):
        """Test FacetCount model"""
        facet = FacetCount(
            facet_type="sel_category",
            facet_value="self_awareness",
            count=23,
            display_name="Self-Awareness",
            icon="🧘",
        )

        assert facet.facet_type == "sel_category"
        assert facet.facet_value == "self_awareness"
        assert facet.count == 23
        assert facet.display_name == "Self-Awareness"
        assert facet.icon == "🧘"

    def test_search_response_basic(self):
        """Test SearchResponse creation"""
        response = SearchResponse(
            results=[{"uid": "ku.001", "title": "Introduction to Self-Awareness"}],
            total=1,
            limit=20,
            offset=0,
            query_text="self-awareness",
        )

        assert response.total == 1
        assert len(response.results) == 1
        assert response.query_text == "self-awareness"
        assert response.has_results() is True
        assert response.has_more_pages() is False

    def test_search_response_pagination(self):
        """Test SearchResponse pagination info"""
        response = SearchResponse(
            results=[{"uid": f"ku.{i}"} for i in range(20)],
            total=100,
            limit=20,
            offset=40,
            query_text="test",
        )

        page_info = response.get_page_info()

        assert page_info["current_page"] == 3  # (40 / 20) + 1
        assert page_info["total_pages"] == 5  # ceil(100 / 20)
        assert page_info["showing_from"] == 41
        assert page_info["showing_to"] == 60
        assert page_info["total_results"] == 100
        assert response.has_more_pages() is True

    def test_search_response_with_facet_counts(self):
        """Test SearchResponse with facet counts"""
        facet_counts = {
            "sel_category": [
                FacetCount(
                    facet_type="sel_category",
                    facet_value="self_awareness",
                    count=23,
                    display_name="Self-Awareness",
                    icon="🧘",
                )
            ],
            "learning_level": [
                FacetCount(facet_type="learning_level", facet_value="beginner", count=15)
            ],
        }

        response = SearchResponse(
            results=[], total=0, limit=20, offset=0, query_text="test", facet_counts=facet_counts
        )

        assert "sel_category" in response.facet_counts
        assert "learning_level" in response.facet_counts
        assert response.facet_counts["sel_category"][0].count == 23


class TestEnumDynamicMethods:
    """Test the new enum dynamic methods"""

    def test_content_type_get_icon(self):
        """Test ContentType.get_icon()"""
        assert ContentType.CONCEPT.get_icon() == "💡"
        assert ContentType.PRACTICE.get_icon() == "🎯"
        assert ContentType.EXAMPLE.get_icon() == "📖"

    def test_content_type_get_color(self):
        """Test ContentType.get_color()"""
        assert ContentType.CONCEPT.get_color() == "#3B82F6"
        assert ContentType.PRACTICE.get_color() == "#10B981"

    def test_educational_level_get_icon(self):
        """Test EducationalLevel.get_icon()"""
        assert EducationalLevel.ELEMENTARY.get_icon() == "🎒"
        assert EducationalLevel.HIGH_SCHOOL.get_icon() == "🎓"
        assert EducationalLevel.PROFESSIONAL.get_icon() == "💼"

    def test_educational_level_get_age_range(self):
        """Test EducationalLevel.get_age_range()"""
        assert EducationalLevel.ELEMENTARY.get_age_range() == (5, 10)
        assert EducationalLevel.HIGH_SCHOOL.get_age_range() == (14, 17)
        assert EducationalLevel.PROFESSIONAL.get_age_range() == (23, 65)

    def test_educational_level_to_numeric(self):
        """Test EducationalLevel.to_numeric()"""
        assert EducationalLevel.ELEMENTARY.to_numeric() == 1
        assert EducationalLevel.HIGH_SCHOOL.to_numeric() == 3
        assert EducationalLevel.LIFELONG.to_numeric() == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
