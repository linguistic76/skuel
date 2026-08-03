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
from ui.journals.week_panel import weekly_period_start

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
            cls=(
                "w-[320px] flex-shrink-0 border-l border-slate-100 bg-slate-50 overflow-y-auto p-4"
            ),
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
    week_panel: "FT | None" = None,
) -> Any:
    """Full-height layout for periodic notes (daily/weekly/monthly).

    Uses a compact calendar navigation sidebar instead of the journal session
    sidebar — periodic notes are date-oriented, not pipeline-session-oriented.

    ``week_panel`` — the weekly note's read panel of the week's existing
    entities (periodic-notes arc S3), rendered as a right column. Only the
    weekly-note route passes it; daily/monthly pages stay two-column.
    """
    columns: list[FT] = [
        _periodic_note_sidebar(entry),
        Div(
            initial_workspace,
            cls="flex-1 flex flex-col overflow-hidden",
        ),
    ]
    if week_panel is not None:
        columns.append(
            Div(
                week_panel,
                cls=(
                    "w-[300px] flex-shrink-0 border-l border-border bg-slate-50 overflow-y-auto p-4"
                ),
            )
        )
    return Div(
        *columns,
        cls="flex overflow-hidden bg-background",
        style="height: calc(100vh - 3.5rem);",
    )


def _periodic_note_sidebar(entry: "UserEntry") -> Any:
    from datetime import date, timedelta

    kind = entry.metadata.get("entry_kind", "daily")
    # period_key is stamped by the calendar routes but not by vault ingestion;
    # the UID always encodes it as the last colon-delimited segment.
    period_key = entry.metadata.get("period_key") or entry.uid.rsplit(":", 1)[-1]
    today = date.today()

    if kind == "daily":
        try:
            ref_date = date.fromisoformat(period_key)
        except ValueError:
            ref_date = today
        highlight_dates: set[date] = {ref_date}
        prev_d = ref_date - timedelta(days=1)
        next_d = ref_date + timedelta(days=1)
        prev_url = f"/journals/daily/{prev_d.isoformat()}"
        next_url = f"/journals/daily/{next_d.isoformat()}"
        prev_label = prev_d.strftime("%a, %b %-d")
        next_label = next_d.strftime("%a, %b %-d")
    elif kind == "weekly":
        monday = weekly_period_start(period_key)
        ref_date = monday if monday is not None else today - timedelta(days=today.weekday())
        highlight_dates = {ref_date + timedelta(days=i) for i in range(7)}
        prev_mon = ref_date - timedelta(weeks=1)
        next_mon = ref_date + timedelta(weeks=1)
        py, pw, _ = prev_mon.isocalendar()
        ny, nw, _ = next_mon.isocalendar()
        prev_url = f"/journals/weekly/{py}/{pw}"
        next_url = f"/journals/weekly/{ny}/{nw}"
        prev_label = f"Week {pw}"
        next_label = f"Week {nw}"
    elif kind == "monthly":
        parts = period_key.split("-")
        try:
            year_m = int(parts[0]) if len(parts) > 0 else today.year
            month_m = int(parts[1]) if len(parts) > 1 else today.month
            ref_date = date(year_m, month_m, 1)
        except ValueError:
            ref_date = today.replace(day=1)
        highlight_dates = set()
        prev_d = (ref_date - timedelta(days=1)).replace(day=1)
        next_d = (ref_date + timedelta(days=32)).replace(day=1)
        prev_url = f"/journals/monthly/{prev_d.year}/{prev_d.month}"
        next_url = f"/journals/monthly/{next_d.year}/{next_d.month}"
        prev_label = prev_d.strftime("%b %Y")
        next_label = next_d.strftime("%b %Y")
    else:
        ref_date = today
        highlight_dates = set()
        prev_url = next_url = "/cal"
        prev_label = next_label = ""

    return Div(
        Div(
            A(
                Icon("chevron-left", size=14),
                Span("Calendar", cls="text-[13px]"),
                href="/cal",
                cls=(
                    "flex items-center gap-1 text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            cls="px-4 py-3 border-b border-border",
        ),
        Div(
            _mini_month_calendar(ref_date, highlight_dates),
            cls="flex-1 py-2",
        ),
        Div(
            A(
                Icon("chevron-left", size=13),
                Span(prev_label, cls="text-[11px]"),
                href=prev_url,
                cls=(
                    "flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            A(
                Span(next_label, cls="text-[11px]"),
                Icon("chevron-right", size=13),
                href=next_url,
                cls=(
                    "flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            cls="flex items-center justify-between px-3 py-3 border-t border-border",
        ),
        cls="w-[220px] flex-shrink-0 border-r border-border bg-slate-50 flex flex-col",
    )


def _mini_month_calendar(ref_date: datetime.date, highlight_dates: "set[datetime.date]") -> Any:
    import calendar as _cal
    from datetime import date

    today = date.today()
    year, month = ref_date.year, ref_date.month
    month_name = ref_date.strftime("%B %Y")
    dow_headers = ["M", "T", "W", "T", "F", "S", "S"]
    weeks = _cal.monthcalendar(year, month)

    def _day_cell(day_num: int) -> Any:
        if day_num == 0:
            return Div(cls="w-7 h-7")
        d = date(year, month, day_num)
        is_hi = d in highlight_dates
        is_today = d == today
        if is_hi and is_today:
            cls = (
                "w-7 h-7 flex items-center justify-center text-[11px] rounded-full"
                " bg-foreground text-background font-bold ring-2 ring-offset-1 ring-foreground"
            )
        elif is_hi:
            cls = (
                "w-7 h-7 flex items-center justify-center text-[11px] rounded-full"
                " bg-foreground text-background font-semibold"
            )
        elif is_today:
            cls = (
                "w-7 h-7 flex items-center justify-center text-[11px] rounded-full"
                " ring-1 ring-foreground font-medium text-foreground"
            )
        else:
            cls = (
                "w-7 h-7 flex items-center justify-center text-[11px] rounded-full"
                " hover:bg-slate-200 text-foreground"
            )
        return A(str(day_num), href=f"/journals/daily/{d.isoformat()}", cls=f"{cls} no-underline")

    return Div(
        Div(
            Span(month_name, cls="text-[12px] font-semibold text-foreground"),
            cls="flex justify-center mb-3 px-1",
        ),
        Div(
            *[
                Div(h, cls="w-7 text-[10px] text-muted-foreground text-center font-medium")
                for h in dow_headers
            ],
            cls="flex gap-0.5 mb-1",
        ),
        *[Div(*[_day_cell(d) for d in week], cls="flex gap-0.5 mb-0.5") for week in weeks],
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
            "bg-slate-50 border-r border-slate-100 flex-shrink-0 overflow-hidden"
            " transition-all duration-300"
        ),
        **{":style": "{ width: sidebarOpen ? '274px' : '62px' }"},
    )


def _sb_header() -> Any:
    return Div(
        Span("Journal", cls="text-[17px] font-bold tracking-tight text-foreground"),
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
            Span("New Journal", cls="text-[14px] font-semibold text-foreground"),
            href="/journals",
            cls=(
                "w-full flex items-center gap-2 px-3 py-[10px] rounded-[10px]"
                " border border-border bg-background hover:bg-slate-50"
                " transition-colors shadow-sm no-underline"
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
            Div(name, cls="text-[13.5px] font-semibold text-foreground leading-tight"),
            Span(
                tier,
                cls=(
                    "text-[10px] font-semibold px-1.5 py-0.5 rounded-[4px]"
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
            cls="text-[12.5px] text-muted-foreground px-4 py-2 leading-snug",
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
                "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                " px-4 pt-3 pb-1"
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
                    "flex-1 min-w-0 truncate text-[13.5px] text-foreground/90 no-underline"
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
                    "flex-1 min-w-0 text-[13.5px] px-2 py-1 rounded border border-border"
                    " bg-background outline-none focus:border-foreground/40"
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
        "w-6 h-6 flex items-center justify-center rounded text-muted-foreground"
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
                    P("Journal", cls="text-[22px] font-bold text-foreground"),
                    P(
                        "Your private thinking space.",
                        cls="text-[15px] text-muted-foreground mt-1",
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
            cls=(
                "flex items-center text-[13px] text-foreground/80 cursor-pointer select-none py-0.5"
            ),
        )
        for book in shelf_books
    ]

    canon_section = (
        Div(
            P(
                "Canon shelf",
                cls="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1",
            ),
            *book_rows,
            cls="mb-3",
        )
        if book_rows
        else P(
            "No books are on the shelf yet.",
            cls="text-[12.5px] text-muted-foreground mb-3",
        )
    )

    return Details(
        Summary(
            "Sources",
            cls=(
                "text-[13px] font-medium text-muted-foreground cursor-pointer select-none"
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
                cls=("flex items-center text-[13px] text-foreground/80 cursor-pointer select-none"),
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
                        "w-full border-none outline-none bg-transparent resize-none"
                        " text-[15px] leading-[1.6] text-foreground"
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
                    " bg-background shadow-sm"
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
