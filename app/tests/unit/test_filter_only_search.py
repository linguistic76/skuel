"""Filter-only faceted search: a filter alone defines a valid search.

The /search route used to short-circuit on an empty query string, so a facet
(e.g. NOUS topic = body, Type = Tasks) could never filter on its own. The
emptiness decision now lives on the built request via
``SearchRequest.has_any_criteria()`` — the blank initial state shows the prompt,
while a filter-only request runs. These tests pin that contract:

- ``has_any_criteria()`` is True for query-only, filter-only, and hybrid; False
  only for a genuinely blank request or a bare enhancement toggle.
- ``from_form_params`` normalizes an empty query to ``None`` (filter-only is
  valid; a bare "" would otherwise trip ``validate_query_text``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import (
    ContentType,
    Domain,
    EntityStatus,
    EntityType,
    LearningLevel,
    Priority,
    SELCategory,
)
from core.models.search_request import SearchRequest
from core.orchestrator.search_router import SearchRouter


class TestHasAnyCriteria:
    def test_blank_request_has_no_criteria(self) -> None:
        assert SearchRequest().has_any_criteria() is False

    def test_query_only_has_criteria(self) -> None:
        assert SearchRequest(query_text="meditation").has_any_criteria() is True

    def test_property_facet_alone_has_criteria(self) -> None:
        assert SearchRequest(nous="body").has_any_criteria() is True
        assert SearchRequest(priority=Priority.HIGH).has_any_criteria() is True
        assert SearchRequest(sel_category=SELCategory.SELF_AWARENESS).has_any_criteria() is True
        assert SearchRequest(nous_subtopic="sleep").has_any_criteria() is True

    def test_entity_type_scope_alone_has_criteria(self) -> None:
        # "Browse all my Tasks" — a domain scope with no query is a real search.
        assert SearchRequest(entity_types=[EntityType.TASK]).has_any_criteria() is True

    def test_domain_scope_alone_has_criteria(self) -> None:
        # Programmatic domain-only path (not the UI's entity_types) — still a
        # real search, since _resolve_single_domain routes request.domain.
        assert SearchRequest(domain=Domain.TASKS).has_any_criteria() is True

    def test_relationship_flag_alone_has_criteria(self) -> None:
        assert SearchRequest(ready_to_learn=True).has_any_criteria() is True

    def test_tag_filter_alone_has_criteria(self) -> None:
        assert SearchRequest(tags_contain=["python"]).has_any_criteria() is True

    def test_enhancement_toggle_alone_is_not_criteria(self) -> None:
        # Semantic boost / learning-aware re-rank a result set; they do not
        # define one, so they cannot stand in for a query or filter.
        assert SearchRequest(enable_semantic_boost=True).has_any_criteria() is False
        assert SearchRequest(enable_learning_aware=True).has_any_criteria() is False

    def test_hybrid_query_plus_filter_has_criteria(self) -> None:
        request = SearchRequest(query_text="breath", nous="body", domain=Domain.KNOWLEDGE)
        assert request.has_any_criteria() is True


class TestFromFormParamsEmptyQuery:
    def test_empty_query_normalizes_to_none(self) -> None:
        # No short-circuit needed: "" → None, and the model accepts it.
        request = SearchRequest.from_form_params(query="")
        assert request.query_text is None

    def test_whitespace_query_normalizes_to_none(self) -> None:
        request = SearchRequest.from_form_params(query="   ")
        assert request.query_text is None

    def test_empty_query_with_facet_is_filter_only_search(self) -> None:
        request = SearchRequest.from_form_params(query="", nous="body")
        assert request.query_text is None
        assert request.to_property_filters()["nous"] == "body"
        assert request.has_any_criteria() is True

    def test_empty_query_with_entity_type_is_filter_only_search(self) -> None:
        # "task" is what the /search Type dropdown emits (singular EntityType value).
        request = SearchRequest.from_form_params(query="", entity_type="task")
        assert request.query_text is None
        assert request.entity_types == [EntityType.TASK]
        assert request.has_any_criteria() is True

    def test_empty_query_and_no_filters_is_blank(self) -> None:
        # The blank initial state — route shows the prompt, does not search.
        request = SearchRequest.from_form_params(query="")
        assert request.has_any_criteria() is False

    def test_hybrid_form_params_preserves_query_and_facets(self) -> None:
        request = SearchRequest.from_form_params(
            query="mindfulness",
            learning_level="beginner",
            content_type="practice",
        )
        assert request.query_text == "mindfulness"
        assert request.learning_level == LearningLevel.BEGINNER
        assert request.content_type == ContentType.PRACTICE
        assert request.has_any_criteria() is True


class TestFromFormParamsTolerantFacets:
    """An unrecognized enum facet value drops to None (no filter) — it must not
    abort the whole search.

    Facet values arrive from the client and can be stale: a service-worker- or
    bfcache-cached older page after a deploy, a hand-edited URL, a replayed
    request. Before this, ``from_form_params`` fed each facet straight into its
    enum constructor, so one junk value (observed live: ``priority='u=4'`` from a
    stale client) raised ``ValueError`` and the route rendered "Invalid filter
    selection", killing an otherwise-valid search.
    """

    def test_unknown_priority_is_dropped(self) -> None:
        request = SearchRequest.from_form_params(query="test", priority="u=4")
        assert request.priority is None
        assert request.query_text == "test"

    def test_valid_priority_is_preserved(self) -> None:
        request = SearchRequest.from_form_params(query="test", priority="high")
        assert request.priority == Priority.HIGH

    def test_bad_facet_does_not_drop_sibling_valid_facets(self) -> None:
        # A junk priority must not take down the whole request — the valid
        # status facet survives and the search still runs.
        request = SearchRequest.from_form_params(
            query="", priority="u=4", status="draft", learning_level="bogus"
        )
        assert request.priority is None
        assert request.learning_level is None
        assert request.status == EntityStatus.DRAFT
        assert request.has_any_criteria() is True

    def test_all_enum_facets_tolerate_junk(self) -> None:
        request = SearchRequest.from_form_params(
            query="test",
            status="nope",
            priority="nope",
            sel_category="nope",
            learning_level="nope",
            content_type="nope",
            educational_level="nope",
        )
        assert request.status is None
        assert request.priority is None
        assert request.sel_category is None
        assert request.learning_level is None
        assert request.content_type is None
        assert request.educational_level is None


class TestCrossDomainRoutesRelationshipOnly:
    """A relationship-only, empty-query, Type=All request must reach the
    faceted sweep — not the plain text sweep, which drops the filter (PR #549).
    """

    @pytest.mark.anyio
    async def test_relationship_only_routes_to_faceted_sweep(self) -> None:
        router = SearchRouter()
        router._faceted_sweep = AsyncMock(return_value=[])  # type: ignore[method-assign]
        router.search_domains = AsyncMock()  # type: ignore[method-assign]

        request = SearchRequest(ready_to_learn=True)  # no query, no property facet
        await router._cross_domain_search(request, user_uid="user_x")

        router._faceted_sweep.assert_awaited_once()
        router.search_domains.assert_not_awaited()

    @pytest.mark.anyio
    async def test_blank_request_routes_to_faceted_sweep(self) -> None:
        # Empty-query browse (July 2026, /explore/library consolidation): a
        # request with no query text routes through the faceted sweep — the
        # plain text sweep would hard-reject the empty query per domain.
        router = SearchRouter()
        router._faceted_sweep = AsyncMock(return_value=[])  # type: ignore[method-assign]
        router.search_domains = AsyncMock()  # type: ignore[method-assign]

        await router._cross_domain_search(SearchRequest(), user_uid="user_x")

        router._faceted_sweep.assert_awaited_once()
        router.search_domains.assert_not_awaited()

    @pytest.mark.anyio
    async def test_query_only_request_uses_plain_text_sweep(self) -> None:
        # Sanity control: query text with no filters still rides the scored
        # plain text sweep (relevance ranking), not the faceted sweep.
        router = SearchRouter()
        router._faceted_sweep = AsyncMock()  # type: ignore[method-assign]
        router.search_domains = AsyncMock(return_value=MagicMock(results_by_domain={}))  # type: ignore[method-assign]

        await router._cross_domain_search(SearchRequest(query_text="breath"), user_uid="user_x")

        router._faceted_sweep.assert_not_awaited()
        router.search_domains.assert_awaited_once()
