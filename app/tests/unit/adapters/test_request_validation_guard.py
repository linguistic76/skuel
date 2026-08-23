"""Body-validation chokepoint guard (adapters/inbound/boundary.py).

Sibling of ``test_malformed_json_guard.py``, for the next failure along the
same seam. A route that annotates its body as a Pydantic model
(``body: SomeRequest``) has that model constructed by FastHTML during parameter
extraction, BEFORE the handler and its ``@boundary_handler`` wrapper run — so a
field constraint rejecting the input escaped as a raw ``ValidationError`` and
surfaced as a 500, i.e. the app reporting "server bug" for ordinary bad input.

``install_request_validation_guard`` (wired once in bootstrap's
``_create_web_app``) maps it to the same ``Errors.validation`` 400 shape
``parse_json_body`` already returns for the identical input.
"""

from __future__ import annotations

from fasthtml.common import fast_app
from pydantic import Field
from starlette.testclient import TestClient

from adapters.inbound.boundary import install_request_validation_guard
from core.models.request_base import RequestBase


class _Body(RequestBase):
    minutes: int | None = Field(default=None, ge=0)


def _make_app(*, guard: bool = True):
    app, rt = fast_app(pico=False, default_hdrs=False)
    if guard:
        install_request_validation_guard(app)

    @rt("/echo", methods=["POST"])
    def echo(body: _Body) -> dict[str, int | None]:
        return {"minutes": body.minutes}

    return app


class TestRequestValidationGuard:
    def test_constraint_violation_is_400_validation(self) -> None:
        client = TestClient(_make_app())

        response = client.post("/echo", json={"minutes": -1})

        assert response.status_code == 400
        body = response.json()
        assert body["category"] == "validation"

    def test_valid_body_still_reaches_handler(self) -> None:
        client = TestClient(_make_app())

        response = client.post("/echo", json={"minutes": 30})

        assert response.status_code == 200
        assert response.json()["minutes"] == 30

    def test_validation_error_on_non_json_request_stays_500(self) -> None:
        """A model built inside a handler on a non-JSON request is a server bug.

        The guard re-raises so it keeps its 500 rather than being mislabelled
        as client input — mirroring the malformed-JSON guard's discriminator.
        """
        app, rt = fast_app(pico=False, default_hdrs=False)
        install_request_validation_guard(app)

        @rt("/boom", methods=["POST"])
        def boom() -> dict[str, str]:
            _Body(minutes=-1)
            return {"unreachable": "yes"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/boom", content=b"x", headers={"content-type": "text/plain"})

        assert response.status_code == 500

    def test_without_guard_constraint_violation_is_500(self) -> None:
        """Pins WHY the chokepoint exists — this was the behaviour on every
        auto-bound body model in the app."""
        client = TestClient(_make_app(guard=False), raise_server_exceptions=False)

        response = client.post("/echo", json={"minutes": -1})

        assert response.status_code == 500
