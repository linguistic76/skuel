"""
SKUEL Theme Configuration
=========================

Centralized theme headers for SKUEL using MonsterUI (FrankenUI + Tailwind).
SKUEL-native configuration for frontend dependencies.

Usage:
    from ui.theme import monster_headers

    # In bootstrap.py
    app, rt = fast_app(hdrs=monster_headers())

Design Principles:
- One Path Forward: MonsterUI for all UI components
- Leverage Maintained Software: FastHTML team maintains MonsterUI
- Progressive Enhancement: Core functionality works without JS
"""

from typing import Any

from fasthtml.common import Link, Script
from monsterui.core import Theme as MonsterTheme

# Re-export MonsterUI Theme for direct access
Theme = MonsterTheme

# Version constants for self-hosted dependencies
HTMX_VERSION = "1.9.10"
ALPINE_VERSION = "3.14.8"


def monster_headers(
    theme: MonsterTheme = MonsterTheme.blue,
    htmx_version: str = HTMX_VERSION,
    alpine_version: str = ALPINE_VERSION,
) -> tuple[Any, ...]:
    """
    Generate SKUEL application headers with MonsterUI + HTMX + Alpine.

    Args:
        theme: MonsterUI theme to use (default: blue)
        htmx_version: HTMX version to use
        alpine_version: Alpine.js version (must match self-hosted file)

    Returns:
        Tuple of header elements for FastHTML fast_app()

    Example:
        from fasthtml.common import fast_app
        from ui.theme import monster_headers

        app, rt = fast_app(hdrs=monster_headers())
    """
    # MonsterUI theme headers (includes FrankenUI + Tailwind + Lucide icons)
    mu_headers = theme.headers()

    headers = list(mu_headers)

    # HTMX for hypermedia (MonsterUI doesn't include this)
    headers.append(Script(src=f"https://unpkg.com/htmx.org@{htmx_version}"))

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

    return tuple(headers)


def pwa_headers(
    app_name: str = "SKUEL",
    theme_color: str = "#2563eb",
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
    """
    from fasthtml.common import Meta

    return (
        Meta(name="application-name", content=app_name),
        Meta(name="apple-mobile-web-app-capable", content="yes"),
        Meta(name="apple-mobile-web-app-status-bar-style", content="default"),
        Meta(name="apple-mobile-web-app-title", content=app_name),
        Meta(name="mobile-web-app-capable", content="yes"),
        Meta(name="theme-color", content=theme_color),
        Link(rel="manifest", href="/manifest.json"),
        Link(rel="apple-touch-icon", href="/static/icons/icon-192x192.png"),
        Link(rel="icon", type="image/png", sizes="32x32", href="/static/icons/favicon-32x32.png"),
        Link(rel="icon", type="image/png", sizes="16x16", href="/static/icons/favicon-16x16.png"),
    )


def dark_mode_script() -> Script:
    """
    Generate dark mode toggle script for MonsterUI theme system.

    MonsterUI uses class-based dark mode (Tailwind's 'dark' class on html element).
    """
    return Script("""
        (function() {
            const THEME_KEY = 'skuel-theme';

            function getPreferredTheme() {
                const stored = localStorage.getItem(THEME_KEY);
                if (stored) return stored;
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }

            function setTheme(theme) {
                if (theme === 'dark') {
                    document.documentElement.classList.add('dark');
                } else {
                    document.documentElement.classList.remove('dark');
                }
                localStorage.setItem(THEME_KEY, theme);
            }

            setTheme(getPreferredTheme());

            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (!localStorage.getItem(THEME_KEY)) {
                    setTheme(e.matches ? 'dark' : 'light');
                }
            });

            window.toggleTheme = function() {
                const isDark = document.documentElement.classList.contains('dark');
                setTheme(isDark ? 'light' : 'dark');
            };
        })();
    """)


def htmx_extensions() -> tuple[Any, ...]:
    """HTMX extensions commonly used in SKUEL."""
    return (
        Script(src="https://unpkg.com/htmx.org/dist/ext/sse.js"),
        Script(src="https://unpkg.com/htmx.org/dist/ext/ws.js"),
        Script(src="https://unpkg.com/htmx.org/dist/ext/response-targets.js"),
    )


def chartjs_headers() -> tuple[Any, ...]:
    """Chart.js headers for analytics dashboards."""
    return (
        Script(src="https://cdn.jsdelivr.net/npm/chart.js@4"),
        Script(src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"),
    )


__all__ = [
    "Theme",
    "monster_headers",
    "pwa_headers",
    "dark_mode_script",
    "htmx_extensions",
    "chartjs_headers",
    "HTMX_VERSION",
    "ALPINE_VERSION",
]
