"""
CardGenerator - Dynamic Display Card Generation from Dataclasses
=================================================================

Generates DaisyUI display cards automatically from dataclass introspection.

Following the 100% dynamic architecture vision:
- Models define structure → UI auto-generates
- Add field to dataclass → Display auto-updates
- No manual display composition needed

Usage:
    from core.models.task.task import Task
    from ui.patterns.card_generator import CardGenerator

    # Auto-generate display card from domain model
    card = CardGenerator.from_dataclass(
        task,
        display_fields=['title', 'description', 'priority', 'status', 'due_date']
    )

Version: 1.0.0
"""

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, get_args, get_origin

from fasthtml.common import H3, Div, Li, P, Span, Ul

from core.utils.logging import get_logger
from ui.forms import Label

logger = get_logger("skuel.components.card_generator")


class FieldRendererMapper:
    """
    Maps dataclass field types to display renderers.

    Uses introspection to determine the appropriate UI rendering
    based on field type and value.
    """

    @staticmethod
    def get_default_renderer(_field_name: str, field_type: type, value: Any) -> Callable:
        """
        Determine default renderer from field type introspection.

        Returns a function that renders the value as a DaisyUI component.
        """
        # Handle None values
        if value is None:
            return FieldRendererMapper._render_none

        # Get origin type (handles Optional, List, etc.)
        origin = get_origin(field_type)
        if origin is not None and (origin is type(None) or str(origin) == "typing.Union"):
            # Handle Optional[T] → extract T
            args = get_args(field_type)
            if args:
                field_type = (
                    args[0] if args[0] is not type(None) else (args[1] if len(args) > 1 else str)
                )

        # Enum → display value with badge
        if isinstance(value, Enum):
            return FieldRendererMapper._render_enum

        # List → render as list items
        if origin is list or isinstance(value, list):
            return FieldRendererMapper._render_list

        # Tuple → render as list items
        if origin is tuple or isinstance(value, tuple):
            return FieldRendererMapper._render_list

        # Dict → render as key-value pairs
        if origin is dict or isinstance(value, dict):
            return FieldRendererMapper._render_dict

        # Date → format nicely
        if isinstance(value, date) and not isinstance(value, datetime):
            return FieldRendererMapper._render_date

        # DateTime → format with time
        if isinstance(value, datetime):
            return FieldRendererMapper._render_datetime

        # Boolean → render as badge
        if isinstance(value, bool):
            return FieldRendererMapper._render_boolean

        # Integer/Float → render with formatting
        if isinstance(value, int | float):
            return FieldRendererMapper._render_number

        # String → render as text (with truncation if long)
        if isinstance(value, str):
            return FieldRendererMapper._render_string

        # Fallback → string representation
        return FieldRendererMapper._render_fallback

    @staticmethod
    def _render_enum(value: Enum) -> Span:
        """Render enum value as a badge"""
        from ui.badge_classes import status_badge_class

        # Type is known to be Enum, use .value directly (per CLAUDE.md Oct 5 update)
        display = str(value.value)

        # Match on lowercase value/name
        key = str(display).lower().replace(" ", "_")
        badge_cls = status_badge_class(key)

        return Span(str(display), cls=f"badge {badge_cls}")

    @staticmethod
    def _render_list(value: list) -> Div:
        """Render list as bullet points"""
        if not value:
            return Span("—", cls="text-muted-foreground italic")

        items = [Li(str(item), cls="text-sm") for item in value]
        return Ul(*items, cls="list-disc list-inside text-foreground/80")

    @staticmethod
    def _render_dict(value: dict) -> Div:
        """Render dict as key-value pairs"""
        if not value:
            return Span("—", cls="text-muted-foreground italic")

        items = [
            Div(
                Span(f"{k}:", cls="font-semibold text-muted-foreground mr-2"),
                Span(str(v), cls="text-foreground/80"),
                cls="flex gap-2",
            )
            for k, v in value.items()
        ]
        return Div(*items, cls="space-y-1")

    @staticmethod
    def _render_date(value: date) -> Span:
        """Render date in readable format"""
        formatted = value.strftime("%B %d, %Y")  # e.g., "October 03, 2025"
        return Span(formatted, cls="text-foreground/80")

    @staticmethod
    def _render_datetime(value: datetime) -> Span:
        """Render datetime with time"""
        formatted = value.strftime("%B %d, %Y at %I:%M %p")  # e.g., "October 03, 2025 at 02:30 PM"
        return Span(formatted, cls="text-foreground/80")

    @staticmethod
    def _render_boolean(value: bool) -> Span:
        """Render boolean as badge"""
        if value:
            return Span("✓ Yes", cls="badge badge-success")
        else:
            return Span("✗ No", cls="badge badge-ghost")

    @staticmethod
    def _render_number(value: float) -> Span:
        """Render number with formatting"""
        if isinstance(value, int):
            return Span(str(value), cls="text-foreground/80 font-mono")
        else:
            # Format float to 2 decimal places
            return Span(f"{value:.2f}", cls="text-foreground/80 font-mono")

    @staticmethod
    def _render_none(_value: Any) -> Span:
        """Render None value as placeholder"""
        return Span("—", cls="text-muted-foreground italic")

    @staticmethod
    def _render_fallback(value: Any) -> P:
        """Render unknown type as string"""
        return P(str(value), cls="text-foreground/80")

    @staticmethod
    def _render_string(value: str) -> P:
        """Render string with truncation if too long"""
        if len(value) > 200:
            # Truncate long strings
            return P(
                value[:200] + "...",
                cls="text-foreground/80 text-sm",
                title=value,  # Full text on hover
            )
        return P(value, cls="text-foreground/80")

    @staticmethod
    def get_field_label(field_name: str) -> str:
        """
        Generate user-friendly label from field name.

        Examples:
        - task_title → Task Title
        - due_date → Due Date
        - estimated_hours → Estimated Hours
        """
        return " ".join(word.capitalize() for word in field_name.split("_"))


class CardGenerator:
    """
    Dynamic display card generator using dataclass introspection.

    Follows 100% dynamic architecture:
    - Introspects dataclass fields via fields()
    - Determines renderers via type annotations
    - Generates DaisyUI components
    """

    @staticmethod
    def from_dataclass(
        instance: Any,
        display_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
        field_order: list[str] | None = None,
        field_renderers: dict[str, Callable] | None = None,
        field_labels: dict[str, str] | None = None,
        title_field: str | None = None,
        card_attrs: dict[str, Any] | None = None,
        show_empty_fields: bool = False,
    ) -> Div:
        """
        Generate display card from dataclass introspection.

        Args:
            instance: Dataclass instance to display,
            display_fields: Only display these fields (None = all),
            exclude_fields: Exclude these fields (default: uid, created_at, updated_at),
            field_order: Custom field ordering,
            field_renderers: Custom renderers for specific fields,
            field_labels: Custom labels for specific fields,
            title_field: Field to use as card title (default: 'title' or 'name'),
            card_attrs: Additional card attributes (cls, id, etc.),
            show_empty_fields: Show fields even if value is None/empty

        Returns:
            DaisyUI Card component

        Example:
            def render_priority(v):
                return Span(v, cls="badge badge-warning")

            card = CardGenerator.from_dataclass(
                task,
                display_fields=['title', 'description', 'priority', 'status'],
                field_renderers={
                    'priority': render_priority
                }
            )
        """
        if not is_dataclass(instance):
            raise ValueError(f"Instance must be a dataclass, got {type(instance)}")

        logger.info(f"Generating card from {type(instance).__name__}")

        # Get dataclass fields via introspection
        all_fields = fields(instance)
        field_dict = {f.name: f for f in all_fields}

        # Determine which fields to display
        field_names = list(field_dict.keys())

        # Default exclusions
        default_exclude = ["uid", "created_at", "updated_at"]
        if exclude_fields is None:
            exclude_fields = default_exclude
        else:
            exclude_fields = list(set(exclude_fields) | set(default_exclude))

        if display_fields:
            field_names = [f for f in field_names if f in display_fields]

        if exclude_fields:
            field_names = [f for f in field_names if f not in exclude_fields]

        # Apply custom ordering
        if field_order:
            ordered_fields = [f for f in field_order if f in field_names]
            remaining_fields = [f for f in field_names if f not in field_order]
            field_names = ordered_fields + remaining_fields

        # Determine title field
        if title_field is None:
            # Auto-detect title field
            if "title" in field_dict:
                title_field = "title"
            elif "name" in field_dict:
                title_field = "name"

        # Build card components
        card_components = []

        # Add title if detected
        if title_field and title_field in field_dict:
            title_value = getattr(instance, title_field)
            if title_value:
                card_components.append(H3(str(title_value), cls="text-lg font-bold mb-4"))
                # Remove title from fields list (already displayed)
                if title_field in field_names:
                    field_names.remove(title_field)

        # Generate field displays
        field_renderers = field_renderers or {}
        field_labels = field_labels or {}

        for field_name in field_names:
            field_info = field_dict[field_name]
            value = getattr(instance, field_name)

            # Skip empty fields if not showing them
            if not show_empty_fields and (
                value is None or (isinstance(value, list | tuple | dict) and not value)
            ):
                continue

            # Get label
            label = field_labels.get(field_name) or FieldRendererMapper.get_field_label(field_name)

            # Get renderer
            if field_name in field_renderers:
                renderer = field_renderers[field_name]
            else:
                renderer = FieldRendererMapper.get_default_renderer(
                    field_name, field_info.type, value
                )

            # Render field
            field_component = Div(
                Label(label, cls="label-text font-semibold text-muted-foreground block mb-1"),
                renderer(value),
                cls="mb-3",
            )

            card_components.append(field_component)

        # Build card attributes
        attrs = {"cls": "card bg-background shadow-md p-6"}
        if card_attrs:
            attrs.update(card_attrs)

        # Return generated card
        card = Div(*card_components, **attrs)

        logger.info(f"✅ Generated card with {len(card_components)} components")
        return card

    @staticmethod
    def from_list(
        instances: list[Any],
        display_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
        field_renderers: dict[str, Callable] | None = None,
        title_field: str | None = None,
        list_attrs: dict[str, Any] | None = None,
    ) -> Div:
        """
        Generate a list of display cards from multiple instances.

        Args:
            instances: List of dataclass instances,
            display_fields: Only display these fields,
            exclude_fields: Exclude these fields,
            field_renderers: Custom renderers for specific fields,
            title_field: Field to use as card title,
            list_attrs: Additional container attributes

        Returns:
            Div containing multiple cards

        Example:
            cards = CardGenerator.from_list(
                tasks,
                display_fields=['title', 'priority', 'status', 'due_date']
            )
        """
        logger.info(f"Generating card list with {len(instances)} items")

        cards = [
            CardGenerator.from_dataclass(
                instance,
                display_fields=display_fields,
                exclude_fields=exclude_fields,
                field_renderers=field_renderers,
                title_field=title_field,
            )
            for instance in instances
        ]

        attrs = {"cls": "space-y-4"}
        if list_attrs:
            attrs.update(list_attrs)

        return Div(*cards, **attrs)

    @staticmethod
    def compact_card(
        instance: Any, display_fields: list[str], title_field: str | None = None
    ) -> Div:
        """
        Generate a compact card (minimal styling, fewer details).

        Useful for list views where you want less detail per item.

        Example:
            card = CardGenerator.compact_card(
                task,
                display_fields=['title', 'priority', 'status']
            )
        """
        return CardGenerator.from_dataclass(
            instance,
            display_fields=display_fields,
            title_field=title_field,
            card_attrs={
                "cls": "card bg-background border border-border p-3 hover:shadow-md transition-shadow"
            },
        )

    @staticmethod
    def detailed_card(instance: Any, exclude_fields: list[str] | None = None) -> Div:
        """
        Generate a detailed card (shows all non-excluded fields).

        Useful for detail views where you want complete information.

        Example:
            card = CardGenerator.detailed_card(
                task,
                exclude_fields=['uid', 'created_at']
            )
        """
        return CardGenerator.from_dataclass(
            instance,
            exclude_fields=exclude_fields,
            show_empty_fields=True,
            card_attrs={"cls": "card bg-background shadow-xl p-8"},
        )


class CardGeneratorExamples:
    """
    Example usage patterns for CardGenerator.

    Demonstrates various use cases and customization options.
    """

    @staticmethod
    def basic_card_example(task) -> Any:
        """Most basic usage - just pass the instance"""
        return CardGenerator.from_dataclass(task)

    @staticmethod
    def selective_fields_example(task) -> Any:
        """Show only specific fields"""
        return CardGenerator.from_dataclass(
            task, display_fields=["title", "description", "priority", "status", "due_date"]
        )

    @staticmethod
    def custom_renderers_example(task) -> Any:
        """Override specific field renderers"""

        def render_priority(v) -> Any:
            bolts = "⚡" * (3 if v.value == "high" else 2 if v.value == "medium" else 1)
            return Span(f"{bolts} {v.value}", cls="badge badge-warning")

        def render_due_date(v) -> Any:
            return Span(f"📅 {v.strftime('%b %d')}", cls="text-info font-semibold")

        return CardGenerator.from_dataclass(
            task,
            display_fields=["title", "priority", "status", "due_date"],
            field_renderers={"priority": render_priority, "due_date": render_due_date},
        )

    @staticmethod
    def list_view_example(tasks) -> Any:
        """Generate list of compact cards"""
        return CardGenerator.from_list(
            tasks, display_fields=["title", "priority", "status", "due_date"]
        )

    @staticmethod
    def htmx_card_example(task) -> Any:
        """Card with HTMX actions"""
        return CardGenerator.from_dataclass(
            task,
            display_fields=["title", "description", "priority", "status"],
            card_attrs={
                "id": f"task-{task.uid}",
                "hx_get": f"/api/tasks/{task.uid}",
                "hx_trigger": "click",
                "hx_target": "#detail-panel",
                "cls": "card bg-background shadow-md p-6 cursor-pointer hover:shadow-xl transition-shadow",
            },
        )


# Export main classes
__all__ = ["CardGenerator", "CardGeneratorExamples", "FieldRendererMapper"]
