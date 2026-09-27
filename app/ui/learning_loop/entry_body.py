"""The body of a UserEntry as its readers see it — one box, one empty state.

The owner's GradeBook page and the teacher's review card both show the work
through ``EntryBody``: pre-wrapped text in a scrollable muted box, escaped like
any FastHTML string, and a stated empty state rather than a blank box.
"""

from fasthtml.common import FT, Div, P


def EntryBody(text: str | None, *, empty: str) -> FT:
    """The entry's text, or ``empty`` when there is none."""
    return Div(
        P(text, cls="whitespace-pre-wrap text-sm")
        if text
        else P(empty, cls="text-sm text-muted-foreground"),
        cls="p-4 bg-muted rounded-lg",
        style="max-height: 600px; overflow-y: auto;",
    )
