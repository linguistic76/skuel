"""
Inline Form Template Renderer
================================

Renders a FormTemplate's form_schema as an embeddable HTMX form.
When submitted, creates a FormSubmission via POST /api/form-submissions/submit.

Reuses the same _build_field() logic from ui/exercises/inline_form.py but
posts to a different endpoint and includes quick-share controls.

Supported field types: text, textarea, select, checkbox, number, date.
"""

import json
from typing import Any

from fasthtml.common import H3, Div, Form, Option, P

from ui.buttons import Button, ButtonT
from ui.forms.components import Checkbox, Input, Label, Select, Textarea


def _build_field(spec: dict[str, Any]) -> Div:
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
        Label(label_text, **({"required": True} if required else {})),
        widget,
    ]

    help_text = spec.get("help_text")
    if help_text:
        children.append(P(help_text, cls="text-sm text-muted-foreground mt-1"))

    return Div(*children, cls="form-control")


def render_inline_form_template(
    form_template_uid: str,
    form_schema: list[dict[str, Any]],
    title: str | None = None,
    instructions: str | None = None,
) -> Any:
    """
    Render a FormTemplate's form_schema as an embeddable HTMX form.

    The form posts JSON to /api/form-submissions/submit. On success, the form
    container is replaced with a success message.

    Args:
        form_template_uid: FormTemplate UID to link submission to
        form_schema: List of field spec dicts from FormTemplate.form_schema
        title: Optional title to display above the form
        instructions: Optional instructions text
    """
    fields = [_build_field(spec) for spec in form_schema]

    header_parts: list[Any] = []
    if title:
        header_parts.append(H3(title, cls="text-base font-semibold mb-2"))
    if instructions:
        header_parts.append(P(instructions, cls="text-sm text-muted-foreground mb-4"))

    # Success/error feedback container
    feedback = Div(id=f"form-feedback-{form_template_uid}", cls="mt-2")

    return Div(
        *header_parts,
        Form(
            *fields,
            # Submit button
            Button("Submit", type="submit", variant=ButtonT.primary, cls="mt-4"),
            feedback,
            # Alpine.js handles JSON submission
            x_data=json.dumps({"submitting": False, "submitted": False}),
            **{
                "@submit.prevent": _submit_handler(form_template_uid, form_schema),
            },
            cls="space-y-4",
        ),
        cls="form-template-container border border-border rounded-lg p-6 my-6",
    )


def _submit_handler(form_template_uid: str, field_specs: list[dict[str, Any]]) -> str:
    """Generate Alpine.js submit handler that posts JSON to the form submission API."""
    # Build form_data object from named fields (checkboxes use .checked, others use .value)
    extractions = []
    for spec in field_specs:
        name = spec["name"]
        if spec["type"] == "checkbox":
            extractions.append(f"'{name}': $el.querySelector('[name={name}]')?.checked || false")
        else:
            extractions.append(f"'{name}': $el.querySelector('[name={name}]')?.value || ''")
    field_extractions = ", ".join(extractions)

    return (
        f"if (submitting) return; "
        f"submitting = true; "
        f"let formData = {{{field_extractions}}}; "
        f"let res = await fetch('/api/form-submissions/submit', {{"
        f"method: 'POST', "
        f"headers: {{'Content-Type': 'application/json'}}, "
        f"body: JSON.stringify({{form_template_uid: '{form_template_uid}', form_data: formData}})"
        f"}}); "
        f"submitting = false; "
        f"if (res.ok) {{ "
        f"submitted = true; "
        f"$el.innerHTML = '<div class=\"alert alert-success\">Submitted successfully.</div>'; "
        f"}} else {{ "
        f"let err = await res.json(); "
        f"document.getElementById('form-feedback-{form_template_uid}').innerHTML = "
        f"'<div class=\"alert alert-error\">' + (err.error || 'Submission failed') + '</div>'; "
        f"}}"
    )


__all__ = ["render_inline_form_template"]
