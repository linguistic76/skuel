# mypy: disable-error-code="attr-defined,var-annotated"
"""
Unit tests for PrinciplesService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.principle_enums import PrincipleCategory
from core.models.principle.principle_request import PrincipleCreateRequest
from core.services.principles_service import PrinciplesService
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def principles_service(mock_backend: Mock, mock_graph_intel: Mock) -> PrinciplesService:
    service = PrinciplesService(
        backend=mock_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=AsyncMock(),
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.search = AsyncMock()
    service.learning = AsyncMock()
    service.alignment = AsyncMock()
    service.reflection = AsyncMock()
    service.planning = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestPrinciplesServiceCreate
# ---------------------------------------------------------------------------


class TestPrinciplesServiceCreate:
    @pytest.mark.asyncio
    async def test_create_principle_delegates_to_core(
        self, principles_service: PrinciplesService
    ) -> None:
        """create_principle delegates to core.create_principle with the request and user_uid."""
        mock_principle = Mock()
        principles_service.core.create_principle = AsyncMock(return_value=Result.ok(mock_principle))

        request = PrincipleCreateRequest(
            title="Do the right thing",
            statement="Always act with integrity",
            principle_category=PrincipleCategory.ETHICAL,
            why_important="Foundation of trust",
        )
        result = await principles_service.create_principle(request, user_uid="user_123")

        assert result.is_ok
        principles_service.core.create_principle.assert_called_once_with(request, "user_123")


# ---------------------------------------------------------------------------
# TestPrinciplesServicePortfolio
# ---------------------------------------------------------------------------


class TestPrinciplesServicePortfolio:
    @pytest.mark.asyncio
    async def test_get_user_principle_portfolio_calls_backend_list(
        self, principles_service: PrinciplesService, mock_backend: Mock
    ) -> None:
        """get_user_principle_portfolio calls backend.list with user_uid filter."""
        mock_principle = Mock()
        mock_backend.list = AsyncMock(return_value=Result.ok(([mock_principle], 1)))

        result = await principles_service.get_user_principle_portfolio("user_test")

        assert result.is_ok
        assert result.value["user_uid"] == "user_test"
        assert result.value["count"] == 1
        mock_backend.list.assert_called_once_with(filters={"user_uid": "user_test"}, limit=100)

    @pytest.mark.asyncio
    async def test_get_user_principle_portfolio_propagates_backend_error(
        self, principles_service: PrinciplesService, mock_backend: Mock
    ) -> None:
        """get_user_principle_portfolio propagates backend error."""
        mock_backend.list = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        result = await principles_service.get_user_principle_portfolio("user_test")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_calculate_principle_integrity_calls_cross_domain_context(
        self, principles_service: PrinciplesService
    ) -> None:
        """calculate_principle_integrity calls relationships.get_cross_domain_context."""
        mock_context = {"tasks": [], "goals": []}
        principles_service.relationships.get_cross_domain_context = AsyncMock(
            return_value=Result.ok(mock_context)
        )

        result = await principles_service.calculate_principle_integrity(
            "user_test", "principle_abc"
        )

        assert result.is_ok
        assert result.value["principle_uid"] == "principle_abc"
        assert result.value["user_uid"] == "user_test"
        principles_service.relationships.get_cross_domain_context.assert_called_once_with(
            "principle_abc"
        )


# ---------------------------------------------------------------------------
# TestPrinciplesServiceRelationships
# ---------------------------------------------------------------------------


class TestPrinciplesServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_principle_to_knowledge_passes_relevance(
        self, principles_service: PrinciplesService
    ) -> None:
        """link_principle_to_knowledge writes the GROUNDED_IN_KNOWLEDGE ('knowledge') edge."""
        principles_service.relationships.create_relationship = AsyncMock(
            return_value=Result.ok(True)
        )

        await principles_service.link_principle_to_knowledge(
            "principle_abc", "ku_stoicism_xyz", relevance="foundational"
        )

        principles_service.relationships.create_relationship.assert_called_once_with(
            "knowledge",
            "principle_abc",
            "ku_stoicism_xyz",
            {"relevance": "foundational"},
        )


# ---------------------------------------------------------------------------
# TestRecordPrincipleReflection
# ---------------------------------------------------------------------------


class TestRecordPrincipleReflection:
    """A reflection's persisted trace is the principle's review stamp plus a dated
    entry in its alignment history, written after the ownership check and
    before anything is announced."""

    @pytest.mark.asyncio
    async def test_reflection_stamps_and_appends_to_the_history_through_the_core(
        self, principles_service: PrinciplesService
    ) -> None:
        from datetime import date

        from core.models.enums.principle_enums import AlignmentLevel
        from core.models.principle.principle_types import AlignmentAssessment

        earlier = AlignmentAssessment(
            assessed_date=date(2026, 8, 1),
            alignment_level=AlignmentLevel.PARTIAL,
            evidence="Self-rated",
        )
        owned = Mock(alignment_history=(earlier,))
        principles_service.core.verify_ownership = AsyncMock(return_value=Result.ok(owned))
        update_principle = AsyncMock(return_value=Result.ok(Mock()))
        principles_service.core.update_principle = update_principle

        result = await principles_service.record_principle_reflection(
            "principle_1", "user_1", "aligned", "Held the line in a hard meeting"
        )

        assert result.is_ok
        update_principle.assert_awaited_once()
        call = update_principle.await_args
        assert call is not None
        uid, intent = call.args
        assert uid == "principle_1"
        assert intent.last_review_date == date.today()
        changes = intent.to_changes()
        assert changes["last_review_date"] == date.today()
        # The stored history, then the reflection as a dated occurrence.
        assert changes["alignment_history"] == [
            earlier.to_record(),
            {
                "assessed_date": date.today().isoformat(),
                "alignment_level": "aligned",
                "evidence": "Held the line in a hard meeting",
                "reflection": None,
                "kind": "reflection",
            },
        ]

    @pytest.mark.asyncio
    async def test_an_unknown_alignment_level_is_refused_before_any_write(
        self, principles_service: PrinciplesService
    ) -> None:
        principles_service.core.verify_ownership = AsyncMock(
            return_value=Result.ok(Mock(alignment_history=()))
        )
        update_principle = AsyncMock(return_value=Result.ok(Mock()))
        principles_service.core.update_principle = update_principle

        result = await principles_service.record_principle_reflection(
            "principle_1", "user_1", "somewhat", "x"
        )

        assert result.is_error
        assert result.expect_error().category.value == "validation"
        update_principle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reflection_on_a_foreign_principle_is_not_found(
        self, principles_service: PrinciplesService
    ) -> None:
        principles_service.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("Principle principle_9 not found"))
        )
        update_principle = AsyncMock(return_value=Result.ok(Mock()))
        principles_service.core.update_principle = update_principle

        result = await principles_service.record_principle_reflection(
            "principle_9", "user_1", "aligned", "x"
        )

        assert result.is_error
        # Ownership is decided before the stamp: a foreign principle is never written.
        update_principle.assert_not_awaited()
