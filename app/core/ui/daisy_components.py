"""
SKUEL DaisyUI Component Library
===============================

Thin Python wrappers around FastHTML FT components with DaisyUI styling.
Provides type-safe, Pythonic component ergonomics with DaisyUI design system.

Philosophy: FT Components → SKUEL Wrappers → DaisyUI Classes

Usage:
    from core.ui.daisy_components import (
        Button, ButtonT, Card, CardBody, Alert, AlertT,
        Badge, BadgeT, Input, Select, Textarea, Modal, Loading,
        DivHStacked, DivVStacked, DivFullySpaced, Grid, Size
    )

    # Button with variant
    Button("Submit", variant=ButtonT.primary, size=Size.lg)

    # Card with body
    Card(CardBody(H1("Title"), P("Content")))

    # Alert
    Alert("Success!", variant=AlertT.success)

Design Principles:
- One Path Forward: Single way to create each component type
- Type Safety: Enums prevent class typos
- Centralized Styling: Changes in one place affect all usages
- FT-Native: Still using FastHTML architecture, just with thin wrappers
- Pure DaisyUI: No legacy framework classes (no uk-* classes)

January 2026: Initial implementation for SKUEL PWA migration
"""

from enum import Enum
from typing import Any

from fasthtml.common import (
    Button as FTButton,
)
from fasthtml.common import (
    Dialog,
    Div,
    Option,
    Span,
)
from fasthtml.common import (
    Input as FTInput,
)
from fasthtml.common import (
    Select as FTSelect,
)
from fasthtml.common import (
    Textarea as FTTextarea,
)

# ============================================================================
# ENUMS - Type-safe variant selection
# ============================================================================


class ButtonT(str, Enum):
    """Button variant types - maps to DaisyUI btn-* classes."""

    primary = "btn-primary"
    secondary = "btn-secondary"
    accent = "btn-accent"
    neutral = "btn-neutral"
    ghost = "btn-ghost"
    link = "btn-link"
    info = "btn-info"
    success = "btn-success"
    warning = "btn-warning"
    error = "btn-error"
    outline = "btn-outline"


class AlertT(str, Enum):
    """Alert variant types - maps to DaisyUI alert-* classes."""

    info = "alert-info"
    success = "alert-success"
    warning = "alert-warning"
    error = "alert-error"


class BadgeT(str, Enum):
    """Badge variant types - maps to DaisyUI badge-* classes."""

    primary = "badge-primary"
    secondary = "badge-secondary"
    accent = "badge-accent"
    neutral = "badge-neutral"
    ghost = "badge-ghost"
    info = "badge-info"
    success = "badge-success"
    warning = "badge-warning"
    error = "badge-error"
    outline = "badge-outline"


class Size(str, Enum):
    """Component size options."""

    xs = "xs"
    sm = "sm"
    md = "md"
    lg = "lg"
    xl = "xl"


class InputT(str, Enum):
    """Input variant types - maps to DaisyUI input-* classes."""

    bordered = "input-bordered"
    ghost = "input-ghost"
    primary = "input-primary"
    secondary = "input-secondary"
    accent = "input-accent"
    info = "input-info"
    success = "input-success"
    warning = "input-warning"
    error = "input-error"


class CardT(str, Enum):
    """Card variant types - maps to DaisyUI styling."""

    default = ""
    bordered = "card-bordered"
    compact = "card-compact"
    side = "card-side"


class ProgressT(str, Enum):
    """Progress variant types - maps to DaisyUI progress-* classes."""

    primary = "progress-primary"
    secondary = "progress-secondary"
    accent = "progress-accent"
    info = "progress-info"
    success = "progress-success"
    warning = "progress-warning"
    error = "progress-error"


class LoadingT(str, Enum):
    """Loading spinner variant types."""

    spinner = "loading-spinner"
    dots = "loading-dots"
    ring = "loading-ring"
    ball = "loading-ball"
    bars = "loading-bars"
    infinity = "loading-infinity"


# ============================================================================
# BUTTON COMPONENTS
# ============================================================================


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
    DaisyUI Button wrapper.

    Args:
        *c: Button content (text, icons, etc.)
        cls: Additional CSS classes
        variant: Button style variant (primary, secondary, etc.)
        size: Button size (xs, sm, md, lg, xl)
        outline: If True, renders as outline button
        disabled: If True, button is disabled
        loading: If True, shows loading spinner
        **kwargs: Additional HTML attributes (hx_*, onclick, etc.)

    Example:
        Button("Submit", variant=ButtonT.primary, size=Size.lg)
        Button("Cancel", variant=ButtonT.ghost, hx_get="/cancel")
    """
    classes = ["btn", variant.value]

    if size:
        classes.append(f"btn-{size.value}")
    if outline and variant != ButtonT.outline:
        classes.append("btn-outline")
    if disabled:
        classes.append("btn-disabled")
    if loading:
        classes.append("loading")

    if cls:
        classes.append(cls)

    return FTButton(*c, cls=" ".join(classes), disabled=disabled, **kwargs)


# ============================================================================
# CARD COMPONENTS
# ============================================================================


def Card(
    *c: Any,
    cls: str = "",
    variant: CardT = CardT.default,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Card wrapper.

    Args:
        *c: Card content (should include CardBody for proper styling)
        cls: Additional CSS classes
        variant: Card style variant
        **kwargs: Additional HTML attributes

    Example:
        Card(CardBody(H1("Title"), P("Content")))
        Card(CardBody(...), variant=CardT.bordered)
    """
    classes = ["card", "bg-base-100", "shadow-sm"]

    if variant.value:
        classes.append(variant.value)

    if cls:
        classes.append(cls)

    return Div(*c, cls=" ".join(classes), **kwargs)


def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card body wrapper.

    Args:
        *c: Card body content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["card-body"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card title wrapper.

    Args:
        *c: Title content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["card-title"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardActions(*c: Any, cls: str = "", justify: str = "end", **kwargs: Any) -> Any:
    """
    DaisyUI Card actions wrapper.

    Args:
        *c: Action buttons/content
        cls: Additional CSS classes
        justify: Justify content ("start", "end", "center", "between")
        **kwargs: Additional HTML attributes
    """
    classes = ["card-actions", f"justify-{justify}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardFigure(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card figure wrapper for images.

    Args:
        *c: Figure content (typically an Img)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Figure

    classes = ["figure"]
    if cls:
        classes.append(cls)
    return Figure(*c, cls=" ".join(classes), **kwargs)


# ============================================================================
# ALERT COMPONENTS
# ============================================================================


def Alert(
    *c: Any,
    cls: str = "",
    variant: AlertT = AlertT.info,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Alert wrapper.

    Args:
        *c: Alert content
        cls: Additional CSS classes
        variant: Alert style variant (info, success, warning, error)
        **kwargs: Additional HTML attributes

    Example:
        Alert("Operation successful!", variant=AlertT.success)
        Alert(Span("Warning!"), P("Please review."), variant=AlertT.warning)
    """
    classes = ["alert", variant.value]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), role="alert", **kwargs)


# ============================================================================
# BADGE COMPONENTS
# ============================================================================


def Badge(
    *c: Any,
    cls: str = "",
    variant: BadgeT = BadgeT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Badge wrapper.

    Args:
        *c: Badge content
        cls: Additional CSS classes
        variant: Badge style variant
        size: Badge size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes

    Example:
        Badge("New", variant=BadgeT.primary)
        Badge("5", variant=BadgeT.error, size=Size.sm)
    """
    classes = ["badge", variant.value]
    if size:
        classes.append(f"badge-{size.value}")
    if cls:
        classes.append(cls)
    return Span(*c, cls=" ".join(classes), **kwargs)


# ============================================================================
# FORM COMPONENTS
# ============================================================================


def Input(
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Input wrapper.

    Args:
        cls: Additional CSS classes
        variant: Input style variant
        size: Input size (xs, sm, md, lg)
        full_width: If True, input takes full width
        **kwargs: Additional HTML attributes (type, name, value, placeholder, etc.)

    Example:
        Input(type="text", name="email", placeholder="Enter email")
        Input(variant=InputT.primary, size=Size.lg)
    """
    classes = ["input", variant.value]
    if size:
        classes.append(f"input-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)
    return FTInput(cls=" ".join(classes), **kwargs)


def Select(
    *options: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Select wrapper.

    Args:
        *options: Option elements or (value, label) tuples
        cls: Additional CSS classes
        variant: Select style variant
        size: Select size (xs, sm, md, lg)
        full_width: If True, select takes full width
        **kwargs: Additional HTML attributes (name, required, etc.)

    Example:
        Select(
            Option("Choose...", value=""),
            Option("Option 1", value="1"),
            Option("Option 2", value="2"),
            name="choice"
        )
    """
    classes = ["select", variant.value.replace("input-", "select-")]
    if size:
        classes.append(f"select-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)
    return FTSelect(*options, cls=" ".join(classes), **kwargs)


def Textarea(
    *c: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Textarea wrapper.

    Args:
        *c: Initial textarea content
        cls: Additional CSS classes
        variant: Textarea style variant
        size: Textarea size (xs, sm, md, lg)
        full_width: If True, textarea takes full width
        **kwargs: Additional HTML attributes (name, rows, placeholder, etc.)

    Example:
        Textarea(name="description", rows="4", placeholder="Enter description...")
    """
    classes = ["textarea", variant.value.replace("input-", "textarea-")]
    if size:
        classes.append(f"textarea-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)
    return FTTextarea(*c, cls=" ".join(classes), **kwargs)


def FormControl(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Form control wrapper for proper form layout.

    Args:
        *c: Form control content (label, input, helper text)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes

    Example:
        FormControl(
            Label("Email", for_="email"),
            Input(type="email", id="email", name="email"),
        )
    """
    classes = ["form-control"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Label(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Label wrapper.

    Args:
        *c: Label content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Label as FTLabel

    classes = ["label"]
    if cls:
        classes.append(cls)
    return FTLabel(*c, cls=" ".join(classes), **kwargs)


def LabelText(*c: Any, cls: str = "", alt: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Label text wrapper.

    Args:
        *c: Label text content
        cls: Additional CSS classes
        alt: If True, uses label-text-alt for smaller text
        **kwargs: Additional HTML attributes
    """
    classes = ["label-text-alt" if alt else "label-text"]
    if cls:
        classes.append(cls)
    return Span(*c, cls=" ".join(classes), **kwargs)


def Checkbox(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Checkbox wrapper.

    Args:
        cls: Additional CSS classes
        variant: Checkbox color variant
        size: Checkbox size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    classes = ["checkbox", variant.value.replace("btn-", "checkbox-")]
    if size:
        classes.append(f"checkbox-{size.value}")
    if cls:
        classes.append(cls)
    return FTInput(type="checkbox", cls=" ".join(classes), **kwargs)


def Radio(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Radio wrapper.

    Args:
        cls: Additional CSS classes
        variant: Radio color variant
        size: Radio size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    classes = ["radio", variant.value.replace("btn-", "radio-")]
    if size:
        classes.append(f"radio-{size.value}")
    if cls:
        classes.append(cls)
    return FTInput(type="radio", cls=" ".join(classes), **kwargs)


def Toggle(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Toggle wrapper.

    Args:
        cls: Additional CSS classes
        variant: Toggle color variant
        size: Toggle size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    classes = ["toggle", variant.value.replace("btn-", "toggle-")]
    if size:
        classes.append(f"toggle-{size.value}")
    if cls:
        classes.append(cls)
    return FTInput(type="checkbox", cls=" ".join(classes), **kwargs)


def Range(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Range slider wrapper.

    Args:
        cls: Additional CSS classes
        variant: Range color variant
        size: Range size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes (min, max, value, step)
    """
    classes = ["range", variant.value.replace("btn-", "range-")]
    if size:
        classes.append(f"range-{size.value}")
    if cls:
        classes.append(cls)
    return FTInput(type="range", cls=" ".join(classes), **kwargs)


# ============================================================================
# MODAL COMPONENTS
# ============================================================================


def Modal(
    id: str,
    *c: Any,
    cls: str = "",
    open_on_load: bool = False,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Modal wrapper using dialog element.

    Args:
        id: Modal ID (required for opening/closing)
        *c: Modal content (should include ModalBox)
        cls: Additional CSS classes
        open_on_load: If True, modal opens when page loads
        **kwargs: Additional HTML attributes

    Example:
        Modal("my-modal",
            ModalBox(
                H2("Modal Title"),
                P("Modal content here"),
                ModalAction(
                    Button("Close", onclick="my-modal.close()")
                )
            )
        )

    To open: document.getElementById('my-modal').showModal()
    To close: document.getElementById('my-modal').close()
    """
    classes = ["modal"]
    if cls:
        classes.append(cls)

    attrs = {"id": id, "cls": " ".join(classes)}
    if open_on_load:
        attrs["open"] = True

    return Dialog(*c, **attrs, **kwargs)


def ModalBox(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Modal box wrapper (the content container).

    Args:
        *c: Modal box content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["modal-box"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def ModalAction(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Modal action wrapper (for buttons).

    Args:
        *c: Action buttons
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["modal-action"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def ModalBackdrop(**kwargs: Any) -> Any:
    """
    DaisyUI Modal backdrop (closes modal on click).

    Add as child of Modal after ModalBox to enable click-outside-to-close.
    """
    from fasthtml.common import Form

    return Form(method="dialog", cls="modal-backdrop")(FTButton("close", **kwargs))


# ============================================================================
# LOADING COMPONENTS
# ============================================================================


def Loading(
    cls: str = "",
    variant: LoadingT = LoadingT.spinner,
    size: Size = Size.md,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Loading spinner.

    Args:
        cls: Additional CSS classes
        variant: Loading animation type
        size: Loading size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes

    Example:
        Loading(size=Size.lg)
        Loading(variant=LoadingT.dots, size=Size.sm)
    """
    classes = ["loading", variant.value, f"loading-{size.value}"]
    if cls:
        classes.append(cls)
    return Span(cls=" ".join(classes), **kwargs)


# ============================================================================
# PROGRESS COMPONENTS
# ============================================================================


def Progress(
    value: int | float | None = None,
    max_val: int = 100,
    cls: str = "",
    variant: ProgressT = ProgressT.primary,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Progress bar.

    Args:
        value: Current progress value (None for indeterminate)
        max_val: Maximum value (default 100)
        cls: Additional CSS classes
        variant: Progress color variant
        **kwargs: Additional HTML attributes

    Example:
        Progress(value=75, variant=ProgressT.success)
        Progress()  # Indeterminate
    """
    from fasthtml.common import Progress as FTProgress

    classes = ["progress", variant.value, "w-full"]
    if cls:
        classes.append(cls)

    attrs = {"cls": " ".join(classes), "max": str(max_val)}
    if value is not None:
        attrs["value"] = str(int(value))

    return FTProgress(**attrs, **kwargs)


def RadialProgress(
    value: int | float,
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: str = "4rem",
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Radial progress (circular).

    Args:
        value: Progress percentage (0-100)
        cls: Additional CSS classes
        variant: Color variant
        size: Size as CSS value (e.g., "4rem", "5rem")
        **kwargs: Additional HTML attributes

    Example:
        RadialProgress(75, variant=ButtonT.success)
    """
    classes = ["radial-progress", variant.value.replace("btn-", "text-")]
    if cls:
        classes.append(cls)

    style = f"--value:{int(value)}; --size:{size};"
    return Div(
        f"{int(value)}%",
        cls=" ".join(classes),
        style=style,
        role="progressbar",
        **kwargs,
    )


# ============================================================================
# LAYOUT HELPERS
# ============================================================================


def DivHStacked(
    *c: Any,
    gap: int = 2,
    cls: str = "",
    align: str = "center",
    **kwargs: Any,
) -> Any:
    """
    Horizontal flex stack.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch", "baseline")
        **kwargs: Additional HTML attributes

    Example:
        DivHStacked(Icon("check"), Span("Success"), gap=2)
    """
    classes = ["flex", "flex-row", f"gap-{gap}", f"items-{align}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivVStacked(
    *c: Any,
    gap: int = 2,
    cls: str = "",
    align: str = "stretch",
    **kwargs: Any,
) -> Any:
    """
    Vertical flex stack.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch")
        **kwargs: Additional HTML attributes

    Example:
        DivVStacked(H1("Title"), P("Description"), gap=4)
    """
    classes = ["flex", "flex-col", f"gap-{gap}", f"items-{align}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivFullySpaced(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Space-between flex layout.

    Args:
        *c: Child elements (typically 2)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes

    Example:
        DivFullySpaced(Span("Left"), Span("Right"))
    """
    classes = ["flex", "justify-between", "items-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivCentered(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Centered flex layout (both axes).

    Args:
        *c: Child elements
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["flex", "justify-center", "items-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Grid(
    *c: Any,
    cols: int = 1,
    gap: int = 4,
    cls: str = "",
    responsive: bool = True,
    **kwargs: Any,
) -> Any:
    """
    CSS Grid wrapper.

    Args:
        *c: Grid items
        cols: Number of columns
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        responsive: If True, adds responsive breakpoints
        **kwargs: Additional HTML attributes

    Example:
        Grid(Card(...), Card(...), Card(...), cols=3, gap=4)
    """
    classes = ["grid", f"gap-{gap}"]

    if responsive:
        # Responsive grid: 1 col on mobile, 2 on sm, cols on md+
        if cols == 2:
            classes.append("grid-cols-1 sm:grid-cols-2")
        elif cols == 3:
            classes.append("grid-cols-1 sm:grid-cols-2 md:grid-cols-3")
        elif cols == 4:
            classes.append("grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4")
        else:
            classes.append(f"grid-cols-{cols}")
    else:
        classes.append(f"grid-cols-{cols}")

    if cls:
        classes.append(cls)

    return Div(*c, cls=" ".join(classes), **kwargs)


def Container(*c: Any, cls: str = "", size: str = "7xl", **kwargs: Any) -> Any:
    """
    Centered container with max-width.

    Args:
        *c: Container content
        cls: Additional CSS classes
        size: Max width size (sm, md, lg, xl, 2xl, 3xl, 4xl, 5xl, 6xl, 7xl)
        **kwargs: Additional HTML attributes
    """
    classes = ["container", "mx-auto", "px-4", f"max-w-{size}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


# ============================================================================
# NAVIGATION COMPONENTS
# ============================================================================


def Navbar(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Navbar wrapper.

    Args:
        *c: Navbar content (NavbarStart, NavbarCenter, NavbarEnd)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["navbar", "bg-base-100"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarStart(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar start section."""
    classes = ["navbar-start"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarCenter(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar center section."""
    classes = ["navbar-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarEnd(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar end section."""
    classes = ["navbar-end"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Menu(*c: Any, cls: str = "", horizontal: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Menu wrapper.

    Args:
        *c: Menu items
        cls: Additional CSS classes
        horizontal: If True, renders horizontally
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    classes = ["menu"]
    if horizontal:
        classes.append("menu-horizontal")
    if cls:
        classes.append(cls)
    return Ul(*c, cls=" ".join(classes), **kwargs)


def MenuItem(*c: Any, cls: str = "", _active: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Menu item wrapper.

    Args:
        *c: Menu item content (typically an A tag)
        cls: Additional CSS classes
        _active: If True, marks as active item (currently unused - active class handled by caller)
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Li

    # The active class goes on the A element inside, not the Li
    return Li(*c, cls=cls if cls else None, **kwargs)


# ============================================================================
# DROPDOWN COMPONENTS
# ============================================================================


def Dropdown(*c: Any, cls: str = "", end: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Dropdown wrapper.

    Args:
        *c: Dropdown trigger and content
        cls: Additional CSS classes
        end: If True, aligns dropdown to end
        **kwargs: Additional HTML attributes

    Example:
        Dropdown(
            DropdownTrigger(Button("Options")),
            DropdownContent(
                MenuItem(A("Edit")),
                MenuItem(A("Delete")),
            )
        )
    """
    classes = ["dropdown"]
    if end:
        classes.append("dropdown-end")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DropdownTrigger(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Dropdown trigger (use tabindex for accessibility).

    Args:
        *c: Trigger content (typically a Button)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = []
    if cls:
        classes.append(cls)
    return Div(
        *c, tabindex="0", role="button", cls=" ".join(classes) if classes else None, **kwargs
    )


def DropdownContent(
    *c: Any,
    cls: str = "",
    tabindex: str = "0",
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Dropdown content wrapper.

    Args:
        *c: Dropdown menu items
        cls: Additional CSS classes
        tabindex: Tabindex for accessibility
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    classes = [
        "dropdown-content",
        "menu",
        "bg-base-100",
        "rounded-box",
        "shadow",
        "z-[1]",
        "w-52",
        "p-2",
    ]
    if cls:
        classes.append(cls)
    return Ul(*c, tabindex=tabindex, cls=" ".join(classes), **kwargs)


# ============================================================================
# TABS COMPONENTS
# ============================================================================


def Tabs(*c: Any, cls: str = "", boxed: bool = False, lifted: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Tabs wrapper.

    Args:
        *c: Tab items
        cls: Additional CSS classes
        boxed: If True, uses boxed style
        lifted: If True, uses lifted style
        **kwargs: Additional HTML attributes
    """
    classes = ["tabs"]
    if boxed:
        classes.append("tabs-boxed")
    if lifted:
        classes.append("tabs-lifted")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), role="tablist", **kwargs)


def Tab(
    *c: Any,
    cls: str = "",
    active: bool = False,
    disabled: bool = False,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Tab item.

    Args:
        *c: Tab content
        cls: Additional CSS classes
        active: If True, marks as active tab
        disabled: If True, disables the tab
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import A

    classes = ["tab"]
    if active:
        classes.append("tab-active")
    if disabled:
        classes.append("tab-disabled")
    if cls:
        classes.append(cls)
    return A(*c, cls=" ".join(classes), role="tab", **kwargs)


# ============================================================================
# TABLE COMPONENTS
# ============================================================================


def Table(*c: Any, cls: str = "", zebra: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Table wrapper.

    Args:
        *c: Table content (Thead, Tbody)
        cls: Additional CSS classes
        zebra: If True, uses zebra striping
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Table as FTTable

    classes = ["table"]
    if zebra:
        classes.append("table-zebra")
    if cls:
        classes.append(cls)
    return FTTable(*c, cls=" ".join(classes), **kwargs)


# Re-export common table elements from fasthtml
from fasthtml.common import Tbody, Td, Th, Thead, Tr  # noqa: E402

# ============================================================================
# TOOLTIP COMPONENTS
# ============================================================================


def Tooltip(
    *c: Any,
    tip: str,
    cls: str = "",
    position: str = "top",
    variant: ButtonT | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Tooltip wrapper.

    Args:
        *c: Element to wrap with tooltip
        tip: Tooltip text
        cls: Additional CSS classes
        position: Tooltip position ("top", "bottom", "left", "right")
        variant: Optional color variant
        **kwargs: Additional HTML attributes

    Example:
        Tooltip(Button("Hover me"), tip="This is a tooltip")
    """
    classes = ["tooltip", f"tooltip-{position}"]
    if variant:
        classes.append(variant.value.replace("btn-", "tooltip-"))
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **{"data-tip": tip}, **kwargs)


# ============================================================================
# DIVIDER
# ============================================================================


def Divider(
    text: str = "",
    cls: str = "",
    horizontal: bool = True,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Divider.

    Args:
        text: Optional text to show in divider
        cls: Additional CSS classes
        horizontal: If True, horizontal divider; else vertical
        **kwargs: Additional HTML attributes
    """
    classes = ["divider"]
    if not horizontal:
        classes.append("divider-horizontal")
    if cls:
        classes.append(cls)
    return Div(text if text else None, cls=" ".join(classes), **kwargs)


# ============================================================================
# AVATAR COMPONENTS
# ============================================================================


def Avatar(*c: Any, cls: str = "", online: bool | None = None, **kwargs: Any) -> Any:
    """
    DaisyUI Avatar wrapper.

    Args:
        *c: Avatar content (typically an Img in a Div)
        cls: Additional CSS classes
        online: If True shows online indicator, False shows offline, None shows nothing
        **kwargs: Additional HTML attributes
    """
    classes = ["avatar"]
    if online is True:
        classes.append("online")
    elif online is False:
        classes.append("offline")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def AvatarGroup(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Avatar group wrapper.

    Args:
        *c: Avatar elements
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["avatar-group", "-space-x-6", "rtl:space-x-reverse"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


# ============================================================================
# STATS COMPONENTS
# ============================================================================


def Stats(*c: Any, cls: str = "", vertical: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Stats wrapper.

    Args:
        *c: Stat items
        cls: Additional CSS classes
        vertical: If True, displays stats vertically
        **kwargs: Additional HTML attributes
    """
    classes = ["stats", "shadow"]
    if vertical:
        classes.append("stats-vertical")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Stat(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Stat item wrapper.

    Args:
        *c: Stat content (StatTitle, StatValue, StatDesc, etc.)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["stat"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Stat title."""
    classes = ["stat-title"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatValue(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Stat value."""
    classes = ["stat-value"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatDesc(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Stat description."""
    classes = ["stat-desc"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatFigure(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Stat figure (for icons)."""
    classes = ["stat-figure"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "ButtonT",
    "AlertT",
    "BadgeT",
    "Size",
    "InputT",
    "CardT",
    "ProgressT",
    "LoadingT",
    # Buttons
    "Button",
    # Cards
    "Card",
    "CardBody",
    "CardTitle",
    "CardActions",
    "CardFigure",
    # Alerts
    "Alert",
    # Badges
    "Badge",
    # Forms
    "Input",
    "Select",
    "Textarea",
    "FormControl",
    "Label",
    "LabelText",
    "Checkbox",
    "Radio",
    "Toggle",
    "Range",
    # Modals
    "Modal",
    "ModalBox",
    "ModalAction",
    "ModalBackdrop",
    # Loading
    "Loading",
    # Progress
    "Progress",
    "RadialProgress",
    # Layout
    "DivHStacked",
    "DivVStacked",
    "DivFullySpaced",
    "DivCentered",
    "Grid",
    "Container",
    # Navigation
    "Navbar",
    "NavbarStart",
    "NavbarCenter",
    "NavbarEnd",
    "Menu",
    "MenuItem",
    # Dropdown
    "Dropdown",
    "DropdownTrigger",
    "DropdownContent",
    # Tabs
    "Tabs",
    "Tab",
    # Tables
    "Table",
    "Thead",
    "Tbody",
    "Tr",
    "Th",
    "Td",
    # Tooltip
    "Tooltip",
    # Divider
    "Divider",
    # Avatar
    "Avatar",
    "AvatarGroup",
    # Stats
    "Stats",
    "Stat",
    "StatTitle",
    "StatValue",
    "StatDesc",
    "StatFigure",
    # Re-export common FT elements
    "Div",
    "Span",
    "Option",
]
