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

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.ps_content.content_chunks import ContentChunkType
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
        """The default 'All Types' sweep never touches the UserEntry store."""
        router = SearchRouter(services=SimpleNamespace())
        swept_types: list[EntityType | NonKuDomain] = []
        swept_uids: list[str | None] = []

        async def fake_search_domains(entity_types, query, limit_per_domain=20, user_uid=None):
            swept_types.extend(entity_types)
            swept_uids.append(user_uid)
            return UnifiedSearchResult(query=query, results_by_domain={}, total_count=0)

        monkeypatch.setattr(router, "search_domains", fake_search_domains)

        request = SearchRequest(query_text="anything")
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert EntityType.USER_ENTRY not in swept_types
        assert EntityType.TASK in swept_types
        # Owner scope threads through so user-owned domains filter server-side
        assert swept_uids == ["user_a"]

    @pytest.mark.asyncio
    async def test_explicit_multi_type_filter_includes_user_entry(self, monkeypatch) -> None:
        """[USER_ENTRY, TASK] narrows the sweep and keeps entries (scoped)."""
        router = SearchRouter(services=SimpleNamespace())
        swept_types: list[EntityType | NonKuDomain] = []
        swept_uids: list[str | None] = []

        async def fake_search_domains(entity_types, query, limit_per_domain=20, user_uid=None):
            swept_types.extend(entity_types)
            swept_uids.append(user_uid)
            return UnifiedSearchResult(query=query, results_by_domain={}, total_count=0)

        monkeypatch.setattr(router, "search_domains", fake_search_domains)

        request = SearchRequest(
            query_text="anything", entity_types=[EntityType.USER_ENTRY, EntityType.TASK]
        )
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert swept_types == [EntityType.USER_ENTRY, EntityType.TASK]
        assert swept_uids == ["user_a"]

    @pytest.mark.asyncio
    async def test_faceted_user_entry_without_user_is_refused(self) -> None:
        """A user_entry faceted request with no user fails loudly, not empty-ok."""
        router = SearchRouter(services=SimpleNamespace())

        request = SearchRequest(query_text="anything", entity_types=[EntityType.USER_ENTRY])
        result = await router.faceted_search(request, user_uid=None)

        assert result.is_error
        assert "user scope" in str(result.expect_error().message)

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

    def test_ku_filter_resolves_to_ku_domain(self) -> None:
        """Ku is a searchable curriculum domain — the /search 'Knowledge
        Units' dropdown option routes to the single-domain path."""
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x", entity_types=[EntityType.KU])

        assert router._resolve_single_domain(request) == "ku"

    def test_non_searchable_type_resolves_to_none(self) -> None:
        """LIFE_PATH is registered for get_service but NOT searchable — the
        dropdown filter must stay consistent with search()'s supports_search()
        gate."""
        router = SearchRouter(services=SimpleNamespace())
        request = SearchRequest(query_text="x", entity_types=[EntityType.LIFE_PATH])

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


class TestBodyChunkAggregation:
    """Parent-dedup + best-chunk-score aggregation for lesson-BODY search.

    DB-free: exercises SearchRouter._aggregate_body_chunk_parents directly with
    fabricated :ContentChunk hit dicts. Guards the merge/dedup contract that the
    body-chunk augmentation relies on — max score per parent, scope filtering,
    and dedupe against parents already in the base results.
    """

    @staticmethod
    def _hit(parent_uid: str, parent_type: str, score: float, text: str = "body prose") -> dict:
        return {
            "chunk_uid": f"chunk_{parent_uid}_{score}",
            # A real persisted value — "CONCEPT" is not a ContentChunkType member
            # at all, so no writer could ever produce it.
            "chunk_type": ContentChunkType.EXPLANATION.value,
            "text": text,
            "context_window": None,
            "similarity_score": score,
            "parent_uid": parent_uid,
            "parent_title": parent_uid.split(".")[-1].title(),
            "parent_entity_type": parent_type,
        }

    def test_best_score_per_parent(self) -> None:
        """Multiple chunks of one parent collapse to a single card at MAX score."""
        hits = [
            self._hit("ku.discipline.visualization", "ku", 0.71, "first passage"),
            self._hit("ku.discipline.visualization", "ku", 0.88, "best passage"),
            self._hit("ku.discipline.visualization", "ku", 0.75, "third passage"),
        ]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids=set()
        )
        assert len(results) == 1
        card = results[0]
        assert card["uid"] == "ku.discipline.visualization"
        assert card["_domain"] == "ku"
        assert card["_score"] == 0.88
        assert card["description"] == "best passage"

    def test_dedupes_against_existing_parents(self) -> None:
        """A parent already in the base results is not re-listed as a body hit."""
        hits = [self._hit("ku.discipline.visualization", "ku", 0.9)]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids={"ku.discipline.visualization"}
        )
        assert results == []

    def test_scope_filters_out_of_target_types(self) -> None:
        """Parents outside the in-scope curriculum types are dropped."""
        hits = [
            self._hit("ku.a", "ku", 0.9),
            self._hit("ps.b", "path_step", 0.95),
        ]
        # Single-domain Ku search: only Ku parents survive.
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids=set()
        )
        assert [r["uid"] for r in results] == ["ku.a"]

    def test_cross_domain_ranks_both_types_by_score(self) -> None:
        """Cross-domain scope keeps Ku and PS, ranked by best-chunk score desc."""
        hits = [
            self._hit("ku.a", "ku", 0.80),
            self._hit("ps.b", "path_step", 0.92),
            self._hit("ku.c", "ku", 0.85),
        ]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku", "path_step"}), existing_uids=set()
        )
        assert [r["uid"] for r in results] == ["ps.b", "ku.c", "ku.a"]
        assert [r["_domain"] for r in results] == ["path_step", "ku", "ku"]

    def test_empty_hits_returns_empty(self) -> None:
        """No chunk hits → no body cards."""
        assert SearchRouter._aggregate_body_chunk_parents([], frozenset({"ku"}), set()) == []
