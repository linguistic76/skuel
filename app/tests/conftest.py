"""
Shared Test Fixtures for SKUEL
==============================

Root conftest: loads ``.env`` and re-exports the embedding mocks for every tier.

No app or database fixture lives here. The app fixture (``skuel_app``) is in
``tests/integration/conftest.py``: it bootstraps the whole app, which needs a
graph, and the only graphs a test may touch are integration testcontainers —
never the graph ``.env``'s ``NEO4J_URI`` names, which is the production AuraDB
instance.

``load_dotenv()`` runs here for everything else ``.env`` carries into the
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
