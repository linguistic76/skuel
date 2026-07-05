"""
SearchRouter registry completeness + UserEntry privacy guards.

The class of bug these tests prevent: ``_SEARCHABLE_DOMAINS`` promising a
domain whose ``_SERVICE_REGISTRY`` attribute the ``Services`` container never
composes. That combination made ``supports_search()`` lie and ``search()``
silently return not_found — user entries were unsearchable for months while
every surface claimed otherwise.

No live database needed: the registry guards introspect the ``Services``
dataclass fields; the routing guards monkeypatch the router's internals.
"""

import dataclasses
from types import SimpleNamespace

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.search.search_router import SearchRouter, UnifiedSearchResult
from core.models.search_request import SearchRequest
from services_bootstrap import Services

SERVICES_FIELD_NAMES = {f.name for f in dataclasses.fields(Services)}


class TestRegistryCompleteness:
    """Every searchable domain must resolve to a real Services field."""

    def test_searchable_domains_are_registered(self) -> None:
        """Every _SEARCHABLE_DOMAINS member has a _SERVICE_REGISTRY entry."""
        unregistered = [
            et
            for et in SearchRouter._SEARCHABLE_DOMAINS
            if et not in SearchRouter._SERVICE_REGISTRY
        ]
        assert not unregistered, (
            f"_SEARCHABLE_DOMAINS promises search for {unregistered} but "
            "_SERVICE_REGISTRY has no service attribute for them — "
            "supports_search() lies and search() silently returns not_found."
        )

    def test_registry_attributes_exist_on_services_container(self) -> None:
        """Every _SERVICE_REGISTRY value is an actual Services dataclass field."""
        phantom = {
            et: attr
            for et, attr in SearchRouter._SERVICE_REGISTRY.items()
            if attr not in SERVICES_FIELD_NAMES
        }
        assert not phantom, (
            f"_SERVICE_REGISTRY points at Services attributes that do not exist: {phantom}. "
            "getattr(services, attr, None) degrades this to a silent not_found at runtime."
        )

    def test_graph_aware_domain_strings_exist_on_services_container(self) -> None:
        """_GRAPH_AWARE_DOMAINS strings are used directly as Services attributes."""
        phantom = sorted(SearchRouter._GRAPH_AWARE_DOMAINS - SERVICES_FIELD_NAMES)
        assert not phantom, (
            f"_GRAPH_AWARE_DOMAINS names Services attributes that do not exist: {phantom}. "
            "This is how the stale 'submissions' → 'submissions_search' alias shipped broken."
        )


class TestUserEntryPrivacyLine:
    """Unscoped UserEntry search must be refused, never leaked."""

    @pytest.mark.asyncio
    async def test_search_without_user_uid_is_refused(self) -> None:
        router = SearchRouter(services=SimpleNamespace())

        result = await router.search(EntityType.USER_ENTRY, "anything")

        assert result.is_error
        assert "user scope" in str(result.expect_error().message)

    @pytest.mark.asyncio
    async def test_cross_domain_sweep_excludes_user_entry(self, monkeypatch) -> None:
        """The 'All Types' sweep never touches the UserEntry store."""
        router = SearchRouter(services=SimpleNamespace())
        captured: dict[str, list] = {}

        async def fake_search_domains(entity_types, query, limit_per_domain=20, user_uid=None):
            captured["types"] = list(entity_types)
            return UnifiedSearchResult(query=query, results_by_domain={}, total_count=0)

        monkeypatch.setattr(router, "search_domains", fake_search_domains)

        request = SearchRequest(query_text="anything")
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert EntityType.USER_ENTRY not in captured["types"]
        assert EntityType.TASK in captured["types"]

    @pytest.mark.asyncio
    async def test_advanced_search_skips_user_entry(self) -> None:
        """Cross-domain advanced search (unscoped strategies) skips UserEntry.

        The empty Services namespace would raise (→ error Result) if the loop
        reached get_service, so an ok/empty result proves the skip fired first.
        """
        router = SearchRouter(services=SimpleNamespace())

        request = SearchRequest(query_text="anything", entity_types=[EntityType.USER_ENTRY])
        result = await router.advanced_search(request)

        assert result.is_ok
        assert result.value.total_count == 0
        assert not result.value.results_by_domain


class TestSingleEntityTypeRouting:
    """The /search dropdown filter routes to the single-domain path."""

    def test_user_entry_filter_resolves_to_user_entry_domain(self) -> None:
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x", entity_types=[EntityType.USER_ENTRY])

        assert router._resolve_single_domain(request) == "user_entry"

    def test_task_filter_resolves_to_tasks_domain(self) -> None:
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x", entity_types=[EntityType.TASK])

        assert router._resolve_single_domain(request) == "tasks"

    def test_no_filter_resolves_to_none(self) -> None:
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x")

        assert router._resolve_single_domain(request) is None

    def test_multiple_filters_resolve_to_none(self) -> None:
        """Two or more entity types stay on the cross-domain path."""
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x", entity_types=[EntityType.TASK, EntityType.GOAL])

        assert router._resolve_single_domain(request) is None

    @pytest.mark.asyncio
    async def test_user_entry_filter_routes_graph_aware_with_user(self, monkeypatch) -> None:
        """user_entry filter + user → OWNS-scoped graph-aware domain search."""
        router = SearchRouter(services=SimpleNamespace())
        captured: dict[str, str] = {}

        async def fake_graph_aware(request, user_uid, domain_str):
            captured["domain"] = domain_str
            captured["user_uid"] = user_uid
            from core.models.search_request import SearchResponse
            from core.utils.result_simplified import Result

            return Result.ok(
                SearchResponse(
                    results=[],
                    total=0,
                    limit=request.limit,
                    offset=request.offset,
                    query_text=request.query_text,
                    domain=domain_str,
                    facet_counts={},
                    applied_filters={},
                    search_time_ms=0.0,
                )
            )

        monkeypatch.setattr(router, "_graph_aware_domain_search", fake_graph_aware)

        request = SearchRequest(query_text="tasks list", entity_types=[EntityType.USER_ENTRY])
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert captured["domain"] == "user_entry"
        assert captured["user_uid"] == "user_a"
