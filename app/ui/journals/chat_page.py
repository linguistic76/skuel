"""Journal chat page — dedicated session view at /journals/{entry_uid}.

Two-column layout: collapsible sidebar (session history, search, identity)
and a main workspace area where HTMX stage/follow-up fragments are swapped.
Mirrors the Askesis shell from ui/askesis/chat.py.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Button, Div, Form, Input, P, Span

from ui.components import Icon
from ui.journals.period_links import (
    PERIOD_ICONS,
    PERIOD_KINDS,
    PERIOD_NAMES,
    period_link,
    period_step,
)
from ui.journals.period_panel import (
    monthly_period_start,
    quarterly_period_start,
    weekly_period_start,
    yearly_period_start,
)

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.conversation import ConversationSession
    from core.models.user.user import User
    from core.models.user_entry.user_entry import UserEntry


def JournalsLandingPage(
    user: "User",
    shelf_books: "list[dict[str, str]] | None" = None,
    sessions: "list[ConversationSession] | None" = None,
    workspace: Any = None,
    model_options: "list[tuple[str, str]] | None" = None,
) -> Any:
    """3-column journal landing page — Claude.ai project-view style.

    Left: collapsible sidebar (New Journal + the revisit list of past
    discussions). Center: chat input with the discussion source panel (FOUNDER
    canon-shelf checkboxes + vault toggle), or — when ``workspace`` is passed —
    a rehydrated discussion thread (continue, ADR-078). Right: compact
    Processing / Sources / Browse upload panel. No Tasks+ sidebar — uses
    BasePage(CUSTOM).

    ``shelf_books`` is the canon shelf (``resource_uid`` + ``title`` per book) —
    the route passes it only for FOUNDERs; empty/omitted renders no picker.
    ``sessions`` are the user's owned discussion sessions (revisit list, ADR-078);
    ``workspace`` pre-fills ``#journal-workspace`` for a continued session.
    ``model_options`` are the ``(value, label)`` models the caller can serve — the
    LLM switcher's options on the start form (empty → no picker, safe default).
    """
    is_founder = user.journal_tier.is_founder()
    from ui.journals.forms import render_right_panel, upload_form_script

    return Div(
        journal_sidebar(user, sessions or []),
        _landing_center_column(
            shelf_books or [], is_founder, workspace=workspace, model_options=model_options or []
        ),
        Div(
            render_right_panel(is_founder=is_founder),
            upload_form_script(),
            cls=("w-[320px] shrink-0 border-l border-slate-100 bg-slate-50 overflow-y-auto p-4"),
        ),
        cls="flex overflow-hidden bg-background",
        style="height: calc(100vh - 3.5rem);",
        # sessionActive: "New Journal" is a reset button. /journals/start swaps the
        # conversation into #journal-workspace with the URL still /journals, so the
        # only signal that a reset has anything to reset is that swap event.
        **{
            "x-data": (
                "{ sidebarOpen: localStorage.getItem('journal-sidebar') !== 'false',"
                f" sessionActive: {'true' if workspace is not None else 'false'} }}"
            ),
            "@htmx:after-swap.window": (
                "if ($event.detail.target.id === 'journal-workspace') sessionActive = true"
            ),
        },
    )


def PeriodicNotePage(
    entry: "UserEntry",
    initial_workspace: Any,
    planning_panel: "FT | None" = None,
) -> Any:
    """Full-height layout for periodic notes (daily/weekly/monthly).

    Uses a compact calendar navigation sidebar instead of the journal session
    sidebar — periodic notes are date-oriented, not pipeline-session-oriented.

    ``planning_panel`` — the note's read panel of the period's existing
    entities (periodic-notes arc S3), rendered as a right column. The route
    passes it for weekly and monthly notes; the daily page stays two-column.
    """
    columns: list[FT] = [
        _periodic_note_sidebar(entry),
        Div(
            initial_workspace,
            cls="flex-1 flex flex-col overflow-hidden",
        ),
    ]
    if planning_panel is not None:
        columns.append(
            Div(
                planning_panel,
                cls=("w-[300px] shrink-0 border-l border-border bg-slate-50 overflow-y-auto p-4"),
            )
        )
    return Div(
        *columns,
        cls="flex overflow-hidden bg-background",
        style="height: calc(100vh - 3.5rem);",
    )


def _periodic_note_sidebar(entry: "UserEntry") -> Any:
    """The periodic note's navigation column: a mini month, then a period rail.

    Two pickers, no overlap. The **mini month** is the fine-grained one — its
    day cells open daily notes and its ISO-week rail opens weekly notes, the
    same two doors the full month grid carries (``ui/calendar/components.py``),
    so the sidebar teaches the same gesture as the calendar it shrinks. The
    **period rail** below it is the coarse one: one row per period kind, each
    naming the period this note sits inside, opening it, and stepping to its
    neighbours.

    Every row is present on every note — the rail is the same five rows whether
    you are reading a day or a year, with the note's own row marked current —
    so there is exactly one prev/next mechanism to learn.
    """
    kind = entry.metadata.get("entry_kind", "daily")
    # period_key is stamped by the calendar routes but not by vault ingestion;
    # the UID always encodes it as the last colon-delimited segment.
    period_key = entry.metadata.get("period_key") or entry.uid.rsplit(":", 1)[-1]
    ref_date, highlight_dates = _note_anchor(kind, period_key)
    # The rail's own row for a weekly note is the week rail's row too, so the
    # week number is marked alongside its seven days.
    iso_year, iso_week, _ = ref_date.isocalendar()
    active_week = (iso_year, iso_week) if kind == "weekly" else None

    return Div(
        Div(
            A(
                Icon("chevron-left", size=14),
                Span("Calendar", cls="text-13"),
                href="/cal",
                cls=(
                    "flex items-center gap-1 text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            cls="px-4 py-3 border-b border-border",
        ),
        Div(
            _mini_month_calendar(ref_date, highlight_dates, active_week),
            cls="py-3",
        ),
        _period_rail(kind, ref_date),
        cls=("w-[240px] shrink-0 border-r border-border bg-slate-50 flex flex-col overflow-y-auto"),
    )


def _note_anchor(kind: str, period_key: str) -> "tuple[datetime.date, set[datetime.date]]":
    """Where the sidebar centres, and which days the mini month marks.

    The anchor is the note's period START, so a week crossing a month boundary
    shows (and ladders up to) its Monday's month — the same anchor the ISO week
    and the planning panel's range already use. A period_key the parsers reject
    falls back to the current period rather than raising: the sidebar renders
    around whatever the route already served.

    Only the two periods a month grid can draw are marked — a day and its week.
    A month, quarter or year would either mark the whole grid or lie about
    where it ends, so those notes get an unmarked calendar and lean on the rail.
    """
    from datetime import date, timedelta

    today = date.today()
    if kind == "daily":
        try:
            day = date.fromisoformat(period_key)
        except ValueError:
            day = today
        return day, {day}
    if kind == "weekly":
        monday = weekly_period_start(period_key)
        if monday is None:
            monday = today - timedelta(days=today.weekday())
        return monday, {monday + timedelta(days=offset) for offset in range(7)}
    if kind == "monthly":
        month_start = monthly_period_start(period_key)
        return (month_start if month_start is not None else today.replace(day=1)), set()
    if kind == "quarterly":
        quarter_start = quarterly_period_start(period_key)
        if quarter_start is None:
            quarter_start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        return quarter_start, set()
    if kind == "yearly":
        year_start = yearly_period_start(period_key)
        return (year_start if year_start is not None else today.replace(month=1, day=1)), set()
    return today, set()


# ─────────────────────────────────────────────────────────────────────────────
# Period rail — one row per period kind, on every periodic note
# ─────────────────────────────────────────────────────────────────────────────
#
# Replaces the "up"-links ladder (#1277) that showed only the periods WIDER
# than the note and could not step between notes of a kind. The rail shows all
# five, because a rail that changes shape per note is a rail you re-read every
# time, and every row steps.
#
# Journal routes answer with a 302 redirect that HTMX boost would swap into the
# current target instead of navigating, so every rail link opts out.
_NO_BOOST = {"hx-boost": "false"}


def _period_rail(kind: str, ref_date: datetime.date) -> Any:
    """The five period rows, narrowest first — day at the top, year at the bottom.

    Narrowest-first matches the calendar above it (days, then their week) and
    the navbar picker's order, so the three surfaces read top-to-bottom the
    same way.
    """
    return Div(
        *[
            _period_rail_row(row_kind, ref_date, is_current=row_kind == kind)
            for row_kind in PERIOD_KINDS
        ],
        cls="flex flex-col gap-0.5 px-2 py-2 border-t border-border",
    )


def _period_rail_row(kind: str, ref_date: datetime.date, *, is_current: bool) -> Any:
    """One period: step back, open it, step forward.

    ``is_current`` marks the row for the note being read. It is a visual mark
    plus ``aria-current`` — the row still links to its own note, because the
    label is also how you get *back* after wandering the calendar.
    """
    link = period_link(kind, ref_date)
    name = PERIOD_NAMES[kind]
    label_cls = (
        "flex-1 flex items-center gap-1.5 min-w-0 px-1.5 py-1 rounded-[6px] no-underline"
        " transition-colors"
    )
    label_cls += (
        " bg-slate-200 text-foreground font-semibold"
        if is_current
        else " text-muted-foreground hover:text-foreground hover:bg-slate-200"
    )
    return Div(
        _period_rail_step(kind, ref_date, -1, name),
        A(
            Icon(PERIOD_ICONS[kind], size=13, cls="shrink-0"),
            Span(link.label, cls="text-11 truncate"),
            href=link.href,
            title=f"Open the {link.label} note",
            aria_label=f"{name} note — {link.label}",
            aria_current="page" if is_current else None,
            **_NO_BOOST,
            cls=label_cls,
        ),
        _period_rail_step(kind, ref_date, 1, name),
        cls="flex items-center gap-0.5",
    )


def _period_rail_step(kind: str, ref_date: datetime.date, steps: int, name: str) -> Any:
    """One prev/next arrow — the neighbouring period's note.

    The neighbour is named in the tooltip and the accessible name, so a step
    across a month, quarter or year boundary says where it went before you
    take it. Arithmetic: :func:`ui.journals.period_links.period_step`.
    """
    link = period_link(kind, period_step(kind, ref_date, steps))
    direction = "Previous" if steps < 0 else "Next"
    return A(
        Icon("chevron-left" if steps < 0 else "chevron-right", size=13),
        href=link.href,
        title=f"{direction}: {link.label}",
        aria_label=f"{direction} {name.lower()} note — {link.label}",
        **_NO_BOOST,
        cls=(
            "shrink-0 flex items-center justify-center w-5 h-6 rounded-[6px]"
            " text-muted-foreground hover:text-foreground hover:bg-slate-200"
            " transition-colors no-underline"
        ),
    )


def _mini_month_calendar(
    ref_date: datetime.date,
    highlight_dates: "set[datetime.date]",
    active_week: "tuple[int, int] | None" = None,
) -> Any:
    """A month at sidebar scale, with the same two doors as the full month grid.

    Day cells open daily notes; the leading ISO-week rail opens weekly notes —
    the mini form of ``create_month_grid``'s rail (``ui/calendar/components.py``),
    down to the Monday-first columns the ISO week numbers depend on.

    ``highlight_dates`` marks the days the note covers; ``active_week`` is the
    ``(iso_year, iso_week)`` of a weekly note, marking its number in the rail.
    """
    import calendar as _cal
    from datetime import date

    today = date.today()
    year, month = ref_date.year, ref_date.month
    month_name = ref_date.strftime("%B %Y")
    dow_headers = ["M", "T", "W", "T", "F", "S", "S"]
    weeks = _cal.monthcalendar(year, month)

    def _day_cell(day_num: int) -> Any:
        if day_num == 0:
            return Div(cls="w-6 h-6")
        d = date(year, month, day_num)
        is_hi = d in highlight_dates
        is_today = d == today
        if is_hi and is_today:
            cls = (
                "w-6 h-6 flex items-center justify-center text-11 rounded-full"
                " bg-foreground text-background font-bold ring-2 ring-offset-1 ring-foreground"
            )
        elif is_hi:
            cls = (
                "w-6 h-6 flex items-center justify-center text-11 rounded-full"
                " bg-foreground text-background font-semibold"
            )
        elif is_today:
            cls = (
                "w-6 h-6 flex items-center justify-center text-11 rounded-full"
                " ring-1 ring-foreground font-medium text-foreground"
            )
        else:
            cls = (
                "w-6 h-6 flex items-center justify-center text-11 rounded-full"
                " hover:bg-slate-200 text-foreground"
            )
        return A(
            str(day_num),
            href=f"/journals/daily/{d.isoformat()}",
            title=f"Daily note — {d:%a, %b %-d}",
            **_NO_BOOST,
            cls=f"{cls} no-underline",
        )

    def _week_rail(week: "list[int]") -> Any:
        """The week number for a rendered row, linked to its weekly note.

        The row's own days name the week: any real day in it carries the same
        ISO week, and a row always has one (``monthcalendar`` never emits an
        all-zero row).
        """
        anchor = date(year, month, next(day for day in week if day))
        iso_year, iso_week, _ = anchor.isocalendar()
        is_active = active_week == (iso_year, iso_week)
        cls = (
            "w-5 h-6 flex items-center justify-center font-mono text-10 rounded-[4px]"
            " no-underline transition-colors"
        )
        cls += (
            " bg-foreground text-background font-semibold"
            if is_active
            else " text-muted-foreground hover:text-foreground hover:bg-slate-200"
        )
        return A(
            str(iso_week),
            href=f"/journals/weekly/{iso_year}/{iso_week}",
            title=f"Weekly note — W{iso_week}, {iso_year}",
            aria_label=f"Weekly note — week {iso_week} of {iso_year}",
            **_NO_BOOST,
            cls=cls,
        )

    return Div(
        Div(
            Span(month_name, cls="text-xs font-semibold text-foreground"),
            cls="flex justify-center mb-3 px-1",
        ),
        Div(
            Div(
                "WK",
                cls="w-5 text-10 text-muted-foreground text-center font-bold tracking-[0.04em]",
            ),
            *[
                Div(h, cls="w-6 text-10 text-muted-foreground text-center font-medium")
                for h in dow_headers
            ],
            cls="flex gap-0.5 mb-1",
        ),
        *[
            Div(_week_rail(week), *[_day_cell(d) for d in week], cls="flex gap-0.5 mb-0.5")
            for week in weeks
        ],
        cls="px-3",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────


def journal_sidebar(user: "User", sessions: "list[ConversationSession] | None" = None) -> Any:
    return Div(
        # Full sidebar (shown when open): entry point, the revisit list of past
        # discussions (ADR-078 — owner-private sessions), and identity.
        Div(
            _sb_header(),
            _sb_new_journal_btn(),
            discussions_revisit_panel(sessions or []),
            _sb_identity_footer(user),
            cls="flex flex-col h-full",
            **{"x-show": "sidebarOpen"},
        ),
        # Collapsed rail (shown when closed)
        Div(
            Button(
                Icon("panel-left-open", size=16),
                cls=(
                    "w-8 h-8 flex items-center justify-center rounded-lg"
                    " text-muted-foreground hover:bg-slate-100 hover:text-slate-600"
                    " transition-colors"
                ),
                type="button",
                aria_label="Expand sidebar",
                **{
                    "@click": (
                        "sidebarOpen = true; localStorage.setItem('journal-sidebar', 'true')"
                    )
                },
            ),
            Button(
                Icon("square-pen", size=16, cls="text-slate-600"),
                cls=(
                    "w-8 h-8 flex items-center justify-center rounded-lg"
                    " border border-border hover:bg-slate-100 transition-colors"
                ),
                type="button",
                aria_label="New Journal",
                **{
                    "@click": "window.location.href='/journals'",
                    "x-show": "sessionActive",
                    "x-cloak": True,
                },
            ),
            Div(cls="flex-1"),
            Div(
                (user.display_name or user.title or "U")[0].upper(),
                cls=(
                    "w-[30px] h-[30px] rounded-full bg-foreground/10 text-foreground"
                    " flex items-center justify-center text-sm font-semibold"
                ),
            ),
            cls="flex flex-col items-center gap-3 py-3 px-2 h-full",
            **{"x-show": "!sidebarOpen", "x-cloak": True},
        ),
        style="width:274px;",
        cls=(
            "bg-slate-50 border-r border-slate-100 shrink-0 overflow-hidden"
            " transition-all duration-300"
        ),
        **{":style": "{ width: sidebarOpen ? '274px' : '62px' }"},
    )


def _sb_header() -> Any:
    return Div(
        Span("Journal", cls="text-lg font-bold tracking-tight text-foreground"),
        Button(
            Icon("panel-left-close", size=16),
            cls=(
                "w-8 h-8 flex items-center justify-center rounded-lg"
                " text-muted-foreground hover:bg-slate-100 hover:text-slate-600"
                " transition-colors"
            ),
            type="button",
            aria_label="Collapse sidebar",
            **{"@click": ("sidebarOpen = false; localStorage.setItem('journal-sidebar', 'false')")},
        ),
        cls="flex items-center justify-between px-4 py-4",
    )


def _sb_new_journal_btn() -> Any:
    return Div(
        A(
            Icon("square-pen", size=17, cls="text-slate-600 shrink-0"),
            Span("New Journal", cls="text-sm font-semibold text-foreground"),
            href="/journals",
            cls=(
                "w-full flex items-center gap-2 px-3 py-[10px] rounded-[10px]"
                " border border-border bg-background hover:bg-slate-50"
                " transition-colors shadow-xs no-underline"
            ),
        ),
        cls="px-3 pb-3",
        **{"x-show": "sessionActive", "x-cloak": True},
    )


def _sb_identity_footer(user: "User") -> Any:
    initials = (user.display_name or user.title or "U")[0].upper()
    name = user.display_name or user.title or "User"
    tier = getattr(user.journal_tier, "value", str(user.journal_tier)).upper()
    return Div(
        Div(
            initials,
            cls=(
                "w-[30px] h-[30px] rounded-full bg-foreground/10 text-foreground"
                " flex items-center justify-center text-sm font-semibold shrink-0"
            ),
        ),
        Div(
            Div(name, cls="text-13 font-semibold text-foreground leading-tight"),
            Span(
                tier,
                cls=(
                    "text-10 font-semibold px-1.5 py-0.5 rounded-[4px]"
                    " bg-foreground/10 text-foreground/70 uppercase tracking-wide"
                ),
            ),
            cls="flex-1 min-w-0",
        ),
        cls="flex items-center gap-2 px-4 py-3 border-t border-border",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Revisit list — past discussions (ADR-078)
# ─────────────────────────────────────────────────────────────────────────────


def discussions_revisit_panel(sessions: "list[ConversationSession]", *, oob: bool = False) -> Any:
    """Scrollable list of the user's owned discussions (revisit, ADR-078).

    Carries a stable ``id=journal-discussions-panel`` so ``POST /journals/save``
    can OOB-swap the whole panel (``oob=True``) after a chat is saved — the newly
    saved discussion appears in the sidebar without a reload, and its per-row
    delete IS the un-save (ADR-078 §5).
    """
    if not sessions:
        body: Any = P(
            "Your past discussions appear here.",
            cls="text-xs text-muted-foreground px-4 py-2 leading-snug",
        )
    else:
        body = Div(
            *[DiscussionRow(session) for session in sessions],
            id="journal-discussions",
            cls="flex flex-col gap-0.5 px-2",
        )
    oob_attr = {"hx_swap_oob": "true"} if oob else {}
    return Div(
        P(
            "Discussions",
            cls=(
                "text-11 font-semibold uppercase tracking-wide text-muted-foreground px-4 pt-3 pb-1"
            ),
        ),
        body,
        id="journal-discussions-panel",
        cls="flex-1 overflow-y-auto min-h-0",
        **oob_attr,
    )


def DiscussionRow(session: "ConversationSession") -> Any:
    """One revisit-list row: title link + hover actions (rename/export/delete).

    Inline rename toggles an Alpine ``editing`` flag local to the row; the rename
    POST swaps the whole row (``outerHTML``) with the re-rendered fragment.
    """
    sid = session.session_id
    title = session.title or "Untitled discussion"
    return Div(
        Div(
            A(
                title,
                href=f"/journals/discussion/{sid}",
                title=title,
                cls=(
                    "flex-1 min-w-0 truncate text-13 text-foreground/90 no-underline"
                    " hover:text-foreground py-0.5"
                ),
            ),
            _DiscussionRowActions(sid, title),
            cls="flex items-center gap-1",
            **{"x-show": "!editing"},
        ),
        Form(
            Input(
                name="title",
                value=title,
                cls=(
                    "flex-1 min-w-0 text-13 px-2 py-1 rounded-sm border border-border"
                    " bg-background outline-hidden focus:border-foreground/40"
                ),
                **{"x-ref": "titleInput", "@keydown.escape": "editing = false"},
            ),
            hx_post=f"/journals/discussion/{sid}/rename",
            hx_target="closest [data-discussion-row]",
            hx_swap="outerHTML",
            cls="flex items-center gap-1",
            **{"x-show": "editing", "x-cloak": True, "@submit": "editing = false"},
        ),
        cls="group px-2 py-1.5 rounded-lg hover:bg-slate-100 transition-colors",
        **{"x-data": "{ editing: false }", "data-discussion-row": sid},
    )


def _DiscussionRowActions(sid: str, title: str) -> Any:
    """Hover-revealed rename / export / delete controls for a discussion row."""
    btn = (
        "w-6 h-6 flex items-center justify-center rounded-sm text-muted-foreground"
        " hover:bg-slate-200 hover:text-foreground opacity-0 group-hover:opacity-100"
        " transition-opacity"
    )
    return Div(
        Button(
            Icon("pencil", size=13),
            type="button",
            aria_label="Rename discussion",
            cls=btn,
            **{"@click": "editing = true; $nextTick(() => $refs.titleInput.focus())"},
        ),
        A(
            Icon("download", size=13),
            href=f"/journals/discussion/{sid}/export",
            aria_label="Export discussion",
            cls=btn + " no-underline",
        ),
        Button(
            Icon("trash-2", size=13),
            type="button",
            aria_label="Delete discussion",
            cls=btn + " hover:text-destructive",
            hx_post=f"/journals/discussion/{sid}/delete",
            hx_target="closest [data-discussion-row]",
            hx_swap="outerHTML",
            hx_confirm=f"Delete “{title}”? This can't be undone.",
        ),
        cls="flex items-center gap-0.5 shrink-0",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Landing page center column
# ─────────────────────────────────────────────────────────────────────────────


def _landing_center_column(
    shelf_books: "list[dict[str, str]]",
    is_founder: bool,
    workspace: Any = None,
    model_options: "list[tuple[str, str]] | None" = None,
) -> Any:
    # A flex-1 flex-col wrapper whose direct child carries id="journal-workspace".
    # /journals/start retargets here (HX-Retarget) and replaces the child in place
    # with the response fragment (itself `flex flex-col h-full`). When ``workspace``
    # is passed (a continued session, ADR-078), it IS that fragment and is rendered
    # directly; otherwise the fresh-entry input form opens.
    if workspace is not None:
        center = workspace  # already carries id="journal-workspace"
    else:
        center = Div(
            Div(
                Div(
                    P("Journal", cls="text-xl font-bold text-foreground"),
                    P(
                        "Your private thinking space.",
                        cls="text-15 text-muted-foreground mt-1",
                    ),
                    cls="mb-6",
                ),
                _landing_text_form(shelf_books, is_founder, model_options or []),
                cls="max-w-[640px] mx-auto pt-10 px-6",
            ),
            id="journal-workspace",
            cls="flex-1 overflow-y-auto",
        )
    return Div(
        center,
        cls="flex-1 flex flex-col overflow-hidden",
    )


def _landing_source_panel(shelf_books: "list[dict[str, str]]") -> Any:
    """FOUNDER discussion source picker — canon shelf checkboxes + vault toggle.

    A native ``<details>`` disclosure (no JS) inside the composer form, so the
    checked ``canon_book_uids`` and ``summon_vault`` POST alongside ``raw_entry``.
    Per-book checkboxes wire straight through ``retrieve(resource_uids=...)`` —
    checked-none = no canon, checked-some = scoped, checked-all = whole shelf
    (C3). Rendered only for FOUNDERs (the canon/vault dials' entitlement).
    """
    from fasthtml.common import Details, Input, Label, Summary

    book_rows = [
        Label(
            Input(
                type="checkbox",
                name="canon_book_uids",
                value=book["resource_uid"],
                cls="mr-2 align-middle accent-foreground",
            ),
            book["title"] or "(untitled)",
            cls=("flex items-center text-13 text-foreground/80 cursor-pointer select-none py-0.5"),
        )
        for book in shelf_books
    ]

    canon_section = (
        Div(
            P(
                "Canon shelf",
                cls="text-11 font-semibold uppercase tracking-wide text-muted-foreground mb-1",
            ),
            *book_rows,
            cls="mb-3",
        )
        if book_rows
        else P(
            "No books are on the shelf yet.",
            cls="text-xs leading-snug text-muted-foreground mb-3",
        )
    )

    return Details(
        Summary(
            "Sources",
            cls=(
                "text-13 font-medium text-muted-foreground cursor-pointer select-none"
                " list-none hover:text-foreground"
            ),
        ),
        Div(
            canon_section,
            Label(
                Input(
                    type="checkbox",
                    name="summon_vault",
                    value="true",
                    cls="mr-2 align-middle accent-foreground",
                ),
                "Draw on my vault",
                cls=("flex items-center text-13 text-foreground/80 cursor-pointer select-none"),
            ),
            cls="mt-2 pl-1",
        ),
        cls="mt-3 pt-3 border-t border-border",
    )


def _landing_text_form(
    shelf_books: "list[dict[str, str]]",
    is_founder: bool,
    model_options: "list[tuple[str, str]] | None" = None,
) -> Any:
    from fasthtml.common import Form, Textarea

    from ui.journals import ModelControl

    return Div(
        Form(
            Div(
                Textarea(
                    name="raw_entry",
                    placeholder="What's on your mind?",
                    rows="5",
                    required=True,
                    cls=(
                        "w-full border-none outline-hidden bg-transparent resize-none"
                        " text-15 leading-[1.6] text-foreground"
                        " placeholder:text-muted-foreground"
                    ),
                ),
                Div(
                    # Per-conversation model switcher for the NEW discussion (empty
                    # options → a hidden field with the safe default).
                    ModelControl("", model_options),
                    Button(
                        Icon("arrow-up", size=16, cls="text-white"),
                        type="submit",
                        aria_label="Start journal entry",
                        cls=(
                            "w-[34px] h-[34px] rounded-full flex items-center justify-center"
                            " bg-foreground hover:bg-foreground/80 transition-colors"
                        ),
                    ),
                    cls="flex justify-between items-center mt-2",
                ),
                # Discussion sources live from message one (FOUNDER dials).
                _landing_source_panel(shelf_books) if is_founder else None,
                cls=(
                    "border border-border rounded-[20px] px-[18px] pt-4 pb-3"
                    " bg-background shadow-xs"
                ),
            ),
            P(
                "Thinking…",
                id="start-loading",
                cls="text-sm text-muted-foreground htmx-indicator mt-2",
            ),
            Div(id="start-status", cls="mt-2"),
            hx_post="/journals/start",
            hx_target="#start-status",
            hx_swap="outerHTML",
            hx_indicator="#start-loading",
        ),
        cls="mb-8",
    )
