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
    PAGE = "p-6 lg:p-8"  # 24px mobile, 32px desktop

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
    BASE = "bg-base-100 border border-base-200 rounded-lg"

    # Card with hover effect
    INTERACTIVE = "bg-base-100 border border-base-200 rounded-lg hover:shadow-md transition-shadow"

    # Padding variants
    PADDING = "p-6"  # Standard (24px)
    PADDING_COMPACT = "p-4"  # Compact (16px)
    PADDING_SPACIOUS = "p-8"  # Spacious (32px)


class Text:
    """Text styling constants for consistent typography."""

    # Headings
    H1 = "text-2xl font-bold"
    H2 = "text-xl font-semibold"
    H3 = "text-lg font-semibold"
    H4 = "text-base font-semibold"

    # Body text
    BODY = "text-base text-base-content"
    SECONDARY = "text-sm text-base-content/70"
    MUTED = "text-sm text-base-content/60"

    # Labels
    LABEL = "text-sm font-medium"


__all__ = ["Spacing", "Container", "Card", "Text"]
