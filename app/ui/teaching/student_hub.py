"""Student hub page — teacher's view of an individual student.

Hub page with no sidebar. Container cards link to submission sections
and KU progress, each with counts as badges.
"""

from fasthtml.common import A, Div
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.patterns.hub import HubCardData, HubContainerGrid
from ui.patterns.page_header import PageHeader


def StudentHub(
    student_name: str,
    student_uid: str,
    pending_count: int,
    revision_count: int,
    completed_count: int,
) -> Div:
    """Student hub — 4 container cards for submission workflow + KU progress."""
    base = f"/teaching/students/{student_uid}/submissions"

    cards: list[HubCardData] = [
        HubCardData(
            icon="📥",
            name="Needs Review",
            href=f"{base}?tab=pending",
            description="Submissions awaiting your review",
            badge=pending_count or None,
        ),
        HubCardData(
            icon="✏️",
            name="Revision Requested",
            href=f"{base}?tab=revision",
            description="Submissions sent back for revision",
            badge=revision_count or None,
        ),
        HubCardData(
            icon="✅",
            name="Completed",
            href=f"{base}?tab=completed",
            description="Reviewed and completed submissions",
            badge=completed_count or None,
        ),
        HubCardData(
            icon="📊",
            name="KU Progress",
            href=f"{base}?tab=ku",
            description="Knowledge unit learning progress",
        ),
    ]

    back_link = A(
        UkIcon("arrow-left", height=16, width=16, cls="inline mr-1"),
        "Students",
        href="/teaching/students",
        cls="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-4",
    )

    return Div(
        back_link,
        PageHeader(student_name, subtitle="Student overview"),
        HubContainerGrid(cards, cols=2),
    )
