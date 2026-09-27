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

``laptop_zone`` is the one clock fixture shared by every tier (opt-in, never
autouse): see its docstring.
"""

# Load .env before any other imports (required for integration tests)
from dotenv import load_dotenv

load_dotenv()

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402

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
from tests.helpers.forced_zone import forced_zone  # noqa: E402

# ============================================================================
# CLOCK FIXTURE — the laptop's case
# ============================================================================


@pytest.fixture
def laptop_zone(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The laptop's case: the host clock and the app default zone agree.

    Both are America/Vancouver: the process zone is forced (``forced_zone``) and
    ``SKUEL_TIMEZONE`` is removed, so the default is ``DEFAULT_TIMEZONE``. CI and
    the cloud run UTC, where a calendar day read on the host clock — a report
    period's bounds, a date-only completion widened to its first instant — sits
    seven or eight hours from midnight, and "earlier today" on the host clock is
    later today in Vancouver. A test whose expectations are the laptop's opts in:
    ``pytestmark = pytest.mark.usefixtures("laptop_zone")``.
    """
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    with forced_zone("America/Vancouver"):
        yield


# Explicitly expose fixtures for pytest discovery
__all__ = [
    "laptop_zone",
    "mock_embedding_vector",
    "mock_embeddings_service",
    "mock_embeddings_unavailable",
    "mock_vector_search_service",
    "mock_vector_search_unavailable",
    "services_with_embeddings",
]
