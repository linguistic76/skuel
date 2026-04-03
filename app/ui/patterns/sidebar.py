"""Unified sidebar component — Tailwind + Alpine.js (MonsterUI).

Desktop: Collapsible fixed sidebar with toggle button.
Mobile: Horizontal tabs at top of content area.

One pattern for all sidebar pages (Profile, KU, Submissions, Journals, Askesis).

Usage:
    from ui.patterns.sidebar import SidebarItem, SidebarPage

    items = [
        SidebarItem("Submit", "/submit", "submit", icon="..."),
        SidebarItem("Browse", "/gradebook", "browse", icon="..."),
    ]

    return await SidebarPage(
        content=my_content,
        items=items,
        active="submit",
        title="GradeBook",
        storage_key="gradebook-sidebar",
        request=request,
        active_page="gradebook",
    )
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, A, Button, Div, Li, P, Span, Ul
from monsterui.franken import UkIcon

from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request


@dataclass
class SidebarItem:
    """Single navigation item for sidebar and mobile tabs."""

    label: str
    href: str
    slug: str
    icon: str = ""
    description: str = ""
    badge_text: str = ""
    badge_cls: str = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground"
    hx_attrs: dict[str, str] = field(default_factory=dict)
    children: list["SidebarItem"] = field(default_factory=list)


def _chevron_svg() -> "FT":
    """Collapse toggle chevron icon."""
    return UkIcon("chevron-left", height=16, width=16, cls="", aria_hidden="true")


def _render_accordion_item(item: SidebarItem, is_active: bool) -> "FT":
    """Render a sidebar item as an accordion with expandable children."""
    active_cls = "bg-accent font-semibold" if is_active else ""
    header_children: list[Any] = []

    if item.icon:
        header_children.append(UkIcon(item.icon, height=18, width=18, cls="shrink-0", aria_hidden="true"))

    header_children.append(Span(item.label, cls="flex-1"))

    if item.badge_text:
        header_children.append(Span(item.badge_text, cls=item.badge_cls))

    # Chevron that rotates when expanded
    header_children.append(
        UkIcon(
            "chevron-down",
            height=14,
            width=14,
            cls="transition-transform duration-200",
            **{":class": "open ? 'rotate-180' : ''"},
        )
    )

    # Child links
    child_links = [
        Li(
            A(
                child.label,
                href=child.href,
                cls="text-sm text-muted-foreground hover:text-foreground transition-colors block py-1.5 px-3",
            )
        )
        for child in item.children
    ]

    return Li(
        Div(
            # Clickable header — toggles accordion
            Div(
                *header_children,
                cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-accent cursor-pointer {active_cls}",
                **{"@click": "open = !open"},
                role="button",
                aria_label=f"Toggle {item.label} list",
            ),
            # Collapsible child list
            Ul(
                *child_links,
                cls="pl-6 list-none",
                x_show="open",
                **{"x-transition.duration.200ms": True},
            ),
            **{
                "x-data": f"{{ open: {str(is_active).lower()} }}",
            },
        )
    )


def _default_item_renderer(item: SidebarItem, is_active: bool) -> "FT":
    """Default sidebar item renderer."""
    # Accordion for items with children
    if item.children:
        return _render_accordion_item(item, is_active)

    active_cls = "bg-accent font-semibold" if is_active else ""
    children: list[Any] = []

    if item.icon:
        children.append(UkIcon(item.icon, height=18, width=18, cls="shrink-0", aria_hidden="true"))

    children.append(Span(item.label, cls="flex-1"))

    if item.description:
        # Two-line item (Askesis style)
        content = Div(
            Div(
                UkIcon(item.icon, height=18, width=18, cls="mr-2 shrink-0", aria_hidden="true") if item.icon else "",
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
                cls=f"flex items-center rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-accent {active_cls}",
                **item.hx_attrs,
            )
        )

    if item.badge_text:
        children.append(Span(item.badge_text, cls=item.badge_cls))

    # Badge placeholder for async OOB swap (Phase 5 sidebar badges)
    children.append(Span(id=f"sidebar-badge-{item.slug}"))

    return Li(
        A(
            *children,
            href=item.href,
            cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-accent {active_cls}",
            **item.hx_attrs,
        )
    )


def SidebarLink(text: str, href: str) -> "FT":
    """Compact sidebar link for entity lists (bookmarks, latest, etc.)."""
    return Li(
        A(
            text,
            href=href,
            cls="text-sm text-muted-foreground hover:text-foreground transition-colors block py-1 px-3",
        ),
    )


def alpine_section_renderer(state_var: str = "section") -> Callable[[SidebarItem, bool], Any]:
    """Item renderer for Alpine-driven section switching (no page navigation).

    Items use @click to set Alpine state variable instead of href links.
    The `slug` field on each SidebarItem maps to the section value.
    """

    def _render(item: SidebarItem, _is_active: bool) -> "FT":
        children: list[Any] = []
        if item.icon:
            children.append(UkIcon(item.icon, height=18, width=18, cls="shrink-0", aria_hidden="true"))
        children.append(Span(item.label, cls="flex-1"))
        if item.badge_text:
            children.append(
                Span(
                    item.badge_text,
                    cls="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-primary/10",
                )
            )

        return Li(
            Div(
                *children,
                cls="flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] "
                "transition-colors hover:bg-accent cursor-pointer",
                role="tab",
                **{
                    "@click": f"{state_var} = '{item.slug}'",
                    ":class": f"{state_var} === '{item.slug}' ? 'bg-accent font-semibold' : ''",
                    ":aria-selected": f"{state_var} === '{item.slug}'",
                },
            )
        )

    return _render


def alpine_mobile_section_renderer(
    state_var: str = "section",
) -> Callable[[SidebarItem, bool], Any]:
    """Mobile tab renderer for Alpine-driven section switching.

    Returns tab-shaped elements with @click instead of href.
    """

    def _render(item: SidebarItem, _is_active: bool) -> "FT":
        tab_children: list[Any] = []
        if item.icon:
            tab_children.append(UkIcon(item.icon, height=16, width=16, cls="shrink-0", aria_hidden="true"))
        tab_children.append(Span(item.label))
        if item.badge_text:
            tab_children.append(Span(item.badge_text, cls="ml-1 text-xs"))

        return Div(
            *tab_children,
            role="tab",
            cls="whitespace-nowrap px-3 py-2 text-sm border-b-2 cursor-pointer flex items-center gap-1.5",
            **{
                "@click": f"{state_var} = '{item.slug}'",
                ":class": f"{state_var} === '{item.slug}' ? 'border-primary text-primary font-medium' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'",
                ":aria-selected": f"{state_var} === '{item.slug}'",
            },
        )

    return _render


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
    default_collapsed: bool = False,
    title_prefix: "FT | None" = None,
    mobile_item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    title_icon: str = "",
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
        title_prefix: Optional element rendered before the title (e.g. back arrow)
        mobile_item_renderer: Custom function to render mobile tab items

    Returns:
        Div containing both desktop sidebar and mobile tabs
    """
    renderer = item_renderer or _default_item_renderer

    # --- Desktop sidebar (hidden below lg:) ---
    sidebar_items = [renderer(item, item.slug == active) for item in items]

    extra_sections = []
    if extra_sidebar_sections:
        extra_sections = [
            Li(cls="border-t border-border my-2"),
            *extra_sidebar_sections,
        ]

    title_el: Any
    if title_icon:
        icon_el = UkIcon(title_icon, height=24, width=24, cls="text-primary")
        if title_href:
            title_el = A(icon_el, href=title_href, aria_label=title)
        else:
            title_el = Div(icon_el, aria_label=title)
    elif title_href:
        title_el = A(
            title,
            href=title_href,
            cls="text-xl font-bold text-primary hover:text-primary/80",
        )
    else:
        title_el = H3(title, cls="text-xl font-bold text-primary")

    # Wrap with prefix (back arrow) if provided
    header_el: Any
    if title_prefix:
        header_el = Div(title_prefix, title_el, cls="flex items-center gap-2")
    else:
        header_el = title_el

    sidebar = Div(
        Div(
            # Toggle button
            Button(
                _chevron_svg(),
                cls="absolute right-2 top-4 w-11 h-11 flex items-center justify-center"
                " rounded-md border border-border bg-background hover:bg-accent"
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
                    header_el,
                    P(subtitle, cls="text-xs opacity-60 mt-1") if subtitle else "",
                    cls="px-4 py-4",
                ),
                Li(cls="border-t border-border my-0"),
                *sidebar_items,
                *extra_sections,
                cls="w-full p-4 transition-opacity duration-300 list-none",
                **{":class": "collapsed ? 'opacity-0 invisible' : 'opacity-100 visible'"},
            ),
            cls="h-full relative overflow-y-auto",
        ),
        cls="hidden lg:block fixed top-16 left-0 bottom-0 w-64 bg-background"
        " border-r border-border z-40 transition-transform duration-300"
        " overflow-hidden",
        **{":class": "collapsed ? '-translate-x-52' : 'translate-x-0'"},
        role="navigation",
        aria_label=f"{title} sidebar",
        hx_get="/api/sidebar/badges",
        hx_trigger="load",
        hx_swap="none",
        **{"x-data": f"collapsibleSidebar('{storage_key}', {str(default_collapsed).lower()})"},
    )

    # --- Mobile tabs (hidden at lg: and above) ---
    tab_items = []
    if mobile_item_renderer:
        for item in items:
            tab_items.append(mobile_item_renderer(item, item.slug == active))
    else:
        for item in items:
            is_active = item.slug == active
            tab_children: list[Any] = []
            if item.icon:
                tab_children.append(UkIcon(item.icon, height=16, width=16, cls="shrink-0", aria_hidden="true"))
            tab_children.append(Span(item.label))
            tab_items.append(
                A(
                    *tab_children,
                    href=item.href,
                    role="tab",
                    cls=f"whitespace-nowrap px-3 py-2 text-sm border-b-2 flex items-center gap-1.5 {'border-primary text-primary font-medium' if is_active else 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'}",
                    **item.hx_attrs,
                )
            )

    mobile_extra = []
    if extra_mobile_sections:
        mobile_extra = list(extra_mobile_sections)

    mobile_tabs = Div(
        Div(
            *tab_items,
            cls="flex overflow-x-auto gap-1 border-b border-border",
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
    default_collapsed: bool = False,
    title_prefix: "FT | None" = None,
    mobile_item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    alpine_state: str = "",
    title_icon: str = "",
) -> "FT":
    """Create a full page with collapsible sidebar navigation.

    Desktop: Fixed sidebar (collapsible) + content area with left margin.
    Mobile: Horizontal tabs above content, no sidebar.

    Args:
        alpine_state: Optional Alpine x-data placed on the wrapper div so sidebar
            and content can share state (e.g. "{ section: 'pending' }").

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
        default_collapsed=default_collapsed,
        title_prefix=title_prefix,
        mobile_item_renderer=mobile_item_renderer,
        title_icon=title_icon,
    )

    collapsed_default = str(default_collapsed).lower()

    # Wrapper attrs — shared Alpine state for sidebar + content communication
    wrapper_attrs: dict[str, Any] = {}
    if alpine_state:
        wrapper_attrs["x-data"] = alpine_state
        wrapper_attrs["x-cloak"] = True

    # Content area with responsive margin
    page_content = Div(
        nav,
        Div(
            Div(
                content,
                cls="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 lg:py-6",
            ),
            cls="lg:ml-64 lg:transition-[margin-left] lg:duration-300 min-h-[calc(100vh-64px)]",
            id="sidebar-content",
            **{
                "x-data": f"collapsibleSidebar('{storage_key}', {collapsed_default})",
                ":class": "collapsed ? 'lg:ml-12' : 'lg:ml-64'",
            },
        ),
        **wrapper_attrs,
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
    "alpine_section_renderer",
    "alpine_mobile_section_renderer",
]
