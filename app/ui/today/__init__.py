"""Today surface — post-login landing page.

``TodayPage(ctx)`` renders the full Today view from a ``TodayPageContext``
(produced by ``core/orchestrator/today_orchestrator.py``).
``render_task_drawer_body(task)`` is the HTMX fragment returned by
``GET /today/tasks/{id}/drawer``.
"""

from ui.today.drawer import render_task_drawer_body
from ui.today.page import TodayPage

__all__ = ["TodayPage", "render_task_drawer_body"]
