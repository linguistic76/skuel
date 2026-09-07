"""Pin API_VALIDATION_PATTERNS.md's HTTP-status claims to the live boundary.

Why this exists
---------------
A status column is a contract a client integrator branches on, so a wrong cell
sends someone to handle a status the app never emits. The guide's claims rest
on one fact: ``_get_status_for_error`` maps ``ErrorCategory.VALIDATION`` to 400,
and 422 belongs to ``BUSINESS`` — a well-formed request that breaks a domain
rule, which this guide does not cover.

So the columns are derived-checked, and by *driving the helper* rather than
reading its source: each documented row runs its real parser over input it must
reject and asserts the response ``result_to_response`` builds carries the
status the table claims. A row with no driver declares its documented status in
``_UNDRIVEN`` instead, which is checked the same way; a row that does neither
breaks the build.

``app/docs/patterns/API_VALIDATION_PATTERNS.md`` is in CI's ``py`` path filter
so a docs-only edit to a status cell still runs this module.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from adapters.inbound.boundary import _get_status_for_error, result_to_response
from adapters.inbound.form_helpers import parse_form_body, parse_json_body
from adapters.inbound.route_factories import (
    parse_bool_query_param,
    parse_date_param_strict,
)
from adapters.inbound.search_routes import create_search_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from adapters.inbound.today_routes import create_today_routes
from core.models.enums.entity_enums import EntityType
from core.models.search_request import SearchRequest
from core.models.task.task_request import ContextualTaskCompletionRequest
from core.utils.result_simplified import Errors, Result

_DOC = Path(__file__).resolve().parents[3] / "docs" / "patterns" / "API_VALIDATION_PATTERNS.md"
_TABLE_HEADING = "## When to Use Each Pattern"


def _fake_authenticated_user(request: object) -> str:
    """Stand in for the session lookup — this row is about validation, not auth."""
    return "user_mike"


# Rows the table documents but this module does not drive, each with the reason.
# A NEW row is neither driven nor listed, so it fails until someone decides which.
_UNDRIVEN: dict[str, str] = {}


class _Body(BaseModel):
    """Minimal schema whose only field rejects the input every driver sends."""

    reflection: str = Field(max_length=5)


class _JsonRequest:
    """Stands in for the JSON half of a Starlette request."""

    async def json(self) -> dict[str, str]:
        return {"reflection": "x" * 10}


class _StubRequest:
    """Serves a caller-supplied JSON body — for driving the guide's own example."""

    def __init__(self, body: dict[str, str]) -> None:
        self._body = body

    async def json(self) -> dict[str, str]:
        return self._body


class _FormRequest:
    """Stands in for the form half of a Starlette request."""

    async def form(self) -> dict[str, str]:
        return {"reflection": "x" * 10}


def _documented_rows() -> dict[str, str]:
    """Parse the guide's table into {input type: documented HTTP status}."""
    text = _DOC.read_text(encoding="utf-8")
    body = text[text.index(_TABLE_HEADING) :]
    rows: dict[str, str] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break  # the table ended
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in {"Input Type", ""} or set(cells[1]) <= {"-"}:
            continue
        rows[cells[0].strip("*").strip()] = cells[2]
    return rows


def _status_of[T](result: Result[T]) -> int:
    """The HTTP status a failed Result actually reaches the client with."""
    assert result.is_error, "driver input was accepted — it must be rejected to have a status"
    return result_to_response(result).status_code


def test_status_map_reserves_422_for_business() -> None:
    """The premise the whole guide rests on: validation is 400, 422 is BUSINESS."""
    assert _get_status_for_error(Errors.validation("bad input")) == 400
    assert _get_status_for_error(Errors.business("rule", "rule violated")) == 422


def test_every_table_row_is_driven_or_declared_undriven() -> None:
    """A new row must arrive with a driver or an explicit reason it has none."""
    documented = _documented_rows()
    assert documented, "the When to Use Each Pattern table went missing or changed shape"

    driven = {
        "Query Params (GET)",
        "Required Params (GET)",
        "JSON Bodies (POST/PUT)",
        "Form Data Bodies (POST)",
        "HTML Form Params (GET)",
        "Path Params",
    }
    assert set(documented) == driven | set(_UNDRIVEN)

    # An undriven row still has a documented status, and nothing else pins it —
    # the 422 scan passes on a 401 just as happily. Its declared value is the pin.
    assert {row: documented[row] for row in _UNDRIVEN} == _UNDRIVEN


@pytest.mark.asyncio
async def test_json_body_row_returns_the_documented_status() -> None:
    """The JSON door rejects into the status the table claims — not 422.

    Every ``parse_json_body`` consumer returns the failed ``Result`` onward, so
    one number describes the row.
    """
    status = _status_of(await parse_json_body(_JsonRequest(), _Body))  # type: ignore[arg-type]

    assert str(status) == _documented_rows()["JSON Bodies (POST/PUT)"]


@pytest.mark.asyncio
async def test_form_body_row_names_both_answers_its_consumers_give(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The form door picks no status, so the row documents both of its consumers.

    An API route hands the failed ``Result`` to ``result_to_response`` and gets
    a 400. The Activity UI create/edit routes re-render the form with a banner,
    which is a 200 — measured here by posting an invalid form at the real
    ``/tasks/create`` rather than inferred from the handler's source.
    """
    api_status = _status_of(await parse_form_body(_FormRequest(), _Body))  # type: ignore[arg-type]

    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(
        "adapters.inbound.tasks_ui.require_authenticated_user", _fake_authenticated_user
    )
    create_tasks_ui_routes(app, rt, MagicMock(), MagicMock())
    ui_response = TestClient(app).post(
        "/tasks/create",
        data={"title": ""},
        cookies={"csrf_token": "tok"},
        headers={"X-CSRF-Token": "tok"},
    )

    cell = _documented_rows()["Form Data Bodies (POST)"]
    assert f"{api_status} API" in cell
    assert f"{ui_response.status_code} banner" in cell
    assert "error" in ui_response.text.lower(), "the UI route rendered no banner — wrong branch"


def test_strict_query_helper_returns_the_documented_status() -> None:
    """The strict helpers' row — a rejected required param."""
    status = _status_of(parse_date_param_strict("not-a-date", "start_date"))

    assert str(status) == _documented_rows()["Required Params (GET)"]


def test_silent_query_helper_never_errors() -> None:
    """The silent helpers' row claims 200: unparseable input yields a value, not an error.

    Not the *default* — an unrecognised string is falsy, and only a missing or
    blank param falls back. Either way nothing reaches ``result_to_response``,
    which is what the row's "200" is claiming.
    """
    assert parse_bool_query_param({"flag": "garbage"}, "flag", default=True) is False
    assert parse_bool_query_param({}, "flag", default=True) is True
    assert _documented_rows()["Query Params (GET)"] == "200 (default)"


def _units(text: str) -> list[str]:
    """Prose paragraphs, with each table row its own unit.

    Line granularity is wrong here: a sentence that names 422 and the category
    that owns it wraps across two lines, so a line scan reports its own
    correction as an offence. A table row is scanned alone because the rows
    around it make no claim about it.
    """
    units: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("|"):
            if buffer:
                units.append(" ".join(buffer))
                buffer = []
            units.append(line)
        elif line.strip():
            buffer.append(line.strip())
        elif buffer:
            units.append(" ".join(buffer))
            buffer = []
    if buffer:
        units.append(" ".join(buffer))
    return units


def test_guide_claims_no_422_for_a_validation_failure() -> None:
    """The regression this module exists for: no 422 attached to a rejected input.

    The guide covers validation only, so its every legitimate mention of 422
    is the sentence naming the category that owns it instead.
    """
    offenders = [
        u for u in _units(_DOC.read_text(encoding="utf-8")) if "422" in u and "BUSINESS" not in u
    ]

    assert offenders == [], f"422 claimed outside a BUSINESS context: {offenders}"


def test_html_form_params_row_answers_with_a_banner_not_a_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The table's one UI-route row, measured through the route itself.

    An unrecognised facet is dropped silently, and a value the model does reject
    raises a ``ValidationError`` — a ``ValueError`` subclass, which is what lets
    ``/search/results`` catch it and answer with a banner. Nothing on that path
    picks a status code, so a reader looking for a 4xx to branch on finds none.
    The status is taken from a real response rather than inferred from the
    pieces: a wrapper that started choosing one would have to show up here.
    """
    kept = SearchRequest.from_form_params(
        query="x", user_uid="user_mike", entity_type=EntityType.TASK.value
    )
    dropped = SearchRequest.from_form_params(
        query="x", user_uid="user_mike", entity_type="nonsense_facet"
    )
    assert kept.entity_types == [EntityType.TASK.value], (
        "the facet parses at all — the next check means something"
    )
    assert dropped.entity_types == []

    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(
        "adapters.inbound.search_routes.require_authenticated_user", _fake_authenticated_user
    )
    # limit=0 fails in from_form_params, before the route reaches the router.
    create_search_api_routes(app, rt, MagicMock())
    response = TestClient(app).get("/search/results", params={"query": "x", "limit": 0})

    assert str(response.status_code) + " (banner)" == _documented_rows()["HTML Form Params (GET)"]
    assert "Invalid filter selection" in response.text


def test_path_params_row_reports_the_disagreement_it_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row says "varies" — so both behaviours it cites are measured.

    Path params are used across the app, so the row is a preference, not an
    absence, and its routes genuinely disagree. ``/today/{date_str}`` coerces an
    unparseable date to today and carries on; the drawer beside it answers 404
    for a uid the caller does not own. Neither belongs in one cell, which is
    what "varies" claims.
    """
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(
        "adapters.inbound.today_routes.require_authenticated_user", _fake_authenticated_user
    )
    services = MagicMock()
    build_context = AsyncMock(return_value=Result.fail(Errors.validation("stub context")))
    services.today_orchestrator.build_context = build_context
    services.tasks.core.verify_ownership = AsyncMock(
        return_value=Result.fail(Errors.not_found("Task", "task_someone_else"))
    )
    create_today_routes(app, rt, services)
    client = TestClient(app)

    # Coercion, not rejection: the garbage date reaches the orchestrator as today.
    client.get("/today/not-a-date")
    assert build_context.await_args is not None, "the route never reached the orchestrator"
    assert date.today() in build_context.await_args.args, (
        "an unparseable date no longer degrades to today"
    )

    # The route beside it rejects instead, with a different status again.
    assert client.get("/today/tasks/task_someone_else/drawer").status_code == 404

    assert _documented_rows()["Path Params"] == "varies"


@pytest.mark.asyncio
async def test_the_documented_response_example_is_what_that_model_emits() -> None:
    """The guide's 400 example is regenerated from the model it names.

    A hand-edited example is a claim about a live response, and this one named a
    model it had never been run against — Pydantic's real message for that body
    says ``model_type``, not ``dict_type``. So the block is derived: the same
    input goes through the same helper, and every field but the timestamp must
    match what the guide prints.
    """
    body = {"context": "string", "reflection": "x" * 2001}
    result = await parse_json_body(_StubRequest(body), ContextualTaskCompletionRequest)  # type: ignore[arg-type]
    response = result_to_response(result)
    measured = json.loads(response.body)

    text = _DOC.read_text(encoding="utf-8")
    start = text.index("**HTTP Response (400):**")
    documented = json.loads(text[text.index("```json", start) + 7 : text.index("```", start + 30)])

    assert response.status_code == 400
    assert {k: v for k, v in measured.items() if k != "timestamp"} == {
        k: v for k, v in documented.items() if k != "timestamp"
    }
