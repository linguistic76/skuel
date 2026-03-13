"""
SKUEL Button Components (MonsterUI)
====================================

ButtonT enum and Button/ButtonLink/IconButton wrappers.
Uses MonsterUI's Button internally, keeps SKUEL's variant= API.
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import A
from monsterui.franken import Button as MButton
from monsterui.franken import ButtonT as MButtonT

from ui.layout import Size

__all__ = ["ButtonT", "Button", "ButtonLink", "IconButton"]


# Mapping from SKUEL ButtonT to MonsterUI ButtonT
_VARIANT_MAP: dict[str, MButtonT | str] = {
    "primary": MButtonT.primary,
    "secondary": MButtonT.secondary,
    "ghost": MButtonT.ghost,
    "link": MButtonT.link,
    "error": MButtonT.destructive,
    "success": MButtonT.primary,
    "warning": MButtonT.secondary,
    "info": MButtonT.secondary,
    "neutral": MButtonT.default,
    "accent": MButtonT.primary,
    "outline": MButtonT.secondary,
}

# Mapping from SKUEL Size to MonsterUI ButtonT size members
_SIZE_MAP: dict[str, MButtonT | str] = {
    "xs": MButtonT.xs,
    "sm": MButtonT.sm,
    "md": "",
    "lg": MButtonT.lg,
    "xl": MButtonT.xl,
}


class ButtonT(StrEnum):
    """Button variant types — SKUEL semantic variants mapped to MonsterUI internally."""

    primary = "primary"
    secondary = "secondary"
    accent = "accent"
    neutral = "neutral"
    ghost = "ghost"
    link = "link"
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"
    outline = "outline"


def Button(
    *c: Any,
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    outline: bool = False,
    disabled: bool = False,
    loading: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Button wrapper using MonsterUI internals.

    Args:
        *c: Button content (text, icons, etc.)
        cls: Additional CSS classes
        variant: Button style variant (primary, secondary, etc.)
        size: Button size (xs, sm, md, lg, xl)
        outline: If True, renders as outline/secondary button
        disabled: If True, button is disabled
        loading: If True, shows loading spinner
        **kwargs: Additional HTML attributes (hx_*, onclick, etc.)
    """
    mu_variant = _VARIANT_MAP.get(variant.value, MButtonT.default)
    if outline and variant != ButtonT.outline:
        mu_variant = MButtonT.secondary

    cls_parts: list[Any] = [mu_variant]

    if size:
        size_cls = _SIZE_MAP.get(size.value, "")
        if size_cls:
            cls_parts.append(size_cls)

    if loading:
        cls_parts.append("opacity-70 pointer-events-none")

    if cls:
        cls_parts.append(cls)

    return MButton(*c, cls=tuple(cls_parts), disabled=disabled, **kwargs)


def ButtonLink(
    *c: Any,
    href: str,
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Button-styled link for navigation.

    Use when the action is navigation rather than form submission.

    Args:
        *c: Link content (text, icons, etc.)
        href: URL to navigate to
        cls: Additional CSS classes
        variant: Button style variant
        size: Button size (xs, sm, md, lg, xl)
        **kwargs: Additional HTML attributes
    """
    mu_variant = _VARIANT_MAP.get(variant.value, MButtonT.default)

    cls_parts: list[str] = [
        "uk-button",
        str(mu_variant) if isinstance(mu_variant, MButtonT) else mu_variant,
    ]
    if size:
        size_cls = _SIZE_MAP.get(size.value, "")
        if size_cls:
            cls_parts.append(str(size_cls) if isinstance(size_cls, MButtonT) else size_cls)
    if cls:
        cls_parts.append(cls)

    return A(*c, href=href, cls=" ".join(cls_parts), **kwargs)


def IconButton(
    icon: str,
    cls: str = "",
    variant: ButtonT = ButtonT.ghost,
    size: Size | None = None,
    label: str | None = None,
    **kwargs: Any,
) -> Any:
    """Icon-only button with optional aria-label.

    Args:
        icon: The icon content (emoji or SVG)
        cls: Additional CSS classes
        variant: Button style variant (default: ghost)
        size: Button size
        label: Accessible label for screen readers
        **kwargs: Additional attributes passed to the Button element
    """
    if label:
        kwargs["aria_label"] = label

    mu_variant = _VARIANT_MAP.get(variant.value, MButtonT.ghost)
    cls_parts: list[Any] = [mu_variant, MButtonT.icon]

    if size:
        size_cls = _SIZE_MAP.get(size.value, "")
        if size_cls:
            cls_parts.append(size_cls)

    if cls:
        cls_parts.append(cls)

    return MButton(icon, cls=tuple(cls_parts), **kwargs)
