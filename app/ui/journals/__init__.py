"""Journals UI module — rendering components for journal entry management."""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from ui.patterns.empty_state import EmptyState

if TYPE_CHECKING:
    from core.models.user.user import User


def JournalsPage(user: "User") -> Any:
    """Shell page for the Journal domain (PR 1 placeholder).

    Renders a landing page inside the Tasks+ sidebar. Full workflow
    (FOUNDER three-stage DNWF / STANDARD continuous) lands in PR 2.
    """
    if user.journal_tier.is_founder():
        description = (
            "Your full Daily Notes Workflow — Scribe, Thought Partner, "
            "and What Is Related — is coming in the next release."
        )
    else:
        description = (
            "Write a journal entry and the app will connect it to your "
            "active goals, tasks, and habits. Coming in the next release."
        )

    return Div(
        EmptyState(
            title="Journal",
            description=description,
            icon="book-open",
        ),
        cls="p-6",
    )
