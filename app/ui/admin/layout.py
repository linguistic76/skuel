"""Admin Dashboard page layout with sidebar navigation.

Uses similar pattern to Profile Hub but specifically for the admin dashboard
with Users, Analytics, System, and Finance navigation.
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import A, Div, NotStr, Span

from ui.layouts.navbar import create_navbar


@dataclass
class AdminNavItem:
    """Sidebar item for admin navigation."""

    name: str  # "Users", "Analytics", etc.
    slug: str  # "users", "analytics", etc.
    icon: str  # Emoji icon
    href: str  # "/admin/users"
    badge: str | None = None  # Optional badge text
    external: bool = False  # If True, opens in new context (e.g., Finance)


# Default admin navigation items
ADMIN_NAV_ITEMS = [
    AdminNavItem(
        name="Overview",
        slug="overview",
        icon="📊",
        href="/admin",
    ),
    AdminNavItem(
        name="Users",
        slug="users",
        icon="👥",
        href="/admin/users",
    ),
    AdminNavItem(
        name="Analytics",
        slug="analytics",
        icon="📈",
        href="/admin/analytics",
    ),
    AdminNavItem(
        name="Learning",
        slug="learning",
        icon="📚",
        href="/admin/learning",
    ),
    AdminNavItem(
        name="System",
        slug="system",
        icon="⚙️",
        href="/admin/system",
    ),
    AdminNavItem(
        name="Finance",
        slug="finance",
        icon="💰",
        href="/finance",
        badge="→",
        external=True,
    ),
    AdminNavItem(
        name="Ingestion",
        slug="ingestion",
        icon="📥",
        href="/ingest",
        badge="→",
        external=True,
    ),
]


def StatusDot(status: str) -> Span:
    """Status indicator dot for system health."""
    color_classes = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
        "unknown": "bg-base-content/60",
    }
    color_class = color_classes.get(status, "bg-base-content/60")
    return Span(
        cls=f"w-2 h-2 rounded-full {color_class}",
        title=f"Status: {status}",
    )


def AdminSidebarItem(item: AdminNavItem, is_active: bool) -> A:
    """Sidebar navigation item for admin dashboard."""
    base_classes = (
        "flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors group"
    )

    if is_active:
        state_classes = (
            "bg-primary/10 text-primary font-semibold border-l-4 border-primary -ml-1 pl-4"
        )
    else:
        state_classes = "text-base-content/70 hover:text-base-content hover:bg-base-100"

    # Right side content (badge if present)
    right_content = []
    if item.badge:
        right_content.append(
            Span(
                item.badge,
                cls="text-xs font-medium text-base-content/60",
            )
        )

    return A(
        # Left side: icon + name
        Div(
            Span(item.icon, cls="text-lg mr-2"),
            Span(item.name, cls="font-medium"),
            cls="flex items-center",
        ),
        # Right side: badge if any
        Div(*right_content, cls="flex items-center gap-2") if right_content else None,
        href=item.href,
        cls=f"{base_classes} {state_classes}",
        target="_blank" if item.external else None,
    )


@dataclass
class AdminLayout:
    """Admin dashboard layout with sidebar navigation.

    Features:
    - Left sidebar: Admin navigation with icons
    - Center: Main content (overview or section-specific view)
    - Collapsible sidebar on mobile
    - Requires ADMIN role (handled by route decorator)
    """

    title: str
    nav_items: list[AdminNavItem]
    active_section: str = ""  # Empty = overview
    admin_username: str = ""
    system_status: str = "healthy"  # Overall system health

    def render(self, content: Any) -> NotStr:
        """Render the admin layout.

        Args:
            content: Main content (HTML string or component)

        Returns:
            Complete HTML page as NotStr
        """
        content_str = str(content) if not isinstance(content, str) else content

        return NotStr(f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title} - SKUEL Admin</title>

    <!-- Local Tailwind CSS -->
    <link rel="stylesheet" href="/static/css/output.css">

    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap">

    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"></script>

    <style>
        /* Admin Sidebar Styles */
        .admin-container {{
            display: flex;
            min-height: 100vh;
            position: relative;
        }}

        .admin-sidebar {{
            width: 288px;
            background-color: oklch(var(--b2));
            border-right: 1px solid oklch(var(--b3));
            transition: transform 0.3s ease;
            position: fixed;
            top: 64px;
            left: 0;
            bottom: 0;
            z-index: 40;
            transform: translateX(0);
            overflow-y: auto;
        }}

        .admin-sidebar.collapsed {{
            transform: translateX(-240px);
        }}

        .admin-content {{
            flex: 1;
            margin-left: 288px;
            transition: margin-left 0.3s ease;
            min-height: calc(100vh - 64px);
            margin-top: 64px;
        }}

        .admin-content.expanded {{
            margin-left: 48px;
        }}

        .sidebar-toggle {{
            position: absolute;
            right: 8px;
            top: 16px;
            background: oklch(var(--b1));
            border: 1px solid oklch(var(--b3));
            cursor: pointer;
            padding: 8px;
            border-radius: 6px;
            transition: background 0.2s, transform 0.3s;
            z-index: 5;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .sidebar-toggle:hover {{
            background: oklch(var(--b2));
        }}

        .sidebar-toggle svg {{
            transition: transform 0.3s ease;
        }}

        .admin-sidebar.collapsed .sidebar-toggle svg {{
            transform: rotate(180deg);
        }}

        .admin-sidebar.collapsed .sidebar-nav,
        .admin-sidebar.collapsed .sidebar-header-text {{
            opacity: 0;
            visibility: hidden;
        }}

        .sidebar-inner {{
            height: 100%;
            position: relative;
        }}

        .admin-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 30;
            display: none;
        }}

        .admin-overlay.active {{
            display: block;
        }}

        /* Mobile responsiveness */
        @media (max-width: 1024px) {{
            .admin-sidebar {{
                width: 85%;
                max-width: 320px;
                top: 0;
            }}

            .admin-sidebar.collapsed {{
                transform: translateX(-100%);
            }}

            .admin-content {{
                margin-left: 0;
            }}

            .admin-content.expanded {{
                margin-left: 0;
            }}

            .sidebar-toggle {{
                display: none;
            }}

            .mobile-header {{
                display: flex !important;
            }}

            .admin-overlay {{
                top: 0;
            }}
        }}

        @media (min-width: 1025px) {{
            .mobile-header {{
                display: none !important;
            }}
        }}

        /* Nav item hover effects */
        .nav-item {{
            transition: all 0.2s ease;
        }}

        .nav-item:hover {{
            transform: translateX(2px);
        }}

        /* Admin badge styling */
        .admin-badge {{
            background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
            color: white;
            font-size: 0.65rem;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
    </style>
</head>
<body class="bg-base-100 text-base-content">

    <!-- Top Navbar -->
    {create_navbar(current_user=self.admin_username, is_authenticated=True, active_page="admin", is_admin=True)}

    <!-- Mobile Sidebar Toggle -->
    <header class="mobile-header sticky top-0 z-30 bg-base-100 border-b border-base-300 px-4 py-3" style="display: none; margin-top: 64px;">
        <div class="flex items-center gap-3">
            <button
                onclick="toggleAdminSidebar()"
                class="p-2 hover:bg-base-200 rounded-lg"
                aria-label="Toggle admin menu"
            >
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>
                </svg>
            </button>
            <span class="text-sm font-medium text-base-content/70">Admin Navigation</span>
        </div>
    </header>

    <div class="admin-container">
        <!-- Overlay for mobile -->
        <div class="admin-overlay" id="admin-overlay" onclick="toggleAdminSidebar()"></div>

        <!-- Sidebar -->
        <aside class="admin-sidebar" id="admin-sidebar">
            <div class="sidebar-inner">
                <!-- Toggle Button -->
                <button class="sidebar-toggle" onclick="toggleAdminSidebar()" title="Toggle Sidebar">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 18l-6-6 6-6"></path>
                    </svg>
                </button>

                {self._build_navigation()}
            </div>
        </aside>

        <!-- Main Content -->
        <main class="admin-content" id="admin-content">
            <div class="p-6 lg:p-8">
                <div class="max-w-6xl mx-auto">
                    {content_str}
                </div>
            </div>
        </main>
    </div>

    <script>
        let adminSidebarCollapsed = false;

        function toggleAdminSidebar() {{
            const sidebar = document.getElementById('admin-sidebar');
            const content = document.getElementById('admin-content');
            const overlay = document.getElementById('admin-overlay');

            adminSidebarCollapsed = !adminSidebarCollapsed;

            if (adminSidebarCollapsed) {{
                sidebar.classList.add('collapsed');
                content.classList.add('expanded');
                overlay.classList.remove('active');
            }} else {{
                sidebar.classList.remove('collapsed');
                content.classList.remove('expanded');

                // Show overlay on mobile
                if (window.innerWidth <= 1024) {{
                    overlay.classList.add('active');
                }}
            }}

            // Save state to localStorage
            localStorage.setItem('admin-sidebar-collapsed', adminSidebarCollapsed);
        }}

        // Restore saved state on load
        document.addEventListener('DOMContentLoaded', function() {{
            const savedState = localStorage.getItem('admin-sidebar-collapsed');

            // Only apply saved state on desktop
            if (window.innerWidth > 1024 && savedState === 'true') {{
                toggleAdminSidebar();
            }}

            // Always start collapsed on mobile
            if (window.innerWidth <= 1024) {{
                adminSidebarCollapsed = false;
                toggleAdminSidebar();
            }}
        }});

        // Handle window resize
        window.addEventListener('resize', function() {{
            const overlay = document.getElementById('admin-overlay');
            if (window.innerWidth > 1024) {{
                overlay.classList.remove('active');
            }}
        }});
    </script>

</body>
</html>""")

    def _build_navigation(self) -> str:
        """Build the sidebar navigation HTML."""
        # Admin header with badge
        admin_name = self.admin_username or "Admin"
        header = f"""
        <div class="p-4 sidebar-header-text" style="padding-right: 50px;">
            <div class="flex items-center gap-2">
                <span class="text-2xl font-bold text-primary">{admin_name}</span>
                <span class="admin-badge">Admin</span>
            </div>
            <p class="text-sm text-base-content/60 mt-1">Admin Dashboard</p>
        </div>
        """

        # Navigation links
        nav_html = '<div class="sidebar-nav">'

        # Overview link (special first item)
        is_overview_active = self.active_section == "" or self.active_section == "overview"
        overview_item = self.nav_items[0] if self.nav_items else None

        if overview_item and overview_item.slug == "overview":
            nav_html += f"""
            <div class="px-2 mb-2">
                {AdminSidebarItem(overview_item, is_overview_active)!s}
            </div>

            <hr class="border-base-300 mx-4 mb-4">

            <div class="px-4 mb-2">
                <span class="text-xs font-semibold text-base-content/60 uppercase tracking-wider">Admin Sections</span>
            </div>
            """

        # Section links (skip overview)
        nav_html += '<nav class="px-2 space-y-1">'
        for item in self.nav_items:
            if item.slug == "overview":
                continue
            is_active = item.slug == self.active_section
            item_html = str(AdminSidebarItem(item, is_active))
            nav_html += f'<div class="nav-item">{item_html}</div>'
        nav_html += "</nav>"

        # System status indicator at bottom
        status_color = {
            "healthy": "text-success",
            "warning": "text-warning",
            "critical": "text-error",
        }.get(self.system_status, "text-base-content/60")

        nav_html += f"""
        <div class="absolute bottom-4 left-4 right-4">
            <div class="flex items-center gap-2 text-xs text-base-content/60">
                {StatusDot(self.system_status)!s}
                <span>System: <span class="{status_color} font-medium">{self.system_status.capitalize()}</span></span>
            </div>
        </div>
        """

        nav_html += "</div>"

        return header + nav_html


def create_admin_page(
    content: Any,
    active_section: str = "",
    admin_username: str = "",
    title: str = "Admin Dashboard",
    system_status: str = "healthy",
) -> NotStr:
    """Convenience function to create an admin page.

    Args:
        content: Main content HTML
        active_section: Currently active section slug (empty = overview)
        admin_username: Admin's display name for header
        title: Page title
        system_status: Overall system health status

    Returns:
        Complete HTML page
    """
    layout = AdminLayout(
        title=title,
        nav_items=ADMIN_NAV_ITEMS,
        active_section=active_section,
        admin_username=admin_username,
        system_status=system_status,
    )
    return layout.render(content)


__all__ = [
    "ADMIN_NAV_ITEMS",
    "AdminLayout",
    "AdminNavItem",
    "AdminSidebarItem",
    "StatusDot",
    "create_admin_page",
]
