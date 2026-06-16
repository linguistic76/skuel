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

All writes are atomic (POSIX ``rename()``): the file is either fully replaced
or untouched.  A stale-read guard (SHA-256 compare before write) prevents
partial writes when the file changes between read and write.

NFS / network drives: ``rename()`` atomicity is NOT guaranteed.  Document as
unsupported; recommend local-disk vault.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from core.ports.vault_bridge_protocol import (
    NoteSnapshot,
    TaskLineUpdate,
    WriteResult,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.adapters.vault.filesystem")

# obsidian-tasks 🆔 pattern (ADR-070 Decision 1)
_VAULT_ID_RE = re.compile(r"🆔️?\s*([\w-]{1,20})")
# Checkbox detection
_UNCHECKED_RE = re.compile(r"^([-*]\s*\[)\s*(\])")
_CHECKED_RE = re.compile(r"^[-*]\s*\[[xX]\]")
# Done-date token: ✅ YYYY-MM-DD
_DONE_DATE_RE = re.compile(r"✅️?\s*\d{4}-\d{2}-\d{2}")


def _file_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_line_hash(line: str) -> str:
    """Compute the same hash the obsidian-tasks adapter uses (ADR-070).

    Strips the checkbox prefix (normalising to ``- [ ] ``), strips the 🆔
    token (hash is stable across ID injection), then sha256 of the
    whitespace-collapsed result.
    """
    # Normalize checked → unchecked
    line = re.sub(r"^[-*]\s*\[[xX]\]\s*", "- [ ] ", line)
    line = re.sub(r"^[-*]\s*\[\s*\]\s*", "- [ ] ", line)
    # Strip 🆔 token
    line = _VAULT_ID_RE.sub("", line)
    # Collapse whitespace
    normalized = " ".join(line.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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

    async def read_note(self, _user_uid: str, path: str) -> NoteSnapshot:
        p = self._resolve(path)
        content = p.read_text(encoding="utf-8")
        return NoteSnapshot.from_content(str(p), content)

    async def write_task_updates(
        self,
        _user_uid: str,
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

        lines = content.splitlines(keepends=True)
        modified = False

        for update in updates:
            if update.mark_done:
                lines, changed = _apply_mark_done(lines, update.vault_id, update.done_date or "")
            elif update.inject_vault_id:
                lines, changed = _apply_inject_id(lines, update.vault_id, update.source_line_hash)
            else:
                changed = False
            if changed:
                modified = True

        if not modified:
            new_sha = current_sha256
            return WriteResult(success=True, new_sha256=new_sha)

        new_content = "".join(lines)
        new_sha256 = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        # Atomic write via temp-file + rename()
        import contextlib

        try:
            fd, tmp_path_str = tempfile.mkstemp(dir=p.parent, suffix=".skuel_tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                tmp_path.rename(p)
            except Exception:
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
                raise
        except OSError as exc:
            return WriteResult(success=False, error=str(exc))

        logger.info(f"VaultWriter: wrote {len(updates)} update(s) to {p}")
        return WriteResult(success=True, new_sha256=new_sha256)

    async def list_vault_notes(
        self, _user_uid: str, vault_path: str, pattern: str = "**/*.md"
    ) -> list[str]:
        base = self._resolve(vault_path)
        return [str(p) for p in base.glob(pattern) if p.is_file()]

    def find_line_by_hash(self, content: str, target_hash: str) -> int | None:
        """Return the 0-based line index whose normalized hash matches target_hash.

        Used by VaultReconciler to locate lines for ID injection without a
        stored line number.
        """
        for i, line in enumerate(content.splitlines()):
            if (_UNCHECKED_RE.match(line) or _CHECKED_RE.match(line)) and _normalize_line_hash(
                line
            ) == target_hash:
                return i
        return None

    def find_line_by_vault_id(self, content: str, vault_id: str) -> int | None:
        """Return 0-based line index of the task line carrying the given 🆔 vault_id."""
        for i, line in enumerate(content.splitlines()):
            m = _VAULT_ID_RE.search(line)
            if m and m.group(1) == vault_id:
                return i
        return None


# ============================================================================
# LINE-LEVEL MUTATIONS (pure functions — easier to test)
# ============================================================================


def _apply_mark_done(lines: list[str], vault_id: str, done_date: str) -> tuple[list[str], bool]:
    """Toggle the line with ``🆔 vault_id`` from ``[ ]`` to ``[x]`` and append ``✅ date``.

    Idempotent only when BOTH the checkbox is already ``[x]`` AND the ``✅ date`` token is
    present.  An already-checked line that is missing the done-date (e.g. checked directly
    in Obsidian without the tasks plugin) still receives the token so SKUEL and the vault
    stay in sync.
    """
    for i, line in enumerate(lines):
        m = _VAULT_ID_RE.search(line)
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


def _apply_inject_id(
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
        if _VAULT_ID_RE.search(line):
            continue  # Already has a 🆔
        if source_line_hash is not None and _normalize_line_hash(line) != source_line_hash:
            continue
        stripped = line.rstrip("\n")
        eol = line[len(stripped) :]
        lines[i] = f"{stripped} 🆔 {vault_id}{eol}"
        return lines, True
    return lines, False
