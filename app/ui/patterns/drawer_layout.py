"""
Drawer Layout Component - CSS-Based Sidebar
=============================================

Reusable drawer layout component using Tailwind's peer-based toggle pattern.
Provides a responsive sidebar visible on desktop and overlay-based on mobile.

Usage:
    from ui.patterns.drawer_layout import DrawerLayout, MenuItem

    menu_items = [
        MenuItem("Overview", "/sel", "overview", "Introduction to SEL"),
        MenuItem("Self Awareness", "/sel/self-awareness", "self-awareness", "Understanding emotions"),
    ]

    layout = DrawerLayout(
        drawer_id="sel-drawer",
        title="SEL Navigation",
        subtitle="Social Emotional Learning",
        menu_items=menu_items,
        active_page="overview",
    )

    page_content = layout.render(main_content)

Benefits:
    - CSS-only toggle (checkbox + Tailwind peer, no JavaScript required)
    - Responsive: sidebar static on lg+, slide-in overlay on mobile
    - Click-outside-to-close via label overlay
    - Smooth slide transition via Tailwind transform

Version: 2.0
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import NotStr


@dataclass
class MenuItem:
    """Menu item for drawer sidebar."""

    title: str
    href: str
    slug: str
    description: str = ""
    icon: str = ""


@dataclass
class DrawerLayout:
    """
    Drawer layout component.

    Args:
        drawer_id: Unique ID for this drawer (for checkbox toggle)
        title: Sidebar header title
        subtitle: Optional sidebar header subtitle
        menu_items: List of MenuItem objects for navigation
        active_page: Slug of the currently active page
        content_id: ID for the main content area (for HTMX targeting)
        sidebar_width: Width class for sidebar (default: w-80)
        show_footer: Whether to show the sidebar footer
        footer_content: Custom footer content (HTML string)
    """

    drawer_id: str
    title: str
    menu_items: list[MenuItem]
    active_page: str = ""
    subtitle: str = ""
    content_id: str = "drawer-content"
    sidebar_width: str = "w-80"
    show_footer: bool = False
    footer_content: str = ""

    def render(self, content: Any) -> NotStr:
        """
        Render the drawer layout with the given main content.

        Args:
            content: Main content to render in the drawer-content area

        Returns:
            Complete drawer layout as NotStr (raw HTML)
        """
        # Build sidebar menu items
        menu_html = self._build_menu_html()

        # Build header HTML
        header_html = self._build_header_html()

        # Build footer HTML
        footer_html = self._build_footer_html() if self.show_footer else ""

        # Drawer HTML — pure Tailwind peer-based sidebar
        drawer_html = f"""
        <div class="relative min-h-screen lg:flex">
            <!-- Mobile toggle checkbox (hidden) -->
            <input id="{self.drawer_id}" type="checkbox" class="hidden peer" />

            <!-- Mobile overlay -->
            <label for="{self.drawer_id}" aria-label="close sidebar"
                   class="fixed inset-0 bg-black/50 z-40 hidden peer-checked:block lg:hidden"></label>

            <!-- Sidebar -->
            <div class="fixed inset-y-0 left-0 z-50 {self.sidebar_width} bg-muted text-foreground
                        transform -translate-x-full peer-checked:translate-x-0
                        transition-transform duration-300
                        lg:translate-x-0 lg:static lg:z-auto
                        overflow-y-auto">
                <div class="p-4">
                    {header_html}

                    <!-- Sidebar Menu -->
                    <ul class="space-y-1">
                        {menu_html}
                    </ul>

                    {footer_html}
                </div>
            </div>

            <!-- Main Content -->
            <div class="flex-1 flex flex-col min-h-screen">
                <!-- Mobile navbar -->
                <div class="flex items-center bg-muted p-2 lg:hidden">
                    <label for="{self.drawer_id}" class="p-2 rounded hover:bg-secondary cursor-pointer">
                        <uk-icon icon="menu" width="24" height="24" class="inline-block w-6 h-6"></uk-icon>
                    </label>
                    <span class="text-xl font-bold ml-2">{self.title}</span>
                </div>

                <!-- Page Content -->
                <div class="flex-1 p-6 lg:p-8 bg-background" id="{self.content_id}">
                    {content}
                </div>
            </div>
        </div>

        <style>
            /* Active menu item styling */
            .drawer-menu-item {{
                padding: 0.75rem 1rem;
                border-radius: 0.5rem;
                cursor: pointer;
                transition: all 0.2s;
                display: block;
                text-decoration: none;
                color: inherit;
            }}

            .drawer-menu-item:hover {{
                background-color: hsl(var(--secondary));
            }}

            .drawer-menu-item.active {{
                background-color: hsl(var(--primary) / 0.1);
                border-left: 3px solid hsl(var(--primary));
                font-weight: 600;
            }}

            .drawer-menu-item .menu-title {{
                font-weight: 600;
                margin-bottom: 0.25rem;
            }}

            .drawer-menu-item .menu-desc {{
                font-size: 0.75rem;
                opacity: 0.7;
                line-height: 1.4;
            }}

            .drawer-menu-item.active .menu-desc {{
                opacity: 0.9;
            }}
        </style>
        """

        return NotStr(drawer_html)

    def _build_menu_html(self) -> str:
        """Build HTML for menu items."""
        menu_items_html = []

        for item in self.menu_items:
            is_active = item.slug == self.active_page
            active_class = "active" if is_active else ""

            icon_html = f'<span class="text-xl mr-2">{item.icon}</span>' if item.icon else ""
            desc_html = (
                f'<div class="menu-desc">{item.description}</div>' if item.description else ""
            )

            menu_items_html.append(f"""
                <li>
                    <a href="{item.href}" class="drawer-menu-item {active_class}">
                        <div class="flex items-center">
                            {icon_html}
                            <div>
                                <div class="menu-title">{item.title}</div>
                                {desc_html}
                            </div>
                        </div>
                    </a>
                </li>
            """)

        return "".join(menu_items_html)

    def _build_header_html(self) -> str:
        """Build HTML for sidebar header."""
        subtitle_html = (
            f'<p class="text-sm text-muted-foreground">{self.subtitle}</p>' if self.subtitle else ""
        )

        return f"""
            <!-- Sidebar Header -->
            <div class="mb-6">
                <h2 class="text-2xl font-bold text-primary mb-1">{self.title}</h2>
                {subtitle_html}
            </div>
        """

    def _build_footer_html(self) -> str:
        """Build HTML for sidebar footer."""
        if self.footer_content:
            return f"""
                <!-- Sidebar Footer -->
                <div class="mt-auto pt-6 border-t border-border">
                    {self.footer_content}
                </div>
            """
        return ""


def create_drawer_layout(
    drawer_id: str,
    title: str,
    menu_items: list[tuple[str, str, str, str]],
    active_page: str,
    content: Any,
    subtitle: str = "",
    show_footer: bool = False,
    footer_content: str = "",
) -> NotStr:
    """
    Convenience function to create a drawer layout.

    Args:
        drawer_id: Unique ID for this drawer
        title: Sidebar header title
        menu_items: List of tuples (title, href, slug, description)
        active_page: Slug of the currently active page
        content: Main content to render
        subtitle: Optional sidebar header subtitle
        show_footer: Whether to show the sidebar footer
        footer_content: Custom footer content (HTML string)

    Returns:
        Complete drawer layout as NotStr (raw HTML)
    """
    items = [MenuItem(title=t, href=h, slug=s, description=d) for t, h, s, d in menu_items]

    layout = DrawerLayout(
        drawer_id=drawer_id,
        title=title,
        menu_items=items,
        active_page=active_page,
        subtitle=subtitle,
        show_footer=show_footer,
        footer_content=footer_content,
    )

    return layout.render(content)


__all__ = ["DrawerLayout", "MenuItem", "create_drawer_layout"]
