"""An online event needs a meeting URL — at every door that can set the pair.

The rule has two halves in ``core.models.validation_rules``:

- ``validate_url_when_online`` — a model-validator helper on the two create
  requests (``EventCreateRequest``, ``EventTemplateCreateRequest``). A field
  validator on ``meeting_url`` would never run for a request that omits the key,
  because Pydantic does not validate an omitted field's default; the model
  validator sees every field, sent or defaulted.
- ``patch_leaves_online_without_url`` — the update hooks
  (``EventsCoreService._validate_update``, ``EventTemplateService._validate_update``)
  judge a partial patch on its merged state, and only when the patch names
  ``is_online`` or ``meeting_url``: a status change or a reschedule of an event
  already stored online without a URL is not refused.

The two staged creators that build an Event from another event's logistics
(``create_event_with_context``, ``create_recurring_instances``) carry the URL
with the flag.
"""

from __future__ import annotations

import json
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from pydantic import ValidationError
from starlette.testclient import TestClient

import adapters.inbound.route_factories.crud_route_factory as crud_module
from adapters.inbound.events_routes import EVENTS_CONFIG
from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory
from core.events.base import BaseEvent
from core.models.enums import RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest, RecurringInstancesRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_request import EventTemplateCreateRequest
from core.models.update_contracts import RawChanges
from core.models.validation_rules import ONLINE_URL_REQUIRED
from core.services.events._orchestration_mixin import _OrchestrationMixin
from core.services.events._scheduling_mixin import _SchedulingMixin
from core.services.events.events_core_service import EventsCoreService
from core.services.templates import EventTemplateService
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

USER = "user_online_url"
EVENT = "event_online_url"
TEMPLATE = "et.online-url.weekly-call"
URL = "https://meet.example.com/abc"
BOOKED = date.today() + timedelta(days=5)

_EVENT_BODY: dict[str, object] = {
    "title": "Study group",
    "event_date": BOOKED.isoformat(),
    "start_time": "09:00:00",
    "end_time": "10:00:00",
}

# Each missing-URL spelling: the key left out, an explicit null, an empty string.
_MISSING_URL: list[dict[str, object]] = [{}, {"meeting_url": None}, {"meeting_url": ""}]


# =============================================================================
# Create requests — the whole request is judged, an omitted key included
# =============================================================================


class TestEventCreateRequest:
    @pytest.mark.parametrize("missing", _MISSING_URL, ids=["omitted", "none", "empty"])
    def test_online_without_a_url_is_refused(self, missing: dict[str, object]) -> None:
        with pytest.raises(ValidationError, match=ONLINE_URL_REQUIRED):
            EventCreateRequest.model_validate({**_EVENT_BODY, "is_online": True, **missing})

    def test_online_with_a_url_is_accepted(self) -> None:
        request = EventCreateRequest.model_validate(
            {**_EVENT_BODY, "is_online": True, "meeting_url": URL}
        )
        assert request.meeting_url == URL

    def test_offline_needs_no_url(self) -> None:
        request = EventCreateRequest.model_validate(_EVENT_BODY)
        assert request.is_online is False
        assert request.meeting_url is None


class TestEventTemplateCreateRequest:
    @pytest.mark.parametrize("missing", _MISSING_URL, ids=["omitted", "none", "empty"])
    def test_online_without_a_url_is_refused(self, missing: dict[str, object]) -> None:
        with pytest.raises(ValidationError, match=ONLINE_URL_REQUIRED):
            EventTemplateCreateRequest.model_validate(
                {"title": "Weekly call", "is_online": True, **missing}
            )

    def test_online_with_a_url_is_accepted(self) -> None:
        request = EventTemplateCreateRequest.model_validate(
            {"title": "Weekly call", "is_online": True, "meeting_url": URL}
        )
        assert request.meeting_url == URL

    def test_offline_needs_no_url(self) -> None:
        request = EventTemplateCreateRequest.model_validate({"title": "Weekly call"})
        assert request.is_online is False


# =============================================================================
# The HTTP door — an API client that leaves the key out gets a 400
# =============================================================================


def _fake_authenticated_user(request: object) -> str:
    """Stand in for the session lookup — these tests are about the body."""
    return USER


def _events_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AsyncMock]:
    """The events CRUD create route, built from the live ``EVENTS_CONFIG``."""
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(crud_module, "require_authenticated_user", _fake_authenticated_user)

    create_event = AsyncMock(return_value=Result.ok({"uid": EVENT}))
    service = MagicMock()
    service.create_event = create_event

    crud = EVENTS_CONFIG.crud
    assert crud is not None
    CRUDRouteFactory(
        service=service,
        domain_name=EVENTS_CONFIG.domain_name,
        create_schema=crud.create_schema,
        update_schema=crud.update_schema,
        uid_prefix=crud.uid_prefix,
        request_create_method=crud.request_create_method,
    ).register_routes(app, rt)
    return TestClient(app, cookies={"csrf_token": "tok"}), create_event


_JSON = {"X-CSRF-Token": "tok", "content-type": "application/json"}


def test_api_create_online_without_meeting_url_key_is_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_event = _events_client(monkeypatch)

    response = client.post(
        "/api/events/create", json={**_EVENT_BODY, "is_online": True}, headers=_JSON
    )

    assert response.status_code == 400, response.text
    payload = json.loads(response.text)
    assert payload["category"] == "validation"
    assert ONLINE_URL_REQUIRED in payload["message"]
    create_event.assert_not_awaited()


def test_api_create_online_with_meeting_url_reaches_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_event = _events_client(monkeypatch)

    response = client.post(
        "/api/events/create",
        json={**_EVENT_BODY, "is_online": True, "meeting_url": URL},
        headers=_JSON,
    )

    assert response.status_code == 201, response.text
    create_event.assert_awaited_once()


# =============================================================================
# Event update — the merged state, only when the patch names the pair
# =============================================================================


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)


def _event(*, is_online: bool, meeting_url: str | None, title: str = "Study group") -> Event:
    return Event(
        uid=EVENT,
        user_uid=USER,
        title=title,
        event_date=BOOKED,
        start_time=time(9, 0),
        end_time=time(10, 0),
        is_online=is_online,
        meeting_url=meeting_url,
    )


def _events_core(stored: Event) -> tuple[EventsCoreService, StatusGuardedWriteRecorder[Event]]:
    backend, recorder = guarded_backend(stored, stored)
    return EventsCoreService(backend=backend, event_bus=_RecordingBus()), recorder


@pytest.mark.asyncio
class TestEventUpdate:
    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _event(is_online=True, meeting_url=URL),
                EventUpdateIntent(meeting_url=None),
                id="clearing-the-url-of-an-online-event",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=URL),
                EventUpdateIntent(meeting_url=""),
                id="emptying-the-url-of-an-online-event",
            ),
            pytest.param(
                _event(is_online=False, meeting_url=None),
                EventUpdateIntent(is_online=True),
                id="turning-online-with-no-url-stored",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=None),
                EventUpdateIntent(title="Study group", is_online=True, meeting_url=None),
                id="the-edit-form-resubmitting-a-url-less-online-event",
            ),
        ],
    )
    async def test_a_patch_leaving_it_online_without_a_url_is_refused(
        self, stored: Event, patch: EventUpdateIntent
    ) -> None:
        service, recorder = _events_core(stored)

        result = await service.update_event(EVENT, patch)

        assert result.is_error
        assert result.expect_error().message == ONLINE_URL_REQUIRED
        assert recorder.calls == [], "a refused patch must not reach the write"

    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _event(is_online=False, meeting_url=None),
                EventUpdateIntent(is_online=True, meeting_url=URL),
                id="turning-online-with-a-url",
            ),
            pytest.param(
                _event(is_online=False, meeting_url=URL),
                EventUpdateIntent(is_online=True),
                id="turning-online-with-a-url-stored",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=None),
                EventUpdateIntent(is_online=False),
                id="turning-a-url-less-online-event-offline",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=None),
                EventUpdateIntent(title="Renamed"),
                id="a-title-edit-of-a-url-less-online-event",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=None),
                EventUpdateIntent(event_date=BOOKED + timedelta(days=1)),
                id="rescheduling-a-url-less-online-event",
            ),
            pytest.param(
                _event(is_online=True, meeting_url=None),
                EventUpdateIntent(status="completed"),
                id="completing-a-url-less-online-event",
            ),
        ],
    )
    async def test_a_patch_leaving_the_pair_consistent_or_untouched_is_written(
        self, stored: Event, patch: EventUpdateIntent
    ) -> None:
        service, recorder = _events_core(stored)

        result = await service.update_event(EVENT, patch)

        assert result.is_ok, result
        assert len(recorder.calls) == 1


# =============================================================================
# EventTemplate update — the same rule through the inherited CRUD update
# =============================================================================


def _template(*, is_online: bool, meeting_url: str | None) -> EventTemplate:
    return EventTemplate(
        uid=TEMPLATE, title="Weekly call", is_online=is_online, meeting_url=meeting_url
    )


def _template_service(stored: EventTemplate) -> tuple[EventTemplateService, AsyncMock]:
    backend = MagicMock()
    backend.get = AsyncMock(return_value=Result.ok(stored))
    update = AsyncMock(return_value=Result.ok(stored))
    backend.update = update
    return EventTemplateService(backend=backend, attachment=MagicMock()), update


@pytest.mark.asyncio
class TestEventTemplateUpdate:
    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _template(is_online=True, meeting_url=URL),
                {"meeting_url": None},
                id="clearing-the-url-of-an-online-template",
            ),
            pytest.param(
                _template(is_online=False, meeting_url=None),
                {"is_online": True},
                id="turning-online-with-no-url-stored",
            ),
        ],
    )
    async def test_a_patch_leaving_it_online_without_a_url_is_refused(
        self, stored: EventTemplate, patch: dict[str, object]
    ) -> None:
        service, update = _template_service(stored)

        result = await service.update(TEMPLATE, RawChanges(patch))

        assert result.is_error
        assert result.expect_error().message == ONLINE_URL_REQUIRED
        update.assert_not_awaited()

    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _template(is_online=False, meeting_url=None),
                {"is_online": True, "meeting_url": URL},
                id="turning-online-with-a-url",
            ),
            pytest.param(
                _template(is_online=True, meeting_url=None),
                {"title": "Weekly call (renamed)"},
                id="a-title-edit-of-a-url-less-online-template",
            ),
        ],
    )
    async def test_a_patch_leaving_the_pair_consistent_or_untouched_is_written(
        self, stored: EventTemplate, patch: dict[str, object]
    ) -> None:
        service, update = _template_service(stored)

        result = await service.update(TEMPLATE, RawChanges(patch))

        assert result.is_ok, result
        update.assert_awaited_once()


# =============================================================================
# Staged creators — the URL travels with the flag
# =============================================================================


class _SchedulingHost(_SchedulingMixin):
    def __init__(self, source: Event) -> None:
        self.backend = MagicMock()
        self.backend.create = AsyncMock(side_effect=_echo)
        self.get_event = AsyncMock(return_value=Result.ok(source))


class _OrchestrationHost(_OrchestrationMixin):
    def __init__(self) -> None:
        self.backend = MagicMock()
        self.backend.create = AsyncMock(side_effect=_echo)
        self.event_bus = _RecordingBus()
        self.logger = MagicMock()


async def _echo(entity: Event) -> Result[Event]:
    return Result.ok(entity)


@pytest.mark.asyncio
async def test_recurring_instances_carry_the_meeting_url() -> None:
    source = Event(
        uid=EVENT,
        user_uid=USER,
        title="Weekly call",
        event_date=BOOKED,
        is_online=True,
        meeting_url=URL,
        recurrence_pattern=RecurrencePattern.WEEKLY,
    )
    host = _SchedulingHost(source)

    result = await host.create_recurring_instances(
        RecurringInstancesRequest(event_uid=EVENT, count=2)
    )

    assert result.is_ok, result
    assert [(e.is_online, e.meeting_url) for e in result.value] == [(True, URL), (True, URL)]


@pytest.mark.asyncio
async def test_context_aware_create_carries_the_meeting_url() -> None:
    request = EventCreateRequest.model_validate(
        {**_EVENT_BODY, "is_online": True, "meeting_url": URL}
    )
    context = SimpleNamespace(user_uid=USER, active_habit_uids=set())

    result = await _OrchestrationHost().create_event_with_context(request, context)

    assert result.is_ok, result
    assert (result.value.is_online, result.value.meeting_url) == (True, URL)
