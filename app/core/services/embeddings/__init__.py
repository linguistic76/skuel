"""Embedding-coverage domain logic (the retrievability gauge)."""

from core.services.embeddings.retrievability import (
    BACKFILL_COMMAND,
    CHUNK_SCAN_LABELS,
    CONTENT_CHUNK_LABEL,
    EMBEDDABLE_LABELS,
    EMBEDDING_SCAN_LABELS,
    LABEL_EXTRA_FILTERS,
    REFERENCE_CHUNK_LABEL,
    REFERENCE_CHUNK_REMEDY,
    EmbeddingCoverage,
    LabelCoverage,
    label_backfill,
    remedy_text,
)

__all__ = [
    "BACKFILL_COMMAND",
    "CHUNK_SCAN_LABELS",
    "CONTENT_CHUNK_LABEL",
    "EMBEDDABLE_LABELS",
    "EMBEDDING_SCAN_LABELS",
    "LABEL_EXTRA_FILTERS",
    "REFERENCE_CHUNK_LABEL",
    "REFERENCE_CHUNK_REMEDY",
    "EmbeddingCoverage",
    "LabelCoverage",
    "label_backfill",
    "remedy_text",
]
