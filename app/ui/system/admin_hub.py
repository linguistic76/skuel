"""Admin hub page content."""

from typing import Any

from fasthtml.common import Div

from ui.patterns.hub import HubCardData, HubSection
from ui.patterns.page_header import PageHeader


def render_admin_hub_content() -> Any:
    """Build admin home hub content with Admin + Teaching cards."""
    cards = [
        HubCardData(
            icon="🛡️",
            name="Admin",
            href="/admin",
            description="User management, analytics, and system health",
        ),
        HubCardData(
            icon="🎓",
            name="Teaching",
            href="/teaching/students",
            description="Review queue, student management, and class groups",
        ),
        HubCardData(
            icon="🎙️",
            name="Journals",
            href="/journals/submit",
            description="Upload audio, video, or text for transcription and structuring",
        ),
    ]

    return Div(
        PageHeader("Home", subtitle="Welcome back"),
        HubSection(title=None, cards=cards, cols=3),
    )
