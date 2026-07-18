"""Explore sidebar navigation — graph-centered with filter tabs.

The sidebar has two zones:
1. Hero graph (Vis.js) — shows entity relationships or learning universe
2. Filtered item list — Learning/Saved/All tabs control both graph highlighting
   and which items appear in the list below

Usage:
    from ui.explore.nav import render_explore_sidebar_page

    # Route handler fetches sidebar_data from orchestrator first:
    sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None

    return await render_explore_sidebar_page(
        content=my_content,
        sidebar_data=sidebar_data,
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Li, P, Span, Ul

from core.models.enums.entity_enums import EntityType
from ui.components import ButtonT
from ui.explore.graph import ExploreGraphView
from ui.patterns.sidebar import SidebarPage
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

EXPLORE_STORAGE_KEY = "explore-sidebar"

# Type pill badge classes (match explore_ui.py)
_KU_PILL_CLS = (
    "bg-violet-100 text-violet-800 border border-violet-200 "
    "text-xs font-medium px-1.5 py-0 rounded-full shrink-0"
)
_PS_PILL_CLS = (
    "bg-teal-100 text-teal-800 border border-teal-200 "
    "text-xs font-medium px-1.5 py-0 rounded-full shrink-0"
)


def _sidebar_link_with_pill(
    title: str, href: str, entity_type: str, is_current: bool = False
) -> "FT":
    """Sidebar link with Ku/PS type pill badge."""
    is_ku = entity_type == EntityType.KU.value
    pill_cls = _KU_PILL_CLS if is_ku else _PS_PILL_CLS
    pill_label = "Ku" if is_ku else "PS"
    active_cls = "font-semibold text-foreground" if is_current else "text-muted-foreground"

    return Li(
        A(
            Span(pill_label, cls=pill_cls),
            Span(title, cls=f"truncate {active_cls}"),
            href=href,
            cls="text-sm hover:text-foreground transition-colors flex items-center gap-2 py-1 px-3",
        ),
    )


def _build_section(
    title: str,
    links: list["FT"],
    empty_text: str = "",
    collapsible: bool = False,
    see_all_href: str = "",
    filter_name: str = "",
) -> "FT":
    """Render a sidebar section with header + link list.

    Args:
        title: Section header.
        links: Pre-rendered link elements.
        empty_text: Text to show when links is empty.
        collapsible: If True, wrap in Alpine x-data for expand/collapse.
        see_all_href: If set, show a "See all" link at the bottom.
        filter_name: If set, only show this section when the filter matches.
    """
    header = P(
        title,
        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
    )

    if not links:
        empty_el = (
            P(empty_text, cls="text-xs text-muted-foreground/60 italic px-4 pb-2")
            if empty_text
            else Div()
        )
        section = Li(header, empty_el)
    elif collapsible:
        footer_parts: list[Any] = []
        if see_all_href:
            footer_parts.append(
                ButtonLink(
                    "See all",
                    href=see_all_href,
                    cls=(ButtonT.ghost, "mx-4 mb-2"),
                    size="xs",
                    x_show="!expanded",
                ),
            )
        section = Li(
            header,
            Div(
                Ul(*links, cls="list-none p-0"),
                *footer_parts,
                x_data="{ expanded: false }",
            ),
        )
    else:
        section = Li(header, Ul(*links, cls="list-none p-0"))

    # Wrap with filter visibility if needed
    if filter_name:
        return Div(
            section,
            x_show=f"filter === '{filter_name}' || filter === 'all'",
            x_cloak=True,
        )
    return section


async def render_explore_sidebar_page(
    content: Any,
    sidebar_data: dict[str, Any] | None,
    request: "Request",
    page_title: str = "Explore",
    current_uid: str = "",
    current_entity_type: str = "",
) -> "FT":
    """Wrap content in Explore sidebar page with graph hero + filtered lists.

    Args:
        content: The page content to render in the main area.
        sidebar_data: Pre-fetched sidebar data from ExploreOrchestrator.get_sidebar_data(),
            or None for unauthenticated users.
        request: The request object for layout rendering.
        page_title: Page title (default "Explore", or entity title on detail pages).
        current_uid: UID of the currently viewed entity (for graph centering).
        current_entity_type: 'ku' or 'ps' — type of current entity.
    """
    sections: list[Any] = []

    # Determine graph mode
    is_entity_mode = bool(current_uid and current_entity_type)
    graph_mode = "entity" if is_entity_mode else "hub"
    alpine_args = f"'{graph_mode}', '{current_uid}', '{current_entity_type}'"

    # Graph hero — always shown, standalone=False so parent Li owns the scope
    graph = ExploreGraphView(
        mode=graph_mode,
        entity_uid=current_uid if is_entity_mode else "",
        entity_type=current_entity_type if is_entity_mode else "",
        standalone=False,
    )

    if sidebar_data is None:
        # Unauthenticated: graph + sign-in prompt in one Alpine scope
        sign_in_prompt = P(
            "Sign in to track your learning",
            cls="text-xs text-muted-foreground/60 italic px-4 py-2",
        )
        sections.append(
            Li(
                Div(
                    graph,
                    sign_in_prompt,
                    x_data=f"exploreGraph({alpine_args})",
                    x_init="init()",
                ),
            )
        )
    else:
        data = sidebar_data

        # Section: Learning (studying Kus + in-progress PSes)
        learning_links: list[Any] = []
        for rec in data["studying_kus"]:
            learning_links.append(
                _sidebar_link_with_pill(
                    rec["title"],
                    f"/explore/ku/{rec['uid']}",
                    "ku",
                    is_current=rec["uid"] == current_uid,
                )
            )
        for ps in data["in_progress_ps"]:
            learning_links.append(
                _sidebar_link_with_pill(
                    ps.title or ps.uid,
                    f"/explore/ps/{ps.uid}",
                    "ps",
                    is_current=ps.uid == current_uid,
                )
            )
        learning_section = _build_section(
            "Learning",
            learning_links,
            empty_text="Start exploring below",
            filter_name="learning",
        )

        # Section: Saved (pinned items)
        saved_links: list[Any] = []
        for pin_uid, pin_title, et in data["pinned_items"]:
            saved_links.append(
                _sidebar_link_with_pill(
                    pin_title,
                    f"/explore/{'ku' if et == EntityType.KU.value else 'ps'}/{pin_uid}",
                    et,
                    is_current=pin_uid == current_uid,
                )
            )
        saved_section = _build_section(
            "Saved",
            saved_links,
            empty_text="Pin items to save them here",
            filter_name="saved",
        )

        # Section: Completed (recent 3, collapsible — shown in "all" filter)
        completed_links: list[Any] = []
        understood = data["understood_kus"]
        display_count = min(len(understood), 3)
        for rec in understood[:display_count]:
            completed_links.append(
                _sidebar_link_with_pill(
                    rec["title"],
                    f"/explore/ku/{rec['uid']}",
                    "ku",
                    is_current=rec["uid"] == current_uid,
                )
            )
        completed_section = _build_section(
            "Completed",
            completed_links,
            empty_text="Nothing completed yet",
            collapsible=len(understood) > 3,
        )

        # Wrap graph + all sections in a single Alpine scope
        sections.append(
            Li(
                Div(
                    graph,
                    learning_section,
                    saved_section,
                    completed_section,
                    x_data=f"exploreGraph({alpine_args})",
                    x_init="init()",
                ),
            )
        )

    return await SidebarPage(
        content=content,
        items=[],
        active="",
        title="Explore",
        storage_key=EXPLORE_STORAGE_KEY,
        extra_sidebar_sections=sections or None,
        page_title=page_title,
        request=request,
        active_page="explore",
        title_href="/explore",
        sidebar_width="w-96",
    )


__all__ = ["render_explore_sidebar_page"]
