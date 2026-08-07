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

from fasthtml.common import H3, Div, Form, P, Small, Span

from ui.components import Button, ButtonT
from ui.forms.components import Checkbox, Input, Label
from ui.forms.field_builder import build_field_from_schema


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
    fields = [build_field_from_schema(spec) for spec in form_schema]

    header_parts: list[Any] = []
    if title:
        header_parts.append(H3(title, cls="text-base font-semibold mb-2"))
    if instructions:
        header_parts.append(P(instructions, cls="text-sm text-muted-foreground mb-4"))

    # Success/error feedback container
    feedback = Div(id=f"form-feedback-{form_template_uid}", cls="mt-2")

    # Sharing controls (collapsible)
    sharing_section = Div(
        Div(
            Small(
                "Sharing options",
                cls="text-muted-foreground cursor-pointer underline",
                **{"@click": "showSharing = !showSharing"},
            ),
            cls="mt-2",
        ),
        Div(
            Div(
                Checkbox(name="share_with_admin"),
                Span("Send to teacher/admin", cls="ml-2 text-sm"),
                cls="flex items-center",
            ),
            Div(
                Label("Share with (comma-separated user IDs)"),
                Input(
                    type="text",
                    name="recipient_uids",
                    placeholder="user_abc123, user_def456",
                ),
                cls="space-y-1 mt-2",
            ),
            x_show="showSharing",
            cls="space-y-2 mt-2 p-3 border border-border rounded-sm",
        ),
    )

    return Div(
        *header_parts,
        Form(
            *fields,
            # Submit button with loading state
            Button(
                "Submit",
                type="submit",
                cls=(ButtonT.primary, "mt-4"),
                **{  # fasthtml dynamic-attr splat
                    "x-text": "submitting ? 'Submitting...' : 'Submit'",
                    ":disabled": "submitting",
                    ":class": "submitting ? 'opacity-50 cursor-not-allowed' : ''",
                },
            ),
            sharing_section,
            feedback,
            # Alpine.js handles JSON submission
            x_data=json.dumps({"submitting": False, "submitted": False, "showSharing": False}),
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
        f"document.getElementById('form-feedback-{form_template_uid}').innerHTML = ''; "
        f"let formData = {{{field_extractions}}}; "
        f"let shareAdmin = $el.querySelector('[name=share_with_admin]')?.checked || false; "
        f"let recipientRaw = $el.querySelector('[name=recipient_uids]')?.value || ''; "
        f"let recipientUids = recipientRaw ? recipientRaw.split(',').map(function(s){{return s.trim()}}).filter(function(s){{return s}}) : null; "
        f"let res = await fetch('/api/form-submissions/submit', {{"
        f"method: 'POST', "
        f"headers: {{'Content-Type': 'application/json'}}, "
        f"body: JSON.stringify({{form_template_uid: '{form_template_uid}', form_data: formData, share_with_admin: shareAdmin, recipient_uids: recipientUids}})"
        f"}}); "
        f"submitting = false; "
        f"if (res.ok) {{ "
        f"submitted = true; "
        f"let data = await res.json(); "
        f"let uid = data.submission?.uid || ''; "
        f"$el.innerHTML = '<div class=\"space-y-3\">' "
        f"+ '<div class=\"p-4 rounded-lg bg-green-50 text-green-800 border border-green-200\">Submitted successfully.</div>' "
        f"+ (uid ? '<a href=\"/my-forms/detail?uid=' + uid + '\" class=\"text-primary underline text-sm\">View Submission</a>' : '') "
        f'+ \' <button onclick="location.reload()" class="text-sm text-muted-foreground underline ml-2">Submit Another</button>\' '
        f"+ '</div>'; "
        f"}} else {{ "
        f"let err = await res.json(); "
        f"document.getElementById('form-feedback-{form_template_uid}').innerHTML = "
        f"'<div class=\"p-4 rounded-lg bg-red-50 text-red-800 border border-red-200 flex items-center justify-between\">' "
        f"+ '<span>' + (err.error || 'Submission failed') + '</span>' "
        f'+ \'<button onclick="this.parentElement.remove()" class="ml-2 font-bold">&times;</button>\' '
        f"+ '</div>'; "
        f"}}"
    )


__all__ = ["render_inline_form_template"]
