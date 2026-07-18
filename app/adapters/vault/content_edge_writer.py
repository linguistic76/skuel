"""
ContentVaultEdgeWriter — the one sanctioned vault-write adapter
===============================================================

Implements ``EdgeFileWriterPort`` (Discovery Analytics PR 4): approving a
prerequisite-edge suggestion writes ONE Edge YAML file into the content
vault's ``edges/`` directory. Mike then syncs it through the existing
content-sync path (``POST /api/vault/sync/content``) — the graph edge is
created by ingestion, never by this adapter.

Safety rails (Mike's ruling 2026-07-10, non-negotiable):
- Scope: ONLY ``{INGESTION_PATH}/edges/`` (content vault) — never
  VAULT_ROOT / personal vaults. The root is injected at composition from
  ``VaultConfig.ingestion_path``.
- Containment: filename must match the strict slug shape (no separators, so
  traversal is structurally impossible), and the resolved target's parent
  must still be the resolved ``edges/`` directory (symlink-escape guard);
  the ``edges/`` directory itself must resolve inside the content root.
- No overwrite: the file is opened with ``"x"`` (atomic create-exclusive) —
  an existing file, including an existing symlink, is refused.
- No implicit directories: a missing ``edges/`` directory is an error, not a
  ``mkdir`` — creating directories at a misconfigured root would widen the
  blast radius of a bad ``INGESTION_PATH``.

Port: core/ports/edge_file_writer_protocol.py
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from pathlib import Path

# Bare slug filename only: no path separators, no dots beyond the .md suffix.
_EDGE_FILENAME_RE = re.compile(r"^edge_[a-z0-9][a-z0-9-]*\.md$")


class ContentVaultEdgeWriter:
    """Writes admin-approved Edge YAML files into the content vault's ``edges/``."""

    def __init__(self, content_vault_root: Path) -> None:
        self._root = content_vault_root
        self._edges_dir = content_vault_root / "edges"

    async def write_edge_file(
        self, filename: str, content: str
    ) -> Result[
        str
    ]:  # skuel-lint: disable=SKUEL029 -- EdgeFileWriterPort protocol declares async; awaited by PrereqSuggestionService
        """Create ``edges/{filename}`` with ``content``; refuse to overwrite.

        See ``EdgeFileWriterPort`` for the contract; the module docstring
        documents each guard.
        """
        if not _EDGE_FILENAME_RE.match(filename):
            return Result.fail(
                Errors.validation(
                    f"Invalid edge filename {filename!r} — expected "
                    "edge_{slug}-{rel}-{slug}.md (lowercase slug characters only)",
                    field="filename",
                )
            )

        root = self._root.resolve()
        edges_dir = self._edges_dir.resolve()
        if not edges_dir.is_dir():
            return Result.fail(
                Errors.business(
                    rule="content_vault_edges_dir",
                    message=f"Content vault edges/ directory not found at {self._edges_dir} — "
                    "check INGESTION_PATH; this writer never creates directories",
                )
            )
        if not edges_dir.is_relative_to(root):
            return Result.fail(
                Errors.business(
                    rule="content_vault_containment",
                    message=f"edges/ resolves outside the content vault root ({edges_dir} "
                    f"not under {root}) — refusing to write",
                )
            )

        target = edges_dir / filename
        # Symlink-escape guard: if the target name already exists as a symlink,
        # resolve() leaves edges_dir — refuse before any open() attempt.
        resolved = target.resolve()
        if resolved.parent != edges_dir:
            return Result.fail(
                Errors.business(
                    rule="content_vault_containment",
                    message=f"Edge file target escapes edges/ ({resolved}) — refusing to write",
                )
            )

        try:
            # O_CREAT|O_EXCL = atomic create-exclusive: no-overwrite without a
            # check-then-write race, and an existing symlink is refused too
            # (os.fdopen write pattern = FilesystemVaultAdapter precedent).
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            return Result.fail(
                Errors.business(
                    rule="edge_file_exists",
                    message=f"edges/{filename} already exists — refusing to overwrite. "
                    "If this pair was already approved, reject the duplicate suggestion.",
                )
            )
        except OSError as e:
            return Result.fail(
                Errors.system(message=f"Failed to write edges/{filename}: {e}", exception=e)
            )

        return Result.ok(str(target))
