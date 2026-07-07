"""NOUS sub-topic (2nd taxonomy level) wiring tests.

Covers the mechanism shipped ahead of the data (there is no authored
`nous_subtopic` content yet — every faucet is fail-soft empty):
- Ku model/DTO round-trip: frontmatter list → tuple, survives DTO → model → DTO
- SearchRequest: the `nous_subtopic` facet lands in property filters (which feed
  chunk `parent_filters`, so scoped RAG retrieval honors it for free)
- from_form_params parses + empty-normalizes it
- /search + Askesis faucets render the control when vocab present, NOTHING when
  empty (fails soft exactly like the `nous` selector)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.search.search_router import SearchRouter
from core.models.search_request import SearchRequest
from core.utils.result_simplified import Result
from ui.askesis.chat import render_askesis_shell
from ui.search.components import _render_nous_subtopic_select


class TestKuNousSubtopicField:
    def test_list_authored_nous_subtopic_normalizes_to_tuple(self) -> None:
        ku = Ku(uid="ku_test_1", title="Test", nous_subtopic=["nervous-system", "sleep"])

        assert ku.nous_subtopic == ("nervous-system", "sleep")

    def test_default_nous_subtopic_is_empty(self) -> None:
        ku = Ku(uid="ku_test_2", title="Unassigned")

        assert ku.nous_subtopic == ()

    def test_dto_round_trip_carries_nous_subtopic(self) -> None:
        # frontmatter/db dict → DTO → model → DTO
        dto = KuDTO.from_dict(
            {"uid": "ku_test_3", "title": "Body", "nous_subtopic": ["nervous-system"]}
        )
        assert dto.nous_subtopic == ["nervous-system"]

        ku = Ku.from_dto(dto)
        assert ku.nous_subtopic == ("nervous-system",)

        back = ku.to_dto()
        assert back.nous_subtopic == ["nervous-system"]


class TestSearchRequestNousSubtopicFacet:
    def test_facet_maps_to_real_property_name(self) -> None:
        request = SearchRequest(nous_subtopic="nervous-system")

        assert request.to_property_filters()["nous_subtopic"] == "nervous-system"

    def test_form_params_normalize_empty_nous_subtopic(self) -> None:
        request = SearchRequest.from_form_params(query="breath", nous_subtopic="")

        assert request.nous_subtopic is None
        assert "nous_subtopic" not in request.to_property_filters()

    def test_form_params_parse_nous_subtopic(self) -> None:
        request = SearchRequest.from_form_params(query="breath", nous_subtopic="sleep")

        assert request.nous_subtopic == "sleep"
        assert request.to_property_filters()["nous_subtopic"] == "sleep"

    def test_filter_only_search_with_nous_subtopic_is_valid(self) -> None:
        # No query_text, but nous_subtopic alone must satisfy the validator.
        request = SearchRequest(nous_subtopic="movement")

        assert request.nous_subtopic == "movement"


class TestScopedChunkRetrievalHonorsSubtopic:
    @pytest.mark.anyio
    async def test_nous_subtopic_reaches_parent_filters(self) -> None:
        """to_property_filters feeds chunk parent_filters — sub-topic scoping is free."""
        vector_search = MagicMock()
        vector_search.find_similar_chunks_by_text = AsyncMock(return_value=Result.ok([]))
        services = MagicMock()
        services.vector_search_service = vector_search
        router = SearchRouter(services)

        request = SearchRequest(
            query_text="what is the vagus nerve?", nous="body", nous_subtopic="nervous-system"
        )
        result = await router.retrieve_scoped_chunks(request)

        assert result.is_ok
        kwargs = vector_search.find_similar_chunks_by_text.await_args.kwargs
        assert kwargs["parent_filters"].get("nous_subtopic") == "nervous-system"
        assert kwargs["parent_filters"].get("nous") == "body"


class TestFaucetFailsSoft:
    def test_search_subtopic_select_renders_control_when_vocab_present(self) -> None:
        html = _render_nous_subtopic_select(["nervous-system", "sleep"])

        assert 'name="nous_subtopic"' in html
        assert "Nervous System" in html
        assert "Sleep" in html

    def test_search_subtopic_select_renders_nothing_when_empty(self) -> None:
        assert _render_nous_subtopic_select([]) == ""

    def test_askesis_subtopic_selector_renders_when_vocab_present(self) -> None:
        xml = to_xml(render_askesis_shell(nous_subtopics=["nervous-system"]))

        # Hidden field always present (bound to root state); selector present with vocab.
        assert 'name="nous_subtopic"' in xml
        assert ':value="selectedNousSubtopic"' in xml
        assert "selectedNousSubtopic:" in xml
        assert "nervous-system" in xml

    def test_askesis_subtopic_selector_absent_when_empty(self) -> None:
        # Empty vocab → no <select> for the sub-topic, but the hidden field + root
        # state still exist (mirror of the nous selector fail-soft).
        xml = to_xml(render_askesis_shell(nous_subtopics=[]))

        assert "Scope answer to a NOUS sub-topic" not in xml
        assert 'name="nous_subtopic"' in xml
        assert 'selectedNousSubtopic: ""' in xml
