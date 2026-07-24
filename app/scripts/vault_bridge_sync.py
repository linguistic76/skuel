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

Embedding freshness (ADR-074): the embedding worker is subscribed BEFORE the
sync and its queues are drained in-process afterwards, so the sync's embedding
events (entity + chunk) are processed right here instead of evaporating with
the script — same event path as the app process, no follow-up commands. In
CORE tier (or with no API key) there is no worker and ingestion publishes no
events, so the drain step is skipped. ``scripts/generate_embeddings_batch.py
[--stale]`` remains the backstop for pre-existing coverage gaps or drift, not
a required follow-up to this script.

Grounding (Entry-Enrichment PR 3): after the drain, personal-vault syncs run
an entry→Ku grounding pass over pending ``pipeline: knowledge`` entries —
because the drain just stored their embeddings, this sync's entries ground
immediately. ``scripts/ground_knowledge_entries.py`` is the backfill/dry-run
counterpart.

Usage:
    uv run scripts/vault_bridge_sync.py --user <user_uid>          # personal
    uv run scripts/vault_bridge_sync.py --vault content            # content
    uv run scripts/vault_bridge_sync.py --vault content --force    # re-ingest all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict


async def run_sync(vault: str, user_uid: str, force: bool = False) -> int:
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.type_hints import UserUID
    from core.services.vault.vault_descriptor import VaultKind
    from services_bootstrap import compose_services

    kind = VaultKind.CONTENT if vault == "content" else VaultKind.PERSONAL

    print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1

        reconciler = composed.value.vault_reconciler
        if reconciler is None:
            print("ERROR: vault_reconciler is not wired (check ADR-070 config)", file=sys.stderr)
            return 1

        # Subscribe the embedding worker BEFORE the sync so the ingest's
        # *EmbeddingRequested / ChunkEmbeddingRequested publishes land in its
        # queues; drain() after persistence processes them in-process
        # (ADR-074 script-mode freshness). None = CORE tier / no API key —
        # ingestion publishes no events, nothing to drain.
        worker = composed.value.embedding_worker
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
            print("\n(no embedding worker — CORE tier or embeddings unavailable; skipped drain)")

        if result.is_error:
            print(f"ERROR: sync failed: {result.expect_error()}", file=sys.stderr)
            return 1

        # Post-sync grounding pass (Entry-Enrichment PR 3): the drain above
        # just stored this sync's UserEntry embeddings in-process, so unlike
        # the app-process route doors this pass grounds THIS sync's entries
        # immediately. Personal vaults only — the content vault has no
        # UserEntries. Fail-soft: a grounding problem never fails the sync.
        if kind is VaultKind.PERSONAL:
            grounding = composed.value.entry_grounding
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
    args = parser.parse_args()

    if args.vault == "personal" and not args.user:
        parser.error("--user is required for --vault personal")

    # For content, the reconciler uses the fixed content-vault owner; the passed
    # user is ignored, so any placeholder is fine.
    user = args.user or "user:system"
    sys.exit(asyncio.run(run_sync(args.vault, user, force=args.force)))


if __name__ == "__main__":
    main()
