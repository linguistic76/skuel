"""
VaultMirrorPuller — ADR-075 Decision 4 (the mirror-refresh pre-phase)
=====================================================================

Keeps a server-side staging mirror faithful to a remote vault so the EXISTING
ingestion engine — tracker, smart-mode skip, deletion reconciliation, the
mass-deletion valve, owner scoping, preview — runs on it unchanged: "keep this
directory faithful to the device, then do what you already do."

The refresh, per ADR-075 Decision 4:

1. ``describe_wall`` — honesty/liveness check (no agent → clear integration
   failure BEFORE anything else, mirror untouched).
2. ``list_changed_since(None)`` — full listing of allowed files.
3. Fetch (``read_note``) only files absent from the mirror or whose mirror
   sha256 differs from the listed hash; verify the returned content hashes to
   the listing (torn-read guard); write atomically (temp-file + ``rename()``).
4. Delete mirror files absent from the listing — the mirror is a cache of the
   listing, nothing more. Their disappearance is exactly what drives the
   existing deletion reconciliation and its valves downstream.

The wall is enforced on BOTH sides (ADR-075 Decision 5): the agent never lists
or serves walled content, and this puller additionally scopes every fetch and
the deletion sweep to the SERVER-side allowed folders (defense in depth — the
effective wall is the intersection; a compromised or misconfigured side cannot
widen it alone). The ``je_*`` staging floor applies unconditionally.

Runs inside the reconciler's per-root lock (a preview can never race a
half-refreshed mirror). The mirror is server-internal state: never a git repo,
never synced anywhere (vault privacy foundation).

See: docs/decisions/ADR-075-local-agent-vault-transport.md
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core.services.ingestion.config import STAGING_EXCLUDED_DIRS, is_staging_path
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.vault_bridge_protocol import AgentWall, RemoteVaultBridgePort

logger = get_logger("skuel.services.vault.mirror_sync")

# The sync surface is ingestible files only — mirrors the agent-side listing
# discipline AND the server-side collect discipline, so the deletion sweep can
# never touch anything the listing could not have contained.
_INGESTIBLE_SUFFIXES: frozenset[str] = frozenset({".md", ".yaml", ".yml"})


def _sha256_file(path: Path) -> str | None:
    """Bare hex sha256 of a mirror file's bytes; None when unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@dataclass
class MirrorPullStats:
    """Outcome of one mirror refresh — honest by construction (G10).

    ``warnings`` carries every skipped row (torn read, per-file fetch failure,
    server-side wall refusal) so a sync door never says "complete" over a
    partially-refreshed mirror; paths in it are vault-relative only.
    """

    fetched: int = 0
    unchanged: int = 0
    deleted: int = 0
    warnings: list[str] = field(default_factory=list)


class VaultMirrorPuller:
    """Refreshes one vault's staging mirror from its remote agent (ADR-075).

    Bound per-descriptor to the mirror root, the remote transport, and the
    server-side allowed top-level folders (``None`` = whole-vault-open, the
    combined-root shape — only the ``je_*`` staging floor applies then).
    """

    def __init__(
        self,
        transport: RemoteVaultBridgePort,
        mirror_root: Path,
        allowed_folders: frozenset[str] | None,
    ) -> None:
        self._transport = transport
        self._mirror_root = mirror_root.resolve()
        self._allowed_folders = allowed_folders

    async def describe_wall(self, user_uid: str) -> Result[AgentWall]:
        """The agent's self-reported wall (pass-through for the UI honesty door)."""
        return await self._transport.describe_wall(user_uid)

    async def refresh(self, user_uid: str) -> Result[MirrorPullStats]:
        """Pull the remote vault's allowed subtree into the mirror (Decision 4).

        Fails without touching the mirror when the agent is unreachable or the
        listing is malformed; per-file problems (torn read, transient fetch
        failure) become warnings and skip that file only — the listing was
        already complete, so the deletion sweep stays sound.
        """
        wall_result = await self._transport.describe_wall(user_uid)
        if wall_result.is_error:
            return Result.fail(wall_result)
        wall = wall_result.value
        # The pull populates only the INTERSECTION of the agent's self-reported
        # wall and the server-side allowed folders (Kody #531): describe_wall
        # is binding, not decorative — an agent that hides a folder cannot
        # still ship its content through the listing, and the server wall
        # stays as defense in depth. The deletion sweep below deliberately
        # keeps the WIDER server scope, so a narrowed agent wall retracts
        # previously-mirrored content retroactively (same fail-closed
        # semantics as the server wall), with the deletion valves as guard.
        agent_allowed = frozenset(wall.allowed_folders)
        effective_allowed = (
            agent_allowed
            if self._allowed_folders is None
            else self._allowed_folders & agent_allowed
        )
        logger.info(
            "Mirror refresh for %s: agent v%s serves %s (effective: %s)",
            user_uid,
            wall.agent_version,
            ", ".join(sorted(agent_allowed)) or "(nothing)",
            ", ".join(sorted(effective_allowed)) or "(nothing)",
        )

        listing_result = await self._transport.list_changed_since(user_uid)
        if listing_result.is_error:
            return Result.fail(listing_result)

        stats = MirrorPullStats()
        listed: set[str] = set()
        for stat in listing_result.value.files:
            target = self._safe_target(stat.relative_path, effective_allowed)
            if target is None:
                stats.warnings.append(
                    f"mirror refresh skipped {stat.relative_path!r}: "
                    "outside the effective vault wall (agent ∩ server)"
                )
                continue
            listed.add(stat.relative_path)
            if target.is_file() and _sha256_file(target) == stat.sha256:
                stats.unchanged += 1
                continue
            await self._fetch_one(user_uid, stat.relative_path, stat.sha256, target, stats)

        self._sweep_absent(listed, stats)
        return Result.ok(stats)

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    async def _fetch_one(
        self,
        user_uid: str,
        relative_path: str,
        expected_sha256: str,
        target: Path,
        stats: MirrorPullStats,
    ) -> None:
        """Fetch one changed/new file and write it atomically into the mirror."""
        try:
            snapshot = await self._transport.read_note(user_uid, relative_path)
        except FILE_IO_EXCEPTIONS as exc:
            stats.warnings.append(f"mirror refresh could not fetch {relative_path!r}: {exc}")
            return
        if snapshot.sha256 != expected_sha256:
            # Torn-read guard: the file changed on the device between listing
            # and fetch — skip it; the next sync's listing catches it.
            stats.warnings.append(
                f"mirror refresh skipped {relative_path!r}: content changed mid-sync"
            )
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(dir=target.parent, suffix=".skuel_tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(snapshot.content)
                tmp_path.rename(target)
            except OSError:
                tmp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            stats.warnings.append(
                f"mirror refresh could not write {relative_path!r}: {type(exc).__name__}"
            )
            return
        stats.fetched += 1

    # ------------------------------------------------------------------
    # containment + sweep
    # ------------------------------------------------------------------

    def _safe_target(self, relative_path: str, allowed: frozenset[str]) -> Path | None:
        """Mirror path for a listed file, or None when the row must be refused.

        Refuses upward/absolute escapes (a listing row is agent-supplied
        input), rows outside ``allowed`` — the effective agent ∩ server folder
        set (Kody #531; Decision 5 defense in depth) — the ``je_*`` staging
        floor, and non-ingestible suffixes.
        """
        candidate = Path(relative_path)
        if candidate.is_absolute() or not relative_path:
            return None
        resolved = (self._mirror_root / candidate).resolve()
        if not resolved.is_relative_to(self._mirror_root):
            return None
        parts = resolved.relative_to(self._mirror_root).parts
        if not parts:
            return None
        if parts[0] not in allowed:
            return None
        if any(part in STAGING_EXCLUDED_DIRS for part in parts):
            return None
        if resolved.suffix.lower() not in _INGESTIBLE_SUFFIXES:
            return None
        return resolved

    def _sweep_roots(self) -> list[Path]:
        """The directories whose contents this puller maintains as a cache."""
        if self._allowed_folders is None:
            return [self._mirror_root]
        return [self._mirror_root / folder for folder in sorted(self._allowed_folders)]

    def _sweep_absent(self, listed: set[str], stats: MirrorPullStats) -> None:
        """Delete pull-managed mirror files absent from the agent's listing.

        Deliberately scoped to the SERVER-side allowed folders — a superset of
        the effective populate scope (agent ∩ server): a folder the agent
        newly hides has its rows dropped from ``listed``, so its previously
        mirrored files are swept here and retract retroactively, matching the
        server wall's fail-closed semantics (Kody #531 follow-through).
        Ingestible suffixes only, staging floor and symlinks skipped — the
        sweep can only ever remove what a listing could have contained. The
        removed files' tracked graph rows then flow through the EXISTING
        deletion reconciliation with all its valves (ADR-075 Decision 4
        step 3).
        """
        for sweep_root in self._sweep_roots():
            if not sweep_root.is_dir():
                continue
            for path in sorted(sweep_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                if path.suffix.lower() not in _INGESTIBLE_SUFFIXES:
                    continue
                relative = path.relative_to(self._mirror_root)
                if is_staging_path(relative):
                    continue
                if relative.as_posix() in listed:
                    continue
                try:
                    path.unlink()
                except OSError as exc:
                    stats.warnings.append(
                        f"mirror refresh could not remove {relative.as_posix()!r}: "
                        f"{type(exc).__name__}"
                    )
                    continue
                stats.deleted += 1


__all__ = ["MirrorPullStats", "VaultMirrorPuller"]
