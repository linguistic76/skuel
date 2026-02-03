"""Button components with consistent styling.

Buttons are used for actions and navigation. They come in different
variants for different contexts (primary actions, secondary actions,
destructive actions, etc.) and sizes.
"""

from typing import Any

from fasthtml.common import A
from fasthtml.common import Button as HtmlButton


def Button(
    text: str,
    variant: str = "primary",
    size: str = "md",
    **kwargs: Any,
) -> HtmlButton:
    """Styled button for actions.

    Args:
        text: The button text
        variant: Style variant - one of:
            - "primary": Blue accent background (default)
            - "secondary": Gray background with border
            - "ghost": Transparent with hover effect
            - "danger": Red background for destructive actions
        size: Size variant - one of:
            - "sm": Small
            - "md": Medium (default)
            - "lg": Large
        **kwargs: Additional attributes passed to the Button element
            Common: type, disabled, hx_post, hx_target, etc.

    Returns:
        A Button element with appropriate styling
    """
    base = (
        "inline-flex items-center justify-center font-medium rounded-lg "
        "transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2"
    )

    variants = {
        "primary": "bg-primary text-primary-content hover:bg-primary-focus focus:ring-primary",
        "secondary": "bg-base-200 text-base-content hover:bg-base-100 border border-base-300",
        "ghost": "text-base-content/70 hover:text-base-content hover:bg-base-200",
        "danger": "bg-error text-error-content hover:bg-error/90 focus:ring-error",
    }

    sizes = {
        "sm": "px-3 py-1.5 text-sm",
        "md": "px-4 py-2 text-sm",
        "lg": "px-6 py-3 text-base",
    }

    variant_cls = variants.get(variant, variants["primary"])
    size_cls = sizes.get(size, sizes["md"])
    full_cls = f"{base} {variant_cls} {size_cls}"

    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        full_cls = f"{full_cls} {extra_cls}"

    return HtmlButton(text, cls=full_cls, **kwargs)


def ButtonLink(
    text: str,
    href: str,
    variant: str = "primary",
    size: str = "md",
    full_width: bool = False,
    **kwargs: Any,
) -> A:
    """Button-styled link for navigation.

    Use this when you need a button appearance but the action is navigation
    rather than form submission or HTMX action.

    Args:
        text: The link text
        href: URL to navigate to
        variant: Style variant - one of:
            - "primary": Blue accent background (default)
            - "secondary": Gray background with border
            - "ghost": Transparent with hover effect
        size: Size variant - one of:
            - "sm": Small
            - "md": Medium (default)
            - "lg": Large
        full_width: If True, button takes full width of container
        **kwargs: Additional attributes passed to the A element

    Returns:
        An A element styled as a button
    """
    base = (
        "inline-flex items-center justify-center font-medium rounded-lg "
        "transition-colors no-underline"
    )

    variants = {
        "primary": "bg-primary text-primary-content hover:bg-primary-focus",
        "secondary": "bg-base-200 text-base-content hover:bg-base-100 border border-base-300",
        "ghost": "text-base-content/70 hover:text-base-content hover:bg-base-200",
    }

    sizes = {
        "sm": "px-3 py-1.5 text-sm",
        "md": "px-4 py-2 text-sm",
        "lg": "px-6 py-3 text-base",
    }

    variant_cls = variants.get(variant, variants["primary"])
    size_cls = sizes.get(size, sizes["md"])
    width_cls = "w-full" if full_width else ""
    full_cls = f"{base} {variant_cls} {size_cls} {width_cls}".strip()

    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        full_cls = f"{full_cls} {extra_cls}"

    return A(text, href=href, cls=full_cls, **kwargs)


def IconButton(
    icon: str,
    variant: str = "ghost",
    size: str = "md",
    label: str | None = None,
    **kwargs: Any,
) -> HtmlButton:
    """Icon-only button with optional aria-label.

    Args:
        icon: The icon content (emoji or SVG)
        variant: Style variant (default: ghost)
        size: Size variant (default: md)
        label: Accessible label for screen readers
        **kwargs: Additional attributes passed to the Button element

    Returns:
        A Button element containing just an icon
    """
    base = (
        "inline-flex items-center justify-center rounded-lg "
        "transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2"
    )

    variants = {
        "primary": "bg-primary text-primary-content hover:bg-primary-focus focus:ring-primary",
        "secondary": "bg-base-200 text-base-content hover:bg-base-100 border border-base-300",
        "ghost": "text-base-content/70 hover:text-base-content hover:bg-base-200",
        "danger": "bg-error text-error-content hover:bg-error/90 focus:ring-error",
    }

    sizes = {
        "sm": "p-1.5 text-sm",
        "md": "p-2 text-base",
        "lg": "p-3 text-lg",
    }

    variant_cls = variants.get(variant, variants["ghost"])
    size_cls = sizes.get(size, sizes["md"])
    full_cls = f"{base} {variant_cls} {size_cls}"

    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        full_cls = f"{full_cls} {extra_cls}"

    # Add aria-label for accessibility
    if label:
        kwargs["aria_label"] = label

    return HtmlButton(icon, cls=full_cls, **kwargs)
