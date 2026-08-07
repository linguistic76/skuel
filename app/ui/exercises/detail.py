"""
Exercise Detail & View Components
===================================

Pure rendering functions for exercise detail and transparency views.
"""

from typing import Any

from fasthtml.common import H3, H4, A, Code, Div, Li, P, Pre, Span, Ul

from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.feedback import Alert, AlertT, Badge, BadgeT
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink
from ui.tokens import Container, Spacing


def render_exercise_view(exercise: Any, required_knowledge: list | None = None) -> Any:
    """View exercise details - TRANSPARENCY: Show exact prompt."""
    # Example entry for preview
    example_entry = "Today I felt overwhelmed by all the tasks on my plate..."

    # Show what the actual prompt would look like
    example_prompt = exercise.get_feedback_prompt(example_entry)

    # Knowledge Foundation section — shows which Kus anchor this exercise
    knowledge_section: Any = ""
    if required_knowledge:
        ku_links = [
            A(
                ku.get("title") or ku.get("uid", "Untitled"),
                href=f"/explore/ku/{ku.get('uid')}",
                cls="text-primary hover:underline mr-3",
            )
            for ku in required_knowledge
        ]
        knowledge_section = Card(
            Div(
                H3("Knowledge Foundation (Ku)", cls="text-lg font-semibold mb-2"),
                P(
                    "This exercise develops understanding of:",
                    cls="text-muted-foreground mb-2",
                ),
                Div(*ku_links),
                cls="p-4",
            ),
            cls="mb-4",
        )

    return Div(
        SectionHeader(exercise.title),
        # Knowledge Foundation — Ku origin of this exercise
        knowledge_section,
        # Transparency notice
        Alert(
            H3("Full Transparency", cls="text-lg font-semibold mb-3"),
            P(
                "Below you can see exactly what gets sent to the "
                "LLM when you request feedback. "
                "No hidden prompts, no black boxes.",
            ),
            variant=AlertT.info,
            cls="mb-4",
        ),
        # Instructions
        Card(
            CardHeader(CardTitle("Instructions")),
            CardBody(
                Pre(
                    Code(exercise.instructions, cls="text-sm"),
                    cls="bg-muted p-4 rounded-sm overflow-x-auto",
                ),
            ),
            cls="mb-4",
        ),
        # Model
        Card(
            CardHeader(CardTitle("Model")),
            CardBody(P(f"{exercise.model}", cls="text-muted-foreground")),
            cls="mb-4",
        ),
        # Context notes
        (
            Card(
                CardHeader(CardTitle("Context Notes")),
                CardBody(
                    Ul(
                        *[Li(note, cls="text-muted-foreground") for note in exercise.context_notes],
                        cls="list-disc list-inside",
                    ),
                ),
                cls="mb-4",
            )
            if exercise.context_notes
            else ""
        ),
        # Example prompt preview
        Card(
            CardHeader(CardTitle("Example Prompt Preview")),
            CardBody(
                P(
                    "Here's what the complete prompt would look like with an example entry:",
                    cls="text-muted-foreground mb-3",
                ),
                Pre(
                    Code(example_prompt, cls="text-sm"),
                    cls="bg-muted p-4 rounded-sm overflow-x-auto",
                ),
            ),
            cls="mb-4",
        ),
        # Action buttons
        Div(
            Button(
                "Edit Exercise",
                hx_get=f"/exercises/{exercise.uid}/edit",
                hx_target="#main-content",
                cls=(ButtonT.primary, "mr-2"),
            ),
            Button(
                "Back to Exercises",
                hx_get="/exercises",
                hx_target="#main-content",
                cls=ButtonT.ghost,
            ),
            cls="mt-4",
        ),
        cls="container mx-auto p-6",
    )


def render_exercise_student_detail(exercise: Any, from_ps: str = "") -> Any:
    """Student-facing exercise detail page body.

    Shows title, description, metadata badges, form field preview,
    instructions (transparency), and action buttons (Download + Submit).
    """
    # ── Metadata badges ───────────────────────────────────────────────
    meta_items: list[Any] = []
    if exercise.sel_category:
        label = getattr(exercise.sel_category, "value", str(exercise.sel_category))
        meta_items.append(Badge(label.replace("_", " ").title(), variant=BadgeT.primary))
    if exercise.learning_level:
        level = getattr(exercise.learning_level, "value", str(exercise.learning_level))
        meta_items.append(Badge(level.title(), variant=BadgeT.ghost))
    if exercise.estimated_time_minutes:
        meta_items.append(Badge(f"{exercise.estimated_time_minutes} min", variant=BadgeT.ghost))
    if exercise.mastery_impact:
        impact = getattr(exercise.mastery_impact, "value", str(exercise.mastery_impact))
        meta_items.append(Badge(f"{impact.title()} impact", variant=BadgeT.info))
    metadata_row = Div(*meta_items, cls="flex flex-wrap gap-2 mb-6") if meta_items else Div()

    # ── Description ───────────────────────────────────────────────────
    description_section = (
        P(exercise.description, cls="text-base-content/70 mb-6") if exercise.description else Div()
    )

    # ── Form fields preview ───────────────────────────────────────────
    form_fields_section: Any = Div()
    if exercise.form_schema:
        field_rows = []
        for field in exercise.form_schema:
            label_text = field.get("label", field.get("name", ""))
            required = field.get("required", False)
            field_type = field.get("type", "text")
            options = field.get("options", [])

            type_hint = field_type
            if options:
                type_hint = f"select: {', '.join(str(o) for o in options)}"

            field_rows.append(
                Div(
                    Div(
                        Span(label_text, cls="text-sm font-medium text-base-content"),
                        Span(" *", cls="text-error text-sm") if required else Span(),
                        cls="flex items-baseline gap-0.5",
                    ),
                    Span(type_hint, cls="text-xs text-base-content/50 mt-0.5"),
                    cls="py-3 border-b border-base-200 last:border-0",
                )
            )

        form_fields_section = Div(
            H4("What You'll Submit", cls="text-base font-semibold mb-3"),
            Div(*field_rows, cls="bg-base-200/40 rounded-lg px-4 mb-6"),
        )

    # ── Instructions (transparency) ────────────────────────────────────
    instructions_section: Any = Div()
    if exercise.instructions:
        from fasthtml.common import Code as FTCode
        from fasthtml.common import Pre as FTPre

        instructions_section = Div(
            H4("Feedback Instructions", cls="text-base font-semibold mb-2"),
            P(
                "These are the exact instructions sent to the AI when generating your feedback.",
                cls="text-xs text-base-content/50 mb-3",
            ),
            FTPre(
                FTCode(exercise.instructions, cls="text-xs leading-relaxed"),
                cls="bg-base-200/60 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap mb-6",
            ),
        )

    # ── Actions ───────────────────────────────────────────────────────
    submit_href = f"/submit?exercise_uid={exercise.uid}"
    if from_ps:
        submit_href += f"&from_ps={from_ps}"
    actions = Div(
        ButtonLink(
            "Download",
            href=f"/api/exercises/md?uid={exercise.uid}",
            cls=ButtonT.secondary,
        ),
        ButtonLink(
            "Submit",
            href=submit_href,
            cls=ButtonT.primary,
        ),
        cls="flex gap-2",
    )

    return Div(
        PageHeader(
            exercise.title,
            subtitle=f"Exercise · {getattr(exercise.scope, 'value', str(exercise.scope)).title()}",
            actions=actions,
        ),
        metadata_row,
        description_section,
        form_fields_section,
        instructions_section,
        ButtonLink(
            "← Back to Curriculum",
            href="/profile?tab=curriculum",
            cls=ButtonT.ghost,
        ),
        cls=f"{Container.STANDARD} {Spacing.PAGE}",
    )
