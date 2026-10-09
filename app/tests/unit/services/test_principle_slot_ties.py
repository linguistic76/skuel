"""The daily plan's principle slot ranks deterministically: a tie goes to the lower uid.

Equal-strength principles each linked to one task due today score the same; which of
them fills a ``limit`` must not depend on the order the context's sets iterate in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from core.services.principles.principles_planning_service import PrinciplesPlanningService
from core.services.user.unified_user_context import UserContext

if TYPE_CHECKING:
    from core.ports.domain_protocols import PrinciplesOperations

PRINCIPLES = ["principle_c", "principle_a", "principle_b"]


def _context(today_task_uids: list[str]) -> UserContext:
    return UserContext(
        user_uid="user_ties",
        today_task_uids=today_task_uids,
        active_task_uids=list(today_task_uids),
        principles_by_task={f"task_{p[-1]}": [p] for p in PRINCIPLES},
        principle_priorities=dict.fromkeys(PRINCIPLES, 0.6),
    )


@pytest.mark.parametrize(
    "today_task_uids",
    [
        ["task_a", "task_b", "task_c"],
        ["task_c", "task_b", "task_a"],
        ["task_b", "task_c", "task_a"],
    ],
)
async def test_tied_principles_fill_the_slot_in_uid_order(today_task_uids: list[str]) -> None:
    # The slot reads only the context; the backend is never called.
    planning = PrinciplesPlanningService(backend=cast("PrinciplesOperations", object()))

    result = await planning.get_contextual_principles_for_user(_context(today_task_uids), limit=2)

    assert result.is_ok, result
    assert [p.uid for p in result.value] == ["principle_a", "principle_b"]
