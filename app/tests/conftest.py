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
runs the app with. It does not override a variable that is already set. The two
exceptions are ``SKUEL_DEFAULT_USER_UID`` and ``SKUEL_CONTENT_VAULT_OWNER``: the run
names them (``tests/helpers/ingestion_owner.py``), so the owner never differs by
machine.

The process clock is pinned to UTC before anything else runs, as every entry
point pins it (``core/utils/process_clock.py``): the graph driver factory refuses
an unpinned process. A test of the unpinned behaviour forces a zone for its own
block (``forced_zone``, ``laptop_zone``), which restores the pin when it exits.

``laptop_zone`` is the one clock fixture shared by every tier (opt-in, never
autouse): see its docstring.
"""

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()

# Load .env before any other imports (required for integration tests)
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# The run names its ingestion owner — no account stands in for an unnamed one, and
# a developer's .env would otherwise make the owner differ by machine. Set before
# any fixture builds a config that reads it.
import os  # noqa: E402

from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER  # noqa: E402

os.environ["SKUEL_DEFAULT_USER_UID"] = INGESTION_TEST_OWNER
os.environ["SKUEL_CONTENT_VAULT_OWNER"] = INGESTION_TEST_OWNER

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

# ============================================================================
# CLOCK FIXTURE — the laptop's case
# ============================================================================


@pytest.fixture
def laptop_zone(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The laptop's case: a user on the app default zone, America/Vancouver.

    ``SKUEL_TIMEZONE`` is removed, so the default is ``DEFAULT_TIMEZONE``; the
    process stays pinned to UTC, as the app's is. A stamp written at a moment on
    the laptop's wall clock is stored as that moment's UTC digits
    (``tests/helpers/laptop_clock.py``). A test whose expectations are a
    Vancouver user's opts in: ``pytestmark = pytest.mark.usefixtures("laptop_zone")``.
    """
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
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
