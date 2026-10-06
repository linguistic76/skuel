"""The cross-domain context buckets a node only when its incident edge leaves the center's kind.

``get_cross_domain_context`` attributes each related node by the edge incident to it.
Several kinds share an edge type: a goal reached habit → principle
-[SUPPORTS_GOAL]-> goal has a ``SUPPORTS_GOAL`` edge pointing into it, from a
principle. A mapping states a link of this domain ("goals this habit supports"), so
the row's ``incident_other_is_center_kind`` decides: ``False`` lands the node in no
bucket, ``True`` in its mapping's bucket. A row without the field is bucketed.

The backend is a fake returning canned rows in the shape
``build_domain_context_with_paths`` returns; the real query is held on a real graph by
tests/integration/test_principle_goal_link.py and
tests/integration/test_principle_choice_link.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.models.relationship_registry import (
    CHOICES_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    DomainRelationshipConfig,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

type Row = dict[str, Any]  # boundary: one raw context row, heterogeneous values


class _CannedContextBackend:
    """Answers the one read the categoriser makes with the rows it was given."""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.asked: list[dict[str, Any]] = []  # boundary: recorded keyword arguments

    async def get_domain_context_raw(self, **kwargs: Any) -> Result[list[Row]]:  # boundary: fake
        self.asked.append(kwargs)
        return Result.ok(self.rows)


def _row(
    uid: str,
    label: str,
    edge: str,
    *,
    into_related: bool,
    distance: int,
    other_is_center_kind: bool | None,
    properties: dict[str, Any] | None = None,  # boundary: raw edge properties
) -> Row:
    row: Row = {
        "uid": uid,
        "title": uid,
        "labels": ["Entity", label],
        "distance": distance,
        "path_strength": 0.8**distance,
        "via_relationships": [],
        "incident_rel_type": edge,
        "incident_into_related": into_related,
        "incident_rel_properties": properties or {},
    }
    if other_is_center_kind is not None:
        row["incident_other_is_center_kind"] = other_is_center_kind
    return row


async def _context(config: DomainRelationshipConfig, rows: list[Row]) -> dict[str, list[str]]:
    """The non-empty buckets, as bucket name -> uids."""
    backend = _CannedContextBackend(rows)
    # boundary: the fake backend stands in for any domain's operations
    service = UnifiedRelationshipService[Any, Any, Any](
        backend=backend, config=config, graph_intel=None
    )
    result = await service.get_cross_domain_context("center")
    assert result.is_ok, result
    assert len(backend.asked) == 1
    return {
        name: [entry["uid"] for entry in entries]
        for name, entries in result.value.items()
        if isinstance(entries, list) and entries
    }


@pytest.mark.asyncio
async def test_a_goal_reached_through_a_principles_edge_is_in_no_habit_bucket() -> None:
    reached = _row(
        "goal_reached",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=2,
        other_is_center_kind=False,
    )

    assert await _context(HABITS_CONFIG, [reached]) == {}


@pytest.mark.asyncio
async def test_a_goal_the_habit_supports_directly_is_among_its_supported_goals() -> None:
    direct = _row(
        "goal_direct",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=1,
        other_is_center_kind=True,
    )

    assert await _context(HABITS_CONFIG, [direct]) == {"supported_goals": ["goal_direct"]}


@pytest.mark.asyncio
async def test_the_two_rows_differ_only_in_the_field_and_only_one_is_bucketed() -> None:
    direct = _row(
        "goal_direct",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=1,
        other_is_center_kind=True,
    )
    reached = {**direct, "uid": "goal_reached", "incident_other_is_center_kind": False}

    assert await _context(HABITS_CONFIG, [reached, direct]) == {"supported_goals": ["goal_direct"]}


@pytest.mark.asyncio
async def test_a_row_without_the_field_is_bucketed() -> None:
    unmarked = _row(
        "goal_unmarked",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=1,
        other_is_center_kind=None,
    )
    assert "incident_other_is_center_kind" not in unmarked

    assert await _context(HABITS_CONFIG, [unmarked]) == {"supported_goals": ["goal_unmarked"]}


@pytest.mark.asyncio
async def test_a_goal_reached_through_a_habits_edge_is_in_no_principle_bucket() -> None:
    reached = _row(
        "goal_reached",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=2,
        other_is_center_kind=False,
    )
    own = _row(
        "goal_own",
        "Goal",
        "SUPPORTS_GOAL",
        into_related=True,
        distance=1,
        other_is_center_kind=True,
    )

    assert await _context(PRINCIPLES_CONFIG, [reached, own]) == {"supported_goals": ["goal_own"]}


@pytest.mark.asyncio
async def test_a_habit_whose_edge_leaves_another_kind_is_in_no_goal_tier_bucket() -> None:
    """The field is checked before the tier filter: an essential edge does not rescue it."""
    essential = {"essentiality": "essential"}
    elsewhere = _row(
        "habit_elsewhere",
        "Habit",
        "SUPPORTS_GOAL",
        into_related=False,
        distance=2,
        other_is_center_kind=False,
        properties=essential,
    )
    own = _row(
        "habit_own",
        "Habit",
        "SUPPORTS_GOAL",
        into_related=False,
        distance=1,
        other_is_center_kind=True,
        properties=essential,
    )

    assert await _context(GOALS_CONFIG, [elsewhere, own]) == {"essential_habits": ["habit_own"]}


@pytest.mark.asyncio
async def test_a_peer_reached_through_a_shared_goal_is_still_a_related_principle() -> None:
    """A shared-neighbour mapping's node is reached THROUGH another kind, so the
    kind condition does not apply to it."""
    peer = _row(
        "principle_peer",
        "Principle",
        "SUPPORTS_GOAL",
        into_related=False,
        distance=2,
        other_is_center_kind=False,
    )

    assert await _context(PRINCIPLES_CONFIG, [peer]) == {
        "related_principles_shared": ["principle_peer"]
    }


# ---------------------------------------------------------------------------
# INFORMS_CHOICE: a choice is informed by a principle, a habit or a PathStep
# ---------------------------------------------------------------------------


def _informer(uid: str, label: str) -> Row:
    """A node at distance 1 whose INFORMS_CHOICE points out of it, into the centre."""
    return _row(
        uid, label, "INFORMS_CHOICE", into_related=False, distance=1, other_is_center_kind=True
    )


@pytest.mark.asyncio
async def test_a_choices_informers_land_in_the_bucket_of_their_kind() -> None:
    rows = [
        _informer("principle_1", "Principle"),
        _informer("habit_1", "Habit"),
        _informer("ps_1", "PathStep"),
    ]

    assert await _context(CHOICES_CONFIG, rows) == {
        "informing_principles": ["principle_1"],
        "informing_habits": ["habit_1"],
    }


@pytest.mark.asyncio
async def test_a_choice_reached_through_a_principles_edge_is_in_no_habit_bucket() -> None:
    """habit -EMBODIES_PRINCIPLE-> principle -INFORMS_CHOICE-> choice."""
    reached = _row(
        "choice_reached",
        "Choice",
        "INFORMS_CHOICE",
        into_related=True,
        distance=2,
        other_is_center_kind=False,
    )
    own = _row(
        "choice_own",
        "Choice",
        "INFORMS_CHOICE",
        into_related=True,
        distance=1,
        other_is_center_kind=True,
    )

    assert await _context(HABITS_CONFIG, [reached, own]) == {"informed_choices": ["choice_own"]}


@pytest.mark.asyncio
async def test_a_choice_reached_through_a_habits_edge_is_in_no_principle_bucket() -> None:
    """principle -INSPIRES_HABIT-> habit -INFORMS_CHOICE-> choice."""
    reached = _row(
        "choice_reached",
        "Choice",
        "INFORMS_CHOICE",
        into_related=True,
        distance=2,
        other_is_center_kind=False,
    )
    own = _row(
        "choice_own",
        "Choice",
        "INFORMS_CHOICE",
        into_related=True,
        distance=1,
        other_is_center_kind=True,
    )

    assert await _context(PRINCIPLES_CONFIG, [reached, own]) == {"informed_choices": ["choice_own"]}


@pytest.mark.asyncio
async def test_a_co_informer_of_the_principles_choice_is_in_no_principle_bucket() -> None:
    """principle -INFORMS_CHOICE-> choice <-INFORMS_CHOICE- habit: the principle reads
    INFORMS_CHOICE outgoing only, so the habit pointing out of itself lands nowhere."""
    co_informer = _row(
        "habit_co",
        "Habit",
        "INFORMS_CHOICE",
        into_related=False,
        distance=2,
        other_is_center_kind=False,
    )

    assert await _context(PRINCIPLES_CONFIG, [co_informer]) == {}
