"""
Report Projects UI Routes - Transparent Feedback System
========================================================

UI for report projects following SKUEL's transparency principles:
- Visible, editable instructions
- User-controlled model selection
- Side-by-side entry + feedback view
- No black boxes

Uses DaisyUI/Tailwind components for clean, consistent design.
"""

from typing import Any

from fasthtml.common import H1, H2, H3, Code, Form, Li, P, Pre, Ul

from core.auth import require_teacher
from core.ui.daisy_components import (
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
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.report_projects.ui")


# ============================================================================
# UI COMPONENT LIBRARY
# ============================================================================


class ReportProjectUIComponents:
    """Reusable report project UI components."""

    @staticmethod
    def render_projects_dashboard(projects=None, request=None, user_uid=None) -> Any:
        """Main report projects dashboard."""
        projects = projects or []

        navbar = create_navbar_for_request(request, active_page="report-projects")

        # Get user_uid from session if not provided
        if user_uid is None and request:
            from core.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)

        return Div(
            navbar,
            H1("Report Projects", cls="text-2xl font-bold mb-6"),
            P(
                "Create instruction sets for AI feedback on your entries. "
                "Full transparency - you write the instructions, select the model, "
                "and see exactly what's sent to the LLM.",
                cls="text-gray-600 mb-6",
            ),
            # Action button
            Div(
                Button(
                    "Create New Project",
                    hx_get=f"/ui/report-projects/new?user_uid={user_uid}",
                    hx_target="#main-content",
                    variant=ButtonT.primary,
                    cls="mb-6",
                ),
                cls="mb-6",
            ),
            # Projects list
            ReportProjectUIComponents.render_projects_list(projects),
            cls="container mx-auto p-6",
            id="main-content",
        )

    @staticmethod
    def render_projects_list(projects) -> Any:
        """List of report projects."""
        if not projects:
            return Card(
                P(
                    "No projects yet. Create your first project to get started!",
                    cls="text-gray-500 text-center py-8",
                ),
                cls="mb-4",
            )

        return Div(
            *[ReportProjectUIComponents.render_project_card(p) for p in projects], cls="space-y-4"
        )

    @staticmethod
    def render_project_card(project) -> Any:
        """Single project card."""
        # Truncate instructions for preview
        instructions_preview = (
            project.instructions[:150] + "..."
            if len(project.instructions) > 150
            else project.instructions
        )

        return Card(
            Div(
                # Header
                Div(
                    H3(project.name, cls="text-lg font-semibold"),
                    Span(
                        "Active" if project.is_active else "Inactive",
                        cls="text-sm "
                        + ("text-green-600" if project.is_active else "text-gray-400"),
                    ),
                    cls="flex justify-between items-start mb-2",
                ),
                # Instructions preview
                P(instructions_preview, cls="text-gray-600 text-sm mb-3"),
                # Model badge
                Span(
                    f"{project.model}",
                    cls="inline-block px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded mb-3",
                ),
                # Context notes count
                (
                    Div(
                        Span(
                            f"{len(project.context_notes)} context notes",
                            cls="text-sm text-gray-500",
                        ),
                        cls="mb-3",
                    )
                    if project.context_notes
                    else ""
                ),
                # Action buttons
                Div(
                    Button(
                        "Edit",
                        hx_get=f"/ui/report-projects/{project.uid}/edit",
                        hx_target="#main-content",
                        variant=ButtonT.ghost,
                        cls="btn-sm mr-2",
                    ),
                    Button(
                        "View Instructions",
                        hx_get=f"/ui/report-projects/{project.uid}/view",
                        hx_target="#main-content",
                        variant=ButtonT.ghost,
                        cls="btn-sm mr-2",
                    ),
                    Button(
                        "Delete",
                        hx_delete=f"/api/report-projects/{project.uid}",
                        hx_confirm="Are you sure you want to delete this project?",
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
    def render_project_editor(project=None, user_uid=None, mode="create") -> Any:
        """Project editor form - TRANSPARENCY: User sees and edits instructions."""
        is_edit = mode == "edit"
        form_title = "Edit Project" if is_edit else "Create New Project"
        submit_url = f"/api/report-projects/{project.uid}" if is_edit else "/api/report-projects"
        submit_method = "put" if is_edit else "post"

        return Div(
            H2(form_title, cls="text-xl font-bold mb-6"),
            Card(
                Form(
                    # Hidden user_uid for create
                    (Input(type="hidden", name="user_uid", value=user_uid) if not is_edit else ""),
                    # Project name
                    Div(
                        Label("Project Name", cls="label-text"),
                        Input(
                            type="text",
                            name="name",
                            value=project.name if project else "",
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
                            cls="text-sm text-gray-600 mb-2",
                        ),
                        Textarea(
                            project.instructions if project else "",
                            name="instructions",
                            rows="8",
                            placeholder="Example:\n\nRead my entry and ask me one clarifying question about the emotions I describe. Focus on self-awareness and be gentle and curious.",
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
                                "Claude 3.5 Sonnet (Recommended)",
                                value="claude-3-5-sonnet-20241022",
                                selected=not project
                                or project.model == "claude-3-5-sonnet-20241022",
                            ),
                            Option(
                                "Claude 3.5 Haiku (Faster)",
                                value="claude-3-5-haiku-20241022",
                                selected=project and project.model == "claude-3-5-haiku-20241022",
                            ),
                            Option(
                                "GPT-4o",
                                value="gpt-4o",
                                selected=project and project.model == "gpt-4o",
                            ),
                            Option(
                                "GPT-4o Mini (Cheaper)",
                                value="gpt-4o-mini",
                                selected=project and project.model == "gpt-4o-mini",
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
                            cls="text-sm text-gray-600 mb-2",
                        ),
                        Textarea(
                            "\n".join(project.context_notes)
                            if project and project.context_notes
                            else "",
                            name="context_notes",
                            rows="4",
                            placeholder="Focus on self-awareness\nBe gentle and curious\nReference my core principles",
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
                        Button("Save Project", type="submit", variant=ButtonT.primary, cls="mr-2"),
                        Button(
                            "Cancel",
                            hx_get="/ui/report-projects",
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
    def render_project_view(project) -> Any:
        """View project details - TRANSPARENCY: Show exact prompt."""
        # Example entry for preview
        example_entry = "Today I felt overwhelmed by all the tasks on my plate..."

        # Show what the actual prompt would look like
        example_prompt = project.get_feedback_prompt(example_entry)

        return Div(
            H2(project.name, cls="text-xl font-bold mb-4"),
            # Transparency notice
            Card(
                Div(
                    H3("Full Transparency", cls="text-lg font-semibold mb-3"),
                    P(
                        "Below you can see exactly what gets sent to the LLM when you request feedback. "
                        "No hidden prompts, no black boxes.",
                        cls="text-gray-600",
                    ),
                    cls="bg-blue-50 p-4 rounded mb-4",
                )
            ),
            # Instructions
            Card(
                H3("Instructions", cls="text-lg font-semibold mb-3"),
                Pre(
                    Code(project.instructions, cls="text-sm"),
                    cls="bg-gray-50 p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Model
            Card(
                H3("Model", cls="text-lg font-semibold mb-3"),
                P(f"{project.model}", cls="text-gray-700"),
                cls="mb-4",
            ),
            # Context notes
            (
                Card(
                    H3("Context Notes", cls="text-lg font-semibold mb-3"),
                    Ul(
                        *[Li(note, cls="text-gray-700") for note in project.context_notes],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-4",
                )
                if project.context_notes
                else ""
            ),
            # Example prompt preview
            Card(
                H3("Example Prompt Preview", cls="text-lg font-semibold mb-3"),
                P(
                    "Here's what the complete prompt would look like with an example entry:",
                    cls="text-gray-600 mb-3",
                ),
                Pre(
                    Code(example_prompt, cls="text-sm"),
                    cls="bg-gray-50 p-4 rounded overflow-x-auto",
                ),
                cls="mb-4",
            ),
            # Action buttons
            Div(
                Button(
                    "Edit Project",
                    hx_get=f"/ui/report-projects/{project.uid}/edit",
                    hx_target="#main-content",
                    variant=ButtonT.primary,
                    cls="mr-2",
                ),
                Button(
                    "Back to Projects",
                    hx_get="/ui/report-projects",
                    hx_target="#main-content",
                    variant=ButtonT.ghost,
                ),
                cls="mt-4",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_entry_with_feedback(entry, feedback=None, project=None) -> Any:
        """Side-by-side view: entry + AI feedback."""
        return Div(
            H2(entry.title, cls="text-xl font-bold mb-4"),
            P(entry.entry_date.strftime("%B %d, %Y"), cls="text-gray-500 mb-6"),
            # Side-by-side layout
            Div(
                # Left: Entry
                Div(
                    Card(
                        H3("Your Entry", cls="text-lg font-semibold mb-4"),
                        Div(entry.content, cls="prose max-w-none"),
                        cls="p-6 h-full",
                    ),
                    cls="w-1/2 pr-2",
                ),
                # Right: AI Feedback
                Div(
                    Card(
                        H3("AI Feedback", cls="text-lg font-semibold mb-4"),
                        (
                            Div(
                                # Show which project was used
                                (
                                    Div(
                                        Span(f"Using: {project.name}", cls="text-sm text-gray-600"),
                                        cls="mb-3",
                                    )
                                    if project
                                    else ""
                                ),
                                # Feedback content
                                Div(feedback, cls="prose max-w-none"),
                                # Timestamp
                                P(
                                    f"Generated: {entry.feedback_generated_at.strftime('%Y-%m-%d %H:%M')}",
                                    cls="text-xs text-gray-400 mt-4",
                                ),
                            )
                            if feedback
                            else Div(
                                P("No feedback yet.", cls="text-gray-500 italic"),
                                Button(
                                    "Generate Feedback",
                                    hx_post=f"/api/report-projects/feedback?entry_uid={entry.uid}",
                                    hx_target="closest .card",
                                    variant=ButtonT.primary,
                                    cls="mt-4",
                                ),
                            )
                        ),
                        cls="p-6 h-full bg-blue-50",
                    ),
                    cls="w-1/2 pl-2",
                ),
                cls="flex gap-4",
            ),
            # Action buttons
            Div(
                Button(
                    "Back to Reports",
                    hx_get="/ui/reports",
                    hx_target="#main-content",
                    variant=ButtonT.ghost,
                    cls="mt-6",
                ),
                cls="mt-6",
            ),
            cls="container mx-auto p-6",
        )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_assignments_ui_routes(
    app,
    rt,
    report_projects_service,
    transcript_service=None,
    user_service=None,
    **related_services: Any,
):
    """
    Create report projects UI routes.

    Role-gated to TEACHER+ — only teachers and admins can create/manage
    AI feedback instruction templates.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        report_projects_service: ReportProjectService instance
        transcript_service: TranscriptProcessor instance (optional)
        user_service: UserService for role checks
        **related_services: Optional related services

    Returns:
        Empty list (routes registered via decorators, not returned)
    """

    # Named function for role decorator (SKUEL012: no lambdas)
    def get_user_service_instance():
        """Get user service for teacher role checks."""
        return user_service

    @app.get("/ui/report-projects")
    @require_teacher(get_user_service_instance)
    async def report_projects_dashboard(request, current_user=None) -> Any:
        """Report projects dashboard."""
        try:
            user_uid = current_user.uid if current_user else None

            # Get user's projects
            result = await report_projects_service.list_user_projects(user_uid)

            projects = [] if result.is_error else result.value

            return ReportProjectUIComponents.render_projects_dashboard(
                projects=projects, request=request, user_uid=user_uid
            )

        except Exception as e:
            logger.error(f"Error rendering projects dashboard: {e}")
            return Div(P(f"Error loading projects: {e}", cls="text-red-600"))

    @app.get("/ui/report-projects/new")
    @require_teacher(get_user_service_instance)
    async def new_project_form(request, current_user=None) -> Any:
        """New project form."""
        user_uid = current_user.uid if current_user else None

        return ReportProjectUIComponents.render_project_editor(user_uid=user_uid, mode="create")

    @app.get("/ui/report-projects/{uid}/edit")
    @require_teacher(get_user_service_instance)
    async def edit_project_form(_request, uid: str, current_user=None) -> Any:
        """Edit project form."""
        try:
            result = await report_projects_service.get_project(uid)

            if result.is_error or not result.value:
                return Div(P("Project not found", cls="text-red-600"))

            project = result.value

            return ReportProjectUIComponents.render_project_editor(project=project, mode="edit")

        except Exception as e:
            logger.error(f"Error loading project for edit: {e}")
            return Div(P(f"Error: {e}", cls="text-red-600"))

    @app.get("/ui/report-projects/{uid}/view")
    @require_teacher(get_user_service_instance)
    async def view_project(_request, uid: str, current_user=None) -> Any:
        """View project with transparency."""
        try:
            result = await report_projects_service.get_project(uid)

            if result.is_error or not result.value:
                return Div(P("Project not found", cls="text-red-600"))

            project = result.value

            return ReportProjectUIComponents.render_project_view(project)

        except Exception as e:
            logger.error(f"Error viewing project: {e}")
            return Div(P(f"Error: {e}", cls="text-red-600"))

    @app.get("/ui/reports/{uid}/with-feedback")
    @require_teacher(get_user_service_instance)
    async def view_entry_with_feedback(_request, uid: str, current_user=None) -> Any:
        """View entry with AI feedback side-by-side."""
        try:
            if transcript_service is None:
                return Div(P("Transcript service not available", cls="text-red-600"))

            entry_result = await transcript_service.get_journal(uid)

            if entry_result.is_error or not entry_result.value:
                return Div(P("Entry not found", cls="text-red-600"))

            entry = entry_result.value

            # Get project if used
            project = None
            if entry.project_uid:
                project_result = await report_projects_service.get_project(entry.project_uid)
                if project_result.is_ok():
                    project = project_result.value

            return ReportProjectUIComponents.render_entry_with_feedback(
                entry=entry, feedback=entry.feedback, project=project
            )

        except Exception as e:
            logger.error(f"Error viewing entry with feedback: {e}")
            return Div(P(f"Error: {e}", cls="text-red-600"))

    logger.info("Report projects UI routes registered")
    return []


__all__ = ["ReportProjectUIComponents", "create_assignments_ui_routes"]
