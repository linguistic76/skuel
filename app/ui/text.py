"""Typography components with consistent styling.

Provides core typography helpers for the SKUEL design system.
All text rendering should use these components for consistent styling.

Type Scale:
- display: 48px (3rem) - Hero titles
- h1: 36px (2.25rem) - Page titles
- h2: 28px (1.75rem) - Section headers
- h3: 22px (1.375rem) - Card titles
- h4: 18px (1.125rem) - Subsections
- body: 16px (1rem) - Body text
- body-sm: 14px (0.875rem) - Secondary text
- caption: 12px (0.75rem) - Labels, captions
"""

from typing import Any

from fasthtml.common import H1, H2, H3, H4, Div, P, Span


def PageTitle(text: str, subtitle: str | None = None, **kwargs: Any) -> Div:
    """Page-level title (h1) with optional subtitle.

    Args:
        text: The main title text
        subtitle: Optional subtitle displayed below the title
        **kwargs: Additional attributes passed to the container div

    Returns:
        A Div containing the title and optional subtitle
    """
    elements = [H1(text, cls="text-4xl font-bold tracking-tight text-foreground")]
    if subtitle:
        elements.append(P(subtitle, cls="mt-2 text-lg text-muted-foreground"))
    return Div(*elements, cls="mb-8", **kwargs)


def SectionTitle(text: str, **kwargs: Any) -> H2:
    """Section header (h2).

    Args:
        text: The section title text
        **kwargs: Additional attributes passed to the H2 element

    Returns:
        An H2 element with section styling
    """
    return H2(text, cls="text-2xl font-semibold tracking-tight text-foreground mb-6", **kwargs)


def CardTitle(text: str, truncate: bool = True, **kwargs: Any) -> H3:
    """Card title (h3) with optional truncation.

    Args:
        text: The card title text
        truncate: Whether to truncate text that overflows (default: True)
        **kwargs: Additional attributes passed to the H3 element

    Returns:
        An H3 element with card title styling
    """
    truncate_cls = "truncate-1" if truncate else ""
    return H3(text, cls=f"text-lg font-semibold text-foreground {truncate_cls}".strip(), **kwargs)


def Subtitle(text: str, **kwargs: Any) -> H4:
    """Subsection header (h4).

    Args:
        text: The subtitle text
        **kwargs: Additional attributes passed to the H4 element

    Returns:
        An H4 element with subtitle styling
    """
    return H4(text, cls="text-base font-semibold text-foreground mb-4", **kwargs)


def BodyText(text: str, muted: bool = False, **kwargs: Any) -> P:
    """Body paragraph text.

    Args:
        text: The body text content
        muted: If True, uses muted color (default: False)
        **kwargs: Additional attributes passed to the P element

    Returns:
        A P element with body text styling
    """
    color = "text-muted-foreground" if muted else "text-foreground"
    return P(text, cls=f"text-base leading-relaxed {color}", **kwargs)


def SmallText(text: str, muted: bool = True, **kwargs: Any) -> Span:
    """Secondary/small text.

    Args:
        text: The small text content
        muted: If True, uses muted color (default: True)
        **kwargs: Additional attributes passed to the Span element

    Returns:
        A Span element with small text styling
    """
    color = "text-muted-foreground" if muted else "text-foreground"
    return Span(text, cls=f"text-sm {color}", **kwargs)


def Caption(text: str, **kwargs: Any) -> Span:
    """Caption/label text (uppercase, small).

    Args:
        text: The caption text
        **kwargs: Additional attributes passed to the Span element

    Returns:
        A Span element with caption styling
    """
    return Span(text, cls="text-xs text-muted-foreground uppercase tracking-wide", **kwargs)


def TruncatedText(text: str, lines: int = 1, cls: str = "", **kwargs: Any) -> Span:
    """Text with line clamping for overflow handling.

    Args:
        text: The text content
        lines: Number of lines to show before truncating (1-3)
        cls: Additional CSS classes to apply
        **kwargs: Additional attributes passed to the Span element

    Returns:
        A Span element with line-clamp styling
    """
    # Validate lines is within supported range
    lines = max(1, min(3, lines))
    return Span(text, cls=f"line-clamp-{lines} {cls}".strip(), **kwargs)
