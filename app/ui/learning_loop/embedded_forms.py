"""Embedded form rendering for PathStep detail pages.

Renders FormTemplates (embedded via EMBEDS_FORM) as inline HTMX forms.
Each form posts to /learning-loop/ps/{ps_uid}/forms/{template_uid}/submit
and swaps itself out with a success/error fragment.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, H4, Div, Form, Option, P

from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Label, LabelCheckbox, LabelInput, LabelTextArea, Select
from ui.patterns.csrf import csrf_hidden_input
from ui.patterns.error_banner import render_inline_error

if TYPE_CHECKING:
    from core.models.forms.form_template import FormTemplate


def render_embedded_forms(
    forms: list["FormTemplate"],
    ps_uid: str,
) -> Div:
    """Render all FormTemplates embedded in a PathStep as inline forms."""
    if not forms:
        return Div()

    return Div(
        H3("Forms", cls="text-base font-semibold mb-4"),
        *[_render_form(form, ps_uid) for form in forms],
        cls="border-t border-border pt-6 mt-8",
        id=f"ps-forms-{ps_uid}",
    )


def render_embedded_forms_success(form: "FormTemplate", ps_uid: str) -> Div:
    """Render a submission-confirmed card to replace the submitted form."""
    return Div(
        Card(
            CardBody(
                H4(form.title or "Form", cls="text-sm font-semibold mb-1"),
                P("Response submitted.", cls="text-sm text-muted-foreground"),
            ),
            cls="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/20",
        ),
        id=f"form-{form.uid}",
    )


def render_embedded_forms_error(form: "FormTemplate", ps_uid: str, message: str) -> Div:
    """Render the form again with an error banner above it (preserves user input is lost — HTMX swap)."""
    return Div(
        render_inline_error(message),
        _render_form(form, ps_uid),
        id=f"form-{form.uid}",
    )


def _render_form(form: "FormTemplate", ps_uid: str) -> Div:
    """Render a single FormTemplate as an HTMX-submittable inline form."""
    fields: list[Any] = [csrf_hidden_input()]

    if form.instructions:
        fields.append(P(form.instructions, cls="text-sm text-muted-foreground mb-4"))

    for spec in form.form_schema or ():
        fields.append(_render_field(spec))

    return Div(
        Card(
            CardBody(
                H4(form.title or "Form", cls="text-sm font-semibold mb-4"),
                Form(
                    *fields,
                    Button(
                        "Submit",
                        type="submit",
                        cls=(ButtonT.primary, "mt-4"),
                        size="sm",
                    ),
                    hx_post=f"/learning-loop/ps/{ps_uid}/forms/{form.uid}/submit",
                    hx_target=f'[id="form-{form.uid}"]',
                    hx_swap="outerHTML",
                ),
            ),
        ),
        id=f"form-{form.uid}",
    )


def _render_field(spec: dict[str, Any]) -> Any:
    """Render a single form schema field spec as an FT element."""
    name: str = spec.get("name", "")
    label: str = spec.get("label", name.replace("_", " ").title())
    field_type: str = spec.get("type", "text")
    required: bool = bool(spec.get("required", False))
    placeholder: str = str(spec.get("placeholder", ""))

    if field_type == "textarea":
        return LabelTextArea(
            label,
            name=name,
            required=required,
            placeholder=placeholder,
            cls="mb-4",
        )

    if field_type == "select":
        options: list[str] = spec.get("options", [])
        return Div(
            Label(label, fr=name),
            Select(
                Option("Select an option", value=""),
                *[Option(o, value=o) for o in options],
                name=name,
                id=name,
                required=required,
            ),
            cls="space-y-2 mb-4",
        )

    if field_type == "number":
        extra: dict[str, Any] = {}
        if spec.get("min") is not None:
            extra["min"] = spec["min"]
        if spec.get("max") is not None:
            extra["max"] = spec["max"]
        return LabelInput(
            label,
            name=name,
            required=required,
            placeholder=placeholder,
            type="number",
            cls="mb-4",
            **extra,
        )

    if field_type == "checkbox":
        return LabelCheckbox(label, name=name, value="true", cls="mb-4")

    if field_type == "date":
        return LabelInput(label, name=name, required=required, type="date", cls="mb-4")

    # default: text
    text_extra: dict[str, Any] = {}
    if spec.get("max_length") is not None:
        text_extra["maxlength"] = spec["max_length"]
    if spec.get("pattern") is not None:
        text_extra["pattern"] = spec["pattern"]
    return LabelInput(
        label,
        name=name,
        required=required,
        placeholder=placeholder,
        type="text",
        cls="mb-4",
        **text_extra,
    )
