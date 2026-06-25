"""Unit tests for ``PsEngagementService.has_task_templates``.

Verifies the delegation contract: the method loads the bundle via
``_TemplateLoader`` and returns True iff ``bundle.tasks`` is non-empty.
Fails open to False on any loader error.

Real template-graph lookups are covered by integration tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.ps_engagement._template_bundle import TemplateBundle
from core.services.ps_engagement.ps_engagement_service import PsEngagementService
from core.utils.result_simplified import Errors, Result


def _service_with_loader(loader_mock: MagicMock) -> PsEngagementService:
    """Build a PsEngagementService with only the loader wired."""
    svc = PsEngagementService.__new__(PsEngagementService)
    svc._loader = loader_mock  # type: ignore[attr-defined]
    return svc


def _bundle(*, tasks: tuple = (), **_: object) -> TemplateBundle:
    return TemplateBundle(
        ps_uid="ps_test",
        tasks=tasks,
        goals=(),
        habits=(),
        events=(),
        choices=(),
        principles=(),
    )


@pytest.mark.anyio
async def test_returns_true_when_task_templates_present() -> None:
    task_template = MagicMock()
    loader = MagicMock()
    loader.load = AsyncMock(return_value=Result.ok(_bundle(tasks=(task_template,))))
    svc = _service_with_loader(loader)

    result = await svc.has_task_templates("ps_test")

    assert result is True
    loader.load.assert_awaited_once_with("ps_test")


@pytest.mark.anyio
async def test_returns_false_when_no_task_templates() -> None:
    loader = MagicMock()
    loader.load = AsyncMock(return_value=Result.ok(_bundle()))
    svc = _service_with_loader(loader)

    result = await svc.has_task_templates("ps_test")

    assert result is False


@pytest.mark.anyio
async def test_fails_open_to_false_on_loader_error() -> None:
    loader = MagicMock()
    loader.load = AsyncMock(
        return_value=Result.fail(Errors.database("load_bundle", message="Neo4j unreachable"))
    )
    svc = _service_with_loader(loader)

    result = await svc.has_task_templates("ps_test")

    assert result is False
