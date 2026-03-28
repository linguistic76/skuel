"""Design tokens for SKUEL unified UX.

Python constants corresponding to CSS variables in input.css.
Use these for consistent spacing across all UI components.

Usage:
    from ui.tokens import Spacing, Container, Card

    # Page content wrapper
    Div(content, cls=f"{Container.STANDARD} {Spacing.PAGE}")

    # Section with standard gap
    Div(*sections, cls=Spacing.SECTION)

    # Card with standard padding
    Div(content, cls=f"{Card.BASE} {Card.PADDING}")
"""


class Spacing:
    """Spacing constants for consistent layout.

    Maps to CSS variables --space-* in input.css.
    """

    # Page-level padding
    PAGE = "p-4 sm:p-6 lg:p-8"  # 16px mobile, 24px tablet, 32px desktop

    # Between major sections
    SECTION = "space-y-8"  # 32px gap

    # Between content items (cards, list items)
    CONTENT = "space-y-4"  # 16px gap
    CONTENT_GAP = "gap-4"  # 16px flex/grid gap

    # Section gap (larger)
    SECTION_GAP = "gap-8"  # 32px flex/grid gap


class Container:
    """Container width constants.

    Standard width is max-w-6xl (1152px) for all pages.
    """

    # Standard page container (most pages)
    STANDARD = "max-w-6xl mx-auto"

    # Narrow container (forms, focused content)
    NARROW = "max-w-4xl mx-auto"

    # Wide container (data-dense views)
    WIDE = "max-w-7xl mx-auto"

    # Full width (no max-width constraint)
    FULL = "w-full"


class Card:
    """Card styling constants for consistent cards."""

    # Base card styling
    BASE = "bg-background border border-border rounded-lg"

    # Card with hover effect
    INTERACTIVE = "bg-background border border-border rounded-lg hover:shadow-md transition-shadow"

    # Padding variants
    PADDING = "p-6"  # Standard (24px)
    PADDING_COMPACT = "p-4"  # Compact (16px)
    PADDING_SPACIOUS = "p-8"  # Spacious (32px)


__all__ = ["Spacing", "Container", "Card"]
