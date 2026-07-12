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
from core.services.vault.vault_reconciler import VaultDescription, VaultSyncPreview
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.components import Button, ButtonT, Loading
from ui.patterns import PageHeader
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from core.services.entry_grounding_service import EntryGroundingService
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


def _preview_button(label: str = "Preview sync", spinner_id: str = "vault-preview-spinner") -> Form:
    """HTMX form for the dry-run preview — secondary styling, same results target."""
    return Form(
        Button(
            label,
            type="submit",
            cls=ButtonT.secondary,
        ),
        Loading(size="sm", id=spinner_id, cls="htmx-indicator ml-3"),
        hx_post="/settings/vault/preview",
        hx_target="#vault-results",
        hx_swap="innerHTML",
        hx_indicator=f"#{spinner_id}",
        cls="flex items-center gap-2",
    )


def _read_scope_phrase(description: VaultDescription) -> tuple[Any, ...]:
    """Inline FT children stating exactly what a sync may read — from the live wall.

    Shared by the consent form and the privacy panel so the two surfaces can
    never drift apart (or from the actual allowlist). Folder names arrive
    vault-relative (``VaultReconciler.describe``, #525 — no absolute paths).
    """
    if description.whole_vault_open:
        return (
            "SKUEL will read notes from your whole vault (a combined vault syncs "
            "every folder), except the ",
            Span("je_*", cls="font-mono text-sm"),
            " pipeline staging folders, which are never read",
        )
    if description.allowed_folders:
        return (
            "SKUEL will read notes from these folders of your vault — ",
            Span(
                ", ".join(f"{folder}/" for folder in description.allowed_folders),
                cls="font-mono text-sm",
            ),
            " — and nothing else",
        )
    return ("No folders are currently synced from this vault, so SKUEL will read nothing",)


def _privacy_wall_panel(description: VaultDescription) -> Div:
    """The visible privacy wall: exactly which folders a sync may read."""
    if description.allowed_folders and not description.whole_vault_open:
        scope: Any = Ul(
            *[
                Li(Span(f"{folder}/", cls="font-mono text-sm"))
                for folder in description.allowed_folders
            ],
            cls="list-disc pl-4 space-y-1 text-sm text-base-content/80",
        )
    else:
        scope = P(*_read_scope_phrase(description), ".", cls="text-sm text-base-content/80")
    return Div(
        H3("What SKUEL can see", cls="text-base font-semibold mb-2"),
        scope,
        P(
            "Everything else in your vault is never read, never searched, "
            "and never sent to an LLM.",
            cls="text-xs text-base-content/60 mt-3",
        ),
        cls="bg-base-200 border border-base-300 rounded-lg p-5 mb-6",
    )


def _consent_form(
    description: VaultDescription,
    *,
    post_to: str = "/settings/vault/consent",
    button_label: str = "Allow and sync",
) -> Div:
    """Fragment shown when first_run_notice is True.

    Consent covers BOTH directions of the sync (read + write) — nothing is
    ingested before the user accepts here. The folder list comes from the live
    allowlist (``VaultReconciler.describe``), never hardcoded prose.
    ``post_to``/``button_label`` keep the requested action honest: consent
    reached from Preview continues into a PREVIEW, never a real sync
    (Kody #527).
    """
    return Div(
        Div(
            H3("Allow SKUEL to sync your Obsidian vault?", cls="text-lg font-semibold mb-2"),
            P(
                "Syncing works in both directions. ",
                *_read_scope_phrase(description),
                ". It will also write ",
                Span("🆔 sk_XXXXXX", cls="font-mono text-sm"),
                " IDs back into your task lines and mark completed tasks with ",
                Span("[x] ✅ date", cls="font-mono text-sm"),
                ". Nothing is read or written until you allow it.",
                cls="text-base-content/70 mb-4",
            ),
            Form(
                Button(
                    button_label,
                    type="submit",
                ),
                Loading(size="sm", id="consent-spinner", cls="htmx-indicator ml-3"),
                hx_post=post_to,
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
    moved = stats_dict.get("moves_detected", 0)
    errors: list[str] = stats_dict.get("errors", [])
    warnings: list[str] = stats_dict.get("warnings", [])

    items = [
        Li(Span(f"{ingested}", cls="font-semibold"), " notes ingested"),
        Li(Span(f"{injected}", cls="font-semibold"), " task IDs injected into vault"),
        Li(Span(f"{done}", cls="font-semibold"), " tasks marked done in vault"),
    ]
    if moved:
        items.append(
            Li(
                Span(f"{moved}", cls="font-semibold"),
                " renamed/moved notes recognized (identity preserved)",
            )
        )
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


def _preview_error_fragment(message: str) -> Div:
    """Fragment shown when the dry-run preview fails."""
    return Div(
        P(f"Preview failed: {message}", cls="text-error text-sm"),
        _preview_button("Try preview again"),
        id="vault-results",
        cls="space-y-3",
    )


def _example_list(examples: tuple[str, ...], total: int) -> Any:
    """Render up to the preview's example paths, noting how many are unlisted."""
    if not examples:
        return Span()
    items = [Li(Span(example, cls="font-mono text-xs")) for example in examples]
    if total > len(examples):
        items.append(Li(f"… and {total - len(examples)} more", cls="text-xs italic"))
    return Ul(*items, cls="list-disc pl-6 space-y-0.5 text-base-content/70")


def _preview_fragment(preview: VaultSyncPreview) -> Div:
    """Dry-run report: what a sync WOULD do — nothing has been written yet."""
    items: list[Any] = [
        Li(
            "ingest ",
            Span(f"{preview.would_ingest_count}", cls="font-semibold"),
            f" notes ({preview.would_ingest_new} new, {preview.would_ingest_changed} changed)",
            _example_list(preview.would_ingest_examples, preview.would_ingest_count),
        ),
        Li(
            "delete ",
            Span(f"{preview.would_delete_entities}", cls="font-semibold"),
            " entities",
            _example_list(preview.would_delete_entity_examples, preview.would_delete_entities),
        ),
    ]
    if preview.would_delete_edges:
        items.append(
            Li(
                "delete ",
                Span(f"{preview.would_delete_edges}", cls="font-semibold"),
                " relationships (edge files)",
                _example_list(preview.would_delete_edge_examples, preview.would_delete_edges),
            )
        )
    if preview.stale_cleanup_count:
        items.append(
            Li(
                "clean ",
                Span(f"{preview.stale_cleanup_count}", cls="font-semibold"),
                " moved-file tracking rows",
            )
        )

    warnings = list(preview.ownership_mismatches)
    if preview.refusal_warning:
        warnings.append(preview.refusal_warning)
    warning_section = (
        Div(
            H3("Warnings", cls="text-sm font-semibold text-warning mt-3 mb-1"),
            Ul(*[Li(w, cls="text-xs text-warning") for w in warnings], cls="list-disc pl-4"),
        )
        if warnings
        else Span()
    )

    # A zero-count preview is only "in sync" when there are no warnings —
    # a refused mass deletion or an ownership mismatch must never hide
    # behind a harmless-sounding header (Kody #527).
    nothing_to_do = (
        not preview.would_ingest_count
        and not preview.would_delete_entities
        and not preview.would_delete_edges
        and not preview.stale_cleanup_count
        and not warnings
    )
    header = (
        H3("Preview — nothing has been changed", cls="text-base font-semibold mb-2")
        if not warnings
        else H3(
            f"Preview — {len(warnings)} warning(s), nothing has been changed",
            cls="text-base font-semibold text-warning mb-2",
        )
    )
    return Div(
        Div(
            header,
            P("This vault is already in sync — a sync would do nothing.", cls="text-sm")
            if nothing_to_do
            else Ul(
                Li("This sync would:", cls="list-none -ml-4 font-medium"),
                *items,
                cls="list-disc pl-4 text-sm text-base-content/80 space-y-1",
            ),
            warning_section,
            cls="bg-base-200 border border-base-300 rounded-lg p-5",
        ),
        Div(
            _sync_button("Run sync now"),
            _preview_button("Preview again"),
            cls="flex items-center gap-4",
        ),
        id="vault-results",
        cls="space-y-4",
    )


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
                _privacy_wall_panel(description),
                Div(
                    _sync_button(),
                    _preview_button(),
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
            return _consent_form(await _describe_personal_vault(user_uid))

        await _ground_after_sync(user_uid)
        return _sync_stats_fragment(asdict(stats))

    @rt("/settings/vault/preview", methods=["POST"])
    @csrf_protected
    async def vault_preview_htmx(request: Request) -> Any:
        """HTMX endpoint: dry-run preview — reports what a sync WOULD do, writes nothing."""
        user_uid = require_authenticated_user(request)

        result = await vault_reconciler.preview(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return _preview_error_fragment(str(result.expect_error()))

        preview = result.value
        if preview.first_run_notice:
            # Consent covers reading too (ADR-070 Decision 6 amendment) —
            # preview compares vault files, so it engages the same gate.
            # Consent granted from HERE continues into a PREVIEW, never a
            # real sync — the user asked to see, not to run (Kody #527).
            return _consent_form(
                await _describe_personal_vault(user_uid),
                post_to="/settings/vault/preview/consent",
                button_label="Allow and preview",
            )

        return _preview_fragment(preview)

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
            return _preview_error_fragment(str(consent_result.expect_error()))

        result = await vault_reconciler.preview(VaultKind.PERSONAL, user_uid)
        if result.is_error:
            return _preview_error_fragment(str(result.expect_error()))

        return _preview_fragment(result.value)

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

        await _ground_after_sync(user_uid)
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
