"""Today surface — the day view.

``TodayPage(ctx)`` renders one day of dated Activity from a ``TodayPageContext``
(produced by ``ui/today/orchestrator.py``); ``habits_fragment`` is the habit
chips container the page renders and the ``calendar-refresh`` listener re-fetches.
"""

from ui.today.page import TodayPage, habits_fragment

__all__ = ["TodayPage", "habits_fragment"]
