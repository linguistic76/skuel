"""
Unit tests for FireflyClient
=============================

Uses `httpx.MockTransport` to intercept requests — no real Firefly III
instance required. Verifies:

- PAT selection per book
- JSON:API response flattening
- Error mapping (transport errors, 4xx/5xx)
- Idempotent lookup via external_id
- Insight endpoint parsing
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from adapters.outbound.firefly_client import FireflyClient


def _make_client(handler: httpx.MockTransport) -> FireflyClient:
    http = httpx.AsyncClient(transport=handler, base_url="http://firefly.test")
    return FireflyClient(
        base_url="http://firefly.test",
        pat_personal="pat-personal-123",
        pat_skuel="pat-skuel-456",
        http_client=http,
    )


def _tx_group(
    tx_id: str = "1",
    amount: str = "42.00",
    description: str = "Coffee",
    tx_type: str = "withdrawal",
    category: str | None = "Food",
) -> dict[str, Any]:
    return {
        "type": "transactions",
        "id": tx_id,
        "attributes": {
            "transactions": [
                {
                    "transaction_journal_id": f"j{tx_id}",
                    "type": tx_type,
                    "date": "2026-04-01T00:00:00+00:00",
                    "amount": amount,
                    "currency_code": "USD",
                    "description": description,
                    "category_name": category,
                    "budget_name": None,
                    "source_name": "Checking",
                    "destination_name": "Groceries",
                    "tags": ["food"],
                    "notes": None,
                }
            ]
        },
    }


# ----------------------------------------------------------------------
# Constructor
# ----------------------------------------------------------------------


def test_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        FireflyClient(base_url="", pat_personal="x", pat_skuel="y")


def test_rejects_no_tokens() -> None:
    with pytest.raises(ValueError, match="Personal Access Token"):
        FireflyClient(base_url="http://x", pat_personal="", pat_skuel="")


# ----------------------------------------------------------------------
# PAT selection
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_transactions_uses_correct_pat_for_skuel_book() -> None:
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"data": []})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_transactions("skuel", limit=10)
    assert result.is_error is False
    assert seen_auth == ["Bearer pat-skuel-456"]
    await client.aclose()


@pytest.mark.asyncio
async def test_list_transactions_uses_correct_pat_for_personal_book() -> None:
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"data": []})

    client = _make_client(httpx.MockTransport(handler))
    await client.list_transactions("personal", limit=10)
    assert seen_auth == ["Bearer pat-personal-123"]
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_pat_for_book_returns_validation_error() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})))
    client = FireflyClient(
        base_url="http://firefly.test",
        pat_personal="only-personal",
        pat_skuel="",  # SKUEL book has no token
        http_client=http,
    )
    result = await client.list_transactions("skuel")
    assert result.is_error
    assert "FIREFLY_PAT_SKUEL" in (result.error.message if result.error else "")
    await client.aclose()


# ----------------------------------------------------------------------
# Transaction shape flattening
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_transactions_flattens_json_api_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/transactions"
        assert request.url.params["limit"] == "50"
        return httpx.Response(200, json={"data": [_tx_group("7", "12.34")]})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_transactions("skuel", limit=50)
    assert result.is_error is False
    rows = result.value
    assert len(rows) == 1
    assert rows[0]["transaction_id"] == "7"
    assert rows[0]["amount"] == "12.34"
    assert rows[0]["type"] == "withdrawal"
    assert rows[0]["category_name"] == "Food"
    assert rows[0]["tags"] == ["food"]
    await client.aclose()


@pytest.mark.asyncio
async def test_list_transactions_passes_date_range_and_type() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"data": []})

    client = _make_client(httpx.MockTransport(handler))
    await client.list_transactions(
        "skuel", start="2026-01-01", end="2026-01-31", transaction_type="deposit"
    )
    assert seen_params["start"] == "2026-01-01"
    assert seen_params["end"] == "2026-01-31"
    assert seen_params["type"] == "deposit"
    await client.aclose()


# ----------------------------------------------------------------------
# Create transaction
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_transaction_wraps_payload_and_lifts_external_id() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": _tx_group("99")})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.create_transaction(
        "skuel",
        {
            "type": "deposit",
            "date": "2026-04-01",
            "amount": "100.00",
            "description": "Stripe charge",
            "source_name": "Stripe",
            "destination_name": "SKUEL Revenue",
            "external_id": "evt_123",
        },
    )
    assert result.is_error is False
    assert captured["method"] == "POST"
    # external_id is lifted to the group level
    assert captured["body"]["external_id"] == "evt_123"
    # The split is wrapped in transactions[]
    assert captured["body"]["transactions"][0]["type"] == "deposit"
    assert captured["body"]["transactions"][0]["amount"] == "100.00"
    assert "external_id" not in captured["body"]["transactions"][0]
    await client.aclose()


# ----------------------------------------------------------------------
# Idempotent lookup
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_by_external_id_returns_none_when_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "external_id_is:evt_missing" in request.url.params["query"]
        return httpx.Response(200, json={"data": []})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.find_transaction_by_external_id("skuel", "evt_missing")
    assert result.is_error is False
    assert result.value is None
    await client.aclose()


@pytest.mark.asyncio
async def test_find_by_external_id_returns_existing_transaction() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_tx_group("42")]})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.find_transaction_by_external_id("skuel", "evt_abc")
    assert result.is_error is False
    assert result.value is not None
    assert result.value["transaction_id"] == "42"
    await client.aclose()


# ----------------------------------------------------------------------
# Error mapping
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_error_maps_to_integration_error() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthenticated."})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_transactions("skuel")
    assert result.is_error
    err = result.error
    assert err is not None
    assert err.details.get("service") == "firefly"
    assert err.details.get("status_code") == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_maps_to_integration_error() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_transactions("skuel")
    assert result.is_error
    err = result.error
    assert err is not None
    assert "transport" in err.message.lower() or "connection" in err.message.lower()
    await client.aclose()


# ----------------------------------------------------------------------
# Budgets, categories, accounts, insights
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_budgets_parses_spent_and_limit() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "3",
                        "attributes": {
                            "name": "Groceries",
                            "active": True,
                            "currency_code": "USD",
                            "spent": [{"sum": "123.45"}],
                            "auto_budget_amount": "500",
                            "auto_budget_period_start": "2026-04-01",
                            "auto_budget_period_end": "2026-04-30",
                        },
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_budgets("skuel")
    assert result.is_error is False
    row = result.value[0]
    assert row["name"] == "Groceries"
    assert row["spent"] == "123.45"
    assert row["limit"] == "500"
    assert row["period_start"] == "2026-04-01"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_categories_parses_spent_earned() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "5",
                        "attributes": {
                            "name": "Food",
                            "spent": [{"sum": "80.00"}],
                            "earned": [{"sum": "0"}],
                        },
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_categories("skuel")
    assert result.is_error is False
    row = result.value[0]
    assert row["name"] == "Food"
    assert row["spent"] == "80.00"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_accounts_filters_by_type() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1",
                        "attributes": {
                            "name": "Checking",
                            "type": "asset",
                            "currency_code": "USD",
                            "current_balance": "1500.00",
                        },
                    }
                ]
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    result = await client.list_accounts("skuel", account_type="asset")
    assert result.is_error is False
    assert seen_params["type"] == "asset"
    assert result.value[0]["current_balance"] == "1500.00"
    await client.aclose()


@pytest.mark.asyncio
async def test_category_insight_parses_flat_list_response() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"name": "Food", "difference_float": -80.0, "currency_code": "USD"},
                {"name": "Rent", "difference_float": -1200.0, "currency_code": "USD"},
            ],
        )

    client = _make_client(httpx.MockTransport(handler))
    result = await client.category_insight("skuel", start="2026-04-01", end="2026-04-30")
    assert result.is_error is False
    rows = result.value
    assert len(rows) == 2
    assert rows[0]["name"] == "Food"
    assert rows[0]["difference"] == "-80.0"
    await client.aclose()


@pytest.mark.asyncio
async def test_health_check_hits_about_endpoint() -> None:
    seen_path: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_path.append(request.url.path)
        return httpx.Response(200, json={"data": {"version": "6.1.0"}})

    client = _make_client(httpx.MockTransport(handler))
    result = await client.health_check("skuel")
    assert result.is_error is False
    assert result.value is True
    assert seen_path == ["/api/v1/about"]
    await client.aclose()
