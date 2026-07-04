"""
Vault Bridge Routes — ADR-070
==============================

Bidirectional Obsidian ↔ SKUEL sync endpoints.

Routes:
    GET  /submissions/sync       — Vault sync page (canonical URL, submissions MOC section).
    GET  /settings/vault         — 301 redirect → /submissions/sync (legacy URL preserved).
    POST /settings/vault/sync    — HTMX endpoint: run sync, return HTML results fragment.
    POST /settings/vault/consent — HTMX endpoint: grant write consent then run sync.
    POST /api/vault/sync         — JSON API: run PERSONAL sync (returns VaultSyncStats dict).
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

from fasthtml.common import (
    H3,
    Div,
    Form,
    Li,
    P,
    Span,
    Ul,
)
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
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.components import Button, Loading
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
        Loading(size="sm", id=spinner_id, cls="htmx-indicator ml-3"),
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
                Loading(size="sm", id="consent-spinner", cls="htmx-indicator ml-3"),
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
    """Fragment shown after a sync ran.

    "Sync complete" ONLY when the run was clean (G10) — failed files,
    ingestion errors, and dangling-target warnings flip the header and are
    listed in full, never hidden behind a success banner.
    """
    ingested = stats_dict.get("entries_ingested", 0)
    injected = stats_dict.get("ids_injected", 0)
    done = stats_dict.get("tasks_marked_done", 0)
    failed = stats_dict.get("files_failed", 0)
    walled = stats_dict.get("files_walled", 0)
    unsupported = stats_dict.get("files_unsupported", 0)
    errors: list[str] = stats_dict.get("errors", [])
    warnings: list[str] = stats_dict.get("warnings", [])

    items = [
        Li(Span(f"{ingested}", cls="font-semibold"), " notes ingested"),
        Li(Span(f"{injected}", cls="font-semibold"), " task IDs injected into vault"),
        Li(Span(f"{done}", cls="font-semibold"), " tasks marked done in vault"),
    ]
    if failed:
        items.append(Li(Span(f"{failed}", cls="font-semibold text-error"), " files failed"))
    if walled:
        items.append(
            Li(Span(f"{walled}", cls="font-semibold"), " files skipped (outside sync folders)")
        )
    if unsupported:
        items.append(
            Li(Span(f"{unsupported}", cls="font-semibold"), " files skipped (unsupported format)")
        )

    error_section = (
        Div(
            H3("Errors", cls="text-sm font-semibold text-error mt-3 mb-1"),
            Ul(*[Li(e, cls="text-xs text-error") for e in errors], cls="list-disc pl-4"),
        )
        if errors
        else Span()
    )
    warning_section = (
        Div(
            H3("Warnings", cls="text-sm font-semibold text-warning mt-3 mb-1"),
            Ul(*[Li(w, cls="text-xs text-warning") for w in warnings], cls="list-disc pl-4"),
        )
        if warnings
        else Span()
    )

    clean = not errors and not warnings and not failed
    # Every failed file also appends an error entry, so len(errors) already
    # covers files_failed — max() only guards a count drift between the two.
    problem_count = max(len(errors), failed)
    header = (
        H3("Sync complete", cls="text-base font-semibold text-success mb-2")
        if clean
        else H3(
            f"Sync finished with problems ({problem_count} error(s), {len(warnings)} warning(s))",
            cls="text-base font-semibold text-error mb-2",
        )
    )

    return Div(
        Div(
            header,
            Ul(*items, cls="list-disc pl-4 text-sm text-base-content/80 space-y-1"),
            error_section,
            warning_section,
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
    app: FastHTMLApp,
    rt: RouteDecorator,
    vault_reconciler: VaultReconciler,
    user_service: Any,
) -> None:
    """Register vault bridge routes (UI + API)."""
    get_user_service = make_service_getter(user_service)

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

        result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
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

        sync_result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
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

        result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
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

        sync_result = await vault_reconciler.sync(VaultKind.PERSONAL, user_uid)
        if sync_result.is_error:
            return Result.fail(sync_result)

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
