"""
Transcription UI Routes
=======================

Component-based UI rendering for audio transcription interface.
Allows users to upload MP3 files for Deepgram transcription.

✅ PHASE 4 STATUS: HTMX-Powered (JavaScript-Minimal)
- Architecture: Component-based with TranscriptionUIComponents class
- Forms: HTMX file upload with hx-post
- Dynamic updates: HTMX with hx-trigger="load" and "every 30s"
- Note: Minimal JavaScript only for UX enhancements (button states)
"""

__version__ = "3.0"

from typing import Any

from fasthtml.common import H1, H2, H3, A, Form, NotStr, P, Script
from starlette.requests import Request

from core.auth import get_current_user
from core.ui.daisy_components import (
    Button,
    Card,
    Container,
    Div,
    Input,
    Label,
    Span,
    Textarea,
)
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.transcription.ui")


# ============================================================================
# HTMX FRAGMENT RENDERING FUNCTIONS
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    is_error: bool = False,
) -> Any:
    """Render upload status as HTML fragment for HTMX swap."""
    if is_error:
        return Div(
            Div(
                H3("Upload Failed", cls="font-semibold text-red-700"),
                P(message, cls="text-red-600"),
                cls="p-4 bg-red-50 border border-red-200 rounded-lg",
            ),
            id="upload-status",
        )

    return Div(
        Div(
            H3("Upload Successful!", cls="font-semibold text-green-700"),
            P(message, cls="text-green-600"),
            cls="p-4 bg-green-50 border border-green-200 rounded-lg",
        ),
        id="upload-status",
    )


def _get_status_class(status: str) -> str:
    """Get CSS class for transcription status badge."""
    classes = {
        "completed": "bg-green-100 text-green-700",
        "processing": "bg-yellow-100 text-yellow-700",
        "failed": "bg-red-100 text-red-700",
        "pending": "bg-gray-100 text-gray-700",
    }
    return classes.get(status, "bg-gray-100 text-gray-700")


def _render_transcription_item(t: dict) -> Any:
    """Render a single transcription item."""
    return Div(
        Div(
            H3(t.get("title") or "Untitled", cls="font-semibold text-gray-800"),
            Span(
                t.get("status", "unknown"),
                cls=f"px-2 py-1 text-xs rounded {_get_status_class(t.get('status', ''))}",
            ),
            cls="flex justify-between items-start mb-2",
        ),
        P(t.get("description") or "No description", cls="text-sm text-gray-600 mb-2"),
        Div(
            Span(t.get("created_at", ""), cls="text-xs text-gray-500"),
            A(
                "View Details",
                href=f"/api/transcriptions/v2/{t.get('uid', '')}",
                cls="text-blue-600 hover:underline text-xs",
            ),
            cls="flex justify-between items-center",
        ),
        cls="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors",
    )


def _render_transcriptions_list(transcriptions: list) -> Any:
    """Render transcriptions list as HTML fragment for HTMX swap."""
    if not transcriptions:
        return Div(
            P(
                "No transcriptions yet. Upload your first audio file!",
                cls="text-gray-500 text-center py-8",
            ),
            id="transcriptions-container",
            # Keep polling for updates
            **{
                "hx-get": "/transcriptions/list",
                "hx-trigger": "every 30s",
                "hx-swap": "outerHTML",
            },
        )

    return Div(
        *[_render_transcription_item(t) for t in transcriptions],
        id="transcriptions-container",
        cls="space-y-4",
        # Auto-refresh every 30 seconds
        **{
            "hx-get": "/transcriptions/list",
            "hx-trigger": "every 30s",
            "hx-swap": "outerHTML",
        },
    )


def _render_statistics(stats: dict) -> Any:
    """Render statistics as HTML fragment for HTMX swap."""
    return Div(
        Div(
            Span(str(stats.get("total", 0)), cls="text-3xl font-bold text-blue-600"),
            P("Total Transcriptions", cls="text-sm text-gray-600"),
            cls="text-center",
        ),
        Div(
            Span(str(stats.get("pending", 0)), cls="text-3xl font-bold text-yellow-600"),
            P("Pending", cls="text-sm text-gray-600"),
            cls="text-center",
        ),
        Div(
            Span(str(stats.get("completed", 0)), cls="text-3xl font-bold text-green-600"),
            P("Completed", cls="text-sm text-gray-600"),
            cls="text-center",
        ),
        Div(
            Span(str(stats.get("failed", 0)), cls="text-3xl font-bold text-red-600"),
            P("Failed", cls="text-sm text-gray-600"),
            cls="text-center",
        ),
        id="stats-container",
        cls="grid grid-cols-2 md:grid-cols-4 gap-6",
        # Auto-refresh every 30 seconds
        **{
            "hx-get": "/transcriptions/stats",
            "hx-trigger": "every 30s",
            "hx-swap": "outerHTML",
        },
    )


class TranscriptionUIComponents:
    """
    Reusable component library for transcription interface.

    ✅ PHASE 3 MIGRATION STATUS:
    - Architecture: Component-based ✅
    - File upload form: Manual composition (required for multipart/form-data)
    - Display components: Organized in static methods
    - FormGenerator: Not applicable for file uploads

    This class demonstrates that not all forms should use FormGenerator.
    File uploads with progress tracking and JavaScript integration are
    better handled with manual composition within component methods.

    Component Organization:
    - render_upload_form() - File upload with progress tracking
    - render_recent_transcriptions() - Dynamic list display
    - render_statistics_card() - Analytics display
    """

    @staticmethod
    def render_upload_form() -> Any:
        """
        Audio file upload form with HTMX.

        ✅ HTMX MIGRATION:
        - Uses hx-post for form submission
        - Uses hx-encoding="multipart/form-data" for file upload
        - Returns HTML fragments instead of JSON
        - Minimal JavaScript only for UX (button states)
        """
        return Div(
            Form(
                # File Upload
                Div(
                    Label(
                        "Audio File (MP3)",
                        for_="audio-file",
                        cls="block text-sm font-medium text-gray-700 mb-2",
                    ),
                    Input(
                        type="file",
                        id="audio-file",
                        name="audio_file",
                        accept=".mp3,audio/mpeg",
                        required=True,
                        cls="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    ),
                    P("Supported format: MP3 (max 100MB)", cls="text-xs text-gray-500 mt-1"),
                    cls="mb-4",
                ),
                # Optional: Title
                Div(
                    Label(
                        "Title (optional)",
                        for_="title",
                        cls="block text-sm font-medium text-gray-700 mb-2",
                    ),
                    Input(
                        type="text",
                        id="title",
                        name="title",
                        placeholder="e.g., Team Meeting 2025-10-02",
                        cls="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    ),
                    cls="mb-4",
                ),
                # Optional: Description
                Div(
                    Label(
                        "Description (optional)",
                        for_="description",
                        cls="block text-sm font-medium text-gray-700 mb-2",
                    ),
                    Textarea(
                        id="description",
                        name="description",
                        placeholder="Add any context about this recording...",
                        rows="3",
                        cls="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    ),
                    cls="mb-6",
                ),
                # Submit Button
                Div(
                    Button(
                        "Upload & Transcribe",
                        type="submit",
                        id="upload-btn",
                        cls="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors",
                    ),
                    cls="mb-4",
                ),
                id="transcription-form",
                cls="space-y-2",
                # HTMX file upload
                **{
                    "hx-post": "/transcriptions/upload",
                    "hx-target": "#upload-status",
                    "hx-swap": "outerHTML",
                    "hx-encoding": "multipart/form-data",
                },
            ),
            # Upload status container (HTMX target)
            Div(id="upload-status"),
        )

    @staticmethod
    def render_upload_instructions() -> Any:
        """Upload instructions card component."""
        return Div(
            H3("Instructions", cls="text-lg font-semibold mb-3 text-gray-800"),
            Div(
                P("1. Select an MP3 audio file from your device", cls="text-sm text-gray-600 mb-2"),
                P("2. Optionally add a title and description", cls="text-sm text-gray-600 mb-2"),
                P("3. Click 'Upload & Transcribe' to process", cls="text-sm text-gray-600 mb-2"),
                P(
                    "4. Transcription will be processed via Deepgram",
                    cls="text-sm text-gray-600 mb-2",
                ),
                P(
                    "5. View results in the Recent Transcriptions section below",
                    cls="text-sm text-gray-600",
                ),
                cls="space-y-1",
            ),
            cls="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200",
        )

    @staticmethod
    def render_recent_transcriptions_section() -> Any:
        """Recent transcriptions list section with HTMX auto-loading."""
        return Card(
            H2("Recent Transcriptions", cls="text-2xl font-semibold mb-6 text-gray-800"),
            # HTMX-powered container - loads on page load, refreshes every 30s
            Div(
                P(
                    "Loading transcriptions...",
                    cls="text-gray-500 text-center py-8",
                ),
                id="transcriptions-container",
                cls="min-h-32",
                **{
                    "hx-get": "/transcriptions/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            # Manual refresh button using HTMX
            Button(
                "Refresh List",
                cls="mt-4 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold py-2 px-4 rounded-lg transition-colors",
                **{
                    "hx-get": "/transcriptions/list",
                    "hx-target": "#transcriptions-container",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="mb-8 p-6",
        )

    @staticmethod
    def render_statistics_card() -> Any:
        """Transcription statistics display card with HTMX auto-loading."""
        return Card(
            H2("Transcription Statistics", cls="text-2xl font-semibold mb-6 text-gray-800"),
            # HTMX-powered container - loads on page load, refreshes every 30s
            Div(
                P("Loading statistics...", cls="text-gray-500 text-center py-4"),
                id="stats-container",
                cls="grid grid-cols-2 md:grid-cols-4 gap-6",
                **{
                    "hx-get": "/transcriptions/stats",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="p-6",
        )


def create_transcription_ui_routes(_app, rt, transcription_service):
    """
    Create transcription UI routes with HTMX endpoints.

    Routes:
    - GET /transcriptions - Main dashboard
    - POST /transcriptions/upload - HTMX file upload (returns HTML fragment)
    - GET /transcriptions/list - HTMX transcription list (returns HTML fragment)
    - GET /transcriptions/stats - HTMX statistics (returns HTML fragment)

    Args:
        _app: FastHTML application instance
        rt: Router instance
        transcription_service: Transcription service instance
    """

    @rt("/transcriptions")
    async def transcription_dashboard(request: Request) -> Any:
        """Audio transcription dashboard with HTMX-powered interface."""
        # Create transcription interface
        transcription_interface = Container(
            # Header
            Div(
                H1("Audio Transcription", cls="text-4xl font-bold text-center mb-2 text-gray-900"),
                P(
                    "Upload MP3 files for automatic transcription via Deepgram",
                    cls="text-muted-foreground text-center mb-8 text-lg",
                ),
                cls="dashboard-header mb-12",
            ),
            # Upload Section
            Card(
                H2("Upload Audio", cls="text-2xl font-semibold mb-6 text-gray-800"),
                TranscriptionUIComponents.render_upload_form(),
                TranscriptionUIComponents.render_upload_instructions(),
                cls="mb-8 p-6",
            ),
            # Recent Transcriptions Section (HTMX-loaded)
            TranscriptionUIComponents.render_recent_transcriptions_section(),
            # Statistics Card (HTMX-loaded)
            TranscriptionUIComponents.render_statistics_card(),
            # Minimal JavaScript for UX enhancements only
            Script(
                NotStr("""
                // HTMX event handlers for button state management
                document.body.addEventListener('htmx:beforeRequest', function(evt) {
                    if (evt.detail.elt.id === 'transcription-form') {
                        const btn = document.getElementById('upload-btn');
                        if (btn) {
                            btn.disabled = true;
                            btn.textContent = 'Uploading...';
                        }
                    }
                });

                document.body.addEventListener('htmx:afterRequest', function(evt) {
                    if (evt.detail.elt.id === 'transcription-form') {
                        const btn = document.getElementById('upload-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Upload & Transcribe';
                        }
                        // Reset form on success
                        if (evt.detail.successful) {
                            evt.detail.elt.reset();
                            // Trigger refresh of list and stats
                            htmx.trigger('#transcriptions-container', 'load');
                            htmx.trigger('#stats-container', 'load');
                        }
                    }
                });
            """)
            ),
            cls="transcription-dashboard p-8 bg-gray-50 min-h-screen",
        )

        navbar = create_navbar_for_request(request, active_page="transcriptions")
        return Div(navbar, transcription_interface)

    # ========================================================================
    # HTMX FRAGMENT ENDPOINTS
    # ========================================================================

    @rt("/transcriptions/upload")
    async def transcriptions_upload(request: Request) -> Any:
        """
        HTMX endpoint for file upload.
        Returns HTML fragment for status display.
        """
        try:
            form_data = await request.form()
            audio_file = form_data.get("audio_file")
            title = form_data.get("title", "")
            description = form_data.get("description", "")

            if not audio_file:
                return _render_upload_status(
                    status="error",
                    message="No audio file provided",
                    is_error=True,
                )

            # Call the transcription service
            if transcription_service:
                user_uid = get_current_user(request)
                result = await transcription_service.create_transcription(
                    audio_file=audio_file,
                    title=title or None,
                    description=description or None,
                    user_uid=user_uid,
                )

                if result.is_error:
                    return _render_upload_status(
                        status="error",
                        message=result.error.message if result.error else "Upload failed",
                        is_error=True,
                    )

                return _render_upload_status(
                    status="success",
                    message="Transcription started! Check the list below for progress.",
                )

            # Fallback for development (no service)
            return _render_upload_status(
                status="success",
                message="Upload received (service not available in dev mode)",
            )

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return _render_upload_status(
                status="error",
                message=f"Upload failed: {e!s}",
                is_error=True,
            )

    @rt("/transcriptions/list")
    async def transcriptions_list(request: Request) -> Any:
        """
        HTMX endpoint for transcription list.
        Returns HTML fragment with auto-refresh trigger.
        """
        try:
            if transcription_service:
                user_uid = get_current_user(request)
                result = await transcription_service.get_recent_transcriptions(
                    user_uid=user_uid,
                    limit=10,
                )

                if result.is_ok:
                    transcriptions = result.value or []
                    return _render_transcriptions_list(transcriptions)

            # Fallback for development
            return _render_transcriptions_list([])

        except Exception as e:
            logger.error(f"Error loading transcriptions: {e}")
            return Div(
                P(
                    f"Error loading transcriptions: {e!s}",
                    cls="text-red-500 text-center py-8",
                ),
                id="transcriptions-container",
                **{
                    "hx-get": "/transcriptions/list",
                    "hx-trigger": "every 30s",
                    "hx-swap": "outerHTML",
                },
            )

    @rt("/transcriptions/stats")
    async def transcriptions_stats(request: Request) -> Any:
        """
        HTMX endpoint for statistics.
        Returns HTML fragment with auto-refresh trigger.
        """
        try:
            if transcription_service:
                user_uid = get_current_user(request)
                result = await transcription_service.get_analytics(user_uid=user_uid)

                if result.is_ok:
                    stats = result.value or {}
                    return _render_statistics(stats)

            # Fallback for development
            return _render_statistics(
                {
                    "total": 0,
                    "pending": 0,
                    "completed": 0,
                    "failed": 0,
                }
            )

        except Exception as e:
            logger.error(f"Error loading statistics: {e}")
            return _render_statistics(
                {
                    "total": 0,
                    "pending": 0,
                    "completed": 0,
                    "failed": 0,
                }
            )

    logger.info("✅ Transcription UI routes created (HTMX-powered)")


# Export
__all__ = ["create_transcription_ui_routes"]
