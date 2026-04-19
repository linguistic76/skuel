"""Tests for the per-user upload rate limiter."""

from unittest.mock import MagicMock

import pytest

from adapters.inbound.rate_limit import rate_limited, reset_buckets_for_testing


def _make_request(user_uid: str | None) -> MagicMock:
    """Build a request with a ``session.user_uid`` shape matching SKUEL auth."""
    request = MagicMock()
    request.url = "/test"
    session = {"user_uid": user_uid} if user_uid else {}
    request.session = session
    return request


@pytest.fixture(autouse=True)
def _reset_buckets():
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


class TestRateLimitDecorator:
    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        calls = 0

        @rate_limited(per_user=3, window_s=60)
        async def handler(request):
            nonlocal calls
            calls += 1
            return "ok"

        request = _make_request("user_1")
        for _ in range(3):
            result = await handler(request)
            assert result == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_rejects_after_limit_with_429(self):
        @rate_limited(per_user=2, window_s=60)
        async def handler(request):
            return "ok"

        request = _make_request("user_1")
        assert await handler(request) == "ok"
        assert await handler(request) == "ok"
        response = await handler(request)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_isolation_between_users(self):
        @rate_limited(per_user=1, window_s=60)
        async def handler(request):
            return "ok"

        a = _make_request("user_a")
        b = _make_request("user_b")
        assert await handler(a) == "ok"
        # user_a is out, but user_b still has a fresh bucket.
        assert await handler(b) == "ok"
        over_a = await handler(a)
        assert over_a.status_code == 429

    @pytest.mark.asyncio
    async def test_unauthenticated_passes_through(self):
        """No session/user_uid → decorator cannot key a bucket, so it lets
        the handler run and the usual auth guard inside the handler fires."""

        @rate_limited(per_user=1, window_s=60)
        async def handler(request):
            return "ok"

        request = _make_request(user_uid=None)
        # Even repeated calls should pass (no bucket created).
        for _ in range(5):
            assert await handler(request) == "ok"
