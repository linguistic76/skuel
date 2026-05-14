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
from ui.patterns.form_generator import FormGenerator

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
        "fields": ["decision_deadline"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "choice_type": "Choice type",
    "domain": "Domain",
    "priority": "Priority",
    "decision_deadline": "Decision deadline",
}

_FIELD_HELP: dict[str, str] = {
    "choice_type": "Single / Multiple / Binary — how this decision is structured.",
    "decision_deadline": "When the decision needs to be made by (optional).",
}


def ChoiceCreateForm() -> Any:
    """Render the Choice create form.

    POSTs ``application/x-www-form-urlencoded`` to ``/choices/create``. Options,
    decision_criteria, constraints, stakeholders, tags, and
    informed_by_knowledge_uids are not in this form — add them on the detail page.
    """
    return FormGenerator.from_model(
        ChoiceCreateRequest,
        action="/choices/create",
        method="POST",
        sections=_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        submit_label="Create Choice",
        form_attrs={"id": "choice-create-form"},
    )


def ChoiceEditForm(choice: Choice) -> Any:
    """Render the Choice edit form prefilled from an existing choice."""
    return FormGenerator.from_instance(
        ChoiceUpdateRequest,
        choice,
        action=f"/choices/edit?uid={choice.uid}",
        method="POST",
        sections=_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        submit_label="Save Changes",
        form_attrs={"id": "choice-edit-form"},
    )


__all__ = ["ChoiceCreateForm", "ChoiceEditForm"]
