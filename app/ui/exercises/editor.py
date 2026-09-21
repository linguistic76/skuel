"""
Exercise Editor Form
=====================

Pure rendering function for the exercise create/edit form.
"""

from typing import Any

from fasthtml.common import Div, Form, Option, P

from core.models.enums.entity_enums import Domain
from ui.components import Button, ButtonT, Card
from ui.forms import Input, Label, Select, Textarea
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink

#: The domains the editor offers, in display order — every value a ``Domain`` member,
#: because the request model rejects anything else. ``Entity.domain`` always holds a
#: value (``Domain.KNOWLEDGE`` is its default), so the default is offered as itself and
#: the select never submits a blank that would clear the stored property.
EDITOR_DOMAINS: tuple[tuple[str, Domain], ...] = (
    ("Knowledge (default)", Domain.KNOWLEDGE),
    ("Personal", Domain.PERSONAL),
    ("Health", Domain.HEALTH),
    ("Learning", Domain.LEARNING),
    ("Business", Domain.BUSINESS),
)

#: The models the editor offers, in display order; the first is the default. A stored
#: model outside this list is appended at render time so an edit never re-points the
#: feedback model as a side effect.
EDITOR_MODELS: tuple[tuple[str, str], ...] = (
    ("Claude Sonnet 4.6 (Recommended)", "claude-sonnet-4-6"),
    ("Claude Opus 4.6 (Most Capable)", "claude-opus-4-6"),
    ("Claude Haiku 4.5 (Fastest)", "claude-haiku-4-5-20251001"),
    ("GPT-4o", "gpt-4o"),
    ("GPT-4o Mini (Cheaper)", "gpt-4o-mini"),
)

#: After a successful save the editor leaves for the dashboard; a failed save keeps
#: the form (the error rides the response's toast headers). ``hx_swap="none"`` because
#: the CRUD door answers the JSON entity, not a fragment.
_AFTER_SAVE = "if(event.detail.successful){window.location.href='/exercises'}"


def render_exercise_editor(exercise: Any = None, mode: str = "create") -> Any:
    """Exercise editor form - TRANSPARENCY: User sees and edits instructions.

    Posts its fields form-encoded to the CRUD factory's write doors
    (``POST /api/exercises/create`` / ``POST /api/exercises/update?uid=``), which
    read either encoding by Content-Type.
    """
    is_edit = mode == "edit"
    form_title = "Edit Exercise" if is_edit else "Create New Exercise"
    submit_url = f"/api/exercises/update?uid={exercise.uid}" if is_edit else "/api/exercises/create"
    # The stored domain and model are always selectable: one the list does not offer
    # is appended as its own option, so a save that touches unrelated fields never
    # changes it.
    current_domain = str(exercise.domain) if exercise else Domain.KNOWLEDGE.value
    domain_options = list(EDITOR_DOMAINS)
    if current_domain not in {d.value for _label, d in EDITOR_DOMAINS}:
        domain_options.append((current_domain.replace("_", " ").title(), Domain(current_domain)))
    current_model = exercise.model if exercise else EDITOR_MODELS[0][1]
    model_options = list(EDITOR_MODELS)
    if current_model not in {value for _label, value in EDITOR_MODELS}:
        model_options.append((current_model, current_model))

    return Div(
        SectionHeader(form_title),
        Card(
            Form(
                # Exercise name
                Div(
                    Label("Exercise Name"),
                    Input(
                        type="text",
                        name="name",
                        value=exercise.title if exercise else "",
                        placeholder="e.g., Daily Reflection, Principle Mining",
                        required=True,
                    ),
                    cls="mb-4",
                ),
                # Instructions - THE KEY TRANSPARENCY ELEMENT
                Div(
                    Label("Instructions (Visible to You & LLM)", cls="font-semibold"),
                    P(
                        "These are the exact instructions sent to the LLM. "
                        "Be clear and specific about what kind of feedback you want.",
                        cls="text-sm text-muted-foreground mb-2",
                    ),
                    Textarea(
                        exercise.instructions if exercise else "",
                        name="instructions",
                        rows="8",
                        placeholder=(
                            "Example:\n\nRead my entry and ask me one "
                            "clarifying question about the emotions I "
                            "describe. Focus on self-awareness."
                        ),
                        required=True,
                    ),
                    cls="mb-4",
                ),
                # Model selection
                Div(
                    Label("LLM Model"),
                    Select(
                        *[
                            Option(label, value=value, selected=(value == current_model))
                            for label, value in model_options
                        ],
                        name="model",
                    ),
                    cls="mb-4",
                ),
                # Context notes (optional)
                Div(
                    Label("Context Notes (Optional)"),
                    P(
                        "Reference materials or context the LLM should consider. One per line.",
                        cls="text-sm text-muted-foreground mb-2",
                    ),
                    Textarea(
                        "\n".join(exercise.context_notes)
                        if exercise and exercise.context_notes
                        else "",
                        name="context_notes",
                        rows="4",
                        placeholder=(
                            "Focus on self-awareness\n"
                            "Be gentle and curious\n"
                            "Reference my core principles"
                        ),
                    ),
                    cls="mb-4",
                ),
                # Domain
                Div(
                    Label("Domain"),
                    Select(
                        *[
                            Option(
                                label, value=domain.value, selected=(domain.value == current_domain)
                            )
                            for label, domain in domain_options
                        ],
                        name="domain",
                    ),
                    cls="mb-4",
                ),
                # Submit buttons
                Div(
                    Button("Save Exercise", type="submit", cls=(ButtonT.primary, "mr-2")),
                    ButtonLink("Cancel", href="/exercises", cls=ButtonT.ghost),
                    cls="mb-4 flex flex-wrap gap-2",
                ),
                hx_post=submit_url,
                hx_swap="none",
                **{"hx-on::after-request": _AFTER_SAVE},
            ),
            cls="p-6",
        ),
        cls="container mx-auto p-6",
    )
