"""
Firefly III REST Client
=======================

Async Firefly III REST adapter. This is the **only** SKUEL file that knows
about Firefly's wire format — services and UI consume `FireflyOperations`
protocol types from `core/ports/finance_protocols.py`.

Two-book design: one Firefly instance, two users (one personal, one SKUEL
business), each with its own Personal Access Token. Every method takes a
`book: FireflyBook` argument that picks which PAT to use.

See: /docs/decisions/ADR-051-firefly-iii-finance-integration.md
"""

from __future__ import annotations

import os
from typing import Any, Literal, cast

import httpx

from core.ports.finance_protocols import (
    FireflyAccountBalance,
    FireflyBook,
    FireflyBudget,
    FireflyCategory,
    FireflyInsightRow,
    FireflyTransaction,
    FireflyTransactionCreate,
)
from core.utils.exception_types import FIREFLY_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.adapters.firefly")

# Default request timeout in seconds — Firefly on a Droplet is slower than
# localhost; keep conservative and tune via FIREFLY_TIMEOUT_SECONDS.
_DEFAULT_TIMEOUT = 10.0


class FireflyClient:
    """Async Firefly III REST client. Implements `FireflyOperations` protocol.

    Construct one per process via the bootstrap layer; it holds an
    `httpx.AsyncClient` that is closed on app shutdown.
    """

    def __init__(
        self,
        base_url: str,
        pat_personal: str,
        pat_skuel: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("Firefly base_url must not be empty")
        if not pat_personal and not pat_skuel:
            raise ValueError(
                "At least one Firefly Personal Access Token must be configured "
                "(FIREFLY_PAT_PERSONAL or FIREFLY_PAT_SKUEL)"
            )

        self._base_url = base_url.rstrip("/")
        self._tokens: dict[FireflyBook, str] = {
            "personal": pat_personal,
            "skuel": pat_skuel,
        }
        self._timeout = timeout_seconds
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(
        self,
    ) -> "FireflyClient":  # skuel-lint: disable=SKUEL029 -- async context-manager protocol: `async with` awaits __aenter__
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    @classmethod
    def from_env(cls, http_client: httpx.AsyncClient | None = None) -> FireflyClient:
        """Build a client from credentials (keychain-first, env fallback).

        PATs go through `get_credential()` so keychain-stored tokens are found
        when `SKUEL_CREDENTIAL_BACKEND=keyring`. Non-secret config (base URL,
        timeout) stays on `os.environ` — it lives in `.env`, not the keychain.
        """
        from core.config.credential_store import get_credential

        return cls(
            base_url=os.environ.get("FIREFLY_BASE_URL", "http://firefly:8080"),
            pat_personal=get_credential("FIREFLY_PAT_PERSONAL", fallback_to_env=True) or "",
            pat_skuel=get_credential("FIREFLY_PAT_SKUEL", fallback_to_env=True) or "",
            timeout_seconds=float(os.environ.get("FIREFLY_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT)),
            http_client=http_client,
        )

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self, book: FireflyBook) -> dict[str, str]:
        token = self._tokens.get(book, "")
        if not token:
            raise ValueError(
                f"No Firefly Personal Access Token configured for book={book!r}. "
                f"Set FIREFLY_PAT_{'PERSONAL' if book == 'personal' else 'SKUEL'}."
            )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        book: FireflyBook,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """Issue a request and return a Result-wrapped JSON body.

        Maps httpx errors to `Errors.integration(service="firefly", ...)` and
        4xx/5xx responses to integration errors with the status code attached.
        """
        url = f"{self._base_url}/api/v1{path}"
        try:
            response = await self._client.request(
                method, url, headers=self._headers(book), params=params, json=json_body
            )
        except FIREFLY_EXCEPTIONS as exc:
            logger.warning(f"Firefly {method} {path} failed: {exc}")
            return Result.fail(
                Errors.integration(
                    service="firefly",
                    message=f"HTTP transport error: {exc}",
                )
            )
        except ValueError as exc:
            # Raised by _headers() if PAT missing for the requested book
            return Result.fail(Errors.validation(field="book", message=str(exc)))

        if response.status_code >= 400:
            # Firefly returns JSON error bodies; surface them for debugging
            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text}
            logger.warning(f"Firefly {method} {path} returned {response.status_code}: {body}")
            return Result.fail(
                Errors.integration(
                    service="firefly",
                    message=f"{response.status_code} {response.reason_phrase}",
                    status_code=response.status_code,
                    body=body,
                )
            )

        try:
            return Result.ok(cast("dict[str, Any]", response.json()))
        except ValueError as exc:
            return Result.fail(
                Errors.integration(
                    service="firefly",
                    message=f"Invalid JSON from Firefly: {exc}",
                )
            )

    # ------------------------------------------------------------------
    # Transaction shape conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_transaction(item: dict[str, Any]) -> FireflyTransaction:
        """Collapse Firefly's nested JSON:API shape into our flat TypedDict.

        Firefly returns `{id, attributes: {transactions: [{...}]}}` — each
        group has one or more splits. We flatten to the first split.
        """
        attrs = item.get("attributes") or {}
        splits = attrs.get("transactions") or [{}]
        split = splits[0]
        return cast(
            "FireflyTransaction",
            {
                "transaction_id": str(item.get("id", "")),
                "transaction_journal_id": str(split.get("transaction_journal_id", "")),
                "type": split.get("type", "withdrawal"),
                "date": split.get("date", ""),
                "amount": str(split.get("amount", "0")),
                "currency_code": split.get("currency_code", "USD"),
                "description": split.get("description", ""),
                "category_name": split.get("category_name"),
                "budget_name": split.get("budget_name"),
                "source_name": split.get("source_name", ""),
                "destination_name": split.get("destination_name", ""),
                "tags": list(split.get("tags") or []),
                "notes": split.get("notes"),
            },
        )

    # ------------------------------------------------------------------
    # FireflyOperations implementation
    # ------------------------------------------------------------------

    async def list_transactions(
        self,
        book: FireflyBook,
        *,
        start: str | None = None,
        end: str | None = None,
        transaction_type: Literal["withdrawal", "deposit", "transfer"] | None = None,
        limit: int = 100,
    ) -> Result[list[FireflyTransaction]]:
        params: dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if transaction_type:
            params["type"] = transaction_type

        result = await self._request("GET", book, "/transactions", params=params)
        if result.is_error:
            return Result.fail(result)

        data = result.value.get("data") or []
        return Result.ok([self._flatten_transaction(item) for item in data])

    async def create_transaction(
        self, book: FireflyBook, payload: FireflyTransactionCreate
    ) -> Result[FireflyTransaction]:
        # Firefly expects the split wrapped in `transactions: [...]`
        split: dict[str, Any] = {k: v for k, v in payload.items() if v is not None}
        body: dict[str, Any] = {
            "error_if_duplicate_hash": False,
            "apply_rules": True,
            "fire_webhooks": True,
            "transactions": [split],
        }
        # external_id is set at the group level, not inside the split
        if "external_id" in split:
            body["external_id"] = split.pop("external_id")

        result = await self._request("POST", book, "/transactions", json_body=body)
        if result.is_error:
            return Result.fail(result)

        data = result.value.get("data") or {}
        return Result.ok(self._flatten_transaction(data))

    async def find_transaction_by_external_id(
        self, book: FireflyBook, external_id: str
    ) -> Result[FireflyTransaction | None]:
        # Firefly search query: `external_id_is:<value>`
        params = {"query": f"external_id_is:{external_id}", "limit": 1}
        result = await self._request("GET", book, "/search/transactions", params=params)
        if result.is_error:
            return Result.fail(result)

        data = result.value.get("data") or []
        if not data:
            return Result.ok(None)
        return Result.ok(self._flatten_transaction(data[0]))

    async def list_budgets(self, book: FireflyBook) -> Result[list[FireflyBudget]]:
        result = await self._request("GET", book, "/budgets")
        if result.is_error:
            return Result.fail(result)

        rows: list[FireflyBudget] = []
        for item in result.value.get("data") or []:
            attrs = item.get("attributes") or {}
            spent_entries = attrs.get("spent") or []
            spent = str(spent_entries[0].get("sum", "0")) if spent_entries else "0"
            limit_val: str | None = None
            period_start: str | None = None
            period_end: str | None = None
            if attrs.get("auto_budget_amount"):
                limit_val = str(attrs["auto_budget_amount"])
                period_start = attrs.get("auto_budget_period_start")
                period_end = attrs.get("auto_budget_period_end")
            rows.append(
                cast(
                    "FireflyBudget",
                    {
                        "budget_id": str(item.get("id", "")),
                        "name": attrs.get("name", ""),
                        "active": bool(attrs.get("active", True)),
                        "currency_code": attrs.get("currency_code", "USD"),
                        "spent": spent,
                        "limit": limit_val,
                        "period_start": period_start,
                        "period_end": period_end,
                    },
                )
            )
        return Result.ok(rows)

    async def list_categories(self, book: FireflyBook) -> Result[list[FireflyCategory]]:
        result = await self._request("GET", book, "/categories")
        if result.is_error:
            return Result.fail(result)

        rows: list[FireflyCategory] = []
        for item in result.value.get("data") or []:
            attrs = item.get("attributes") or {}
            spent_list = attrs.get("spent") or []
            earned_list = attrs.get("earned") or []
            spent = str(spent_list[0].get("sum", "0")) if spent_list else "0"
            earned = str(earned_list[0].get("sum", "0")) if earned_list else "0"
            rows.append(
                cast(
                    "FireflyCategory",
                    {
                        "category_id": str(item.get("id", "")),
                        "name": attrs.get("name", ""),
                        "spent": spent,
                        "earned": earned,
                    },
                )
            )
        return Result.ok(rows)

    async def list_accounts(
        self,
        book: FireflyBook,
        *,
        account_type: Literal["asset", "revenue", "expense"] | None = None,
    ) -> Result[list[FireflyAccountBalance]]:
        params: dict[str, Any] = {}
        if account_type:
            params["type"] = account_type
        result = await self._request("GET", book, "/accounts", params=params)
        if result.is_error:
            return Result.fail(result)

        rows: list[FireflyAccountBalance] = []
        for item in result.value.get("data") or []:
            attrs = item.get("attributes") or {}
            rows.append(
                cast(
                    "FireflyAccountBalance",
                    {
                        "account_id": str(item.get("id", "")),
                        "name": attrs.get("name", ""),
                        "type": attrs.get("type", ""),
                        "currency_code": attrs.get("currency_code", "USD"),
                        "current_balance": str(attrs.get("current_balance", "0")),
                    },
                )
            )
        return Result.ok(rows)

    async def category_insight(
        self, book: FireflyBook, *, start: str, end: str
    ) -> Result[list[FireflyInsightRow]]:
        result = await self._request(
            "GET",
            book,
            "/insight/expense/category",
            params={"start": start, "end": end},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_parse_insight_rows(result.value))

    async def budget_insight(
        self, book: FireflyBook, *, start: str, end: str
    ) -> Result[list[FireflyInsightRow]]:
        result = await self._request(
            "GET",
            book,
            "/insight/expense/budget",
            params={"start": start, "end": end},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_parse_insight_rows(result.value))

    async def health_check(self, book: FireflyBook) -> Result[bool]:
        result = await self._request("GET", book, "/about", params=None)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)


def _parse_insight_rows(
    body: dict[str, Any] | list[dict[str, Any]],
) -> list[FireflyInsightRow]:
    """Firefly insight endpoints return a flat list (not JSON:API)."""
    rows_in = body if isinstance(body, list) else body.get("data") or []
    return [
        cast(
            "FireflyInsightRow",
            {
                "name": row.get("name", ""),
                "difference": str(row.get("difference_float", row.get("difference", "0"))),
                "currency_code": row.get("currency_code", "USD"),
            },
        )
        for row in rows_in
    ]


__all__ = ["FireflyClient"]
