"""GET /api/lifepath/alignment/chart — the alignment radar's Chart.js config.

The route answers a ``ChartJsConfig`` through the boundary like the other chart
routes. On success the body is pinned byte for byte, colours included. The radar
draws no tick numbers: Chart.js puts them on the first axis, under its point, and
the rows below the radar print every score. Its axis labels are the rows' names.
A failed alignment read is an error
response, which the card shows as its error: an all-zero radar would present a
failure as the learner's alignment.
"""

import re
from unittest.mock import MagicMock

import pytest
from fasthtml.common import Div, fast_app, to_xml
from starlette.testclient import TestClient

import adapters.inbound.lifepath_ui as lifepath_ui
from core.models.type_hints import UserUID
from core.ports.query_types import AlignmentDimensions, LifePathAlignmentResult
from core.utils.result_simplified import Errors, Result
from ui.lifepath.alignment import render_alignment_dashboard

URL = "/api/lifepath/alignment/chart"

DIMENSIONS: AlignmentDimensions = {
    "knowledge": 0.5,
    "activity": 0.25,
    "goal": 1.0,
    "principle": 0.0,
    "momentum": 0.75,
}

RADAR_BODY = (
    '{"type":"radar","data":{"labels":["Knowledge","Activity","Goal","Principle","Momentum"],'
    '"datasets":[{"label":"Your Alignment","data":[0.5,0.25,1.0,0.0,0.75],'
    '"backgroundColor":"rgba(59, 130, 246, 0.2)","borderColor":"rgba(59, 130, 246, 1)",'
    '"borderWidth":2,"pointBackgroundColor":"rgba(59, 130, 246, 1)","pointBorderColor":"#fff"}]},'
    '"options":{"scales":{"r":{"min":0,"max":1,"ticks":{"stepSize":0.2,"display":false}}},'
    '"plugins":{"legend":{"display":false}}}}'
)


class _LifePath:
    def __init__(self, alignment: Result[LifePathAlignmentResult]) -> None:
        self.alignment = alignment
        self.asked: list[UserUID] = []

    async def get_alignment(self, user_uid: UserUID) -> Result[LifePathAlignmentResult]:
        self.asked.append(user_uid)
        return self.alignment


def _client(monkeypatch: pytest.MonkeyPatch, service: _LifePath) -> TestClient:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    monkeypatch.setattr(lifepath_ui, "require_authenticated_user", signed_in)
    app, rt = fast_app(pico=False, default_hdrs=False)
    lifepath_ui.create_lifepath_ui_routes(app, rt, service, MagicMock())
    return TestClient(app)


def test_the_radar_config_is_pinned_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _LifePath(Result.ok({"dimensions": DIMENSIONS}))
    response = _client(monkeypatch, service).get(URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.text == RADAR_BODY
    assert service.asked == ["user_learner"]


def test_no_designation_draws_an_empty_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _LifePath(Result.ok({"message": "No life path designated"}))
    body = _client(monkeypatch, service).get(URL).json()

    assert body["data"]["datasets"][0]["data"] == [0.0] * 5


def test_a_failed_alignment_read_is_an_error_not_a_zero_radar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _LifePath(Result.fail(Errors.database("get_alignment", "graph unavailable")))
    response = _client(monkeypatch, service).get(URL)

    assert response.status_code == 503
    assert "datasets" not in response.text


def test_the_radar_names_each_axis_as_the_rows_below_it_do() -> None:
    page = to_xml(render_alignment_dashboard({"alignment": {"dimensions": DIMENSIONS}}, Div()))
    rows = re.findall(r'<span class="text-sm font-medium">([^<]*)</span>', page)

    assert lifepath_ui._alignment_radar_config(DIMENSIONS)["data"]["labels"] == rows
