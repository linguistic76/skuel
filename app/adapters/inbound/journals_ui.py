"""
Journals UI Routes
==================

Two-tier journal submission interface:
- **PJ1 (Voice Journals)**: Ephemeral audio journals, max 3 stored, FIFO auto-cleanup
- **PJ2 (Curated Journals)**: Permanent text/markdown journals, human-edited

**Design Philosophy:**
- Tab-based UI separating ephemeral (voice) from permanent (curated)
- Voice journals for quick capture, auto-cleaned to prevent clutter
- Curated journals for intentional, refined content

**Data Model (January 2026 - Domain Separation):**
- Both tiers stored as :Journal nodes with JournalType enum:
  - JournalType.VOICE: Ephemeral, max 3, FIFO cleanup
  - JournalType.CURATED: Permanent
- Uses JournalsCoreService for CRUD operations

**HTMX-Based (December 2025):**
All form submissions use HTMX for cleaner, JavaScript-minimal UX.
"""

from typing import Any

from fasthtml.common import H1, H3, H4, H5, A, Form, NotStr, P
from fasthtml.common import Script as FTScript
from starlette.datastructures import UploadFile
from starlette.requests import Request

from core.auth import require_authenticated_user
from core.models.enums.journal_enums import JournalType
from core.models.journal.journal_pure import create_journal
from core.ui.daisy_components import (
    Button,
    ButtonT,
    Card,
    CardBody,
    Container,
    Div,
    Input,
    Label,
    Span,
)
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.journals.ui")


# ============================================================================
# HTML FRAGMENT HELPERS
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    assignment_uid: str | None = None,
    is_error: bool = False,
    target_id: str = "voice-upload-status",
) -> Any:
    """Render upload status as HTML fragment for HTMX swap."""
    if is_error:
        return Div(
            Div(
                H4("Upload Failed", cls="m-0"),
                P(message, cls="m-0"),
                cls="alert alert-error",
            ),
            id=target_id,
        )

    alert_class = "alert-success" if status == "completed" else "alert-warning"
    status_text = "Journal processed successfully!" if status == "completed" else "Processing..."

    return Div(
        Div(
            H4("Journal Uploaded!", cls="m-0"),
            P(status_text, cls="m-0"),
            P(A("View Details", href=f"/assignments/{assignment_uid}")) if assignment_uid else "",
            cls=f"alert {alert_class}",
        ),
        id=target_id,
    )


def _render_recent_voice_journals(journals: list[Any]) -> Any:
    """Render recent voice journals list (max 3, ephemeral)."""
    if not journals:
        return Div(
            P(
                "No voice journals yet. Upload an audio recording above!",
                cls="text-center text-gray-500",
            ),
            id="recent-voice-journals",
        )

    def get_status_class(status: str) -> str:
        classes = {
            "draft": "badge-warning",
            "transcribed": "badge-info",
            "published": "badge-success",
            "archived": "badge-ghost",
        }
        return classes.get(status, "badge-ghost")

    journal_cards = []
    for journal in journals[:3]:  # Enforce max 3 in display
        # Get display title
        title = journal.title or "Voice Journal"
        if hasattr(journal, "metadata") and journal.metadata:
            title = journal.metadata.get("original_filename", title)

        # Get date
        entry_date = journal.entry_date if hasattr(journal, "entry_date") else journal.created_at
        created_date = (
            entry_date.strftime("%m/%d/%Y")
            if hasattr(entry_date, "strftime")
            else str(entry_date)[:10]
        )

        # Get status
        status_value = (
            journal.status.value if hasattr(journal.status, "value") else str(journal.status)
        )

        journal_cards.append(
            Card(
                CardBody(
                    Div(
                        Div(
                            H5(title, cls="m-0"),
                            P(created_date, cls="text-sm text-gray-500 m-0"),
                            cls="flex-1",
                        ),
                        Div(
                            Span(
                                status_value,
                                cls=f"badge {get_status_class(status_value)}",
                            ),
                            cls="w-auto",
                        ),
                        Div(
                            A(
                                "View",
                                href=f"/journals/{journal.uid}",
                                cls="btn btn-sm btn-ghost",
                            ),
                            cls="w-auto",
                        ),
                        cls="grid grid-cols-[1fr_auto_auto] gap-2 items-center",
                    ),
                    cls="p-2",
                ),
                cls="card bg-base-100 shadow-sm mb-2",
            )
        )

    return Div(*journal_cards, id="recent-voice-journals")


def _render_recent_curated_journals(journals: list[Any]) -> Any:
    """Render recent curated journals list (permanent, no limit)."""
    if not journals:
        return Div(
            P(
                "No curated journals yet. Upload a text or markdown file above!",
                cls="text-center text-gray-500",
            ),
            id="recent-curated-journals",
        )

    def get_status_class(status: str) -> str:
        classes = {
            "draft": "badge-warning",
            "transcribed": "badge-info",
            "published": "badge-success",
            "archived": "badge-ghost",
        }
        return classes.get(status, "badge-ghost")

    journal_cards = []
    for journal in journals:
        # Get display title
        title = journal.title or "Curated Journal"
        if hasattr(journal, "metadata") and journal.metadata:
            title = journal.metadata.get("original_filename", title)

        # Get date
        entry_date = journal.entry_date if hasattr(journal, "entry_date") else journal.created_at
        created_date = (
            entry_date.strftime("%m/%d/%Y")
            if hasattr(entry_date, "strftime")
            else str(entry_date)[:10]
        )

        # Get status
        status_value = (
            journal.status.value if hasattr(journal.status, "value") else str(journal.status)
        )

        journal_cards.append(
            Card(
                CardBody(
                    Div(
                        Div(
                            H5(title, cls="m-0"),
                            P(created_date, cls="text-sm text-gray-500 m-0"),
                            cls="flex-1",
                        ),
                        Div(
                            Span(
                                status_value,
                                cls=f"badge {get_status_class(status_value)}",
                            ),
                            cls="w-auto",
                        ),
                        Div(
                            A(
                                "View",
                                href=f"/journals/{journal.uid}",
                                cls="btn btn-sm btn-ghost",
                            ),
                            cls="w-auto",
                        ),
                        cls="grid grid-cols-[1fr_auto_auto] gap-2 items-center",
                    ),
                    cls="p-2",
                ),
                cls="card bg-base-100 shadow-sm mb-2",
            )
        )

    return Div(*journal_cards, id="recent-curated-journals")


# ============================================================================
# COMPONENT CLASS
# ============================================================================


class JournalUIComponents:
    """Reusable component library for two-tier journal interface."""

    @staticmethod
    def render_voice_journal_form() -> Any:
        """
        Voice journal upload form (PJ1 - ephemeral).

        Features:
        - Audio file input (mp3, m4a, wav)
        - Optional title field
        - HTMX-based form submission
        - Note about auto-cleanup
        """
        return Card(
            CardBody(
                H3("Voice Journal", cls="card-title"),
                P("Upload an audio recording of your thoughts", cls="text-gray-500"),
                P(
                    Span("Ephemeral", cls="badge badge-warning"),
                    " - Only 3 most recent kept (auto-cleanup)",
                    cls="text-sm text-gray-500",
                ),
                Form(
                    # File input
                    Div(
                        Input(
                            type="file",
                            name="file",
                            id="voice-journal-input",
                            accept="audio/*",
                            required=True,
                            cls="file-input file-input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Title input
                    Div(
                        Label("Title (optional)", cls="label-text"),
                        Input(
                            type="text",
                            name="title",
                            id="voice-journal-title",
                            placeholder="e.g., Morning Reflection",
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Upload button
                    Div(
                        Button(
                            "Upload & Process",
                            variant=ButtonT.primary,
                            type="submit",
                        ),
                        cls="text-center",
                    ),
                    # Upload status (HTMX target)
                    Div(id="voice-upload-status", cls="mt-4 text-center"),
                    # HTMX attributes
                    **{
                        "hx-post": "/journals/upload/voice",
                        "hx-target": "#voice-upload-status",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                    },
                    id="voice-journal-form",
                ),
            ),
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        )

    @staticmethod
    def render_curated_journal_form() -> Any:
        """
        Curated journal upload form (PJ2 - permanent).

        Features:
        - Text/Markdown file input (.txt, .md)
        - Optional title field
        - HTMX-based form submission
        - Note about permanent storage
        """
        return Card(
            CardBody(
                H3("Curated Journal", cls="card-title"),
                P("Upload a text or markdown file", cls="text-gray-500"),
                P(
                    Span("Permanent", cls="badge badge-success"),
                    " - Stored permanently for intentional reflection",
                    cls="text-sm text-gray-500",
                ),
                Form(
                    # File input
                    Div(
                        Input(
                            type="file",
                            name="file",
                            id="curated-journal-input",
                            accept=".txt,.md,text/plain,text/markdown",
                            required=True,
                            cls="file-input file-input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Title input
                    Div(
                        Label("Title (optional)", cls="label-text"),
                        Input(
                            type="text",
                            name="title",
                            id="curated-journal-title",
                            placeholder="e.g., Weekly Reflection",
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Upload button
                    Div(
                        Button(
                            "Save Journal",
                            variant=ButtonT.primary,
                            type="submit",
                        ),
                        cls="text-center mt-4",
                    ),
                    # Upload status (HTMX target)
                    Div(id="curated-upload-status", cls="mt-4 text-center"),
                    # HTMX attributes
                    **{
                        "hx-post": "/journals/upload/curated",
                        "hx-target": "#curated-upload-status",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                    },
                    id="curated-journal-form",
                ),
            ),
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        )

    @staticmethod
    def render_voice_journals_section() -> Any:
        """Recent voice journals list (max 3, HTMX loaded)."""
        return Card(
            CardBody(
                H4(
                    "Recent Voice Journals ",
                    Span("(max 3)", cls="text-sm text-gray-500"),
                    cls="card-title",
                ),
                Div(
                    P("Loading...", cls="text-center text-gray-500"),
                    id="recent-voice-journals",
                    **{
                        "hx-get": "/journals/recent/voice",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
            ),
            cls="card bg-base-100 shadow-sm",
        )

    @staticmethod
    def render_curated_journals_section() -> Any:
        """Curated journals list (all, HTMX loaded)."""
        return Card(
            CardBody(
                H4("Curated Journals", cls="card-title"),
                Div(
                    P("Loading...", cls="text-center text-gray-500"),
                    id="recent-curated-journals",
                    **{
                        "hx-get": "/journals/recent/curated",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
            ),
            cls="card bg-base-100 shadow-sm",
        )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_journals_ui_routes(_app, rt, journals_core_service, transcription_service=None):
    """
    Create two-tier journal UI routes with HTMX support.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        journals_core_service: JournalsCoreService - CRUD for Journal nodes
        transcription_service: Optional transcription service for audio processing

    Routes:
        /journals - Main dashboard with tabs
        /journals/upload/voice - Voice journal upload (PJ1)
        /journals/upload/curated - Curated journal upload (PJ2)
        /journals/recent/voice - Recent voice journals (max 3)
        /journals/recent/curated - Recent curated journals (all)
    """
    from datetime import datetime

    if not journals_core_service:
        logger.warning("JournalsCoreService not provided - journal routes may not work")

    logger.info("Creating Journals UI routes (two-tier system)")

    # ========================================================================
    # HTMX ENDPOINTS - VOICE JOURNALS (PJ1)
    # ========================================================================

    @rt("/journals/upload/voice")
    async def upload_voice_journal(request: Request) -> Any:
        """
        HTMX endpoint for voice journal upload (PJ1 - ephemeral).
        Uses JournalType.VOICE with FIFO auto-cleanup.
        """
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            title = form.get("title", "")

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status(
                    "error",
                    "No audio file provided",
                    is_error=True,
                    target_id="voice-upload-status",
                )

            user_uid = require_authenticated_user(request)  # Enforce authentication
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename

            logger.info(f"Voice journal upload: {filename} ({len(file_content)} bytes)")

            # Create voice journal with FIFO cleanup
            # TODO: Add transcription service integration for audio processing
            journal = create_journal(
                uid=f"journal:{user_uid}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_uid=user_uid,
                title=title or filename or "Voice Journal",
                content=f"[Audio upload: {filename}]",  # Placeholder until transcription
                journal_type=JournalType.VOICE,
                metadata={
                    "original_filename": filename,
                    "file_size": len(file_content),
                    "pending_transcription": True,
                },
            )

            result = await journals_core_service.create_journal(journal, enforce_fifo=True)

            if result.is_error:
                error = result.expect_error()
                return _render_upload_status(
                    "error",
                    str(error),
                    is_error=True,
                    target_id="voice-upload-status",
                )

            created_journal = result.value
            return _render_upload_status(
                "completed",
                "Success",
                created_journal.uid,
                target_id="voice-upload-status",
            )

        except Exception as e:
            logger.error(f"Error uploading voice journal: {e}", exc_info=True)
            return _render_upload_status(
                "error", str(e), is_error=True, target_id="voice-upload-status"
            )

    @rt("/journals/recent/voice")
    async def get_recent_voice_journals(request: Request) -> Any:
        """HTMX endpoint for loading recent voice journals (max 3)."""
        try:
            user_uid = require_authenticated_user(request)  # Enforce authentication

            result = await journals_core_service.get_voice_journals(user_uid, limit=3)

            if result.is_error:
                return Div(
                    P("Failed to load voice journals", cls="text-center text-error"),
                    id="recent-voice-journals",
                )

            journals = result.value or []
            return _render_recent_voice_journals(journals)

        except Exception as e:
            logger.error(f"Error loading voice journals: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="recent-voice-journals",
            )

    # ========================================================================
    # HTMX ENDPOINTS - CURATED JOURNALS (PJ2)
    # ========================================================================

    @rt("/journals/upload/curated")
    async def upload_curated_journal(request: Request) -> Any:
        """
        HTMX endpoint for curated journal upload (PJ2 - permanent).
        Uses JournalType.CURATED with no auto-cleanup.
        """
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            title = form.get("title", "")

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status(
                    "error",
                    "No file provided",
                    is_error=True,
                    target_id="curated-upload-status",
                )

            # Validate file type
            filename = uploaded_file.filename or ""
            if not filename.lower().endswith((".txt", ".md")):
                return _render_upload_status(
                    "error",
                    "Only .txt and .md files are accepted for curated journals",
                    is_error=True,
                    target_id="curated-upload-status",
                )

            user_uid = require_authenticated_user(request)  # Enforce authentication
            file_content = await uploaded_file.read()

            logger.info(f"Curated journal upload: {filename} ({len(file_content)} bytes)")

            # Decode file content as text
            try:
                content = file_content.decode("utf-8")
            except UnicodeDecodeError:
                content = file_content.decode("latin-1")

            # Create curated journal (permanent, no cleanup)
            journal = create_journal(
                uid=f"journal:{user_uid}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_uid=user_uid,
                title=title or filename or "Curated Journal",
                content=content,
                journal_type=JournalType.CURATED,
                metadata={
                    "original_filename": filename,
                    "file_size": len(file_content),
                },
            )

            result = await journals_core_service.create_journal(journal, enforce_fifo=False)

            if result.is_error:
                error = result.expect_error()
                return _render_upload_status(
                    "error",
                    str(error),
                    is_error=True,
                    target_id="curated-upload-status",
                )

            created_journal = result.value
            return _render_upload_status(
                "completed",
                "Success",
                created_journal.uid,
                target_id="curated-upload-status",
            )

        except Exception as e:
            logger.error(f"Error uploading curated journal: {e}", exc_info=True)
            return _render_upload_status(
                "error", str(e), is_error=True, target_id="curated-upload-status"
            )

    @rt("/journals/recent/curated")
    async def get_recent_curated_journals(request: Request) -> Any:
        """HTMX endpoint for loading curated journals (no limit)."""
        try:
            user_uid = require_authenticated_user(request)  # Enforce authentication

            result = await journals_core_service.get_curated_journals(user_uid, limit=50)

            if result.is_error:
                return Div(
                    P("Failed to load curated journals", cls="text-center text-error"),
                    id="recent-curated-journals",
                )

            journals = result.value or []
            return _render_recent_curated_journals(journals)

        except Exception as e:
            logger.error(f"Error loading curated journals: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="recent-curated-journals",
            )

    # LEGACY ENDPOINTS REMOVED (January 2026)
    # Previously: /journals/upload/audio -> redirected to upload_voice_journal
    # Previously: /journals/recent -> redirected to get_recent_voice_journals
    # Use /journals/recent/voice and /journals/upload/voice instead

    # ========================================================================
    # MAIN DASHBOARD
    # ========================================================================

    @rt("/journals")
    async def journals_dashboard(request: Request) -> Any:
        """
        Two-tier journal dashboard with tabs.

        Tabs:
        - Voice Journals (PJ1): Ephemeral, max 3, auto-cleanup
        - Curated Journals (PJ2): Permanent, text/markdown
        """
        require_authenticated_user(request)  # Enforce authentication

        # Build tab components
        voice_form = JournalUIComponents.render_voice_journal_form()
        voice_list = JournalUIComponents.render_voice_journals_section()
        curated_form = JournalUIComponents.render_curated_journal_form()
        curated_list = JournalUIComponents.render_curated_journals_section()

        # Tab navigation (DaisyUI tabs)
        # WCAG 2.1 Level AA accessible tabs with Alpine.js
        tabs = Div(
            Div(
                A(
                    "Voice Journals",
                    cls="tab tab-active",
                    role="tab",
                    id="tab-voice-btn",
                    **{
                        "aria-controls": "tab-voice",
                        "aria-selected": "true",
                        "tabindex": 0,
                        ":aria-selected": "activeTab === 'voice' ? 'true' : 'false'",
                        ":tabindex": "activeTab === 'voice' ? 0 : -1",
                        ":class": "{'tab-active': activeTab === 'voice'}",
                        "@click.prevent": "setActiveTab('voice')",
                        "@keydown": "handleTabKeydown($event, 'voice')",
                    },
                ),
                A(
                    "Curated Journals",
                    cls="tab",
                    role="tab",
                    id="tab-curated-btn",
                    **{
                        "aria-controls": "tab-curated",
                        "aria-selected": "false",
                        "tabindex": -1,
                        ":aria-selected": "activeTab === 'curated' ? 'true' : 'false'",
                        ":tabindex": "activeTab === 'curated' ? 0 : -1",
                        ":class": "{'tab-active': activeTab === 'curated'}",
                        "@click.prevent": "setActiveTab('curated')",
                        "@keydown": "handleTabKeydown($event, 'curated')",
                    },
                ),
                cls="tabs tabs-bordered",
                role="tablist",
                **{"x-data": "accessibleTabs({ activeTab: 'voice' })"},
            ),
            cls="mb-4",
        )

        # Tab content with role="tabpanel" for screen readers
        tab_content = Div(
            # Voice Journals Tab
            Div(
                Div(
                    Div(voice_form, cls="w-full md:w-2/3"),
                    cls="flex justify-center mb-4",
                ),
                voice_list,
                id="tab-voice",
                role="tabpanel",
                **{
                    "aria-labelledby": "tab-voice-btn",
                    ":class": "activeTab === 'voice' ? 'block' : 'hidden'",
                },
            ),
            # Curated Journals Tab
            Div(
                Div(
                    Div(curated_form, cls="w-full md:w-2/3"),
                    cls="flex justify-center mb-4",
                ),
                curated_list,
                id="tab-curated",
                role="tabpanel",
                **{
                    "aria-labelledby": "tab-curated-btn",
                    ":class": "activeTab === 'curated' ? 'block' : 'hidden'",
                },
            ),
            cls="mt-4",
            **{"x-data": "{}"},  # Share Alpine.js scope with tabs above
        )

        # Main dashboard layout
        dashboard = Container(
            # Header
            Div(
                H1("Journals", cls="text-3xl font-bold"),
                P(
                    "Capture your thoughts through voice or curated text",
                    cls="text-lg text-gray-500",
                ),
                cls="text-center mb-8",
            ),
            # Tabs
            tabs,
            tab_content,
            # HTMX handling for form submissions
            FTScript(
                NotStr("""
                // Note: Tab switching now handled by Alpine.js accessibleTabs component (WCAG 2.1 Level AA)

                // Add loading state to buttons during HTMX requests
                document.body.addEventListener('htmx:beforeRequest', function(evt) {
                    const form = evt.detail.elt;
                    const btn = form.querySelector('button[type="submit"]');
                    if (btn) {
                        btn.disabled = true;
                        btn.textContent = 'Processing...';
                    }
                });

                document.body.addEventListener('htmx:afterRequest', function(evt) {
                    const form = evt.detail.elt;
                    if (form.id === 'voice-journal-form') {
                        form.reset();
                        // Reload voice journals list
                        htmx.trigger('#recent-voice-journals', 'load');
                    } else if (form.id === 'curated-journal-form') {
                        form.reset();
                        // Reload curated journals list
                        htmx.trigger('#recent-curated-journals', 'load');
                    }
                    // Re-enable button
                    const btn = form.querySelector('button[type="submit"]');
                    if (btn) {
                        btn.disabled = false;
                        if (form.id === 'voice-journal-form') {
                            btn.textContent = 'Upload & Process';
                        } else {
                            btn.textContent = 'Save Journal';
                        }
                    }
                });
            """)
            ),
            cls="container mx-auto mt-8 px-4",
        )

        # Create navbar
        navbar = create_navbar_for_request(request, active_page="journals")

        return Div(navbar, dashboard)

    logger.info("Journals UI routes created successfully (two-tier system)")
    logger.info("   - /journals: Two-tier dashboard with tabs")
    logger.info("   - /journals/upload/voice: Voice journal upload (PJ1)")
    logger.info("   - /journals/upload/curated: Curated journal upload (PJ2)")
    logger.info("   - /journals/recent/voice: Voice journals list (max 3)")
    logger.info("   - /journals/recent/curated: Curated journals list")


# Export the route creation function
__all__ = ["create_journals_ui_routes"]
