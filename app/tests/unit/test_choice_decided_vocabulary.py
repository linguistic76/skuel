"""
Pending and decided are Choice's own predicates, not status values.

A Choice's status is one of DRAFT / ACTIVE / COMPLETED / ARCHIVED; "pending" and
"decided" are not among them. ``Choice.is_decided`` / ``Choice.is_pending`` are the
one definition, and every reader that counts or filters by them — the stats the
daily plan reads, the facade's filtered context, the list page's filter and its
stats bar — answers through those two methods.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fasthtml.common import to_xml

from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.choices_service import ChoicesService
from core.utils.activity_stats import compute_choice_stats
from core.utils.entity_filters import filter_choices
from core.utils.result_simplified import Result
from ui.activities.choices_views import ChoiceStatsBar

_DECIDED_AT = datetime(2026, 9, 1, 12, 0)


def _choice(uid: str, status: EntityStatus, decided_at: datetime | None = None) -> Choice:
    return Choice(uid=uid, title=uid, user_uid="user_v", status=status, decided_at=decided_at)


# (status, decided_at) -> (is_decided, is_pending), every legal status both ways.
_MATRIX = [
    (EntityStatus.DRAFT, None, False, True),
    (EntityStatus.ACTIVE, None, False, True),
    (EntityStatus.COMPLETED, None, True, False),
    (EntityStatus.ARCHIVED, None, False, False),
    (EntityStatus.DRAFT, _DECIDED_AT, True, False),
    (EntityStatus.ACTIVE, _DECIDED_AT, True, False),
    (EntityStatus.COMPLETED, _DECIDED_AT, True, False),
    (EntityStatus.ARCHIVED, _DECIDED_AT, True, False),
]


def _one_of_each() -> list[Choice]:
    return [
        _choice(f"c_{status.value}_{'decided' if decided_at else 'open'}", status, decided_at)
        for status, decided_at, _, _ in _MATRIX
    ]


_PENDING_UIDS = {"c_draft_open", "c_active_open"}
_DECIDED_UIDS = {
    "c_completed_open",
    "c_draft_decided",
    "c_active_decided",
    "c_completed_decided",
    "c_archived_decided",
}


def test_the_matrix_covers_every_choice_status() -> None:
    assert {status for status, _, _, _ in _MATRIX} == set(EntityType.CHOICE.valid_statuses())


@pytest.mark.parametrize(("status", "decided_at", "decided", "pending"), _MATRIX)
def test_the_model_decides(
    status: EntityStatus, decided_at: datetime | None, decided: bool, pending: bool
) -> None:
    choice = _choice("c", status, decided_at)

    assert choice.is_decided() is decided
    assert choice.is_pending() is pending


def test_a_decision_made_keeps_the_choice_active() -> None:
    """Deciding is not a status change: the decided choice is ACTIVE and decided."""
    choice = _choice("c", EntityStatus.ACTIVE, _DECIDED_AT)

    assert choice.status == EntityStatus.ACTIVE
    assert choice.is_decided()
    assert not choice.is_pending()


def test_stats_count_by_the_models_predicates() -> None:
    stats = compute_choice_stats(_one_of_each())

    assert stats.total == 8
    assert stats.pending == 2
    assert stats.decided == 5
    assert stats.active == stats.pending


def test_the_list_filter_selects_by_the_models_predicates() -> None:
    choices = _one_of_each()

    assert {c.uid for c in filter_choices(choices, status_filter="pending")} == _PENDING_UIDS
    assert {c.uid for c in filter_choices(choices, status_filter="decided")} == _DECIDED_UIDS
    assert len(filter_choices(choices, status_filter="all")) == 8


def test_the_stats_bar_shows_the_same_counts() -> None:
    html = to_xml(ChoiceStatsBar(_one_of_each()))

    pending_at = html.index("Pending")
    decided_at = html.index("Decided")
    total_at = html.index("Total")
    assert total_at < pending_at < decided_at
    # Each stat renders its value beside its label; read the three in order.
    values = [
        int(token)
        for token in html.replace("<", " ").replace(">", " ").split()
        if token in {"8", "2", "5"}
    ]
    assert values[:3] == [8, 2, 5]


def _facade(choices: list[Choice]) -> ChoicesService:
    """The real facade over a core that hands back ``choices`` for any owner."""
    facade = object.__new__(ChoicesService)
    facade.core = SimpleNamespace(  # type: ignore[assignment]  # one-method stand-in for the core
        get_all_for_user=AsyncMock(return_value=Result.ok(choices))
    )
    return facade


@pytest.mark.asyncio
async def test_the_filtered_context_counts_and_filters_alike() -> None:
    facade = _facade(_one_of_each())

    everything = await facade.get_filtered_context("user_v", status_filter="all")
    pending = await facade.get_filtered_context("user_v", status_filter="pending")
    decided = await facade.get_filtered_context("user_v", status_filter="decided")

    assert everything.is_ok and pending.is_ok and decided.is_ok
    assert everything.value["stats"] == {"total": 8, "active": 2, "pending": 2, "decided": 5}
    assert len(everything.value["entities"]) == 8
    assert {c.uid for c in pending.value["entities"]} == _PENDING_UIDS
    assert {c.uid for c in decided.value["entities"]} == _DECIDED_UIDS
    # Stats are computed before the filter, so every view reports the same counts.
    assert pending.value["stats"] == decided.value["stats"] == everything.value["stats"]
