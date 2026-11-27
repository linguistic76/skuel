"""``priority_sort_order`` is the one place a priority takes in a list sorted by priority.

HIGH first, then MEDIUM, then LOW, then an item that states no priority. A member's
place is its ``sort_order()``; no priority is ``len(Priority)``, after every member.
"""

from __future__ import annotations

from core.models.enums import Priority, priority_sort_order


class TestTheRank:
    def test_each_member_takes_its_sort_order(self) -> None:
        for priority in Priority:
            assert priority_sort_order(priority) == priority.sort_order()

    def test_high_medium_low_in_that_order(self) -> None:
        assert (
            priority_sort_order(Priority.HIGH)
            < priority_sort_order(Priority.MEDIUM)
            < priority_sort_order(Priority.LOW)
        )

    def test_no_priority_comes_after_every_member(self) -> None:
        assert priority_sort_order(None) == len(Priority)
        assert all(priority_sort_order(None) > priority_sort_order(p) for p in Priority)
