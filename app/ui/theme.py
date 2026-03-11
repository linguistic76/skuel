"""
SKUEL Theme Configuration
=========================

Centralized theme headers for SKUEL PWA using DaisyUI components.
SKUEL-native configuration for frontend dependencies.

Usage:
    from ui.theme import daisy_headers, Theme

    # In bootstrap.py
    app, rt = fast_app(hdrs=daisy_headers())

    # Or with custom theme
    app, rt = fast_app(hdrs=daisy_headers(theme=Theme.dark))

Design Principles:
- One Path Forward: Single place to configure all frontend dependencies
- CDN-first: Use CDN for DaisyUI/Tailwind, self-host Alpine.js for stability
- Version-pinned: All dependency versions explicitly set
- Progressive Enhancement: Core functionality works without JS

January 2026: Initial implementation for SKUEL PWA migration
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import Link, Meta, Script


class Theme(StrEnum):
    """
    DaisyUI theme options.

    These map to DaisyUI's built-in themes.
    Set via data-theme attribute on html element.
    """

    light = "light"
    dark = "dark"
    cupcake = "cupcake"
    bumblebee = "bumblebee"
    emerald = "emerald"
    corporate = "corporate"
    synthwave = "synthwave"
    retro = "retro"
    cyberpunk = "cyberpunk"
    valentine = "valentine"
    halloween = "halloween"
    garden = "garden"
    forest = "forest"
    aqua = "aqua"
    lofi = "lofi"
    pastel = "pastel"
    fantasy = "fantasy"
    wireframe = "wireframe"
    black = "black"
    luxury = "luxury"
    dracula = "dracula"
    cmyk = "cmyk"
    autumn = "autumn"
    business = "business"
    acid = "acid"
    lemonade = "lemonade"
    night = "night"
    coffee = "coffee"
    winter = "winter"
    dim = "dim"
    nord = "nord"
    sunset = "sunset"


# Version constants - update these when upgrading dependencies
DAISYUI_VERSION = "5"  # Major version for CDN
HTMX_VERSION = "1.9.10"
ALPINE_VERSION = "3.14.8"


def daisy_headers(
    htmx_version: str = HTMX_VERSION,
    alpine_version: str = ALPINE_VERSION,
    theme: Theme = Theme.light,
    include_icons: bool = True,
    include_fonts: bool = True,
) -> tuple[Any, ...]:
    """
    Generate SKUEL application headers with DaisyUI + Tailwind + HTMX + Alpine.

    Args:
        htmx_version: HTMX version to use
        alpine_version: Alpine.js version (must match self-hosted file)
        theme: DaisyUI theme to use
        include_icons: If True, includes Lucide icons
        include_fonts: If True, includes Inter font

    Returns:
        Tuple of header elements for FastHTML fast_app()

    Example:
        from fasthtml.common import fast_app
        from ui.theme import daisy_headers

        app, rt = fast_app(hdrs=daisy_headers(theme=Theme.dark))
    """
    headers = [
        # Meta tags
        Meta(charset="UTF-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
        # Theme configuration (set default theme)
        Script(f"document.documentElement.setAttribute('data-theme', '{theme.value}')"),
    ]

    # Fonts
    if include_fonts:
        headers.extend(
            [
                Link(rel="preconnect", href="https://fonts.googleapis.com"),
                Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
                Link(
                    rel="stylesheet",
                    href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
                ),
            ]
        )

    # Core CSS/JS (order matters!)
    headers.extend(
        [
            # DaisyUI + Tailwind CSS (CDN version includes both)
            Link(
                href=f"https://cdn.jsdelivr.net/npm/daisyui@{DAISYUI_VERSION}/dist/full.min.css",
                rel="stylesheet",
                type="text/css",
            ),
            # Tailwind CSS (via CDN for development)
            Script(src="https://cdn.tailwindcss.com"),
            # HTMX for hypermedia
            Script(src=f"https://unpkg.com/htmx.org@{htmx_version}"),
        ]
    )

    # Icons
    if include_icons:
        headers.append(
            Script(src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"),
        )

    # Alpine.js (self-hosted for stability)
    headers.append(
        Script(src=f"/static/vendor/alpinejs/alpine.{alpine_version}.min.js", defer=True),
    )

    # SKUEL custom CSS and JS
    headers.extend(
        [
            Link(rel="stylesheet", href="/static/css/main.css"),
            Script(src="/static/js/skuel.js"),
        ]
    )

    # Icon initialization (if icons included)
    if include_icons:
        headers.append(
            Script("document.addEventListener('DOMContentLoaded', () => lucide.createIcons());"),
        )

    return tuple(headers)


def pwa_headers(
    app_name: str = "SKUEL",
    theme_color: str = "#570df8",
    _background_color: str = "#ffffff",
) -> tuple[Any, ...]:
    """
    Generate PWA-specific headers for SKUEL.

    Args:
        app_name: Application name for manifest
        theme_color: Theme color for browser chrome
        _background_color: Background color for splash screen (reserved for future manifest.json generation)

    Returns:
        Tuple of PWA-related header elements

    Example:
        app, rt = fast_app(hdrs=(*daisy_headers(), *pwa_headers()))
    """
    return (
        # PWA Meta tags
        Meta(name="application-name", content=app_name),
        Meta(name="apple-mobile-web-app-capable", content="yes"),
        Meta(name="apple-mobile-web-app-status-bar-style", content="default"),
        Meta(name="apple-mobile-web-app-title", content=app_name),
        Meta(name="mobile-web-app-capable", content="yes"),
        Meta(name="theme-color", content=theme_color),
        # PWA Manifest
        Link(rel="manifest", href="/manifest.json"),
        # Apple touch icons
        Link(rel="apple-touch-icon", href="/static/icons/icon-192x192.png"),
        # Favicon
        Link(rel="icon", type="image/png", sizes="32x32", href="/static/icons/favicon-32x32.png"),
        Link(rel="icon", type="image/png", sizes="16x16", href="/static/icons/favicon-16x16.png"),
    )


def dark_mode_script() -> Script:
    """
    Generate dark mode toggle script.

    Returns JavaScript that handles theme switching based on user preference.
    Respects system preference and stores user choice in localStorage.

    Usage:
        app, rt = fast_app(hdrs=(*daisy_headers(), dark_mode_script()))
    """
    return Script("""
        // Dark mode handler
        (function() {
            const THEME_KEY = 'skuel-theme';

            function getPreferredTheme() {
                const stored = localStorage.getItem(THEME_KEY);
                if (stored) return stored;
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }

            function setTheme(theme) {
                document.documentElement.setAttribute('data-theme', theme);
                localStorage.setItem(THEME_KEY, theme);
            }

            // Set initial theme
            setTheme(getPreferredTheme());

            // Listen for system preference changes
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (!localStorage.getItem(THEME_KEY)) {
                    setTheme(e.matches ? 'dark' : 'light');
                }
            });

            // Expose toggle function globally
            window.toggleTheme = function() {
                const current = document.documentElement.getAttribute('data-theme');
                setTheme(current === 'dark' ? 'light' : 'dark');
            };
        })();
    """)


def htmx_extensions() -> tuple[Any, ...]:
    """
    HTMX extensions commonly used in SKUEL.

    Returns:
        Tuple of Script elements for HTMX extensions
    """
    return (
        # SSE extension for real-time updates
        Script(src="https://unpkg.com/htmx.org/dist/ext/sse.js"),
        # WebSocket extension
        Script(src="https://unpkg.com/htmx.org/dist/ext/ws.js"),
        # Response targets extension
        Script(src="https://unpkg.com/htmx.org/dist/ext/response-targets.js"),
    )


def chartjs_headers() -> tuple[Any, ...]:
    """
    Chart.js headers for analytics dashboards.

    Returns:
        Tuple of Script elements for Chart.js
    """
    return (
        Script(src="https://cdn.jsdelivr.net/npm/chart.js@4"),
        # Date adapter for time scales
        Script(src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"),
    )


__all__ = [
    "Theme",
    "daisy_headers",
    "pwa_headers",
    "dark_mode_script",
    "htmx_extensions",
    "chartjs_headers",
    "DAISYUI_VERSION",
    "HTMX_VERSION",
    "ALPINE_VERSION",
]
