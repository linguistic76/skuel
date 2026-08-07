"""Explore reading plan — reading-column view for /explore.

Implements the reading-first design from data/handoff/explore/explore.html.
Renders entirely server-side; Alpine owns only:
  - greeting text (time-of-day)
  - "why am I ready?" disclosure toggle
  - save button optimistic state
  - keyboard shortcuts (r / w / s / /)

The Alpine factory lives in static/js/explore-reading.js.
The x-data expression carries the minimal seed Alpine needs; all visual
content comes from the server-rendered plan dict.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H2,
    H3,
    A,
    Article,
    Button,
    Div,
    Header,
    Li,
    P,
    Section,
    Span,
    Ul,
)

from ui.components import Icon
from ui.patterns.keyboard_hints import keyboard_hint, keyboard_hints_bar

if TYPE_CHECKING:
    from fasthtml.common import FT

_COLUMN_CLS = "mx-auto max-w-[720px] px-4 sm:px-6 pt-7 sm:pt-10 pb-28"


# ---------------------------------------------------------------------------
# Capability tray metadata
# ---------------------------------------------------------------------------

_CAP_STYLES: dict[str, tuple[str, str, str, str]] = {
    # kind → (lucide-icon, label, icon-bg-cls, label-color-cls)
    "practice": (
        "activity",
        "Practice",
        "bg-green-50 text-green-700",
        "bg-green-50 text-green-700",
    ),
    "apply": ("target", "Apply", "bg-blue-50 text-blue-700", "bg-blue-50 text-blue-700"),
    "assessment": (
        "clipboard-check",
        "Assessment",
        "bg-amber-50 text-amber-700",
        "bg-amber-50 text-amber-700",
    ),
    "reflection": (
        "pen-line",
        "Reflection",
        "bg-violet-50 text-violet-700",
        "bg-violet-50 text-violet-700",
    ),
    "journal": (
        "book-open",
        "Journal",
        "bg-violet-50 text-violet-700",
        "bg-violet-50 text-violet-700",
    ),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ExploreReadingView(plan: dict[str, Any]) -> "FT":
    """Reading-column layout for /explore.

    plan: dict returned by ExploreOrchestrator.get_reading_plan().
    """
    seed = _build_alpine_seed(plan)
    # Inline in x-data, never a window global set by a sibling <script>: htmx
    # defers inline-script evaluation to the settle phase, but Alpine
    # initializes the swapped tree first — the global would be undefined.
    # json.dumps default ensure_ascii keeps the payload ASCII-only (covers
    # U+2028/29), and FastHTML's attribute escaping covers the HTML context.
    seed_json = json.dumps(seed, default=str)

    return Div(
        _greeting_header(plan),
        _hero_article(plan),
        _thread_rail(plan),
        _in_progress_section(plan),
        _path_step_section(plan),
        _related_section(plan),
        _library_section(plan),
        _keyboard_hints(),
        cls=_COLUMN_CLS,
        **{
            "x-data": f"exploreReading({seed_json})",
            "@keydown.window": "onKey($event)",
        },
    )


# ---------------------------------------------------------------------------
# Alpine seed
# ---------------------------------------------------------------------------


def _build_alpine_seed(plan: dict[str, Any]) -> dict[str, Any]:
    """Build the minimal SEED dict Alpine needs; everything else is server-rendered."""
    featured = plan.get("featured", {})
    last_completed = plan.get("last_completed", {})
    return {
        "reader_name": plan.get("reader_name", "there"),
        "date_label": plan.get("date_label", ""),
        "featured_uid": featured.get("uid", ""),
        "why": featured.get("why", []),
        "last_completed_title": last_completed.get("title", ""),
        "saved_uids": plan.get("pinned_uids", []),
    }


# ---------------------------------------------------------------------------
# Greeting header
# ---------------------------------------------------------------------------


def _greeting_header(plan: dict[str, Any]) -> "FT":
    last_completed = plan.get("last_completed", {})
    last_title = last_completed.get("title", "")
    date_label = plan.get("date_label", "")

    return Header(
        Div(
            date_label,
            cls="font-mono text-[11px] font-medium tracking-widest uppercase text-muted-foreground",
        ),
        H2(
            Span(**{"x-text": "greeting()"}),
            ", ",
            Span(**{"x-text": "seed.reader_name"}),
            ".",
            cls="mt-2 text-[clamp(24px,5vw,30px)] font-bold tracking-tight leading-[1.1]",
        ),
        P(
            "You finished ",
            Span(last_title, cls="text-foreground font-medium"),
            " yesterday. Here's the idea you're ready to hold next.",
            cls="mt-2 text-[clamp(14px,2.6vw,15.5px)] text-muted-foreground leading-relaxed max-w-[46ch]",
        )
        if last_title
        else Div(),
        cls="mb-7 sm:mb-8",
    )


# ---------------------------------------------------------------------------
# Hero article — the featured KU
# ---------------------------------------------------------------------------


def _hero_article(plan: dict[str, Any]) -> "FT":
    featured = plan.get("featured", {})
    uid = featured.get("uid", "")
    if not uid:
        return Div()
    title = featured.get("title", "")
    thread = featured.get("thread", "")
    excerpt = featured.get("excerpt", "")
    minutes = featured.get("reading_minutes", 0)

    return Article(
        # "Ready now" · thread label
        Div(
            Span(
                Span(cls="w-[7px] h-[7px] rounded-full bg-green-500 flex-none"),
                featured.get("status_label", "Ready now"),
                cls="inline-flex items-center gap-1.5 font-mono text-[10.5px] font-medium tracking-widest uppercase text-green-700",
            ),
            Span("·", cls="text-[11px] text-muted-foreground/70"),
            Span(
                "an idea on ",
                Span(thread, cls="text-foreground font-medium"),
                cls="text-[12px] text-muted-foreground",
            ),
            cls="flex flex-wrap items-center gap-2.5 mb-4",
        ),
        # Title
        H2(
            title,
            id="featured-title",
            cls="text-[clamp(28px,6vw,40px)] font-bold tracking-tight leading-[1.04]",
        ),
        # Excerpt
        P(
            excerpt,
            cls="mt-3.5 text-[clamp(16px,3vw,19px)] leading-relaxed text-foreground/90 max-w-[52ch]",
        ),
        # "Why now" panel
        _why_now_panel(featured) if featured.get("why_now") else Div(),
        # CTA row
        _hero_actions(uid, minutes),
        cls="border border-border rounded-xl p-5 sm:p-7 shadow-xs mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "featured-title"},
    )


def _why_now_panel(featured: dict[str, Any]) -> "FT":
    why_now_text = featured.get("why_now", "")
    why_evidence = featured.get("why", [])

    evidence_items = [_evidence_item(row) for row in why_evidence]

    return Div(
        Div(
            Icon("compass", cls="w-4 h-4 text-primary flex-none mt-0.5"),
            P(
                Span("Why now — ", cls="font-semibold text-foreground"),
                why_now_text,
                cls="text-[13px] leading-relaxed text-foreground/80",
            ),
            cls="flex gap-3 items-start",
        ),
        Div(
            Button(
                "Why am I ready?",
                Span(
                    Icon("chevron-down"),
                    cls="w-3.5 h-3.5 inline-flex items-center transition-transform",
                    **{":class": "{'rotate-180': whyOpen}"},
                ),
                type="button",
                cls="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-primary",
                **{
                    "@click": "whyOpen = !whyOpen",
                    ":aria-expanded": "whyOpen.toString()",
                    "aria-controls": "why-evidence",
                },
            ),
            Ul(
                *evidence_items,
                id="why-evidence",
                cls="mt-3 space-y-2.5",
                role="list",
                **{"x-show": "whyOpen", "x-cloak": True},
            )
            if evidence_items
            else Div(),
            cls="mt-3 pt-3 border-t border-border/40",
        ),
        cls="mt-5 p-4 rounded-lg bg-primary/5",
    )


def _evidence_item(row: dict[str, Any]) -> "FT":
    met = row.get("met")
    text = row.get("text", "")

    if met is True:
        indicator: FT = Icon("check", cls="w-[15px] h-[15px] text-green-600 flex-none mt-0.5")
        text_cls = "text-[12.5px] leading-snug text-foreground/80"
    else:
        indicator = Span(
            Span(cls="w-[7px] h-[7px] rounded-full border-[1.5px] border-muted-foreground"),
            cls="flex-none mt-0.5 w-[15px] h-[15px] flex items-center justify-center",
        )
        text_cls = "text-[12.5px] leading-snug text-muted-foreground"

    return Li(
        indicator,
        Span(text, cls=text_cls),
        cls="flex gap-2.5 items-start",
    )


def _hero_actions(uid: str, minutes: int) -> "FT":
    return Div(
        A(
            Icon("book-open", cls="w-[17px] h-[17px]"),
            " Read",
            href=f"/explore/read/{uid}",
            cls=(
                "inline-flex items-center gap-2.5 bg-foreground text-background "
                "rounded-lg px-5 py-3 text-[14.5px] font-semibold "
                "hover:opacity-90 focus:outline-hidden focus-visible:ring-2"
            ),
        ),
        Span(
            f"{minutes} min read" if minutes else "",
            cls="font-mono text-[12.5px] text-muted-foreground",
        ),
        Button(
            Icon("bookmark", cls="w-[17px] h-[17px]"),
            type="button",
            cls=(
                "ml-auto w-[38px] h-[38px] border border-border bg-card rounded-lg "
                "flex items-center justify-center hover:bg-muted "
                "focus:outline-hidden focus-visible:ring-2"
            ),
            **{
                "@click": f"toggleSave('{uid}')",
                ":aria-label": f"isSaved('{uid}') ? 'Saved' : 'Save for later'",
                ":class": f"isSaved('{uid}') ? 'text-primary fill-current' : 'text-muted-foreground'",
            },
        ),
        cls="flex flex-wrap items-center gap-3.5 mt-5",
    )


# ---------------------------------------------------------------------------
# Thread rail — "Or follow your own thread"
# ---------------------------------------------------------------------------


def _thread_rail(plan: dict[str, Any]) -> "FT":
    also_ready = plan.get("also_ready", [])
    if not also_ready:
        return Div()

    cards = [_thread_card(ku) for ku in also_ready]

    return Section(
        Div(
            Span(
                "Or follow your own thread",
                id="thread-heading",
                cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground",
            ),
            Span(
                "you're ready for these too — pick what pulls you",
                cls="text-[12px] text-muted-foreground/80 hidden sm:inline",
            ),
            cls="flex items-baseline justify-between gap-3 mb-3.5",
        ),
        Div(
            *cards,
            cls=(
                "flex gap-3 overflow-x-auto -mx-4 px-4 pb-1.5 "
                "scrollbar-none [&::-webkit-scrollbar]:hidden"
            ),
            role="list",
        ),
        cls="mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "thread-heading"},
    )


def _thread_card(ku: dict[str, Any]) -> "FT":
    thread_color = ku.get("thread_color", "currentColor")
    minutes = ku.get("reading_minutes", 0)

    return A(
        Span(
            Span(cls="w-[7px] h-[7px] rounded-full", style=f"background:{thread_color}"),
            Span(
                ku.get("thread", ""),
                cls="font-mono text-[10px] tracking-[0.06em] uppercase text-muted-foreground",
            ),
            cls="flex items-center gap-2",
        ),
        Span(ku.get("title", ""), cls="text-[15px] font-semibold text-foreground"),
        Span(ku.get("excerpt", ""), cls="text-[12.5px] text-muted-foreground leading-snug"),
        Span(
            Span(cls="w-[6px] h-[6px] rounded-full bg-green-500"),
            Span(f"ready · {minutes} min", cls="font-mono text-[11px] text-muted-foreground"),
            cls="flex items-center gap-2 mt-auto",
        ),
        href=f"/explore/read/{ku.get('uid', '')}",
        role="listitem",
        cls=(
            "flex-none w-[min(74vw,228px)] min-h-[150px] flex flex-col gap-2.5 "
            "p-4 border border-border rounded-xl bg-card "
            "hover:border-muted-foreground/40 transition-colors "
            "focus:outline-hidden focus-visible:ring-2"
        ),
    )


# ---------------------------------------------------------------------------
# In-progress section
# ---------------------------------------------------------------------------


def _in_progress_section(plan: dict[str, Any]) -> "FT":
    in_progress = plan.get("in_progress", [])
    if not in_progress:
        return Div()

    rows = [_in_progress_row(r) for r in in_progress]

    return Section(
        Div(
            "Pick up where you left off",
            id="continue-heading",
            cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground mb-3",
        ),
        Div(*rows, cls="flex flex-col gap-2"),
        cls="mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "continue-heading"},
    )


def _in_progress_row(r: dict[str, Any]) -> "FT":
    progress = r.get("progress", 0)
    minutes_left = r.get("minutes_left", 0)
    width_pct = f"{round(progress * 100)}%"

    return A(
        Span(
            Icon("book-marked", cls="w-[18px] h-[18px]"),
            cls="flex-none w-[38px] h-[38px] rounded-lg flex items-center justify-center bg-violet-50 text-violet-700",
        ),
        Span(
            Span(r.get("title", ""), cls="block text-[14.5px] font-semibold text-foreground"),
            Span(
                Span(
                    Span(cls="block h-full rounded-full bg-primary", style=f"width:{width_pct}"),
                    cls="flex-1 max-w-[200px] h-1 bg-muted rounded-full overflow-hidden",
                ),
                Span(f"{minutes_left} min left", cls="font-mono text-[11px] text-muted-foreground"),
                cls="flex items-center gap-2.5 mt-2",
            ),
            cls="flex-1 min-w-0",
        ),
        Icon("chevron-right", cls="w-[18px] h-[18px] text-muted-foreground/70 flex-none"),
        href=f"/explore/read/{r.get('uid', '')}",
        cls=(
            "w-full flex items-center gap-3.5 px-4 py-3.5 border border-border "
            "rounded-xl bg-card hover:border-muted-foreground/40 transition-colors "
            "focus:outline-hidden focus-visible:ring-2"
        ),
    )


# ---------------------------------------------------------------------------
# Path step section
# ---------------------------------------------------------------------------


def _path_step_section(plan: dict[str, Any]) -> "FT":
    ps = plan.get("active_path_step")
    if not ps:
        return Div()

    featured_thread = plan.get("featured", {}).get("thread", "")

    return Section(
        Div(
            Span(
                "The path step you're inside",
                cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground",
            ),
            Span(featured_thread, cls="text-[12px] text-muted-foreground/80"),
            cls="flex items-baseline justify-between gap-3 mb-3.5",
        ),
        Div(
            _ps_header(ps),
            _ps_ku_list(ps),
            _ps_capabilities(ps),
            cls="border border-border rounded-xl overflow-hidden shadow-xs",
        ),
        cls="mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "ps-title"},
    )


def _ps_header(ps: dict[str, Any]) -> "FT":
    units_read = ps.get("units_read", 0)
    units_total = ps.get("units_total", 0)
    progress = ps.get("progress", 0.0)
    width_pct = f"{round(progress * 100)}%"

    return Div(
        Span(
            Icon("layers", cls="w-3 h-3"),
            " Path step",
            cls="inline-flex items-center gap-1.5 font-mono text-[10px] font-medium tracking-widest uppercase text-primary rounded-md px-2.5 py-1 bg-primary/8",
        ),
        H3(
            ps.get("title", ""),
            id="ps-title",
            cls="mt-3 text-[clamp(18px,3.6vw,21px)] font-bold tracking-tight leading-snug",
        ),
        P(
            ps.get("summary", ""),
            cls="mt-1.5 text-[13.5px] text-muted-foreground leading-relaxed max-w-[50ch]",
        ),
        Div(
            Span(
                Span(cls="block h-full rounded-full bg-primary", style=f"width:{width_pct}"),
                cls="flex-1 max-w-[280px] h-[5px] bg-muted rounded-full overflow-hidden",
            ),
            Span(
                f"{units_read} / {units_total} ideas read",
                cls="font-mono text-[11px] text-muted-foreground whitespace-nowrap",
            ),
            cls="flex items-center gap-3 mt-4",
        ),
        cls="p-5 sm:p-[22px] border-b border-muted",
    )


def _ps_ku_list(ps: dict[str, Any]) -> "FT":
    kus = ps.get("knowledge_units", [])
    units_total = ps.get("units_total", len(kus))
    rows = [_ps_ku_row(ku) for ku in kus]

    return Div(
        Div(
            f"Built from {units_total} ideas",
            cls="font-mono text-[10px] font-medium tracking-widest uppercase text-muted-foreground/70 mb-3",
        ),
        Div(*rows, cls="flex flex-col gap-0.5"),
        cls="p-4 sm:p-[19px]",
    )


def _ps_ku_row(ku: dict[str, Any]) -> "FT":
    status = ku.get("status", "upcoming")
    uid = ku.get("uid", "")
    title = ku.get("title", "")
    excerpt = ku.get("excerpt")
    minutes = ku.get("reading_minutes", 0)

    if status == "read":
        node: FT = Span(
            Icon("check", cls="w-3 h-3"),
            cls="flex-none w-[22px] h-[22px] rounded-full flex items-center justify-center bg-muted border border-border text-muted-foreground",
        )
        title_cls = "text-[14px] text-muted-foreground line-through"
        row_cls = "py-2 px-0 hover:bg-muted/50"
        meta: FT = Span(
            f"read · {minutes} min" if minutes else "read",
            cls="font-mono text-[11px] text-muted-foreground/50 whitespace-nowrap",
        )
    elif status == "current":
        node = Span(
            Span(cls="w-[7px] h-[7px] rounded-full bg-primary"),
            cls="flex-none w-[22px] h-[22px] rounded-full flex items-center justify-center bg-white border-2 border-primary",
        )
        title_cls = "text-[14px] font-semibold text-foreground"
        row_cls = "px-3 py-2.5 border rounded-lg bg-primary/5 border-primary/20"
        meta = Span(
            "reading now",
            cls="font-mono text-[10.5px] font-medium tracking-wider uppercase text-primary whitespace-nowrap",
        )
    else:  # upcoming
        node = Span(
            cls="flex-none w-[22px] h-[22px] rounded-full bg-white",
            style="border: 1.5px dashed hsl(214 20% 78%)",
        )
        title_cls = "text-[14px] font-medium text-foreground/90"
        row_cls = "py-2 px-0 hover:bg-muted/50"
        meta = Span(
            f"{minutes} min" if minutes else "",
            cls="font-mono text-[11px] text-muted-foreground whitespace-nowrap",
        )

    return A(
        node,
        Span(
            Span(title, cls=title_cls),
            Span(excerpt, cls="block text-[12.5px] text-muted-foreground mt-0.5")
            if excerpt
            else Div(),
            cls="flex-1 min-w-0",
        ),
        meta,
        href=f"/explore/read/{uid}",
        cls=f"flex items-start gap-3 rounded-lg transition-colors focus:outline-hidden focus-visible:ring-2 {row_cls}",
    )


def _ps_capabilities(ps: dict[str, Any]) -> "FT":
    capabilities = ps.get("capabilities", [])
    if not capabilities:
        return Div()

    ps_uid = ps.get("uid", "")
    cap_buttons = [_ps_capability_button(cap, ps_uid) for cap in capabilities]

    return Div(
        Div(
            Span(
                "What this step adds",
                cls="font-mono text-[10px] font-medium tracking-widest uppercase text-muted-foreground/70",
            ),
            Span("varies by step", cls="text-[11px] text-muted-foreground/60"),
            cls="flex items-baseline justify-between gap-2.5 mb-3",
        ),
        Div(*cap_buttons, cls="flex flex-col gap-2"),
        P(
            "Another step might add an assessment, a journal, or nothing at all — the tray belongs to the step.",
            cls="mt-3 text-[11.5px] text-muted-foreground/80 leading-snug",
        ),
        cls="p-4 sm:p-[19px] bg-muted/40 border-t border-muted",
    )


def _ps_capability_button(cap: dict[str, Any], ps_uid: str) -> "FT":
    kind = cap.get("kind", "practice")
    locked = cap.get("locked", False)
    icon_name, label, icon_bg_cls, label_cls = _CAP_STYLES.get(
        kind,
        (
            "circle",
            kind.title(),
            "bg-muted text-muted-foreground",
            "bg-muted text-muted-foreground",
        ),
    )

    base_cls = (
        "text-left flex items-start gap-3 p-3 bg-card border border-muted "
        "rounded-xl focus:outline-hidden focus-visible:ring-2"
    )
    locked_cls = "cursor-not-allowed opacity-60" if locked else "hover:border-muted-foreground/30"

    htmx_attrs: dict[str, Any] = {}
    if not locked:
        htmx_attrs["hx-post"] = f"/explore/path-steps/{ps_uid}/capabilities/{kind}/start"
        htmx_attrs["hx-swap"] = "none"

    return Button(
        Span(
            Icon(icon_name, cls="w-4 h-4"),
            cls=f"flex-none w-[34px] h-[34px] rounded-lg flex items-center justify-center {icon_bg_cls}",
        ),
        Span(
            Span(
                Span(
                    cap.get("title", ""),
                    cls=f"text-[14px] font-semibold {'text-foreground/80' if locked else 'text-foreground'}",
                ),
                Span(
                    label,
                    cls=f"font-mono text-[9.5px] font-medium tracking-[0.06em] uppercase rounded-sm px-1.5 py-0.5 {label_cls}",
                ),
                Span(
                    Icon("lock", cls="w-2.5 h-2.5"),
                    " locked",
                    cls="inline-flex items-center gap-1 font-mono text-[9.5px] text-muted-foreground bg-muted rounded-sm px-1.5 py-0.5",
                )
                if locked
                else Div(),
                cls="flex items-center gap-2 flex-wrap",
            ),
            Span(
                cap.get("summary", ""),
                cls="block text-[12.5px] mt-0.5 leading-snug text-muted-foreground",
            ),
            cls="flex-1 min-w-0",
        ),
        type="button",
        disabled=locked or None,
        cls=f"{base_cls} {locked_cls}",
        **htmx_attrs,
    )


# ---------------------------------------------------------------------------
# "Because you read X" lateral section
# ---------------------------------------------------------------------------


def _related_section(plan: dict[str, Any]) -> "FT":
    related = plan.get("related", [])
    last_title = plan.get("last_completed", {}).get("title", "")
    if not related:
        return Div()

    rows = [_related_row(k) for k in related]
    heading = f"Because you read {last_title}" if last_title else "Related ideas"

    return Section(
        Div(
            heading,
            id="related-heading",
            cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground mb-3.5",
        ),
        Div(*rows, cls="flex flex-col gap-0.5"),
        cls="mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "related-heading"},
    )


def _related_row(k: dict[str, Any]) -> "FT":
    kind = k.get("kind", "")
    minutes = k.get("reading_minutes", 0)

    return A(
        Span(
            Span(
                Span(k.get("title", ""), cls="text-[14.5px] font-semibold text-foreground"),
                Span(
                    kind,
                    cls="font-mono text-[10px] text-muted-foreground bg-muted rounded-sm px-1.5 py-0.5",
                )
                if kind
                else Div(),
                cls="flex items-center gap-2.5",
            ),
            Span(
                k.get("excerpt", ""),
                cls="block text-[13px] text-muted-foreground mt-1 leading-snug",
            ),
            cls="flex-1 min-w-0",
        ),
        Span(
            f"{minutes} min",
            cls="font-mono text-[11px] text-muted-foreground whitespace-nowrap pt-0.5",
        ),
        href=f"/explore/read/{k.get('uid', '')}",
        cls=(
            "w-full flex items-start gap-3.5 p-3.5 rounded-xl border border-transparent "
            "hover:bg-muted/50 transition-colors focus:outline-hidden focus-visible:ring-2"
        ),
    )


# ---------------------------------------------------------------------------
# Library browse section
# ---------------------------------------------------------------------------


def _library_section(plan: dict[str, Any]) -> "FT":
    library = plan.get("library", {})
    total = library.get("total", 0)
    tags = library.get("tags", [])
    total_text = f"{total} ideas" if total else "many ideas"

    tag_links = [
        A(
            tag,
            href=f"/explore/library?tag={tag.lstrip('#')}",
            cls="text-[12px] text-muted-foreground bg-card border border-border rounded-full px-2.5 py-1 hover:bg-muted",
        )
        for tag in tags
    ]

    return Section(
        Div(
            "Looking for something specific?",
            id="browse-heading",
            cls="text-[14.5px] font-semibold text-foreground",
        ),
        P(
            f"The full library is {total_text}. Most days you won't need it — but it's here when you do.",
            cls="mt-1 text-[13px] text-muted-foreground leading-relaxed",
        ),
        A(
            Icon("search", cls="w-4 h-4 text-muted-foreground/70"),
            Span(
                "Search ideas, paths, and tags…",
                cls="flex-1 text-[13.5px] text-muted-foreground/70",
            ),
            href="/explore/library",
            cls=(
                "mt-3.5 flex items-center gap-2.5 px-3.5 py-3 bg-card "
                "border border-border rounded-lg hover:border-muted-foreground/40 transition-colors"
            ),
        ),
        Div(
            *tag_links,
            A(
                "Browse all ",
                Icon("arrow-right", cls="w-3.5 h-3.5"),
                href="/explore/library",
                cls="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-primary px-1 py-1",
            ),
            cls="flex flex-wrap items-center gap-2 mt-3.5",
        ),
        A(
            Icon("share-2", cls="w-3.5 h-3.5"),
            " View learning graph",
            href="/explore/graph",
            cls=(
                "mt-3 inline-flex items-center gap-1.5 text-[12px] "
                "text-muted-foreground hover:text-foreground transition-colors"
            ),
        ),
        cls="rounded-xl border border-muted bg-muted/40 p-5 sm:p-6 mb-7 sm:mb-9",
        role="region",
        **{"aria-labelledby": "browse-heading"},
    )


# ---------------------------------------------------------------------------
# Keyboard hints footer
# ---------------------------------------------------------------------------


def _keyboard_hints() -> "FT":
    return keyboard_hints_bar(
        keyboard_hint("read", "r"),
        keyboard_hint("why am I ready", "w"),
        keyboard_hint("save", "s"),
        keyboard_hint("search library", "/"),
    )


__all__ = ["ExploreReadingView"]
