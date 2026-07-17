"""Today page — FastHTML translation of ``handoff/today/today.html``.

Structural 1:1 port. The Alpine factory ``today()`` lives in
``static/js/today.js``; this module emits the DOM tree it binds to plus
the ``window.SEED`` block seeded from the server-built
``TodayPageContext``.

Wiring: route handler (Phase 4) wraps this in
``BasePage(layout=STANDARD, active_page="today",
extra_css=["/static/css/today.css"])``.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Aside,
    Button,
    Div,
    Header,
    Kbd,
    Li,
    Main,
    NotStr,
    P,
    Script,
    Section,
    Span,
    Template,
    Ul,
)

from ui.components import Icon
from ui.primitives import section_label, view_switcher

if TYPE_CHECKING:
    from fasthtml.common import FT

    from ui.page_contexts import TodayPageContext


_CONTAINER_CLS = "mx-auto max-w-[1280px] py-8 pb-24"

# Force a full browser navigation on the Daily-note link — /journals/daily/*
# answers with a 302 redirect that HTMX boost would otherwise swap in place.
_NO_BOOST = {"hx-boost": "false"}


def TodayPage(ctx: TodayPageContext) -> FT:
    """Render the complete Today surface from a ``TodayPageContext``.

    The context is serialized into ``window.SEED`` so the Alpine factory
    (``static/js/today.js``) can read it without a second HTTP round-trip.
    """
    seed_json = json.dumps(dict(ctx), default=str)

    # The lens switcher + Daily-note link are static server HTML (not Alpine-seeded)
    # so their active/href state is correct without JS. date.today() is the server
    # clock — the same source the orchestrator uses to build the context.
    today = date.today()

    return Main(
        _seed_script(seed_json),
        _header(today),
        _two_column(),
        _flash_toast(),
        _drawer(),
        # Synchronous (no defer) so this registers the alpine:init listener
        # BEFORE Alpine's deferred bundle fires that event and scans the DOM.
        # With defer on both, Alpine runs first and our Alpine.data('today', ...)
        # registration misses the initial scan.
        Script(src="/static/js/today.js"),
        cls=_CONTAINER_CLS,
        **{
            "x-data": "today",
            "@keydown.window": "onKey($event)",
        },
    )


# ============================================================================
# Seed data
# ============================================================================


def _seed_script(seed_json: str) -> FT:
    # NotStr so FastHTML doesn't escape the JSON braces/quotes — but then
    # we owe the JS-context escape ourselves: `</`, `<!`, U+2028, U+2029
    # can break out of a <script> tag or act as JS line terminators
    # inside a string literal. json.dumps doesn't handle this; the five
    # replacements below do, without affecting JSON validity.
    safe = (
        seed_json.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return Script(NotStr(f"window.SEED = {safe};"))


# ============================================================================
# Header — date, title, subtitle, stats row
# ============================================================================


def _header(today: date) -> FT:
    return Header(
        Div(
            Div(
                cls="text-[11px] font-bold uppercase tracking-[0.09em] text-muted-foreground",
                **{"x-text": "seed.date_label"},
            ),
            H1("Today", cls="mt-1.5 text-[44px] font-bold leading-none tracking-tight"),
            P(
                cls="mt-2.5 text-sm text-muted-foreground max-w-lg leading-relaxed",
                **{
                    "x-text": (
                        "allEmpty "
                        "? 'Your ribbons are clear.' "
                        ": 'One ribbon per LifePath. Drag any item right to defer. "
                        "Press j/k to move.'"
                    ),
                },
            ),
            cls="min-w-[280px] flex-1",
        ),
        # Right column: the Today | Week | Month lens switcher + Daily-note link
        # sit top-right (Today active), the stats row below them.
        Div(
            Div(
                view_switcher("today", today),
                _daily_note_button(today),
                cls="flex items-center gap-2",
            ),
            _stats_row(),
            cls="flex flex-col items-end gap-4",
        ),
        cls="flex flex-wrap items-end justify-between gap-5 mb-8",
    )


def _daily_note_button(today: date) -> FT:
    """Daily-note link — the Today rung of the periodic-notes ladder.

    Styled like the calendar's Monthly-note button (square-pen icon); the
    ``_NO_BOOST`` splat forces a full navigation through the journal redirect.
    """
    return A(
        Icon("square-pen", cls="w-[15px] h-[15px]"),
        Span("Daily note"),
        href=f"/journals/daily/{today.isoformat()}",
        title="Open daily note",
        **_NO_BOOST,
        cls=(
            "inline-flex items-center gap-[7px] h-[34px] px-[13px] border border-border"
            " bg-card rounded-lg text-[13px] font-medium text-foreground hover:bg-muted"
            " whitespace-nowrap"
        ),
    )


def _stats_row() -> FT:
    stat_cell = Div(
        Span(
            cls="text-[22px] font-semibold tabular-nums leading-none",
            **{":class": "s.accent || 'text-foreground'", "x-text": "s.value"},
        ),
        Span(
            cls="mt-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground",
            **{"x-text": "s.label"},
        ),
        cls="flex flex-col items-start",
    )
    return Div(
        Template(stat_cell, **{"x-for": "s in statList", ":key": "s.label"}),
        cls="flex items-center gap-6",
        **{"x-show": "!allEmpty"},
    )


# ============================================================================
# Two-column layout — ribbons left, day spine right
# ============================================================================


def _two_column() -> FT:
    return Div(
        _ribbons_column(),
        _day_spine(),
        cls="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_252px] gap-7 items-start",
    )


def _ribbons_column() -> FT:
    return Div(
        _empty_state(),
        _triage_bar(),
        _lifepath_ribbons(),
        _keyboard_hints(),
    )


# ---- Empty state ----------------------------------------------------------


def _empty_state() -> FT:
    # x-show (not x-if) keeps the empty-state block in the DOM and toggles visibility,
    # matching the other always-rendered sections; icons are server-rendered inline SVG.
    return Div(
        Div(
            Icon("check-circle-2", size=28),
            cls=(
                "mx-auto mb-5 w-14 h-14 rounded-lg bg-priority-low/15 text-priority-low "
                "flex items-center justify-center"
            ),
        ),
        H2(
            "You're caught up.",
            cls="text-[22px] font-bold tracking-tight mb-2",
        ),
        P(
            "No nodes scheduled for today. This is the point where most apps would "
            "offer you more to do. SKUEL suggests you close the laptop.",
            cls="text-[13.5px] text-muted-foreground leading-relaxed",
        ),
        cls="text-center mx-auto max-w-md py-20 px-8",
        **{"x-show": "allEmpty"},
    )


# ---- Task row (shared by triage bar + LifePath ribbons) -------------------
#
# Rendered inside an Alpine ``<template x-for="t in ...">``. Alpine binds
# ``t`` to the current task and handles HTML escaping of every ``x-text`` /
# attribute binding — task titles containing ``<script>`` render as text,
# never as markup. The previous innerHTML / template-literal renderer
# required two hand-maintained escape contexts (HTML and JS-string); this
# structural swap eliminates both.


def _task_row(*, is_triage: bool) -> FT:
    right_label_expr = "t.reason || ''" if is_triage else "t.due_label || ''"
    row_classes = (
        "task-row relative flex items-center gap-3 px-3.5 py-2.5 bg-card "
        "rounded-[12px] cursor-grab select-none"
    )
    if is_triage:
        row_classes += " border border-border"

    kind_icon = Div(
        Span(**{"x-html": "kindIconHtml(t.kind)"}),
        cls=(
            "w-[34px] h-[34px] rounded-[8px] flex-none flex items-center justify-center "
            "bg-blue-50 text-blue-600"
        ),
    )

    title_block = Div(
        Div(
            Span(
                cls="text-[14px] font-semibold text-foreground leading-snug truncate",
                **{"x-text": "t.label"},
            ),
            Span(
                cls="w-1.5 h-1.5 rounded-full flex-none",
                **{
                    ":class": (
                        "t.priority === 'high' ? 'bg-priority-high' "
                        ": t.priority === 'medium' ? 'bg-priority-medium' "
                        ": 'bg-priority-low'"
                    ),
                    ":title": "t.priority",
                },
            ),
            cls="flex items-center gap-2",
        ),
        Div(
            cls="text-[12px] text-slate-400 font-mono mt-0.5 truncate",
            **{"x-text": "t.meta || ''"},
        ),
        cls="flex-1 min-w-0",
    )

    right_block = Div(
        Span(
            cls="text-[11px] font-semibold text-foreground",
            **{"x-text": right_label_expr},
        ),
        Span(
            Span(**{"x-text": "t.est_min"}),
            "m",
            cls="text-[10px] text-muted-foreground font-mono",
        ),
        cls="flex flex-col items-end gap-0.5 flex-none",
    )

    open_btn = Button(
        Icon("play", size=12),
        type="button",
        cls="w-7 h-7 rounded flex-none flex items-center justify-center",
        **{
            ":class": (
                "selectedId === t.id "
                "? 'bg-primary text-primary-foreground' "
                ": 'text-muted-foreground hover:bg-muted'"
            ),
            ":aria-label": "'Open ' + (t.label || '')",
            "@click.stop": "openDrawer(t.id)",
        },
    )

    inner_row = Div(
        kind_icon,
        title_block,
        right_block,
        open_btn,
        cls=row_classes,
        role="button",
        tabindex="0",
        **{
            ":class": "{ 'ring-2 ring-primary/40 shadow-focus': selectedId === t.id }",
            ":aria-label": (
                f"(t.label || '') + ' · ' + ({right_label_expr}) + ' · ' + t.est_min + 'm'"
            ),
            "@mousedown": "rowDown($event, t.id)",
            "@click": "rowClick($event, t.id)",
            "@keydown": "rowKey($event, t.id)",
        },
    )

    backdrop = Div(
        Span("drag to defer", cls="opacity-50", **{"data-defer-hint": True}),
        cls=(
            "defer-backdrop absolute inset-0 rounded-md flex items-center justify-end "
            "px-4 text-xs font-semibold tracking-wide pointer-events-none"
        ),
        **{"data-defer-backdrop": True},
    )

    return Div(
        backdrop,
        inner_row,
        cls="relative",
        **{":data-task-row": "t.id"},
    )


# ---- Triage bar -----------------------------------------------------------


def _triage_bar() -> FT:
    heading = Div(
        Div(
            Icon("alert-triangle", size=13),
            cls=(
                "w-[22px] h-[22px] rounded bg-destructive/15 text-destructive "
                "flex items-center justify-center"
            ),
        ),
        Div(
            Div(
                "Face first",
                id="triage-heading",
                cls="text-[10px] font-bold uppercase tracking-[0.09em] text-destructive",
            ),
            Div(
                Span(**{"x-text": "fTriage.length"}),
                " item",
                Span("s", **{"x-show": "fTriage.length !== 1"}),
                " need",
                Span("s", **{"x-show": "fTriage.length === 1"}),
                " your attention",
                cls="text-[13px] font-semibold text-foreground",
            ),
            cls="flex-1 min-w-0",
        ),
        Span(
            "drag → to defer",
            cls="font-mono text-[11px] text-muted-foreground hidden sm:inline",
        ),
        cls="flex items-center gap-2.5 mb-3",
    )
    list_body = Ul(
        Template(
            Li(_task_row(is_triage=True)),
            **{"x-for": "t in fTriage", ":key": "t.id"},
        ),
        cls="flex flex-col gap-2",
        role="list",
    )
    return Section(
        heading,
        list_body,
        cls=(
            "mb-7 rounded-lg border border-destructive/40 "
            "bg-gradient-to-b from-destructive/5 to-transparent "
            "px-[18px] py-3.5 shadow-[0_1px_2px_rgba(220,38,38,0.08)]"
        ),
        role="region",
        **{
            "x-show": "!allEmpty && fTriage.length > 0",
            "aria-labelledby": "triage-heading",
        },
    )


# ---- LifePath ribbons -----------------------------------------------------


def _lifepath_ribbons() -> FT:
    return Template(
        Section(
            _dormant_ribbon(),
            _active_ribbon(),
            cls="mb-5",
            role="region",
            **{":aria-labelledby": "'ribbon-' + lp.id"},
        ),
        **{"x-for": "lp in seed.lifepaths", ":key": "lp.id"},
    )


def _dormant_ribbon() -> FT:
    inner = Div(
        Div(
            cls="w-1.5 h-5.5 rounded-sm",
            **{":style": "`background:${lp.color};opacity:.4`"},
        ),
        Div(
            Div(
                Span(**{":id": "'ribbon-' + lp.id", "x-text": "lp.label"}),
                Span(
                    "dormant",
                    cls=(
                        "ml-2 inline-block text-[10px] font-semibold uppercase "
                        "tracking-[0.08em] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                    ),
                ),
                cls="text-[13px] font-semibold text-foreground",
            ),
            Div(
                "Nothing active today. Last touched ",
                Span(**{"x-text": "lp.last_touched"}),
                ".",
                Template(
                    NotStr("<em x-text=\"' · ' + principlesFor(lp.id)[0].label\"></em>"),
                    **{"x-if": "principlesFor(lp.id)[0]"},
                ),
                cls="text-[11.5px] mt-0.5",
            ),
            cls="flex-1 min-w-0",
        ),
        Button(
            "Wake this path",
            type="button",
            cls=(
                "bg-transparent border border-border px-3 py-1.5 rounded text-xs font-medium "
                "text-foreground hover:bg-muted focus:outline-none focus:shadow-focus"
            ),
            **{
                ":hx-post": "`/today/lifepaths/${lp.id}/wake`",
                "hx-target": "closest section",
                "hx-swap": "outerHTML",
            },
        ),
        cls=(
            "flex items-center gap-3.5 px-[18px] py-3 rounded-lg bg-card "
            "border border-dashed border-border text-muted-foreground"
        ),
    )
    return Template(inner, **{"x-if": "lp.dormant"})


def _active_ribbon() -> FT:
    ribbon_header = Header(
        Div(cls="w-1.5 h-6 rounded-sm", **{":style": "`background:${lp.color}`"}),
        Div(
            Div(
                H2(
                    cls="text-[15px] font-semibold tracking-tight",
                    **{":id": "'ribbon-' + lp.id", "x-text": "lp.label"},
                ),
                Span(
                    cls="text-[11px] text-muted-foreground font-mono",
                    **{"x-text": "lp.blurb"},
                ),
                cls="flex items-center gap-2",
            ),
            Div(
                Template(
                    Span(
                        Span(**{"x-text": "p.label"}),
                        Span(
                            cls="font-mono opacity-60",
                            **{
                                "x-text": "p.embodiment_rate > 0 "
                                "? ('· ' + Math.round(p.embodiment_rate * 100) + '%') "
                                ": ''"
                            },
                        ),
                        cls="inline-flex items-center gap-1 text-[10.5px] font-medium px-1.5 py-0.5 rounded-full",
                        **{":class": "strengthClass(p.strength)"},
                    ),
                    **{"x-for": "p in principlesFor(lp.id)", ":key": "p.id"},
                ),
                cls="mt-1 flex items-center gap-1.5 flex-wrap",
            ),
            cls="flex-1 min-w-0",
        ),
        Span(
            cls="text-[11px] text-muted-foreground font-mono flex-none",
            **{"x-text": "tasksFor(lp.id).length + ' today'"},
        ),
        cls="flex items-center gap-3 px-[18px] py-3 border-b border-border/70",
    )
    tasks_list = Ul(
        Template(
            Li(_task_row(is_triage=False)),
            **{"x-for": "t in tasksFor(lp.id)", ":key": "t.id"},
        ),
        Template(
            Li(
                "Nothing committed for today on this ribbon.",
                cls="px-[18px] py-3 text-[12px] text-muted-foreground italic",
            ),
            **{"x-if": "tasksFor(lp.id).length === 0"},
        ),
        cls="divide-y divide-border/70",
        role="list",
    )
    inner = Div(
        ribbon_header,
        tasks_list,
        cls="rounded-lg border border-border bg-card overflow-hidden",
    )
    return Template(inner, **{"x-if": "!lp.dormant"})


# ---- Keyboard hints -------------------------------------------------------


def _keyboard_hints() -> FT:
    def _hint(*children: Any) -> FT:
        return Span(*children)

    return Div(
        _hint(Kbd("j", cls="kbd"), Kbd("k", cls="kbd"), " move"),
        _hint(Kbd("↵", cls="kbd"), " open"),
        _hint(Kbd("x", cls="kbd"), " complete"),
        _hint(Kbd("d", cls="kbd"), " defer 1d"),
        _hint(Kbd("⇧", cls="kbd"), Kbd("d", cls="kbd"), " defer 1w"),
        Span("or drag any card →", cls="ml-auto"),
        cls=(
            "mt-8 px-[18px] py-3.5 bg-card border border-border rounded-lg "
            "flex items-center gap-6 text-[11px] text-muted-foreground font-mono flex-wrap"
        ),
        **{"x-show": "!allEmpty"},
    )


# ============================================================================
# Right column — day spine
# ============================================================================


def _day_spine() -> FT:
    return Aside(
        Div(
            "Day spine",
            cls=(
                "absolute top-3.5 left-[18px] text-[10px] font-bold uppercase "
                "tracking-[0.09em] text-muted-foreground"
            ),
        ),
        Div(cls="absolute left-[30px] top-[52px] bottom-[18px] w-0.5 bg-border"),
        _hour_ticks(),
        _now_marker(),
        _rituals_list(),
        cls=(
            "relative sticky top-7 h-[640px] w-full max-w-[252px] bg-card "
            "border border-border rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.03)] "
            "pt-12 pr-3.5 pb-[18px] pl-12 box-border overflow-hidden"
        ),
        **{"aria-label": "Day spine"},
    )


def _hour_ticks() -> FT:
    return Template(
        Div(
            cls="absolute left-2.5 -translate-y-1/2 text-[9px] text-muted-foreground/70 font-mono",
            **{
                ":style": "`top: calc(52px + ${((h - 6) / 16) * (640 - 70)}px)`",
                "x-text": "String(h).padStart(2, '0')",
            },
        ),
        **{"x-for": "h in [8, 12, 16, 20]", ":key": "h"},
    )


def _now_marker() -> FT:
    return Div(
        Span(cls="absolute left-[18px] -top-1 w-2 h-2 rounded-full bg-destructive"),
        Span(
            "NOW · ",
            Span(**{"x-text": "seed.now_hhmm"}),
            cls=(
                "absolute left-8 -top-2 text-[9px] font-bold text-destructive "
                "bg-card px-1 font-mono whitespace-nowrap"
            ),
        ),
        cls="absolute left-2.5 right-3 h-px bg-destructive",
        **{":style": "`top: calc(52px + ${(nowPct / 100) * (640 - 70)}px)`"},
    )


def _rituals_list() -> FT:
    dot = Div(
        Span(**{"x-html": "ritualIconHtml(r.time)"}),
        cls="w-[18px] h-[18px] rounded-full flex-none flex items-center justify-center",
        **{
            ":class": (
                "ritualPast(r.time) "
                "? 'bg-muted text-muted-foreground border border-border' "
                ": 'bg-strength-core/10 text-strength-core border-2 border-strength-core'"
            ),
        },
    )
    body = Div(
        Div(
            cls="text-[11.5px] font-semibold truncate",
            **{
                ":class": (
                    "ritualPast(r.time) ? 'text-muted-foreground line-through' : 'text-foreground'"
                ),
                "x-text": "r.label",
            },
        ),
        Div(
            Span(**{"x-text": "r.time"}),
            " · ",
            Span(**{"x-text": "r.est_min"}),
            "m",
            cls="text-[9.5px] font-mono text-muted-foreground",
        ),
        cls="flex-1 min-w-0",
    )
    return Template(
        Div(
            dot,
            body,
            cls="absolute left-2.5 right-3 -translate-y-1/2 flex items-center gap-2",
            **{":style": "`top: calc(52px + ${ritualPct(r.time) * (640 - 70)}px)`"},
        ),
        **{"x-for": "r in seed.rituals", ":key": "r.id"},
    )


# ============================================================================
# Flash toast
# ============================================================================


def _flash_toast() -> FT:
    return Div(
        Span(**{"x-text": "flash?.msg"}),
        Button(
            "Undo",
            type="button",
            cls=(
                "bg-transparent border border-background/20 text-background "
                "px-2.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider "
                "hover:bg-background/10 focus:outline-none focus:shadow-focus"
            ),
            **{"x-show": "flash?.action === 'undo'", "@click": "undoFlash()"},
        ),
        cls=(
            "fixed bottom-6 left-1/2 -translate-x-1/2 z-20 "
            "bg-foreground text-background rounded-lg px-4 py-2.5 pr-3 "
            "flex items-center gap-3.5 text-[13px] shadow-xl"
        ),
        role="status",
        **{
            "x-show": "flash",
            "x-cloak": True,
            "x-transition.opacity.duration.150ms": True,
            "aria-live": "polite",
        },
    )


# ============================================================================
# Detail drawer
# ============================================================================


def _drawer() -> FT:
    scrim = Div(
        cls="absolute inset-0 bg-foreground/40",
        **{
            "x-show": "openTask",
            "x-transition.opacity.duration.200ms": True,
            "@click": "closeDrawer()",
        },
    )
    panel = _drawer_panel()
    return Div(
        scrim,
        panel,
        cls="fixed inset-0 z-30",
        role="dialog",
        **{
            "x-show": "openTask",
            "x-cloak": True,
            ":aria-labelledby": "openTask ? 'drawer-title' : null",
            "aria-modal": "true",
            "@keydown.escape.window": "closeDrawer()",
        },
    )


def _drawer_panel() -> FT:
    return Aside(
        Template(_drawer_inner(), **{"x-if": "openTask"}),
        cls=(
            "absolute top-0 right-0 h-full w-full max-w-[440px] bg-background "
            "border-l border-border shadow-2xl overflow-y-auto"
        ),
        **{
            "x-show": "openTask",
            "x-transition:enter": "transition ease-out duration-200",
            "x-transition:enter-start": "translate-x-full",
            "x-transition:enter-end": "translate-x-0",
            "x-transition:leave": "transition ease-in duration-150",
            "x-transition:leave-start": "translate-x-0",
            "x-transition:leave-end": "translate-x-full",
            # Server-swapped richer body. `openDrawer()` in today.js fires
            # `load-drawer` on body (after setting openTaskId) to trigger this.
            ":hx-get": "openTask ? `/today/tasks/${openTask.id}/drawer` : null",
            "hx-trigger": "load-drawer from:body",
            "hx-target": "#drawer-body",
            "hx-swap": "innerHTML",
        },
    )


def _drawer_inner() -> FT:
    return Div(
        _drawer_toolbar(),
        _drawer_title_meta(),
        _drawer_primary_action(),
        _drawer_secondary_actions(),
        _drawer_connects(),
        Div(id="drawer-body", cls="mt-6"),
        cls="p-6",
    )


def _drawer_toolbar() -> FT:
    kind_chip = Span(
        Span(**{"x-html": "openTaskIconHtml()"}),
        Span(**{"x-text": "seed.kinds[openTask.kind]?.label || openTask.kind"}),
        cls=(
            "inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10.5px] "
            "font-semibold uppercase tracking-[0.08em] bg-muted text-muted-foreground"
        ),
    )
    star_btn = Button(
        Icon("star", size=14),
        type="button",
        cls="w-7 h-7 rounded hover:bg-muted flex items-center justify-center",
        **{":hx-post": "`/today/tasks/${openTask.id}/star`", "aria-label": "Star"},
    )
    close_btn = Button(
        Icon("x", size=14),
        type="button",
        cls="w-7 h-7 rounded hover:bg-muted flex items-center justify-center",
        **{"@click": "closeDrawer()", "aria-label": "Close drawer"},
    )
    return Div(
        kind_chip,
        Div(star_btn, close_btn, cls="flex items-center gap-1"),
        cls="flex items-center justify-between mb-5",
    )


def _drawer_title_meta() -> FT:
    priority_dot = Span(
        cls="w-1.5 h-1.5 rounded-full",
        **{
            ":class": (
                "openTask.priority === 'high'   ? 'bg-priority-high' "
                ": openTask.priority === 'medium' ? 'bg-priority-medium' "
                ": 'bg-priority-low'"
            ),
        },
    )
    sep = Span(cls="w-[3px] h-[3px] rounded-full bg-border")
    return Div(
        H2(
            id="drawer-title",
            cls="text-[22px] font-bold tracking-tight leading-tight",
            **{"x-text": "openTask.label"},
        ),
        Div(
            Span(**{"x-text": "openTask.meta"}),
            sep,
            Span(
                **{
                    ":class": (
                        "(openTask.due_label || '').startsWith('Overdue') || "
                        "(openTask.reason || '').startsWith('Overdue') "
                        "? 'text-destructive' : ''"
                    ),
                    "x-text": "openTask.due_label || openTask.reason || 'Triage'",
                },
            ),
            sep,
            Span(
                priority_dot,
                Span(**{"x-text": "openTask.priority"}),
                cls="inline-flex items-center gap-1",
            ),
            sep,
            Span(Span(**{"x-text": "openTask.est_min"}), "m"),
            cls="mt-2.5 flex items-center gap-3 text-[12px] text-muted-foreground font-mono",
        ),
    )


def _drawer_primary_action() -> FT:
    return Button(
        Icon("check", size=16),
        "Mark complete",
        type="button",
        cls=(
            "mt-4 w-full inline-flex items-center justify-center gap-2 "
            "px-4 py-2.5 rounded-md bg-foreground text-background "
            "text-sm font-semibold hover:opacity-90 "
            "focus:outline-none focus:shadow-focus"
        ),
        **{
            ":hx-post": "`/today/tasks/${openTask.id}/complete`",
            "hx-swap": "none",
            "@click": "completeTask(openTask.id); closeDrawer()",
        },
    )


def _drawer_secondary_actions() -> FT:
    def _defer_btn(label: str, span: str) -> FT:
        return Button(
            label,
            type="button",
            cls=(
                "px-3 py-2 rounded-md border border-border bg-card "
                "text-sm font-medium hover:bg-muted "
                "focus:outline-none focus:shadow-focus"
            ),
            **{
                ":hx-post": "`/today/tasks/${openTask.id}/defer`",
                "hx-vals": f'{{"span":"{span}"}}',
                "hx-swap": "none",
                "@click": f"deferTask(openTask.id, '{span}'); closeDrawer()",
            },
        )

    return Div(
        _defer_btn("Defer tomorrow", "1d"),
        _defer_btn("Defer next week", "1w"),
        cls="mt-2.5 grid grid-cols-2 gap-2",
    )


def _drawer_connects() -> FT:
    def _row(icon: str, label: str, field_expr: str, if_expr: str) -> FT:
        return Template(
            Div(
                Icon(icon, size=14, cls="text-muted-foreground"),
                Span(label, cls="text-muted-foreground"),
                Span(cls="font-medium", **{"x-text": field_expr}),
                cls="flex items-center gap-2 text-[13px]",
            ),
            **{"x-if": if_expr},
        )

    return Section(
        section_label("Connects"),
        Div(
            _row("target", "Goal:", "goalFor(openTask).label", "goalFor(openTask)"),
            _row("anchor", "Principle:", "principleFor(openTask).label", "principleFor(openTask)"),
            _row("compass", "LifePath:", "lifepathFor(openTask).label", "lifepathFor(openTask)"),
            cls="rounded-lg border border-border bg-muted/40 p-3.5 space-y-2",
        ),
        cls="mt-7",
    )


__all__ = ["TodayPage"]
