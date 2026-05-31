"""
Schema-Driven Field Builder
==============================

Builds a single form field (Div with label + widget) from a spec dict.
Shared by inline exercise forms and inline form-template forms.

Supported field types: text, textarea, select, checkbox, number, date.

Each field spec is a dict with:
    name (str): Field name (form input name)
    type (str): Widget type
    label (str): Display label
    required (bool, optional): Whether field is required (default: False)
    placeholder (str, optional): Input placeholder text
    options (list[str], optional): Select options (required for type=select)
    min_length / max_length (int, optional): Text length constraints
    min / max (number, optional): Number range constraints
    pattern (str, optional): Regex pattern for text inputs
    help_text (str, optional): Help text displayed below the field
"""

from typing import Any

from fasthtml.common import Div, Option, P

from ui.forms.components import Checkbox, Input, Label, Select, Textarea


def build_field_from_schema(spec: dict[str, Any]) -> Div:
    """Build a single form field from a schema spec dict."""
    name = spec["name"]
    label_text = spec["label"]
    field_type = spec["type"]
    required = spec.get("required", False)
    placeholder = spec.get("placeholder", f"Enter {label_text.lower()}...")

    attrs: dict[str, Any] = {"name": name}
    if required:
        attrs["required"] = True

    # Text-length and pattern constraints (text + textarea)
    if field_type in ("text", "textarea"):
        min_length = spec.get("min_length")
        max_length = spec.get("max_length")
        if min_length is not None:
            attrs["minlength"] = min_length
        if max_length is not None:
            attrs["maxlength"] = max_length

    if field_type == "textarea":
        widget = Textarea(rows=4, placeholder=placeholder, **attrs)
    elif field_type == "select":
        options_list = spec.get("options", [])
        option_elements = [Option("-- Select --", value="", selected=True)]
        option_elements.extend(Option(opt, value=opt) for opt in options_list)
        widget = Select(*option_elements, **attrs)
    elif field_type == "checkbox":
        widget = Checkbox(**attrs)
    elif field_type == "number":
        min_val = spec.get("min")
        max_val = spec.get("max")
        if min_val is not None:
            attrs["min"] = min_val
        if max_val is not None:
            attrs["max"] = max_val
        widget = Input(type="number", placeholder=placeholder, **attrs)
    elif field_type == "date":
        widget = Input(type="date", **attrs)
    else:
        # Default: text input
        pattern = spec.get("pattern")
        if pattern is not None:
            attrs["pattern"] = pattern
        widget = Input(type="text", placeholder=placeholder, **attrs)

    children: list[Any] = [
        Label(label_text, required=required),
        widget,
    ]

    help_text = spec.get("help_text")
    if help_text:
        children.append(P(help_text, cls="text-sm text-muted-foreground mt-1"))

    return Div(*children, cls="space-y-2")


__all__ = ["build_field_from_schema"]
