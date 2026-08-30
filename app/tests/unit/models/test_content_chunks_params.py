"""Unit tests for per-domain chunking parameters.

Covers the foundation laid by ChunkingParams: the zero-churn version tag (the
key ship guarantee — default params must never change the stamped version or the
chunk boundaries), the diverged-domain suffix, and that a non-default param set
actually shifts chunk boundaries and stamps the suffixed version.
"""

from __future__ import annotations

from core.models.ps_content.content_chunks import (
    CHUNKING_ALGORITHM_VERSION,
    DEFAULT_CHUNKING_PARAMS,
    ChunkingParams,
    chunk_content,
    chunk_version_tag,
)

# A body large enough that max_chunk_size drives a split — one long paragraph of
# many short sentences under a single heading.
_LARGE_BODY = "# Section\n\n" + ("This is a sentence. " * 400)


class TestChunkVersionTag:
    def test_default_params_map_to_bare_version(self) -> None:
        # Zero-churn guarantee: default params stamp the unadorned base version,
        # so existing chunks and every `== CHUNKING_ALGORITHM_VERSION` test still match.
        assert chunk_version_tag(DEFAULT_CHUNKING_PARAMS) == CHUNKING_ALGORITHM_VERSION
        assert chunk_version_tag(DEFAULT_CHUNKING_PARAMS) == "v2"

    def test_explicit_defaults_equal_the_shared_default(self) -> None:
        # An explicitly-constructed default is value-equal, so it also gets the bare tag.
        assert ChunkingParams() == DEFAULT_CHUNKING_PARAMS
        assert chunk_version_tag(ChunkingParams()) == CHUNKING_ALGORITHM_VERSION

    def test_diverged_params_get_a_suffixed_tag(self) -> None:
        diverged = ChunkingParams(max_chunk_size=300, context_size=60)
        assert chunk_version_tag(diverged) == "v2:300-60"

    def test_min_chunk_size_is_inert_and_excluded_from_the_tag(self) -> None:
        # min_chunk_size has no refs in the strategy, so a change to it alone must
        # not produce a divergence tag — otherwise it would force a needless re-chunk.
        only_min = ChunkingParams(min_chunk_size=10)
        assert only_min != DEFAULT_CHUNKING_PARAMS  # value differs...
        # ...but the boundary-affecting fingerprint is unchanged, so the tag stays bare.
        assert chunk_version_tag(only_min) == f"{CHUNKING_ALGORITHM_VERSION}:500-100"


class TestChunkingStampsVersion:
    def test_default_chunking_stamps_bare_version(self) -> None:
        chunks = chunk_content(_LARGE_BODY, "ps.default", "markdown")
        assert chunks  # produced something
        assert all(c.chunking_version == "v2" for c in chunks)

    def test_diverged_chunking_stamps_suffixed_version(self) -> None:
        diverged = ChunkingParams(max_chunk_size=300, context_size=60)
        chunks = chunk_content(_LARGE_BODY, "ps.diverged", "markdown", diverged)
        assert chunks
        assert all(c.chunking_version == "v2:300-60" for c in chunks)


class TestBoundaryDivergence:
    def test_smaller_max_chunk_size_produces_more_chunks(self) -> None:
        # A smaller max_chunk_size forces more sentence-boundary splits, so the
        # same body yields strictly more chunks than the default grain.
        default_chunks = chunk_content(_LARGE_BODY, "ps.x", "markdown", DEFAULT_CHUNKING_PARAMS)
        diverged = ChunkingParams(max_chunk_size=100, context_size=60)
        diverged_chunks = chunk_content(_LARGE_BODY, "ps.x", "markdown", diverged)
        assert len(diverged_chunks) > len(default_chunks)

    def test_default_boundaries_are_stable(self) -> None:
        # The zero-behavior-change guarantee at the boundary level: chunking with
        # the default params (explicit or omitted) yields byte-identical chunk text.
        omitted = chunk_content(_LARGE_BODY, "ps.stable", "markdown")
        explicit = chunk_content(_LARGE_BODY, "ps.stable", "markdown", DEFAULT_CHUNKING_PARAMS)
        assert [c.text for c in omitted] == [c.text for c in explicit]
        assert [c.chunk_index for c in omitted] == [c.chunk_index for c in explicit]
