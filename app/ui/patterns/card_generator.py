"""
CardGenerator - Dynamic Display Card Generation
=================================================

Generates display cards automatically from dataclass or dict introspection.

Following the 100% dynamic architecture vision:
- Models define structure → UI auto-generates
- Add field to dataclass → Display auto-updates
- No manual display composition needed

THE single card component for all SKUEL UI contexts.

Supports detail cards (labeled fields), list cards (compact, unlabeled),
teaching rows (subtitle + badges + extra), and insight cards.

Usage:
    from ui.patterns.card_generator import CardGenerator

    # Detail card from dataclass
    card = CardGenerator.from_dataclass(
        task,
        display_fields=['title', 'description', 'priority', 'status'],
    )

    # List card with badges and metadata
    card = CardGenerator.from_dataclass(
        {"title": goal.title, "description": goal.description},
        display_fields=["description"],
        show_labels=False,
        header_badges=[StatusBadge("active"), PriorityBadge("high")],
        metadata=[progress_component, "Due: 2026-04-01"],
        actions=Div(Button("View"), Button("Edit")),
    )

    # Teaching row card
    card = CardGenerator.from_dataclass(
        item,
        display_fields=[],
        subtitle="by Student Name",
        header_badges=[feedback_badge, status_badge],
        actions=ButtonLink("Review", href="/review/123"),
        extra=feedback_toggle,
    )
"""

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, get_args, get_origin

from fasthtml.common import H3, A, Div, Li, P, Span, Ul

from core.utils.logging import get_logger
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.forms import Label
from ui.layout import FlexItem, Row
from ui.text import SmallText

logger = get_logger("skuel.components.card_generator")


class _DictFieldInfo:
    """Synthetic field info for dict entries, matching dataclass field interface."""

    __slots__ = ("name", "type")

    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.type = type(value) if value is not None else str


class FieldRendererMapper:
    """
    Maps field types to display renderers.

    Uses introspection to determine the appropriate UI rendering
    based on field type and value.
    """

    @staticmethod
    def get_default_renderer(_field_name: str, field_type: type, value: Any) -> Callable:
        """
        Determine default renderer from field type introspection.

        Returns a function that renders the value as a UI component.
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
        from ui.enum_helpers import get_status_badge_class

        display = str(value.value)
        key = str(display).lower().replace(" ", "_")
        badge_cls = get_status_badge_class(key)

        return Badge(str(display), variant=None, cls=badge_cls)

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
        formatted = value.strftime("%B %d, %Y")
        return Span(formatted, cls="text-foreground/80")

    @staticmethod
    def _render_datetime(value: datetime) -> Span:
        """Render datetime with time"""
        formatted = value.strftime("%B %d, %Y at %I:%M %p")
        return Span(formatted, cls="text-foreground/80")

    @staticmethod
    def _render_boolean(value: bool) -> Span:
        """Render boolean as badge"""
        if value:
            return Badge("✓ Yes", variant=BadgeT.success)
        else:
            return Badge("✗ No", variant=BadgeT.ghost)

    @staticmethod
    def _render_number(value: float) -> Span:
        """Render number with formatting"""
        if isinstance(value, int):
            return Span(str(value), cls="text-foreground/80 font-mono")
        else:
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
            return P(
                value[:200] + "...",
                cls="text-foreground/80 text-sm",
                title=value,
            )
        return P(value, cls="text-foreground/80")

    @staticmethod
    def get_field_label(field_name: str) -> str:
        """Generate user-friendly label from field name."""
        return " ".join(word.capitalize() for word in field_name.split("_"))


def _get_value(instance: Any, field_name: str) -> Any:
    """Get a field value from a dataclass or dict."""
    if isinstance(instance, dict):
        return instance.get(field_name)
    return getattr(instance, field_name)


def _build_field_dict(instance: Any) -> dict[str, Any]:
    """Build field info dict from a dataclass or dict instance."""
    if isinstance(instance, dict):
        return {k: _DictFieldInfo(k, v) for k, v in instance.items()}
    all_fields = fields(instance)
    return {f.name: f for f in all_fields}


def _render_header_badges(
    instance: Any,
    badge_field_names: list[str | Any],
    field_dict: dict[str, Any],
    field_renderers: dict[str, Callable],
) -> list[Any]:
    """Render specified fields as badge elements for the title row.

    Items can be:
    - str: introspect from dataclass field (existing behavior)
    - None: skipped silently (enables conditional badges)
    - Any other FT component: passed through directly
    """
    elements: list[Any] = []
    for item in badge_field_names:
        if item is None:
            continue
        if not isinstance(item, str):
            # Pre-rendered FT component — pass through
            elements.append(item)
            continue
        # String item — introspect from dataclass field
        field_name = item
        if field_name not in field_dict:
            continue
        value = _get_value(instance, field_name)
        if value is None:
            continue
        if field_name in field_renderers:
            rendered = field_renderers[field_name](value)
        else:
            field_info = field_dict[field_name]
            renderer = FieldRendererMapper.get_default_renderer(field_name, field_info.type, value)
            rendered = renderer(value)
        if rendered is not None:
            elements.append(rendered)
    return elements


def _render_title(title_value: str, title_href: str | None) -> Any:
    """Render title text, optionally as a link."""
    if title_href:
        return H3(
            A(str(title_value), href=title_href, cls="text-primary hover:underline"),
            cls="text-lg font-semibold mb-2",
        )
    return H3(str(title_value), cls="text-lg font-semibold mb-2")


class CardGenerator:
    """
    Dynamic display card generator from dataclass or dict introspection.

    Introspects fields, determines renderers via type, generates UI components.
    Accepts both dataclass instances and plain dicts.
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
        show_labels: bool = True,
        actions: Any = None,
        header_badges: list[str | Any] | None = None,
        title_href: str | None = None,
        subtitle: str | Any | None = None,
        metadata: list[Any] | None = None,
        extra: Any | None = None,
    ) -> Div:
        """
        Generate display card from dataclass or dict introspection.

        Args:
            instance: Dataclass instance or dict to display
            display_fields: Only display these fields (None = all)
            exclude_fields: Exclude these fields (default: uid, created_at, updated_at)
            field_order: Custom field ordering
            field_renderers: Custom renderers for specific fields (return None to skip)
            field_labels: Custom labels for specific fields
            title_field: Field to use as card title (default: 'title' or 'name')
            card_attrs: Additional card attributes (cls, id, etc.)
            show_empty_fields: Show fields even if value is None/empty
            show_labels: When False, render values without Label wrappers (for list cards)
            actions: Optional action elements appended at card bottom with border separator
            header_badges: Fields or pre-rendered FT components for badges beside the title.
                String items are introspected from dataclass; non-string items pass through;
                None items are skipped silently (enables conditional badges).
            title_href: Optional URL to make the title a clickable link
            subtitle: Text or FT component below the title (before badges row)
            metadata: Pre-composed flex row after body fields, before actions.
                Strings are wrapped in SmallText(); FT components pass through.
            extra: Content appended after the actions slot, no wrapper.

        Returns:
            Card component
        """
        if not is_dataclass(instance) and not isinstance(instance, dict):
            raise ValueError(f"Instance must be a dataclass or dict, got {type(instance)}")

        # Build field dict from dataclass or dict
        field_dict = _build_field_dict(instance)

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

        # Remove header_badges fields from body rendering
        if header_badges:
            field_names = [f for f in field_names if f not in header_badges]

        # Apply custom ordering
        if field_order:
            ordered_fields = [f for f in field_order if f in field_names]
            remaining_fields = [f for f in field_names if f not in field_order]
            field_names = ordered_fields + remaining_fields

        # Determine title field
        if title_field is None:
            if "title" in field_dict:
                title_field = "title"
            elif "name" in field_dict:
                title_field = "name"

        # Build card components
        card_components: list[Any] = []

        # Add title if detected
        if title_field and title_field in field_dict:
            title_value = _get_value(instance, title_field)
            if title_value:
                title_component = _render_title(str(title_value), title_href)

                # Add subtitle below title if provided
                if subtitle is not None:
                    if isinstance(subtitle, str):
                        subtitle_component = P(subtitle, cls="text-sm text-muted-foreground")
                    else:
                        subtitle_component = subtitle
                    title_block = Div(title_component, subtitle_component)
                else:
                    title_block = title_component

                if header_badges:
                    badge_elements = _render_header_badges(
                        instance, header_badges, field_dict, field_renderers or {}
                    )
                    if badge_elements:
                        card_components.append(
                            Row(
                                FlexItem(title_block, grow=True),
                                FlexItem(Div(*badge_elements, cls="flex gap-2"), shrink=False),
                                gap=3,
                            )
                        )
                    else:
                        card_components.append(title_block)
                else:
                    card_components.append(title_block)
                # Remove title from fields list (already displayed)
                if title_field in field_names:
                    field_names.remove(title_field)

        # Generate field displays
        field_renderers = field_renderers or {}
        field_labels = field_labels or {}

        for field_name in field_names:
            field_info = field_dict[field_name]
            value = _get_value(instance, field_name)

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
            rendered_value = renderer(value)
            if rendered_value is None:
                continue

            if show_labels:
                field_component = Div(
                    Label(label, cls="font-semibold text-muted-foreground block mb-1"),
                    rendered_value,
                    cls="mb-3",
                )
            else:
                field_component = Div(rendered_value, cls="mb-2")

            card_components.append(field_component)

        # Add metadata row
        if metadata:
            meta_items = [SmallText(m) if isinstance(m, str) else m for m in metadata]
            card_components.append(Div(*meta_items, cls="flex flex-wrap gap-3 mt-3"))

        # Add actions slot
        if actions is not None:
            card_components.append(Div(actions, cls="mt-4 pt-3 border-t border-border"))

        # Add extra content (raw append, no wrapper)
        if extra is not None:
            card_components.append(extra)

        # Build card attributes
        attrs: dict[str, Any] = {}
        if card_attrs:
            attrs.update(card_attrs)

        return Card(CardBody(*card_components), **attrs)

    @staticmethod
    def from_list(
        instances: list[Any],
        display_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
        field_renderers: dict[str, Callable] | None = None,
        title_field: str | None = None,
        list_attrs: dict[str, Any] | None = None,
        show_labels: bool = True,
        header_badges: list[str | Any] | None = None,
        subtitle: str | Any | None = None,
        metadata: list[Any] | None = None,
        extra: Any | None = None,
    ) -> Div:
        """Generate a list of display cards from multiple instances."""
        cards = [
            CardGenerator.from_dataclass(
                instance,
                display_fields=display_fields,
                exclude_fields=exclude_fields,
                field_renderers=field_renderers,
                title_field=title_field,
                show_labels=show_labels,
                header_badges=header_badges,
                subtitle=subtitle,
                metadata=metadata,
                extra=extra,
            )
            for instance in instances
        ]

        attrs = {"cls": "space-y-4"}
        if list_attrs:
            attrs.update(list_attrs)

        return Div(*cards, **attrs)

    @staticmethod
    def compact_card(
        instance: Any,
        display_fields: list[str],
        title_field: str | None = None,
        subtitle: str | Any | None = None,
        metadata: list[Any] | None = None,
    ) -> Div:
        """Generate a compact card (minimal styling, fewer details)."""
        return CardGenerator.from_dataclass(
            instance,
            display_fields=display_fields,
            title_field=title_field,
            subtitle=subtitle,
            metadata=metadata,
            card_attrs={
                "cls": "bg-background border border-border hover:shadow-md transition-shadow"
            },
        )

    @staticmethod
    def detailed_card(instance: Any, exclude_fields: list[str] | None = None) -> Div:
        """Generate a detailed card (shows all non-excluded fields)."""
        return CardGenerator.from_dataclass(
            instance,
            exclude_fields=exclude_fields,
            show_empty_fields=True,
            card_attrs={"cls": "bg-background shadow-xl"},
        )


# Export main classes
__all__ = ["CardGenerator", "FieldRendererMapper"]
