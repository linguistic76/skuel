"""
FilesystemVaultAdapter — ADR-070 Stage 1
=========================================

Direct local-filesystem implementation of ``VaultBridgePort``.  Intended for
Stage 1 (local Docker, same-machine vault).  Stage 2+ swaps this for
``LocalAgentVaultAdapter`` with no changes to ``core/``.

**VaultWriter** (embedded here):
    Three outbound write operations per ADR-070 Decision 4:
    1. ID injection: append ``🆔 <vault_id>`` to a task line that has no token.
    2. Status round-trip: toggle ``- [ ]`` → ``- [x]`` AND append ``✅ YYYY-MM-DD``.
    3. Undone round-trip (deferred v1 — not implemented).
    The pure line mutations live in ``core/ports/vault_bridge_protocol.py``
    (``apply_task_updates``) — shared with the user-side vault agent (ADR-075 B3)
    so both transports mutate lines byte-identically.

All writes are atomic (POSIX ``rename()``): the file is either fully replaced
or untouched.  A stale-read guard (SHA-256 compare before write) prevents
partial writes when the file changes between read and write.

NFS / network drives: ``rename()`` atomicity is NOT guaranteed.  Document as
unsupported; recommend local-disk vault.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path

from core.ports.vault_bridge_protocol import (
    NoteSnapshot,
    TaskLineUpdate,
    WriteResult,
    apply_task_updates,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.adapters.vault.filesystem")


class FilesystemVaultAdapter:
    """VaultBridgePort backed by direct filesystem I/O.

    All vault paths are validated against ``allowed_root`` (the user's vault
    root) so that API callers cannot escape the vault directory.
    """

    def __init__(self, allowed_root: Path) -> None:
        """
        Args:
            allowed_root: Absolute path to the user's vault root.  All file
                paths are validated to be under this root.
        """
        self._root = allowed_root.resolve()

    def _resolve(self, path: str) -> Path:
        """Resolve path relative to vault root; raise ValueError if outside."""
        resolved = (
            (self._root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        )
        if not resolved.is_relative_to(self._root):
            raise ValueError(f"Path {path!r} escapes vault root {self._root}")
        return resolved

    async def read_note(
        self, user_uid: str, path: str
    ) -> NoteSnapshot:  # skuel-lint: disable=SKUEL029 -- VaultBridgePort protocol: local_agent transport sibling does real I/O
        p = self._resolve(path)
        content = p.read_text(encoding="utf-8")
        return NoteSnapshot.from_content(str(p), content)

    async def write_task_updates(  # skuel-lint: disable=SKUEL029 -- VaultBridgePort protocol: local_agent transport sibling does real I/O
        self,
        user_uid: str,
        path: str,
        updates: list[TaskLineUpdate],
        expected_sha256: str,
    ) -> WriteResult:
        """Apply task-line writes atomically via temp-file + rename().

        Stale-read guard: re-reads file, checks SHA-256 against
        ``expected_sha256``; aborts if they differ.
        """
        p = self._resolve(path)
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as exc:
            return WriteResult(success=False, error=str(exc))

        current_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if current_sha256 != expected_sha256:
            return WriteResult(
                success=False,
                error=(
                    f"Stale-read guard: file changed since last sync "
                    f"(expected {expected_sha256[:8]}, got {current_sha256[:8]}). "
                    "Re-queue for re-sync."
                ),
            )

        new_content, modified = apply_task_updates(content, updates)
        if not modified:
            return WriteResult(success=True, new_sha256=current_sha256)

        new_sha256 = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        # Atomic write via temp-file + rename()
        try:
            fd, tmp_path_str = tempfile.mkstemp(dir=p.parent, suffix=".skuel_tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                tmp_path.rename(p)
            except Exception:  # intentional-broad: cleanup handler, always re-raises
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
                raise
        except OSError as exc:
            return WriteResult(success=False, error=str(exc))

        logger.info(f"VaultWriter: wrote {len(updates)} update(s) to {p}")
        return WriteResult(success=True, new_sha256=new_sha256)

    async def list_vault_notes(  # skuel-lint: disable=SKUEL029 -- VaultBridgePort protocol: local_agent transport sibling does real I/O
        self, user_uid: str, vault_path: str, pattern: str = "**/*.md"
    ) -> list[str]:
        """Vault-relative POSIX paths of matching notes (harmonized, ADR-075 B4)."""
        base = self._resolve(vault_path) if vault_path not in ("", ".") else self._root
        return sorted(
            p.relative_to(self._root).as_posix() for p in base.glob(pattern) if p.is_file()
        )
