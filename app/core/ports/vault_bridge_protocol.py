"""
VaultBridgePort — ADR-070
=========================

Protocol for the bidirectional Obsidian ↔ SKUEL vault bridge.  All identity,
change-detection, reconciliation, and conflict logic lives in ``core/`` behind
this protocol.  The transport (local filesystem vs. secure local-agent) is an
interchangeable adapter in ``adapters/vault/``.

Stage 1 uses ``FilesystemVaultAdapter`` (direct file I/O, local Docker).
Stage 2+ swaps in ``LocalAgentVaultAdapter`` (encrypted outbound-only channel)
with zero changes to ``core/``.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass(frozen=True)
class NoteSnapshot:
    """Point-in-time snapshot of a vault markdown file."""

    path: str
    content: str
    sha256: str

    @classmethod
    def from_content(cls, path: str, content: str) -> NoteSnapshot:
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(path=path, content=content, sha256=sha)


@dataclass(frozen=True)
class TaskLineUpdate:
    """An outbound write operation targeting one task line in a vault file.

    Exactly one of ``mark_done`` / ``inject_vault_id`` must be set.

    For ``inject_vault_id=True``, ``source_line_hash`` is the normalized
    sha-256 of the target line (obsidian-tasks adapter hash, 🆔-stripped) so
    the adapter can find the right line when multiple tasks need injection.

    For ``mark_done=True``, ``vault_id`` is the locator (line already has 🆔).
    """

    vault_id: str
    mark_done: bool = False
    done_date: str | None = None  # YYYY-MM-DD when mark_done=True
    inject_vault_id: bool = False  # Write ``🆔 <vault_id>`` to an ID-less line
    source_line_hash: str | None = None  # Required when inject_vault_id=True


@dataclass
class WriteResult:
    """Outcome of a vault write operation."""

    success: bool
    new_sha256: str | None = None
    error: str | None = None


@dataclass
class VaultSyncStats:
    """Aggregate results of a VaultReconciler.sync() call."""

    entries_ingested: int = 0
    tasks_extracted: int = 0
    ids_injected: int = 0
    tasks_marked_done: int = 0
    errors: list[str] = field(default_factory=list)


# ============================================================================
# PROTOCOL
# ============================================================================


class VaultBridgePort(Protocol):
    """Transport-agnostic interface for vault read/write operations.

    All methods are per-user so the port is multi-tenant from day one, even
    though Stage 1 only serves a single local user (ADR-070 Decision 5).
    """

    async def read_note(self, user_uid: str, path: str) -> NoteSnapshot:
        """Read the current content of a vault note, returning a snapshot with SHA-256."""
        ...

    async def write_task_updates(
        self,
        user_uid: str,
        path: str,
        updates: list[TaskLineUpdate],
        expected_sha256: str,
    ) -> WriteResult:
        """Apply a batch of outbound task-line writes to a vault file.

        ``expected_sha256`` is the hash from the last-known NoteSnapshot.  The
        adapter re-reads the file, computes the current hash, and aborts if
        they differ (stale-read guard — ADR-070 Decision 4).

        Writes are atomic (POSIX ``rename()``); the file is either fully
        replaced or untouched.
        """
        ...

    async def list_vault_notes(
        self, user_uid: str, vault_path: str, pattern: str = "**/*.md"
    ) -> list[str]:
        """Return absolute paths of markdown notes in the vault matching the pattern."""
        ...
