"""Add-relationship authoring modal — one modal, four lateral edge types.

A single "Add relationship" button opens an :func:`AlpineModal` holding a type
selector and one sub-form per authorable lateral type (BLOCKS / PREREQUISITE_FOR
/ ALTERNATIVE_TO / COMPLEMENTARY_TO). The selector (``x-model="relType"``) reveals
exactly one sub-form via ``x-show``; each sub-form posts *directly* to its
existing ``POST /api/{domain}/{uid}/lateral/{segment}`` route (no duplicated
create logic) with ``hx_swap="none"``.

On success the route emits ``HX-Trigger: relationships-changed``; the modal's
``x-on:relationships-changed.window`` closes it and the shared readers/graph
refresh off the same event. Errors surface via the global toast handler
(``X-Toast-Message``) and leave the modal open.

Target selection reuses :func:`EntityPicker`; CSRF rides the global
``htmx:configRequest`` ``X-CSRF-Token`` header (no hidden field needed).

Authoring is currently enabled for entity types the picker supports
(task/goal/habit); DEPENDS_ON has its own task-scoped section.
"""

from __future__ import annotations

from fasthtml.common import H3, Div, Form, Option, Span

from core.models.relationship_names import RelationshipName
from ui.components.button import Button, ButtonT
from ui.forms import Input, LabelSelect, Select
from ui.patterns.entity_picker import EntityPicker
from ui.patterns.modal import AlpineModal

__all__ = ["AddRelationshipModal", "PICKER_TYPES"]

# entity_type (route form) → EntityPicker target_type. Only these support authoring.
PICKER_TYPES: dict[str, str] = {"tasks": "task", "goals": "goal", "habits": "habit"}

# (relType value, path segment, label) for each authorable lateral type.
# relType speaks the canonical RelationshipName value (drives x-model/x-show).
_LATERAL_FORMS: tuple[tuple[str, str, str], ...] = (
    (RelationshipName.BLOCKS.value, "blocks", "Blocks"),
    (RelationshipName.PREREQUISITE_FOR.value, "prerequisites", "Prerequisite for"),
    (RelationshipName.ALTERNATIVE_TO.value, "alternatives", "Alternative to"),
    (RelationshipName.COMPLEMENTARY_TO.value, "complementary", "Complementary to"),
)


def _sub_form(
    entity_uid: str,
    entity_type: str,
    picker_type: str,
    rel_value: str,
    segment: str,
    *metadata_fields: object,
) -> Div:
    """One lateral sub-form, shown only when the selector matches ``rel_value``."""
    return Div(
        Form(
            EntityPicker(
                name="target_uid",
                target_type=picker_type,
                exclude_uid=entity_uid,
                required=True,
            ),
            *metadata_fields,
            Button("Add relationship", type="submit", cls=ButtonT.primary, size="sm"),
            hx_post=f"/api/{entity_type}/{entity_uid}/lateral/{segment}",
            hx_swap="none",
            cls="space-y-3",
            # Clear inputs after a successful write so a reopened modal is fresh.
            **{"hx-on::after-request": "if (event.detail.successful) this.reset()"},
        ),
        **{"x-show": f"relType === '{rel_value}'"},
    )


def AddRelationshipModal(entity_uid: str, entity_type: str) -> Div:
    """Render the "Add relationship" button + authoring modal for an entity.

    Args:
        entity_uid: The entity the new edge originates from.
        entity_type: Route-form domain (e.g. ``"tasks"``) — also picks the
            EntityPicker target type.
    """
    picker_type = PICKER_TYPES.get(entity_type, "task")

    severity_select = Select(
        Option("Required", value="required"),
        Option("Recommended", value="recommended"),
        Option("Suggested", value="suggested"),
        name="severity",
        aria_label="Blocking severity",
    )

    blocks_form = _sub_form(
        entity_uid,
        entity_type,
        picker_type,
        RelationshipName.BLOCKS.value,
        "blocks",
        Input(name="reason", placeholder="Why must this finish first?", required=True),
        severity_select,
    )
    prereq_form = _sub_form(
        entity_uid,
        entity_type,
        picker_type,
        RelationshipName.PREREQUISITE_FOR.value,
        "prerequisites",
        Input(name="reasoning", placeholder="Why is this a prerequisite? (optional)"),
    )
    alt_form = _sub_form(
        entity_uid,
        entity_type,
        picker_type,
        RelationshipName.ALTERNATIVE_TO.value,
        "alternatives",
        Input(name="comparison_criteria", placeholder="How do these compare?", required=True),
    )
    comp_form = _sub_form(
        entity_uid,
        entity_type,
        picker_type,
        RelationshipName.COMPLEMENTARY_TO.value,
        "complementary",
        Input(name="synergy_description", placeholder="How do these complement?", required=True),
    )

    modal = AlpineModal(
        H3("Add relationship", cls="text-lg font-bold mb-4"),
        LabelSelect(
            *[Option(label, value=value) for value, _seg, label in _LATERAL_FORMS],
            label="Relationship type",
            name="__rel_type_selector",
            **{"x-model": "relType"},
        ),
        Div(
            blocks_form,
            prereq_form,
            alt_form,
            comp_form,
            cls="mt-4",
        ),
        Div(
            Button(
                "Cancel",
                type="button",
                cls=ButtonT.ghost,
                size="sm",
                **{"x-on:click": "open = false"},
            ),
            cls="mt-4 flex justify-end",
        ),
        show="open",
        close="open = false",
        max_width="max-w-lg",
        id=f"add-rel-modal-{entity_uid}",
    )

    return Div(
        Button(
            Span("＋ ", cls="font-bold"),
            "Add relationship",
            type="button",
            cls=ButtonT.primary,
            size="sm",
            **{"x-on:click": "open = true"},
        ),
        modal,
        # relType seeds the selector; a successful write dispatches
        # relationships-changed (via HX-Trigger) which closes the modal.
        **{
            "x-data": f"{{ open: false, relType: '{RelationshipName.BLOCKS.value}' }}",
            "x-on:relationships-changed.window": "open = false",
        },
    )
