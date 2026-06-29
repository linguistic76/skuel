"""Askesis chat shell — three-column full-height layout.

Three zones: conversation sidebar · message thread · composer (inline in thread).
POST /askesis/api/submit → HTMX appends (user_bubble, ai_bubble) to #thread-messages.
Alpine: { sidebarOpen } on shell root; { sourcesOpen } per AI message.
"""

from typing import Any

from fasthtml.common import Button, Div, Form, Input, P, Span, Textarea

from ui.components import Icon

# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: full chat shell
# ─────────────────────────────────────────────────────────────────────────────


def render_askesis_shell(
    username: str = "User",
    learning_path_label: str = "Learning path",
) -> Any:
    """
    Full-height 3-column chat surface for /askesis.

    Height calc(100vh - 3.5rem) aligns with the SKUEL top navbar (h-14 = 3.5rem).
    Alpine root state: { sidebarOpen: true }
    """
    return Div(
        _sidebar(username, learning_path_label),
        _center_panel(),
        cls="flex overflow-hidden bg-background",
        style="height: calc(100vh - 3.5rem);",
        **{
            "x-data": (
                "{ sidebarOpen: true, settingsOpen: false,"
                " responseMode: localStorage.getItem('askesis_mode') || 'direct' }"
            )
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: HTMX message fragments
# ─────────────────────────────────────────────────────────────────────────────


def render_user_message(text: str) -> Any:
    """Right-aligned user bubble — appended to #thread-messages via HTMX beforeend."""
    return Div(
        Div(
            text,
            cls="max-w-[80%] bg-muted rounded-[20px] px-[18px] py-3 text-[15px] leading-[1.6] text-foreground",
        ),
        cls="flex justify-end px-7 py-2",
    )


def render_assistant_message(text: str, sources: list[dict] | None = None) -> Any:
    """Left-aligned AI message with avatar, optional sources accordion, and action bar."""
    content_nodes: list[Any] = [
        Div(text, cls="text-[15px] leading-[1.75] text-foreground/80"),
    ]
    if sources:
        content_nodes.append(_sources_accordion(sources))
    content_nodes.append(_action_bar())

    return Div(
        Div(
            "A",
            cls="w-[30px] h-[30px] rounded-full bg-foreground text-background flex items-center justify-center text-sm font-bold flex-shrink-0",
        ),
        Div(*content_nodes, cls="flex-1 min-w-0"),
        cls="flex gap-4 px-7 py-4",
        **{"x-data": "{ sourcesOpen: true }"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE: sidebar
# ─────────────────────────────────────────────────────────────────────────────


def _sidebar(username: str, learning_path_label: str) -> Any:
    """Left sidebar: conversation list + controls. Width transitions 274px ↔ 62px."""
    return Div(
        # Full sidebar content (shown when open)
        Div(
            _sb_header(),
            _sb_new_chat_btn(),
            _sb_search_field(),
            _sb_history(),
            _sb_account_footer(username, learning_path_label),
            cls="flex flex-col h-full",
            **{"x-show": "sidebarOpen"},
        ),
        # Collapsed rail (shown when closed)
        Div(
            Button(
                Icon("panel-left-open", size=16),
                cls="w-8 h-8 flex items-center justify-center rounded-lg text-muted-foreground hover:bg-slate-100 hover:text-slate-600 transition-colors",
                type="button",
                aria_label="Expand sidebar",
                **{"@click": "sidebarOpen = true"},
            ),
            Button(
                Icon("square-pen", size=16, cls="text-slate-600"),
                cls="w-8 h-8 flex items-center justify-center rounded-lg border border-border hover:bg-slate-100 transition-colors",
                type="button",
                aria_label="New chat",
            ),
            Div(cls="flex-1"),
            Div(
                username[0].upper(),
                cls="w-[30px] h-[30px] rounded-full bg-foreground/10 text-foreground flex items-center justify-center text-sm font-semibold",
            ),
            cls="flex flex-col items-center gap-3 py-3 px-2 h-full",
            **{"x-show": "!sidebarOpen", "x-cloak": True},
        ),
        # Static width=274px matches sidebarOpen=true default — prevents layout flash
        style="width:274px;",
        cls="bg-slate-50 border-r border-slate-100 flex-shrink-0 overflow-hidden transition-all duration-300",
        **{":style": "{ width: sidebarOpen ? '274px' : '62px' }"},
    )


def _sb_header() -> Any:
    return Div(
        Span("Askesis", cls="text-[17px] font-bold tracking-tight text-foreground"),
        Button(
            Icon("panel-left-close", size=16),
            cls="w-8 h-8 flex items-center justify-center rounded-lg text-muted-foreground hover:bg-slate-100 hover:text-slate-600 transition-colors",
            type="button",
            aria_label="Collapse sidebar",
            **{"@click": "sidebarOpen = false"},
        ),
        cls="flex items-center justify-between px-4 py-4",
    )


def _sb_new_chat_btn() -> Any:
    return Div(
        Button(
            Icon("square-pen", size=17, cls="text-slate-600 shrink-0"),
            Span("New chat", cls="text-[14px] font-semibold text-foreground"),
            cls="w-full flex items-center gap-2 px-3 py-[10px] rounded-[10px] border border-border bg-background hover:bg-slate-50 transition-colors shadow-sm",
            type="button",
        ),
        cls="px-3 pb-3",
    )


def _sb_search_field() -> Any:
    return Div(
        Div(
            Icon("search", size=15, cls="text-muted-foreground shrink-0"),
            Input(
                type="search",
                placeholder="Search chats",
                cls="flex-1 bg-transparent border-none outline-none text-[13.5px] text-foreground placeholder:text-muted-foreground",
            ),
            cls="flex items-center gap-2 h-[38px] rounded-[9px] px-3 bg-slate-100",
        ),
        cls="px-3 pb-4",
    )


def _sb_history() -> Any:
    """Scrollable conversation history grouped by recency."""
    return Div(
        Div(
            "Today",
            cls="px-3 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider",
        ),
        Div(cls="border-t border-border mx-3 mb-1"),
        P(
            "No conversations yet. Start chatting above.",
            cls="px-4 py-3 text-[12.5px] text-muted-foreground italic",
        ),
        cls="flex-1 overflow-y-auto",
    )


def _sb_account_footer(username: str, learning_path_label: str) -> Any:
    return Div(
        _response_mode_panel(),
        Div(
            Div(
                username[0].upper(),
                cls="w-[30px] h-[30px] rounded-full bg-foreground/10 text-foreground flex items-center justify-center text-sm font-semibold shrink-0",
            ),
            Div(
                Div(
                    username,
                    cls="text-[13.5px] font-semibold text-foreground leading-tight",
                ),
                Div(
                    learning_path_label,
                    cls="text-[11.5px] text-muted-foreground leading-tight truncate",
                ),
                cls="flex-1 min-w-0",
            ),
            Button(
                Icon("settings-2", size=16, cls="text-muted-foreground"),
                cls="hover:text-foreground transition-colors",
                type="button",
                aria_label="Response mode settings",
                **{"@click": "settingsOpen = !settingsOpen"},
            ),
            cls="flex items-center gap-2 px-4 py-3 border-t border-border",
        ),
        cls="relative",
    )


def _response_mode_panel() -> Any:
    """Response mode picker — floats above the account footer row when settingsOpen."""
    modes = [
        ("direct", "Direct", "Clear, informational answers from your curriculum"),
        (
            "socratic",
            "Socratic",
            "Probes your understanding with questions, doesn't give answers",
        ),
        (
            "exploratory",
            "Exploratory",
            "Guided discovery through scaffolding and connections",
        ),
    ]
    return Div(
        Div(
            Span("Response mode", cls="text-[13px] font-semibold text-foreground"),
            Button(
                Icon("x", size=14),
                cls="text-muted-foreground hover:text-foreground transition-colors",
                type="button",
                aria_label="Close settings",
                **{"@click": "settingsOpen = false"},
            ),
            cls="flex items-center justify-between mb-2",
        ),
        *[_mode_row(v, label, desc) for v, label, desc in modes],
        cls=(
            "absolute bottom-full left-4 right-4 mb-2 z-50"
            " bg-background border border-border rounded-[10px] shadow-lg p-3"
        ),
        **{
            "x-show": "settingsOpen",
            "x-cloak": True,
            "@click.outside": "settingsOpen = false",
            "x-transition:enter": "transition ease-out duration-150",
            "x-transition:enter-start": "opacity-0 translate-y-1",
            "x-transition:enter-end": "opacity-100 translate-y-0",
        },
    )


def _mode_row(value: str, label: str, desc: str) -> Any:
    return Div(
        # Custom radio circle
        Div(
            Div(
                cls="w-2 h-2 rounded-full bg-foreground",
                **{"x-show": f"responseMode === '{value}'"},
            ),
            cls=(
                "w-4 h-4 rounded-full border border-border flex items-center"
                " justify-center shrink-0 transition-colors"
            ),
            **{":class": f"responseMode === '{value}' ? 'border-foreground' : ''"},
        ),
        Div(
            Div(label, cls="text-[13px] font-semibold text-foreground leading-tight"),
            Div(desc, cls="text-[11.5px] text-muted-foreground leading-snug"),
            cls="flex-1",
        ),
        cls=(
            "flex items-start gap-2.5 px-2.5 py-2 rounded-[8px] cursor-pointer"
            " hover:bg-muted transition-colors"
        ),
        **{
            "@click": (
                f"responseMode = '{value}';"
                f" localStorage.setItem('askesis_mode', '{value}');"
                " settingsOpen = false;"
            ),
            ":class": f"responseMode === '{value}' ? 'bg-muted' : ''",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE: center panel (thread + composer)
# ─────────────────────────────────────────────────────────────────────────────


def _center_panel() -> Any:
    return Div(
        _top_bar(),
        Div(
            Div(
                id="thread-messages",
                cls="space-y-1 py-[30px]",
            ),
            cls="flex-1 overflow-y-auto max-w-[768px] mx-auto w-full",
            id="thread-scroll",
        ),
        _composer_area(),
        cls="flex-1 flex flex-col overflow-hidden",
    )


def _top_bar() -> Any:
    return Div(
        Button(
            Span("Sonnet 4.5", cls="text-[15.5px] font-semibold text-foreground"),
            Icon("chevron-down", size=16, cls="text-muted-foreground"),
            cls="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-muted transition-colors",
            type="button",
        ),
        Div(
            _icon_ghost_btn("share", "Share"),
            _icon_ghost_btn("more-horizontal", "More options"),
            cls="flex items-center gap-1",
        ),
        cls="flex items-center justify-between px-5 flex-shrink-0 border-b border-border",
        style="height:56px;",
    )


def _composer_area() -> Any:
    return Div(
        Div(
            _composer_form(),
            P(
                "Askesis answers from your Learning Path and cites its sources. Verify anything important.",
                cls="text-center text-[11.5px] text-muted-foreground mt-2 px-4",
            ),
            cls="max-w-[768px] mx-auto w-full px-4",
        ),
        cls="flex-shrink-0 pb-4 pt-2",
    )


def _composer_form() -> Any:
    return Form(
        Input(type="hidden", name="mode", **{":value": "responseMode"}),
        Textarea(
            placeholder="Ask about your Learning Path…",
            name="message",
            rows=1,
            cls="w-full border-none outline-none bg-transparent resize-none text-[15px] leading-[1.6] text-foreground placeholder:text-muted-foreground",
            style="max-height:200px; overflow:hidden;",
            oninput="this.style.height='auto'; this.style.height=Math.min(this.scrollHeight,200)+'px'",
            required=True,
        ),
        Div(
            Div(
                _circle_btn("plus", "Attach", bordered=True),
                _kb_pill(),
                cls="flex items-center gap-2",
            ),
            Div(
                _circle_btn("mic", "Dictate"),
                _send_btn(),
                cls="flex items-center gap-2",
            ),
            cls="flex items-center justify-between mt-2",
        ),
        cls="border border-border rounded-[25px] px-[18px] pt-[9px] pb-[9px] bg-background shadow-md",
        hx_post="/askesis/api/submit",
        hx_target="#thread-messages",
        hx_swap="beforeend",
        **{
            "hx-on::after-request": (
                "this.reset();"
                " var ta=this.querySelector('textarea'); if(ta){ta.style.height='auto';}"
                " var s=document.getElementById('thread-scroll'); if(s){s.scrollTop=s.scrollHeight;}"
            ),
        },
    )


def _kb_pill() -> Any:
    return Button(
        Icon("book-open-text", size=14, cls="shrink-0 text-strength-core"),
        Span("Knowledge base", cls="text-[13px] font-semibold text-strength-core"),
        cls="flex items-center gap-1.5 px-3 py-1.5 rounded-[18px] transition-colors",
        style="background:#f4f1fc; border:1px solid #e0d9f4;",
        type="button",
    )


def _send_btn() -> Any:
    return Button(
        Icon("arrow-up", size=16, cls="text-white"),
        cls="w-[34px] h-[34px] rounded-full flex items-center justify-center bg-foreground hover:bg-foreground/80 transition-colors",
        type="submit",
        aria_label="Send message",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE: sources accordion
# ─────────────────────────────────────────────────────────────────────────────


def _sources_accordion(sources: list[dict]) -> Any:
    """Collapsible sources panel. Uses sourcesOpen from the parent AI message x-data."""
    count = len(sources)
    kb_count = sum(1 for s in sources if s.get("kind") in ("ku", "submission"))
    web_count = count - kb_count
    caption_parts: list[str] = []
    if kb_count:
        caption_parts.append(f"{kb_count} from your knowledge base")
    if web_count:
        caption_parts.append(f"{web_count} web")
    caption = " · ".join(caption_parts)

    return Div(
        Button(
            Div(
                Icon("book-open-text", size=16, cls="text-strength-core shrink-0"),
                Span("Sources", cls="text-[13px] font-semibold text-foreground"),
                Span(
                    str(count),
                    cls="text-[11px] font-mono px-2 py-0.5 rounded-[20px] bg-muted text-muted-foreground",
                ),
                cls="flex items-center gap-1.5",
            ),
            Div(
                (Span(caption, cls="text-[12px] text-muted-foreground mr-2") if caption else None),
                Div(
                    Icon(
                        "chevron-down",
                        size=16,
                        cls="text-muted-foreground transition-transform duration-200",
                    ),
                    **{":class": "sourcesOpen ? '' : '-rotate-90'"},
                ),
                cls="flex items-center",
            ),
            cls="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors",
            type="button",
            **{"@click": "sourcesOpen = !sourcesOpen"},
        ),
        Div(
            *[_source_card(i + 1, s) for i, s in enumerate(sources)],
            cls="border-t border-border",
            **{"x-show": "sourcesOpen", "x-cloak": True},
        ),
        cls="rounded-[13px] border border-border mt-5 overflow-hidden",
    )


def _source_card(n: int, source: dict) -> Any:
    kind = source.get("kind", "web")
    title = source.get("title", "Untitled")
    snippet = source.get("snippet", "")
    origin = source.get("origin", "")

    if kind == "ku":
        icon = Icon("gem", size=14, cls="text-strength-core shrink-0")
    elif kind == "submission":
        icon = Icon("file-text", size=14, cls="text-strength-strong shrink-0")
    else:
        icon = Icon("globe", size=14, cls="text-muted-foreground shrink-0")

    title_row: list[Any] = [
        icon,
        Span(title, cls="text-[13.5px] font-semibold text-foreground truncate"),
    ]
    if kind == "web" and source.get("url"):
        title_row.append(Icon("arrow-up-right", size=13, cls="text-muted-foreground shrink-0"))

    return Div(
        Div(
            str(n),
            cls="w-[21px] h-[21px] rounded-[6px] flex items-center justify-center text-[11px] font-semibold font-mono bg-muted text-muted-foreground shrink-0",
        ),
        Div(
            Div(*title_row, cls="flex items-center gap-1.5"),
            (
                P(
                    snippet,
                    cls="text-[12.5px] text-muted-foreground leading-[1.5] line-clamp-2 mt-0.5",
                )
                if snippet
                else None
            ),
            (
                Span(origin, cls="text-[11px] text-muted-foreground font-mono mt-1 block")
                if origin
                else None
            ),
        ),
        cls="flex gap-3 px-3 py-[11px] hover:bg-slate-50 transition-colors",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE: action bar + UI atoms
# ─────────────────────────────────────────────────────────────────────────────


def _action_bar() -> Any:
    return Div(
        _icon_ghost_btn("copy", "Copy"),
        _icon_ghost_btn("thumbs-up", "Good answer"),
        _icon_ghost_btn("thumbs-down", "Bad answer"),
        _icon_ghost_btn("refresh-cw", "Regenerate"),
        cls="flex items-center gap-0.5 mt-3",
    )


def _icon_ghost_btn(icon: str, label: str) -> Any:
    return Button(
        Icon(icon, size=15),
        cls="w-[30px] h-[30px] flex items-center justify-center rounded-[7px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors",
        type="button",
        aria_label=label,
    )


def _circle_btn(icon: str, label: str, bordered: bool = False) -> Any:
    border_cls = "border border-border" if bordered else ""
    return Button(
        Icon(icon, size=16),
        cls=f"w-[34px] h-[34px] rounded-full flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors {border_cls}".strip(),
        type="button",
        aria_label=label,
    )
