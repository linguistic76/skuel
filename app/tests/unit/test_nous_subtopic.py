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

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.search.search_router import SearchRouter
from core.models.search_request import SearchRequest
from core.utils.result_simplified import Result
from ui.askesis.chat import render_askesis_shell
from ui.search.components import (
    _render_nous_select,
    _render_nous_subtopic_select,
    render_nous_subtopic_inner,
)


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
        # No query_text, but nous_subtopic alone is a valid filter-only search:
        # the model is permissive and has_any_criteria() reports the filter.
        request = SearchRequest(nous_subtopic="movement")

        assert request.nous_subtopic == "movement"
        assert request.has_any_criteria() is True


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
        html = to_xml(_render_nous_subtopic_select(["nervous-system", "sleep"]))

        assert 'name="nous_subtopic"' in html
        assert "Nervous System" in html
        assert "Sleep" in html

    def test_search_subtopic_select_renders_nothing_when_empty(self) -> None:
        assert _render_nous_subtopic_select([]) is None

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


class TestPathStepNousSubtopicField:
    """PathStep mirrors `nous_subtopic` symmetrically with Ku (and with its own
    `nous`) — else a subtopic-scoped search/RAG would drop every PathStep card and
    body chunk, since the predicate is applied to PathStep parents too (Kody #546)."""

    def test_list_authored_nous_subtopic_normalizes_to_tuple(self) -> None:
        from core.models.pathways.path_step import PathStep

        ps = PathStep(uid="ps.body.breath", title="Breath", nous_subtopic=["nervous-system"])
        assert ps.nous_subtopic == ("nervous-system",)

    def test_default_nous_subtopic_is_empty(self) -> None:
        from core.models.pathways.path_step import PathStep

        ps = PathStep(uid="ps.x.y", title="Unassigned")
        assert ps.nous_subtopic == ()


def test_nous_subtopic_select_escapes_option_values() -> None:
    """Graph-derived sub-topic strings are HTML-escaped by the FT renderer — a
    malicious authored value can't inject stored XSS on /search (Kody #546)."""
    html = to_xml(_render_nous_subtopic_select(['"><script>alert(1)</script>']))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html

    # The re-rendered fragment (HTMX swap target of /search/subtopics) escapes too.
    inner = to_xml(render_nous_subtopic_inner(['"><script>alert(1)</script>']))
    assert "<script>" not in inner
    assert "&lt;script&gt;" in inner


class TestNousSubtopicDependentDropdown:
    """#547 item 1: selecting a NOUS topic narrows the sub-topic options.

    The column re-fetches ``/search/subtopics`` on ``change from:[name='nous']``
    (pure HTMX, no Alpine window-global seeding), and the NOUS select drops the
    now-orphaned ``nous_subtopic`` from its results request so a topic switch
    re-scopes cleanly instead of carrying a stale sub-topic.
    """

    def test_subtopic_column_wires_dependent_htmx(self) -> None:
        html = to_xml(_render_nous_subtopic_select(["nervous-system"]))

        assert 'id="nous-subtopic-column"' in html
        assert 'hx-get="/search/subtopics"' in html
        assert "change from:[name='nous']" in html
        assert 'hx-target="#nous-subtopic-column"' in html
        assert "[name='nous']" in html  # hx-include scopes the fetch by nous

    def test_nous_select_excludes_subtopic_from_results_include(self) -> None:
        # Switching NOUS invalidates the old sub-topic — results must re-scope by
        # NOUS alone while the column concurrently resets its options.
        html = to_xml(_render_nous_select(["body", "investment"]))

        assert "[name='nous_subtopic']" not in html

    def test_inner_fragment_omits_column_wrapper(self) -> None:
        # /search/subtopics returns ONLY the inner label+select (innerHTML swap);
        # the container wrapper with its HTMX trigger must persist, not nest.
        inner = to_xml(render_nous_subtopic_inner(["breath"]))

        assert 'name="nous_subtopic"' in inner
        assert "nous-subtopic-column" not in inner

    def test_inner_fragment_fail_soft_empty_keeps_all_option(self) -> None:
        # A NOUS topic with no authored sub-topics → just "All Sub-topics" (the
        # column stays present so the HTMX target never vanishes mid-interaction).
        inner = to_xml(render_nous_subtopic_inner([]))

        assert "All Sub-topics" in inner
        assert 'name="nous_subtopic"' in inner


class TestSearchRouterNousSubtopicMerge:
    """`SearchRouter.nous_subtopic_map` / `list_nous_subtopics` merge each
    curriculum domain's OWN-label pairs (Ku + PathStep) into the dependent-
    dropdown vocabulary. Cross-domain aggregation lives here in the service
    layer, not in a single-domain backend (Codex #551 P1)."""

    def _router(self, ku_pairs: list[dict[str, Any]], ps_pairs: list[dict[str, Any]]) -> Any:
        from core.models.enums.entity_enums import EntityType
        from core.models.search.search_router import SearchRouter

        router = SearchRouter.__new__(SearchRouter)
        router.logger = MagicMock()  # type: ignore[misc]
        ku_service = MagicMock()
        ku_service.nous_subtopic_pairs = AsyncMock(return_value=Result.ok(ku_pairs))
        ps_service = MagicMock()
        ps_service.nous_subtopic_pairs = AsyncMock(return_value=Result.ok(ps_pairs))
        services = {EntityType.KU: ku_service, EntityType.PATH_STEP: ps_service}
        router.get_service = MagicMock(side_effect=services.get)  # type: ignore[method-assign]
        return router

    @pytest.mark.asyncio
    async def test_map_merges_ku_and_pathstep_pairs(self) -> None:
        # PathStep contributes (body, attention) — a pair no Ku carries; the
        # merge must fold it in so the facet is complete.
        router = self._router(
            ku_pairs=[
                {"nous": "body", "subtopic": "breath"},
                {"nous": "body", "subtopic": "movement"},
                {"nous": "investment", "subtopic": "compounding"},
            ],
            ps_pairs=[
                {"nous": "body", "subtopic": "attention"},  # PathStep-only pair
                {"nous": "body", "subtopic": "breath"},  # dup across domains
            ],
        )

        result = await router.nous_subtopic_map()

        assert result.is_ok
        assert result.value == {
            "body": ["attention", "breath", "movement"],
            "investment": ["compounding"],
        }

    @pytest.mark.asyncio
    async def test_flat_list_shares_map_source_and_dedupes(self) -> None:
        # The flat vocabulary (which gates whether the /search column renders)
        # MUST share the map's Ku+PathStep source, or a PathStep-only sub-topic
        # corpus would omit the column and orphan those options (Codex #551).
        router = self._router(
            ku_pairs=[{"nous": "self-awareness", "subtopic": "breath"}],
            ps_pairs=[
                {"nous": "body", "subtopic": "movement"},
                {"nous": "body", "subtopic": "breath"},
            ],
        )

        result = await router.list_nous_subtopics()

        assert result.is_ok
        assert result.value == ["breath", "movement"]

    @pytest.mark.asyncio
    async def test_domain_failure_fails_soft(self) -> None:
        # An errored/missing domain contributes nothing rather than failing the
        # whole vocabulary.
        from core.utils.result_simplified import Errors

        router = self._router(
            ku_pairs=[{"nous": "body", "subtopic": "breath"}],
            ps_pairs=[],
        )
        # Make the PS contribution error out.
        from core.models.enums.entity_enums import EntityType

        ps = router.get_service(EntityType.PATH_STEP)
        ps.nous_subtopic_pairs = AsyncMock(
            return_value=Result.fail(
                Errors.database(message="boom", operation="nous_subtopic_pairs")
            )
        )

        result = await router.nous_subtopic_map()

        assert result.is_ok
        assert result.value == {"body": ["breath"]}

    @pytest.mark.asyncio
    async def test_ku_search_service_pairs_passthrough(self) -> None:
        # The per-domain sub-service returns its OWN label's raw pairs (scoped to
        # :Ku) for the router to merge.
        from core.services.ku.ku_search_service import KuSearchService

        service = KuSearchService.__new__(KuSearchService)
        service.backend = MagicMock()  # type: ignore[misc]
        service.backend.nous_subtopic_pairs = AsyncMock(
            return_value=Result.ok([{"nous": "body", "subtopic": "breath"}])
        )

        result = await service.nous_subtopic_pairs()

        assert result.is_ok
        assert result.value == [{"nous": "body", "subtopic": "breath"}]
