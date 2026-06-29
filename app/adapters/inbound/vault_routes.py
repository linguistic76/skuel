"""
Vault Bridge Routes — ADR-070
==============================

Bidirectional Obsidian ↔ SKUEL sync endpoints.

Routes:
    GET  /submissions/sync       — Vault sync page (canonical URL, submissions MOC section).
    GET  /settings/vault         — 301 redirect → /submissions/sync (legacy URL preserved).
    POST /settings/vault/sync    — HTMX endpoint: run sync, return HTML results fragment.
    POST /settings/vault/consent — HTMX endpoint: grant write consent then run sync.
    POST /api/vault/sync         — JSON API: run sync (returns VaultSyncStats dict).
    POST /api/vault/sync/consent — JSON API: grant consent + run sync.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    Div,
    Form,
    Li,
    P,
    Span,
    Ul,
)
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.components import Button
from ui.patterns import PageHeader
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from core.services.vault.vault_reconciler import VaultReconciler

logger = get_logger("skuel.routes.vault")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _sync_button(label: str = "Sync from Obsidian", spinner_id: str = "vault-spinner") -> Form:
    """HTMX form that triggers vault sync and swaps the results area."""
    return Form(
        Button(
            label,
            type="submit",
        ),
        Span(
            "",
            id=spinner_id,
            cls="htmx-indicator ml-3",
            **{"uk-spinner": "ratio: 0.6"},
        ),
        hx_post="/settings/vault/sync",
        hx_target="#vault-results",
        hx_swap="innerHTML",
        hx_indicator=f"#{spinner_id}",
        cls="flex items-center gap-2",
    )


def _consent_form() -> Div:
    """Fragment shown when first_run_notice is True."""
    return Div(
        Div(
            H3("Allow Obsidian write access?", cls="text-lg font-semibold mb-2"),
            P(
                "After syncing, SKUEL will inject ",
                Span("🆔 sk_XXXXXX", cls="font-mono text-sm"),
                " IDs back into your vault files and mark completed tasks with ",
                Span("[x] ✅ date", cls="font-mono text-sm"),
                ". This is the round-trip that keeps Obsidian and SKUEL in step.",
                cls="text-base-content/70 mb-4",
            ),
            Form(
                Button(
                    "Allow and sync",
                    type="submit",
                ),
                Span(
                    "",
                    id="consent-spinner",
                    cls="htmx-indicator ml-3",
                    **{"uk-spinner": "ratio: 0.6"},
                ),
                hx_post="/settings/vault/consent",
                hx_target="#vault-results",
                hx_swap="innerHTML",
                hx_indicator="#consent-spinner",
                cls="flex items-center gap-2",
            ),
            cls="bg-base-200 border border-base-300 rounded-lg p-5",
        ),
        id="vault-results",
    )


def _sync_stats_fragment(stats_dict: dict[str, Any]) -> Div:
    """Fragment shown after a successful sync."""
    ingested = stats_dict.get("entries_ingested", 0)
    injected = stats_dict.get("ids_injected", 0)
    done = stats_dict.get("tasks_marked_done", 0)
    errors: list[str] = stats_dict.get("errors", [])

    items = [
        Li(Span(f"{ingested}", cls="font-semibold"), " notes ingested"),
        Li(Span(f"{injected}", cls="font-semibold"), " task IDs injected into vault"),
        Li(Span(f"{done}", cls="font-semibold"), " tasks marked done in vault"),
    ]
    error_section = (
        Div(
            H3("Errors", cls="text-sm font-semibold text-error mt-3 mb-1"),
            Ul(*[Li(e, cls="text-xs text-error") for e in errors], cls="list-disc pl-4"),
        )
        if errors
        else Span()
    )

    return Div(
        Div(
            H3("Sync complete", cls="text-base font-semibold text-success mb-2"),
            Ul(*items, cls="list-disc pl-4 text-sm text-base-content/80 space-y-1"),
            error_section,
            cls="bg-base-200 border border-base-300 rounded-lg p-5",
        ),
        _sync_button("Sync again"),
        id="vault-results",
        cls="space-y-4",
    )


def _sync_error_fragment(message: str) -> Div:
    """Fragment shown when sync fails."""
    return Div(
        P(f"Sync failed: {message}", cls="text-error text-sm"),
        _sync_button("Try again"),
        id="vault-results",
        cls="space-y-3",
    )


def create_vault_routes(
    app: FastHTMLApp, rt: RouteDecorator, vault_reconciler: VaultReconciler
) -> None:
    """Register vault bridge routes (UI + API)."""

    # ------------------------------------------------------------------
    # UI routes
    # ------------------------------------------------------------------

    @rt("/submissions/sync")
    async def submissions_sync_page(request: Request) -> Any:
        """Vault sync page under the Submissions MOC."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Obsidian Sync",
                subtitle="Pull your Daily Notes into SKUEL and write completion dates back.",
            ),
            P(
                "Each daily note with ",
                Span("pipeline: extract_activities", cls="font-mono text-sm"),
                " in its frontmatter is ingested as a UserEntry. "
                "Checkbox lines become Tasks. "
                "SKUEL injects a ",
                Span("🆔 sk_XXXXXX", cls="font-mono text-sm"),
                " ID into each task line so completed tasks can be written back.",
                cls="text-base-content/70 mb-6",
            ),
            _sync_button(),
            Div(id="vault-results"),
            cls="max-w-2xl",
        )

        return await render_submissions_sidebar_page(
            content=content,
            active="sync",
            request=request,
        )

    @rt("/settings/vault")
    async def vault_settings_redirect(request: Request) -> Any:
        """301 redirect — canonical URL moved to /submissions/sync."""
        return RedirectResponse(url="/submissions/sync", status_code=301)

    @rt("/settings/vault/sync", methods=["POST"])
    @csrf_protected
    async def vault_sync_htmx(request: Request) -> Any:
        """HTMX endpoint: run sync, return HTML results fragment."""
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.sync(
            user_uid=user_uid,
            vault_path=str(vault_reconciler.vault_root),
        )
        if result.is_error:
            return _sync_error_fragment(str(result.expect_error()))

        stats = result.value
        if stats.first_run_notice:
            return _consent_form()

        return _sync_stats_fragment(asdict(stats))

    @rt("/settings/vault/consent", methods=["POST"])
    @csrf_protected
    async def vault_consent_htmx(request: Request) -> Any:
        """HTMX endpoint: grant write consent then run sync, return results fragment."""
        user_uid = require_authenticated_user(request)

        consent_result = await vault_reconciler.grant_consent(user_uid)
        if consent_result.is_error:
            return _sync_error_fragment(str(consent_result.expect_error()))

        sync_result = await vault_reconciler.sync(
            user_uid=user_uid,
            vault_path=str(vault_reconciler.vault_root),
        )
        if sync_result.is_error:
            return _sync_error_fragment(str(sync_result.expect_error()))

        return _sync_stats_fragment(asdict(sync_result.value))

    # ------------------------------------------------------------------
    # JSON API routes (existing)
    # ------------------------------------------------------------------

    @rt("/api/vault/sync", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def vault_sync(request: Request) -> Result[dict[str, Any]]:
        """Run a full bidirectional vault sync for the authenticated user.

        Returns:
            200 + VaultSyncStats dict on success.
            200 + {"first_run_notice": true} on first call before consent.
        """
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.sync(
            user_uid=user_uid, vault_path=str(vault_reconciler.vault_root)
        )
        if result.is_error:
            return Result.fail(result)

        stats = result.value
        if stats.first_run_notice:
            return Result.ok({"first_run_notice": True})
        return Result.ok(asdict(stats))

    @rt("/api/vault/sync/consent", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def vault_sync_consent(request: Request) -> Result[dict[str, Any]]:
        """Grant vault-write consent for the authenticated user.

        After consent is granted, triggers a full sync and returns its stats.
        """
        user_uid = require_authenticated_user(request)

        consent_result = await vault_reconciler.grant_consent(user_uid)
        if consent_result.is_error:
            return Result.fail(consent_result)

        sync_result = await vault_reconciler.sync(
            user_uid=user_uid, vault_path=str(vault_reconciler.vault_root)
        )
        if sync_result.is_error:
            return Result.fail(sync_result)

        stats = sync_result.value
        payload = asdict(stats)
        payload["consented"] = True
        return Result.ok(payload)
