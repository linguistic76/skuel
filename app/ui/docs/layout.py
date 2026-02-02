"""Documentation layout using raw Tailwind CSS.

This replaces the DaisyUI-based docs_layout.py with a layout built
on our typography-first design system.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    NotStr,
)

from ui.docs.components import DocsSection
from ui.layouts.navbar import create_navbar, create_navbar_for_request

if TYPE_CHECKING:
    from starlette.requests import Request

# Default worldview sections
WORLDVIEW_SECTIONS = [
    DocsSection("stories", "Stories", "", "Foundational narratives and wisdom traditions"),
    DocsSection("environment", "Environment", "", "Sustainability, weather, and cycles of life"),
    DocsSection("intelligence", "Intelligence", "", "Education and learning"),
    DocsSection("investment", "Investment", "", "Long-term thinking and growth"),
    DocsSection("words", "Words & Meaning", "", "Language, thinking, and communication"),
    DocsSection("self-awareness", "Self Awareness", "", "Psyche, emotions, and behavior"),
    DocsSection("life", "Life", "", "Growth, relationships, and purpose"),
]


@dataclass
class DocsLayout:
    """Documentation layout with sidebar navigation.

    Features:
    - Left sidebar: Navigation (collapsible on mobile)
    - Center: Main content with prose styling
    - Right: Optional table of contents (desktop only)
    """

    title: str
    sections: list[DocsSection]
    active_section: str = ""
    active_topic: str = ""
    show_toc: bool = False
    toc_html: str = ""
    base_path: str = "/docs"  # Base path for navigation links (/docs or /nous)
    request: "Request | None" = None  # Request for automatic auth detection

    def render(self, content: Any) -> NotStr:
        """Render the documentation layout.

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
    <title>{self.title} - SKUEL Docs</title>

    <!-- Local Tailwind CSS -->
    <link rel="stylesheet" href="/static/css/output.css">

    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap">

    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"></script>

    <!-- Documentation styles -->
    <link rel="stylesheet" href="/static/css/docs.css">

    <style>
        /* Collapsible Sidebar Styles */
        .docs-container {{
            display: flex;
            min-height: 100vh;
            position: relative;
        }}

        .docs-sidebar {{
            width: 256px;
            background-color: oklch(var(--color-base-200));
            border-right: 1px solid oklch(var(--color-base-300));
            transition: transform 0.3s ease;
            position: fixed;
            top: 64px;
            left: 0;
            bottom: 0;
            z-index: 40;
            transform: translateX(0);
            overflow-y: auto;
        }}

        .docs-sidebar.collapsed {{
            transform: translateX(-208px);
        }}

        .docs-content {{
            flex: 1;
            margin-left: 256px;
            transition: margin-left 0.3s ease;
            min-height: calc(100vh - 64px);
            margin-top: 64px;
        }}

        .docs-content.expanded {{
            margin-left: 48px;
        }}

        .sidebar-toggle {{
            position: absolute;
            right: 8px;
            top: 16px;
            background: oklch(var(--color-base-100));
            border: 1px solid oklch(var(--color-base-300));
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
            background: oklch(var(--color-base-200));
        }}

        .sidebar-toggle svg {{
            transition: transform 0.3s ease;
        }}

        .docs-sidebar.collapsed .sidebar-toggle svg {{
            transform: rotate(180deg);
        }}

        .docs-sidebar.collapsed .sidebar-nav,
        .docs-sidebar.collapsed .sidebar-header-text {{
            opacity: 0;
            visibility: hidden;
        }}

        .sidebar-inner {{
            height: 100%;
            position: relative;
        }}

        .docs-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 30;
            display: none;
        }}

        .docs-overlay.active {{
            display: block;
        }}

        /* Mobile responsiveness */
        @media (max-width: 1024px) {{
            .docs-sidebar {{
                width: 85%;
                max-width: 320px;
                top: 0;
            }}

            .docs-sidebar.collapsed {{
                transform: translateX(-100%);
            }}

            .docs-content {{
                margin-left: 0;
            }}

            .docs-content.expanded {{
                margin-left: 0;
            }}

            .sidebar-toggle {{
                display: none;
            }}

            .mobile-header {{
                display: flex !important;
            }}

            .docs-overlay {{
                top: 0;
            }}
        }}

        @media (min-width: 1025px) {{
            .mobile-header {{
                display: none !important;
            }}
        }}
    </style>
</head>
<body class="bg-base-100 text-base-content">

    <!-- Top Navbar -->
    {create_navbar_for_request(self.request, active_page="docs") if self.request else create_navbar(active_page="docs")}

    <!-- Mobile Sidebar Toggle -->
    <header class="mobile-header sticky top-0 z-30 bg-base-100 border-b border-base-300 px-4 py-3" style="display: none; margin-top: 64px;">
        <div class="flex items-center gap-3">
            <button
                onclick="toggleDocsSidebar()"
                class="p-2 hover:bg-base-200 rounded-lg"
                aria-label="Toggle docs menu"
            >
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>
                </svg>
            </button>
            <span class="text-sm font-medium text-base-content/70">Docs Navigation</span>
        </div>
    </header>

    <div class="docs-container">
        <!-- Overlay for mobile -->
        <div class="docs-overlay" id="docs-overlay" onclick="toggleDocsSidebar()"></div>

        <!-- Sidebar -->
        <aside class="docs-sidebar" id="docs-sidebar">
            <div class="sidebar-inner">
                <!-- Toggle Button -->
                <button class="sidebar-toggle" onclick="toggleDocsSidebar()" title="Toggle Sidebar">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 18l-6-6 6-6"></path>
                    </svg>
                </button>

                {self._build_navigation()}
            </div>
        </aside>

        <!-- Main Content -->
        <main class="docs-content" id="docs-content">
            <div class="p-6 lg:p-8">
                <div class="flex gap-8 max-w-6xl mx-auto">
                    <!-- Content Column -->
                    <article class="flex-1 min-w-0">
                        {content_str}
                    </article>

                    <!-- TOC Sidebar (desktop only) -->
                    {self._build_toc()}
                </div>
            </div>
        </main>
    </div>

    <script>
        let docsSidebarCollapsed = false;

        function toggleDocsSidebar() {{
            const sidebar = document.getElementById('docs-sidebar');
            const content = document.getElementById('docs-content');
            const overlay = document.getElementById('docs-overlay');

            docsSidebarCollapsed = !docsSidebarCollapsed;

            if (docsSidebarCollapsed) {{
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
            localStorage.setItem('docs-sidebar-collapsed', docsSidebarCollapsed);
        }}

        // Restore saved state on load
        document.addEventListener('DOMContentLoaded', function() {{
            const savedState = localStorage.getItem('docs-sidebar-collapsed');

            // Only apply saved state on desktop
            if (window.innerWidth > 1024 && savedState === 'true') {{
                toggleDocsSidebar();
            }}

            // Always start collapsed on mobile
            if (window.innerWidth <= 1024) {{
                docsSidebarCollapsed = false;
                toggleDocsSidebar();
            }}
        }});

        // Handle window resize
        window.addEventListener('resize', function() {{
            const overlay = document.getElementById('docs-overlay');
            if (window.innerWidth > 1024) {{
                overlay.classList.remove('active');
            }}
        }});
    </script>

</body>
</html>""")

    def _build_navigation(self) -> str:
        """Build the sidebar navigation HTML."""
        # Determine title based on base path
        nav_title = "SKUEL Nous" if self.base_path == "/nous" else "SKUEL Docs"
        nav_subtitle = (
            "Worldview & Philosophy" if self.base_path == "/nous" else "Worldview Documentation"
        )

        # Header - needs sidebar-header-text class for fade on collapse
        header = f"""
        <div class="p-4 sidebar-header-text" style="padding-right: 50px;">
            <a href="{self.base_path}" class="text-2xl font-bold text-primary hover:text-primary-focus">
                {nav_title}
            </a>
            <p class="text-sm text-base-content/60 mt-1">{nav_subtitle}</p>
        </div>
        """

        # Section links wrapped in sidebar-nav for fade on collapse
        sections_html = '<div class="sidebar-nav">'

        sections_html += '<nav class="px-2">'
        for section in self.sections:
            is_active = section.slug == self.active_section
            active_cls = (
                "bg-primary/10 text-primary font-semibold"
                if is_active
                else "text-base-content/70 hover:text-base-content hover:bg-base-100"
            )
            icon = f'<span class="mr-2">{section.icon}</span>' if section.icon else ""

            sections_html += f"""
            <a href="{self.base_path}/{section.slug}"
               class="flex items-center px-3 py-2 rounded-lg transition-colors {active_cls}">
                {icon}{section.title}
            </a>
            """
        sections_html += "</nav>"
        sections_html += "</div>"

        return header + sections_html

    def _build_toc(self) -> str:
        """Build the table of contents sidebar."""
        if not self.show_toc or not self.toc_html:
            return ""

        return f"""
        <aside class="hidden xl:block w-64 flex-shrink-0">
            <div class="sticky top-8">
                <h4 class="text-sm font-semibold text-base-content/60 mb-4 uppercase tracking-wide">On this page</h4>
                <nav class="text-sm space-y-2">
                    {self.toc_html}
                </nav>
            </div>
        </aside>
        """


def create_docs_page(
    title: str,
    content: Any,
    active_section: str = "",
    active_topic: str = "",
    sections: list[DocsSection] | None = None,
    toc_html: str = "",
    base_path: str = "/docs",
    request: "Request | None" = None,
) -> NotStr:
    """Convenience function to create a documentation page.

    Args:
        title: Page title
        content: Main content HTML
        active_section: Currently active section slug
        active_topic: Currently active topic slug
        sections: Navigation sections (defaults to WORLDVIEW_SECTIONS)
        toc_html: Optional table of contents HTML
        base_path: Base URL path ("/docs" or "/nous")
        request: Request object for automatic auth detection (recommended)

    Returns:
        Complete HTML page
    """
    layout = DocsLayout(
        title=title,
        sections=sections or WORLDVIEW_SECTIONS,
        active_section=active_section,
        active_topic=active_topic,
        show_toc=bool(toc_html),
        toc_html=toc_html,
        base_path=base_path,
        request=request,
    )
    return layout.render(content)
