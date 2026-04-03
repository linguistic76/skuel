"""Student hub page — teacher's view of an individual student.

Hub page with no sidebar. HTMX-loaded preview blocks show actual submission
and KU progress data inline, matching the evolved hub pattern (Activities,
GradeBook, Library).
"""

from fasthtml.common import A, Div
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader


def StudentHub(student_name: str, student_uid: str) -> Div:
    """Student hub — 4 domain blocks with HTMX-loaded previews."""
    base_href = f"/teaching/students/{student_uid}/submissions"
    base_api = f"/api/teaching/students/{student_uid}"

    blocks: list[HubBlockData] = [
        HubBlockData(
            label="Needs Review",
            slug="pending",
            icon="inbox",
            color="#F59E0B",
            href=f"{base_href}?tab=pending",
            preview_url=f"{base_api}/pending/preview",
        ),
        HubBlockData(
            label="Revision Requested",
            slug="revision",
            icon="edit-3",
            color="#EF4444",
            href=f"{base_href}?tab=revision",
            preview_url=f"{base_api}/revision/preview",
        ),
        HubBlockData(
            label="Completed",
            slug="completed",
            icon="check-circle",
            color="#10B981",
            href=f"{base_href}?tab=completed",
            preview_url=f"{base_api}/completed/preview",
        ),
        HubBlockData(
            label="KU Progress",
            slug="ku",
            icon="bar-chart-2",
            color="#8B5CF6",
            href=f"{base_href}?tab=ku",
            preview_url=f"{base_api}/ku/preview",
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
        HubDomainBlockList(blocks),
    )
