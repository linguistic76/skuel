"""
Unit guards for the Choices period-analytics window filter.
===========================================================

The three period methods on ``_AnalyticsMixin`` — ``get_decision_patterns``,
``get_choice_quality_correlations``, ``get_domain_decision_patterns`` — used to fetch
their window with::

    await self.backend.find_by(user_uid=..., date__gte=start, date__lte=end)

``Choice`` has no ``date`` field. ``build_search_query`` skips filter keys that are not
model fields (with a warning), so both temporal predicates were **dropped** and the query
degraded to ``WHERE n.user_uid = $user_uid`` — every choice the user has ever made, with
no time bound at all. ``days`` was inert: ``days=7`` and ``days=365`` returned the same
set, while ``choices_per_week`` kept dividing by the *requested* window.

The generic guard here is `test_window_fetch_only_names_real_choice_fields`: it collects
every model field name each method sends to the backend and asserts membership in
``fields(Choice)``. That catches the whole family, not just the one bad key — a future
``date__gte``/``occurred_at``/``completed_at`` typo fails the same assertion.

See: tests/integration/test_choices_analytics_window.py for the real-graph half.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from core.models.choice.choice import Choice
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.utils.result_simplified import Result

CHOICE_FIELDS = {f.name for f in fields(Choice)}

PERIOD_METHODS = [
    "get_decision_patterns",
    "get_choice_quality_correlations",
    "get_domain_decision_patterns",
]


class RecordingBackend:
    """Records whichever fetch the mixin reaches for, so either shape can be inspected."""

    def __init__(self, choices: list[Choice] | None = None) -> None:
        self.choices = choices or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def find_by(self, **filters: Any) -> Result[list[Choice]]:
        self.calls.append(("find_by", filters))
        return Result.ok(self.choices)

    async def find_by_date_range(self, **kwargs: Any) -> Result[list[Choice]]:
        self.calls.append(("find_by_date_range", kwargs))
        return Result.ok(self.choices)

    def referenced_model_fields(self) -> set[str]:
        """Every ``Choice`` field name the recorded calls tried to filter or sort on."""
        referenced: set[str] = set()
        for name, kwargs in self.calls:
            if name == "find_by":
                for key in kwargs:
                    if key in {"limit", "offset", "sort_by", "sort_order"}:
                        continue
                    # "created_at__gte" -> "created_at"; bare keys are already field names
                    referenced.add(key.rsplit("__", 1)[0] if "__" in key else key)
            else:
                referenced.add(str(kwargs["date_field"]))
                referenced.update(kwargs.get("additional_filters") or {})
        return referenced


def make_service(backend: RecordingBackend) -> ChoicesIntelligenceService:
    # ChoicesIntelligenceService declares _require_relationships = True, so construction
    # refuses a missing relationship service. These tests never reach a relationship read
    # (RecordingBackend returns no choices, so each method exits through `if not choices:`)
    # — the stub only has to satisfy the constructor's fail-fast check.
    return ChoicesIntelligenceService(
        backend=backend, cross_domain_query=None, relationship_service=MagicMock()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", PERIOD_METHODS)
async def test_window_fetch_only_names_real_choice_fields(method_name: str) -> None:
    """Every field the period fetch names must exist on Choice.

    RED before the fix: the methods filtered on ``date__gte``/``date__lte``, and
    ``date`` is not a Choice field — Neo4j never saw a temporal predicate.
    """
    backend = RecordingBackend()
    await getattr(make_service(backend), method_name)("user_window", days=30)

    unknown = backend.referenced_model_fields() - CHOICE_FIELDS
    assert not unknown, (
        f"{method_name} filters on {sorted(unknown)}, which "
        f"Choice does not declare — the predicate is silently dropped"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", PERIOD_METHODS)
async def test_window_is_bounded_by_the_requested_period(method_name: str) -> None:
    """The fetch must carry the [today - days, today] bounds, not just a user filter."""
    backend = RecordingBackend()
    await getattr(make_service(backend), method_name)("user_window", days=30)

    assert len(backend.calls) == 1, f"{method_name} made {len(backend.calls)} fetches"
    _name, kwargs = backend.calls[0]
    assert kwargs["start_date"] == date.today() - timedelta(days=30)
    assert kwargs["end_date"] == date.today()
    assert (kwargs.get("additional_filters") or {})["user_uid"] == "user_window"


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", PERIOD_METHODS)
async def test_window_field_is_created_at(method_name: str) -> None:
    """created_at is the decided window key — decided_at has no reachable writer."""
    backend = RecordingBackend()
    await getattr(make_service(backend), method_name)("user_window", days=90)

    _name, kwargs = backend.calls[0]
    assert kwargs["date_field"] == "created_at"


@pytest.mark.asyncio
async def test_days_argument_changes_the_requested_window() -> None:
    """A different ``days`` must produce a different window — it was inert before."""
    windows = []
    for days in (7, 365):
        backend = RecordingBackend()
        await make_service(backend).get_decision_patterns("user_window", days=days)
        _name, kwargs = backend.calls[0]
        windows.append(kwargs["start_date"])

    assert windows[0] != windows[1]
