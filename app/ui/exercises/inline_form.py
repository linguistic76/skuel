"""
Inline Exercise Form Renderer
===============================

Renders an Exercise's form_schema as an embeddable HTMX form.
When submitted, creates an ExerciseSubmission via POST /api/submissions/form.

Supported field types: text, textarea, select, checkbox, number, date.

Each field spec is a dict with:
    name (str): Field name (form input name)
    type (str): Widget type
    label (str): Display label
    required (bool, optional): Whether field is required (default: False)
    placeholder (str, optional): Input placeholder text
    options (list[str], optional): Select options (required for type=select)
"""

import json
from typing import Any

from fasthtml.common import H3, Div, Form, Option, P

from ui.buttons import Button, ButtonT
from ui.forms import Checkbox, Input, Label, Select, Textarea


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

    return Div(*children, cls="space-y-2")


def render_inline_exercise_form(
    exercise_uid: str,
    form_schema: list[dict[str, Any]],
    exercise_title: str | None = None,
) -> Any:
    """
    Render an Exercise's form_schema as an embeddable HTMX form.

    The form posts JSON to /api/submissions/form. On success, the form
    container is replaced with a success message.

    Args:
        exercise_uid: Exercise UID to link submission to
        form_schema: List of field spec dicts from Exercise.form_schema
        exercise_title: Optional title to display above the form
    """
    fields = [_build_field(spec) for spec in form_schema]

    # Collect field names for the Alpine.js submit handler
    field_names = [spec["name"] for spec in form_schema]

    header_parts: list[Any] = []
    if exercise_title:
        header_parts.append(H3(exercise_title, cls="text-base font-semibold mb-2"))

    # Success/error feedback container
    feedback = Div(id=f"form-feedback-{exercise_uid}", cls="mt-2")

    return Div(
        *header_parts,
        Form(
            *fields,
            # Submit button with loading state
            Button(
                "Submit",
                type="submit",
                variant=ButtonT.primary,
                cls="mt-4",
                **{
                    "x-text": "submitting ? 'Submitting...' : 'Submit'",
                    ":disabled": "submitting",
                    ":class": "submitting ? 'opacity-50 cursor-not-allowed' : ''",
                },
            ),
            feedback,
            # Alpine.js handles JSON submission
            x_data=json.dumps({"submitting": False, "submitted": False}),
            **{
                "@submit.prevent": _submit_handler(exercise_uid, field_names),
            },
            cls="space-y-4",
        ),
        cls="exercise-form-container border border-border rounded-lg p-6 my-6",
    )


def _submit_handler(exercise_uid: str, field_names: list[str]) -> str:
    """Generate Alpine.js submit handler that posts JSON to the form API."""
    # Build form_data object from named fields
    field_extractions = ", ".join(
        f"'{name}': $el.querySelector('[name={name}]')?.value || ''" for name in field_names
    )

    return (
        f"if (submitting) return; "
        f"submitting = true; "
        f"document.getElementById('form-feedback-{exercise_uid}').innerHTML = ''; "
        f"let formData = {{{field_extractions}}}; "
        f"let res = await fetch('/api/submissions/form', {{"
        f"method: 'POST', "
        f"headers: {{'Content-Type': 'application/json'}}, "
        f"body: JSON.stringify({{exercise_uid: '{exercise_uid}', form_data: formData}})"
        f"}}); "
        f"submitting = false; "
        f"if (res.ok) {{ "
        f"submitted = true; "
        f"let data = await res.json(); "
        f"$el.innerHTML = '<div class=\"space-y-3\">' "
        f"+ '<div class=\"uk-alert uk-alert-success\">Submitted successfully.</div>' "
        f'+ \'<a href="/submissions" class="text-primary underline text-sm">View Your Submissions</a>\' '
        f'+ \' <button onclick="location.reload()" class="text-sm text-muted-foreground underline ml-2">Submit Another</button>\' '
        f"+ '</div>'; "
        f"}} else {{ "
        f"let err = await res.json(); "
        f"document.getElementById('form-feedback-{exercise_uid}').innerHTML = "
        f"'<div class=\"uk-alert uk-alert-danger flex items-center justify-between\">' "
        f"+ '<span>' + (err.error || 'Submission failed') + '</span>' "
        f'+ \'<button onclick="this.parentElement.remove()" class="ml-2 font-bold">&times;</button>\' '
        f"+ '</div>'; "
        f"}}"
    )


__all__ = ["render_inline_exercise_form"]
