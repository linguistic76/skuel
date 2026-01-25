"""Card components for content containers.

Cards are the primary way to display grouped content in SKUEL.
They provide consistent styling for borders, backgrounds, and shadows.
"""

from typing import Any

from fasthtml.common import A, Div


def Card(*children: Any, padding: str = "p-6", hover: bool = False, **kwargs: Any) -> Div:
    """Base card container.

    Args:
        *children: Child elements
        padding: Padding class (default: p-6)
        hover: If True, adds hover shadow effect (default: False)
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with card styling
    """
    hover_cls = "hover:shadow-md transition-shadow" if hover else ""
    base_cls = f"bg-base-100 border border-base-200 rounded-lg {padding} {hover_cls}"

    # Merge with any additional classes from kwargs
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Div(*children, cls=full_cls, **kwargs)


def CardLink(*children: Any, href: str, **kwargs: Any) -> A:
    """Clickable card that acts as a link.

    Args:
        *children: Child elements
        href: URL to navigate to when clicked
        **kwargs: Additional attributes passed to the A element

    Returns:
        An A element styled as a card with hover effects
    """
    base_cls = "block bg-base-100 border border-base-200 rounded-lg p-6 hover:border-primary hover:shadow-md transition-all"

    # Merge with any additional classes from kwargs
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return A(*children, href=href, cls=full_cls, **kwargs)


def CardHeader(*children: Any, **kwargs: Any) -> Div:
    """Card header section.

    Use this for titles and actions at the top of a card.

    Args:
        *children: Child elements (typically CardTitle + badges/actions)
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with header styling
    """
    base_cls = "mb-4"
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Div(*children, cls=full_cls, **kwargs)


def CardBody(*children: Any, **kwargs: Any) -> Div:
    """Card body section.

    Use this for the main content of a card.

    Args:
        *children: Child elements
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element for card body content
    """
    return Div(*children, **kwargs)


def CardFooter(*children: Any, **kwargs: Any) -> Div:
    """Card footer with top border.

    Use this for actions or metadata at the bottom of a card.

    Args:
        *children: Child elements (typically buttons or links)
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with footer styling and top border
    """
    base_cls = "mt-4 pt-4 border-t border-base-200"
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Div(*children, cls=full_cls, **kwargs)
