"""
Exercise List & Card Components
================================

Pure rendering functions for exercise list and card views.
"""

from typing import Any

from fasthtml.common import Div, P, Span
from monsterui.franken import Button, ButtonT
from monsterui.franken import CardContainer as Card

from ui.feedback import Badge, BadgeT
from ui.patterns.card_generator import CardGenerator


def render_exercises_list(exercises: Any) -> Any:
    """List of exercises."""
    if not exercises:
        return Card(
            P(
                "No exercises yet. Create your first exercise to get started!",
                cls="text-muted-foreground text-center py-8",
            ),
            cls="mb-4",
        )

    return Div(*[render_exercise_card(e) for e in exercises], cls="space-y-4")


def render_exercise_card(exercise: Any) -> Any:
    """Single exercise card using CardGenerator."""

    def render_model_badge(value: str) -> Any:
        return Badge(value, variant=BadgeT.info)

    def render_context_notes(value: list) -> Any:
        if not value:
            return None
        return Span(
            f"{len(value)} context notes",
            cls="text-sm text-muted-foreground",
        )

    action_buttons = Div(
        Button(
            "Edit",
            hx_get=f"/exercises/{exercise.uid}/edit",
            hx_target="#main-content",
            cls=(ButtonT.ghost, ButtonT.sm),
        ),
        Button(
            "View Instructions",
            hx_get=f"/exercises/{exercise.uid}/view",
            hx_target="#main-content",
            cls=(ButtonT.ghost, ButtonT.sm),
        ),
        Button(
            "Delete",
            hx_delete=f"/api/exercises/{exercise.uid}",
            hx_confirm="Are you sure you want to delete this exercise?",
            hx_target="closest .card",
            hx_swap="outerHTML",
            cls=(ButtonT.destructive, ButtonT.sm),
        ),
        cls="flex gap-2",
    )

    return CardGenerator.from_dataclass(
        exercise,
        display_fields=["instructions", "model", "context_notes"],
        show_labels=False,
        field_renderers={
            "model": render_model_badge,
            "context_notes": render_context_notes,
        },
        actions=action_buttons,
        card_attrs={"cls": "mb-4 p-4"},
    )
