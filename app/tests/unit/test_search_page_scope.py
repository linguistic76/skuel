"""
`/search` result scope — the 6 Activity Domains + Ku
=====================================================

The facet redesign's first rung (`docs/roadmap/deferred-work.md` §
"`/search` Facet Redesign"): the page states which domains it searches instead
of inheriting SearchRouter's cross-domain sweep default (every searchable
domain except UserEntry). Ruling 1 of that section — **removal is from the
RESULTS, not just the filter** — is what these tests pin: an unfiltered
`/search` must not return a PathStep, LearningPath, Exercise, RevisedExercise
or UserEntry that no facet on the page can filter to or away.

The negative control is `/explore/library`, which shares `faceted_search` and
must keep its merged Ku + PathStep catalog — including the lesson-body half.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.inbound.explore_ui import _library_search_request
from adapters.inbound.search_routes import (
    SEARCH_PAGE_ENTITY_TYPES,
    create_search_api_routes,
    scope_to_search_page,
)
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.search.filter_enums import SearchSortOrder
from core.models.search_request import SearchRequest, SearchResponse
from core.orchestrator.search_router import SearchRouter
from core.utils.result_simplified import Result
from ui.explore.cards import LIBRARY_DEFAULT_SORT

# The types /search must never return. DERIVED from the router's searchable set
# minus the page scope rather than typed out, so promoting a new domain to
# _SEARCHABLE_DOMAINS lands here instead of silently widening the page.
EXCLUDED_TYPES = frozenset(SearchRouter._SEARCHABLE_DOMAINS) - frozenset(SEARCH_PAGE_ENTITY_TYPES)

SCOPE_VALUES = [entity_type.value for entity_type in SEARCH_PAGE_ENTITY_TYPES]


def _graph_aware_service(
    records: list[dict[str, Any]],
    visibility: SearchVisibility = SearchVisibility.PUBLIC,
) -> MagicMock:
    """A domain search service stub the sweep will actually call.

    ``search_visibility`` and ``graph_aware_faceted_search`` must be REAL
    attributes — a lazily-created MagicMock attribute passes the anonymous gate
    by accident.
    """
    service = MagicMock()
    service.graph_aware_faceted_search = AsyncMock(return_value=Result.ok(records))
    service.search_visibility = visibility
    return service


def _chunk_hit(parent_uid: str, parent_type: str, score: float) -> dict[str, Any]:
    """One `:ContentChunk` body hit, in the shape the vector service returns."""
    return {
        "parent_uid": parent_uid,
        "parent_title": parent_uid.upper(),
        "parent_entity_type": parent_type,
        "text": "a passage about breath",
        "similarity_score": score,
    }


def _vector_search(hits: list[dict[str, Any]]) -> MagicMock:
    vector = MagicMock()
    vector.config = MagicMock(body_chunk_search_min_score=0.5)
    vector.find_similar_chunks_by_text = AsyncMock(return_value=Result.ok(hits))
    return vector


# ============================================================================
# 1. The scope itself
# ============================================================================


class TestSearchPageScope:
    def test_scope_is_the_six_activity_domains_plus_ku(self) -> None:
        assert set(SEARCH_PAGE_ENTITY_TYPES) == {
            EntityType.TASK,
            EntityType.GOAL,
            EntityType.HABIT,
            EntityType.EVENT,
            EntityType.CHOICE,
            EntityType.PRINCIPLE,
            EntityType.KU,
        }

    def test_excluded_types_are_exactly_the_five_ruled_off_the_page(self) -> None:
        assert {
            EntityType.PATH_STEP,
            EntityType.LEARNING_PATH,
            EntityType.EXERCISE,
            EntityType.REVISED_EXERCISE,
            EntityType.USER_ENTRY,
        } == EXCLUDED_TYPES

    def test_unfiltered_request_gets_the_whole_scope(self) -> None:
        scoped = scope_to_search_page(SearchRequest(query_text="breath"))

        assert scoped.entity_types == SCOPE_VALUES

    def test_in_scope_filter_is_preserved(self) -> None:
        scoped = scope_to_search_page(SearchRequest(entity_types=[EntityType.TASK]))

        assert scoped.entity_types == [EntityType.TASK.value]

    @pytest.mark.parametrize("excluded", sorted(EXCLUDED_TYPES))
    def test_out_of_scope_filter_falls_back_to_the_scope(self, excluded: EntityType) -> None:
        # A hand-crafted ?entity_type= once PR-2 drops the dropdown option.
        # Narrowing to nothing would be a silent empty page, so it is dropped —
        # the same way from_form_params already drops an unparseable value.
        scoped = scope_to_search_page(SearchRequest(entity_types=[excluded]))

        assert scoped.entity_types == SCOPE_VALUES

    @pytest.mark.parametrize("excluded", sorted(EXCLUDED_TYPES))
    def test_no_excluded_type_ever_survives_scoping(self, excluded: EntityType) -> None:
        for request in (
            SearchRequest(query_text="breath"),
            SearchRequest(entity_types=[excluded]),
            SearchRequest(entity_types=[EntityType.TASK, excluded]),
        ):
            assert excluded.value not in scope_to_search_page(request).entity_types

    def test_scope_emits_canonical_values_not_enum_members(self) -> None:
        # entity_types is a machine channel and use_enum_values=True means a
        # validated request carries value strings — the scoped copy must match
        # that shape, since model_copy skips validation.
        scoped = scope_to_search_page(SearchRequest(query_text="breath"))

        assert [type(value) for value in scoped.entity_types] == [str] * len(SCOPE_VALUES)

    def test_scoping_does_not_invent_criteria(self) -> None:
        # The route scopes AFTER has_any_criteria(); scoping a blank request
        # would otherwise turn the empty prompt state into a full-scope search.
        assert SearchRequest().has_any_criteria() is False
        assert scope_to_search_page(SearchRequest()).has_any_criteria() is True


# ============================================================================
# 2. The scope reaching the router's sweeps
# ============================================================================


class TestScopedSweep:
    @pytest.mark.asyncio
    async def test_scored_text_sweep_receives_only_scoped_domains(self) -> None:
        # Pure text + RELEVANCE (the default landing shape) takes search_domains.
        router = SearchRouter(event_bus=None)
        search_domains = AsyncMock(return_value=MagicMock(results_by_domain={}))
        router.search_domains = search_domains  # type: ignore[method-assign]

        await router.faceted_search(
            scope_to_search_page(SearchRequest(query_text="breath")), user_uid="user_x"
        )

        call = search_domains.await_args
        assert call is not None
        assert set(call.args[0]) == set(SEARCH_PAGE_ENTITY_TYPES)

    @pytest.mark.asyncio
    async def test_faceted_sweep_never_reaches_an_excluded_domain(self) -> None:
        # An explicit sort forces the faceted sweep — the other cross-domain path.
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        ps = _graph_aware_service([{"uid": "ps_1", "title": "P", "_domain": "path_step"}])
        exercises = _graph_aware_service(
            [{"uid": "ex_1", "title": "E", "_domain": "exercise"}],
            visibility=SearchVisibility.SCOPE_AWARE,
        )
        tasks = _graph_aware_service(
            [{"uid": "task_1", "title": "T", "_domain": "task"}],
            visibility=SearchVisibility.OWNER_ONLY,
        )
        router = SearchRouter(ku=ku, ps=ps, exercises=exercises, tasks=tasks, event_bus=None)

        request = scope_to_search_page(
            SearchRequest(query_text="breath", sort_order=SearchSortOrder.TITLE_ASC)
        )
        result = await router.faceted_search(request, user_uid="user_x")

        assert result.is_ok
        assert {record["_domain"] for record in result.value.results} == {"ku", "task"}
        ps.graph_aware_faceted_search.assert_not_awaited()
        exercises.graph_aware_faceted_search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_router_sweep_default_is_untouched(self) -> None:
        # Constraint: the scope lives at the /search entry point, NOT in the
        # shared default — /explore and /explore/library ride the same method.
        router = SearchRouter()
        faceted_sweep = AsyncMock(return_value=[])
        router._faceted_sweep = faceted_sweep  # type: ignore[method-assign]

        await router._cross_domain_search(SearchRequest(), user_uid="user_x")

        call = faceted_sweep.await_args
        assert call is not None
        assert set(call.args[2]) == set(SearchRouter._SEARCHABLE_DOMAINS) - {EntityType.USER_ENTRY}


# ============================================================================
# 3. Negative control — /explore/library is unchanged
# ============================================================================


class TestLibraryUnchanged:
    @pytest.mark.asyncio
    async def test_library_sweep_still_returns_path_steps(self) -> None:
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        ps = _graph_aware_service([{"uid": "ps_1", "title": "P", "_domain": "path_step"}])
        router = SearchRouter(ku=ku, ps=ps, event_bus=None)

        request = _library_search_request("breath", "", "", LIBRARY_DEFAULT_SORT, 0)
        result = await router.faceted_search(request, user_uid=None)

        assert result.is_ok
        assert {record["_domain"] for record in result.value.results} == {"ku", "path_step"}

    @pytest.mark.asyncio
    async def test_library_body_chunks_still_admit_path_step_parents(self) -> None:
        # The catalog really does carry both curriculum domains, so an explicit
        # Ku+PathStep request keeps both halves of the body-chunk augmentation.
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        ps = _graph_aware_service([{"uid": "ps_1", "title": "P", "_domain": "path_step"}])
        vector = _vector_search([_chunk_hit("ps_9", EntityType.PATH_STEP.value, 0.9)])
        router = SearchRouter(ku=ku, ps=ps, vector_search_service=vector, event_bus=None)

        request = SearchRequest(
            query_text="breath",
            entity_types=[EntityType.KU, EntityType.PATH_STEP],
            enable_semantic_boost=True,
            sort_order=SearchSortOrder.TITLE_ASC,
        )
        result = await router.faceted_search(request, user_uid=None)

        assert result.is_ok
        assert "ps_9" in {record["uid"] for record in result.value.results}


# ============================================================================
# 4. The Digital-layer half — body chunks follow the same scope
# ============================================================================


class TestScopedBodyChunks:
    @pytest.mark.asyncio
    async def test_excluded_curriculum_bodies_do_not_re_enter_the_results(self) -> None:
        # Semantic boost folds Ku/PS lesson BODIES in as parent cards. Scoping
        # only the frontmatter sweep would let PathStep back onto the page
        # through the Digital layer — a filter-only removal by another door.
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        vector = _vector_search(
            [
                _chunk_hit("ps_9", EntityType.PATH_STEP.value, 0.9),
                _chunk_hit("ku_9", EntityType.KU.value, 0.8),
            ]
        )
        router = SearchRouter(ku=ku, vector_search_service=vector, event_bus=None)

        request = scope_to_search_page(
            SearchRequest(
                query_text="breath",
                enable_semantic_boost=True,
                sort_order=SearchSortOrder.TITLE_ASC,
            )
        )
        result = await router.faceted_search(request, user_uid="user_x")

        assert result.is_ok
        uids = {record["uid"] for record in result.value.results}
        assert "ku_9" in uids
        assert "ps_9" not in uids

    @pytest.mark.asyncio
    async def test_sweep_without_a_curriculum_domain_skips_the_vector_call(self) -> None:
        tasks = _graph_aware_service(
            [{"uid": "task_1", "title": "T", "_domain": "task"}],
            visibility=SearchVisibility.OWNER_ONLY,
        )
        vector = _vector_search([_chunk_hit("ku_9", EntityType.KU.value, 0.8)])
        router = SearchRouter(tasks=tasks, vector_search_service=vector, event_bus=None)

        request = SearchRequest(
            query_text="breath",
            entity_types=[EntityType.TASK, EntityType.GOAL],
            enable_semantic_boost=True,
            sort_order=SearchSortOrder.TITLE_ASC,
        )
        result = await router.faceted_search(request, user_uid="user_x")

        assert result.is_ok
        vector.find_similar_chunks_by_text.assert_not_awaited()


# ============================================================================
# 5. The wiring — /search/results actually applies the scope
# ============================================================================


class _RouteRegistry:
    """Capture handlers by (path, method) instead of registering with FastHTML."""

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None) -> Any:
        method = (methods[0] if methods else "GET").upper()

        def decorator(func: Any) -> Any:
            self.handlers[(path, method)] = func
            return func

        return decorator


class TestRouteWiring:
    @staticmethod
    def _handler_and_router() -> tuple[Any, MagicMock]:
        registry = _RouteRegistry()
        search_router = MagicMock()
        search_router.faceted_search = AsyncMock(
            return_value=Result.ok(SearchResponse(results=[], total=0, limit=20, offset=0))
        )
        create_search_api_routes(app=MagicMock(), rt=registry, search_router=search_router)
        return registry.handlers[("/search/results", "GET")], search_router

    @staticmethod
    def _authenticated_request() -> SimpleNamespace:
        return SimpleNamespace(
            method="GET",
            session={"user_uid": "user_caller"},
            url=SimpleNamespace(path="/search/results"),
            headers={},
        )

    @pytest.mark.asyncio
    async def test_unfiltered_search_reaches_the_router_already_scoped(self) -> None:
        handler, search_router = self._handler_and_router()

        await handler(self._authenticated_request(), query="breath")

        sent = search_router.faceted_search.await_args.args[0]
        assert sent.entity_types == SCOPE_VALUES

    @pytest.mark.asyncio
    async def test_blank_request_still_shows_the_prompt_instead_of_searching(self) -> None:
        # The scope must not manufacture criteria out of the empty initial state.
        handler, search_router = self._handler_and_router()

        await handler(self._authenticated_request(), query="")

        search_router.faceted_search.assert_not_awaited()
