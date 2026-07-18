"""
Exercise Editor Form
=====================

Pure rendering function for the exercise create/edit form.
Imports Form/Input/Label/Textarea — the exact signal the route thinning rule flags.
"""

from typing import Any

from fasthtml.common import Div, Option, P

from ui.components import Button, ButtonT, Card
from ui.forms import Input, Label, Select, Textarea
from ui.patterns.section_header import SectionHeader


def render_exercise_editor(exercise: Any = None, mode: str = "create") -> Any:
    """Exercise editor form - TRANSPARENCY: User sees and edits instructions."""
    is_edit = mode == "edit"
    form_title = "Edit Exercise" if is_edit else "Create New Exercise"
    submit_url = f"/api/exercises/{exercise.uid}" if is_edit else "/api/exercises"
    submit_method = "put" if is_edit else "post"

    from fasthtml.common import Form

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
                        Option(
                            "Claude Sonnet 4.6 (Recommended)",
                            value="claude-sonnet-4-6",
                            selected=not exercise or exercise.model == "claude-sonnet-4-6",
                        ),
                        Option(
                            "Claude Opus 4.6 (Most Capable)",
                            value="claude-opus-4-6",
                            selected=exercise and exercise.model == "claude-opus-4-6",
                        ),
                        Option(
                            "Claude Haiku 4.5 (Fastest)",
                            value="claude-haiku-4-5-20251001",
                            selected=exercise and exercise.model == "claude-haiku-4-5-20251001",
                        ),
                        Option(
                            "GPT-4o",
                            value="gpt-4o",
                            selected=exercise and exercise.model == "gpt-4o",
                        ),
                        Option(
                            "GPT-4o Mini (Cheaper)",
                            value="gpt-4o-mini",
                            selected=exercise and exercise.model == "gpt-4o-mini",
                        ),
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
                # Domain (optional)
                Div(
                    Label("Domain (Optional)"),
                    Select(
                        Option("None", value=""),
                        Option("Personal", value="personal"),
                        Option("Health", value="health"),
                        Option("Learning", value="learning"),
                        Option("Work", value="work"),
                        name="domain",
                    ),
                    cls="mb-4",
                ),
                # Submit buttons
                Div(
                    Button("Save Exercise", type="submit", cls=(ButtonT.primary, "mr-2")),
                    Button(
                        "Cancel",
                        hx_get="/exercises",
                        hx_target="#main-content",
                        cls=ButtonT.ghost,
                    ),
                    cls="mb-4",
                ),
                **{
                    "hx-" + submit_method: submit_url,
                    "hx-target": "#main-content",
                    "hx-swap": "innerHTML",
                },
            ),
            cls="p-6",
        ),
        cls="container mx-auto p-6",
    )
