"""Tests for the SearchResponse enrichment fields — facet_counts + capacity_warnings.

Wired July 2026 (previously writer-less "reserved" fields):
- ``build_facet_counts`` derives window-scoped counts from the returned results
- ``UserContext.get_capacity_warnings`` reads builder-computed workload state
- ``SearchRouter._peek_capacity_warnings`` is cache-hit-only (never builds —
  the /search path must not pay MEGA-QUERY latency)
- ``SearchRouter.faceted_search`` populates both on the response
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.models.search_request import SearchRequest, SearchResponse, build_facet_counts
from core.orchestrator.search_router import SearchRouter
from core.services.user.unified_user_context import UserContext

# ============================================================================
# 1. build_facet_counts — window-scoped facet derivation
# ============================================================================


class TestBuildFacetCounts:
    def test_empty_results_yield_empty_dict(self) -> None:
        assert build_facet_counts([]) == {}

    def test_entity_type_counts_sorted_descending(self) -> None:
        results = [
            {"_domain": "task"},
            {"_domain": "ku"},
            {"_domain": "task"},
            {"_domain": "task"},
            {"_domain": "goal"},
        ]
        counts = build_facet_counts(results)["entity_type"]
        assert [(c.facet_value, c.count) for c in counts] == [("task", 3), ("ku", 1), ("goal", 1)]
        assert counts[0].facet_type == "entity_type"
        assert counts[0].display_name == "Task"

    def test_display_name_titlecases_underscores(self) -> None:
        counts = build_facet_counts([{"_domain": "user_entry"}])["entity_type"]
        assert counts[0].display_name == "User Entry"

    def test_nous_counts_from_array_and_scalar(self) -> None:
        results = [
            {"_domain": "ku", "nous": ["body", "mind"]},
            {"_domain": "ku", "nous": "body"},  # scalar tolerated
            {"_domain": "ps", "nous": ("body",)},
        ]
        counts = build_facet_counts(results)
        nous = {c.facet_value: c.count for c in counts["nous"]}
        assert nous == {"body": 3, "mind": 1}

    def test_results_without_domain_or_nous_contribute_nothing(self) -> None:
        assert build_facet_counts([{"uid": "x"}, {"nous": []}]) == {}


# ============================================================================
# 2. UserContext.get_capacity_warnings
# ============================================================================


def _context(**overrides: Any) -> UserContext:
    ctx = UserContext(user_uid="user_test")
    for field_name, value in overrides.items():
        setattr(ctx, field_name, value)
    return ctx


class TestCapacityWarnings:
    def test_fresh_context_has_no_warnings(self) -> None:
        assert _context().get_capacity_warnings() == {}

    def test_below_threshold_has_no_workload_warning(self) -> None:
        assert _context(current_workload_score=0.79).get_capacity_warnings() == {}

    def test_high_workload_warns(self) -> None:
        ctx = _context(
            current_workload_score=0.85,
            active_task_uids=["t1", "t2", "t3"],
        )
        warnings = ctx.get_capacity_warnings()
        assert warnings["workload"]["level"] == "high"
        assert warnings["workload"]["score"] == 0.85
        assert warnings["workload"]["active_items"] == 3
        assert "near your daily capacity" in warnings["workload"]["message"]

    def test_at_capacity_level(self) -> None:
        warnings = _context(current_workload_score=1.0).get_capacity_warnings()
        assert warnings["workload"]["level"] == "at_capacity"
        assert "at your daily capacity" in warnings["workload"]["message"]

    def test_overdue_tasks_warn_with_count(self) -> None:
        warnings = _context(overdue_task_uids=["t1", "t2"]).get_capacity_warnings()
        assert warnings["overdue_tasks"]["count"] == 2
        assert "2 tasks overdue" in warnings["overdue_tasks"]["message"]

    def test_single_overdue_is_singular(self) -> None:
        warnings = _context(overdue_task_uids=["t1"]).get_capacity_warnings()
        assert "1 task overdue" in warnings["overdue_tasks"]["message"]

    def test_both_warnings_compose(self) -> None:
        ctx = _context(current_workload_score=0.9, overdue_task_uids=["t1"])
        assert set(ctx.get_capacity_warnings()) == {"workload", "overdue_tasks"}


# ============================================================================
# 3. SearchRouter._peek_capacity_warnings — cache-hit-only, never builds
# ============================================================================


class TestPeekCapacityWarnings:
    def test_missing_user_service_is_empty(self) -> None:
        router = SearchRouter()  # no user service wired
        assert router._peek_capacity_warnings("user_x") == {}

    def test_cold_cache_is_empty(self) -> None:
        user = MagicMock()
        user.peek_cached_context.return_value = None
        router = SearchRouter(user=user)
        assert router._peek_capacity_warnings("user_x") == {}
        user.peek_cached_context.assert_called_once_with("user_x")

    def test_warm_cache_yields_context_warnings(self) -> None:
        user = MagicMock()
        user.peek_cached_context.return_value = _context(
            current_workload_score=0.9, active_task_uids=["t1"]
        )
        router = SearchRouter(user=user)
        warnings = router._peek_capacity_warnings("user_x")
        assert warnings["workload"]["level"] == "high"

    def test_never_calls_the_building_path(self) -> None:
        user = MagicMock()
        user.peek_cached_context.return_value = None
        router = SearchRouter(user=user)
        router._peek_capacity_warnings("user_x")
        user.get_rich_unified_context.assert_not_called()


# ============================================================================
# 4. faceted_search populates both fields on the response
# ============================================================================


@pytest.mark.asyncio
async def test_faceted_search_populates_enrichment_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    user = MagicMock()
    user.peek_cached_context.return_value = _context(overdue_task_uids=["t1"])
    router = SearchRouter(user=user)
    router._publish_search_event = AsyncMock()

    cross_results: list[dict[str, Any]] = [
        {"uid": "t1", "title": "Alpha", "_domain": "task"},
        {"uid": "k1", "title": "Beta", "_domain": "ku", "nous": ["body"]},
    ]

    async def fake_cross_domain(request: Any, user_uid: Any) -> list[dict[str, Any]]:
        return cross_results

    monkeypatch.setattr(router, "_cross_domain_search", fake_cross_domain)

    request = SearchRequest(query_text="alpha", user_uid="user_x")
    result = await router.faceted_search(request, "user_x")

    assert result.is_ok
    response = result.value
    entity_counts = {c.facet_value: c.count for c in response.facet_counts["entity_type"]}
    assert entity_counts == {"task": 1, "ku": 1}
    assert {c.facet_value for c in response.facet_counts["nous"]} == {"body"}
    assert response.capacity_warnings["overdue_tasks"]["count"] == 1


@pytest.mark.asyncio
async def test_faceted_search_respects_include_facet_counts_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = MagicMock()
    user.peek_cached_context.return_value = None
    router = SearchRouter(user=user)
    router._publish_search_event = AsyncMock()

    async def fake_cross_domain(request: Any, user_uid: Any) -> list[dict[str, Any]]:
        return [{"uid": "t1", "_domain": "task"}]

    monkeypatch.setattr(router, "_cross_domain_search", fake_cross_domain)

    request = SearchRequest(query_text="alpha", user_uid="user_x", include_facet_counts=False)
    result = await router.faceted_search(request, "user_x")

    assert result.is_ok
    assert result.value.facet_counts == {}
    assert result.value.capacity_warnings == {}  # cold cache


# ============================================================================
# 5. UI consumers — banner + breakdown chips
# ============================================================================


def _response(**overrides: Any) -> SearchResponse:
    base: dict[str, Any] = {
        "results": [{"uid": "t1", "title": "Alpha", "_domain": "task"}],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "query_text": "alpha",
        "search_time_ms": 1.0,
    }
    base.update(overrides)
    return SearchResponse(**base)


class TestSearchResultsEnrichmentUI:
    def test_no_banner_without_warnings(self) -> None:
        from ui.search.components import render_search_results

        html = to_xml(render_search_results(_response()))
        assert "daily capacity" not in html
        assert "overdue" not in html

    def test_banner_joins_warning_messages(self) -> None:
        from ui.search.components import render_search_results

        html = to_xml(
            render_search_results(
                _response(
                    capacity_warnings={
                        "workload": {
                            "level": "high",
                            "score": 0.9,
                            "active_items": 12,
                            "message": "You're near your daily capacity.",
                        },
                        "overdue_tasks": {"count": 2, "message": "2 tasks overdue."},
                    }
                )
            )
        )
        assert "near your daily capacity" in html
        assert "2 tasks overdue" in html

    def test_banner_renders_on_empty_results_too(self) -> None:
        from ui.search.components import render_search_results

        html = to_xml(
            render_search_results(
                _response(
                    results=[],
                    total=0,
                    capacity_warnings={"overdue_tasks": {"count": 1, "message": "1 task overdue."}},
                )
            )
        )
        assert "No results found" in html
        assert "1 task overdue" in html

    def test_breakdown_chips_only_for_multi_domain(self) -> None:
        from core.models.search_request import build_facet_counts
        from ui.search.components import render_search_results

        single = _response(facet_counts=build_facet_counts([{"_domain": "task"}]))
        assert "setEntityType" not in to_xml(render_search_results(single))

        multi_results = [
            {"uid": "1", "title": "A", "_domain": "task"},
            {"uid": "2", "title": "B", "_domain": "ku"},
        ]
        multi = _response(
            results=multi_results,
            total=2,
            facet_counts=build_facet_counts(multi_results),
        )
        html = to_xml(render_search_results(multi))
        assert "setEntityType('task')" in html
        assert "setEntityType('ku')" in html
        assert "Task 1" in html

    def test_breakdown_chip_emits_canonical_entity_type_values(self) -> None:
        # Emission rule: the Type dropdown's option values ARE canonical
        # EntityType values ('path_step'), matching the _domain stamps 1:1 —
        # chips pass the stamp straight through, no alias translation layer.
        # (Aliases like 'ps' remain valid INPUT via EntityType.from_string.)
        from core.models.search_request import build_facet_counts
        from ui.search.components import render_search_results

        results = [
            {"uid": "1", "title": "A", "_domain": "path_step"},
            {"uid": "2", "title": "B", "_domain": "learning_path"},
        ]
        html = to_xml(
            render_search_results(
                _response(results=results, total=2, facet_counts=build_facet_counts(results))
            )
        )
        assert "setEntityType('path_step')" in html
        assert "setEntityType('learning_path')" in html
        assert "setEntityType('ps')" not in html

    def test_breakdown_chip_without_dropdown_option_is_inert(self) -> None:
        # A domain with no Type-dropdown option (e.g. exercise) renders as a
        # plain count badge — never a click that would reset the filter.
        from core.models.search_request import build_facet_counts
        from ui.search.components import render_search_results

        results = [
            {"uid": "1", "title": "A", "_domain": "exercise"},
            {"uid": "2", "title": "B", "_domain": "task"},
        ]
        html = to_xml(
            render_search_results(
                _response(results=results, total=2, facet_counts=build_facet_counts(results))
            )
        )
        assert "Exercise 1" in html
        assert "setEntityType('exercise')" not in html
        assert "setEntityType('task')" in html
