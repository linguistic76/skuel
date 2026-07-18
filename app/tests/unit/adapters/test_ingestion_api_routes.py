"""Ingestion API security/wiring pins (adapters/inbound/ingestion_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the admin ingestion doors — ADMIN role gate (401/403), CSRF, and the path
allowlist contract: fail-closed when neither ``SKUEL_INGESTION_ALLOWED_PATHS``
nor ``INGESTION_PATH`` is configured, traversal outside the allowlist
rejected, symlinked files rejected on the ORIGINAL path (the resolve()-based
validator erases symlink-ness), and the acting-user hint forwarded on the
happy path (ADR-070). Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.ingestion_api import create_ingestion_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_admin"


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


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    ingestion: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    ingestion = MagicMock()
    ingestion.ingest_file = AsyncMock(
        return_value=Result.ok({"uid": "ku_new_1", "title": "New Ku"})
    )
    ingestion.ingest_vault = AsyncMock(return_value=Result.ok(MagicMock()))
    ingestion.ingest_bundle = AsyncMock(return_value=Result.ok(MagicMock()))
    ingestion.ingest_directory = AsyncMock(return_value=Result.ok(MagicMock()))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_ingestion_api_routes(app, rt, ingestion, user_service=user_service)
    return _Harness(client=TestClient(app), ingestion=ingestion)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAdminGate:
    def test_ingest_file_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/ingest/file", {"file_path": "/x.md"})

        assert response.status_code == 401
        harness.ingestion.ingest_file.assert_not_awaited()

    def test_ingest_file_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(harness.client, "/api/ingest/file", {"file_path": "/x.md"})

        assert response.status_code == 403
        harness.ingestion.ingest_file.assert_not_awaited()


class TestCsrfEnforcement:
    def test_ingest_file_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/ingest/file", json={"file_path": "/x.md"})

        assert response.status_code == 403
        harness.ingestion.ingest_file.assert_not_awaited()


class TestPathAllowlist:
    def test_no_allowlist_configured_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Default-deny: neither env var set → every path rejected, even real files.
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.delenv("INGESTION_PATH", raising=False)
        harness = _make_harness(monkeypatch)
        target = tmp_path / "note.md"
        target.write_text("# hi")

        response = _post_json(harness.client, "/api/ingest/file", {"file_path": str(target)})

        assert response.status_code == 400
        harness.ingestion.ingest_file.assert_not_awaited()

    def test_path_outside_allowlist_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.setenv("INGESTION_PATH", str(vault))
        harness = _make_harness(monkeypatch)
        outside = tmp_path / "outside.md"
        outside.write_text("# nope")

        response = _post_json(
            harness.client,
            "/api/ingest/file",
            {"file_path": str(vault / ".." / "outside.md")},
        )

        assert response.status_code == 400
        harness.ingestion.ingest_file.assert_not_awaited()

    def test_symlinked_file_rejected_on_original_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The validator resolves symlinks for traversal protection, which would
        # erase symlink-ness — the single-file door must reject BEFORE resolving.
        vault = tmp_path / "vault"
        vault.mkdir()
        secret = tmp_path / "secret.md"
        secret.write_text("# secret")
        link = vault / "link.md"
        link.symlink_to(secret)
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.setenv("INGESTION_PATH", str(vault))
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/ingest/file", {"file_path": str(link)})

        assert response.status_code == 400
        harness.ingestion.ingest_file.assert_not_awaited()


class TestIngestFile:
    def test_happy_path_forwards_acting_user_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "note.md"
        target.write_text("# hi")
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.setenv("INGESTION_PATH", str(vault))
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/ingest/file", {"file_path": str(target)})

        assert response.status_code == 200
        assert response.json()["success"] is True
        harness.ingestion.ingest_file.assert_awaited_once_with(target.resolve(), user_uid=_USER_UID)

    def test_missing_file_is_404(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.setenv("INGESTION_PATH", str(vault))
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client, "/api/ingest/file", {"file_path": str(vault / "ghost.md")}
        )

        assert response.status_code == 404
        harness.ingestion.ingest_file.assert_not_awaited()


class TestIngestVault:
    def test_nonexistent_vault_dir_is_404(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
        monkeypatch.setenv("INGESTION_PATH", str(vault))
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client, "/api/ingest/vault", {"vault_path": str(vault / "missing")}
        )

        assert response.status_code == 404
        harness.ingestion.ingest_vault.assert_not_awaited()
