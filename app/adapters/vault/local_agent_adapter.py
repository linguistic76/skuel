"""
LocalAgentVaultAdapter — ADR-075 Stage 2
=========================================

``RemoteVaultBridgePort`` implementation that reaches the user's vault through
their live agent channel (``WS /ws/agent``): the vault lives on the user's own
machine and the ``skuel-vault-agent`` process there is the only thing that
touches its files. This adapter resolves the user's :class:`AgentSession` from
the :class:`AgentChannelRegistry` at call time and speaks the ADR-075
Decision 3 envelope; no connected agent = every operation fails fast with a
clear "agent not connected" error (human-initiated sync: you start your agent,
then you click "Update from my vault").

Path translation happens HERE, at the adapter boundary: the reconciler
addresses files by their absolute path under the server-side staging mirror
(``{user_vaults_root}/{user_uid}/…`` — the mirror root this adapter is bound
to), while the wire carries vault-RELATIVE paths only (ADR-075 Decision 3 —
the server never learns the device-side absolute root, and the agent never
learns the mirror's).

Counterparty: ``agent/skuel_vault_agent.py`` (frame shapes are LOCKED there).
See: docs/decisions/ADR-075-local-agent-vault-transport.md
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from adapters.inbound.agent_channel_registry import DEFAULT_RPC_TIMEOUT_S
from core.ports.vault_bridge_protocol import (
    AgentWall,
    NoteSnapshot,
    TaskLineUpdate,
    VaultFileStat,
    VaultListing,
    WriteResult,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.inbound.agent_channel_registry import AgentChannelRegistry, AgentSession

logger = get_logger("skuel.adapters.vault.local_agent")

AGENT_NOT_CONNECTED = "agent not connected — start `skuel-vault-agent run` on your machine"

_SHA256_PREFIX = "sha256:"


def _bare_sha256(content_hash: str) -> str:
    """Strip the wire's ``sha256:`` prefix; accept an already-bare hex hash."""
    return content_hash.removeprefix(_SHA256_PREFIX)


class LocalAgentVaultAdapter:
    """VaultBridgePort over the per-user agent channel (ADR-075).

    Bound to one mirror root (one descriptor, one user's vault) — absolute
    mirror paths from the reconciler are translated to vault-relative wire
    paths against it, with the same containment guard as
    ``FilesystemVaultAdapter._resolve`` (resolve, then ``is_relative_to``).
    """

    def __init__(
        self,
        registry: AgentChannelRegistry,
        mirror_root: Path,
        rpc_timeout_s: float = DEFAULT_RPC_TIMEOUT_S,
    ) -> None:
        """
        Args:
            registry: Live agent channels, resolved per-user at call time.
            mirror_root: Absolute server-side mirror root for this vault — the
                addressing base for absolute paths the reconciler passes.
            rpc_timeout_s: Per-RPC answer deadline (registry await machinery).
        """
        self._registry = registry
        self._mirror_root = mirror_root.resolve()
        self._rpc_timeout_s = rpc_timeout_s

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------

    def _session_result(self, user_uid: str) -> Result[AgentSession]:
        session = self._registry.get(user_uid)
        if session is None:
            return Result.fail(Errors.integration("vault_agent", AGENT_NOT_CONNECTED))
        return Result.ok(session)

    def _to_relative(self, path: str) -> str:
        """Mirror-absolute (or already-relative) path → vault-relative POSIX.

        Raises ValueError on any escape of the mirror root — same posture as
        ``FilesystemVaultAdapter._resolve``, sanitized: the message never
        carries the caller's absolute path.
        """
        p = Path(path)
        resolved = (self._mirror_root / p).resolve() if not p.is_absolute() else p.resolve()
        if not resolved.is_relative_to(self._mirror_root):
            raise ValueError("path escapes the vault mirror root")
        relative = resolved.relative_to(self._mirror_root).as_posix()
        if relative == ".":
            raise ValueError("path addresses the vault root, not a note")
        return relative

    async def _call(self, user_uid: str, op: str, params: dict[str, Any]) -> Result[dict[str, Any]]:
        session_result = self._session_result(user_uid)
        if session_result.is_error:
            return Result.fail(session_result)
        return await session_result.value.call(op, params, timeout_s=self._rpc_timeout_s)

    # ------------------------------------------------------------------
    # VaultBridgePort
    # ------------------------------------------------------------------

    async def read_note(self, user_uid: str, path: str) -> NoteSnapshot:
        """Fetch one note's content from the agent.

        Raises ConnectionError (an OSError, so existing ``FILE_IO_EXCEPTIONS``
        handling applies) when no agent is connected or the RPC is refused —
        messages carry vault-relative paths only.
        """
        relative = self._to_relative(path)
        result = await self._call(user_uid, "read_note", {"relative_path": relative})
        if result.is_error:
            raise ConnectionError(result.expect_error().message)
        content = result.value.get("content")
        if not isinstance(content, str):
            raise ConnectionError(f"agent returned a malformed read_note frame for {relative!r}")
        return NoteSnapshot.from_content(relative, content)

    async def write_task_updates(
        self,
        user_uid: str,
        path: str,
        updates: list[TaskLineUpdate],
        expected_sha256: str,
    ) -> WriteResult:
        """Forward the outbound task-line batch to the agent (ADR-075 Decision 3).

        The agent applies the SAME pure mutations, SHA-256 stale-read guard,
        and atomic temp-file + ``rename()`` mechanics as Stage 1 — the wire
        carries the ``TaskLineUpdate`` shapes verbatim (including ``mark_undone``,
        protocol v3) and the per-update outcomes back (``updates_applied``,
        protocol v2).
        """
        try:
            relative = self._to_relative(path)
        except ValueError as exc:
            return WriteResult(success=False, error=str(exc))
        result = await self._call(
            user_uid,
            "write_task_updates",
            {
                "relative_path": relative,
                "expected_sha256": expected_sha256,
                "updates": [
                    {
                        "vault_id": update.vault_id,
                        "mark_done": update.mark_done,
                        "done_date": update.done_date,
                        "mark_undone": update.mark_undone,
                        "inject_vault_id": update.inject_vault_id,
                        "source_line_hash": update.source_line_hash,
                    }
                    for update in updates
                ],
            },
        )
        if result.is_error:
            return WriteResult(success=False, error=result.expect_error().message)
        payload = result.value
        new_sha256 = payload.get("new_sha256")
        error = payload.get("error")
        raw_applied = payload.get("updates_applied")
        # Fail-closed, and only a REAL JSON boolean counts as confirmation.
        # ``bool(flag)`` would read the string "false" as True and hand the
        # reconciler a confirmation the agent never gave — re-creating the exact
        # phantom-🆔 these outcomes exist to report away (Codex #1151). A list
        # carrying any non-boolean is discarded WHOLE: a partially-typed reply
        # is not a trustworthy POSITIONAL answer, and the caller then reads
        # every update as unapplied through ``was_applied``. Same reason
        # ``success`` must be the literal ``True``, not merely truthy.
        updates_applied: tuple[bool, ...] = ()
        if isinstance(raw_applied, list) and all(isinstance(flag, bool) for flag in raw_applied):
            updates_applied = tuple(raw_applied)
        return WriteResult(
            success=payload.get("success") is True,
            new_sha256=new_sha256 if isinstance(new_sha256, str) else None,
            error=error if isinstance(error, str) else None,
            updates_applied=updates_applied,
        )

    async def list_vault_notes(
        self, user_uid: str, vault_path: str, pattern: str = "**/*.md"
    ) -> list[str]:
        """Vault-relative POSIX paths of matching notes, derived from the agent listing.

        Raises ConnectionError when no agent is connected (same error family
        as ``read_note``).
        """
        listing_result = await self.list_changed_since(user_uid)
        if listing_result.is_error:
            raise ConnectionError(listing_result.expect_error().message)
        base = "" if vault_path in ("", ".") else self._to_relative(vault_path)
        matched: list[str] = []
        for stat in listing_result.value.files:
            if base:
                if not stat.relative_path.startswith(f"{base}/"):
                    continue
                candidate = stat.relative_path[len(base) + 1 :]
            else:
                candidate = stat.relative_path
            if Path(candidate).full_match(pattern):
                matched.append(stat.relative_path)
        return sorted(matched)

    # ------------------------------------------------------------------
    # RemoteVaultBridgePort (the mirror-pull surface)
    # ------------------------------------------------------------------

    async def list_changed_since(
        self, user_uid: str, since_state: str | None = None
    ) -> Result[VaultListing]:
        """Full remote listing (presence + hashes) — the mirror's source of truth.

        Fails closed on a malformed listing: the absence-driven deletion sweep
        (ADR-075 Decision 4 step 3) must never run against a listing it cannot
        trust, and a relative path that escapes upward is treated as hostile.
        """
        result = await self._call(user_uid, "list_changed_since", {"since_state": since_state})
        if result.is_error:
            return Result.fail(result)
        payload = result.value
        raw_files = payload.get("files")
        state = payload.get("state")
        if not isinstance(raw_files, list) or not isinstance(state, str):
            return Result.fail(
                Errors.integration("vault_agent", "agent sent a malformed listing frame")
            )
        files: list[VaultFileStat] = []
        for row in raw_files:
            relative_path = row.get("relative_path") if isinstance(row, dict) else None
            content_hash = row.get("content_hash") if isinstance(row, dict) else None
            if not isinstance(relative_path, str) or not isinstance(content_hash, str):
                return Result.fail(
                    Errors.integration("vault_agent", "agent sent a malformed listing row")
                )
            files.append(
                VaultFileStat(relative_path=relative_path, sha256=_bare_sha256(content_hash))
            )
        return Result.ok(VaultListing(files=tuple(files), state=state))

    async def describe_wall(self, user_uid: str) -> Result[AgentWall]:
        """The agent's self-reported wall — honesty check + liveness probe."""
        result = await self._call(user_uid, "describe_wall", {})
        if result.is_error:
            return Result.fail(result)
        payload = result.value
        folders = payload.get("allowed_folders")
        if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
            return Result.fail(
                Errors.integration("vault_agent", "agent sent a malformed describe_wall frame")
            )
        version = payload.get("agent_version")
        return Result.ok(
            AgentWall(
                allowed_folders=tuple(sorted(folders)),
                agent_version=version if isinstance(version, str) else "unknown",
            )
        )


__all__ = ["AGENT_NOT_CONNECTED", "LocalAgentVaultAdapter"]
