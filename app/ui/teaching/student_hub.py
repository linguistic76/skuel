"""Student hub page — teacher's view of an individual student.

Hub page with no sidebar. HTMX-loaded preview blocks show actual submission
and KU progress data inline, matching the evolved hub pattern (Activities,
GradeBook, Library).
"""

from fasthtml.common import A, Div
from monsterui.franken import UkIcon

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader


def StudentHub(student_name: str, student_uid: str) -> Div:
    """Student hub — 4 domain blocks with HTMX-loaded previews."""
    base_href = f"/teaching/students/{student_uid}/submissions"
    base_api = f"/api/teaching/students/{student_uid}"

    # The 3 submission blocks share one DB call — populated via OOB swap from
    # /api/teaching/students/{uid}/submissions/preview (no individual preview_url).
    # KU progress has an independent data source so it self-loads as normal.
    blocks: list[HubBlockData] = [
        HubBlockData(
            label="Needs Review",
            slug="pending",
            icon="inbox",
            color="#F59E0B",
            href=f"{base_href}?tab=pending",
        ),
        HubBlockData(
            label="Revision Requested",
            slug="revision",
            icon="edit-3",
            color="#EF4444",
            href=f"{base_href}?tab=revision",
        ),
        HubBlockData(
            label="Completed",
            slug="completed",
            icon="check-circle",
            color="#10B981",
            href=f"{base_href}?tab=completed",
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

    # Single hidden trigger — fetches all 3 submission buckets in one DB round-trip,
    # swapping each into hub-panel-{slug} via OOB. Mirrors the sidebar badges pattern.
    oob_trigger = Div(
        hx_get=f"{base_api}/submissions/preview",
        hx_trigger="load",
        hx_swap="none",
    )

    return Div(
        back_link,
        PageHeader(student_name, subtitle="Student overview"),
        oob_trigger,
        HubDomainBlockList(blocks),
    )
