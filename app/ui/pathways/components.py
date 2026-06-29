"""Pathways UI components — cards, filters, and step renderers."""

from typing import Any

from fasthtml.common import (
    H3,
    H4,
    Div,
    Option,
    P,
    Span,
)
from monsterui.franken import CardContainer as Card

from core.models.pathways.pathways_request import LearningPathFilterRequest
from ui.components import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.forms import LabelSelect
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.form_generator import FormGenerator
from ui.primitives import ButtonLink
from ui.ui_types import ActivePathData


def difficulty_label(rating: float) -> str:
    """Convert 0.0-1.0 difficulty rating to human-readable label."""
    if rating <= 0.35:
        return "beginner"
    if rating <= 0.65:
        return "intermediate"
    return "advanced"


def path_to_display_dict(path: Any) -> dict[str, Any]:
    """Convert a LearningPath domain model to a display dict for browser cards."""
    return {
        "uid": path.uid,
        "title": path.title or "Untitled Path",
        "description": path.description or "",
        "difficulty": difficulty_label(path.difficulty_rating),
        "estimated_hours": int(path.estimated_hours or 0),
        "tags": list(path.tags) if path.tags else [],
    }


def render_step_browser_card(step: Any) -> Any:
    """Render a path step as a browseable card using CardGenerator."""

    def render_difficulty(value: float) -> Any:
        if not value:
            return None
        return Badge(difficulty_label(value).title(), variant=BadgeT.primary, size=Size.sm)

    def render_hours(value: float) -> Any:
        if not value:
            return None
        return Badge(f"{value:.1f}h", variant=BadgeT.secondary, size=Size.sm)

    def render_sequence(value: int) -> Any:
        if not value:
            return None
        return Badge(f"Step {value}", variant=BadgeT.info, size=Size.sm)

    def render_description(value: str) -> Any:
        text = value or getattr(step, "intent", "") or ""
        if not text:
            return None
        return P(text[:200], cls="text-muted-foreground text-sm")

    return CardGenerator.from_dataclass(
        step,
        display_fields=["description", "difficulty_rating", "estimated_hours", "sequence"],
        show_labels=False,
        title_href=f"/explore/ps/{step.uid}",
        field_renderers={
            "description": render_description,
            "difficulty_rating": render_difficulty,
            "estimated_hours": render_hours,
            "sequence": render_sequence,
        },
    )


class PathwaysUIComponents:
    """Reusable component library for pathway browsing interface."""

    @staticmethod
    def render_filter_form() -> Any:
        """Learning path filter form using FormGenerator with custom select widgets."""
        return FormGenerator.from_model(
            LearningPathFilterRequest,
            action="/api/pathways/filter-paths",
            method="POST",
            include_fields=["difficulty", "domain", "duration"],
            custom_widgets={
                "difficulty": LabelSelect(
                    Option("All Levels", value="all", selected=True),
                    Option("Beginner", value="beginner"),
                    Option("Intermediate", value="intermediate"),
                    Option("Advanced", value="advanced"),
                    label="Difficulty Level",
                    name="difficulty",
                ),
                "domain": LabelSelect(
                    Option("All Domains", value="all", selected=True),
                    Option("Programming", value="programming"),
                    Option("Data Science", value="data_science"),
                    Option("Web Development", value="web_dev"),
                    Option("Cloud Computing", value="cloud"),
                    label="Domain",
                    name="domain",
                ),
                "duration": LabelSelect(
                    Option("Any Duration", value="all", selected=True),
                    Option("Under 20 hours", value="short"),
                    Option("20-50 hours", value="medium"),
                    Option("50+ hours", value="long"),
                    label="Time Commitment",
                    name="duration",
                ),
            },
            form_attrs={
                "cls": "space-y-4",
                "hx_post": "/api/pathways/filter-paths",
                "hx_target": "#learning-paths-grid",
            },
            submit_label="Apply Filters",
        )

    @staticmethod
    def render_learning_path_card(path: ActivePathData) -> Any:
        """Create a learning path card for the dashboard."""
        return Card(
            Div(
                # Path Header
                Div(
                    H3(path.title, cls="text-lg font-semibold"),
                    Badge(path.difficulty.title(), variant=BadgeT.primary),
                    cls="flex justify-between items-start mb-2",
                ),
                # Progress Bar
                Div(
                    Div(f"{path.progress:.1f}% Complete", cls="text-sm text-muted-foreground mb-1"),
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full transition-all",
                            style=f"width: {path.progress}%",
                        ),
                        cls="w-full bg-secondary rounded-full h-2",
                    ),
                    cls="mb-3",
                ),
                # Current Step & Time
                Div(
                    P(f"Current: {path.current_step}", cls="text-sm text-foreground/80"),
                    P(f"{path.time_invested} invested", cls="text-xs text-muted-foreground"),
                    P(
                        f"{path.estimated_completion} to complete",
                        cls="text-xs text-muted-foreground",
                    ),
                    cls="space-y-1 mb-4",
                ),
                # Action Button
                ButtonLink(
                    "Continue Learning",
                    href=f"/pathways/path/{path.uid}",
                    cls=(ButtonT.primary, "w-full"),
                    size="sm",
                ),
                cls="p-4",
            ),
            cls="hover:shadow-lg transition-shadow",
        )

    @staticmethod
    def render_learning_path_browser_card(path: dict[str, Any]) -> Any:
        """Create a learning path card for the browse page using CardGenerator."""

        def render_difficulty(value: str) -> Any:
            return Badge(value.title(), variant=BadgeT.primary)

        def render_hours(value: int) -> Any:
            return Span(f"{value}h", cls="text-sm text-muted-foreground")

        def render_tags(value: list) -> Any:
            if not value:
                return None
            return Div(
                *[Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in value[:3]],
                cls="flex flex-wrap gap-1",
            )

        action_buttons = Div(
            ButtonLink(
                "View Details",
                href=f"/pathways/path/{path['uid']}",
                cls=(ButtonT.secondary, "flex-1"),
                size="sm",
            ),
            Button(
                "Enroll",
                cls=(ButtonT.primary, "flex-1"),
                size="sm",
                hx_post=f"/api/pathways/enroll/{path['uid']}",
                hx_target="#main-content",
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            path,
            display_fields=["description", "estimated_hours", "difficulty", "tags"],
            show_labels=False,
            field_renderers={
                "difficulty": render_difficulty,
                "estimated_hours": render_hours,
                "tags": render_tags,
            },
            actions=action_buttons,
            card_attrs={"cls": "hover:shadow-lg transition-shadow h-full p-4"},
        )

    @staticmethod
    def render_step_item(step: Any, index: int, is_mastered: bool) -> Any:
        """Render a single path step in a path's curriculum list."""
        mastery_badge = (
            Badge("Mastered", variant=BadgeT.success, size=Size.sm)
            if is_mastered
            else Badge("Not started", variant=BadgeT.outline, size=Size.sm)
        )
        diff = difficulty_label(step.difficulty_rating) if step.difficulty_rating else ""
        difficulty_badge = (
            Badge(diff.title(), variant=BadgeT.primary, size=Size.sm) if diff else None
        )
        hours_text = f"{step.estimated_hours:.0f}h" if step.estimated_hours else ""

        return Div(
            Div(
                # Sequence number
                Badge(f"Step {index}", variant=BadgeT.primary, cls="mr-2"),
                # Title
                H4(step.title or f"Step {index}", cls="text-lg font-semibold flex-1"),
                # Mastery status
                mastery_badge,
                cls="flex items-center justify-between mb-2",
            ),
            Div(
                P(
                    step.description or step.intent or "",
                    cls="text-muted-foreground mb-2",
                ),
                Div(
                    Span(hours_text, cls="text-sm text-muted-foreground mr-3")
                    if hours_text
                    else None,
                    difficulty_badge,
                    cls="flex items-center gap-2",
                ),
                cls="ml-8",
            ),
            cls="border border-border rounded-lg p-4 hover:bg-background transition-colors",
        )
