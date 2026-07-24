"""Vault Sync Fragments — ADR-070
================================

FT fragment builders for the Obsidian vault sync page (/submissions/sync)
and its HTMX endpoints: sync/preview trigger buttons, the privacy wall,
the first-run consent form, and the post-run stats/preview/error fragments.

Route wiring lives in adapters/inbound/vault_routes.py; these builders are
pure presentation over core vault models (VaultDescription, VaultSyncPreview).

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import (
    H3,
    Div,
    Form,
    Li,
    P,
    Span,
    Ul,
)

from core.services.vault.vault_reconciler import VaultDescription, VaultSyncPreview
from ui.components import Button, ButtonT, Loading


def sync_button(label: str = "Sync from Obsidian", spinner_id: str = "vault-spinner") -> Form:
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


def preview_button(label: str = "Preview sync", spinner_id: str = "vault-preview-spinner") -> Form:
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


def privacy_wall_panel(description: VaultDescription) -> Div:
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


def consent_form(
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


def sync_stats_fragment(stats_dict: dict[str, Any]) -> Div:
    """Fragment shown after a sync ran.

    "Sync complete" ONLY when the run was clean (G10) — failed files,
    ingestion errors, and dangling-target warnings flip the header and are
    listed in full, never hidden behind a success banner. Ignored files
    (content-caused: no ``type:``, malformed frontmatter) list with their
    reasons but do NOT flip the header — a sync whose only findings are
    ignored files is complete (2026-07-23 ruling).
    """
    ingested = stats_dict.get("entries_ingested", 0)
    injected = stats_dict.get("ids_injected", 0)
    done = stats_dict.get("tasks_marked_done", 0)
    failed = stats_dict.get("files_failed", 0)
    walled = stats_dict.get("files_walled", 0)
    unsupported = stats_dict.get("files_unsupported", 0)
    moved = stats_dict.get("moves_detected", 0)
    ignored: list[str] = stats_dict.get("ignored", [])
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
    if ignored:
        items.append(
            Li(
                Span(f"{len(ignored)}", cls="font-semibold"),
                " files ignored (not ingestible — see list below)",
            )
        )
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
    # Neutral styling on purpose: ignored files are information, not a
    # problem state — the reasons say which are deliberate non-entity notes
    # and which declared a type the author probably wants to fix.
    ignored_section = (
        Div(
            H3(
                "Ignored files (not ingested)",
                cls="text-sm font-semibold text-base-content/70 mt-3 mb-1",
            ),
            Ul(
                *[Li(line, cls="text-xs text-base-content/60") for line in ignored],
                cls="list-disc pl-4",
            ),
        )
        if ignored
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
            ignored_section,
            cls="bg-base-200 border border-base-300 rounded-lg p-5",
        ),
        sync_button("Sync again"),
        id="vault-results",
        cls="space-y-4",
    )


def sync_error_fragment(message: str) -> Div:
    """Fragment shown when sync fails."""
    return Div(
        P(f"Sync failed: {message}", cls="text-error text-sm"),
        sync_button("Try again"),
        id="vault-results",
        cls="space-y-3",
    )


def preview_error_fragment(message: str) -> Div:
    """Fragment shown when the dry-run preview fails."""
    return Div(
        P(f"Preview failed: {message}", cls="text-error text-sm"),
        preview_button("Try preview again"),
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


def preview_fragment(preview: VaultSyncPreview) -> Div:
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
            sync_button("Run sync now"),
            preview_button("Preview again"),
            cls="flex items-center gap-4",
        ),
        id="vault-results",
        cls="space-y-4",
    )
