"""
Vault Bridge Routes — ADR-070
==============================

Bidirectional Obsidian ↔ SKUEL sync endpoints.

Routes:
    GET  /submissions/sync       — Vault sync page (canonical URL, submissions MOC section).
    GET  /settings/vault         — 301 redirect → /submissions/sync (legacy URL preserved).
    POST /settings/vault/sync    — HTMX endpoint: run sync, return HTML results fragment.
    POST /settings/vault/preview — HTMX endpoint: dry-run preview, nothing is written.
    POST /settings/vault/preview/consent — HTMX endpoint: grant consent then re-run the PREVIEW.
    POST /settings/vault/consent — HTMX endpoint: grant write consent then run sync.
    POST /api/vault/sync         — JSON API: run PERSONAL sync (returns VaultSyncStats dict).
    POST /api/vault/preview      — JSON API: dry-run PERSONAL preview (VaultSyncPreview dict).
    POST /api/vault/sync/consent — JSON API: grant consent + run PERSONAL sync.
    POST /api/vault/sync/content — JSON API (admin): run CONTENT vault sync (inbound-only).

The reconciler is the single directory-ingest engine (ADR-070 Decision 9). CONTENT
sync is the admin door onto it — the same ``VaultReconciler.sync`` the personal
routes use, scoped to ``VaultKind.CONTENT`` (fixed content-vault owner, no outbound).

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P, Span
from pydantic import ValidationError
from starlette.responses import RedirectResponse

from adapters.inbound.auth import (
    make_service_getter,
    require_admin,
    require_authenticated_user,
)
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.models.type_hints import UserUID
from core.models.vault_request import ContentVaultSyncRequest
from core.services.vault.vault_descriptor import VaultKind
from core.services.vault.vault_reconciler import VaultDescription
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.patterns import PageHeader
from ui.vault.sync_fragments import (
    consent_form,
    preview_button,
    preview_error_fragment,
    preview_fragment,
    privacy_wall_panel,
    sync_button,
    sync_error_fragment,
    sync_stats_fragment,
)
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from core.services.entry_grounding_service import EntryGroundingService
    from core.services.vault.vault_reconciler import VaultReconciler

logger = get_logger("skuel.routes.vault")


def create_vault_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    vault_reconciler: VaultReconciler,
    user_service: Any,
    entry_grounding: EntryGroundingService | None = None,
) -> None:
    """Register vault bridge routes (UI + API)."""
    get_user_service = make_service_getter(user_service)

    async def _ground_after_sync(user_uid: UserUID) -> None:
        """Post-sync entry→Ku grounding pass (Entry-Enrichment PR 3).

        Fail-soft: grounding problems are logged, never surfaced as a sync
        failure. Eventual consistency by design — in the app process the
        background embedding worker embeds THIS sync's new entries up to a
        batch interval later, so this pass grounds everything embedded since
        the previous pass and a just-synced entry grounds on the next sync
        (or via scripts/ground_knowledge_entries.py). Keeps the worker
        generic — no domain logic inside it (ADR-070 no-background-watcher
        stance for the trigger).
        """
        if entry_grounding is None:
            return
        result = await entry_grounding.ground_pending(user_uid)
        if result.is_error:
            logger.warning(f"Post-sync grounding pass failed: {result.expect_error()}")
            return
        report = result.value
        if report.edges_written:
            logger.info(
                f"Post-sync grounding: {report.edges_written} edge(s) across "
                f"{report.entries_with_writes} entries for {user_uid}"
            )

    async def _describe_personal_vault(user_uid: UserUID) -> VaultDescription:
        """Unwrap the reconciler's read-only wall description for UI rendering.

        ``describe`` reports "no vault" as ``vault_configured=False`` rather
        than an error; an error here would be a wiring defect — fall back to
        the unconfigured shape instead of a 500 on a trust page.
        """
        result = await vault_reconciler.describe(VaultKind.PERSONAL, user_uid)
        return result.value if result.is_ok else VaultDescription(vault_configured=False)

    # ------------------------------------------------------------------
    # UI routes
    # ------------------------------------------------------------------

    @rt("/submissions/sync")
    async def submissions_sync_page(request: Request) -> Any:
        """Vault sync page under the Submissions MOC — shows the privacy wall."""
        user_uid = require_authenticated_user(request)

        description = await _describe_personal_vault(user_uid)
        if description.vault_configured:
            sync_area: tuple[Any, ...] = (
                privacy_wall_panel(description),
                Div(
                    sync_button(),
                    preview_button(),
                    cls="flex items-center gap-4",
                ),
                Div(id="vault-results"),
            )
        else:
            sync_area = (
                Div(
                    P(
                        "No personal vault is configured for your account, "
                        "so there is nothing to sync — and nothing is read.",
                        cls="text-sm text-base-content/70",
                    ),
                    cls="bg-base-200 border border-base-300 rounded-lg p-5",
                ),
            )

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
            *sync_area,
            cls="max-w-2xl",
        )

        return render_submissions_sidebar_page(
            content=content,
            active="sync",
            request=request,
        )

    @rt("/settings/vault")
    def vault_settings_redirect(request: Request) -> Any:
        """301 redirect — canonical URL moved to /submissions/sync."""
        return RedirectResponse(url="/submissions/sync", status_code=301)

    @rt("/settings/vault/sync", methods=["POST"])
    @csrf_protected
    async def vault_sync_htmx(request: Request) -> Any:
        """HTMX endpoint: run sync, return HTML results fragment."""
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return sync_error_fragment(str(result.expect_error()))

        stats = result.value
        if stats.first_run_notice:
            return consent_form(await _describe_personal_vault(user_uid))

        await _ground_after_sync(user_uid)
        return sync_stats_fragment(asdict(stats))

    @rt("/settings/vault/preview", methods=["POST"])
    @csrf_protected
    async def vault_preview_htmx(request: Request) -> Any:
        """HTMX endpoint: dry-run preview — reports what a sync WOULD do, writes nothing."""
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.preview(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return preview_error_fragment(str(result.expect_error()))

        preview = result.value
        if preview.first_run_notice:
            # Consent covers reading too (ADR-070 Decision 6 amendment) —
            # preview compares vault files, so it engages the same gate.
            # Consent granted from HERE continues into a PREVIEW, never a
            # real sync — the user asked to see, not to run (Kody #527).
            return consent_form(
                await _describe_personal_vault(user_uid),
                post_to="/settings/vault/preview/consent",
                button_label="Allow and preview",
            )

        return preview_fragment(preview)

    @rt("/settings/vault/preview/consent", methods=["POST"])
    @csrf_protected
    async def vault_preview_consent_htmx(request: Request) -> Any:
        """HTMX endpoint: grant sync consent then run the DRY-RUN preview.

        The preview-first flow must stay a preview across the consent hop —
        the sibling ``/settings/vault/consent`` runs a real sync (Kody #527).
        """
        user_uid = require_authenticated_user(request)

        consent_result = await vault_reconciler.grant_consent(user_uid)
        if consent_result.is_error:
            return preview_error_fragment(str(consent_result.expect_error()))

        result = await vault_reconciler.preview(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return preview_error_fragment(str(result.expect_error()))

        return preview_fragment(result.value)

    @rt("/settings/vault/consent", methods=["POST"])
    @csrf_protected
    async def vault_consent_htmx(request: Request) -> Any:
        """HTMX endpoint: grant write consent then run sync, return results fragment."""
        user_uid = require_authenticated_user(request)

        consent_result = await vault_reconciler.grant_consent(user_uid)
        if consent_result.is_error:
            return sync_error_fragment(str(consent_result.expect_error()))

        sync_result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
        if sync_result.is_error:
            return sync_error_fragment(str(sync_result.expect_error()))

        await _ground_after_sync(user_uid)
        return sync_stats_fragment(asdict(sync_result.value))

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

        result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return Result.fail(result)

        stats = result.value
        if stats.first_run_notice:
            return Result.ok({"first_run_notice": True})
        await _ground_after_sync(user_uid)
        return Result.ok(asdict(stats))

    @rt("/api/vault/preview", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def vault_preview(request: Request) -> Result[dict[str, Any]]:
        """Dry-run preview of a PERSONAL vault sync — nothing is written.

        Returns:
            200 + VaultSyncPreview dict on success (vault-relative paths only).
            200 + {"first_run_notice": true} before consent (preview reads the
            vault, so it shares the sync consent gate).
        """
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.preview(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return Result.fail(result)

        preview = result.value
        if preview.first_run_notice:
            return Result.ok({"first_run_notice": True})
        return Result.ok(asdict(preview))

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

        sync_result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
        if sync_result.is_error:
            return Result.fail(sync_result)

        await _ground_after_sync(user_uid)
        stats = sync_result.value
        payload = asdict(stats)
        payload["consented"] = True
        return Result.ok(payload)

    @rt("/api/vault/sync/content", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler(success_status=200)
    async def vault_sync_content(
        request: Request, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Sync the shared content (curriculum) vault through the reconciler.

        Admin-only. Inbound-only: ``sync`` ignores the acting user for
        ``VaultKind.CONTENT`` (the fixed content-vault owner from the descriptor
        wins) and returns after ingest, since the content vault has no task
        round-trip. This is the one directory-ingest path (ADR-070 Decision 9) —
        it replaces the retired ``POST /api/ingest/directory`` admin door.

        Request body (JSON, optional — validated by ContentVaultSyncRequest):
            force: bool — re-process unchanged files too (re-chunk/migration
                campaigns); the wall and deletion reconciliation stay active.

        Returns:
            200 + VaultSyncStats dict on success.
        """
        try:
            raw = await request.body()
            payload = json.loads(raw) if raw else {}
            body = ContentVaultSyncRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        result = await vault_reconciler.sync(
            VaultKind.CONTENT, UserUID(current_user.uid), force=body.force
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(asdict(result.value))
