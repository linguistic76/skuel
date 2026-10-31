"""
Exercise Detail & View Components
===================================

Pure rendering functions for exercise detail and transparency views.
"""

from typing import Any

from fasthtml.common import H4, Div, P, Span

from ui.components import ButtonT
from ui.feedback import Badge, BadgeT
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.user_entry.forms import submit_page_href


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
        P(exercise.description, cls="text-muted-foreground mb-6") if exercise.description else Div()
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
                        Span(label_text, cls="text-sm font-medium text-foreground"),
                        Span(" *", cls="text-error text-sm") if required else Span(),
                        cls="flex items-baseline gap-0.5",
                    ),
                    Span(type_hint, cls="text-xs text-foreground/60 mt-0.5"),
                    cls="py-3 border-b border-border last:border-0",
                )
            )

        form_fields_section = Div(
            H4("What You'll Submit", cls="text-base font-semibold mb-3"),
            Div(*field_rows, cls="bg-muted/40 rounded-lg px-4 mb-6"),
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
                cls="text-xs text-muted-foreground mb-3",
            ),
            FTPre(
                FTCode(exercise.instructions, cls="text-xs leading-relaxed"),
                cls="bg-muted/60 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap mb-6",
            ),
        )

    # ── Actions ───────────────────────────────────────────────────────
    submit_href = submit_page_href(exercise.uid, from_ps=from_ps or None)
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
            subtitle="Exercise",
            actions=actions,
        ),
        metadata_row,
        description_section,
        form_fields_section,
        instructions_section,
        ButtonLink(
            "← Back to Library",
            href="/library",
            cls=ButtonT.ghost,
        ),
    )
