"""Entity card pattern used across all SKUEL entity types.

This is the primary pattern for displaying domain entities (Tasks, Goals,
Habits, Events, etc.) in lists and grids. It provides consistent layout
with priority indicators, status badges, and proper text truncation.

Variant System:
    - CardVariant enum: DEFAULT, COMPACT, HIGHLIGHTED
    - CardConfig dataclass: Configurable styling and behavior
    - Factory methods: .default(), .compact(), .highlighted()
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from fasthtml.common import Div

from ui.cards import Card, CardBody
from ui.feedback import PriorityBadge, StatusBadge
from ui.layout import FlexItem, Row
from ui.text import CardTitle, SmallText, TruncatedText

# ============================================================================
# VARIANT SYSTEM
# ============================================================================


class CardVariant(str, Enum):
    """Card display variants for different UI contexts.

    Variants provide consistent styling patterns across all entity cards:

    DEFAULT: Standard card with full layout
        - Padding: p-4
        - Shows: description (2 lines), metadata, actions
        - Use for: Main content lists, detail views

    COMPACT: Condensed card for dense displays
        - Padding: p-3
        - Shows: title, badges only (no description/metadata)
        - Use for: Sidebars, mobile views, dashboard widgets

    HIGHLIGHTED: Emphasized card for featured content
        - Padding: p-4
        - Shows: all content + border + background
        - Use for: Pinned items, search results, featured content

    Example:
        # Standard list view
        EntityCard(title="Task", config=CardConfig.default())

        # Sidebar widget
        EntityCard(title="Task", config=CardConfig.compact())

        # Pinned/featured item
        EntityCard(title="Task", config=CardConfig.highlighted())
    """

    DEFAULT = "default"
    COMPACT = "compact"
    HIGHLIGHTED = "highlighted"


@dataclass
class CardConfig:
    """Configuration for EntityCard variant styling and behavior.

    Controls content visibility, spacing, and visual styling for entity cards.
    Use factory methods for common configurations instead of manual construction.

    Factory Methods:
        CardConfig.default() - Standard card for main content
        CardConfig.compact() - Condensed card for sidebars/mobile
        CardConfig.highlighted() - Emphasized card for featured items

    Attributes:
        variant: Card variant type
        show_description: Whether to display description text
        show_metadata: Whether to display metadata items
        show_actions: Whether to display action buttons
        truncate_title: Whether to truncate long titles
        description_lines: Number of lines before truncating description
        padding_cls: Tailwind padding classes
        gap_cls: Tailwind gap classes for spacing
        border_cls: Tailwind border classes
        background_cls: Tailwind background classes

    Example:
        # Custom configuration
        custom_config = CardConfig(
            variant=CardVariant.DEFAULT,
            show_description=True,
            description_lines=3, # Show 3 lines instead of 2
            padding_cls="p-5",
        )
    """

    variant: CardVariant = CardVariant.DEFAULT

    # Content visibility
    show_description: bool = True
    show_metadata: bool = True
    show_actions: bool = True

    # Text settings
    truncate_title: bool = True
    description_lines: int = 2

    # Spacing
    padding_cls: str = "p-4"
    gap_cls: str = "gap-3"

    # Styling
    border_cls: str = ""
    background_cls: str = ""

    @classmethod
    def default(cls) -> "CardConfig":
        """Standard card configuration for main content areas.

        Full layout with description (2 lines), metadata, and actions.
        Padding: p-4, Gap: gap-3
        """
        return cls(
            variant=CardVariant.DEFAULT,
            padding_cls="p-4",
            gap_cls="gap-3",
        )

    @classmethod
    def compact(cls) -> "CardConfig":
        """Compact card configuration for dense lists and sidebars.

        Shows only title and badges. No description, metadata, or actions.
        Padding: p-3, Gap: gap-2
        """
        return cls(
            variant=CardVariant.COMPACT,
            show_description=False,
            show_metadata=False,
            description_lines=1,
            padding_cls="p-3",
            gap_cls="gap-2",
        )

    @classmethod
    def highlighted(cls) -> "CardConfig":
        """Highlighted card configuration for featured content.

        Full layout with visual emphasis (border, background).
        Padding: p-4, Gap: gap-3, Border: border-2 border-primary
        """
        return cls(
            variant=CardVariant.HIGHLIGHTED,
            padding_cls="p-4",
            gap_cls="gap-3",
            border_cls="border-2 border-primary",
            background_cls="bg-primary/5",
        )


# ============================================================================
# ENTITY CARD
# ============================================================================


def EntityCard(
    title: str,
    description: str = "",
    status: str | None = None,
    priority: str | None = None,
    metadata: list[str] | None = None,
    actions: Any = None,
    href: str | None = None,
    config: CardConfig | None = None,
    **kwargs: Any,
) -> Div:
    """Generic entity card for all SKUEL domains with variant support.

    This card pattern is designed to work with all entity types:
    Tasks, Goals, Habits, Events, Choices, Principles, Finance,
    KU, LS, LP, MOC, Journals, Reports, and LifePath.

    Supports three display variants via CardConfig:
    - DEFAULT: Full layout (description, metadata, actions)
    - COMPACT: Condensed (title and badges only)
    - HIGHLIGHTED: Emphasized (border, background)

    Args:
        title: Entity title (will be truncated if too long)
        description: Optional description (truncated based on config)
        status: Optional status string (active, completed, pending, etc.)
        priority: Optional priority string (critical, high, medium, low)
        metadata: Optional list of metadata strings to display
        actions: Optional action elements (buttons, links)
        href: Optional URL - if provided, card becomes clickable
        config: Variant configuration (defaults to CardConfig.default())
        **kwargs: Additional attributes passed to Card

    Returns:
        A Card component with the entity content

    Examples:
        # Standard card (default)
        EntityCard(
            title="Complete project proposal",
            description="Draft and finalize the Q4 project proposal",
            status="in_progress",
            priority="high",
            metadata=["Due: Dec 15", "Project: Q4 Planning"],
            actions=ButtonLink("View", href="/tasks/123"),
        )

        # Compact card for sidebar
        EntityCard(
            title="Complete project proposal",
            description="...", # Won't show in compact mode
            status="in_progress",
            priority="high",
            config=CardConfig.compact(),
        )

        # Highlighted card for pinned items
        EntityCard(
            title="Complete project proposal",
            description="Draft and finalize the Q4 project proposal",
            priority="critical",
            config=CardConfig.highlighted(),
        )
    """
    # Use default config if not provided
    config = config or CardConfig.default()

    # Apply config to control content visibility
    if not config.show_description:
        description = ""
    if not config.show_metadata:
        metadata = None
    if not config.show_actions:
        actions = None
    # Priority border colors
    from ui.badge_classes import priority_border_class

    border_cls = ""
    if priority:
        border_cls = priority_border_class(priority)

    # Build header row: title + badges
    badges = []
    priority_badge = PriorityBadge(priority)
    status_badge = StatusBadge(status)
    if priority_badge:
        badges.append(priority_badge)
    if status_badge:
        badges.append(status_badge)

    if badges:
        badge_row = Row(*badges, gap=2)
        header = Row(
            FlexItem(CardTitle(title, truncate=True), grow=True),
            FlexItem(badge_row, shrink=False),
            gap=3,
        )
    else:
        header = FlexItem(CardTitle(title, truncate=True), grow=True)

    # Build content list
    content = [header]

    if description:
        content.append(
            TruncatedText(
                description,
                lines=config.description_lines,  # Use config
                cls="text-sm text-base-content/70 mt-2 block",
            )
        )

    if metadata:
        meta_items = [SmallText(m) for m in metadata]
        content.append(Div(*meta_items, cls="flex flex-wrap gap-3 mt-3"))

    if actions:
        content.append(Div(actions, cls="mt-4 pt-3 border-t border-base-200"))

    # Card styling - apply variant configuration
    card_cls_parts = []

    # Priority border (left border for priority indication)
    if border_cls:
        card_cls_parts.append(f"border-l-4 {border_cls}")

    # Variant border (from config - may override or supplement priority border)
    if config.border_cls:
        card_cls_parts.append(config.border_cls)

    # Variant background
    if config.background_cls:
        card_cls_parts.append(config.background_cls)

    # Merge with kwargs cls
    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        card_cls_parts.append(extra_cls)

    card_cls = " ".join(card_cls_parts).strip()

    return Card(CardBody(*content), cls=card_cls, **kwargs)


__all__ = ["CardVariant", "CardConfig", "EntityCard"]
