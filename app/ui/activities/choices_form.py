"""
Choice create / edit form
=========================

FormGenerator-rendered Choice forms used by ``adapters/inbound/choices_ui.py``
(``GET /choices/create`` and ``GET /choices/edit``).

The nested ``options`` list and the free-text list fields (``decision_criteria``,
``constraints``, ``stakeholders``, ``tags``) are intentionally omitted — they hit
the FormGenerator list-input bug and belong on the detail page anyway. Cross-domain
relationships (``informed_by_knowledge_uids``) are list-typed and assigned via the
detail-page relationship picker.
"""

from __future__ import annotations

from typing import Any

from core.models.choice.choice import Choice
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceUpdateRequest
from ui.patterns.activity_form_helper import render_activity_form

_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description"]},
    "Classification": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["choice_type", "domain", "priority"],
    },
    "Decision": {
        "icon": "calendar",
        "accent": "amber",
        "fields": ["decision_context", "decision_deadline"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "choice_type": "Choice type",
    "domain": "Domain",
    "priority": "Priority",
    "decision_context": "Situation",
    "decision_deadline": "Decision deadline",
}

_FIELD_HELP: dict[str, str] = {
    "choice_type": "Single / Multiple / Binary — how this decision is structured.",
    "decision_context": "What is going on that forces this choice? The circumstance, "
    "not the reasoning for whichever option you end up picking.",
    "decision_deadline": "When the decision needs to be made by (optional).",
}


def ChoiceCreateForm() -> Any:
    """Render the Choice create form."""
    return render_activity_form(
        domain_slug="choices",
        entity_name="Choice",
        request_model=ChoiceCreateRequest,
        operation="create",
        sections=_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
    )


def ChoiceEditForm(choice: Choice) -> Any:
    """Render the Choice edit form prefilled from an existing choice."""
    return render_activity_form(
        domain_slug="choices",
        entity_name="Choice",
        request_model=ChoiceUpdateRequest,
        operation="edit",
        sections=_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        entity=choice,
    )


__all__ = ["ChoiceCreateForm", "ChoiceEditForm"]
