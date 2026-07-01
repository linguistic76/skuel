#!/usr/bin/env python3
"""Run a full VaultBridge sync for a user, in-process (no HTTP/login needed).

Composes the app's services and invokes the exact reconciler that
``POST /api/vault/sync`` runs — but as any ``--user`` you name, without needing
that user's password. Useful for admin-triggered / scripted personal-vault syncs
and for backfilling after a vault reorganization.

What it does (VaultReconciler.sync, ADR-070):
  1. Inbound: ingest the personal vault (VAULT_ROOT) in ``smart`` mode, scoped by
     the fail-closed SyncAllowlist (``SKUEL_VAULT_SYNC_ALLOWED_DIRS``). New/changed
     allowlisted notes become UserEntry nodes OWNED by ``--user``.
  2. Consent gate: if the user has not granted ``vault_write_consent``, stops after
     inbound and reports ``first_run_notice`` (no outbound writes).
  3. Outbound (consented only): inject ``🆔 sk_`` IDs into periodic-note tasks that
     lack them and write ``[x]``/``✅`` for SKUEL-completed ones. Idempotent.

⚠️  Allowlist gotcha: the SyncAllowlist reads ``SKUEL_VAULT_SYNC_ALLOWED_DIRS`` from
the process environment, and python-dotenv does NOT override an already-exported
var. If a stale export shadows your ``.env`` value, a folder you expect to sync will
be silently walled off. Pass the intended value inline to be sure, e.g.:

    SKUEL_VAULT_SYNC_ALLOWED_DIRS="$VAULT/periodic_notes:$VAULT/knowledge" \
        uv run scripts/vault_bridge_sync.py --user user_linguistic76

Usage:
    uv run scripts/vault_bridge_sync.py --user <user_uid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict


async def run_sync(user_uid: str) -> int:
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from services_bootstrap import compose_services

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

        vault_path = str(reconciler.vault_root)
        print(f"Full VaultBridge sync for {user_uid} on {vault_path} ...")
        result = await reconciler.sync(user_uid=user_uid, vault_path=vault_path)
        if result.is_error:
            print(f"ERROR: sync failed: {result.expect_error()}", file=sys.stderr)
            return 1

        stats = result.value
        print("\n=== VaultSyncStats ===")
        for key, value in asdict(stats).items():
            print(f"  {key}: {value}")
        if stats.first_run_notice:
            print("\nNOTE: first_run_notice — user has not granted vault_write_consent;")
            print("      inbound ingest ran, outbound writeback was skipped.")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a full VaultBridge sync for a user.")
    parser.add_argument("--user", required=True, help="user_uid to sync as (owns the entries)")
    args = parser.parse_args()
    sys.exit(asyncio.run(run_sync(args.user)))


if __name__ == "__main__":
    main()
