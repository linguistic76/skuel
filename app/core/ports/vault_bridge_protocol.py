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
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Annotation-only (this module keeps a stdlib-only RUNTIME dependency chain
    # so the PEP 723 vault agent can import the line-mutation contract).
    from core.utils.result_simplified import Result

# ============================================================================
# VAULT-LINE NORMALIZATION CONTRACT (ADR-070 Decision 1 + Decision 4)
# ============================================================================
# Single definition used by all the sites that must agree on line identity:
#   - obsidian_tasks_adapter  (produces source_line_hash stored on EXTRACTED_FROM)
#   - VaultReconciler         (looks up lines by hash for ID injection)
#   - FilesystemVaultAdapter  (targets the right line inside apply_inject_id)
#   - agent/skuel_vault_agent (applies the SAME mutations on the user's device,
#     ADR-075 B3 — this module is deliberately importable with a stdlib-only
#     dependency chain so the PEP 723 agent can share it)
#
# A divergence here silently injects IDs into the wrong lines — keep it here.

VAULT_ID_RE = re.compile(r"🆔️?\s*([\w-]{1,20})")
"""Matches the obsidian-tasks 🆔 ID token (ADR-070 Decision 1).

The optional ``️`` is a Unicode variation selector some editors append.
"""


def normalize_vault_line_hash(line: str) -> str:
    """Stable hash for a vault task line used as ``source_line_hash`` on EXTRACTED_FROM edges.

    Normalizes the checkbox prefix to ``- [ ] ``, strips the 🆔 token so
    the hash is stable across ID injection, then sha256s the
    whitespace-collapsed result.
    """
    line = re.sub(r"^[-*]\s*\[[xX]\]\s*", "- [ ] ", line)
    line = re.sub(r"^[-*]\s*\[\s*\]\s*", "- [ ] ", line)
    line = VAULT_ID_RE.sub("", line)
    return hashlib.sha256(" ".join(line.split()).encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class VaultFileStat:
    """One row of a remote vault listing (ADR-075 ``list_changed_since``).

    ``relative_path`` is vault-relative POSIX (the only path shape that crosses
    the wire); ``sha256`` is the bare hex content hash (wire ``content_hash``
    with its ``sha256:`` prefix stripped).
    """

    relative_path: str
    sha256: str


@dataclass(frozen=True)
class VaultListing:
    """A full remote-vault listing: presence + content hashes (ADR-075 Decision 3).

    ``state`` is the agent's opaque cursor — unused in v1 (deletion
    reconciliation needs the full-presence listing), carried so a future
    delta-plus-tombstones optimization is a protocol no-op.
    """

    files: tuple[VaultFileStat, ...]
    state: str


@dataclass(frozen=True)
class AgentWall:
    """The agent's self-reported privacy wall (ADR-075 ``describe_wall``).

    Keeps the server-side "What SKUEL can see" panel honest about what a sync
    can actually reach — the effective wall is the intersection of this and
    the server-side descriptor allowlist (ADR-075 Decision 5).
    """

    allowed_folders: tuple[str, ...]
    agent_version: str


@dataclass
class VaultSyncStats:
    """Aggregate results of a VaultReconciler.sync() call.

    Honest by construction (G10): ingestion failures, dangling-target
    warnings, and skip reasons all survive into this object — a sync door
    may only say "complete" when ``is_clean`` is True.
    """

    entries_ingested: int = 0
    ids_injected: int = 0
    tasks_marked_done: int = 0
    # Inbound ingestion outcome (carried from IngestionStats/IncrementalStats)
    files_failed: int = 0
    files_walled: int = 0
    files_unsupported: int = 0
    entities_deleted: int = 0
    edges_deleted: int = 0
    # Content-hash move detection: uid-less renames whose identity survived
    # (tracker row rewritten in place — not a delete + a create).
    moves_detected: int = 0
    moves: list[str] = field(default_factory=list)  # vault-relative "old → new" lines
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    first_run_notice: bool = False

    @property
    def is_clean(self) -> bool:
        """No failures and no surfaced warnings — the only 'Sync complete' state."""
        return not self.errors and not self.warnings and self.files_failed == 0


# ============================================================================
# LINE-LEVEL MUTATIONS (pure functions — ADR-070 Decision 4)
# ============================================================================
# The outbound write operations, shared by BOTH transports (One Path Forward):
# FilesystemVaultAdapter (Stage 1, server-local) and the user-side vault agent
# (ADR-075 B3, device-local) apply the exact same mutations, so 🆔 injection
# and done-toggling behave byte-identically wherever the vault lives.

# Checkbox detection
_UNCHECKED_RE = re.compile(r"^([-*]\s*\[)\s*(\])")
_CHECKED_RE = re.compile(r"^[-*]\s*\[[xX]\]")
# Done-date token: ✅ YYYY-MM-DD
_DONE_DATE_RE = re.compile(r"✅️?\s*\d{4}-\d{2}-\d{2}")


def apply_mark_done(lines: list[str], vault_id: str, done_date: str) -> tuple[list[str], bool]:
    """Toggle the line with ``🆔 vault_id`` from ``[ ]`` to ``[x]`` and append ``✅ date``.

    Idempotent only when BOTH the checkbox is already ``[x]`` AND the ``✅ date`` token is
    present.  An already-checked line that is missing the done-date (e.g. checked directly
    in Obsidian without the tasks plugin) still receives the token so SKUEL and the vault
    stay in sync.
    """
    for i, line in enumerate(lines):
        m = VAULT_ID_RE.search(line)
        if not m or m.group(1) != vault_id:
            continue
        checked = bool(_CHECKED_RE.match(line))
        if not checked and not _UNCHECKED_RE.match(line):
            return lines, False

        # True no-op: already checked AND already has a done-date
        if checked and _DONE_DATE_RE.search(line):
            return lines, False

        # Flip checkbox if needed
        if not checked:
            line = re.sub(r"^([-*]\s*)\[\s*\]", r"\1[x]", line)

        # Append ✅ date if still absent
        if not _DONE_DATE_RE.search(line):
            stripped = line.rstrip("\n")
            eol = line[len(stripped) :]
            line = f"{stripped} ✅ {done_date}{eol}"

        lines[i] = line
        return lines, True
    return lines, False


def apply_inject_id(
    lines: list[str], vault_id: str, source_line_hash: str | None
) -> tuple[list[str], bool]:
    """Find the target checkbox line and append ``🆔 <vault_id>``.

    When ``source_line_hash`` is provided, finds the line whose normalized hash
    matches — guaranteeing the right line is targeted even when multiple tasks
    in the same file lack an ID.  Falls back to the first ID-less checkbox line
    when no hash is provided.
    """
    for i, line in enumerate(lines):
        if not (_UNCHECKED_RE.match(line) or _CHECKED_RE.match(line)):
            continue
        if VAULT_ID_RE.search(line):
            continue  # Already has a 🆔
        if source_line_hash is not None and normalize_vault_line_hash(line) != source_line_hash:
            continue
        stripped = line.rstrip("\n")
        eol = line[len(stripped) :]
        lines[i] = f"{stripped} 🆔 {vault_id}{eol}"
        return lines, True
    return lines, False


def apply_task_updates(content: str, updates: list[TaskLineUpdate]) -> tuple[str, bool]:
    """Apply a batch of task-line updates to note content; pure — no I/O.

    Returns ``(new_content, modified)``.  Both transports wrap this with the
    same SHA-256 stale-read guard and atomic temp-file + ``rename()`` write.
    """
    lines = content.splitlines(keepends=True)
    modified = False
    for update in updates:
        if update.mark_done:
            lines, changed = apply_mark_done(lines, update.vault_id, update.done_date or "")
        elif update.inject_vault_id:
            lines, changed = apply_inject_id(lines, update.vault_id, update.source_line_hash)
        else:
            changed = False
        if changed:
            modified = True
    return "".join(lines), modified


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
        """Return vault-RELATIVE POSIX paths of notes matching ``pattern``.

        ``vault_path`` scopes the listing to a subdirectory (``""``/``"."`` for
        the whole vault); returned paths are relative to the VAULT ROOT, not to
        ``vault_path``. Harmonized to vault-relative for all adapters in
        ADR-075 B4 (One Path Forward — #525 made relative the only path shape
        that leaves the service layer, and wire paths are structurally
        relative).
        """
        ...


class RemoteVaultBridgePort(VaultBridgePort, Protocol):
    """A ``VaultBridgePort`` whose vault lives on a remote device (ADR-075).

    Adds the two sync-metadata operations the server-side mirror pull needs
    (`VaultMirrorPuller`, ADR-075 Decision 4). The filesystem transport
    deliberately does NOT implement this: it has no self-reported wall (the
    server-side allowlist IS its wall) and the ingest engine walks its root
    directly — a filesystem ``describe_wall`` would fabricate honesty.
    """

    async def list_changed_since(
        self, user_uid: str, since_state: str | None = None
    ) -> Result[VaultListing]:
        """Full listing of the remote vault's allowed files (presence + hashes).

        ``since_state=None`` (always, in v1) requests the complete listing —
        absence from it is the mirror's deletion signal. Fails with an
        integration error when no agent is connected for ``user_uid``.
        """
        ...

    async def describe_wall(self, user_uid: str) -> Result[AgentWall]:
        """The agent's self-reported allowed folders + version (honesty check).

        Exchanges no vault content — folder names are the pre-consent maximum
        (ADR-075 Decision 5). Fails with an integration error when no agent is
        connected.
        """
        ...
