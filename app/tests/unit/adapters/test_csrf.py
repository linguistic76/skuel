"""Tests for the CSRF double-submit token middleware and decorator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from adapters.inbound.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    csrf_protected,
    is_csrf_enforced,
    mint_token,
    verify_csrf,
)
from core.utils.csrf_token_context import CSRF_FORM_FIELD, current_csrf_token
from ui.patterns.csrf import csrf_hidden_input


def _make_request(
    *,
    method: str = "POST",
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    form_data: dict[str, str] | None = None,
    content_type: str | None = None,
    path: str = "/api/test",
) -> MagicMock:
    """Build a minimal Request-shaped mock for decorator/verify tests."""
    request = MagicMock()
    request.method = method
    request.cookies = cookies or {}
    hdrs = dict(headers or {})
    if content_type and "content-type" not in {k.lower() for k in hdrs}:
        hdrs["content-type"] = content_type
    # headers.get is case-insensitive in Starlette; our test harness uses dict
    request.headers = _CaseInsensitiveDict(hdrs)
    request.url = MagicMock()
    request.url.path = path

    if form_data is not None:

        async def _form():
            return form_data

        request.form = _form
    else:

        async def _form_empty():
            return {}

        request.form = _form_empty

    return request


class _CaseInsensitiveDict(dict):
    """Minimal case-insensitive header dict for testing."""

    def get(self, key, default=None):  # type: ignore[override]
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


# ============================================================================
# Token minting
# ============================================================================


class TestTokenMinting:
    def test_mint_token_returns_urlsafe_string(self):
        token = mint_token()
        assert isinstance(token, str)
        assert len(token) >= 32

    def test_mint_token_is_random(self):
        assert mint_token() != mint_token()


# ============================================================================
# Enforcement flag
# ============================================================================


class TestEnforcementFlag:
    def test_default_is_enforced(self, monkeypatch):
        monkeypatch.delenv("SKUEL_CSRF_ENFORCE", raising=False)
        assert is_csrf_enforced() is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", " NO "])
    def test_falsy_values_disable(self, monkeypatch, value):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", value)
        assert is_csrf_enforced() is False

    @pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
    def test_truthy_values_enforce(self, monkeypatch, value):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", value)
        assert is_csrf_enforced() is True


# ============================================================================
# verify_csrf
# ============================================================================


class TestVerifyCsrf:
    @pytest.mark.asyncio
    async def test_missing_cookie_fails(self):
        request = _make_request(cookies={}, headers={CSRF_HEADER_NAME: "whatever"})
        assert await verify_csrf(request) == (False, "no_cookie")

    @pytest.mark.asyncio
    async def test_missing_submitted_token_fails(self):
        request = _make_request(cookies={CSRF_COOKIE_NAME: "t"})
        assert await verify_csrf(request) == (False, "no_submitted_token")

    @pytest.mark.asyncio
    async def test_mismatched_token_fails(self):
        request = _make_request(
            cookies={CSRF_COOKIE_NAME: "cookie-token"},
            headers={CSRF_HEADER_NAME: "different-token"},
        )
        assert await verify_csrf(request) == (False, "token_mismatch")

    @pytest.mark.asyncio
    async def test_matching_header_token_passes(self):
        token = mint_token()
        request = _make_request(
            cookies={CSRF_COOKIE_NAME: token},
            headers={CSRF_HEADER_NAME: token},
        )
        assert await verify_csrf(request) == (True, "ok")

    @pytest.mark.asyncio
    async def test_matching_form_field_passes(self):
        token = mint_token()
        request = _make_request(
            cookies={CSRF_COOKIE_NAME: token},
            content_type="application/x-www-form-urlencoded",
            form_data={CSRF_FORM_FIELD: token},
        )
        assert await verify_csrf(request) == (True, "ok")

    @pytest.mark.asyncio
    async def test_multipart_form_field_passes(self):
        token = mint_token()
        request = _make_request(
            cookies={CSRF_COOKIE_NAME: token},
            content_type="multipart/form-data; boundary=---x",
            form_data={CSRF_FORM_FIELD: token},
        )
        assert await verify_csrf(request) == (True, "ok")

    @pytest.mark.asyncio
    async def test_header_preferred_over_form(self):
        cookie = mint_token()
        request = _make_request(
            cookies={CSRF_COOKIE_NAME: cookie},
            headers={CSRF_HEADER_NAME: cookie},
            content_type="application/x-www-form-urlencoded",
            form_data={CSRF_FORM_FIELD: "wrong"},
        )
        assert await verify_csrf(request) == (True, "ok")


# ============================================================================
# @csrf_protected decorator
# ============================================================================


class TestCsrfProtectedDecorator:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    async def test_safe_methods_pass_through(self, method):
        @csrf_protected
        async def handler(request):
            return "ok"

        request = _make_request(method=method)
        assert await handler(request) == "ok"

    @pytest.mark.asyncio
    async def test_enforcement_off_passes(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "local")

        @csrf_protected
        async def handler(request):
            return "ok"

        # POST with no token at all — should still pass because enforcement off
        request = _make_request(method="POST")
        assert await handler(request) == "ok"

    @pytest.mark.asyncio
    async def test_missing_token_returns_403(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")

        @csrf_protected
        async def handler(request):
            return "ok"

        request = _make_request(method="POST")
        response = await handler(request)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_token_runs_handler(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
        token = mint_token()

        @csrf_protected
        async def handler(request):
            return "ran"

        request = _make_request(
            method="POST",
            cookies={CSRF_COOKIE_NAME: token},
            headers={CSRF_HEADER_NAME: token},
        )
        assert await handler(request) == "ran"

    @pytest.mark.asyncio
    async def test_decorator_preserves_kwargs(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
        token = mint_token()

        @csrf_protected
        async def handler(request, *, uid: str):
            return f"ran-{uid}"

        request = _make_request(
            method="POST",
            cookies={CSRF_COOKIE_NAME: token},
            headers={CSRF_HEADER_NAME: token},
        )
        assert await handler(request, uid="abc") == "ran-abc"


# ============================================================================
# Production enforcement override
# ============================================================================


class TestProductionEnforcement:
    @pytest.mark.asyncio
    async def test_production_ignores_enforce_flag(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "production")

        @csrf_protected
        async def handler(request):
            return "ok"

        request = _make_request(method="POST")
        response = await handler(request)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_production_respects_flag(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "staging")

        @csrf_protected
        async def handler(request):
            return "ok"

        request = _make_request(method="POST")
        assert await handler(request) == "ok"

    @pytest.mark.asyncio
    async def test_production_with_valid_token_passes(self, monkeypatch):
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "production")
        token = mint_token()

        @csrf_protected
        async def handler(request):
            return "ran"

        request = _make_request(
            method="POST",
            cookies={CSRF_COOKIE_NAME: token},
            headers={CSRF_HEADER_NAME: token},
        )
        assert await handler(request) == "ran"


# ============================================================================
# csrf_hidden_input helper
# ============================================================================


class TestCsrfHiddenInput:
    def test_renders_empty_when_no_contextvar(self):
        # No middleware in play — contextvar defaults to None.
        component = csrf_hidden_input()
        rendered = str(component)
        assert 'name="csrf_token"' in rendered
        assert 'type="hidden"' in rendered
        assert 'value=""' in rendered

    def test_uses_contextvar_token(self):
        from core.utils.csrf_token_context import csrf_token_var

        token = mint_token()
        reset = csrf_token_var.set(token)
        try:
            assert current_csrf_token() == token
            rendered = str(csrf_hidden_input())
            assert f'value="{token}"' in rendered
        finally:
            csrf_token_var.reset(reset)
