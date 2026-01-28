# Embedding Fixtures Usage Guide

## Overview

The embedding fixtures provide mock implementations of the Neo4j GenAI embeddings and vector search services. These fixtures enable testing of semantic search functionality without making actual API calls to OpenAI or requiring the Neo4j GenAI plugin.

**Location:** `tests/fixtures/embedding_fixtures.py`

## Available Fixtures

### `mock_embedding_vector`

Generates a consistent 1536-dimensional embedding vector for testing.

```python
def test_something(mock_embedding_vector):
    assert len(mock_embedding_vector) == 1536
    assert all(isinstance(x, float) for x in mock_embedding_vector)
```

### `mock_embeddings_service`

Mock implementation of `Neo4jGenAIEmbeddingsService` that returns deterministic embeddings without API calls.

**Methods:**
- `create_embedding(text, metadata=None)` - Generate single embedding
- `create_batch_embeddings(texts, metadata_list=None)` - Generate batch embeddings
- `calculate_similarity(embedding1, embedding2)` - Calculate cosine similarity

**Attributes:**
- `model` - "text-embedding-3-small"
- `dimension` - 1536
- `_plugin_available` - True

**Example:**
```python
@pytest.mark.asyncio
async def test_semantic_search(mock_embeddings_service):
    result = await mock_embeddings_service.create_embedding("Python programming")

    assert result.is_ok
    embedding = result.value
    assert len(embedding) == 1536
```

### `mock_vector_search_service`

Mock implementation of `Neo4jVectorSearchService` that returns predefined similar nodes without Neo4j queries.

**Methods:**
- `find_similar_by_vector(label, embedding, limit=10, min_score=0.7)`
- `find_similar_by_text(label, text, limit=10, min_score=0.7)`
- `find_similar_to_node(label, uid, limit=10, min_score=0.7, exclude_self=True)`
- `find_cross_domain_similar(embedding, labels, limit_per_label=5, min_score=0.7)`

**Example:**
```python
@pytest.mark.asyncio
async def test_vector_search(mock_vector_search_service):
    result = await mock_vector_search_service.find_similar_by_vector(
        label="Ku",
        embedding=[0.1] * 1536,
        limit=5
    )

    assert result.is_ok
    similar = result.value
    for item in similar:
        assert "node" in item
        assert "score" in item
```

### `services_with_embeddings`

Convenience fixture that provides both embeddings and vector search services in a dict.

**Example:**
```python
@pytest.mark.asyncio
async def test_ku_search(services_with_embeddings):
    ku_search = KuSearchService(
        backend=mock_backend,
        embeddings_service=services_with_embeddings["embeddings"],
        vector_search_service=services_with_embeddings["vector_search"]
    )

    result = await ku_search.find_similar_content("ku.python", limit=5)
    assert result.is_ok
```

### `mock_embeddings_unavailable`

Mock embeddings service that simulates the GenAI plugin being unavailable. Use this to test graceful degradation.

**Example:**
```python
@pytest.mark.asyncio
async def test_fallback_when_embeddings_unavailable(mock_embeddings_unavailable):
    result = await mock_embeddings_unavailable.create_embedding("Test")

    assert result.is_error
    error = result.expect_error()
    assert "unavailable" in str(error).lower()
```

### `mock_vector_search_unavailable`

Mock vector search service that simulates vector indexes being unavailable. Use this to test graceful degradation.

**Example:**
```python
@pytest.mark.asyncio
async def test_fallback_when_vector_search_unavailable(mock_vector_search_unavailable):
    result = await mock_vector_search_unavailable.find_similar_by_vector(
        label="Ku",
        embedding=[0.1] * 1536,
        limit=5
    )

    assert result.is_error
```

## Usage Patterns

### Testing Semantic Search with Embeddings

```python
@pytest.mark.asyncio
async def test_semantic_search_with_embeddings(services_with_embeddings):
    """Test semantic search when embeddings available."""

    ku_search = KuSearchService(
        backend=mock_backend,
        vector_search_service=services_with_embeddings["vector_search"],
        embeddings_service=services_with_embeddings["embeddings"]
    )

    result = await ku_search.find_similar_content("ku.python", limit=5)

    assert result.is_ok
    similar = result.value
    assert len(similar) > 0
```

### Testing Fallback Without Embeddings

```python
@pytest.mark.asyncio
async def test_semantic_search_fallback_without_embeddings():
    """Test fallback to keyword search when embeddings unavailable."""

    ku_search = KuSearchService(
        backend=mock_backend,
        vector_search_service=None,  # No vector search
        embeddings_service=None  # No embeddings
    )

    result = await ku_search.find_similar_content("ku.python", limit=5)

    assert result.is_ok  # Should not fail
    # Should use keyword search fallback
```

### Testing Both Available and Unavailable Scenarios

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "embeddings_fixture,expected_method",
    [
        ("mock_embeddings_service", "vector_search"),
        ("mock_embeddings_unavailable", "keyword_search"),
    ],
)
async def test_search_with_different_availability(embeddings_fixture, expected_method, request):
    """Test search behavior with different embedding availability."""

    embeddings_service = request.getfixturevalue(embeddings_fixture)

    search_service = create_search_service(embeddings_service=embeddings_service)

    result = await search_service.search("Python")

    assert result.is_ok
    # Verify correct fallback behavior
```

## Fixture Auto-Discovery

All embedding fixtures are automatically available in tests because they are imported in `tests/conftest.py`. You don't need to import them manually - just declare them as test parameters:

```python
# ✅ GOOD - Fixtures auto-discovered
@pytest.mark.asyncio
async def test_something(mock_embeddings_service, mock_vector_search_service):
    # Use fixtures directly
    pass

# ❌ NOT NEEDED - Don't manually import fixtures
from tests.fixtures.embedding_fixtures import mock_embeddings_service  # Unnecessary!
```

## Implementation Notes

### Deterministic Embeddings

The mock embeddings are deterministic based on text length, making tests reproducible:

```python
# Same text → same embedding
result1 = await mock_embeddings_service.create_embedding("Test")
result2 = await mock_embeddings_service.create_embedding("Test")
assert result1.value == result2.value

# Different text length → different embedding
result3 = await mock_embeddings_service.create_embedding("A much longer test")
assert result1.value[0] != result3.value[0]  # First element varies by length
```

### Result Pattern Compliance

All fixtures follow SKUEL's `Result[T]` pattern:

- Success: `Result.ok(value)`
- Error: `Result.fail(error_dict)`
- Check: `result.is_ok` or `result.is_error`
- Extract: `result.value` or `result.expect_error()`

### Vector Search Behavior

The mock vector search returns up to 3 results with descending similarity scores (0.9, 0.8, 0.7), respecting `min_score` and `limit` parameters:

```python
result = await mock_vector_search_service.find_similar_by_vector(
    label="Ku",
    embedding=[0.1] * 1536,
    limit=5,
    min_score=0.8  # Only returns first 2 results (0.9, 0.8)
)
```

## Test Examples

See `tests/integration/test_embedding_fixtures_usage.py` for comprehensive examples of:

- Embedding generation and validation
- Batch embedding generation
- Similarity calculation
- Vector search by embedding, text, and node
- Cross-domain search
- Graceful degradation scenarios
- Determinism and variance testing

## Integration with Domain Services

When testing domain services that use semantic search (KU, Tasks, Goals, etc.), inject the mock services:

```python
@pytest.mark.asyncio
async def test_ku_semantic_relationships(services_with_embeddings):
    """Test KU semantic relationships with mock embeddings."""

    ku_service = KuService(
        backend=mock_ku_backend,
        embeddings_service=services_with_embeddings["embeddings"],
        vector_search_service=services_with_embeddings["vector_search"],
    )

    # Test semantic operations
    result = await ku_service.find_related_concepts("ku.python-basics")
    assert result.is_ok
```

## Success Criteria Checklist

Phase 6.1 completion criteria:

- ✅ Mock fixtures created (`embedding_fixtures.py`)
- ✅ Tests run without API calls
- ✅ Tests cover both available and unavailable scenarios
- ✅ Fixtures easily reusable across test files
- ✅ Auto-discovery via `conftest.py`
- ✅ Comprehensive usage examples
- ✅ Documentation provided

## Future Enhancements

Potential improvements for future iterations:

1. **Similarity Tuning:** Allow configuring similarity scores per test
2. **Embedding Caching:** Mock embedding cache for performance testing
3. **Error Scenarios:** Additional error conditions (rate limits, timeouts)
4. **Cross-Domain Patterns:** Pre-configured multi-domain search scenarios
5. **Vector Index Simulation:** Mock vector index creation and management

## Related Files

- `app/core/services/neo4j_genai_embeddings_service.py` - Real embeddings service
- `app/core/services/neo4j_vector_search_service.py` - Real vector search service
- `tests/conftest.py` - Fixture auto-discovery configuration
- `tests/integration/test_embedding_fixtures_usage.py` - Usage examples
