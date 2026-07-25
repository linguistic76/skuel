"""
Unit tests for embedding versioning system.

Tests version tracking, metadata storage, and cache-first retrieval.

Created: January 2026
Updated: March 2026 — HuggingFace migration (1536→1024 dims, v1→v2)
Updated: April 2026 — EmbeddingsBackend migration (executor → typed backend)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    EmbeddingsService,
)
from core.utils.embedding_text_builder import hash_embedding_text
from core.utils.result_simplified import Errors, Result

# Dimension for BAAI/bge-m3 (dense) — EmbeddingGeometry.DIMENSION
DIM = 1024


@pytest.fixture
def mock_backend():
    """Mock EmbeddingsBackend for testing."""
    backend = MagicMock()
    backend.store_embedding_metadata = AsyncMock()
    backend.get_embedding_metadata = AsyncMock()
    backend.get_cached_embedding = AsyncMock()
    backend.get_embedding_freshness = AsyncMock()
    backend.touch_embedding_updated_at = AsyncMock(return_value=Result.ok([{"touched": 1}]))
    backend.stamp_embedding_text_hashes = AsyncMock()
    return backend


@pytest.fixture
def embeddings_service(mock_backend):
    """Create embeddings service with mock backend + inference client.

    These tests exercise version/metadata storage logic, which uses the backend
    — the injected inference client is never called.
    """
    mock_client = MagicMock()
    mock_client.model = "BAAI/bge-m3"
    mock_client.dimension = DIM
    mock_client.max_input_chars = 20000
    mock_client.embed = AsyncMock()
    return EmbeddingsService(mock_backend, embedding_client=mock_client)


@pytest.mark.asyncio
async def test_embedding_version_constant():
    """Test that EMBEDDING_VERSION is defined."""
    assert EMBEDDING_VERSION is not None
    assert isinstance(EMBEDDING_VERSION, str)
    assert EMBEDDING_VERSION.startswith("v")
    assert EMBEDDING_VERSION == "v3"  # ADR-068: OpenAI text-embedding-3-small @1024


@pytest.mark.asyncio
async def test_store_embedding_with_metadata(embeddings_service, mock_backend):
    """Test storing embedding with version metadata."""
    # Mock successful update
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.python"}])

    embedding = [0.1] * DIM

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.python", label="Entity", embedding=embedding, text="Python programming"
    )

    assert result.is_ok

    # Verify backend method was called — the hash of the embedded text is
    # stored, not the text itself (embedding_text_hash supersedes
    # embedding_source_text on entities)
    mock_backend.store_embedding_metadata.assert_called_once_with(
        label="Entity",
        uid="ku.python",
        embedding=embedding,
        version=EMBEDDING_VERSION,
        model="BAAI/bge-m3",
        text_hash=hash_embedding_text("Python programming"),
    )


@pytest.mark.asyncio
async def test_store_embedding_node_not_found(embeddings_service, mock_backend):
    """Test storing embedding when node doesn't exist."""
    # Mock no results (node not found)
    mock_backend.store_embedding_metadata.return_value = Result.ok([])

    embedding = [0.1] * DIM

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.nonexistent", label="Entity", embedding=embedding, text="gone"
    )

    assert result.is_error
    assert "not_found" in str(result.error).lower()


@pytest.mark.asyncio
async def test_get_embedding_metadata(embeddings_service, mock_backend):
    """Test getting embedding metadata."""
    # Mock metadata response
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v2",
                "model": "BAAI/bge-large-en-v1.5",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.get_embedding_metadata(uid="ku.python", label="Entity")

    assert result.is_ok
    metadata = result.value

    assert metadata["has_embedding"] is True
    assert metadata["version"] == "v2"
    assert metadata["model"] == "BAAI/bge-large-en-v1.5"
    assert metadata["updated_at"] == "2026-03-12T12:00:00Z"
    assert metadata["dimension"] == DIM


@pytest.mark.asyncio
async def test_get_embedding_metadata_no_embedding(embeddings_service, mock_backend):
    """Test getting metadata when node has no embedding."""
    # Mock node with no embedding
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [{"embedding": None, "version": None, "model": None, "updated_at": None}]
    )

    result = await embeddings_service.get_embedding_metadata(uid="ku.test", label="Entity")

    assert result.is_ok
    metadata = result.value

    assert metadata["has_embedding"] is False
    assert metadata["version"] is None
    assert metadata["model"] is None
    assert metadata["dimension"] is None


@pytest.mark.asyncio
async def test_check_version_compatibility_current(embeddings_service, mock_backend):
    """Test version compatibility check for current version."""
    # Mock current version
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": EMBEDDING_VERSION,
                "model": "text-embedding-3-small",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is True
    assert compat["node_version"] == EMBEDDING_VERSION
    assert compat["current_version"] == EMBEDDING_VERSION
    assert compat["needs_update"] is False
    assert compat["has_embedding"] is True


@pytest.mark.asyncio
async def test_check_version_compatibility_stale(embeddings_service, mock_backend):
    """Test version compatibility check for stale version."""
    # Mock old version
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v1",  # Old version
                "model": "text-embedding-3-small",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] == "v1"
    assert compat["current_version"] == EMBEDDING_VERSION
    assert compat["needs_update"] is True  # Has embedding but wrong version
    assert compat["has_embedding"] is True


@pytest.mark.asyncio
async def test_check_version_compatibility_no_version(embeddings_service, mock_backend):
    """Test version compatibility when node has embedding but no version."""
    # Mock embedding without version metadata
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [{"embedding": [0.1] * DIM, "version": None, "model": None, "updated_at": None}]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] is None
    assert compat["needs_update"] is True  # Has embedding but no version


# ---------------------------------------------------------------------------
# verify_fresh_embeddings — THE pre-generation skip decision
# ---------------------------------------------------------------------------


def _freshness_row(uid: str, text: str, **overrides) -> dict:
    row = {
        "uid": uid,
        "has_embedding": True,
        "version": EMBEDDING_VERSION,
        "text_hash": hash_embedding_text(text),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_verify_fresh_skips_hash_match(embeddings_service, mock_backend):
    """Version-current + hash-equal → fresh, and embedding_updated_at is touched."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "same text")]
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "same text"})

    assert result.is_ok
    assert result.value == {"ku.a"}
    mock_backend.touch_embedding_updated_at.assert_awaited_once_with(["ku.a"])


@pytest.mark.asyncio
async def test_verify_fresh_reembeds_on_text_change(embeddings_service, mock_backend):
    """A changed text hashes differently → not fresh, no touch."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "old text")]
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "new text"})

    assert result.is_ok
    assert result.value == set()
    mock_backend.touch_embedding_updated_at.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_fresh_version_outranks_hash(embeddings_service, mock_backend):
    """A version mismatch is NEVER fresh — a model migration must re-embed
    even when the text hash matches exactly."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "same text", version="v2")]
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "same text"})

    assert result.is_ok
    assert result.value == set()


@pytest.mark.asyncio
async def test_verify_fresh_null_hash_is_not_fresh(embeddings_service, mock_backend):
    """Pre-rollout nodes (no hash yet) are never skipped."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "same text", text_hash=None)]
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "same text"})

    assert result.is_ok
    assert result.value == set()


@pytest.mark.asyncio
async def test_verify_fresh_missing_embedding_is_not_fresh(embeddings_service, mock_backend):
    """A node without an embedding can't be fresh regardless of metadata."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "same text", has_embedding=False)]
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "same text"})

    assert result.is_ok
    assert result.value == set()


@pytest.mark.asyncio
async def test_verify_fresh_empty_candidates_no_read(embeddings_service, mock_backend):
    """No candidates → no backend round-trip."""
    result = await embeddings_service.verify_fresh_embeddings({})

    assert result.is_ok
    assert result.value == set()
    mock_backend.get_embedding_freshness.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_fresh_read_failure_propagates(embeddings_service, mock_backend):
    """A freshness-read failure is an error Result — callers fail OPEN on it."""
    mock_backend.get_embedding_freshness.return_value = Result.fail(
        Errors.database(operation="get_embedding_freshness", message="boom")
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "text"})

    assert result.is_error


@pytest.mark.asyncio
async def test_verify_fresh_touch_failure_keeps_verdict(embeddings_service, mock_backend):
    """A failed touch is a warning, not a verdict change — the node just
    re-enters the coarse filter and hash-skips again next run."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.a", "same text")]
    )
    mock_backend.touch_embedding_updated_at.return_value = Result.fail(
        Errors.database(operation="touch_embedding_updated_at", message="boom")
    )

    result = await embeddings_service.verify_fresh_embeddings({"ku.a": "same text"})

    assert result.is_ok
    assert result.value == {"ku.a"}


# ---------------------------------------------------------------------------
# stamp_embedding_hashes — one-shot hash rollout (no API calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stamp_hashes_uses_the_one_hash_recipe(embeddings_service, mock_backend):
    """Stamping hashes each text through hash_embedding_text and passes the
    current version so the backend's guards track the same constant."""
    mock_backend.stamp_embedding_text_hashes.return_value = Result.ok([{"stamped": 2}])

    result = await embeddings_service.stamp_embedding_hashes(
        "Entity", {"ku.a": "text a", "ku.b": "text b"}
    )

    assert result.is_ok
    assert result.value == 2
    mock_backend.stamp_embedding_text_hashes.assert_awaited_once_with(
        label="Entity",
        rows=[
            {"uid": "ku.a", "text_hash": hash_embedding_text("text a")},
            {"uid": "ku.b", "text_hash": hash_embedding_text("text b")},
        ],
        version=EMBEDDING_VERSION,
    )


@pytest.mark.asyncio
async def test_stamp_hashes_empty_is_noop(embeddings_service, mock_backend):
    result = await embeddings_service.stamp_embedding_hashes("Entity", {})

    assert result.is_ok
    assert result.value == 0
    mock_backend.stamp_embedding_text_hashes.assert_not_awaited()
