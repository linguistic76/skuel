"""
Drawer Layout Component - DaisyUI-Based Sidebar
================================================

Reusable drawer layout component using DaisyUI's CSS-only drawer pattern.
Provides a responsive sidebar that is open on desktop (lg:drawer-open) and
overlay-based on mobile.

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

Benefits over custom CSS/JS:
    - CSS-only toggle (checkbox-based, no JavaScript required for basic function)
    - Built-in responsive: lg:drawer-open shows sidebar on desktop, overlay on mobile
    - Built-in overlay: drawer-overlay handles click-to-close
    - DaisyUI themes automatically apply
    - ~90 lines vs ~280 lines of custom CSS/JS

Version: 1.0
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
    DaisyUI Drawer layout component.

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

        # DaisyUI Drawer HTML
        drawer_html = f"""
        <div class="drawer lg:drawer-open">
            <!-- Drawer Toggle (Hidden checkbox) -->
            <input id="{self.drawer_id}" type="checkbox" class="drawer-toggle" />

            <!-- Main Content -->
            <div class="drawer-content flex flex-col" id="{self.content_id}">
                <!-- Navbar for mobile (shows hamburger menu) -->
                <div class="navbar bg-muted lg:hidden">
                    <div class="flex-none">
                        <label for="{self.drawer_id}" class="btn btn-square btn-ghost drawer-button">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="inline-block w-6 h-6 stroke-current">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>
                            </svg>
                        </label>
                    </div>
                    <div class="flex-1">
                        <span class="text-xl font-bold">{self.title}</span>
                    </div>
                </div>

                <!-- Page Content -->
                <div class="flex-1 p-6 lg:p-8 bg-background">
                    {content}
                </div>
            </div>

            <!-- Sidebar -->
            <div class="drawer-side">
                <label for="{self.drawer_id}" aria-label="close sidebar" class="drawer-overlay"></label>
                <div class="menu p-4 {self.sidebar_width} min-h-full bg-muted text-foreground">
                    {header_html}

                    <!-- Sidebar Menu -->
                    <ul class="menu space-y-1">
                        {menu_html}
                    </ul>

                    {footer_html}
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
                background-color: hsl(var(--b3));
            }}

            .drawer-menu-item.active {{
                background-color: hsl(var(--p) / 0.1);
                border-left: 3px solid hsl(var(--p));
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

            /* Smooth transitions */
            .drawer-content {{
                transition: margin-left 0.3s ease;
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
