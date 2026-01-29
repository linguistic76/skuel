"""Form input components with consistent styling.

These components provide styled form inputs that integrate with
the design system's color tokens and focus states.
"""

from typing import Any

from fasthtml.common import Div, Label, Option, Select
from fasthtml.common import Input as HtmlInput
from fasthtml.common import Textarea as HtmlTextarea


def Input(
    name: str,
    label: str | None = None,
    placeholder: str = "",
    type: str = "text",
    required: bool = False,
    error: str | None = None,
    **kwargs: Any,
) -> Div:
    """Text input with optional label and error message.

    Args:
        name: The input name attribute (also used for id)
        label: Optional label text displayed above the input
        placeholder: Placeholder text shown when input is empty
        type: Input type (text, email, password, number, etc.)
        required: Whether the field is required
        error: Optional error message to display below the input
        **kwargs: Additional attributes passed to the Input element

    Returns:
        A Div containing the label (optional), input, and error (optional)

    Accessibility:
        - Uses aria-invalid to indicate error state
        - Links error message via aria-describedby
        - Error div has role="alert" for screen reader announcements
    """
    input_cls = (
        "w-full px-3 py-2 bg-base-100 border rounded-lg text-base-content "
        "placeholder:text-base-content/50 "
        "focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
    )

    if error:
        input_cls += " border-error"
    else:
        input_cls += " border-base-300"

    elements = []
    error_id = f"{name}-error"
    has_error = error is not None

    if label:
        label_cls = "block text-sm font-medium text-base-content mb-1.5"
        label_text = f"{label} *" if required else label
        elements.append(Label(label_text, cls=label_cls, for_=name))

    # Build ARIA attributes for accessibility
    aria_attrs = {}
    if has_error:
        aria_attrs["aria_invalid"] = "true"
        aria_attrs["aria_describedby"] = error_id

    elements.append(
        HtmlInput(
            name=name,
            type=type,
            placeholder=placeholder,
            cls=input_cls,
            id=name,
            required=required,
            **aria_attrs,
            **kwargs,
        )
    )

    # Error message with proper ARIA role for screen readers
    if error:
        elements.append(
            Div(
                error,
                id=error_id,
                role="alert",
                cls="mt-1 text-sm text-error",
            )
        )

    return Div(*elements, cls="space-y-1")


def Textarea(
    name: str,
    label: str | None = None,
    placeholder: str = "",
    rows: int = 4,
    required: bool = False,
    error: str | None = None,
    **kwargs: Any,
) -> Div:
    """Textarea with optional label and error message.

    Args:
        name: The textarea name attribute (also used for id)
        label: Optional label text displayed above the textarea
        placeholder: Placeholder text shown when textarea is empty
        rows: Number of visible rows (default: 4)
        required: Whether the field is required
        error: Optional error message to display below the textarea
        **kwargs: Additional attributes passed to the Textarea element

    Returns:
        A Div containing the label (optional), textarea, and error (optional)

    Accessibility:
        - Uses aria-invalid to indicate error state
        - Links error message via aria-describedby
        - Error div has role="alert" for screen reader announcements
    """
    textarea_cls = (
        "w-full px-3 py-2 bg-base-100 border rounded-lg text-base-content "
        "placeholder:text-base-content/50 "
        "focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent "
        "resize-y"
    )

    if error:
        textarea_cls += " border-error"
    else:
        textarea_cls += " border-base-300"

    elements = []
    error_id = f"{name}-error"
    has_error = error is not None

    if label:
        label_cls = "block text-sm font-medium text-base-content mb-1.5"
        label_text = f"{label} *" if required else label
        elements.append(Label(label_text, cls=label_cls, for_=name))

    # Build ARIA attributes for accessibility
    aria_attrs = {}
    if has_error:
        aria_attrs["aria_invalid"] = "true"
        aria_attrs["aria_describedby"] = error_id

    elements.append(
        HtmlTextarea(
            name=name,
            placeholder=placeholder,
            rows=rows,
            cls=textarea_cls,
            id=name,
            required=required,
            **aria_attrs,
            **kwargs,
        )
    )

    # Error message with proper ARIA role for screen readers
    if error:
        elements.append(
            Div(
                error,
                id=error_id,
                role="alert",
                cls="mt-1 text-sm text-error",
            )
        )

    return Div(*elements, cls="space-y-1")


def SelectInput(
    name: str,
    options: list[tuple[str, str]],
    label: str | None = None,
    placeholder: str = "Select an option",
    required: bool = False,
    selected: str | None = None,
    error: str | None = None,
    **kwargs: Any,
) -> Div:
    """Select dropdown with optional label.

    Args:
        name: The select name attribute (also used for id)
        options: List of (value, display_text) tuples
        label: Optional label text displayed above the select
        placeholder: Placeholder text for the empty option
        required: Whether the field is required
        selected: Currently selected value
        error: Optional error message to display below the select
        **kwargs: Additional attributes passed to the Select element

    Returns:
        A Div containing the label (optional), select, and error (optional)

    Accessibility:
        - Uses aria-invalid to indicate error state
        - Links error message via aria-describedby
        - Error div has role="alert" for screen reader announcements
    """
    select_cls = (
        "w-full px-3 py-2 bg-base-100 border rounded-lg text-base-content "
        "focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
    )

    if error:
        select_cls += " border-error"
    else:
        select_cls += " border-base-300"

    elements = []
    error_id = f"{name}-error"
    has_error = error is not None

    if label:
        label_cls = "block text-sm font-medium text-base-content mb-1.5"
        label_text = f"{label} *" if required else label
        elements.append(Label(label_text, cls=label_cls, for_=name))

    # Build options
    option_elements = [Option(placeholder, value="", disabled=True, selected=(selected is None))]
    for value, display in options:
        option_elements.append(Option(display, value=value, selected=(value == selected)))

    # Build ARIA attributes for accessibility
    aria_attrs = {}
    if has_error:
        aria_attrs["aria_invalid"] = "true"
        aria_attrs["aria_describedby"] = error_id

    elements.append(
        Select(
            *option_elements,
            name=name,
            cls=select_cls,
            id=name,
            required=required,
            **aria_attrs,
            **kwargs,
        )
    )

    # Error message with proper ARIA role for screen readers
    if error:
        elements.append(
            Div(
                error,
                id=error_id,
                role="alert",
                cls="mt-1 text-sm text-error",
            )
        )

    return Div(*elements, cls="space-y-1")


def Checkbox(
    name: str,
    label: str,
    checked: bool = False,
    **kwargs: Any,
) -> Div:
    """Checkbox input with label.

    Args:
        name: The checkbox name attribute (also used for id)
        label: Label text displayed next to the checkbox
        checked: Whether the checkbox is initially checked
        **kwargs: Additional attributes passed to the Input element

    Returns:
        A Div containing the checkbox and label
    """
    checkbox_cls = (
        "h-4 w-4 rounded border-base-300 text-primary "
        "focus:ring-2 focus:ring-primary focus:ring-offset-2"
    )

    checkbox = HtmlInput(
        name=name,
        type="checkbox",
        cls=checkbox_cls,
        id=name,
        checked=checked,
        **kwargs,
    )

    label_element = Label(
        label,
        cls="text-sm text-base-content",
        for_=name,
    )

    return Div(
        checkbox,
        label_element,
        cls="flex items-center gap-2",
    )
