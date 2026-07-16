"""Submissions tab panel — Submissions tab on /profile.

SubmissionsTabPanel feeds the Submissions tab in ui/profile/hub.py: one
navigation button per /submissions sidebar category (see ui/workbench/nav.py).
"""

from fasthtml.common import Div

from ui.components import ButtonT, Icon
from ui.primitives import ButtonLink

_SUBMISSION_LINKS: tuple[tuple[str, str, str], ...] = (
    ("Sync", "/submissions/sync", "refresh-cw"),
    ("Exercises", "/submissions/exercise", "send"),
    ("Journals", "/submissions/journal", "book-open"),
    ("History", "/submissions/history", "clock"),
)


def SubmissionsTabPanel() -> Div:
    """Four link buttons mirroring the /submissions sidebar categories."""
    return Div(
        *[
            ButtonLink(
                Icon(icon, cls="size-4 mr-2"),
                label,
                href=href,
                cls=ButtonT.default,
                size="lg",
            )
            for label, href, icon in _SUBMISSION_LINKS
        ],
        cls="flex flex-col items-start gap-4",
    )


__all__ = ["SubmissionsTabPanel"]
