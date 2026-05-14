"""
Activity form helper
====================

Thin wrapper around ``FormGenerator`` that encodes the three conventions every
activity domain form shares:

- action URL pattern: ``/{slug}/create`` and ``/{slug}/edit?uid={uid}`` (plural slug)
- submit label pattern: ``"Create {Entity}"`` / ``"Save Changes"``
- form id pattern: ``{entity}-{create|edit}-form`` (singular entity, lowercased)

Everything genuinely per-domain (sections, labels, help text, EntityPicker
widgets, prefill overrides) stays as plain dicts passed through.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ui.patterns.form_generator import FormGenerator


def render_activity_form(
    *,
    domain_slug: str,
    entity_name: str,
    request_model: type[BaseModel],
    operation: Literal["create", "edit"],
    sections: dict[str, dict[str, Any]],
    labels: dict[str, str] | None = None,
    help_texts: dict[str, str] | None = None,
    custom_widgets: dict[str, Any] | None = None,
    entity: Any = None,
    values: dict[str, Any] | None = None,
) -> Any:
    """Render an activity domain create or edit form with SKUEL conventions.

    ``entity`` is required when ``operation="edit"`` — its ``uid`` builds the
    action URL and (unless ``values`` is supplied) its fields prefill the form.
    Pass ``values`` to override the prefill when request-model field names
    diverge from the domain model (e.g. Habit's ``name`` vs ``title``).
    """
    entity_slug = entity_name.lower()
    if operation == "create":
        action = f"/{domain_slug}/create"
        submit_label = f"Create {entity_name}"
        form_id = f"{entity_slug}-create-form"
    else:
        if entity is None:
            raise ValueError("entity is required when operation='edit'")
        action = f"/{domain_slug}/edit?uid={entity.uid}"
        submit_label = "Save Changes"
        form_id = f"{entity_slug}-edit-form"

    common: dict[str, Any] = {
        "action": action,
        "method": "POST",
        "sections": sections,
        "labels": labels or {},
        "help_texts": help_texts or {},
        "custom_widgets": custom_widgets or {},
        "submit_label": submit_label,
        "form_attrs": {"id": form_id},
    }

    if operation == "edit" and values is None:
        return FormGenerator.from_instance(request_model, entity, **common)

    if values is not None:
        return FormGenerator.from_model(request_model, values=values, **common)

    return FormGenerator.from_model(request_model, **common)


__all__ = ["render_activity_form"]
