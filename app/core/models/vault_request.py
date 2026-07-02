"""
Vault Sync Request Models (Pydantic)
=====================================

Pydantic models for vault-sync API boundaries (ADR-070).
"""

from pydantic import BaseModel, Field


class ContentVaultSyncRequest(BaseModel):
    """Request body for ``POST /api/vault/sync/content`` (optional — empty body = defaults).

    ``force`` re-processes every surviving allowed file regardless of the
    IngestionMetadata hash/mtime match, while keeping smart-mode semantics
    (fail-closed allowlist, metadata re-stamping, deletion reconciliation).
    The sanctioned re-chunk/migration path — force ≠ full.
    """

    force: bool = Field(
        default=False,
        description="Re-process unchanged files too (re-chunk/migration campaigns). "
        "Deletion reconciliation and the vault wall stay active.",
    )
