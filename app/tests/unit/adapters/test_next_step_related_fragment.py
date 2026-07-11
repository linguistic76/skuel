"""Tests for the "Related to your next step" lens (PS detail page).

PR 5 of the discovery-analytics arc — reuses the #598 chip mechanic for the
viewer's ZPD next-step Kus. Three layers:
- ``render_ps_next_step_related`` — chip rows (next-step Ku + undirected
  "related (unordered)" hints) that collapse to an empty div (stable id) when
  there is nothing to show.
- The ``/explore/next-step/related`` fragment handler — fail-soft at every
  layer: anonymous viewer, CORE tier (zpd or vector service None), ZPD errors,
  and an empty proximal zone all collapse to the empty fragment.

The undirected labeling is a product ruling (2026-07-10): vector neighbours
are hints, never curriculum order — the section must say so.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fasthtml.common import to_xml

from adapters.inbound.learning_loop_routes import create_learning_loop_detail_routes
from core.models.zpd.zpd_assessment import ZPDAssessment
from core.utils.result_simplified import Errors, Result
from ui.explore.ps_detail import render_ps_detail_content, render_ps_next_step_related

# ============================================================================
# Section renderer
# ============================================================================


def _group(ku_uid: str, ku_title: str, related: list[dict] | None = None) -> dict:
    return {"ku": {"uid": ku_uid, "title": ku_title}, "related": related or []}


class TestRenderNextStepRelated:
    def test_next_step_ku_and_related_chips_link_to_reading_pages(self) -> None:
        html = to_xml(
            render_ps_next_step_related(
                [
                    _group(
                        "ku.sel.habits",
                        "Habits",
                        [{"uid": "ku.discipline.atomic-habits", "title": "Atomic Habits"}],
                    )
                ]
            )
        )

        assert "Related to your next step" in html
        assert 'href="/explore/ku/ku.sel.habits"' in html
        assert 'href="/explore/ku/ku.discipline.atomic-habits"' in html

    def test_related_chips_are_labeled_unordered(self) -> None:
        """The ruling: neighbours are undirected hints, never a sequence."""
        html = to_xml(
            render_ps_next_step_related([_group("ku.a.b", "B", [{"uid": "ku.a.c", "title": "C"}])])
        )

        assert "related (unordered)" in html
        assert "not a prescribed sequence" in html

    def test_group_without_related_still_shows_next_step_chip(self) -> None:
        html = to_xml(render_ps_next_step_related([_group("ku.a.b", "B")]))

        assert 'href="/explore/ku/ku.a.b"' in html
        assert "related (unordered)" not in html

    def test_empty_input_collapses_to_empty_div_with_stable_id(self) -> None:
        html = to_xml(render_ps_next_step_related([]))

        assert 'id="ps-next-step-fragment"' in html
        assert "Related to your next step" not in html

    def test_groups_without_ku_uid_are_filtered(self) -> None:
        html = to_xml(render_ps_next_step_related([{"ku": {}, "related": []}]))

        assert "Related to your next step" not in html

    def test_no_raw_scores_in_output(self) -> None:
        html = to_xml(
            render_ps_next_step_related([_group("ku.a.b", "B", [{"uid": "ku.a.c", "title": "C"}])])
        )

        assert "score" not in html.lower()


class TestPsDetailMount:
    def _render(self, *, show: bool) -> str:
        return to_xml(
            render_ps_detail_content(
                step=SimpleNamespace(title="Step", description="d", tags=()),
                uid="ps.test.step",
                content_html="",
                is_marked_read=False,
                is_bookmarked=False,
                is_in_progress=False,
                is_mastered=False,
                user_uid="user_test" if show else None,
                show_next_step_related=show,
            )
        )

    def test_placeholder_mounted_when_enabled(self) -> None:
        html = self._render(show=True)
        assert 'hx-get="/explore/next-step/related"' in html

    def test_placeholder_absent_when_disabled(self) -> None:
        html = self._render(show=False)
        assert "/explore/next-step/related" not in html


# ============================================================================
# Fragment handler — fail-soft at every layer
# ============================================================================


class _RouteRecorder:
    """Fake ``rt`` decorator — records path → handler for direct invocation."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None) -> Any:
        def _register(handler: Any) -> Any:
            self.handlers[path] = handler
            return handler

        return _register


def _authed_request(user_uid: str | None = "user_test") -> SimpleNamespace:
    session: dict[str, str] = {"user_uid": user_uid} if user_uid else {}
    return SimpleNamespace(session=session)


def _handler(
    *,
    zpd_service: Any,
    vector_search_service: Any,
    orchestrator: Any | None = None,
) -> Any:
    recorder = _RouteRecorder()
    create_learning_loop_detail_routes(
        MagicMock(),
        recorder,  # type: ignore[arg-type]  # boundary: test double for RouteDecorator
        orchestrator=orchestrator or MagicMock(),
        vector_search_service=vector_search_service,
        zpd_service=zpd_service,
    )
    return recorder.handlers["/explore/next-step/related"]


def _vector_service(neighbours: list[dict]) -> MagicMock:
    service = MagicMock()
    service.find_related_concepts = AsyncMock(
        return_value=Result.ok([{"node": n, "score": 0.75} for n in neighbours])
    )
    return service


def _assessment(
    proximal: list[str],
    current: list[str] | None = None,
    readiness: dict[str, float] | None = None,
) -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=current or [],
        proximal_zone=proximal,
        engaged_paths=[],
        readiness_scores=readiness or {},
        blocking_gaps=[],
        behavioral_readiness=0.5,
    )


def _zpd(
    proximal: list[str],
    current: list[str] | None = None,
    readiness: dict[str, float] | None = None,
) -> MagicMock:
    zpd = MagicMock()
    zpd.assess_zone = AsyncMock(return_value=Result.ok(_assessment(proximal, current, readiness)))
    return zpd


async def test_happy_path_renders_next_step_and_related_chips() -> None:
    orchestrator = MagicMock()
    orchestrator.get_ku = AsyncMock(return_value=Result.ok(SimpleNamespace(title="Habits")))
    handler = _handler(
        zpd_service=_zpd(["ku.sel.habits"]),
        vector_search_service=_vector_service(
            [{"uid": "ku.discipline.atomic-habits", "title": "Atomic Habits"}]
        ),
        orchestrator=orchestrator,
    )

    html = to_xml(await handler(_authed_request()))

    assert "Related to your next step" in html
    assert 'href="/explore/ku/ku.sel.habits"' in html
    assert "Habits" in html
    assert 'href="/explore/ku/ku.discipline.atomic-habits"' in html
    assert "related (unordered)" in html


async def test_proximal_zone_is_capped_at_two_rows_by_readiness() -> None:
    """Top-2 proximal Kus by readiness score — not list order."""
    orchestrator = MagicMock()
    orchestrator.get_ku = AsyncMock(return_value=Result.ok(SimpleNamespace(title="T")))
    zpd = _zpd(
        ["ku.a", "ku.b", "ku.c", "ku.d"],
        readiness={"ku.a": 0.2, "ku.b": 1.0, "ku.c": 0.1, "ku.d": 0.9},
    )
    handler = _handler(
        zpd_service=zpd, vector_search_service=_vector_service([]), orchestrator=orchestrator
    )

    html = to_xml(await handler(_authed_request()))

    assert 'href="/explore/ku/ku.b"' in html
    assert 'href="/explore/ku/ku.d"' in html
    assert "ku.a" not in html
    assert "ku.c" not in html


async def test_engaged_kus_are_filtered_from_related_hints() -> None:
    """Runtime-observed noise: the engaged Ku is often a vector neighbour of the
    Ku it enables — already-engaged Kus must not resurface as 'related' hints."""
    orchestrator = MagicMock()
    orchestrator.get_ku = AsyncMock(return_value=Result.ok(SimpleNamespace(title="Compounding")))
    zpd = _zpd(["ku.discipline.compounding"], current=["ku.discipline.investment"])
    handler = _handler(
        zpd_service=zpd,
        vector_search_service=_vector_service(
            [
                {"uid": "ku.sel.habits", "title": "Habits"},
                {"uid": "ku.discipline.investment", "title": "Investment"},  # engaged
            ]
        ),
        orchestrator=orchestrator,
    )

    html = to_xml(await handler(_authed_request()))

    assert 'href="/explore/ku/ku.sel.habits"' in html
    assert "ku.discipline.investment" not in html


async def test_anonymous_viewer_gets_empty_fragment() -> None:
    handler = _handler(zpd_service=_zpd(["ku.a"]), vector_search_service=_vector_service([]))

    html = to_xml(await handler(_authed_request(user_uid=None)))

    assert 'id="ps-next-step-fragment"' in html
    assert "Related to your next step" not in html


async def test_core_tier_no_zpd_service_gets_empty_fragment() -> None:
    handler = _handler(zpd_service=None, vector_search_service=_vector_service([]))

    html = to_xml(await handler(_authed_request()))

    assert 'id="ps-next-step-fragment"' in html
    assert "Related to your next step" not in html


async def test_core_tier_no_vector_service_gets_empty_fragment() -> None:
    handler = _handler(zpd_service=_zpd(["ku.a"]), vector_search_service=None)

    html = to_xml(await handler(_authed_request()))

    assert "Related to your next step" not in html


async def test_zpd_error_fails_soft() -> None:
    zpd = MagicMock()
    zpd.assess_zone = AsyncMock(
        return_value=Result.fail(Errors.database(operation="zone", message="boom"))
    )
    handler = _handler(zpd_service=zpd, vector_search_service=_vector_service([]))

    html = to_xml(await handler(_authed_request()))

    assert 'id="ps-next-step-fragment"' in html
    assert "error" not in html.lower()


async def test_empty_proximal_zone_collapses() -> None:
    handler = _handler(zpd_service=_zpd([]), vector_search_service=_vector_service([]))

    html = to_xml(await handler(_authed_request()))

    assert 'id="ps-next-step-fragment"' in html
    assert "Related to your next step" not in html


async def test_ku_title_falls_back_to_uid_when_lookup_fails() -> None:
    orchestrator = MagicMock()
    orchestrator.get_ku = AsyncMock(
        return_value=Result.fail(Errors.not_found(resource="Ku", identifier="ku.a"))
    )
    handler = _handler(
        zpd_service=_zpd(["ku.a"]),
        vector_search_service=_vector_service([]),
        orchestrator=orchestrator,
    )

    html = to_xml(await handler(_authed_request()))

    assert 'href="/explore/ku/ku.a"' in html
    assert "ku.a" in html
