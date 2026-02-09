"""Unified sidebar component — Tailwind + Alpine.js.

Desktop: Collapsible fixed sidebar with toggle button.
Mobile: Horizontal DaisyUI tabs at top of content area.

One pattern for all sidebar pages (Profile, KU, Reports, Journals, Askesis).

Usage:
    from ui.patterns.sidebar import SidebarItem, SidebarPage

    items = [
        SidebarItem("Submit", "/reports/submit", "submit", icon="📤"),
        SidebarItem("Browse", "/reports/browse", "browse", icon="📂"),
    ]

    return await SidebarPage(
        content=my_content,
        items=items,
        active="submit",
        title="Reports",
        storage_key="reports-sidebar",
        request=request,
        active_page="reports",
    )
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from fasthtml.common import A, Button, Div, H3, Li, NotStr, P, Span, Ul

from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


@dataclass
class SidebarItem:
    """Single navigation item for sidebar and mobile tabs."""

    label: str
    href: str
    slug: str
    icon: str = ""
    description: str = ""
    badge_text: str = ""
    badge_cls: str = "badge badge-sm badge-ghost"
    hx_attrs: dict[str, str] = field(default_factory=dict)


def _chevron_svg() -> "FT":
    """Collapse toggle chevron icon."""
    return NotStr(
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M15 18l-6-6 6-6"></path>'
        "</svg>"
    )


def _default_item_renderer(item: SidebarItem, is_active: bool) -> "FT":
    """Default sidebar item renderer."""
    active_cls = "bg-base-200 font-semibold" if is_active else ""
    children: list[Any] = []

    if item.icon:
        children.append(Span(item.icon, cls="text-lg", aria_hidden="true"))

    children.append(Span(item.label, cls="flex-1"))

    if item.description:
        # Two-line item (Askesis style)
        content = Div(
            Div(
                Span(item.icon, cls="text-lg mr-2", aria_hidden="true") if item.icon else "",
                Span(item.label, cls="font-medium"),
                cls="flex items-center",
            ),
            P(item.description, cls="text-xs opacity-60 mt-0.5 ml-7")
            if item.icon
            else P(item.description, cls="text-xs opacity-60 mt-0.5"),
            cls="w-full",
        )
        return Li(
            A(
                content,
                href=item.href,
                cls=f"flex items-center rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-base-200 {active_cls}",
                **{"hx-boost": "false"},
                **item.hx_attrs,
            )
        )

    if item.badge_text:
        children.append(Span(item.badge_text, cls=item.badge_cls))

    return Li(
        A(
            *children,
            href=item.href,
            cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-base-200 {active_cls}",
            **{"hx-boost": "false"},
            **item.hx_attrs,
        )
    )


def SidebarNav(
    items: list[SidebarItem],
    active: str,
    title: str,
    subtitle: str = "",
    storage_key: str = "sidebar",
    extra_sidebar_sections: list[Any] | None = None,
    extra_mobile_sections: list[Any] | None = None,
    item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    title_href: str = "",
) -> "FT":
    """Build sidebar navigation (desktop) + horizontal tabs (mobile).

    Args:
        items: Navigation items
        active: Currently active item slug
        title: Sidebar heading
        subtitle: Optional subtitle below heading
        storage_key: localStorage key for collapse state
        extra_sidebar_sections: Additional content appended to desktop sidebar
        extra_mobile_sections: Additional content below mobile tabs
        item_renderer: Custom function to render sidebar items
        title_href: Optional link for the title heading

    Returns:
        Div containing both desktop sidebar and mobile tabs
    """
    renderer = item_renderer or _default_item_renderer

    # --- Desktop sidebar (hidden below lg:) ---
    sidebar_items = [renderer(item, item.slug == active) for item in items]

    extra_sections = []
    if extra_sidebar_sections:
        extra_sections = [
            Li(cls="border-t border-base-200 my-2"),
            *extra_sidebar_sections,
        ]

    title_el: Any
    if title_href:
        title_el = A(
            title,
            href=title_href,
            cls="text-xl font-bold text-primary hover:text-primary-focus",
            **{"hx-boost": "false"},
        )
    else:
        title_el = H3(title, cls="text-xl font-bold text-primary")

    sidebar = Div(
        Div(
            # Toggle button
            Button(
                _chevron_svg(),
                cls="absolute right-2 top-4 w-11 h-11 flex items-center justify-center"
                " rounded-md border border-base-300 bg-white hover:bg-base-200"
                " transition-all duration-300 cursor-pointer z-10",
                type="button",
                aria_label="Toggle sidebar",
                **{
                    ":aria-expanded": "!collapsed",
                    "@click": "toggle()",
                    ":class": "collapsed ? '[&_svg]:rotate-180' : ''",
                },
            ),
            # Nav menu
            Ul(
                # Header
                Li(
                    title_el,
                    P(subtitle, cls="text-xs opacity-60 mt-1") if subtitle else "",
                    cls="px-4 py-4",
                ),
                Li(cls="border-t border-base-200 my-0"),
                *sidebar_items,
                *extra_sections,
                cls="menu w-full p-4 transition-opacity duration-300",
                **{":class": "collapsed ? 'opacity-0 invisible' : 'opacity-100 visible'"},
            ),
            cls="h-full relative overflow-y-auto",
        ),
        cls="hidden lg:block fixed top-16 left-0 bottom-0 w-64 bg-white"
        " border-r border-base-300 z-40 transition-transform duration-300"
        " overflow-hidden",
        **{":class": "collapsed ? '-translate-x-52' : 'translate-x-0'"},
        role="navigation",
        aria_label=f"{title} sidebar",
        **{"x-data": f"collapsibleSidebar('{storage_key}')"},
    )

    # --- Mobile tabs (hidden at lg: and above) ---
    tab_items = []
    for item in items:
        is_active = item.slug == active
        tab_label = f"{item.icon} {item.label}" if item.icon else item.label
        tab_items.append(
            A(
                tab_label,
                href=item.href,
                role="tab",
                cls=f"tab whitespace-nowrap {'tab-active' if is_active else ''}",
                **{"hx-boost": "false"},
                **item.hx_attrs,
            )
        )

    mobile_extra = []
    if extra_mobile_sections:
        mobile_extra = list(extra_mobile_sections)

    mobile_tabs = Div(
        Div(
            *tab_items,
            cls="tabs tabs-bordered overflow-x-auto flex-nowrap",
            role="tablist",
            aria_label=f"{title} navigation",
        ),
        *mobile_extra,
        cls="lg:hidden mb-4",
    )

    return Div(sidebar, mobile_tabs)


async def SidebarPage(
    content: Any,
    items: list[SidebarItem],
    active: str,
    title: str,
    subtitle: str = "",
    storage_key: str = "sidebar",
    extra_sidebar_sections: list[Any] | None = None,
    extra_mobile_sections: list[Any] | None = None,
    page_title: str = "",
    request: "Request | None" = None,
    active_page: str = "",
    item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    title_href: str = "",
) -> "FT":
    """Create a full page with collapsible sidebar navigation.

    Desktop: Fixed sidebar (collapsible) + content area with left margin.
    Mobile: Horizontal tabs above content, no sidebar.

    See: /docs/patterns/UI_COMPONENT_PATTERNS.md
    """
    nav = SidebarNav(
        items=items,
        active=active,
        title=title,
        subtitle=subtitle,
        storage_key=storage_key,
        extra_sidebar_sections=extra_sidebar_sections,
        extra_mobile_sections=extra_mobile_sections,
        item_renderer=item_renderer,
        title_href=title_href,
    )

    # Content area with responsive margin
    # x-data needed here too to read collapsed state for margin adjustment
    page_content = Div(
        nav,
        Div(
            Div(
                content,
                cls="max-w-6xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
            ),
            cls="lg:ml-64 lg:transition-[margin-left] lg:duration-300 min-h-[calc(100vh-64px)]",
            id="sidebar-content",
            **{
                "x-data": f"collapsibleSidebar('{storage_key}')",
                ":class": "collapsed ? 'lg:ml-12' : 'lg:ml-64'",
            },
        ),
    )

    return await BasePage(
        content=page_content,
        title=page_title or title,
        page_type=PageType.CUSTOM,
        request=request,
        active_page=active_page,
    )


__all__ = [
    "SidebarItem",
    "SidebarNav",
    "SidebarPage",
]
