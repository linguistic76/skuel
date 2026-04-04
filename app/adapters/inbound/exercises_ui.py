"""
Exercises UI Routes - Transparent Feedback System
===================================================

UI for exercises (instruction templates) following SKUEL's transparency principles:
- Visible, editable instructions
- User-controlled model selection
- Side-by-side entry + feedback view
- No black boxes

Uses MonsterUI/Tailwind components for clean, consistent design.

Formerly assignments_ui.py — renamed per of Ku hierarchy refactoring.
"""

from typing import Any

from fasthtml.common import H2, H3, H4, A, Code, Div, Form, Li, Option, P, Pre, Span, Ul

from adapters.inbound.auth import make_service_getter, require_authenticated_user, require_teacher
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card
from ui.feedback import Alert, AlertT, Badge, BadgeT
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.card_generator import CardGenerator
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.page_header import PageHeader
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.exercises.ui")


# ============================================================================
# UI COMPONENT LIBRARY
# ============================================================================


class ExerciseUIComponents:
    """Reusable exercise UI components."""

    @staticmethod
    def render_exercises_list(exercises) -> Any:
        """List of exercises."""
        if not exercises:
            return Card(
                P(
                    "No exercises yet. Create your first exercise to get started!",
                    cls="text-muted-foreground text-center py-8",
                ),
                cls="mb-4",
            )

        return Div(
            *[ExerciseUIComponents.render_exercise_card(e) for e in exercises], cls="space-y-4"
        )

    @staticmethod
    def render_exercise_card(exercise) -> Any:
        """Single exercise card using CardGenerator."""

        def render_model_badge(value: str) -> Any:
            return Badge(value, variant=BadgeT.info)

        def render_context_notes(value: list) -> Any:
            if not value:
                return None
            return Span(
                f"{len(value)} context notes",
                cls="text-sm text-muted-foreground",
            )

        action_buttons = Div(
            Button(
                "Edit",
                hx_get=f"/exercises/{exercise.uid}/edit",
                hx_target="#main-content",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            Button(
                "View Instructions",
                hx_get=f"/exercises/{exercise.uid}/view",
                hx_target="#main-content",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            Button(
                "Delete",
                hx_delete=f"/api/exercises/{exercise.uid}",
                hx_confirm="Are you sure you want to delete this exercise?",
                hx_target="closest .card",
                hx_swap="outerHTML",
                variant=ButtonT.error,
                size=Size.sm,
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            exercise,
            display_fields=["instructions", "model", "context_notes"],
            show_labels=False,
            field_renderers={
                "model": render_model_badge,
                "context_notes": render_context_notes,
            },
            actions=action_buttons,
            card_attrs={"cls": "mb-4 p-4"},
        )

    @staticmethod
    def render_exercise_editor(exercise=None, user_uid=None, mode="create") -> Any:
        """Exercise editor form - TRANSPARENCY: User sees and edits instructions."""
        is_edit = mode == "edit"
        form_title = "Edit Exercise" if is_edit else "Create New Exercise"
        submit_url = f"/api/exercises/{exercise.uid}" if is_edit else "/api/exercises"
        submit_method = "put" if is_edit else "post"

        return Div(
            H2(form_title, cls="text-xl font-bold mb-6"),
            Card(
                Form(
                    # Hidden user_uid for create
                    (Input(type="hidden", name="user_uid", value=user_uid) if not is_edit else ""),
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
                        Button("Save Exercise", type="submit", variant=ButtonT.primary, cls="mr-2"),
                        Button(
                            "Cancel",
                            hx_get="/exercises",
                            hx_target="#main-content",
                            variant=ButtonT.ghost,
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

    @staticmethod
    def render_exercise_view(exercise, required_knowledge: list | None = None) -> Any:
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
            H2(exercise.title, cls="text-xl font-bold mb-4"),
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
                H3("Instructions", cls="text-lg font-semibold mb-3"),
                Pre(
                    Code(exercise.instructions, cls="text-sm"),
                    cls="bg-muted p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Model
            Card(
                H3("Model", cls="text-lg font-semibold mb-3"),
                P(f"{exercise.model}", cls="text-muted-foreground"),
                cls="mb-4",
            ),
            # Context notes
            (
                Card(
                    H3("Context Notes", cls="text-lg font-semibold mb-3"),
                    Ul(
                        *[Li(note, cls="text-muted-foreground") for note in exercise.context_notes],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-4",
                )
                if exercise.context_notes
                else ""
            ),
            # Example prompt preview
            Card(
                H3("Example Prompt Preview", cls="text-lg font-semibold mb-3"),
                P(
                    "Here's what the complete prompt would look like with an example entry:",
                    cls="text-muted-foreground mb-3",
                ),
                Pre(
                    Code(example_prompt, cls="text-sm"),
                    cls="bg-muted p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Action buttons
            Div(
                Button(
                    "Edit Exercise",
                    hx_get=f"/exercises/{exercise.uid}/edit",
                    hx_target="#main-content",
                    variant=ButtonT.primary,
                    cls="mr-2",
                ),
                Button(
                    "Back to Exercises",
                    hx_get="/exercises",
                    hx_target="#main-content",
                    variant=ButtonT.ghost,
                ),
                cls="mt-4",
            ),
            cls="container mx-auto p-6",
        )


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_exercises_ui_routes(
    app,
    rt,
    exercises_service,
    transcript_service=None,
    user_service=None,
    **related_services: Any,
):
    """
    Create exercises UI routes.

    Dashboard is open to all authenticated users (exercises are shared curriculum).
    Create/edit/delete routes are TEACHER+ gated.
    """

    get_user_service = make_service_getter(user_service)

    @app.get("/exercises")
    async def exercises_dashboard(request) -> Any:
        """Exercises dashboard — open to all authenticated users, Learn sidebar layout."""
        try:
            user_uid = require_authenticated_user(request)

            result = await exercises_service.list_user_exercises(user_uid)
            exercises = [] if result.is_error else result.value

            content = Div(
                PageHeader(
                    "Exercises",
                    subtitle="Practice with exercises linked to path steps and knowledge units",
                ),
                ExerciseUIComponents.render_exercises_list(exercises),
                id="main-content",
            )
            return await BasePage(
                content=content,
                title="Exercises",
                request=request,
                active_page="curriculum",
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error rendering exercises dashboard: {e}")
            return render_error_banner("Error loading exercises", technical_details=str(e))

    @app.get("/exercises/new")
    @require_teacher(get_user_service)
    async def new_exercise_form(request, current_user=None) -> Any:
        """New exercise form."""
        user_uid = current_user.uid if current_user else None

        return ExerciseUIComponents.render_exercise_editor(user_uid=user_uid, mode="create")

    @app.get("/exercises/{uid}/edit")
    @require_teacher(get_user_service)
    async def edit_exercise_form(_request, uid: str, current_user=None) -> Any:
        """Edit exercise form."""
        try:
            result = await exercises_service.get_exercise(uid)

            if result.is_error or not result.value:
                return render_inline_error("Exercise not found")

            exercise = result.value

            return ExerciseUIComponents.render_exercise_editor(exercise=exercise, mode="edit")

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error loading exercise for edit: {e}")
            return render_inline_error(f"Error: {e}")

    @app.get("/exercises/{uid}/view")
    @require_teacher(get_user_service)
    async def view_exercise(_request, uid: str, current_user=None) -> Any:
        """View exercise with transparency and required Ku foundation."""
        try:
            result = await exercises_service.get_exercise(uid)

            if result.is_error or not result.value:
                return render_inline_error("Exercise not found")

            exercise = result.value

            knowledge_result = await exercises_service.get_required_knowledge(uid)
            required_knowledge = knowledge_result.value if knowledge_result.is_ok else []

            return ExerciseUIComponents.render_exercise_view(
                exercise, required_knowledge=required_knowledge
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error viewing exercise: {e}")
            return render_inline_error(f"Error: {e}")

    @app.get("/exercises/get")
    async def exercise_detail(request, uid: str, from_ps: str = "") -> Any:
        """Student-facing exercise detail page.

        Shows title, description, form fields, and instructions so a student
        knows exactly what is expected before submitting. Linked from the
        Library Exercises tab.
        """
        try:
            require_authenticated_user(request)

            result = await exercises_service.get_exercise(uid)
            if result.is_error or not result.value:
                return await BasePage(
                    Div(
                        PageHeader("Exercise Not Found"),
                        P("This exercise could not be found.", cls="text-base-content/70"),
                        A(
                            "← Back to Library",
                            href="/library",
                            cls="text-primary hover:underline text-sm",
                        ),
                        cls=f"{Container.STANDARD} {Spacing.PAGE}",
                    ),
                    title="Exercise Not Found",
                    request=request,
                    active_page="library",
                )

            exercise = result.value

            # ── Metadata badges ───────────────────────────────────────────────
            meta_items = []
            if exercise.sel_category:
                label = getattr(exercise.sel_category, "value", str(exercise.sel_category))
                meta_items.append(Badge(label.replace("_", " ").title(), variant=BadgeT.primary))
            if exercise.learning_level:
                level = getattr(exercise.learning_level, "value", str(exercise.learning_level))
                meta_items.append(Badge(level.title(), variant=BadgeT.ghost))
            if exercise.estimated_time_minutes:
                meta_items.append(
                    Badge(f"{exercise.estimated_time_minutes} min", variant=BadgeT.ghost)
                )
            if exercise.mastery_impact:
                impact = getattr(exercise.mastery_impact, "value", str(exercise.mastery_impact))
                meta_items.append(Badge(f"{impact.title()} impact", variant=BadgeT.info))
            metadata_row = (
                Div(*meta_items, cls="flex flex-wrap gap-2 mb-6") if meta_items else Div()
            )

            # ── Description ───────────────────────────────────────────────────
            description_section = (
                P(exercise.description, cls="text-base-content/70 mb-6")
                if exercise.description
                else Div()
            )

            # ── Form fields preview ───────────────────────────────────────────
            form_fields_section = Div()
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
            instructions_section = Div()
            if exercise.instructions:
                instructions_section = Div(
                    H4("Feedback Instructions", cls="text-base font-semibold mb-2"),
                    P(
                        "These are the exact instructions sent to the AI when generating your feedback.",
                        cls="text-xs text-base-content/50 mb-3",
                    ),
                    Pre(
                        Code(exercise.instructions, cls="text-xs leading-relaxed"),
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
                    variant=ButtonT.secondary,
                ),
                ButtonLink(
                    "Submit",
                    href=submit_href,
                    variant=ButtonT.primary,
                ),
                cls="flex gap-2",
            )

            content = Div(
                PageHeader(
                    exercise.title,
                    subtitle=f"Exercise · {getattr(exercise.scope, 'value', str(exercise.scope)).title()}",
                    actions=actions,
                ),
                metadata_row,
                description_section,
                form_fields_section,
                instructions_section,
                A(
                    "← Back to Library",
                    href="/library",
                    cls="text-sm text-base-content/50 hover:text-primary",
                ),
                cls=f"{Container.STANDARD} {Spacing.PAGE}",
            )

            return await BasePage(
                content,
                title=exercise.title,
                request=request,
                active_page="library",
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error rendering exercise detail {uid}: {e}")
            return render_error_banner("Error loading exercise", technical_details=str(e))

    logger.info("Exercises UI routes registered")
    return []


__all__ = ["ExerciseUIComponents", "create_exercises_ui_routes"]
