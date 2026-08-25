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
#
# The digest is also part of the local_agent WIRE PROTOCOL (ADR-075): the agent
# reproduces the server's ``source_line_hash`` ON THE DEVICE to find the line
# to inject into, so any change to what this digest ignores is a protocol
# change — bump ``PROTOCOL_VERSION`` on both sides (``device_routes.py`` and
# the agent, parity contract-tested) so a stale agent refuses at handshake
# instead of silently missing its target while the reconciler persists the
# minted 🆔. No compatibility shim: the user updates the agent by pulling.
#
# So is the shape of the write-result frame: ``WriteResult.updates_applied``
# (protocol v2) is the per-update outcome the agent must report back, and it
# reads fail-closed — an agent that cannot report it would leave every 🆔
# injection unpersisted rather than guess. The handshake mismatch is what
# stops that from ever being reached.
#
# So is the SET of operations ``TaskLineUpdate`` can carry: v3 added
# ``mark_undone``. A stale agent parses only the flags it knows, so it would
# build an update with NO operation set, apply nothing, and answer
# ``success: True`` — the server would believe the un-check landed. The
# handshake refusal is what turns that silent divergence into a loud one.

VAULT_ID_RE = re.compile(r"🆔️?\s*([\w-]{1,20})")
"""Matches the obsidian-tasks 🆔 ID token (ADR-070 Decision 1).

The optional ``️`` is a Unicode variation selector some editors append.
"""


def normalize_vault_line_hash(line: str) -> str:
    """Stable hash for a vault task line used as ``source_line_hash`` on EXTRACTED_FROM edges.

    Normalizes the checkbox prefix to ``- [ ] ``, strips the 🆔 token so
    the hash is stable across ID injection, then sha256s the
    whitespace-collapsed result.

    The ``✅ YYYY-MM-DD`` done-date is deliberately KEPT in the digest: it is
    the only thing that tells two same-title completed occurrences in one
    note apart (a weekly note logging the same task on two days), and
    stripping it swallowed the second one. SKUEL's own ``[x]`` + ``✅``
    write-back therefore DOES move a line's hash — that line is recognised
    by its 🆔 instead (extraction Guard 2b; ADR-070: the hash is the change
    signal, the 🆔 the identity), never by blinding the digest to more tokens.
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

    Exactly one of ``mark_done`` / ``mark_undone`` / ``inject_vault_id`` must
    be set.

    For ``inject_vault_id=True``, ``source_line_hash`` is the normalized
    sha-256 of the target line (obsidian-tasks adapter hash, 🆔-stripped) so
    the adapter can find the right line when multiple tasks need injection.

    For ``mark_done=True`` and ``mark_undone=True``, ``vault_id`` is the
    locator (line already has 🆔). ``mark_undone`` is the reverse of
    ``mark_done`` — un-check plus strip the ``✅ date`` — and carries no
    ``done_date``: there is no date to write, only one to remove.
    """

    vault_id: str
    mark_done: bool = False
    done_date: str | None = None  # YYYY-MM-DD when mark_done=True
    mark_undone: bool = False  # Un-check + strip ``✅ date`` (the reopen surface)
    inject_vault_id: bool = False  # Write ``🆔 <vault_id>`` to an ID-less line
    source_line_hash: str | None = None  # Required when inject_vault_id=True


@dataclass
class WriteResult:
    """Outcome of a vault write operation — file-level AND per-update.

    ``success`` is file-level: the write was applied (or no line needed
    changing) and the stale-read guard held. It does NOT say every queued
    update found its target — an update whose ``vault_id`` or
    ``source_line_hash`` matches no line in the file is a silent no-op INSIDE
    a successful write.

    ``updates_applied`` closes that gap: index ``i`` is whether ``updates[i]``
    actually changed a line, positionally parallel to the batch handed to
    ``write_task_updates``. A caller that persists per-update state (the
    reconciler minting a 🆔 onto an ``EXTRACTED_FROM`` edge) must gate on this
    tuple, never on ``success`` alone — persisting a 🆔 the file never received
    strands the task: no later sync can find its line, so its completion
    write-back silently never happens (deferred-work § Phantom-🆔).

    It is empty on every failure path and reads fail-CLOSED through
    ``was_applied``: unreported is "did not land", so a transport that cannot
    report outcomes withholds the persist rather than guessing it landed.
    """

    success: bool
    new_sha256: str | None = None
    error: str | None = None
    updates_applied: tuple[bool, ...] = ()

    def was_applied(self, index: int) -> bool:
        """Whether the update at ``index`` changed a line (False when unreported)."""
        return index < len(self.updates_applied) and self.updates_applied[index]


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

    ``errors``/``files_failed`` are reserved for SYSTEM faults (IO, Neo4j,
    real bugs). Files whose CONTENT can't be ingested — missing/improper
    YAML frontmatter, a malformed field — land in ``ignored`` with a
    per-file reason instead (2026-07-23 ruling): they are not sync failures,
    and a sync whose only findings are ignored files is clean. Ignored files
    carry no ingestion stamp, so they re-report on every sync — standing
    visibility by design, not noise.
    """

    entries_ingested: int = 0
    # The three outbound write counters count what LANDED in the file, not what
    # was queued: each is gated on its own ``WriteResult.updates_applied`` slot
    # (ADR-070; the pair's semantics were settled together 2026-08-24). A
    # queued write that matched no line, or one the file already satisfied, is
    # a no-op inside a successful write — counting it would tell the user their
    # vault changed when it did not, and a repeat sync of an unchanged vault
    # would re-report every completed task forever. Fail-closed follows from
    # ``was_applied``: a transport that reports no outcomes under-counts rather
    # than guessing, which costs a display number and never durable state.
    ids_injected: int = 0
    tasks_marked_done: int = 0
    tasks_marked_undone: int = 0
    # Inbound ingestion outcome (carried from IngestionStats/IncrementalStats)
    files_failed: int = 0
    files_walled: int = 0
    files_unsupported: int = 0
    # Standalone Edge YAMLs, both directions. Writes are split by what the
    # upsert did, so adding an edge file that reports "updated" tells the author
    # the relationship already existed. Relationships declared in entity
    # frontmatter are not counted here — they are not edge files, and only edge
    # files have a deletion counterpart.
    edges_created: int = 0
    edges_updated: int = 0
    entities_deleted: int = 0
    edges_deleted: int = 0
    # Content-hash move detection: uid-less renames whose identity survived
    # (tracker row rewritten in place — not a delete + a create).
    moves_detected: int = 0
    moves: list[str] = field(default_factory=list)  # vault-relative "old → new" lines
    # Content-caused non-ingestion: files skipped over their own frontmatter
    # (no type, empty uid, invalid enum value, broken YAML) — reported, never
    # counted as failures.
    files_ignored: int = 0
    ignored: list[str] = field(default_factory=list)  # vault-relative "path — reason" lines
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Retrievability (embedding coverage): how much of the corpus lacks a
    # vector AFTER this sync, and how much the gap GREW across this sync's
    # window. Measured in the graph by an optional count probe — a CORE-tier
    # period stores content with embedding = NULL, so a "complete" sync can
    # still leave its content invisible to vector search. Absolute counts are
    # corpus-wide (chunks vs entities split because their remedies differ)
    # and are filled for CONTENT-vault syncs ONLY: personal-sync stats
    # serialize through non-admin responses, and corpus aggregates over
    # other users' entities are admin-surface data — a personal sync carries
    # just the delta and the probe flag, absolutes stay 0.
    # The delta is corpus-wide too, probed before/after ingest and clamped
    # ≥ 0: in the common case it is exactly what this sync added, but a
    # concurrent writer (another root's sync, an API create) lands in the
    # same window — every counted item IS genuinely not yet searchable
    # either way. NULL vectors only: a stale vector on an updated entity is
    # invisible to a count probe by design — that class belongs to the
    # content-hash backstops (generate_embeddings_batch --stale/--audit,
    # ADR-074 §8), not to a per-sync count query.
    chunks_awaiting_embedding: int = 0
    entities_awaiting_embedding: int = 0
    retrievability_delta: int = 0
    # The probe is optional and fail-soft: True means the three counts above
    # are missing or partial, NOT that the sync failed. NEVER appended to
    # ``warnings`` — an optional probe's outage must not turn a perfect
    # sync's banner red, so ``is_clean`` stays a function of errors/warnings/
    # files_failed only. A sync that ADDED unretrievable content stays clean
    # too: the sync door's header variant carries that signal instead.
    coverage_probe_failed: bool = False
    first_run_notice: bool = False

    @property
    def is_clean(self) -> bool:
        """No system failures and no surfaced warnings — the only 'Sync complete' state.

        Ignored files (content-caused, listed in ``ignored``) do NOT flip
        cleanliness: the sync did its job; those files opted out or need
        author attention, which the ignored list reports on every run.
        """
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
# The same token PLUS the single separating space ``apply_mark_done`` wrote in
# front of it (``f"{stripped} ✅ {done_date}{eol}"``). Stripping the bare
# ``_DONE_DATE_RE`` match instead leaves that space behind, so an un-checked
# line is no longer byte-identical to what it was before completion — a
# whitespace bug that survives every assertion that is not byte-exact.
_DONE_DATE_STRIP_RE = re.compile(r"[ \t]?✅️?\s*\d{4}-\d{2}-\d{2}")


def _carries_skuel_done_marker(line: str) -> bool:
    """Whether this line carries the ``✅ date`` token — SKUEL's own completion write.

    ⚠ **The discriminator for the un-check, and it is deliberately NOT "is the
    box checked".** ``apply_mark_done`` ALWAYS appends a ``✅ date`` (its last
    act, unconditional once the box is checked), so SKUEL never authors a
    ``[x]`` without one. A dateless ``[x]`` on a 🆔 line is therefore
    *definitionally* something the USER checked in Obsidian — and since a
    vault-side check does not reach SKUEL (extraction Guard 2b; inbound is
    parked, deferred-work § R4), reverting it would silently erase a deliberate
    edit SKUEL cannot even read, on the sync right after they made it.

    So the un-check takes back only what SKUEL wrote. It is not an opinion
    about who owns the checkbox; it is the narrower and defensible claim that a
    withdrawn completion must not leave SKUEL's own completion token behind.
    A dateless ``[x]`` stays, diverging visibly — which is the pre-existing
    state § R4 exists to close, not a new one this creates.
    """
    return bool(_DONE_DATE_RE.search(line))


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


def apply_mark_undone(lines: list[str], vault_id: str) -> tuple[list[str], bool]:
    """Reverse ``apply_mark_done``: un-check the ``🆔 vault_id`` line and strip its ``✅ date``.

    The vault surface of a reopen (ADR-070 Resolved Design Question 2,
    amended 2026-08-24). Byte-exact reverse of ``apply_mark_done`` — the
    separating space that function wrote in front of the ✅ token goes with the
    token, so a complete → reopen round-trip restores the ORIGINAL line
    byte-for-byte.

    ⚠ Gated on the ``✅ date`` token, NOT on the checkbox — see
    ``_carries_skuel_done_marker``. A dateless ``[x]`` is a user's own Obsidian
    check that SKUEL never wrote and cannot read back, and it is left alone. A
    manually un-checked line still carrying a stale ✅ date DOES have the token
    stripped: that token is SKUEL's, and it records a completion that was
    withdrawn.

    A line with no ✅ date is a no-op (``changed=False``), as is a ``vault_id``
    that matches no line in the file — the caller distinguishes the two through
    ``WriteResult.updates_applied`` plus its own queue-time gate, never from
    this return value alone.
    """
    for i, line in enumerate(lines):
        m = VAULT_ID_RE.search(line)
        if not m or m.group(1) != vault_id:
            continue
        # A 🆔 on a non-checkbox line is not a task line — mirrors the same
        # guard in ``apply_mark_done``; nothing here may edit prose.
        if not _CHECKED_RE.match(line) and not _UNCHECKED_RE.match(line):
            return lines, False
        if not _carries_skuel_done_marker(line):
            return lines, False

        updated = re.sub(r"^([-*]\s*)\[[xX]\]", r"\1[ ]", line, count=1)
        updated = _DONE_DATE_STRIP_RE.sub("", updated)
        lines[i] = updated
        return lines, True
    return lines, False


def needs_mark_undone(content: str, vault_id: str) -> bool:
    """Would ``apply_mark_undone`` change this file? The outbound queue's cost gate.

    Correctness never needs this — ``apply_mark_undone`` is already a no-op on
    a line with nothing to undo. COST does: ``VaultReconciler`` calls the write
    door whenever its batch is non-empty, so an ungated un-check arm would make
    the batch non-empty for nearly every file that holds tasks and issue a
    write RPC per file on every sync — a network round-trip each, on the
    ``local_agent`` transport.

    It answers by RUNNING the mutation against a throwaway copy of the lines
    rather than re-stating its conditions, so the gate cannot drift from what
    the write would actually do. That is what makes a queued un-check reporting
    ``updates_applied=False`` a real divergence (a concurrent edit between the
    snapshot and the write) worth warning about, rather than an ordinary no-op.
    ``content`` is not mutated.
    """
    _lines, changed = apply_mark_undone(content.splitlines(keepends=True), vault_id)
    return changed


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


def apply_task_updates(content: str, updates: list[TaskLineUpdate]) -> tuple[str, tuple[bool, ...]]:
    """Apply a batch of task-line updates to note content; pure — no I/O.

    Returns ``(new_content, applied)`` where ``applied`` is POSITIONALLY
    parallel to ``updates``: each element is whether that one update changed a
    line. The per-update outcome is the return value, never OR-ed away — a
    file-level "something changed" cannot tell a caller WHICH update landed,
    and an update that matched no line is a silent no-op inside an otherwise
    successful write (``WriteResult.updates_applied``, deferred-work
    § Phantom-🆔). Callers needing the file-level answer take ``any(applied)``.

    Both transports wrap this with the same SHA-256 stale-read guard and
    atomic temp-file + ``rename()`` write.
    """
    lines = content.splitlines(keepends=True)
    applied: list[bool] = []
    for update in updates:
        if update.mark_done:
            lines, changed = apply_mark_done(lines, update.vault_id, update.done_date or "")
        elif update.mark_undone:
            lines, changed = apply_mark_undone(lines, update.vault_id)
        elif update.inject_vault_id:
            lines, changed = apply_inject_id(lines, update.vault_id, update.source_line_hash)
        else:
            changed = False
        applied.append(changed)
    return "".join(lines), tuple(applied)


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

        The returned ``WriteResult`` carries ``updates_applied`` positionally
        parallel to ``updates`` — a caller persisting per-update state gates on
        that, not on file-level ``success``.
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
