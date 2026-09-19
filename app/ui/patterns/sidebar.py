"""Unified sidebar component — Tailwind + Alpine.js.

Desktop (lg+): a collapsible fixed sidebar with a toggle button.
Below lg: the section nav — a horizontally scrolling list of the same links
above the content, the current page marked ``aria-current="page"`` and
scrolled into the middle of the row before first paint.

One pattern for every sidebar page (Tasks+, Library, Submissions, Teaching,
Explore, Admin, Finance, LifePath, Activity Review).

Usage:
    from ui.patterns.sidebar import SidebarItem, SidebarPage

    items = [
        SidebarItem("Exercises", "/library/exercises", "exercises", icon="book-open"),
        SidebarItem("Resources", "/library/resources", "resources", icon="bookmark"),
    ]

    return SidebarPage(
        content=my_content,
        items=items,
        active="exercises",
        title="Library",
        storage_key="library-sidebar",
        request=request,
        active_page="library",
    )
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, A, Button, Div, Li, Nav, P, Script, Span, Ul

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
    "w-80": ("lg:ml-80", "translate-x-[-308px]"),  # 320-12=308px offset
    "w-96": ("lg:ml-96", "translate-x-[-372px]"),  # 384-12=372px offset
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


# The section nav's one-shot layout enhancement: centre the current page's link
# in the row and stamp the overflow state the CSS fade reads. Inline and
# parse-time (it runs as soon as the row above it exists, before the deferred
# Alpine bundle) so the row never paints scrolled to 0 and then jumps. With JS
# off the row is a plain scrolling list. `scrollLeft` is set directly —
# `scrollIntoView` would scroll the page too.
_SECTION_NAV_SCRIPT = """
(function () {
  var nav = document.currentScript.previousElementSibling;
  var row = nav.querySelector('ul');
  var current = row.querySelector('[aria-current="page"]');
  function stamp() {
    nav.toggleAttribute('data-overflow', row.scrollWidth > row.clientWidth);
    nav.toggleAttribute('data-at-end', row.scrollLeft + row.clientWidth >= row.scrollWidth - 1);
  }
  if (current) {
    var left = current.getBoundingClientRect().left - row.getBoundingClientRect().left;
    row.scrollLeft = left - (row.clientWidth - current.offsetWidth) / 2;
  }
  stamp();
  row.addEventListener('scroll', stamp, { passive: true });
  window.addEventListener('resize', stamp, { passive: true });
})();
"""


def _chevron_svg() -> FT:
    """Collapse toggle chevron icon."""
    return Icon("chevron-left", size=16, cls="")


def _default_item_renderer(item: SidebarItem, is_active: bool) -> FT:
    """Default sidebar item renderer."""
    active_cls = "bg-accent font-semibold" if is_active else ""
    current_attrs: dict[str, str] = {"aria_current": "page"} if is_active else {}
    children: list[Any] = []

    if item.icon:
        children.append(Icon(item.icon, size=18, cls="shrink-0"))

    children.append(Span(item.label, cls="flex-1"))

    if item.description:
        # Two-line item (Askesis style)
        content = Div(
            Div(
                (Icon(item.icon, size=18, cls="mr-2 shrink-0") if item.icon else ""),
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
                **current_attrs,
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
            **current_attrs,
            **item.hx_attrs,
        )
    )


def SidebarLink(text: str, href: str) -> FT:
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

    def _render(item: SidebarItem, _is_active: bool) -> FT:
        children: list[Any] = []
        if item.icon:
            children.append(Icon(item.icon, size=18, cls="shrink-0"))
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
    """Section-nav item renderer for Alpine-driven section switching.

    Returns a list item whose tab-shaped element switches the section with
    @click instead of navigating.
    """

    def _render(item: SidebarItem, _is_active: bool) -> FT:
        tab_children: list[Any] = []
        if item.icon:
            tab_children.append(Icon(item.icon, size=16, cls="shrink-0"))
        tab_children.append(Span(item.label))
        if item.badge_text:
            tab_children.append(Span(item.badge_text, cls="ml-1 text-xs"))

        return Li(
            Div(
                *tab_children,
                role="tab",
                cls="whitespace-nowrap px-3 py-2.5 min-h-[44px] text-sm border-b-2 cursor-pointer flex items-center gap-1.5",
                **{
                    "@click": f"{state_var} = '{item.slug}'",
                    ":class": f"{state_var} === '{item.slug}' ? 'border-primary text-primary font-medium' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'",
                    ":aria-selected": f"{state_var} === '{item.slug}'",
                },
            ),
            cls="shrink-0",
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
    title_prefix: FT | None = None,
    mobile_item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    title_icon: str = "",
    sidebar_width: str = "w-64",
) -> FT:
    """Build the desktop sidebar + the below-lg section nav.

    Args:
        items: Navigation items
        active: Currently active item slug
        title: Sidebar heading
        subtitle: Optional subtitle below heading
        storage_key: localStorage key for collapse state
        extra_sidebar_sections: Additional content appended to desktop sidebar
        extra_mobile_sections: Additional content below the section nav
        item_renderer: Custom function to render sidebar items
        title_href: Optional link for the title heading
        title_prefix: Optional element rendered before the title (e.g. back arrow)
        mobile_item_renderer: Custom function to render section-nav items;
            it must return an ``<li>`` (the row is a list)

    Returns:
        Div containing both the desktop sidebar and the section nav
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

    sidebar = Nav(
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
        aria_label=f"{title} sidebar",
        # The async badge loader: OOB-swapped count/health badges on the domain rows.
        hx_get="/api/sidebar/badges",
        hx_trigger="load",
        hx_swap="none",
        **{"x-data": f"collapsibleSidebar('{storage_key}', {str(default_collapsed).lower()})"},
    )

    # --- Section nav (hidden at lg: and above) ---
    # A nav of page links, not a tabs widget: these links navigate between
    # pages, so the current one is marked aria-current, never aria-selected.
    # role="list" restores the list semantics that `list-none` strips in
    # VoiceOver; shrink-0 keeps every item whole so the ROW overflows, never
    # the page.
    section_items: list[Any] = []
    if mobile_item_renderer:
        section_items = [mobile_item_renderer(item, item.slug == active) for item in items]
    else:
        for item in items:
            is_active = item.slug == active
            link_children: list[Any] = []
            if item.icon:
                link_children.append(Icon(item.icon, size=16, cls="shrink-0"))
            link_children.append(Span(item.label))
            section_items.append(
                Li(
                    A(
                        *link_children,
                        href=item.href,
                        cls=f"whitespace-nowrap px-3 py-2.5 min-h-[44px] text-sm border-b-2 flex items-center gap-1.5 {'border-primary text-primary font-medium' if is_active else 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'}",
                        **({"aria_current": "page"} if is_active else {}),
                        **item.hx_attrs,
                    ),
                    cls="shrink-0",
                )
            )

    section_nav: list[Any] = []
    if section_items:
        section_nav.append(
            Nav(
                Ul(
                    *section_items,
                    role="list",
                    cls="flex overflow-x-auto gap-1 border-b border-border list-none m-0 p-0",
                ),
                aria_label=title,
            )
        )
        # The centring script reads live geometry, so it is scoped to the
        # default row: a custom renderer's row may sit inside an `x-cloak`
        # wrapper, where the row has no size until Alpine boots.
        if not mobile_item_renderer:
            section_nav.append(Script(_SECTION_NAV_SCRIPT))

    mobile_extra = list(extra_mobile_sections) if extra_mobile_sections else []

    # No items and nothing extra → no empty bordered strip.
    mobile_tabs: Any = ""
    if section_nav or mobile_extra:
        mobile_tabs = Div(*section_nav, *mobile_extra, cls="section-nav lg:hidden mb-4")

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
    request: Request | None = None,
    active_page: str = "",
    item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    title_href: str = "",
    default_collapsed: bool = False,
    title_prefix: FT | None = None,
    mobile_item_renderer: Callable[[SidebarItem, bool], Any] | None = None,
    alpine_state: str = "",
    title_icon: str = "",
    sidebar_width: str = "w-64",
    extra_css: list[str] | None = None,
    extra_scripts: list[str] | None = None,
    content_max_width: str = "max-w-6xl",
) -> FT:
    """Create a full page with collapsible sidebar navigation.

    Desktop: Fixed sidebar (collapsible) + content area with left margin.
    Below lg: the section nav above the content, no sidebar.

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
                ":class": "collapsed ? 'lg:ml-12!' : ''",
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
