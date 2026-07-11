"""
EdgeFileWriterPort — content-vault Edge YAML writer boundary
============================================================

The first sanctioned vault-write capability (Discovery Analytics PR 4,
Mike's ruling 2026-07-10): approving a prerequisite-edge suggestion writes
ONE Edge YAML file into the content vault's ``edges/`` directory, which the
admin then syncs through the existing content-sync path. Nothing else about
this feature touches the vault or the graph.

Safety rails (non-negotiable, enforced by the adapter):
- Writes ONLY into ``{INGESTION_PATH}/edges/`` — never VAULT_ROOT / personal
  vaults; containment is verified after ``resolve()`` (no traversal, no
  symlink escape).
- NEVER overwrites: an existing target filename is refused with a clear error.
- The write happens only on an explicit admin approve (POST + CSRF + admin
  role) — no background writes, no batch writes.

Implementation: adapters/vault/content_edge_writer.py (filesystem I/O lives
below the hexagonal boundary, VaultBridgePort precedent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from core.utils.result_simplified import Result


class EdgeFileWriterPort(Protocol):
    """Write one Edge YAML file into the content vault's ``edges/`` directory."""

    async def write_edge_file(self, filename: str, content: str) -> Result[str]:
        """Create ``edges/{filename}`` with ``content``; refuse to overwrite.

        Args:
            filename: Bare filename (``edge_{slug}-{rel}-{slug}.md``) — the
                adapter validates the shape and refuses anything that is not a
                plain slug filename.
            content: Full rendered Edge YAML text.

        Returns:
            ``Result.ok(absolute_path_written)`` or a validation/business
            failure (bad filename, containment violation, file exists).
        """
        ...
