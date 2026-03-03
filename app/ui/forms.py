"""
SKUEL DaisyUI Form Components
================================

InputT enum and Input, Select, Textarea, FormControl, Label, LabelText,
Checkbox, Radio, Toggle, Range wrappers.
"""

from enum import Enum
from typing import Any

from fasthtml.common import Div, Span
from fasthtml.common import Input as FTInput
from fasthtml.common import Select as FTSelect
from fasthtml.common import Textarea as FTTextarea

from ui.buttons import ButtonT
from ui.layout import Size

__all__ = [
    "InputT",
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
]


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


def Input(
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Input wrapper with optional help text and error message.

    Args:
        cls: Additional CSS classes
        variant: Input style variant
        size: Input size (xs, sm, md, lg)
        full_width: If True, input takes full width
        help_text: Optional help text displayed below the input (e.g., "Must be at least 8 characters")
        error_text: Optional error message displayed below the input
        **kwargs: Additional HTML attributes (type, name, value, placeholder, id, etc.)

    Returns:
        If help_text or error_text provided: Div wrapper with input + help/error text
        Otherwise: Just the input element (backward compatible)

    Example:
        Input(type="text", name="email", placeholder="Enter email")
        Input(type="password", name="password", help_text="Must be at least 8 characters")
        Input(variant=InputT.error, error_text="Email is required")
    """
    classes = ["input", variant.value]
    if size:
        classes.append(f"input-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)

    # Build ARIA attributes if help or error text provided
    input_name = kwargs.get("name", kwargs.get("id", "input"))
    help_id = f"{input_name}-help"
    error_id = f"{input_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    input_element = FTInput(cls=" ".join(classes), **kwargs)

    # If no help or error text, return just the input (backward compatible)
    if not help_text and not error_text:
        return input_element

    # Otherwise, wrap with help/error text
    elements = [input_element]

    if help_text:
        elements.append(Div(help_text, id=help_id, cls="mt-1 text-sm text-base-content/70"))

    if error_text:
        elements.append(Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-error"))

    return Div(*elements, cls="w-full" if full_width else "")


def Select(
    *options: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Select wrapper with optional help text and error message.

    Args:
        *options: Option elements or (value, label) tuples
        cls: Additional CSS classes
        variant: Select style variant
        size: Select size (xs, sm, md, lg)
        full_width: If True, select takes full width
        help_text: Optional help text displayed below the select
        error_text: Optional error message displayed below the select
        **kwargs: Additional HTML attributes (name, required, id, etc.)

    Returns:
        If help_text or error_text provided: Div wrapper with select + help/error text
        Otherwise: Just the select element (backward compatible)

    Example:
        Select(
            Option("Choose...", value=""),
            Option("Option 1", value="1"),
            Option("Option 2", value="2"),
            name="choice"
        )
        Select(..., help_text="Select your preferred option")
    """
    classes = ["select", variant.value.replace("input-", "select-")]
    if size:
        classes.append(f"select-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)

    # Build ARIA attributes if help or error text provided
    select_name = kwargs.get("name", kwargs.get("id", "select"))
    help_id = f"{select_name}-help"
    error_id = f"{select_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    select_element = FTSelect(*options, cls=" ".join(classes), **kwargs)

    # If no help or error text, return just the select (backward compatible)
    if not help_text and not error_text:
        return select_element

    # Otherwise, wrap with help/error text
    elements = [select_element]

    if help_text:
        elements.append(Div(help_text, id=help_id, cls="mt-1 text-sm text-base-content/70"))

    if error_text:
        elements.append(Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-error"))

    return Div(*elements, cls="w-full" if full_width else "")


def Textarea(
    *c: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Textarea wrapper with optional help text and error message.

    Args:
        *c: Initial textarea content
        cls: Additional CSS classes
        variant: Textarea style variant
        size: Textarea size (xs, sm, md, lg)
        full_width: If True, textarea takes full width
        help_text: Optional help text displayed below the textarea
        error_text: Optional error message displayed below the textarea
        **kwargs: Additional HTML attributes (name, rows, placeholder, id, etc.)

    Returns:
        If help_text or error_text provided: Div wrapper with textarea + help/error text
        Otherwise: Just the textarea element (backward compatible)

    Example:
        Textarea(name="description", rows="4", placeholder="Enter description...")
        Textarea(name="bio", help_text="Tell us about yourself (max 500 characters)")
    """
    classes = ["textarea", variant.value.replace("input-", "textarea-")]
    if size:
        classes.append(f"textarea-{size.value}")
    if full_width:
        classes.append("w-full")
    if cls:
        classes.append(cls)

    # Build ARIA attributes if help or error text provided
    textarea_name = kwargs.get("name", kwargs.get("id", "textarea"))
    help_id = f"{textarea_name}-help"
    error_id = f"{textarea_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    textarea_element = FTTextarea(*c, cls=" ".join(classes), **kwargs)

    # If no help or error text, return just the textarea (backward compatible)
    if not help_text and not error_text:
        return textarea_element

    # Otherwise, wrap with help/error text
    elements = [textarea_element]

    if help_text:
        elements.append(Div(help_text, id=help_id, cls="mt-1 text-sm text-base-content/70"))

    if error_text:
        elements.append(Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-error"))

    return Div(*elements, cls="w-full" if full_width else "")


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
