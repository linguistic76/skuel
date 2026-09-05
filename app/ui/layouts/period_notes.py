"""The "Notes" picker — one navbar door to all five periodic notes.

Daily → yearly notes are one click from every page, because the picker lives in
the top bar rather than on the calendar toolbar it started on (#1278). Global
chrome has no view context of its own, so the one thing the toolbar gave it for
free — *which* period each row opens — is recovered from the request path here:

- ``/cal/month/2026/10`` → the Monthly row opens October, the month on screen
- ``/cal/week/2026-08-20`` → the Weekly row opens that week
- ``/today/2026-08-02`` → the Daily row opens that day
- ``/journals/quarterly/2026/2`` → the Quarterly row opens the note being read
- anywhere else → every row opens the CURRENT period

That is the same mixed rule the toolbar carried (ruling 2026-09-05): the row for
the surface's OWN period follows the view, every other row opens the current
period. Reading it off the path keeps it working on the calendar and extends it
to the periodic notes themselves, with no per-page plumbing — but it does bind
this module to those route shapes, so a route rename must be mirrored in
:func:`viewed_period` (``tests/unit/ui/test_navbar_period_notes.py`` pins each
one against the registered path).

The picker renders on EVERY page, so :func:`viewed_period` never raises: a
malformed date in a URL falls back to "no view" rather than 500-ing the chrome
around it.
"""

from __future__ import annotations

from datetime import date

from fasthtml.common import A, Div, Span
from fasthtml.common import Button as HtmlButton

from ui.components import Icon
from ui.journals.period_links import PERIOD_KINDS, PERIOD_NAMES, period_link
from ui.primitives import dropdown_menu

# Force a full browser navigation (journal routes answer with a 302 redirect
# that HTMX boost would otherwise swap into the current target).
_NO_BOOST = {"hx-boost": "false"}

# Calendar view segment → the period kind it shows.
_CAL_VIEW_KINDS: dict[str, str] = {"month": "monthly", "week": "weekly"}


def _journal_period(kind: str, args: list[str]) -> tuple[str, date]:
    """A ``/journals/{kind}/...`` URL's period, as (kind, a date inside it).

    Each branch mirrors the route's own signature — ``weekly/{year}/{week}``
    carries an ISO week, ``quarterly/{year}/{quarter}`` a quarter index — and
    every conversion below raises ``ValueError`` on a nonsense value, which
    :func:`viewed_period` turns into "no view".
    """
    if kind == "daily":
        return (kind, date.fromisoformat(args[0]))
    if kind == "weekly":
        return (kind, date.fromisocalendar(int(args[0]), int(args[1]), 1))
    if kind == "monthly":
        return (kind, date(int(args[0]), int(args[1]), 1))
    if kind == "quarterly":
        return (kind, date(int(args[0]), int(args[1]) * 3 - 2, 1))
    return (kind, date(int(args[0]), 1, 1))


def _derive(parts: list[str]) -> tuple[str, date]:
    """The period a path shows, or ``("", today)`` when it shows none."""
    today = date.today()
    if not parts:
        return ("", today)
    if parts[0] == "today":
        # /today, /today/{date_str}
        return ("daily", date.fromisoformat(parts[1]) if len(parts) > 1 else today)
    if parts[0] == "cal" and len(parts) > 1:
        kind = _CAL_VIEW_KINDS.get(parts[1], "")
        if kind == "monthly":
            # /cal/month, /cal/month/{year}/{month}
            if len(parts) > 3:
                return (kind, date(int(parts[2]), int(parts[3]), 1))
            return (kind, today.replace(day=1))
        if kind == "weekly":
            # /cal/week, /cal/week/{date_str}
            return (kind, date.fromisoformat(parts[2]) if len(parts) > 2 else today)
        return ("", today)
    if parts[0] == "journals" and len(parts) > 1 and parts[1] in PERIOD_KINDS:
        # /journals/{kind}/... — the yearly note is the only one-argument form,
        # and a kind reached with no argument at all keeps its current period.
        if len(parts) > 2:
            return _journal_period(parts[1], parts[2:])
        return (parts[1], today)
    return ("", today)


def viewed_period(path: str) -> tuple[str, date]:
    """The period the page at ``path`` is showing: (kind, a date inside it).

    ``("", today)`` means the page shows no period — the picker then opens the
    current one on every row. An unparseable date, month or week resolves the
    same way: the navbar renders everywhere, so a hand-typed URL must degrade
    to a working menu, never to a broken page.
    """
    parts = [segment for segment in path.split("/") if segment]
    try:
        return _derive(parts)
    except ValueError, IndexError:
        return ("", date.today())


def _period_note_row(kind: str, ref_date: date) -> A:
    """One period's row in the Notes menu — its name, then the period it opens.

    The trailing short label ("W36", "September", "Q3") is what makes the menu
    self-documenting: the row heading names the KIND, the label names the
    period, so a row that does not follow the viewed period says so on its face.
    """
    link = period_link(kind, ref_date)
    name = PERIOD_NAMES[kind]
    return A(
        Span(name, cls="text-13 font-medium"),
        Span(
            link.short_label,
            cls="ml-auto text-11 text-muted-foreground tabular-nums whitespace-nowrap",
        ),
        href=link.href,
        title=f"Open the {link.label} note",
        aria_label=f"{name} note — {link.label}",
        **_NO_BOOST,
        cls=(
            "flex items-center gap-4 px-[11px] py-2 rounded-[9px] no-underline"
            " text-foreground hover:bg-muted focus-visible:bg-muted"
        ),
    )


def PeriodNotesPicker(path: str) -> Div:
    """The navbar "Notes" disclosure — one door to all five periodic notes.

    A disclosure, not an ARIA menu: every row is a plain navigation link, so Tab
    walks them and Escape closes, with no arrow-key roving to hand-roll (Alpine's
    focus plugin is not vendored).

    ``path`` is the request path; :func:`viewed_period` reads the shown period
    off it, and the matching row follows that period instead of the current one.
    """
    own_kind, own_date = viewed_period(path)
    today = date.today()
    rows = [
        _period_note_row(kind, own_date if kind == own_kind else today) for kind in PERIOD_KINDS
    ]
    return Div(
        HtmlButton(
            Span("Notes", cls="sr-only"),
            Icon("square-pen", cls="size-6", aria_hidden="true"),
            type="button",
            aria_expanded="false",
            aria_controls="period-note-menu",
            cls=(
                "inline-flex items-center justify-center size-11 rounded-full cursor-pointer"
                " hover:bg-accent text-muted-foreground hover:text-foreground"
            ),
            **{
                "x-ref": "trigger",
                "@click": "open = !open",
                ":aria-expanded": "open ? 'true' : 'false'",
            },
        ),
        dropdown_menu(
            *rows,
            align="right",
            cls="w-[232px]",
            id="period-note-menu",
            **{
                "x-show": "open",
                "x-cloak": True,  # boundary: fasthtml-elements
                "@click.outside": "open = false",
            },
        ),
        cls="relative",
        **{
            "x-data": "{ open: false }",
            # Escape anywhere inside (trigger or a focused row) closes and hands
            # focus back to the trigger, so keyboard focus never lands nowhere.
            "@keydown.escape": "open = false; $refs.trigger.focus()",
        },
    )


__all__ = ["PeriodNotesPicker", "viewed_period"]
