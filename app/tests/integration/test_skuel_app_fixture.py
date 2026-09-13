"""
The ``skuel_app`` fixture boots the app against the integration testcontainer.

``bootstrap_skuel()`` takes its Neo4j target from the process environment, and
``tests/conftest.py`` fills that environment from the developer's ``.env`` —
which since the AuraDB cutover (2026-08-15) names the PRODUCTION graph. A
session-scoped app fixture with no dependency on the container fixture
therefore boots against production while looking, from the test's side,
exactly like one that doesn't. Nothing in a passing run distinguishes the two;
only the server's own report does.

These tests are that report, kept permanent: the app's driver must reach a
container (the calendar-pinned kernel, never an ``-aura`` one), and it must be
the app fixture's OWN container — a version match alone would also pass
against a self-hosted sandbox on the pinned image.

Gated on what ``bootstrap_skuel()`` itself demands (``OPENAI_API_KEY`` through
``EnvironmentValidator.REQUIRED_VARS``), not on Askesis — the fixture is
tier-independent.
"""

import pytest
from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential
from tests.integration._neo4j_pin import NEO4J_SERVER_VERSION, running_kernel_version

pytestmark = pytest.mark.skipif(
    not get_credential("OPENAI_API_KEY"),
    reason="bootstrap_skuel() requires OPENAI_API_KEY (EnvironmentValidator.REQUIRED_VARS)",
)

_MARKER_UID = "skuel_app_fixture_probe"


@pytest.mark.asyncio
async def test_app_driver_reaches_the_pinned_testcontainer_kernel(skuel_app) -> None:
    """The bootstrapped app's own driver reports the calendar-pinned kernel."""
    version = await running_kernel_version(skuel_app.state.services.neo4j_driver)

    assert version == NEO4J_SERVER_VERSION, (
        f"skuel_app bootstrapped against a Neo4j kernel reporting {version!r}, not the "
        f"pinned testcontainer ({NEO4J_SERVER_VERSION!r}). An '-aura' suffix means the "
        "app read .env's NEO4J_URI — the production graph. The fixture repoints "
        "NEO4J_URI at the container BEFORE settings are built; check that ordering."
    )


@pytest.mark.asyncio
async def test_app_driver_reaches_the_app_fixtures_own_container(
    skuel_app, skuel_app_container
) -> None:
    """A node written straight into the app's container is visible through the app's driver.

    Positive control for the kernel check: same version proves the same
    *release*, this proves the same *database* — the one ``skuel_app_container``
    started, not the shared ``neo4j_container`` and not a sandbox.
    """
    app_driver = skuel_app.state.services.neo4j_driver
    direct = AsyncGraphDatabase.driver(skuel_app_container.get_connection_url())
    try:
        async with direct.session() as session:
            await session.run("MERGE (:FixtureProbe {uid: $uid})", uid=_MARKER_UID)
        try:
            async with app_driver.session() as session:
                result = await session.run(
                    "MATCH (p:FixtureProbe {uid: $uid}) RETURN count(p) AS n", uid=_MARKER_UID
                )
                record = await result.single()
            assert record is not None and record["n"] == 1, (
                "skuel_app's driver cannot see a node just written into skuel_app_container — "
                "the app bootstrapped against a different graph."
            )
        finally:
            async with direct.session() as session:
                await session.run("MATCH (p:FixtureProbe {uid: $uid}) DELETE p", uid=_MARKER_UID)
    finally:
        await direct.close()
