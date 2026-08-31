"""
`/search` result scope — the 6 Activity Domains + Ku
=====================================================

The facet redesign's first rung (`docs/roadmap/done/search-facet-redesign.md`):
the page states which domains it searches instead of inheriting SearchRouter's
cross-domain sweep default (every searchable domain except UserEntry). Ruling 1
of that arc — **removal is from the RESULTS, not just the filter** — is what
these tests pin: an unfiltered
`/search` must not return a PathStep, LearningPath, Exercise, RevisedExercise
or UserEntry that no facet on the page can filter to or away.

The negative control is `/explore/library`, which shares `faceted_search` and
must keep its merged Ku + PathStep catalog — including the lesson-body half.

Section 6 covers the second rung: the Type dropdown and its JS facet-group map.
The type vocabulary lives in THREE sites — `SEARCH_PAGE_ENTITY_TYPES` here,
`_ENTITY_TYPE_OPTIONS` (`ui/search/components.py`) and `entityTypeFilters`
(`static/js/skuel.js`) — and each is derived from the scope rather than typed
out again, so a fourth type cannot arrive in one site alone.

Section 8 covers the fourth rung: the facet vocabularies. They must follow the
result scope or the facets lie — a NOUS sub-topic authored only on a PathStep is
offerable on `/search` but unreachable there. The scope is DERIVED from
`SEARCH_PAGE_ENTITY_TYPES`, and the negative control is again
`/explore/library`, which keeps the merged Ku + PathStep vocabulary its catalog
really carries (pinned in `tests/unit/test_nous_subtopic.py`).

Section 7 covers the third rung: knowledge mode. The four knowledge context
filters lost their only door when Ku left the Type dropdown; the NOUS facet is
the new one, and the two scope facets are mutually exclusive because their
intersection is empty by construction. Both halves live in the MARKUP the
Alpine component reads, so they are pinned here rather than in
`tests/js/search-filters.test.js`, which sees no server-rendered HTML.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.explore_ui import _library_search_request
from adapters.inbound.search_routes import (
    SEARCH_PAGE_ENTITY_TYPES,
    SEARCH_PAGE_FACET_DOMAINS,
    create_search_api_routes,
    scope_to_search_page,
)
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.search.filter_enums import BodyFoldStatus, SearchSortOrder
from core.models.search_request import FacetCount, SearchRequest, SearchResponse
from core.orchestrator.search_router import CURRICULUM_FACET_DOMAINS, SearchRouter
from core.utils.result_simplified import Errors, Result
from ui.explore.cards import LIBRARY_DEFAULT_SORT
from ui.search.components import (
    _ENTITY_TYPE_OPTIONS,
    _render_context_filters,
    _render_domain_breakdown,
    _render_filter_panel,
)

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


def _body_fold_request() -> SearchRequest:
    """A request the fold is eligible for: both body domains + query text."""
    return SearchRequest(
        query_text="breath",
        entity_types=[EntityType.KU, EntityType.PATH_STEP],
        enable_semantic_boost=True,
        sort_order=SearchSortOrder.TITLE_ASC,
    )


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
    async def test_completed_fold_reports_candidates_and_parents(self) -> None:
        # The fold fails SOFT, so its status has to be REPORTED or a chunk-blind
        # response is indistinguishable from a chunk-aware one that matched
        # nothing (ruled 2026-08-30, eval arc PR-2).
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        vector = _vector_search(
            [
                _chunk_hit("ku_9", EntityType.KU.value, 0.9),
                _chunk_hit("ku_9", EntityType.KU.value, 0.8),  # same parent, deduped
            ]
        )
        router = SearchRouter(ku=ku, vector_search_service=vector, event_bus=None)

        result = await router.faceted_search(_body_fold_request(), user_uid=None)

        assert result.is_ok
        fold = result.value.body_fold
        assert fold.status is BodyFoldStatus.COMPLETED
        assert fold.status.searched_bodies()
        # Two passages above the floor, ONE parent card — the counts are not
        # interchangeable, which is why both are reported.
        assert fold.chunk_candidates == 2
        assert fold.parents_added == 1

    @pytest.mark.asyncio
    async def test_fold_that_found_nothing_is_completed_not_degraded(self) -> None:
        # Measured on the live corpus: the real query `body` clears the 0.68
        # floor with ZERO passages. That is a finding about the corpus, and it
        # must never read as a broken Digital layer.
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        router = SearchRouter(ku=ku, vector_search_service=_vector_search([]), event_bus=None)

        result = await router.faceted_search(_body_fold_request(), user_uid=None)

        assert result.is_ok
        fold = result.value.body_fold
        assert fold.status is BodyFoldStatus.COMPLETED
        assert not fold.status.is_degraded()
        assert (fold.chunk_candidates, fold.parents_added) == (0, 0)

    @pytest.mark.asyncio
    async def test_core_tier_reports_unavailable(self) -> None:
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        router = SearchRouter(ku=ku, vector_search_service=None, event_bus=None)

        result = await router.faceted_search(_body_fold_request(), user_uid=None)

        assert result.is_ok
        assert result.value.results  # fails SOFT — frontmatter results stand
        assert result.value.body_fold.status is BodyFoldStatus.UNAVAILABLE
        assert result.value.body_fold.status.is_degraded()

    @pytest.mark.asyncio
    async def test_chunk_search_error_reports_failed(self) -> None:
        ku = _graph_aware_service([{"uid": "ku_1", "title": "K", "_domain": "ku"}])
        vector = _vector_search([])
        vector.find_similar_chunks_by_text = AsyncMock(
            return_value=Result.fail(Errors.database(operation="chunks", message="boom"))
        )
        router = SearchRouter(ku=ku, vector_search_service=vector, event_bus=None)

        result = await router.faceted_search(_body_fold_request(), user_uid=None)

        assert result.is_ok
        assert result.value.results
        assert result.value.body_fold.status is BodyFoldStatus.FAILED

    @pytest.mark.asyncio
    async def test_ineligible_sweep_reports_not_attempted(self) -> None:
        # An Activity-only sweep never wanted bodies — not a degradation, so
        # `is_degraded()` must stay False and a caller must not raise an alarm.
        tasks = _graph_aware_service(
            [{"uid": "task_1", "title": "T", "_domain": "task"}],
            visibility=SearchVisibility.OWNER_ONLY,
        )
        router = SearchRouter(tasks=tasks, vector_search_service=_vector_search([]), event_bus=None)

        result = await router.faceted_search(
            SearchRequest(
                query_text="breath",
                entity_types=[EntityType.TASK],
                enable_semantic_boost=True,
                sort_order=SearchSortOrder.TITLE_ASC,
            ),
            user_uid="user_x",
        )

        assert result.is_ok
        assert result.value.body_fold.status is BodyFoldStatus.NOT_ATTEMPTED
        assert not result.value.body_fold.status.is_degraded()

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


# ============================================================================
# 6. The dropdown vocabulary — the other two sites, derived from this one
# ============================================================================

APP_ROOT = Path(__file__).resolve().parents[2]
SKUEL_JS = APP_ROOT / "static" / "js" / "skuel.js"

# The `entityTypeFilters: { ... }` object literal, then its quoted keys. Read
# from the real file: a hand-copied list here would be a FOURTH vocabulary site.
_JS_MAP_RE = re.compile(r"entityTypeFilters:\s*\{(.*?)\n\s*\},", re.DOTALL)
_JS_KEY_RE = re.compile(r"['\"]([\w-]+)['\"]")
_JS_ENTRY_RE = re.compile(r"['\"](\w+)['\"]\s*:\s*\[([^\]]*)\]")


def _entity_type_filter_map() -> dict[str, list[str]]:
    """searchFilters.entityTypeFilters, read out of skuel.js."""
    source = re.sub(r"^\s*//.*$", "", SKUEL_JS.read_text(encoding="utf-8"), flags=re.MULTILINE)
    body = _JS_MAP_RE.search(source)
    assert body is not None, "entityTypeFilters literal not found in skuel.js"
    mapping = {
        key: _JS_KEY_RE.findall(groups) for key, groups in _JS_ENTRY_RE.findall(body.group(1))
    }
    assert mapping, "entityTypeFilters parsed to no keys — the regex has drifted"
    assert all(mapping.values()), "an entityTypeFilters entry parsed to no groups"
    return mapping


def _entity_type_filter_keys() -> set[str]:
    """The keys of searchFilters.entityTypeFilters, read out of skuel.js."""
    return set(_entity_type_filter_map())


DROPDOWN_VALUES = [value for value, _ in _ENTITY_TYPE_OPTIONS if value]


class TestDropdownVocabulary:
    def test_dropdown_is_the_scope_minus_ku(self) -> None:
        # Ku stays a live RESULT type (it is in SEARCH_PAGE_ENTITY_TYPES) but
        # leaves the Type dropdown — it is reached through the Nous facet.
        assert set(DROPDOWN_VALUES) == {
            entity_type.value for entity_type in SEARCH_PAGE_ENTITY_TYPES
        } - {EntityType.KU.value}

    def test_dropdown_offers_no_type_the_page_refuses(self) -> None:
        # The failure this pins is the one PR-1 left open: an option whose value
        # the route drops, so choosing it silently returns the whole page scope.
        assert not set(DROPDOWN_VALUES) & {excluded.value for excluded in EXCLUDED_TYPES}

    def test_dropdown_keeps_an_all_types_option_first(self) -> None:
        assert _ENTITY_TYPE_OPTIONS[0][0] == ""

    def test_dropdown_values_are_canonical_entity_types(self) -> None:
        for value in DROPDOWN_VALUES:
            parsed = EntityType.from_string(value)
            assert parsed is not None and parsed.value == value

    def test_js_facet_map_is_the_dropdown_plus_the_ku_staging_key(self) -> None:
        # The ONE deliberate divergence between the three sites, and it is one
        # PR long: 'ku' is the only thing making the four knowledge filters
        # reachable, and the next PR re-homes them onto a Nous-driven knowledge
        # mode. Deleting it with the option would strand them meanwhile.
        assert _entity_type_filter_keys() == set(DROPDOWN_VALUES) | {EntityType.KU.value}

    def test_js_facet_map_names_no_type_off_the_page(self) -> None:
        assert not _entity_type_filter_keys() & {excluded.value for excluded in EXCLUDED_TYPES}


class TestResultBreakdownChips:
    """The chips derive from _ENTITY_TYPE_OPTIONS, so the dropdown trim reaches them."""

    @staticmethod
    def _breakdown(*domains: str) -> str:
        response = SearchResponse(results=[], total=0, limit=20, offset=0)
        response.facet_counts = {
            "entity_type": [
                FacetCount(
                    facet_type="entity_type",
                    facet_value=domain,
                    count=3,
                    display_name=domain.replace("_", " ").title(),
                )
                for domain in domains
            ]
        }
        return to_xml(_render_domain_breakdown(response))

    def test_an_activity_chip_still_narrows_the_type_filter(self) -> None:
        markup = self._breakdown(EntityType.TASK.value, EntityType.KU.value)

        assert "setEntityType('task')" in markup

    def test_the_ku_chip_is_a_plain_count_not_a_control(self) -> None:
        # Accepted consequence, not a regression: Ku left the dropdown, and a
        # chip can only set the control the dropdown owns. Assigning an absent
        # value would CLEAR the select — worse than not being clickable.
        markup = self._breakdown(EntityType.TASK.value, EntityType.KU.value)

        assert "setEntityType('ku')" not in markup
        assert "Ku 3" in markup


# ============================================================================
# 7. Knowledge mode — the NOUS facet is the door the Type dropdown closed
# ============================================================================

# Markers, not controls: no context column is named either (skuel.js says so —
# these tests are what make that comment checkable).
_FILTER_GROUP_MARKERS = {"common", "knowledge"}

_SELECT_RE = re.compile(r'<select\b[^>]*\bname="(\w+)"[^>]*>')
_VISIBILITY_GROUP_RE = re.compile(r"isFilterVisible\('(\w+)'\)")
_TITLE_RE = re.compile(r"""x-bind:title=(?P<q>["'])(?P<expr>.*?)(?P=q)""", re.DOTALL)


def _filter_panel_markup() -> str:
    """The rendered /search filter panel, exactly as it is served."""
    _, _, panel = _render_filter_panel(["body"], ["nervous-system"], ["breath"])
    return to_xml(panel)


def _select_tag(markup: str, name: str) -> str:
    """The opening ``<select name="...">`` tag, with its attributes."""
    for tag in _SELECT_RE.finditer(markup):
        if tag.group(1) == name:
            return tag.group(0)
    raise AssertionError(f'no <select name="{name}"> in the filter panel')


def _title_expression(select_tag: str) -> str:
    """The Alpine expression behind ``x-bind:title`` on one control.

    Decoded: FastHTML picks the attribute delimiter from the value, so an
    expression carrying both quote styles comes back with ``&#39;`` in it —
    the browser hands Alpine the decoded form, which is what to assert on.
    """
    match = _TITLE_RE.search(select_tag)
    assert match is not None, f"no x-bind:title on {select_tag[:60]}…"
    return html.unescape(match.group("expr"))


def _rendered_visibility_groups() -> set[str]:
    """Every group name the Tier 2 context row keys a column to."""
    groups = set(_VISIBILITY_GROUP_RE.findall(to_xml(_render_context_filters())))
    assert groups, "no isFilterVisible() columns rendered — the regex has drifted"
    return groups


def _js_groups(*keys: str) -> set[str]:
    """Filter groups the JS map names for the given entity types, markers dropped."""
    mapping = _entity_type_filter_map()
    named = {group for key in keys for group in mapping[key]}
    return named - _FILTER_GROUP_MARKERS


class TestKnowledgeMode:
    """The NOUS facet drives the four knowledge filters, since Ku left the dropdown."""

    def test_the_nous_select_is_bound_to_the_component(self) -> None:
        # Without x-model the component never learns a topic was chosen, and
        # knowledge mode is a getter over state nothing writes.
        assert 'x-model="nousTopic"' in _select_tag(_filter_panel_markup(), "nous")

    def test_the_knowledge_columns_are_exactly_the_groups_the_ku_entry_names(self) -> None:
        # Derived from skuel.js, not typed out: the 'ku' entry IS the mapping
        # knowledge mode reads, so a group added on one side alone fails here.
        knowledge_groups = _js_groups(EntityType.KU.value)

        assert knowledge_groups <= _rendered_visibility_groups()
        assert knowledge_groups == {
            "sel_category",
            "learning_level",
            "content_type",
            "educational_level",
        }

    def test_every_context_column_is_named_by_the_js_map_and_vice_versa(self) -> None:
        # The server renders the columns; the JS map decides which are visible.
        # A column named by neither side is dead markup; a group named only in
        # JS reveals nothing. Both are silent failures, so pin the equality.
        assert _rendered_visibility_groups() == _js_groups(*_entity_type_filter_map())

    def test_the_marker_groups_name_no_column(self) -> None:
        assert not _rendered_visibility_groups() & _FILTER_GROUP_MARKERS


class TestOutOfScopeContextFilters:
    """A hidden context filter must not ride the request (Codex, #1157)."""

    def test_every_context_column_is_disabled_while_it_is_hidden(self) -> None:
        # `hx-include` names every filter on the page, so hiding a control with
        # x-show alone leaves it submitting. Same predicate for both, so the two
        # cannot disagree: shown == enabled.
        markup = to_xml(_render_context_filters())

        for group in _rendered_visibility_groups():
            assert f"x-bind:disabled=\"!isFilterVisible('{group}')\"" in markup

    def test_the_panel_adopts_a_scope_change_in_the_capture_phase(self) -> None:
        # Capture beats the changed control's own htmx listener by spec; the
        # bubble-phase tally then counts what the request will actually carry.
        # Bubble-only would serialize the vacated scope's filters one last time.
        markup = _filter_panel_markup()

        assert 'x-on:change.capture="adoptScope($event)"' in markup
        assert 'x-on:change="updateFilterCount()"' in markup


class TestMutuallyExclusiveScopeFacets:
    """Type and Nous cannot both be set: their intersection is empty by construction."""

    def test_a_chosen_nous_topic_disables_the_type_control(self) -> None:
        assert 'x-bind:disabled="isKnowledgeMode"' in _select_tag(
            _filter_panel_markup(), "entity_type"
        )

    def test_a_chosen_type_disables_the_nous_control(self) -> None:
        assert "x-bind:disabled=\"entityType !== ''\"" in _select_tag(
            _filter_panel_markup(), "nous"
        )

    def test_each_disabled_control_says_which_one_to_clear(self) -> None:
        # A greyed control with no explanation is the silent dead end this arc
        # refuses elsewhere; the hint only exists while the control is disabled
        # (Alpine removes an attribute bound to false).
        markup = _filter_panel_markup()

        type_title = _select_tag(markup, "entity_type")
        assert "x-bind:title=" in type_title
        assert "All Nous" in type_title

        nous_title = _select_tag(markup, "nous")
        assert "x-bind:title=" in nous_title
        assert "All Types" in nous_title

    def test_the_hint_is_absent_while_the_control_is_usable(self) -> None:
        # `false`, not `''` — Alpine REMOVES an attribute bound to false, so an
        # enabled select carries no title at all rather than an empty one.
        markup = _filter_panel_markup()

        for name in ("entity_type", "nous"):
            hint = _title_expression(_select_tag(markup, name))
            assert hint.endswith(" : false"), hint

    def test_the_two_scope_facets_still_include_each_other(self) -> None:
        # hx-include keeps naming both — the exclusion is `disabled` (htmx skips
        # disabled elements), not a narrowed include set, so nothing has to stay
        # in sync when the other control is re-enabled.
        markup = _filter_panel_markup()

        assert "[name='nous']" in _select_tag(markup, "entity_type")
        assert "[name='entity_type']" in _select_tag(markup, "nous")


# ============================================================================
# 8. The facet vocabularies — derived from the scope, applied at BOTH doors
# ============================================================================


class TestFacetVocabularyScope:
    def test_facet_scope_is_derived_from_the_result_scope(self) -> None:
        # Not a fourth vocabulary site: whichever curriculum domains the page
        # RETURNS are exactly the ones its vocabularies aggregate, so the two
        # cannot drift.
        derived = tuple(
            entity_type
            for entity_type in CURRICULUM_FACET_DOMAINS
            if entity_type in SEARCH_PAGE_ENTITY_TYPES
        )

        assert derived == SEARCH_PAGE_FACET_DOMAINS

    def test_the_facet_scope_is_ku_only_today(self) -> None:
        assert SEARCH_PAGE_FACET_DOMAINS == (EntityType.KU,)
        assert EntityType.PATH_STEP not in SEARCH_PAGE_FACET_DOMAINS

    def test_no_facet_domain_is_out_of_the_result_scope(self) -> None:
        # The property that keeps the derivation honest if either list moves.
        assert set(SEARCH_PAGE_FACET_DOMAINS) <= set(SEARCH_PAGE_ENTITY_TYPES)


class TestFacetVocabularyWiring:
    """Both doors onto the sub-topic control pass the SAME scope.

    The flat list (``search_page``) only gates whether the column renders; the
    OPTIONS come from ``/search/subtopics``. Scoping one alone leaves a
    PathStep-only sub-topic selectable — the exact defect this rung closes.
    """

    @staticmethod
    def _handlers_and_router() -> tuple[dict[tuple[str, str], Any], MagicMock]:
        registry = _RouteRegistry()
        search_router = MagicMock()
        search_router.list_nous_subtopics = AsyncMock(return_value=Result.ok(["breath"]))
        search_router.nous_subtopic_map = AsyncMock(return_value=Result.ok({"body": ["breath"]}))
        search_router.list_tags = AsyncMock(return_value=Result.ok([]))
        ku_service = MagicMock()
        ku_service.list_nous_topics = AsyncMock(return_value=Result.ok(["body"]))
        create_search_api_routes(
            app=MagicMock(), rt=registry, search_router=search_router, ku_service=ku_service
        )
        return registry.handlers, search_router

    @staticmethod
    def _authenticated_request(path: str) -> SimpleNamespace:
        return SimpleNamespace(
            method="GET",
            session={"user_uid": "user_caller"},
            url=SimpleNamespace(path=path),
            headers={},
            query_params={},
        )

    @pytest.mark.asyncio
    async def test_the_render_gate_is_fetched_at_the_page_scope(self) -> None:
        handlers, search_router = self._handlers_and_router()

        await handlers[("/search", "GET")](self._authenticated_request("/search"))

        assert search_router.list_nous_subtopics.await_args.args == (SEARCH_PAGE_FACET_DOMAINS,)

    @pytest.mark.asyncio
    async def test_the_options_are_fetched_at_the_page_scope(self) -> None:
        handlers, search_router = self._handlers_and_router()

        await handlers[("/search/subtopics", "GET")](
            self._authenticated_request("/search/subtopics"), nous="body"
        )

        assert search_router.nous_subtopic_map.await_args.args == (SEARCH_PAGE_FACET_DOMAINS,)
