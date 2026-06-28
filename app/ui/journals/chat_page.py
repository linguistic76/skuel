"""Journal chat page — dedicated session view at /journals/{entry_uid}.

Two-column layout: collapsible sidebar (session history, search, identity)
and a main workspace area where HTMX stage/follow-up fragments are swapped.
Mirrors the Askesis shell from ui/askesis/chat.py.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Button, Div, Input, P, Span
from monsterui.franken import UkIcon

if TYPE_CHECKING:
    from core.models.user.user import User
    from core.models.user_entry.user_entry import UserEntry


def JournalChatPage(
    entry: "UserEntry",
    recent_entries: "list[UserEntry]",
    initial_workspace: Any,
    user: "User",
) -> Any:
    """Full-height two-column journal session shell."""
    return Div(
        _journal_sidebar(recent_entries, entry.uid, user),
        Div(
            initial_workspace,
            cls="flex-1 overflow-y-auto",
        ),
        cls="flex overflow-hidden bg-background",
        style="height: calc(100vh - 3.5rem);",
        **{
            "x-data": (
                "{ sidebarOpen: localStorage.getItem('journal-sidebar') !== 'false',"
                " search: '' }"
            )
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────


def _journal_sidebar(
    recent_entries: "list[UserEntry]",
    active_uid: str,
    user: "User",
) -> Any:
    return Div(
        # Full sidebar (shown when open)
        Div(
            _sb_header(),
            _sb_new_journal_btn(),
            _sb_search_field(),
            _sb_session_list(recent_entries, active_uid),
            _sb_identity_footer(user),
            cls="flex flex-col h-full",
            **{"x-show": "sidebarOpen"},
        ),
        # Collapsed rail (shown when closed)
        Div(
            Button(
                UkIcon("panel-left-open", height=16, width=16),
                cls=(
                    "w-8 h-8 flex items-center justify-center rounded-lg"
                    " text-muted-foreground hover:bg-slate-100 hover:text-slate-600"
                    " transition-colors"
                ),
                type="button",
                aria_label="Expand sidebar",
                **{
                    "@click": (
                        "sidebarOpen = true;"
                        " localStorage.setItem('journal-sidebar', 'true')"
                    )
                },
            ),
            Button(
                UkIcon("square-pen", height=16, width=16, cls="text-slate-600"),
                cls=(
                    "w-8 h-8 flex items-center justify-center rounded-lg"
                    " border border-border hover:bg-slate-100 transition-colors"
                ),
                type="button",
                aria_label="New Journal",
                **{"@click": "window.location.href='/journals'"},
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
            UkIcon("panel-left-close", height=16, width=16),
            cls=(
                "w-8 h-8 flex items-center justify-center rounded-lg"
                " text-muted-foreground hover:bg-slate-100 hover:text-slate-600"
                " transition-colors"
            ),
            type="button",
            aria_label="Collapse sidebar",
            **{
                "@click": (
                    "sidebarOpen = false;"
                    " localStorage.setItem('journal-sidebar', 'false')"
                )
            },
        ),
        cls="flex items-center justify-between px-4 py-4",
    )


def _sb_new_journal_btn() -> Any:
    return Div(
        A(
            UkIcon("square-pen", height=17, width=17, cls="text-slate-600 shrink-0"),
            Span("New Journal", cls="text-[14px] font-semibold text-foreground"),
            href="/journals",
            cls=(
                "w-full flex items-center gap-2 px-3 py-[10px] rounded-[10px]"
                " border border-border bg-background hover:bg-slate-50"
                " transition-colors shadow-sm no-underline"
            ),
        ),
        cls="px-3 pb-3",
    )


def _sb_search_field() -> Any:
    return Div(
        Div(
            UkIcon("search", height=15, width=15, cls="text-muted-foreground shrink-0"),
            Input(
                type="search",
                placeholder="Search sessions",
                cls=(
                    "flex-1 bg-transparent border-none outline-none"
                    " text-[13.5px] text-foreground placeholder:text-muted-foreground"
                ),
                **{"x-model": "search"},
            ),
            cls="flex items-center gap-2 h-[38px] rounded-[9px] px-3 bg-slate-100",
        ),
        cls="px-3 pb-4",
    )


def _sb_session_list(entries: "list[UserEntry]", active_uid: str) -> Any:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    groups: dict[str, list[UserEntry]] = {"TODAY": [], "YESTERDAY": [], "EARLIER": []}
    for e in entries:
        created = getattr(e, "created_at", None)
        if created is not None:
            entry_date = created.date() if hasattr(created, "date") else today
        else:
            entry_date = today

        if entry_date == today:
            groups["TODAY"].append(e)
        elif entry_date == yesterday:
            groups["YESTERDAY"].append(e)
        else:
            groups["EARLIER"].append(e)

    sections: list[Any] = []
    for label, group_entries in groups.items():
        if not group_entries:
            continue
        sections.append(
            Div(
                label,
                cls=(
                    "px-3 py-1 text-[11px] font-semibold text-muted-foreground"
                    " uppercase tracking-wider"
                ),
            )
        )
        sections.append(Div(cls="border-t border-border mx-3 mb-1"))
        for e in group_entries:
            sections.append(_session_item(e, active=e.uid == active_uid))

    if not sections:
        sections.append(
            P(
                "No sessions yet.",
                cls="px-4 py-3 text-[12.5px] text-muted-foreground italic",
            )
        )

    return Div(
        *sections,
        cls="flex-1 overflow-y-auto",
    )


def _session_item(entry: "UserEntry", active: bool) -> Any:
    title = (entry.title or "Untitled")[:40]
    active_cls = "bg-slate-200/70" if active else "hover:bg-slate-100"
    return A(
        Span(title, cls="text-[13.5px] text-foreground truncate flex-1"),
        href=f"/journals/{entry.uid}",
        cls=(
            f"flex items-center gap-2 px-3 py-[9px] mx-1 rounded-[8px]"
            f" transition-colors cursor-pointer no-underline {active_cls}"
        ),
        **{
            "x-show": (
                "search === '' || "
                f"{_js_str(title)}.toLowerCase().includes(search.toLowerCase())"
            )
        },
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
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _js_str(s: str) -> str:
    """Produce a JS string literal safe to embed in an Alpine x-show expression."""
    escaped = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
