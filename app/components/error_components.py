"""
Error Components - Consolidated error rendering for UI routes
===============================================================

Provides consistent error banner rendering across all UI routes.

Usage:
    from components.error_components import ErrorComponents

    # In UI routes
    return ErrorComponents.render_error_banner("User not found")

Created: January 2026
Pattern: Consolidated from 6 UI route files (tasks, goals, habits, events, choices, principles)
"""

from fasthtml.common import P

from ui.daisy_components import Div


class ErrorComponents:
    """Consolidated error rendering components for UI routes."""

    @staticmethod
    def render_error_banner(message: str) -> Div:
        """
        Render error banner for UI failures.

        Args:
            message: Error message to display

        Returns:
            Div: Error banner with red alert styling
        """
        return Div(
            Div(
                P("⚠️ Error", cls="font-bold text-error"),
                P(message, cls="text-sm"),
                cls="alert alert-error",
            ),
            cls="mb-4",
        )
