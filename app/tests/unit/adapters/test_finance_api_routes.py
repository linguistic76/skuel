"""Finance API security/wiring pins (adapters/inbound/finance_api.py).

Testing-gap roadmap item 6 (tranche 2, system/infra cluster): PIN tests over
the surviving invoice surface (ADR-052 Phase 5) — the ADMIN_ONLY domain gate
on every route (401/403; Finance has no ownership checks by design), CSRF on
create, require_found 404 on missing invoices, the PDF error contract
(text/plain 500, never a broken PDF), and exact service kwargs on the list
happy path. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.finance_api import create_finance_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_admin"
_INVOICE_UID = "invoice_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


def _invoice() -> MagicMock:
    invoice = MagicMock()
    invoice.uid = _INVOICE_UID
    invoice.to_dto.return_value.to_dict.return_value = {"uid": _INVOICE_UID, "total": 100.0}
    return invoice


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    finance: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    finance = MagicMock()
    finance.list_invoices = AsyncMock(return_value=Result.ok([_invoice()]))
    finance.create_invoice = AsyncMock(return_value=Result.ok(_invoice()))
    finance.get_invoice_stats = AsyncMock(return_value=Result.ok({"total_invoices": 1}))
    finance.get_invoice = AsyncMock(return_value=Result.ok(_invoice()))
    finance.generate_invoice_pdf = AsyncMock(return_value=Result.ok(b"%PDF-1.7 fake"))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_finance_api_routes(app, rt, finance, user_service=user_service)
    return _Harness(client=TestClient(app), finance=finance)


class TestAdminOnlyDomain:
    def test_list_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/invoices")

        assert response.status_code == 401
        harness.finance.list_invoices.assert_not_awaited()

    def test_list_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get("/api/invoices")

        assert response.status_code == 403
        harness.finance.list_invoices.assert_not_awaited()

    def test_pdf_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get(f"/api/invoices/pdf?uid={_INVOICE_UID}")

        assert response.status_code == 403
        harness.finance.generate_invoice_pdf.assert_not_awaited()


class TestCsrfEnforcement:
    def test_create_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/invoices", json={})

        assert response.status_code == 403
        harness.finance.create_invoice.assert_not_awaited()


class TestInvoiceReads:
    def test_list_forwards_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/invoices?type=outgoing&status=paid&limit=10")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        harness.finance.list_invoices.assert_awaited_once_with(
            limit=10, invoice_type="outgoing", status="paid"
        )

    def test_get_missing_invoice_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.finance.get_invoice.return_value = Result.ok(None)

        response = harness.client.get(f"/api/invoices/get?uid={_INVOICE_UID}")

        assert response.status_code == 404

    def test_stats_happy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/invoices/stats")

        assert response.status_code == 200
        harness.finance.get_invoice_stats.assert_awaited_once()


class TestPdfDownload:
    def test_pdf_happy_sets_attachment_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/invoices/pdf?uid={_INVOICE_UID}")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert _INVOICE_UID in response.headers["content-disposition"]

    def test_pdf_failure_is_plain_text_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.finance.generate_invoice_pdf.return_value = Result.fail(
            Errors.system("PDF engine unavailable", operation="generate_invoice_pdf")
        )

        response = harness.client.get(f"/api/invoices/pdf?uid={_INVOICE_UID}")

        assert response.status_code == 500
        assert response.headers["content-type"].startswith("text/plain")
