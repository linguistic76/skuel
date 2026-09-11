"""Activity report producers: generate now, annotate, download as Markdown.

The three routes restored/added by the calendar priority-lens arc (PR A2).
Handlers are invoked directly on request stubs, as the other route suites do;
CSRF is a real cookie+header pair (``tests/fixtures/csrf``).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
from adapters.outbound.activity_report_renderer import (
    activity_report_filename,
    render_activity_report_md,
)
from core.models.enums.pipeline import ReportSource
from core.models.report.activity_report import ActivityReport
from core.utils.result_simplified import Errors, Result
from tests.fixtures.csrf import attach_csrf


class _RouteRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "GET"):
        return self.handlers[(path, method.upper())]


def _make_request(
    *,
    user_uid: str = "user_reports",
    json_body: dict | None = None,
    query_params: dict | None = None,
    method: str = "POST",
):
    request = SimpleNamespace()
    request.session = {"user_uid": user_uid}
    request.url = SimpleNamespace(path="/test")
    request.method = method
    request.cookies = {}
    request.headers = {}
    request.query_params = query_params or {}
    request.json = AsyncMock(return_value=json_body if json_body is not None else {})
    return attach_csrf(request)


def _report(**overrides) -> ActivityReport:
    fields = {
        "uid": "activity_report_abc123",
        "title": "Activity Report — Sep 1 - Sep 8, 2026",
        "user_uid": "user_reports",
        "subject_uid": "user_reports",
        "processor_type": ReportSource.AUTOMATIC,
        "time_period": "7d",
        "period_start": datetime(2026, 9, 1),
        "period_end": datetime(2026, 9, 8),
        "depth": "standard",
        "domains_covered": ("tasks", "habits"),
        "processed_content": "# Progress Report\n\n- **Completed:** 3 / 5",
        "created_at": datetime(2026, 9, 8, 7, 30),
    }
    fields.update(overrides)
    return ActivityReport(**fields)


def _body(response) -> str:
    if hasattr(response, "body"):
        return response.body.decode()
    return to_xml(response)


@pytest.fixture
def registry_orchestrator_generator():
    registry = _RouteRegistry()
    orchestrator = AsyncMock()
    generator = AsyncMock()
    create_activity_reports_ui_routes(
        None, registry, orchestrator=orchestrator, progress_generator=generator
    )
    return registry, orchestrator, generator


# ============================================================================
# Registration
# ============================================================================


def test_producer_routes_are_registered(registry_orchestrator_generator) -> None:
    registry, _, _ = registry_orchestrator_generator
    for key in [
        ("/api/reports/progress/generate", "POST"),
        ("/api/activity-reports/annotate", "POST"),
        ("/activity-reports/md", "GET"),
    ]:
        assert key in registry.handlers, key


# ============================================================================
# Generate now
# ============================================================================


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generates_for_the_session_user_and_links_the_report(
        self, registry_orchestrator_generator
    ) -> None:
        registry, _, generator = registry_orchestrator_generator
        generator.generate = AsyncMock(return_value=Result.ok(_report()))
        handler = registry.get("/api/reports/progress/generate", "POST")

        response = await handler(
            _make_request(json_body={"time_period": "30d", "depth": "summary"})
        )

        assert response.status_code == 200
        generator.generate.assert_awaited_once_with(
            user_uid="user_reports",
            time_period="30d",
            domains=None,
            depth="summary",
            include_insights=True,
        )
        html = _body(response)
        assert "/activity-reports/detail?uid=activity_report_abc123" in html
        # The recent-reports list is refreshed out of band.
        assert 'id="progress-list"' in html and "hx-swap-oob" in html

    @pytest.mark.asyncio
    async def test_cooldown_refusal_renders_inline(self, registry_orchestrator_generator) -> None:
        registry, _, generator = registry_orchestrator_generator
        generator.generate = AsyncMock(
            return_value=Result.fail(
                Errors.business("cooldown", "A report was generated 12 minutes ago")
            )
        )
        handler = registry.get("/api/reports/progress/generate", "POST")

        response = await handler(_make_request(json_body={"time_period": "7d"}))

        assert response.status_code == 200
        assert "12 minutes ago" in _body(response)

    @pytest.mark.asyncio
    async def test_malformed_body_is_400(self, registry_orchestrator_generator) -> None:
        registry, _, generator = registry_orchestrator_generator
        handler = registry.get("/api/reports/progress/generate", "POST")

        response = await handler(_make_request(json_body={"time_period": "last-tuesday"}))

        assert response.status_code == 400
        generator.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_csrf_is_refused(self, registry_orchestrator_generator) -> None:
        registry, _, generator = registry_orchestrator_generator
        handler = registry.get("/api/reports/progress/generate", "POST")
        request = _make_request(json_body={"time_period": "7d"})
        request.headers = {}

        response = await handler(request)

        assert response.status_code == 403
        generator.generate.assert_not_awaited()


# ============================================================================
# Annotate
# ============================================================================


class TestAnnotate:
    @pytest.mark.asyncio
    async def test_saves_through_the_owner_scoped_delegation(
        self, registry_orchestrator_generator
    ) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        orchestrator.annotate_activity_report = AsyncMock(
            return_value=Result.ok({"uid": "r1", "annotation_mode": "additive"})
        )
        handler = registry.get("/api/activity-reports/annotate", "POST")

        response = await handler(
            _make_request(
                json_body={
                    "uid": "r1",
                    "annotation_mode": "additive",
                    "user_annotation": "Good week.",
                    "user_revision": None,
                }
            )
        )

        assert response.status_code == 200
        assert "Saved" in _body(response)
        orchestrator.annotate_activity_report.assert_awaited_once_with(
            "r1",
            "user_reports",
            "additive",
            user_annotation="Good week.",
            user_revision=None,
        )

    @pytest.mark.asyncio
    async def test_mode_without_text_renders_inline(self, registry_orchestrator_generator) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        orchestrator.annotate_activity_report = AsyncMock(
            return_value=Result.fail(
                Errors.validation("user_annotation required for additive mode")
            )
        )
        handler = registry.get("/api/activity-reports/annotate", "POST")

        response = await handler(
            _make_request(json_body={"uid": "r1", "annotation_mode": "additive"})
        )

        assert response.status_code == 200
        assert "user_annotation required" in _body(response)

    @pytest.mark.asyncio
    async def test_foreign_report_is_not_found(self, registry_orchestrator_generator) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        orchestrator.annotate_activity_report = AsyncMock(
            return_value=Result.fail(Errors.not_found("ActivityReport r9 not found"))
        )
        handler = registry.get("/api/activity-reports/annotate", "POST")

        response = await handler(
            _make_request(
                json_body={"uid": "r9", "annotation_mode": "revision", "user_revision": "x"}
            )
        )

        assert response.status_code == 404


# ============================================================================
# Download as Markdown
# ============================================================================


class TestDownload:
    @pytest.mark.asyncio
    async def test_owned_report_downloads_as_markdown(
        self, registry_orchestrator_generator
    ) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        orchestrator.get_activity_report = AsyncMock(return_value=Result.ok(_report()))
        handler = registry.get("/activity-reports/md", "GET")

        response = await handler(
            _make_request(method="GET", query_params={"uid": "activity_report_abc123"})
        )

        assert response.status_code == 200
        assert response.media_type == "text/markdown; charset=utf-8"
        assert response.headers["content-disposition"] == (
            'attachment; filename="activity-report-7d-2026-09-08.md"'
        )
        assert "# Activity Report" in response.body.decode()
        orchestrator.get_activity_report.assert_awaited_once_with(
            "activity_report_abc123", "user_reports"
        )

    @pytest.mark.asyncio
    async def test_foreign_report_is_404_and_never_rendered(
        self, registry_orchestrator_generator, monkeypatch
    ) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        orchestrator.get_activity_report = AsyncMock(
            return_value=Result.fail(Errors.not_found("nope"))
        )
        rendered: list[object] = []

        def _record_render(report: object) -> str:
            rendered.append(report)
            return ""

        monkeypatch.setattr(
            "adapters.inbound.activity_reports_ui.render_activity_report_md", _record_render
        )
        handler = registry.get("/activity-reports/md", "GET")

        response = await handler(_make_request(method="GET", query_params={"uid": "r9"}))

        assert response.status_code == 404
        assert response.media_type == "text/plain"
        assert rendered == []

    @pytest.mark.asyncio
    async def test_missing_uid_is_404(self, registry_orchestrator_generator) -> None:
        registry, orchestrator, _ = registry_orchestrator_generator
        handler = registry.get("/activity-reports/md", "GET")

        response = await handler(_make_request(method="GET", query_params={}))

        assert response.status_code == 404
        orchestrator.get_activity_report.assert_not_awaited()


# ============================================================================
# Renderer
# ============================================================================


class TestRenderer:
    def test_frontmatter_title_and_content(self) -> None:
        md = render_activity_report_md(_report())

        assert md.startswith("---\nuid: activity_report_abc123\n")
        assert "period: 7d" in md
        assert "period_start: 2026-09-01" in md
        assert "domains: tasks, habits" in md
        assert "processor: automatic" in md
        assert "# Activity Report — Sep 1 - Sep 8, 2026" in md
        assert "- **Completed:** 3 / 5" in md

    def test_additive_annotation_follows_the_content(self) -> None:
        md = render_activity_report_md(
            _report(annotation_mode="additive", user_annotation="Slept badly on Tuesday.")
        )

        assert "## Your notes\n\nSlept badly on Tuesday." in md
        assert "- **Completed:** 3 / 5" in md

    def test_revision_replaces_the_content(self) -> None:
        md = render_activity_report_md(
            _report(annotation_mode="revision", user_revision="My own account of the week.")
        )

        assert "My own account of the week." in md
        assert "- **Completed:** 3 / 5" not in md

    def test_recommendations_are_listed(self) -> None:
        md = render_activity_report_md(
            _report(
                metadata={
                    "intelligence": {
                        "recommendations": [
                            {"domain": "habits", "severity": "warning", "text": "Fewer habits."},
                            {"text": "Keep going."},
                            "not-a-dict",
                        ]
                    }
                }
            )
        )

        assert "## Recommendations" in md
        assert "- Fewer habits. _(habits · warning)_" in md
        assert "- Keep going." in md

    def test_filename_is_slug_safe(self) -> None:
        assert activity_report_filename(_report()) == "activity-report-7d-2026-09-08.md"
        assert activity_report_filename(_report(time_period=None, created_at=None)) == (
            "activity-report.md"
        )
