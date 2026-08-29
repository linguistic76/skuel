"""
APOC Allowlist Lockdown Tests
=============================

The companion to ``test_apoc_canary.py``. The two modules answer different
questions and need opposite server configurations, which is why both exist:

===========================  ==========================  ======================
Module                       Question                    Container profile
===========================  ==========================  ======================
``test_apoc_canary.py``      "is the plugin alive?"      permissive (``apoc.*``)
``test_apoc_allowlist_...``  "is the lockdown on?"       production (compose)
===========================  ==========================  ======================

The canary CANNOT answer the second question. Its fixture
(``conftest.py::neo4j_container``) sets ``..._unrestricted`` to ``apoc.*`` and
never sets ``..._allowlist`` at all, so it is strictly more permissive than
compose — a green canary run is not evidence that the allowlist is intact, and
the canary would keep passing if the allowlist were widened or dropped.

WHAT THIS MODULE GUARDS
-----------------------
A procedure allowlist has two failure directions, and only testing both catches
a misconfiguration:

* **Too wide** — the lockdown silently stops applying (someone widens the knob
  to ``apoc.*``, or deletes it). Caught by the *refusal* tests below. This is
  the direction a success-only test can never catch, and the reason this module
  exists.
* **Too narrow** — the lockdown breaks something the product depends on.
  Caught by ``test_meta_namespace_call_is_allowed``.

NON-CIRCULARITY
---------------
Two properties keep these tests from grading their own homework:

1. **The container is configured FROM the compose files** — the APOC knobs, the
   plugin list, and the server image — not from constants hand-copied out of
   them. Widen ``docker-compose.yml`` to ``apoc.*`` and this container starts
   permissive, so the refusal tests fail. Every value this fixture supplies by
   fiat instead is a way for the suite to stay green over a broken dev stack:
   a hard-coded ``apoc.meta.*`` would pass over a wide-open config, a hard-coded
   image would validate a stale APOC after a version bump, and a hard-coded
   ``NEO4J_PLUGINS`` would keep asserting ``apoc.meta.*`` works after compose
   stopped installing the plugin at all.
2. **Every refusal is paired with a positive control** on the permissive
   canary container. An allowlist refusal and a *typo* in the probe query raise
   the identical ``Neo.ClientError.Procedure.ProcedureNotFound`` — so a bare
   "it raised" assertion would pass vacuously against a misspelled procedure
   name. Requiring the same query string to SUCCEED under the permissive
   profile is what proves the allowlist is doing the blocking.

MEASURED BEHAVIOUR (neo4j:2026.06.0)
------------------------------------
The allowlist gates user-defined FUNCTIONS as well as procedures, but they fail
differently — both are ``ClientError`` subclasses, so both are caught below:

* blocked procedure -> ``ClientError``, ``Neo.ClientError.Procedure.ProcedureNotFound``
* blocked function  -> ``CypherSyntaxError``, ``Neo.ClientError.Statement.SyntaxError``
  ("Unknown function 'x'")

Note ``apoc.version()`` is a FUNCTION, so it too sits outside ``apoc.meta.*``
and is refused in production — the canary's version check is one of the three
canaries the production profile blocks, not one of the two it permits.

COST
----
This module starts a SECOND Neo4j testcontainer (session-scoped, ~30-45s). It
starts only when this module runs; the rest of the integration suite is
unaffected.

See: /docs/patterns/CYPHER_VS_APOC_STRATEGY.md § Operational Hygiene
"""

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ClientError
from testcontainers.neo4j import Neo4jContainer  # type: ignore[import-untyped]

from tests.integration._neo4j_pin import NEO4J_IMAGE

# ============================================================================
# Compose configuration — the source of truth for the profile under test
# ============================================================================

ALLOWLIST_KEY = "NEO4J_dbms_security_procedures_allowlist"
UNRESTRICTED_KEY = "NEO4J_dbms_security_procedures_unrestricted"
PLUGINS_KEY = "NEO4J_PLUGINS"

# Everything the container needs to reproduce the deployed APOC profile. Every
# value the fixture would otherwise supply by fiat belongs here — each one is a
# way for this suite to stay green over a broken dev stack. The plugin list is
# the least obvious member: without it the fixture installs APOC itself, and the
# meta tests keep asserting `apoc.meta.*` works after compose stopped installing
# the plugin at all. Adding a key here extends the drift check automatically.
PROFILE_KEYS = (ALLOWLIST_KEY, UNRESTRICTED_KEY, PLUGINS_KEY)

# The intended lockdown. Hard-coded ON PURPOSE and used ONLY by the config-drift
# test — that test's whole job is to pin the value compose is allowed to declare.
# The behavioural tests below never read this constant; they run against whatever
# compose actually says, which is what makes them non-circular.
LOCKED_NAMESPACE = "apoc.meta.*"

_APP_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _APP_DIR.parent

# Both composes that define a neo4j service. app/docker-compose.yml `extends`
# the infrastructure one but re-declares these knobs, so both are checked.
COMPOSE_FILES: dict[str, Path] = {
    "infrastructure/docker-compose.yml": _REPO_ROOT / "infrastructure" / "docker-compose.yml",
    "app/docker-compose.yml": _APP_DIR / "docker-compose.yml",
}

# The base compose is the single source of truth for server config; the app
# compose only overrides deltas.
BASE_COMPOSE = "infrastructure/docker-compose.yml"


def _neo4j_service(compose_path: Path) -> dict[str, object]:
    """
    Parse the `neo4j` service block out of a compose file.

    Typed `object` rather than `Any`: a compose service block is genuinely
    heterogeneous (strings, dicts, lists), and callers narrow what they read.
    """
    assert compose_path.is_file(), f"compose file not found: {compose_path}"

    service = yaml.safe_load(compose_path.read_text())["services"]["neo4j"]
    assert isinstance(service, dict), f"{compose_path}: `services.neo4j` is not a mapping"
    return service


def _read_apoc_env(compose_path: Path) -> dict[str, str]:
    """Extract the APOC profile keys declared on the compose file's neo4j service."""
    environment = _neo4j_service(compose_path).get("environment", {})
    assert isinstance(environment, dict), (
        f"{compose_path} uses list-form `environment:`; this parser expects mapping form"
    )

    return {key: str(environment[key]) for key in PROFILE_KEYS if key in environment}


def resolve_locked_profile() -> dict[str, str]:
    """
    Build the container env for the production-shaped profile FROM compose.

    Returns the knobs exactly as the deployed dev stack declares them, so a
    change to compose changes what these tests run against.
    """
    base = _read_apoc_env(COMPOSE_FILES[BASE_COMPOSE])

    missing = set(PROFILE_KEYS) - base.keys()
    assert not missing, (
        f"{BASE_COMPOSE} no longer declares {sorted(missing)}. The APOC lockdown is "
        "config-only — if these knobs are gone, nothing constrains APOC at the server, "
        "and this fixture must not supply them by fiat."
    )
    return base


# ============================================================================
# Fixtures — the production-shaped container
# ============================================================================


@pytest.fixture(scope="session")
def locked_neo4j_container():
    """
    Neo4j configured with the compose APOC profile.

    Deliberately NOT the shared `neo4j_container` fixture, which is permissive
    on purpose so the canary can probe plugin liveness across all namespaces.

    Auth is disabled for test-harness convenience only; the procedure allowlist
    is a registration-level filter and applies regardless of auth (a blocked
    procedure reports as *not found*, not as *not permitted*).
    """
    # The pin is read by tests/integration/_neo4j_pin.py — the one reader every
    # integration container shares, so this suite can never validate allowlist
    # behaviour against a stale APOC on an old release (ADR-067 § 3a).
    container = Neo4jContainer(NEO4J_IMAGE)
    container.with_env("NEO4J_dbms_security_auth__enabled", "false")

    for key, value in resolve_locked_profile().items():
        container.with_env(key, value)

    container.start()
    yield container
    container.stop()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def locked_neo4j_driver(locked_neo4j_container) -> AsyncGenerator[AsyncDriver]:
    """Driver onto the production-shaped container."""
    driver = AsyncGraphDatabase.driver(
        locked_neo4j_container.get_connection_url(), auth=("neo4j", "testpassword")
    )

    async with driver.session() as session:
        result = await session.run("RETURN 1 AS test")
        record = await result.single()
        assert record["test"] == 1

    yield driver

    await driver.close()


# ============================================================================
# Probe corpus
# ============================================================================

# Calls OUTSIDE apoc.meta.* — the production profile must refuse every one.
# Each is exercised against BOTH containers (see the positive-control note in
# the module docstring).
OUT_OF_NAMESPACE_CALLS = [
    pytest.param(
        "apoc.periodic.iterate",
        "CALL apoc.periodic.iterate('RETURN 1 AS n', 'RETURN n', {batchSize: 1}) "
        "YIELD batches RETURN batches",
        id="periodic.iterate",
    ),
    pytest.param(
        "apoc.convert.fromJsonMap",
        'RETURN apoc.convert.fromJsonMap(\'{"name": "Test"}\') AS parsed',
        id="convert.fromJsonMap",
    ),
    # A function, and the call the canary's version check makes. Outside the
    # allowlisted namespace like the rest — production refuses it too.
    pytest.param(
        "apoc.version",
        "RETURN apoc.version() AS version",
        id="version",
    ),
    # Used by scripts/migrations/hash_session_tokens_2026_03.cypher. Its header
    # lists "APOC plugin installed" as the prerequisite, which is necessary but
    # NOT sufficient: the migrations are hand-run against a session configured
    # more permissively than compose. See CYPHER_VS_APOC_STRATEGY.md.
    pytest.param(
        "apoc.util.sha256",
        "RETURN apoc.util.sha256(['x']) AS digest",
        id="util.sha256",
    ),
]

# Calls INSIDE apoc.meta.* — the allowlist must not be so narrow it breaks these.
IN_NAMESPACE_CALLS = [
    pytest.param(
        "apoc.meta.graph",
        "CALL apoc.meta.graph() YIELD nodes, relationships RETURN nodes, relationships",
        id="meta.graph",
    ),
    pytest.param(
        "apoc.meta.nodeTypeProperties",
        "CALL apoc.meta.nodeTypeProperties() YIELD nodeType RETURN nodeType LIMIT 1",
        id="meta.nodeTypeProperties",
    ),
    pytest.param(
        "apoc.meta.stats",
        "CALL apoc.meta.stats() YIELD nodeCount RETURN nodeCount",
        id="meta.stats",
    ),
]


async def _execute(driver: AsyncDriver, query: str) -> None:
    """Run a query to completion, surfacing any server-side refusal."""
    async with driver.session() as session:
        result = await session.run(query)
        await result.consume()


# ============================================================================
# Tests
# ============================================================================


class TestApocAllowlistConfiguration:
    """The lockdown is config-only, so the config itself is part of the contract."""

    def test_compose_declares_the_locked_profile(self):
        """
        Both APOC knobs are declared on the base compose and pin apoc.meta.*.

        Catches the lockdown being widened or deleted at its source. The
        behavioural tests below would also catch it (they run against whatever
        compose says), but this failure names the file and the value directly.
        """
        base = _read_apoc_env(COMPOSE_FILES[BASE_COMPOSE])

        assert base.get(ALLOWLIST_KEY) == LOCKED_NAMESPACE, (
            f"{BASE_COMPOSE} declares {ALLOWLIST_KEY}={base.get(ALLOWLIST_KEY)!r}, "
            f"expected {LOCKED_NAMESPACE!r}. Widening the allowlist admits APOC "
            "namespaces the architecture says are unavailable (SKUEL001)."
        )
        assert base.get(UNRESTRICTED_KEY) == LOCKED_NAMESPACE, (
            f"{BASE_COMPOSE} declares {UNRESTRICTED_KEY}={base.get(UNRESTRICTED_KEY)!r}, "
            f"expected {LOCKED_NAMESPACE!r}."
        )

    def test_compose_declares_the_apoc_plugin(self):
        """
        The base compose still installs APOC.

        Without this the allowlist tests could be read as proving `apoc.meta.*`
        works in the deployed profile, when a compose change had removed the
        plugin outright — the fixture takes the plugin list from compose, so
        this names the regression instead of leaving it to a confusing refusal.
        """
        declared = _read_apoc_env(COMPOSE_FILES[BASE_COMPOSE]).get(PLUGINS_KEY)
        assert declared is not None, f"{BASE_COMPOSE} no longer declares {PLUGINS_KEY}."

        plugins = json.loads(declared)
        assert "apoc" in plugins, (
            f"{BASE_COMPOSE} declares {PLUGINS_KEY}={declared!r}, which does not install "
            "APOC. The allowlist is moot without the plugin, and every apoc.meta.* call "
            "the product's schema tooling relies on would be unavailable."
        )

    def test_no_compose_file_overrides_the_base_profile(self):
        """
        Every profile key declared in any compose file agrees with the base.

        Deliberately general over every PROFILE_KEYS/COMPOSE_FILES pair, not a
        list of specific assertions. The container is built from the BASE
        compose alone, so any file that overrides a profile key to a different
        value runs a stack this suite is not testing — and `app/` is the primary
        dev workflow, not a secondary. Enumerating the pairs by hand is how the
        plugin override got missed once already; adding a key to PROFILE_KEYS or
        a file to COMPOSE_FILES now extends this check automatically.
        """
        base = resolve_locked_profile()

        for label, path in COMPOSE_FILES.items():
            if label == BASE_COMPOSE:
                continue  # the reference itself; pinned by the two tests above

            for key, value in _read_apoc_env(path).items():
                assert value == base[key], (
                    f"{label} overrides {key} to {value!r}, disagreeing with "
                    f"{BASE_COMPOSE}'s {base[key]!r}. That stack would run a different "
                    "APOC profile than the one this suite builds and tests."
                )


@pytest.mark.asyncio
class TestApocAllowlistEnforcement:
    """The production profile, exercised against a real server."""

    @pytest.mark.parametrize(("procedure", "query"), OUT_OF_NAMESPACE_CALLS)
    async def test_out_of_namespace_call_is_refused(
        self,
        neo4j_driver: AsyncDriver,
        locked_neo4j_driver: AsyncDriver,
        procedure: str,
        query: str,
    ):
        """
        A call outside apoc.meta.* is refused under the compose profile.

        THE valuable assertion: a test that only checks procedures succeed
        cannot catch an allowlist that is too wide.
        """
        # Positive control. A refusal and a typo'd procedure name raise the SAME
        # ProcedureNotFound, so without this the assertion below would pass
        # vacuously against a misspelled probe. Failure here means the probe is
        # broken, not that the lockdown is.
        await _execute(neo4j_driver, query)

        with pytest.raises(ClientError) as exc_info:
            await _execute(locked_neo4j_driver, query)

        assert procedure in str(exc_info.value), (
            f"Expected the refusal to name {procedure}, got: {exc_info.value}. "
            "A different error means the query failed for some other reason and "
            "this test is not measuring the allowlist."
        )

    @pytest.mark.parametrize(("procedure", "query"), IN_NAMESPACE_CALLS)
    async def test_meta_namespace_call_is_allowed(
        self, locked_neo4j_driver: AsyncDriver, procedure: str, query: str
    ):
        """
        apoc.meta.* still works under the compose profile.

        The other failure direction: an allowlist narrowed past what the
        allowlisted namespace is supposed to permit.
        """
        await _execute(locked_neo4j_driver, query)
