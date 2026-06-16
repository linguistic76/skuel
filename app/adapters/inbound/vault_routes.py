"""
Vault Bridge Routes — ADR-070
==============================

Bidirectional Obsidian ↔ SKUEL sync endpoints.

Routes:
    POST /api/vault/sync         — Run a full vault sync for the authenticated user.
                                   Returns VaultSyncStats JSON on success.
                                   Returns {"first_run_notice": true} when consent has not
                                   yet been granted; the client renders the consent modal.
    POST /api/vault/sync/consent — Grant vault-write consent and re-trigger sync.
    GET  /settings/vault         — Settings page with "Update from my vault" button.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.vault.vault_reconciler import VaultReconciler

logger = get_logger("skuel.routes.vault")


def create_vault_routes(
    app: FastHTMLApp, rt: RouteDecorator, vault_reconciler: VaultReconciler
) -> None:
    """Register vault bridge routes."""

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
