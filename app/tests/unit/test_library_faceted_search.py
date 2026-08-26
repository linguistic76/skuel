"""
Library ⇄ SearchRouter consolidation — faceted-path capability tests
=====================================================================

Unit coverage for the July 2026 /explore/library consolidation, which made
SearchRouter.faceted_search the single path for the library catalog and
closed four faceted-path gaps in the process:

1. Real sort — SearchSortOrder plumbed end-to-end (ORDER BY in
   ``faceted_search_raw``; field whitelisted, direction honored).
2. Tags facet — ``tags_contain`` ANY/ALL membership clause in the
   faceted Cypher; CSV ``tags`` param parsed at the form boundary.
3. Pagination — SKIP emission (single-domain) and global-window
   over-fetch + slice (multi-domain sweep).
4. Anonymous browse — PUBLIC-visibility domains take the rich
   graph-aware path without a user; OWNER_ONLY fails closed.
5. Tag vocabulary — ``SearchRouter.tag_frequencies`` Ku+PS aggregation
   (count-summed, most-used first) + the alphabetical ``list_tags`` shape
   derived from it, and the panel's visible/overflow chip split.
6. Route mapping — the library panel's form params onto SearchRequest.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.explore_ui import _library_cards, _library_search_request
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.search.filter_enums import SearchSortOrder
from core.models.search_request import SearchRequest
from core.orchestrator.search_router import SearchRouter
from core.utils.result_simplified import Result
from tests.helpers.faceted_capture import CapturedQuery, run_faceted
from ui.explore.cards import (
    LIBRARY_PAGE_SIZE,
    VISIBLE_TAG_CHIPS,
    render_explore_search_panel,
)

# ============================================================================
# 1. SearchSortOrder mapping
# ============================================================================


class TestSearchSortOrder:
    @pytest.mark.parametrize(
        ("member", "field", "descending"),
        [
            (SearchSortOrder.RELEVANCE, None, True),
            (SearchSortOrder.CREATED_DESC, "created_at", True),
            (SearchSortOrder.CREATED_ASC, "created_at", False),
            (SearchSortOrder.UPDATED_DESC, "updated_at", True),
            (SearchSortOrder.TITLE_ASC, "title", False),
        ],
    )
    def test_field_and_direction(self, member, field, descending) -> None:
        assert member.get_sort_field() == field
        assert member.is_descending() is descending

    def test_from_string_falls_back_to_relevance(self) -> None:
        assert SearchSortOrder.from_string("title_asc") is SearchSortOrder.TITLE_ASC
        assert SearchSortOrder.from_string("bogus") is SearchSortOrder.RELEVANCE
        assert SearchSortOrder.from_string("") is SearchSortOrder.RELEVANCE
        assert SearchSortOrder.from_string(None) is SearchSortOrder.RELEVANCE


class TestFormParamBoundary:
    def test_sort_order_parsed(self) -> None:
        request = SearchRequest.from_form_params(query="x", sort_order="created_asc")
        assert request.get_sort_order() is SearchSortOrder.CREATED_ASC

    def test_tags_csv_parsed_and_trimmed(self) -> None:
        request = SearchRequest.from_form_params(query="x", tags="yoga, mind ,,anxiety")
        assert request.tags_contain == ["yoga", "mind", "anxiety"]
        assert request.has_tag_filter()

    def test_empty_tags_is_no_filter(self) -> None:
        request = SearchRequest.from_form_params(query="x", tags="")
        assert request.tags_contain is None
        assert not request.has_tag_filter()

    def test_get_sort_order_rehydrates_enum_values_string(self) -> None:
        # use_enum_values=True stores the raw string — the accessor re-wraps.
        request = SearchRequest(sort_order=SearchSortOrder.TITLE_ASC)
        assert request.get_sort_order() is SearchSortOrder.TITLE_ASC


# ============================================================================
# 2/3. faceted_search_raw Cypher composition
# ============================================================================


class TestFacetedSearchRawClauses:
    @pytest.mark.asyncio
    async def test_default_order_by_config_field_desc(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store)
        assert "ORDER BY entity.updated_at DESC" in store["query"]
        assert "SKIP" not in store["query"]

    @pytest.mark.asyncio
    async def test_explicit_sort_overrides_direction_and_field(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store, order_by="title", order_desc=False)
        assert "ORDER BY entity.title ASC" in store["query"]

    @pytest.mark.asyncio
    async def test_offset_emits_skip_before_limit(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store, offset=24, limit=24)
        query = store["query"]
        assert "SKIP 24" in query
        assert query.index("SKIP 24") < query.index("LIMIT 24")

    @pytest.mark.asyncio
    async def test_tags_any_semantics(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store, tags_contain=["yoga", "mind"])
        assert "ANY(t IN $tags_contain WHERE t IN entity.tags)" in store["query"]
        assert store["params"]["tags_contain"] == ["yoga", "mind"]

    @pytest.mark.asyncio
    async def test_tags_all_semantics(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store, tags_contain=["yoga"], tags_match_all=True)
        assert "ALL(t IN $tags_contain WHERE t IN entity.tags)" in store["query"]

    @pytest.mark.asyncio
    async def test_malicious_sort_field_rejected_before_query(self) -> None:
        # _validate_identifier raises; safe_backend_operation converts to a
        # failed Result. Either way the injection must never reach the driver.
        store: CapturedQuery = {}
        result = await run_faceted(store, order_by="title DESC; MATCH (n) DETACH DELETE n //")
        assert result.is_error
        assert "query" not in store  # never reached the driver

    @pytest.mark.asyncio
    async def test_empty_query_text_omits_text_clause(self) -> None:
        store: CapturedQuery = {}
        await run_faceted(store, query_text=None)
        assert "CONTAINS" not in store["query"]


# ============================================================================
# 4. Router gates — anonymous PUBLIC browse + empty-query sweep
# ============================================================================


def _graph_aware_service(
    records: list[dict[str, Any]],
    visibility: SearchVisibility = SearchVisibility.PUBLIC,
) -> MagicMock:
    service = MagicMock()
    # Protocol isinstance uses getattr_static (Py 3.12+) — SupportsGraphAwareSearch
    # members must be REAL attributes on the mock, not lazily-created ones.
    service.graph_aware_faceted_search = AsyncMock(return_value=Result.ok(records))
    service.search_visibility = visibility
    return service


class TestAnonymousGates:
    @pytest.mark.asyncio
    async def test_anon_public_single_domain_takes_rich_path(self) -> None:
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        router = SearchRouter(ku=ku, event_bus=None)

        result = await router.faceted_search(
            SearchRequest(entity_types=[EntityType.KU]), user_uid=None
        )

        assert result.is_ok
        assert [r["uid"] for r in result.value.results] == ["ku_1"]
        ku.graph_aware_faceted_search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_anon_owner_only_domain_skipped_in_sweep(self) -> None:
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        tasks = _graph_aware_service(
            [{"uid": "task_1", "title": "T", "_domain": "task"}],
            visibility=SearchVisibility.OWNER_ONLY,
        )
        router = SearchRouter(ku=ku, tasks=tasks, event_bus=None)

        results = await router._faceted_sweep(
            SearchRequest(), None, [EntityType.KU, EntityType.TASK]
        )

        assert [r["uid"] for r in results] == ["ku_1"]
        tasks.graph_aware_faceted_search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_query_multi_domain_routes_to_faceted_sweep(self) -> None:
        router = SearchRouter()
        router._faceted_sweep = AsyncMock(return_value=[])  # type: ignore[method-assign]
        router.search_domains = AsyncMock()  # type: ignore[method-assign]

        request = SearchRequest(entity_types=[EntityType.KU, EntityType.PATH_STEP])
        await router._cross_domain_search(request, user_uid=None)

        router._faceted_sweep.assert_awaited_once()
        router.search_domains.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_text_query_with_explicit_sort_routes_to_faceted_sweep(self) -> None:
        # The library's All-Types text search carries an explicit sort
        # (created_desc/title_asc). The scored text sweep ignores sort and
        # offset and caps at limit//6 minimal records per domain — an explicit
        # sort must force the faceted sweep (Codex, PR #669).
        router = SearchRouter()
        router._faceted_sweep = AsyncMock(return_value=[])  # type: ignore[method-assign]
        router.search_domains = AsyncMock()  # type: ignore[method-assign]

        request = SearchRequest(
            query_text="breath",
            entity_types=[EntityType.KU, EntityType.PATH_STEP],
            sort_order=SearchSortOrder.CREATED_DESC,
        )
        await router._cross_domain_search(request, user_uid=None)

        router._faceted_sweep.assert_awaited_once()
        router.search_domains.assert_not_awaited()


class TestSweepMergeAndPagination:
    @pytest.mark.asyncio
    async def test_explicit_sort_merges_across_domains(self) -> None:
        ku = _graph_aware_service(
            [
                {"uid": "ku_b", "title": "Banana", "_domain": "ku"},
                {"uid": "ku_z", "title": "zebra", "_domain": "ku"},
            ]
        )
        ps = _graph_aware_service([{"uid": "ps_a", "title": "Apple", "_domain": "path_step"}])
        router = SearchRouter(ku=ku, ps=ps, event_bus=None)

        request = SearchRequest(sort_order=SearchSortOrder.TITLE_ASC)
        results = await router._faceted_sweep(
            request, "user_x", [EntityType.KU, EntityType.PATH_STEP]
        )

        # Case-insensitive title merge across both domains
        assert [r["uid"] for r in results] == ["ps_a", "ku_b", "ku_z"]

    @pytest.mark.asyncio
    async def test_sweep_returns_full_dicts(self) -> None:
        record = {
            "uid": "ps_1",
            "title": "Step",
            "_domain": "path_step",
            "tags": ["yoga"],
            "created_at": "2026-01-01T00:00:00",
            "learning_level": "beginner",
            "estimated_time_minutes": 15,
        }
        ps = _graph_aware_service([record])
        router = SearchRouter(ps=ps, event_bus=None)

        results = await router._faceted_sweep(SearchRequest(), "user_x", [EntityType.PATH_STEP])

        assert results[0]["tags"] == ["yoga"]
        assert results[0]["estimated_time_minutes"] == 15

    @pytest.mark.asyncio
    async def test_offset_slices_merged_window(self) -> None:
        ku = _graph_aware_service(
            [{"uid": f"ku_{i}", "title": f"T{i:02d}", "_domain": "ku"} for i in range(5)]
        )
        router = SearchRouter(ku=ku, event_bus=None)

        request = SearchRequest(sort_order=SearchSortOrder.TITLE_ASC, limit=2, offset=2)
        results = await router._faceted_sweep(request, "user_x", [EntityType.KU])

        assert [r["uid"] for r in results] == ["ku_2", "ku_3"]
        # Domain call over-fetched the whole window from 0 (offset+limit, offset=0)
        window_request = ku.graph_aware_faceted_search.await_args.kwargs["request"]
        assert window_request.limit == 4
        assert window_request.offset == 0


# ============================================================================
# 5. Tag vocabulary aggregation
# ============================================================================


class _TagSearchSub:
    """Stand-in for a domain's SEARCH SUB-SERVICE, shaped like the real one.

    `SearchRouter._get_search_service` rejects a bare MagicMock on purpose: it
    requires `.search` to be a non-callable attribute holding the sub-service
    (a MagicMock's `.search` is itself callable, so it reads as a method). The
    tag vocabulary then narrows that sub-service to `SupportsTagVocabulary`, so
    the double must carry BOTH halves the router reads — the visibility
    declaration and the counts — or the fixture would pass while the real
    wiring could not.
    """

    def __init__(
        self,
        frequencies: Any,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
        ownership_property: str = "user_uid",
    ) -> None:
        self.search_visibility = visibility
        self.ownership_property = ownership_property
        self._frequencies = frequencies
        self.scopes_received: list[Any] = []

    async def search(self, *_args: Any, **_kwargs: Any) -> Result[list[Any]]:
        return Result.ok([])

    async def tag_frequencies(self, user_uid: Any = None) -> Result[dict[str, int]]:
        self.scopes_received.append(user_uid)
        if isinstance(self._frequencies, Result):
            return self._frequencies
        return Result.ok(self._frequencies)


class _TagDomain:
    """A domain facade double whose `.search` is the sub-service, not a method."""

    def __init__(
        self,
        frequencies: Any,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
        ownership_property: str = "user_uid",
    ) -> None:
        self.search = _TagSearchSub(frequencies, visibility, ownership_property)


class TestTagVocabulary:
    @pytest.mark.asyncio
    async def test_frequencies_sum_across_domains_most_used_first(self) -> None:
        ku = _TagDomain({"yoga": 2, "mind": 1})
        ps = _TagDomain({"yoga": 3, "attention": 1})
        router = SearchRouter(ku=ku, ps=ps)

        result = await router.tag_frequencies()

        assert result.is_ok
        assert result.value == [
            {"tag": "yoga", "count": 5},
            {"tag": "attention", "count": 1},
            {"tag": "mind", "count": 1},
        ]

    @pytest.mark.asyncio
    async def test_frequency_ties_break_alphabetically(self) -> None:
        ku = _TagDomain({"zen": 1, "action": 1})
        ps = _TagDomain({})
        router = SearchRouter(ku=ku, ps=ps)

        result = await router.tag_frequencies()

        assert [item["tag"] for item in result.value] == ["action", "zen"]

    @pytest.mark.asyncio
    async def test_list_tags_derives_alphabetical_unique(self) -> None:
        ku = _TagDomain({"yoga": 2, "mind": 1})
        ps = _TagDomain({"yoga": 9, "attention": 1})
        router = SearchRouter(ku=ku, ps=ps)

        result = await router.list_tags()

        assert result.is_ok
        assert result.value == ["attention", "mind", "yoga"]

    @pytest.mark.asyncio
    async def test_fails_soft_per_domain(self) -> None:
        ku = _TagDomain(Result.fail(MagicMock(is_error=True)))
        ps = _TagDomain({"attention": 1})
        router = SearchRouter(ku=ku, ps=ps)

        result = await router.list_tags()

        assert result.is_ok
        assert result.value == ["attention"]


class TestSearchPanelTagChips:
    """Visible/overflow split of the frequency-ranked chip row."""

    def _tags(self, n: int) -> list[str]:
        return [f"tag{i:03d}" for i in range(n)]

    def test_few_tags_render_without_expander(self) -> None:
        html = to_xml(render_explore_search_panel(self._tags(5)))
        assert html.count("#tag0") == 5
        assert "showAllTags" not in html

    def test_overflow_tags_are_cloaked_behind_expander(self) -> None:
        html = to_xml(render_explore_search_panel(self._tags(VISIBLE_TAG_CHIPS + 6)))
        # Every tag renders (full vocabulary reachable), overflow x-cloaked.
        assert html.count("setTag(") == VISIBLE_TAG_CHIPS + 6
        assert html.count("x-cloak") == 6
        assert "'+6 more'" in html
        # Collapsed by default when no active tag is hidden.
        assert "{ showAllTags: false }" in html

    def test_active_tag_in_overflow_starts_expanded(self) -> None:
        tags = self._tags(VISIBLE_TAG_CHIPS + 2)
        html = to_xml(render_explore_search_panel(tags, active_tag=tags[-1]))
        assert "{ showAllTags: true }" in html


# ============================================================================
# 6. Library route param mapping + card assembly
# ============================================================================


class TestLibrarySearchRequest:
    def test_all_types_browse_defaults(self) -> None:
        request = _library_search_request("", "", "", SearchSortOrder.CREATED_DESC.value, 0)
        assert request.query_text is None
        assert len(request.entity_types) == 2
        assert request.tags_contain is None
        assert request.get_sort_order() is SearchSortOrder.CREATED_DESC
        assert request.limit == LIBRARY_PAGE_SIZE
        assert request.offset == 0

    def test_ps_alias_resolves_at_boundary(self) -> None:
        request = _library_search_request("", "ps", "", SearchSortOrder.CREATED_DESC.value, 0)
        assert request.entity_types == [EntityType.PATH_STEP.value]

    def test_tag_and_title_sort_and_offset(self) -> None:
        # The library speaks canonical SearchSortOrder values (title_asc), not
        # the former "title" shorthand.
        request = _library_search_request(
            "breath", "ku", "yoga", SearchSortOrder.TITLE_ASC.value, 24
        )
        assert request.query_text == "breath"
        assert request.tags_contain == ["yoga"]
        assert request.get_sort_order() is SearchSortOrder.TITLE_ASC
        assert request.offset == 24

    def test_unknown_sort_falls_back_to_newest(self) -> None:
        request = _library_search_request("", "", "", "bogus", 0)
        assert request.get_sort_order() is SearchSortOrder.CREATED_DESC

    def test_relevance_sort_clamped_to_newest(self) -> None:
        # RELEVANCE parses cleanly but is NOT a catalog sort: for an All-Types
        # text query it drops into SearchRouter's non-pageable scored sweep and
        # starves the grid. The route clamps it back to the browse default so a
        # crafted ?sort=relevance can't reopen that hole (Codex #778).
        request = _library_search_request("breath", "", "", SearchSortOrder.RELEVANCE.value, 0)
        assert request.get_sort_order() is SearchSortOrder.CREATED_DESC


class TestLibraryCards:
    def _records(self, n: int) -> list[dict[str, Any]]:
        return [{"uid": f"ku_{i}", "title": f"K{i}", "_domain": "ku"} for i in range(n)]

    def test_full_page_appends_load_more_sentinel(self) -> None:
        cards = _library_cards(self._records(LIBRARY_PAGE_SIZE), set(), {}, offset=0)
        assert len(cards) == LIBRARY_PAGE_SIZE + 1  # cards + sentinel

    def test_short_page_has_no_sentinel(self) -> None:
        cards = _library_cards(self._records(3), set(), {}, offset=0)
        assert len(cards) == 3


# ============================================================================
# 5b. Tag vocabulary — scope widening and per-domain ownership (PR-4b)
# ============================================================================


class TestTagVocabularyScope:
    """`tags` is an Entity base field, so the vocabulary follows the SURFACE's
    result set — not the curriculum catalog. Ownership is enforced per domain
    and fails CLOSED: an OWNER_ONLY domain is skipped rather than counted
    unscoped, because an unscoped count lists every user's tag names.

    The negative control is `TestTagVocabulary` above: the default scope must
    stay curriculum-only and unscoped, because /explore/library is anonymous.
    """

    @staticmethod
    def _router() -> tuple[Any, Any, Any]:
        ku = _TagDomain({"breath": 4}, SearchVisibility.PUBLIC)
        tasks = _TagDomain({"errand": 2}, SearchVisibility.OWNER_ONLY)
        return SearchRouter(ku=ku, tasks=tasks), ku, tasks

    @pytest.mark.asyncio
    async def test_activity_tags_join_the_vocabulary_at_page_scope(self) -> None:
        router, _ku, _tasks = self._router()

        result = await router.list_tags((EntityType.KU, EntityType.TASK), "user_alice")

        assert result.value == ["breath", "errand"]

    @pytest.mark.asyncio
    async def test_owner_only_domain_is_skipped_without_a_user(self) -> None:
        # Fail CLOSED. Counting it unscoped would hand every caller the whole
        # tenant's tag names, which is a leak, not a wider vocabulary.
        router, _ku, tasks = self._router()

        result = await router.list_tags((EntityType.KU, EntityType.TASK))

        assert result.value == ["breath"]
        assert tasks.search.scopes_received == []

    @pytest.mark.asyncio
    async def test_each_domain_is_asked_at_its_own_declared_scope(self) -> None:
        # THE privacy assertion: PUBLIC curriculum is counted corpus-wide
        # (None), the OWNER_ONLY domain for the caller ALONE. Asserting the
        # returned tags alone would pass even if the activity domain had been
        # queried unscoped and merely happened to hold one user's data.
        router, ku, tasks = self._router()

        await router.list_tags((EntityType.KU, EntityType.TASK), "user_alice")

        assert ku.search.scopes_received == [None]
        assert tasks.search.scopes_received == ["user_alice"]

    @pytest.mark.asyncio
    async def test_scope_aware_domain_is_skipped_rather_than_property_scoped(self) -> None:
        # SCOPE_AWARE scope lives in :OWNS / :SHARES_WITH / group edges, which
        # a `user_uid` property filter cannot express — it would silently drop
        # shared rows and misreport the rest. Refusing beats answering wrongly.
        exercises = _TagDomain({"drill": 1}, SearchVisibility.SCOPE_AWARE)
        router = SearchRouter(ku=_TagDomain({"breath": 1}), exercises=exercises)

        result = await router.list_tags((EntityType.KU, EntityType.EXERCISE), "user_alice")

        assert result.value == ["breath"]
        assert exercises.search.scopes_received == []

    @pytest.mark.asyncio
    async def test_a_domain_scoping_another_property_is_refused(self) -> None:
        # The vocabulary query scopes on `user_uid` specifically. A domain that
        # declares a different ownership property (Group: `owner_uid`, ADR-086)
        # would be filtered on a property it does not write — returning its
        # tags for nobody, silently. Refuse rather than guess.
        odd = _TagDomain({"secret": 1}, SearchVisibility.OWNER_ONLY, "owner_uid")
        router = SearchRouter(ku=_TagDomain({"breath": 1}), tasks=odd)

        result = await router.list_tags((EntityType.KU, EntityType.TASK), "user_alice")

        assert result.value == ["breath"]
        assert odd.search.scopes_received == []

    @pytest.mark.asyncio
    async def test_the_library_default_never_reaches_an_activity_domain(self) -> None:
        # /explore/library is ANONYMOUS. The default scope must stay the
        # curriculum pair, asked corpus-wide, with no user in play.
        router, ku, tasks = self._router()

        await router.list_tags()

        assert ku.search.scopes_received == [None]
        assert tasks.search.scopes_received == []
