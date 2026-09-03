#!/usr/bin/env python3
"""Run a full VaultBridge sync for a vault, in-process (no HTTP/login needed).

Composes the app's services and invokes the exact reconciler that
``POST /api/vault/sync`` runs — but as any ``--user`` you name, without needing
that user's password, and against either vault. Useful for admin-triggered /
scripted syncs and for backfilling after a vault reorganization.

Two vaults (``--vault``):
  - ``personal`` (default): a user's Obsidian vault (VAULT_ROOT). Bidirectional —
    requires ``--user``; the entries are OWNED by that user.
  - ``content``: the admin curriculum vault (INGESTION_PATH). Owned by the fixed
    content-vault admin account; ``--user`` is ignored. Inbound-only today
    (curriculum has no checkbox round-trip).

What it does (VaultReconciler.sync, ADR-070):
  1. Consent gate (personal vaults): if the vault owner has not granted
     ``vault_write_consent``, stops BEFORE any read and reports
     ``first_run_notice`` (nothing ingested, nothing written).
  2. Inbound: ingest the vault in ``smart`` mode, scoped by that vault's own
     fail-closed allowlist.
  3. Outbound (personal only): inject ``🆔 sk_`` IDs into periodic-note
     tasks that lack them and write ``[x]``/``✅`` for SKUEL-completed ones.

``--force`` re-processes unchanged files too (re-chunk/migration campaigns) while
keeping smart-mode semantics — the wall, metadata re-stamping, and deletion
reconciliation all stay active (force ≠ full).

``--preview`` is the dry run: ``VaultReconciler.preview`` — the same read-only
report the personal "Preview sync" button renders — printed and nothing
written. What a sync WOULD ingest (new / changed, with the ingest gate's
no-type verdict applied so loose untyped notes are one set-aside count rather
than hundreds of "new" files), what deletion reconciliation WOULD remove, stale
tracking rows, ownership mismatches, and any mass-deletion refusal. No
embedding worker, no drain, no grounding pass — there is nothing to drain. This
is the one-liner for "will my vault deletion propagate?" before a sync.

Embedding freshness (ADR-074): the embedding worker is subscribed BEFORE the
sync and its queues are drained in-process afterwards, so the sync's embedding
events (entity + chunk) are processed right here instead of evaporating with
the script — same event path as the app process, no follow-up commands. In
CORE tier there is no worker and ingestion publishes no events, so the drain
step is skipped and this sync's new content is stored without embeddings
(``./dev embed-backfill`` under FULL tier fills the gap). A FULL-tier run
re-probes coverage AFTER the drain so the printed figures are post-drain.

Grounding (Entry-Enrichment PR 3): after the drain, personal-vault syncs run
an entry→Ku grounding pass over pending ``pipeline: knowledge`` entries —
because the drain just stored their embeddings, this sync's entries ground
immediately. ``scripts/ground_knowledge_entries.py`` is the backfill/dry-run
counterpart.

Usage:
    uv run scripts/vault_bridge_sync.py --user <user_uid>            # personal
    uv run scripts/vault_bridge_sync.py --vault content              # content
    uv run scripts/vault_bridge_sync.py --vault content --force      # re-ingest all
    uv run scripts/vault_bridge_sync.py --vault content --preview    # dry run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.services.vault.vault_descriptor import VaultKind
    from core.services.vault.vault_reconciler import VaultReconciler
    from services_bootstrap import Services


def _vault_kind(vault: str) -> VaultKind:
    from core.services.vault.vault_descriptor import VaultKind

    return VaultKind.CONTENT if vault == "content" else VaultKind.PERSONAL


async def _compose(adapter: Neo4jAdapter) -> tuple[Services, VaultReconciler] | None:
    """Compose the app's services around ``adapter``; ``None`` (already reported) on failure."""
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from services_bootstrap import compose_services

    composed = await compose_services(adapter, InMemoryEventBus())
    if composed.is_error:
        print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
        return None
    reconciler = composed.value.vault_reconciler
    if reconciler is None:
        print("ERROR: vault_reconciler is not wired (check ADR-070 config)", file=sys.stderr)
        return None
    return composed.value, reconciler


async def run_sync(vault: str, user_uid: str, force: bool = False) -> int:
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.type_hints import UserUID
    from core.services.vault.vault_descriptor import VaultKind

    kind = _vault_kind(vault)

    print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await _compose(adapter)
        if composed is None:
            return 1
        services, reconciler = composed

        # Subscribe the embedding worker BEFORE the sync so the ingest's
        # *EmbeddingRequested / ChunkEmbeddingRequested publishes land in its
        # queues; drain() after persistence processes them in-process
        # (ADR-074 script-mode freshness). None = CORE tier / no API key —
        # ingestion publishes no events, nothing to drain.
        worker = services.embedding_worker
        if worker is not None:
            worker.subscribe()

        forced = " [FORCE — re-processing unchanged files]" if force else ""
        print(f"Full VaultBridge sync ({kind.value}) as {user_uid}{forced} ...")
        result = await reconciler.sync(kind, UserUID(user_uid), force=force)

        # Drain BEFORE the error check: sync() can fail after ingest persisted
        # entities (e.g. the consent-gate user lookup), and their already-queued
        # embedding events must not evaporate with the script — the exact drift
        # this drain step exists to prevent. No-op when nothing was queued.
        if worker is not None:
            print("\nDraining embedding events in-process ...")
            drained = await worker.drain()
            print(
                f"  entity embedding requests dequeued: {drained['entity_requests']}"
                " (includes retry passes)"
            )
            print(f"  chunk parents dequeued: {drained['chunk_parents']} (includes retry passes)")
        else:
            print(
                "\n(no embedding worker — CORE tier: this sync's new content is stored"
                "\n without embeddings and is not yet vector-searchable; run"
                "\n ./dev embed-backfill under FULL tier to fill the gap)"
            )

        if result.is_error:
            print(f"ERROR: sync failed: {result.expect_error()}", file=sys.stderr)
            return 1

        # Post-sync grounding pass (Entry-Enrichment PR 3): the drain above
        # just stored this sync's UserEntry embeddings in-process, so unlike
        # the app-process route doors this pass grounds THIS sync's entries
        # immediately. Personal vaults only — the content vault has no
        # UserEntries. Fail-soft: a grounding problem never fails the sync.
        if kind is VaultKind.PERSONAL:
            grounding = services.entry_grounding
            if grounding is not None:
                print("\nGrounding knowledge entries (post-sync pass) ...")
                grounded = await grounding.ground_pending(UserUID(user_uid))
                if grounded.is_error:
                    print(f"WARNING: grounding pass failed: {grounded.expect_error()}")
                else:
                    report = grounded.value
                    print(
                        f"  entries scanned: {report.entries_scanned}, "
                        f"edges written: {report.edges_written}, "
                        f"failed: {report.entries_failed} "
                        f"(judge={'on' if report.judged else 'off'})"
                    )

        stats = result.value
        print("\n=== VaultSyncStats ===")
        for key, value in asdict(stats).items():
            if key == "ignored":
                continue  # rendered line-by-line below (9 reasons in one list is unreadable)
            print(f"  {key}: {value}")

        # The retrievability figures above were measured INSIDE sync(), i.e.
        # BEFORE the in-process drain embedded this sync's content — without a
        # re-probe this report would claim missing coverage the drain already
        # filled. Only when a worker drained and the stats carry a gap
        # (personal syncs carry only the delta — absolutes are content-only).
        gauge = reconciler.embedding_coverage
        if (
            worker is not None
            and gauge is not None
            and (
                stats.retrievability_delta
                or stats.chunks_awaiting_embedding
                or stats.entities_awaiting_embedding
            )
        ):
            coverage = await gauge.measure_embedding_coverage()
            if coverage.is_ok:
                cov = coverage.value
                print(
                    f"\n  post-drain coverage: {cov.missing} node(s) still missing embeddings"
                    f" corpus-wide ({cov.missing_chunks} chunks, {cov.missing_entities}"
                    " entities) — the retrievability figures above are pre-drain"
                )
            else:
                print(
                    "\n  (post-drain coverage re-probe failed — the retrievability figures"
                    " above are pre-drain; ./dev knowledge-health for current coverage)"
                )
        if stats.ignored:
            print(f"\nIgnored files ({len(stats.ignored)}) — content not ingestible; fix or leave:")
            for line in stats.ignored:
                print(f"  - {line}")
        if stats.first_run_notice:
            print("\nNOTE: first_run_notice — the vault owner has not granted")
            print("      vault_write_consent; nothing was ingested or written.")
        return 0
    finally:
        await adapter.close()


def _print_examples(examples: tuple[str, ...], total: int) -> None:
    """The preview's vault-relative example paths, noting how many are unlisted."""
    for example in examples:
        print(f"    - {example}")
    if total > len(examples):
        print(f"    … and {total - len(examples)} more")


async def run_preview(vault: str, user_uid: str) -> int:
    """Dry run: print what a sync of ``vault`` WOULD do. Nothing is written."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.type_hints import UserUID

    kind = _vault_kind(vault)

    print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await _compose(adapter)
        if composed is None:
            return 1
        _services, reconciler = composed

        print(
            f"VaultBridge sync PREVIEW ({kind.value}) as {user_uid} — dry run, nothing written ..."
        )
        result = await reconciler.preview(kind, UserUID(user_uid))
        if result.is_error:
            print(f"ERROR: preview failed: {result.expect_error()}", file=sys.stderr)
            return 1
        preview = result.value
        if preview.first_run_notice:
            print("\nNOTE: first_run_notice — the vault owner has not granted")
            print("      vault_write_consent; the vault was not read.")
            return 0

        print("\n=== VaultSyncPreview ===")
        print(
            f"  would ingest: {preview.would_ingest_count} "
            f"({preview.would_ingest_new} new, {preview.would_ingest_changed} changed)"
        )
        _print_examples(preview.would_ingest_examples, preview.would_ingest_count)
        print(f"  set aside (no 'type:' field — not ingestible): {preview.non_entity_notes}")
        print(f"  would delete entities: {preview.would_delete_entities}")
        _print_examples(preview.would_delete_entity_examples, preview.would_delete_entities)
        print(f"  would delete relationships (edge files): {preview.would_delete_edges}")
        _print_examples(preview.would_delete_edge_examples, preview.would_delete_edges)
        print(f"  stale tracking rows to clean: {preview.stale_cleanup_count}")
        if preview.ownership_mismatches:
            print(f"  ownership mismatches ({len(preview.ownership_mismatches)}) — never deleted:")
            for line in preview.ownership_mismatches:
                print(f"    - {line}")
        if preview.refusal_warning:
            print(f"\nWARNING: {preview.refusal_warning}")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a full VaultBridge sync for a vault.")
    parser.add_argument(
        "--vault",
        choices=("personal", "content"),
        default="personal",
        help="Which vault to sync (default: personal)",
    )
    parser.add_argument(
        "--user",
        help="user_uid to sync as (required for --vault personal; ignored for content)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-process unchanged files too (re-chunk/migration campaigns); "
        "deletion reconciliation and the vault wall stay active. Embeddings "
        "refresh in-process via the post-sync drain (FULL tier).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="dry run: print what a sync WOULD ingest (untyped notes set aside as one "
        "count) and what deletion reconciliation WOULD remove; nothing is written, "
        "no embeddings are touched. Not combinable with --force (a sync knob).",
    )
    args = parser.parse_args()

    if args.vault == "personal" and not args.user:
        parser.error("--user is required for --vault personal")
    if args.preview and args.force:
        parser.error("--preview is a dry run and --force is a sync knob — pick one")

    # For content, the reconciler uses the fixed content-vault owner; the passed
    # user is ignored, so any placeholder is fine.
    user = args.user or "user:system"
    if args.preview:
        sys.exit(asyncio.run(run_preview(args.vault, user)))
    sys.exit(asyncio.run(run_sync(args.vault, user, force=args.force)))


if __name__ == "__main__":
    main()
