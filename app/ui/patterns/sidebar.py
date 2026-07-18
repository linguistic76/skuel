"""Unified sidebar component — Tailwind + Alpine.js.

Desktop: Collapsible fixed sidebar with toggle button.
Mobile: Horizontal tabs at top of content area.

One pattern for all sidebar pages (Profile, KU, Submissions, Journals, Askesis).

Usage:
    from ui.patterns.sidebar import SidebarItem, SidebarPage

    items = [
        SidebarItem("Submit", "/submit", "submit", icon="..."),
        SidebarItem("Browse", "/profile?tab=reports", "browse", icon="..."),
    ]

    return SidebarPage(
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

from ui.components import Icon
from ui.feedback import Badge, BadgeT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

# Sidebar width → (margin class, collapse translate).
# w-64=256px, w-80=320px, w-96=384px. Collapse leaves 12px (w-12) visible.
_SIDEBAR_WIDTH_CONFIG: dict[str, tuple[str, str]] = {
    "w-64": ("lg:ml-64", "-translate-x-52"),  # 256-48=208px offset
    "w-80": ("lg:ml-80", "-translate-x-[308px]"),  # 320-12=308px offset
    "w-96": ("lg:ml-96", "-translate-x-[372px]"),  # 384-12=372px offset
}
_SIDEBAR_MARGIN_MAP: dict[str, str] = {k: v[0] for k, v in _SIDEBAR_WIDTH_CONFIG.items()}


@dataclass
class SidebarItem:
    """Single navigation item for sidebar and mobile tabs."""

    label: str
    href: str
    slug: str
    icon: str = ""
    description: str = ""
    badge_text: str = ""
    hx_attrs: dict[str, str] = field(default_factory=dict)
    children: list["SidebarItem"] = field(default_factory=list)


def _chevron_svg() -> "FT":
    """Collapse toggle chevron icon."""
    return Icon("chevron-left", size=16, cls="", aria_hidden="true")


def _render_accordion_item(item: SidebarItem, is_active: bool) -> "FT":
    """Render a sidebar item as an accordion with expandable children."""
    active_cls = "bg-accent font-semibold" if is_active else ""
    header_children: list[Any] = []

    if item.icon:
        header_children.append(Icon(item.icon, size=18, cls="shrink-0", aria_hidden="true"))

    header_children.append(Span(item.label, cls="flex-1"))

    if item.badge_text:
        header_children.append(Badge(item.badge_text, variant=BadgeT.neutral))

    # Chevron that rotates when expanded
    header_children.append(
        Icon(
            "chevron-down",
            size=14,
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
        children.append(Icon(item.icon, size=18, cls="shrink-0", aria_hidden="true"))

    children.append(Span(item.label, cls="flex-1"))

    if item.description:
        # Two-line item (Askesis style)
        content = Div(
            Div(
                (
                    Icon(item.icon, size=18, cls="mr-2 shrink-0", aria_hidden="true")
                    if item.icon
                    else ""
                ),
                Span(item.label, cls="font-medium"),
                cls="flex items-center",
            ),
            (
                P(item.description, cls="text-xs opacity-60 mt-0.5 ml-7")
                if item.icon
                else P(item.description, cls="text-xs opacity-60 mt-0.5")
            ),
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
        children.append(Badge(item.badge_text, variant=BadgeT.neutral))

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


def alpine_section_renderer(
    state_var: str = "section",
) -> Callable[[SidebarItem, bool], Any]:
    """Item renderer for Alpine-driven section switching (no page navigation).

    Items use @click to set Alpine state variable instead of href links.
    The `slug` field on each SidebarItem maps to the section value.
    """

    def _render(item: SidebarItem, _is_active: bool) -> "FT":
        children: list[Any] = []
        if item.icon:
            children.append(Icon(item.icon, size=18, cls="shrink-0", aria_hidden="true"))
        children.append(Span(item.label, cls="flex-1"))
        if item.badge_text:
            children.append(Badge(item.badge_text, variant=BadgeT.primary))

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
            tab_children.append(Icon(item.icon, size=16, cls="shrink-0", aria_hidden="true"))
        tab_children.append(Span(item.label))
        if item.badge_text:
            tab_children.append(Span(item.badge_text, cls="ml-1 text-xs"))

        return Div(
            *tab_children,
            role="tab",
            cls="whitespace-nowrap px-3 py-2.5 min-h-[44px] text-sm border-b-2 cursor-pointer flex items-center gap-1.5",
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
    sidebar_width: str = "w-64",
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
    _margin_cls, collapse_translate = _SIDEBAR_WIDTH_CONFIG.get(
        sidebar_width, ("lg:ml-64", "-translate-x-52")
    )

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
        icon_el = Icon(title_icon, size=24, cls="text-primary")
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
        cls=f"hidden lg:block fixed top-16 left-0 bottom-0 {sidebar_width} bg-background"
        " border-r border-border z-40 transition-transform duration-300"
        " overflow-hidden",
        **{":class": f"collapsed ? '{collapse_translate}' : 'translate-x-0'"},
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
                tab_children.append(Icon(item.icon, size=16, cls="shrink-0", aria_hidden="true"))
            tab_children.append(Span(item.label))
            tab_items.append(
                A(
                    *tab_children,
                    href=item.href,
                    role="tab",
                    cls=f"whitespace-nowrap px-3 py-2.5 min-h-[44px] text-sm border-b-2 flex items-center gap-1.5 {'border-primary text-primary font-medium' if is_active else 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'}",
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


def SidebarPage(
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
    sidebar_width: str = "w-64",
    extra_css: list[str] | None = None,
    extra_scripts: list[str] | None = None,
    content_max_width: str = "max-w-6xl",
) -> "FT":
    """Create a full page with collapsible sidebar navigation.

    Desktop: Fixed sidebar (collapsible) + content area with left margin.
    Mobile: Horizontal tabs above content, no sidebar.

    Args:
        alpine_state: Optional Alpine x-data placed on the wrapper div so sidebar
            and content can share state (e.g. "{ section: 'pending' }").
        content_max_width: Tailwind max-width class for the content column.
            Pass "max-w-none" for fluid pages (e.g. calendar grids) that should
            fill the space freed when the sidebar collapses.

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
        sidebar_width=sidebar_width,
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
                cls=f"{content_max_width} mx-auto px-4 sm:px-6 lg:px-8 py-4 lg:py-6",
            ),
            cls=f"{_SIDEBAR_MARGIN_MAP.get(sidebar_width, 'lg:ml-64')} lg:transition-[margin-left] lg:duration-300 min-h-[calc(100vh-64px)]",
            id="sidebar-content",
            **{
                "x-data": f"collapsibleSidebar('{storage_key}', {collapsed_default})",
                # !important variant: Alpine's :class can't REMOVE the static
                # margin class, and lg:ml-64 sorts after lg:ml-12 in the
                # compiled CSS — without the ! the collapsed margin never wins
                # and content never reflows into the freed space.
                ":class": "collapsed ? 'lg:!ml-12' : ''",
            },
        ),
        **wrapper_attrs,
    )

    return BasePage(
        content=page_content,
        title=page_title or title,
        page_type=PageType.CUSTOM,
        request=request,
        active_page=active_page,
        extra_css=extra_css,
        extra_scripts=extra_scripts,
    )


__all__ = [
    "SidebarItem",
    "SidebarNav",
    "SidebarPage",
    "alpine_section_renderer",
    "alpine_mobile_section_renderer",
]
