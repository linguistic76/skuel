"""
Exercises UI Routes - Transparent Feedback System
===================================================

UI for exercises (instruction templates) following SKUEL's transparency principles:
- Visible, editable instructions
- User-controlled model selection
- Side-by-side entry + feedback view
- No black boxes

Uses DaisyUI/Tailwind components for clean, consistent design.

Formerly assignments_ui.py — renamed per of Ku hierarchy refactoring.
"""

from typing import Any

from fasthtml.common import H1, H2, H3, A, Code, Form, Li, P, Pre, Ul

from adapters.inbound.auth import require_teacher
from core.utils.logging import get_logger
from ui.daisy_components import (
    Button,
    ButtonT,
    Card,
    Div,
    Input,
    Label,
    Option,
    Select,
    Span,
    Textarea,
)
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.exercises.ui")


# ============================================================================
# UI COMPONENT LIBRARY
# ============================================================================


class ExerciseUIComponents:
    """Reusable exercise UI components."""

    @staticmethod
    def render_exercises_dashboard(exercises=None, request=None, user_uid=None) -> Any:
        """Main exercises dashboard."""
        exercises = exercises or []

        navbar = create_navbar_for_request(request, active_page="exercises")

        # Get user_uid from session if not provided
        if user_uid is None and request:
            from adapters.inbound.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)

        return Div(
            navbar,
            H1("Exercises", cls="text-2xl font-bold mb-6"),
            P(
                "Create instruction sets for AI feedback on your entries. "
                "Full transparency - you write the instructions, select the model, "
                "and see exactly what's sent to the LLM.",
                cls="text-base-content/70 mb-6",
            ),
            # Action button
            Div(
                Button(
                    "Create New Exercise",
                    hx_get=f"/ui/exercises/new?user_uid={user_uid}",
                    hx_target="#main-content",
                    variant=ButtonT.primary,
                    cls="mb-6",
                ),
                cls="mb-6",
            ),
            # Exercises list
            ExerciseUIComponents.render_exercises_list(exercises),
            cls="container mx-auto p-6",
            id="main-content",
        )

    @staticmethod
    def render_exercises_list(exercises) -> Any:
        """List of exercises."""
        if not exercises:
            return Card(
                P(
                    "No exercises yet. Create your first exercise to get started!",
                    cls="text-base-content/60 text-center py-8",
                ),
                cls="mb-4",
            )

        return Div(
            *[ExerciseUIComponents.render_exercise_card(e) for e in exercises], cls="space-y-4"
        )

    @staticmethod
    def render_exercise_card(exercise) -> Any:
        """Single exercise card."""
        # Truncate instructions for preview
        instructions_text = exercise.instructions or ""
        instructions_preview = (
            instructions_text[:150] + "..." if len(instructions_text) > 150 else instructions_text
        )

        return Card(
            Div(
                # Header
                Div(
                    H3(exercise.title, cls="text-lg font-semibold"),
                    cls="flex justify-between items-start mb-2",
                ),
                # Instructions preview
                P(instructions_preview, cls="text-base-content/70 text-sm mb-3"),
                # Model badge
                Span(
                    f"{exercise.model}",
                    cls="inline-block px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded mb-3",
                ),
                # Context notes count
                (
                    Div(
                        Span(
                            f"{len(exercise.context_notes)} context notes",
                            cls="text-sm text-base-content/60",
                        ),
                        cls="mb-3",
                    )
                    if exercise.context_notes
                    else ""
                ),
                # Action buttons
                Div(
                    Button(
                        "Edit",
                        hx_get=f"/ui/exercises/{exercise.uid}/edit",
                        hx_target="#main-content",
                        variant=ButtonT.ghost,
                        cls="btn-sm mr-2",
                    ),
                    Button(
                        "View Instructions",
                        hx_get=f"/ui/exercises/{exercise.uid}/view",
                        hx_target="#main-content",
                        variant=ButtonT.ghost,
                        cls="btn-sm mr-2",
                    ),
                    Button(
                        "Delete",
                        hx_delete=f"/api/exercises/{exercise.uid}",
                        hx_confirm="Are you sure you want to delete this exercise?",
                        hx_target="closest .card",
                        hx_swap="outerHTML",
                        variant=ButtonT.error,
                        cls="btn-sm",
                    ),
                    cls="flex gap-2",
                ),
                cls="p-4",
            ),
            cls="mb-4",
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
                        Label("Exercise Name", cls="label-text"),
                        Input(
                            type="text",
                            name="name",
                            value=exercise.title if exercise else "",
                            placeholder="e.g., Daily Reflection, Principle Mining",
                            required=True,
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Instructions - THE KEY TRANSPARENCY ELEMENT
                    Div(
                        Label(
                            "Instructions (Visible to You & LLM)", cls="label-text font-semibold"
                        ),
                        P(
                            "These are the exact instructions sent to the LLM. "
                            "Be clear and specific about what kind of feedback you want.",
                            cls="text-sm text-base-content/70 mb-2",
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
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Model selection
                    Div(
                        Label("LLM Model", cls="label-text"),
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
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Context notes (optional)
                    Div(
                        Label("Context Notes (Optional)", cls="label-text"),
                        P(
                            "Reference materials or context the LLM should consider. One per line.",
                            cls="text-sm text-base-content/70 mb-2",
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
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Domain (optional)
                    Div(
                        Label("Domain (Optional)", cls="label-text"),
                        Select(
                            Option("None", value=""),
                            Option("Personal", value="personal"),
                            Option("Health", value="health"),
                            Option("Learning", value="learning"),
                            Option("Work", value="work"),
                            name="domain",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Submit buttons
                    Div(
                        Button("Save Exercise", type="submit", variant=ButtonT.primary, cls="mr-2"),
                        Button(
                            "Cancel",
                            hx_get="/ui/exercises",
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
                    href=f"/ku/{ku.get('uid')}",
                    cls="link link-primary mr-3",
                )
                for ku in required_knowledge
            ]
            knowledge_section = Card(
                Div(
                    H3("Knowledge Foundation (Ku)", cls="text-lg font-semibold mb-2"),
                    P(
                        "This exercise develops understanding of:",
                        cls="text-base-content/70 mb-2",
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
            Card(
                Div(
                    H3("Full Transparency", cls="text-lg font-semibold mb-3"),
                    P(
                        "Below you can see exactly what gets sent to the "
                        "LLM when you request feedback. "
                        "No hidden prompts, no black boxes.",
                        cls="text-base-content/70",
                    ),
                    cls="bg-blue-50 p-4 rounded mb-4",
                )
            ),
            # Instructions
            Card(
                H3("Instructions", cls="text-lg font-semibold mb-3"),
                Pre(
                    Code(exercise.instructions, cls="text-sm"),
                    cls="bg-base-200 p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Model
            Card(
                H3("Model", cls="text-lg font-semibold mb-3"),
                P(f"{exercise.model}", cls="text-base-content/70"),
                cls="mb-4",
            ),
            # Context notes
            (
                Card(
                    H3("Context Notes", cls="text-lg font-semibold mb-3"),
                    Ul(
                        *[Li(note, cls="text-base-content/70") for note in exercise.context_notes],
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
                    cls="text-base-content/70 mb-3",
                ),
                Pre(
                    Code(example_prompt, cls="text-sm"),
                    cls="bg-base-200 p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Action buttons
            Div(
                Button(
                    "Edit Exercise",
                    hx_get=f"/ui/exercises/{exercise.uid}/edit",
                    hx_target="#main-content",
                    variant=ButtonT.primary,
                    cls="mr-2",
                ),
                Button(
                    "Back to Exercises",
                    hx_get="/ui/exercises",
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

    Role-gated to TEACHER+ — only teachers and admins can create/manage
    AI feedback instruction templates.
    """

    # Named function for role decorator (SKUEL012: no lambdas)
    def get_user_service_instance():
        """Get user service for teacher role checks."""
        return user_service

    @app.get("/ui/exercises")
    @require_teacher(get_user_service_instance)
    async def exercises_dashboard(request, current_user=None) -> Any:
        """Exercises dashboard."""
        try:
            user_uid = current_user.uid if current_user else None

            result = await exercises_service.list_user_exercises(user_uid)
            exercises = [] if result.is_error else result.value

            return ExerciseUIComponents.render_exercises_dashboard(
                exercises=exercises, request=request, user_uid=user_uid
            )

        except Exception as e:
            logger.error(f"Error rendering exercises dashboard: {e}")
            return Div(P(f"Error loading exercises: {e}", cls="text-red-600"))

    @app.get("/ui/exercises/new")
    @require_teacher(get_user_service_instance)
    async def new_exercise_form(request, current_user=None) -> Any:
        """New exercise form."""
        user_uid = current_user.uid if current_user else None

        return ExerciseUIComponents.render_exercise_editor(user_uid=user_uid, mode="create")

    @app.get("/ui/exercises/{uid}/edit")
    @require_teacher(get_user_service_instance)
    async def edit_exercise_form(_request, uid: str, current_user=None) -> Any:
        """Edit exercise form."""
        try:
            result = await exercises_service.get_exercise(uid)

            if result.is_error or not result.value:
                return Div(P("Exercise not found", cls="text-red-600"))

            exercise = result.value

            return ExerciseUIComponents.render_exercise_editor(exercise=exercise, mode="edit")

        except Exception as e:
            logger.error(f"Error loading exercise for edit: {e}")
            return Div(P(f"Error: {e}", cls="text-red-600"))

    @app.get("/ui/exercises/{uid}/view")
    @require_teacher(get_user_service_instance)
    async def view_exercise(_request, uid: str, current_user=None) -> Any:
        """View exercise with transparency and required Ku foundation."""
        try:
            result = await exercises_service.get_exercise(uid)

            if result.is_error or not result.value:
                return Div(P("Exercise not found", cls="text-red-600"))

            exercise = result.value

            knowledge_result = await exercises_service.get_required_knowledge(uid)
            required_knowledge = knowledge_result.value if knowledge_result.is_ok else []

            return ExerciseUIComponents.render_exercise_view(
                exercise, required_knowledge=required_knowledge
            )

        except Exception as e:
            logger.error(f"Error viewing exercise: {e}")
            return Div(P(f"Error: {e}", cls="text-red-600"))

    logger.info("Exercises UI routes registered")
    return []


__all__ = ["ExerciseUIComponents", "create_exercises_ui_routes"]
