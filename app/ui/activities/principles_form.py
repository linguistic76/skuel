"""
Principle create / edit form
============================

FormGenerator-rendered Principle forms used by ``adapters/inbound/principles_ui.py``
(``GET /principles/create`` and ``GET /principles/edit``).

List-typed fields (``key_behaviors``, ``decision_criteria``, ``tags``) and the nested
``expressions`` list are intentionally omitted — list inputs hit the FormGenerator
list-input bug, and structured nested fields belong on the detail page. Cross-domain
links to goals / habits / knowledge are list-typed and assigned via the detail-page
relationship picker.

PrincipleUpdateRequest uses ``category`` / ``source`` while the Principle domain
model uses ``principle_category`` / ``principle_source``, so the edit form passes
an explicit ``values`` dict to bridge those field names.
"""

from __future__ import annotations

from typing import Any

from core.models.principle.principle import Principle, split_why_important
from core.models.principle.principle_request import PrincipleCreateRequest, PrincipleUpdateRequest
from ui.patterns.activity_form_helper import render_activity_form

_CREATE_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "statement", "description"],
    },
    "Classification": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["category", "source", "strength"],
    },
    "Context": {
        "icon": "book-open",
        "accent": "cyan",
        "fields": ["tradition", "original_source", "personal_interpretation"],
    },
    "Reflection": {
        "icon": "flame",
        "accent": "rose",
        "fields": ["why_important", "origin_story"],
    },
    "Organization": {"icon": "flag", "accent": "amber", "fields": ["priority"]},
}

_EDIT_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "statement", "description"],
    },
    "Classification": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["category", "source", "strength", "priority"],
    },
    "Context": {
        "icon": "book-open",
        "accent": "cyan",
        "fields": ["tradition", "personal_interpretation"],
    },
    "Reflection": {
        "icon": "flame",
        "accent": "rose",
        "fields": ["why_important"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "statement": "Statement",
    "description": "Description",
    "category": "Category",
    "source": "Source",
    "strength": "Strength",
    "tradition": "Tradition / school of thought",
    "original_source": "Original source text",
    "personal_interpretation": "Personal interpretation",
    "why_important": "Why this matters",
    "origin_story": "Origin story",
    "priority": "Priority",
}

_FIELD_HELP: dict[str, str] = {
    "statement": "Short, memorable expression of the principle.",
    "description": "Fuller explanation. Optional — leave blank if the statement says it all.",
    "tradition": "Philosophical, religious, or cultural tradition this comes from (optional).",
    "original_source": "Specific text, author, or speaker if applicable.",
    "personal_interpretation": "Your reading of it — how you understand it in practice.",
    "why_important": "What changes for you if you live by this?",
    "origin_story": "How you came to hold this principle.",
}


def PrincipleCreateForm() -> Any:
    """Render the Principle create form."""
    return render_activity_form(
        domain_slug="principles",
        entity_name="Principle",
        request_model=PrincipleCreateRequest,
        operation="create",
        sections=_CREATE_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
    )


def PrincipleEditForm(principle: Principle) -> Any:
    """Render the Principle edit form prefilled from an existing principle.

    Bridges the request-model / domain-model field-name mismatch via ``values``.
    ``why_important`` lives inside ``description`` (no dedicated model field) —
    split it back out so the field round-trips through edit.
    """
    description, why_important = split_why_important(principle.description)
    return render_activity_form(
        domain_slug="principles",
        entity_name="Principle",
        request_model=PrincipleUpdateRequest,
        operation="edit",
        sections=_EDIT_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        entity=principle,
        values={
            "title": principle.title,
            "statement": principle.statement,
            "description": description,
            "category": principle.principle_category,
            "source": principle.principle_source,
            "strength": principle.strength,
            "tradition": principle.tradition,
            "personal_interpretation": principle.personal_interpretation,
            "why_important": why_important,
            "priority": principle.priority,
        },
    )


__all__ = ["PrincipleCreateForm", "PrincipleEditForm"]
