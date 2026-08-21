# mypy: disable-error-code="typeddict-item"
"""Tests for ContextRetriever — engagement-aware active-PS selection (ADR-059).

Covers ``_find_active_ps`` selection rules:

1. When an engaged candidate exists, it wins over unengaged candidates.
2. When no candidate is engaged, the first unengaged non-mastered PS is used.
3. Mastered candidates are always skipped, regardless of engagement state.
4. When ``ps_engagement_service`` is None (unit-test ergonomics), the legacy
   selection (first non-mastered) is preserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.askesis.context_retriever import ContextRetriever
from core.services.ps_engagement.engagement import Engagement
from core.utils.result_simplified import Result


def _ps_item(
    uid: str, current_mastery: float = 0.0, mastery_threshold: float = 0.7
) -> dict[str, Any]:
    return {
        "entity": {
            "uid": uid,
            "title": f"Step {uid}",
            "current_mastery": current_mastery,
            "mastery_threshold": mastery_threshold,
            "knowledge_uids": [],
            "semantic_links": [],
        },
        "graph_context": {},
    }


def _user_context(items: list[dict[str, Any]]) -> MagicMock:
    ctx = MagicMock()
    ctx.active_path_steps_rich = items
    return ctx


def _engagement(ps_uid: str, state: str = "engaged") -> Engagement:
    return Engagement(
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
    items = [_ps_item("ps:first"), _ps_item("ps:second")]
    ctx = _user_context(items)
    svc = _engagement_service({"ps:second": _engagement("ps:second")})
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:second"
    assert engagement is not None
    assert engagement.state == "engaged"
    assert engagement.ps_uid == "ps:second"


@pytest.mark.anyio
async def test_first_engaged_wins_when_multiple_engaged() -> None:
    """List order is the tiebreaker among engaged candidates."""
    items = [_ps_item("ps:a"), _ps_item("ps:b")]
    ctx = _user_context(items)
    svc = _engagement_service({"ps:a": _engagement("ps:a"), "ps:b": _engagement("ps:b")})
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:a"
    assert engagement is not None
    assert engagement.ps_uid == "ps:a"


@pytest.mark.anyio
async def test_unengaged_fallback_when_no_engagements() -> None:
    """No active engagement → first non-mastered candidate (engagement is None)."""
    items = [_ps_item("ps:first"), _ps_item("ps:second")]
    ctx = _user_context(items)
    svc = _engagement_service({})  # no engagements
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:first"
    assert engagement is None


@pytest.mark.anyio
async def test_completed_engagement_is_not_engaged() -> None:
    """Only state == 'engaged' counts; completed engagements don't bias selection."""
    items = [_ps_item("ps:first"), _ps_item("ps:second")]
    ctx = _user_context(items)
    svc = _engagement_service({"ps:second": _engagement("ps:second", state="completed")})
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    # ps:second has an engagement edge (completed), so it is neither engaged
    # nor unengaged for our purposes. ps:first has no edge → unengaged_match.
    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:first"
    assert engagement is None


@pytest.mark.anyio
async def test_mastered_candidates_are_skipped() -> None:
    """A mastered PS is never selected even if it carries an engagement."""
    items = [
        _ps_item("ps:mastered", current_mastery=0.9, mastery_threshold=0.7),
        _ps_item("ps:active"),
    ]
    ctx = _user_context(items)
    # Engagement on the mastered PS — should still be skipped
    svc = _engagement_service({"ps:mastered": _engagement("ps:mastered")})
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:active"
    assert engagement is None  # ps:active has no engagement


@pytest.mark.anyio
async def test_no_candidates_returns_none() -> None:
    """Empty rich context → (None, None)."""
    ctx = _user_context([])
    retriever = _retriever(_engagement_service({}))

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is None
    assert engagement is None


@pytest.mark.anyio
async def test_all_mastered_returns_none() -> None:
    """When every candidate is mastered, no PS is returned."""
    items = [
        _ps_item("ps:a", current_mastery=0.9, mastery_threshold=0.7),
        _ps_item("ps:b", current_mastery=0.95, mastery_threshold=0.7),
    ]
    ctx = _user_context(items)
    retriever = _retriever(_engagement_service({}))

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is None
    assert engagement is None


@pytest.mark.anyio
async def test_legacy_path_without_engagement_service() -> None:
    """When ps_engagement_service is None, fall back to first-non-mastered."""
    items = [_ps_item("ps:first"), _ps_item("ps:second")]
    ctx = _user_context(items)
    retriever = _retriever(engagement_service=None)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:first"
    assert engagement is None


@pytest.mark.anyio
async def test_engagement_lookup_failure_does_not_break_selection() -> None:
    """If find_active raises, that candidate is skipped — selection continues."""
    items = [_ps_item("ps:broken"), _ps_item("ps:ok")]
    ctx = _user_context(items)

    async def _find_active(_user_uid: str, ps_uid: str) -> Result[Engagement | None]:
        if ps_uid == "ps:broken":
            raise RuntimeError("neo4j hiccup")
        return Result.ok(_engagement(ps_uid))

    svc = MagicMock()
    svc.find_active = AsyncMock(side_effect=_find_active)
    retriever = _retriever(svc)

    ps_rich, engagement = await retriever._find_active_ps("user_1", ctx)

    assert ps_rich is not None
    assert ps_rich["entity"]["uid"] == "ps:ok"
    assert engagement is not None
    assert engagement.ps_uid == "ps:ok"
