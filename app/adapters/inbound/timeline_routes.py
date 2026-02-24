"""
Timeline Routes - REST Endpoints and Web Interface
=================================================

Provides REST API endpoints and web interfaces for timeline visualization.

Architecture (January 2026 - Vis.js Timeline):
    - UI Components: /components/timeline_components.py
    - CSS: /static/css/timeline.css
    - Alpine.js: timelineVis component in /static/js/skuel.js
    - Vendor: /static/vendor/vis-timeline/

The /timelines web interface now uses Vis.js Timeline instead of Markwhen.
Legacy Markwhen export API remains for backwards compatibility.

Version: 3.0 - Vis.js Timeline
"""

from datetime import date
from typing import Any

from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from ui.timeline.components import (
    render_timeline_error,
    render_timeline_viewer_page,
)
from core.models.enums import EntityStatus
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_timeline_api_routes(_app, rt, tasks_service: Any):
    """Create timeline routes for both REST API and web interface."""

    @rt("/api/tasks/timeline")
    async def get_tasks_timeline(
        request,
        start_date: str | None = None,
        end_date: str | None = None,
        project: str | None = None,
        status: str | None = None,
        include_completed: bool = True,
        format: str = "markwhen",
    ) -> Response:
        """
        REST API endpoint for Markwhen timeline export.

        Query Parameters:
        - start_date: ISO date string (YYYY-MM-DD) for filtering start
        - end_date: ISO date string (YYYY-MM-DD) for filtering end
        - project: Project ID to filter by
        - status: Comma-separated list of statuses to include
        - include_completed: Whether to include completed tasks (default: true)
        - format: Export format (currently only 'markwhen' supported)

        Returns:
        - 200: Markwhen timeline content (text/plain) with file download headers
        - 400: Invalid parameters or export failure
        - 500: Server error

        Note: This route does NOT use @boundary_handler because it needs custom
        Content-Disposition headers for file downloads.
        """
        require_authenticated_user(request)
        try:
            logger.info(
                "Timeline API request received",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "project": project,
                    "status": status,
                    "include_completed": include_completed,
                },
            )

            # Parse date parameters
            start_date_parsed = None
            if start_date:
                try:
                    start_date_parsed = date.fromisoformat(start_date)
                except ValueError:
                    return Response(
                        content=f"Invalid start_date format. Use YYYY-MM-DD. Got: {start_date}",
                        status_code=400,
                        media_type="text/plain",
                    )

            end_date_parsed = None
            if end_date:
                try:
                    end_date_parsed = date.fromisoformat(end_date)
                except ValueError:
                    return Response(
                        content=f"Invalid end_date format. Use YYYY-MM-DD. Got: {end_date}",
                        status_code=400,
                        media_type="text/plain",
                    )

            # Validate date range
            if start_date_parsed and end_date_parsed and start_date_parsed > end_date_parsed:
                return Response(
                    content=f"start_date ({start_date}) cannot be after end_date ({end_date})",
                    status_code=400,
                    media_type="text/plain",
                )

            # Parse status filter
            status_filter = None
            if status:
                status_filter = [s.strip() for s in status.split(",") if s.strip()]
                # Validate status values
                valid_statuses = {s.value for s in EntityStatus}
                invalid_statuses = [s for s in status_filter if s not in valid_statuses]
                if invalid_statuses:
                    return Response(
                        content=f"Invalid status values: {invalid_statuses}. Valid: {sorted(valid_statuses)}",
                        status_code=400,
                        media_type="text/plain",
                    )

            # Validate format
            if format != "markwhen":
                return Response(
                    content=f"Unsupported format: {format}. Only 'markwhen' is supported.",
                    status_code=400,
                    media_type="text/plain",
                )

            # Get tasks service and export timeline
            if tasks_service is None:
                raise RuntimeError(
                    "TasksService must be explicitly injected for timeline functionality"
                )

            result = await tasks_service.export_to_markwhen(
                start_date=start_date_parsed,
                end_date=end_date_parsed,
                project_filter=project,
                status_filter=status_filter,
                include_completed=include_completed,
            )

            if result.is_success:
                timeline_content = result.value

                # Generate filename based on filters
                filename_parts = ["tasks"]
                if project:
                    filename_parts.append(f"project-{project}")
                if start_date or end_date:
                    date_range = f"{start_date or 'start'}-to-{end_date or 'end'}"
                    filename_parts.append(date_range)
                filename = "_".join(filename_parts) + ".mw"

                logger.info(
                    "Timeline export successful",
                    content_length=len(timeline_content),
                    filename=filename,
                )

                return Response(
                    content=timeline_content,
                    media_type="text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            else:
                logger.error("Timeline export failed", error=str(result.error))
                return Response(
                    content=f"Timeline export failed: {result.error}",
                    status_code=400,
                    media_type="text/plain",
                )

        except Exception as e:
            logger.error("Timeline API error", error=str(e))
            return Response(
                content=f"Internal server error: {e!s}", status_code=500, media_type="text/plain"
            )

    @rt("/api/tasks/timeline/preview")
    @boundary_handler()
    async def get_timeline_preview(
        request,
        start_date: str | None = None,
        end_date: str | None = None,
        project: str | None = None,
        status: str | None = None,
        include_completed: bool = True,
    ) -> Result[Any]:
        """
        REST API endpoint for timeline preview (first 10 lines + stats).

        Same parameters as full timeline export but returns JSON with preview data.
        Useful for UI previews before full export.
        """
        require_authenticated_user(request)
        try:
            # Use same parameter parsing as main endpoint
            start_date_parsed = None
            if start_date:
                try:
                    start_date_parsed = date.fromisoformat(start_date)
                except ValueError:
                    return Result.fail(
                        Errors.validation(
                            message="Invalid start_date format. Use YYYY-MM-DD.",
                            field="start_date",
                            value=start_date,
                        )
                    )

            end_date_parsed = None
            if end_date:
                try:
                    end_date_parsed = date.fromisoformat(end_date)
                except ValueError:
                    return Result.fail(
                        Errors.validation(
                            message="Invalid end_date format. Use YYYY-MM-DD.",
                            field="end_date",
                            value=end_date,
                        )
                    )

            status_filter = None
            if status:
                status_filter = [s.strip() for s in status.split(",") if s.strip()]

            # Get timeline content
            if tasks_service is None:
                raise RuntimeError(
                    "TasksService must be explicitly injected for timeline functionality"
                )
            result = await tasks_service.export_to_markwhen(
                start_date=start_date_parsed,
                end_date=end_date_parsed,
                project_filter=project,
                status_filter=status_filter,
                include_completed=include_completed,
            )

            if result.is_success:
                timeline_content = result.value
                lines = timeline_content.split("\n")

                # Extract preview (first 10 content lines, skip title/comments)
                content_lines = [
                    line for line in lines if line.strip() and not line.strip().startswith("//")
                ]
                preview_lines = content_lines[:10]

                # Extract stats from comments
                stats = {}
                for line in lines:
                    if line.strip().startswith("// Total tasks:"):
                        stats["total_tasks"] = line.split(":")[1].strip()
                    elif line.strip().startswith("// High Priority:"):
                        stats["high_priority"] = line.split(":")[1].strip()
                    elif line.strip().startswith("// In Progress:"):
                        stats["in_progress"] = line.split(":")[1].strip()
                    elif line.strip().startswith("// Blocked:"):
                        stats["blocked"] = line.split(":")[1].strip()
                    elif line.strip().startswith("// Overdue:"):
                        stats["overdue"] = line.split(":")[1].strip()

                return Result.ok(
                    {
                        "success": True,
                        "preview": preview_lines,
                        "stats": stats,
                        "total_lines": len(content_lines),
                        "showing_lines": len(preview_lines),
                    }
                )
            else:
                # Propagate the error from export_to_markwhen
                return Result.fail(result.expect_error())

        except Exception as e:
            logger.error("Timeline preview error", error=str(e))
            return Result.fail(Errors.system(message="Timeline preview failed", exception=e))

    @rt("/timelines")
    @boundary_handler()
    async def timeline_viewer(
        request, src: str | None = None, project: str | None = None, _view: str = "timeline"
    ) -> Result[Any]:
        """
        Web interface for Vis.js Timeline visualization.

        Query Parameters:
        - src: URL to timeline data source (optional - uses visualization API if not provided)
        - project: Project filter to apply
        - view: View type (timeline, calendar, gantt) - future enhancement

        Returns interactive Vis.js timeline viewer HTML page.
        """
        user_uid = require_authenticated_user(request)

        try:
            # Render page using Vis.js Timeline component
            return Result.ok(
                render_timeline_viewer_page(
                    src=src,
                    project=project,
                    user_uid=user_uid,
                )
            )

        except Exception as e:
            logger.error("Timeline viewer error", error=str(e))
            return Result.ok(render_timeline_error(str(e)))

    return [get_tasks_timeline, get_timeline_preview, timeline_viewer]


# ---------------------------------------------------------------------------
# DomainRouteConfig wiring
# ---------------------------------------------------------------------------

TIMELINE_CONFIG = DomainRouteConfig(
    domain_name="timeline",
    primary_service_attr="tasks",
    api_factory=create_timeline_api_routes,
)


def create_timeline_routes(app, rt, services, _sync_service=None):
    """Wire timeline routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TIMELINE_CONFIG)


__all__ = ["create_timeline_routes"]
