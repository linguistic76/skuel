"""
Shared Test Fixtures for SKUEL
==============================

Root conftest: loads ``.env`` and re-exports the embedding mocks for every tier.

The app fixture (``skuel_app``) lives in ``tests/integration/conftest.py`` — it
bootstraps the whole app, which needs a graph, and the only graphs a test may
touch are integration testcontainers. Keeping it there, next to the container
fixtures, is what stops ``.env``'s ``NEO4J_URI`` (the production AuraDB
instance since 2026-08-15) from ever becoming a test target again.

``load_dotenv()`` still runs here for everything else ``.env`` carries into the
process — the credential-backend selector, the intelligence tier, vault paths —
so an integration test sees the same non-database configuration the developer
runs the app with. It does not override a variable that is already set.
"""

# Load .env before any other imports (required for integration tests)
from dotenv import load_dotenv

load_dotenv()


# ============================================================================
# EMBEDDING & VECTOR SEARCH FIXTURES
# ============================================================================
# Import fixtures from embedding_fixtures module to make them available
# for all tests without explicit imports

from tests.fixtures.embedding_fixtures import (  # noqa: E402
    mock_embedding_vector,
    mock_embeddings_service,
    mock_embeddings_unavailable,
    mock_vector_search_service,
    mock_vector_search_unavailable,
    services_with_embeddings,
)

# Explicitly expose fixtures for pytest discovery
__all__ = [
    "mock_embedding_vector",
    "mock_embeddings_service",
    "mock_embeddings_unavailable",
    "mock_vector_search_service",
    "mock_vector_search_unavailable",
    "services_with_embeddings",
]
