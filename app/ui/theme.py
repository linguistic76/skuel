"""
SKUEL Theme Configuration
=========================

Pure SKUEL headers built on pre-compiled Tailwind CLI (output.css),
self-hosted Lucide icons, HTMX, and Alpine.js.

Usage:
    from ui.theme import skuel_headers

    # In bootstrap.py
    app, rt = fast_app(hdrs=(*skuel_headers(), *chartjs_headers()))
"""

from typing import Any

from fasthtml.common import Link, Script

# Version constants for self-hosted dependencies
HTMX_VERSION = "1.9.10"
ALPINE_VERSION = "3.14.8"
CHARTJS_VERSION = "4"
CHARTJS_ADAPTER_VERSION = "3"


def skuel_headers(
    htmx_version: str = HTMX_VERSION,
    alpine_version: str = ALPINE_VERSION,
) -> tuple[Any, ...]:
    """Pure SKUEL headers — no UIkit/MonsterUI.

    Loads pre-compiled output.css (Tailwind CLI), self-hosted HTMX,
    Alpine.js, SKUEL's custom CSS, and SKUEL's Alpine component JS.
    Icons are server-rendered inline SVG (no lucide runtime).

    Example:
        from fasthtml.common import fast_app
        from ui.theme import skuel_headers, chartjs_headers

        app, rt = fast_app(hdrs=(*skuel_headers(), *chartjs_headers()))
    """
    return (
        Link(rel="stylesheet", href="/static/css/output.css"),
        # Icons are server-rendered inline SVG (ui/components/icon.py) — no lucide runtime.
        # HTMX (self-hosted — avoids cross-site CSRF cookie rejection in Firefox)
        Script(src=f"/static/vendor/htmx.org/htmx.{htmx_version}.min.js"),
        # Alpine.js (self-hosted for stability)
        Script(src=f"/static/vendor/alpinejs/alpine.{alpine_version}.min.js", defer=True),
        Link(rel="stylesheet", href="/static/css/main.css"),
        Script(src="/static/js/skuel.js"),
    )


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
    """Dark mode toggle script — class-based (Tailwind 'dark' on html element)."""
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
        Script(src="/static/vendor/htmx.org/ext/sse.js"),
        Script(src="/static/vendor/htmx.org/ext/ws.js"),
        Script(src="/static/vendor/htmx.org/ext/response-targets.js"),
    )


def chartjs_headers() -> tuple[Any, ...]:
    """Chart.js headers for analytics dashboards."""
    return (
        Script(src="/static/vendor/chart.js/chart.umd.js"),
        Script(
            src=f"/static/vendor/chart.js/chartjs-adapter-date-fns.{CHARTJS_ADAPTER_VERSION}.min.js"
        ),
    )


__all__ = [
    "skuel_headers",
    "pwa_headers",
    "dark_mode_script",
    "htmx_extensions",
    "chartjs_headers",
    "HTMX_VERSION",
    "ALPINE_VERSION",
    "CHARTJS_VERSION",
    "CHARTJS_ADAPTER_VERSION",
]
