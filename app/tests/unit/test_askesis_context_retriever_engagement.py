# mypy: disable-error-code="typeddict-item"
"""Tests for ContextRetriever — engagement-aware active-PS selection (ADR-059).

Covers ``choose_path_step``'s selection rules among steps that read
(``test_askesis_unreadable_step_choice.py`` covers a step that does not):

1. When an engaged candidate exists, it wins over unengaged candidates.
2. When no candidate is engaged, the first unengaged non-mastered PS is used.
3. Mastered candidates are always skipped, regardless of engagement state.
4. When ``ps_engagement_service`` is None, every step ranks as not engaged, so
   the first non-mastered step is chosen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.query_types import RichPathStepItem
from core.services.askesis.context_retriever import ContextRetriever
from core.services.ps_engagement.engagement import Engagement
from core.services.user import UserContext
from core.utils.result_simplified import Result


def _ps_item(uid: str) -> RichPathStepItem:
    return {
        "step": {
            "uid": uid,
            "title": f"Step {uid}",
            "mastery_threshold": 0.7,
            "knowledge_uids": [],
            "semantic_links": [],
        },
        "graph_context": {},
    }


def _user_context(items: list[RichPathStepItem], mastered: tuple[str, ...] = ()) -> UserContext:
    """A real context: the learner's mastered steps are their MASTERED edges."""
    ctx = UserContext(user_uid="user_1")
    ctx.active_path_steps_rich = items
    ctx.mastered_ps_uids = set(mastered)
    return ctx


def _engagement(ps_uid: str, state: str = "engaged") -> Engagement:
    return Engagement(
        uid="engagement_test",
        student_uid="user_1",
        ps_uid=ps_uid,
        state=state,  # type: ignore[arg-type]
        since=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )


def _engagement_service(engagements_by_ps: dict[str, Engagement | None]) -> MagicMock:
    """Mock service whose find_active returns the configured Engagement (or None) per ps_uid."""

    async def _find_active(_user_uid: str, ps_uid: str) -> Result[Engagement | None]:
        return Result.ok(engagements_by_ps.get(ps_uid))

    svc = MagicMock()
    svc.find_active = AsyncMock(side_effect=_find_active)
    return svc


def _retriever(engagement_service: Any | None) -> ContextRetriever:
    return ContextRetriever(
        ps_engagement_service=engagement_service,
    )


@pytest.mark.anyio
async def test_engaged_candidate_preferred_over_unengaged() -> None:
    """When multiple non-mastered candidates exist, the engaged one wins."""
    items = [_ps_item("ps.test.first"), _ps_item("ps.test.second")]
    ctx = _user_context(items)
    svc = _engagement_service({"ps.test.second": _engagement("ps.test.second")})
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.second"
    assert chosen.engagement is not None
    assert chosen.engagement.state == "engaged"
    assert chosen.engagement.ps_uid == "ps.test.second"


@pytest.mark.anyio
async def test_first_engaged_wins_when_multiple_engaged() -> None:
    """List order is the tiebreaker among engaged candidates."""
    items = [_ps_item("ps.test.a"), _ps_item("ps.test.b")]
    ctx = _user_context(items)
    svc = _engagement_service(
        {"ps.test.a": _engagement("ps.test.a"), "ps.test.b": _engagement("ps.test.b")}
    )
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.a"
    assert chosen.engagement is not None
    assert chosen.engagement.ps_uid == "ps.test.a"


@pytest.mark.anyio
async def test_unengaged_fallback_when_no_engagements() -> None:
    """No active engagement → first non-mastered candidate (engagement is None)."""
    items = [_ps_item("ps.test.first"), _ps_item("ps.test.second")]
    ctx = _user_context(items)
    svc = _engagement_service({})  # no engagements
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.first"
    assert chosen.engagement is None


@pytest.mark.anyio
async def test_completed_engagement_is_not_engaged() -> None:
    """Only state == 'engaged' counts; completed engagements don't bias selection."""
    items = [_ps_item("ps.test.first"), _ps_item("ps.test.second")]
    ctx = _user_context(items)
    svc = _engagement_service({"ps.test.second": _engagement("ps.test.second", state="completed")})
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    # ps.test.second has an engagement edge (completed), so it is neither engaged
    # nor unengaged for our purposes. ps.test.first has no edge → not engaged.
    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.first"
    assert chosen.engagement is None


@pytest.mark.anyio
async def test_mastered_candidates_are_skipped() -> None:
    """A mastered PS is never selected even if it carries an engagement."""
    items = [
        _ps_item("ps.test.mastered"),
        _ps_item("ps.test.active"),
    ]
    ctx = _user_context(items, mastered=("ps.test.mastered",))
    # Engagement on the mastered PS — should still be skipped
    svc = _engagement_service({"ps.test.mastered": _engagement("ps.test.mastered")})
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.active"
    assert chosen.engagement is None  # ps.test.active has no engagement


@pytest.mark.anyio
async def test_no_candidates_returns_none() -> None:
    """Empty rich context → nothing chosen."""
    ctx = _user_context([])
    retriever = _retriever(_engagement_service({}))

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is None


@pytest.mark.anyio
async def test_all_mastered_returns_none() -> None:
    """When every candidate is mastered, no PS is returned."""
    items = [
        _ps_item("ps.test.a"),
        _ps_item("ps.test.b"),
    ]
    ctx = _user_context(items, mastered=("ps.test.a", "ps.test.b"))
    retriever = _retriever(_engagement_service({}))

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is None


@pytest.mark.anyio
async def test_without_engagement_service_the_first_non_mastered_step_is_chosen() -> None:
    """When ps_engagement_service is None, every step ranks as not engaged."""
    items = [_ps_item("ps.test.first"), _ps_item("ps.test.second")]
    ctx = _user_context(items)
    retriever = _retriever(engagement_service=None)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.first"
    assert chosen.engagement is None


@pytest.mark.anyio
async def test_engagement_lookup_failure_does_not_break_selection() -> None:
    """If find_active raises, that candidate is skipped — selection continues."""
    items = [_ps_item("ps.test.broken"), _ps_item("ps.test.ok")]
    ctx = _user_context(items)

    async def _find_active(_user_uid: str, ps_uid: str) -> Result[Engagement | None]:
        if ps_uid == "ps.test.broken":
            raise RuntimeError("neo4j hiccup")
        return Result.ok(_engagement(ps_uid))

    svc = MagicMock()
    svc.find_active = AsyncMock(side_effect=_find_active)
    retriever = _retriever(svc)

    chosen = (await retriever.choose_path_step("user_1", ctx)).chosen

    assert chosen is not None
    assert chosen.path_step.uid == "ps.test.ok"
    assert chosen.engagement is not None
    assert chosen.engagement.ps_uid == "ps.test.ok"
