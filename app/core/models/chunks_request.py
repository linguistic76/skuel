"""
Chunks Request Models (Pydantic)
=================================

Pydantic models for chunk-management API boundaries.
"""

from pydantic import BaseModel, Field


class RegenerateChunksRequest(BaseModel):
    """Request to regenerate :ContentChunk nodes for one or more :Content parents.

    Empty `parent_uids` means "every :Content node" — the operation can be
    expensive on a large graph, so callers should pass an explicit subset
    unless they intend a full sweep.
    """

    parent_uids: list[str] | None = Field(
        default=None,
        description="Restrict regeneration to these :Content uids. None = all.",
    )
    force: bool = Field(
        default=False,
        description="Regenerate even when chunks already match the current "
        "CHUNKING_ALGORITHM_VERSION. False = skip up-to-date parents.",
    )
