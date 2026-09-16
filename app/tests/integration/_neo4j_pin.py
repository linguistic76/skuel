"""
The pinned Neo4j server image, read from the ONE place it is authored.

ADR-067 § 3a pins the server to an exact calendar release (``neo4j:YYYY.MM.N``)
in ``infrastructure/docker-compose.yml``, and this module is its single reader:
every integration container (``conftest``'s shared one, the app fixture's own,
the APOC-lockdown suite's) starts the image it names, and the version canary
asserts the running server reports exactly it — so a bump is one line in one
file and the readers agree by construction (the ADR records why a copy is
never kept).

The tag is validated, not just read: a floating tag (``neo4j:latest``,
``neo4j:2026``), a suffixed one (``…-community``), or a missing service fails
loudly at import — ADR-067's "never a floating tag" rule enforced at the only
reader that could silently tolerate one. YAML-parsed, so a validly quoted
``image: "neo4j:2026.07.1"`` reads the same as the bare form.

``running_kernel_version`` is the other half of the comparison: what the server
on the far end of a driver actually reports. The version canary compares the
two, and the ``skuel_app`` fixture refuses to yield an app whose driver reports
anything else — an AuraDB kernel reports ``5.27-aura``, never a calendar tag.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# tests/integration/_neo4j_pin.py → parents: [0] integration, [1] tests, [2] app, [3] repo root
COMPOSE_FILE = Path(__file__).resolve().parents[3] / "infrastructure" / "docker-compose.yml"

_EXACT_CALENDAR_TAG = re.compile(r"^neo4j:\d{4}\.\d{2}\.\d+$")


def neo4j_image_from_compose(compose_file: Path = COMPOSE_FILE) -> str:
    """Return the exact ``neo4j:YYYY.MM.N`` tag the compose file's ``neo4j`` service pins.

    Raises ``RuntimeError`` when the service or its image is missing, or the tag
    is not an exact calendar release — the integration session must fail, not
    fall back (ADR-067 § 3a: exact calendar tag, never floating).
    """
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = document.get("services") if isinstance(document, dict) else None
    service = services.get("neo4j") if isinstance(services, dict) else None
    image = service.get("image") if isinstance(service, dict) else None
    if not isinstance(image, str) or not _EXACT_CALENDAR_TAG.match(image):
        raise RuntimeError(
            f"{compose_file}: `services.neo4j.image` must be an exact `neo4j:YYYY.MM.N` "
            f"calendar tag, found {image!r} (ADR-067 § 3a: exact calendar tag, never floating)"
        )
    return image


NEO4J_IMAGE: str = neo4j_image_from_compose()
"""``neo4j:2026.07.1``-shaped tag every integration container starts."""

NEO4J_SERVER_VERSION: str = NEO4J_IMAGE.removeprefix("neo4j:")
"""What ``CALL dbms.components()`` must report for the running container."""


async def running_kernel_version(driver: AsyncDriver) -> str:
    """The ``Neo4j Kernel`` version the server behind ``driver`` reports.

    ``CALL dbms.components()`` is the one procedure that names the server
    itself rather than its data, and it is callable on every deployment shape
    (container, self-host, AuraDB) — which is what makes it usable as a
    "which graph am I talking to" probe.
    """
    async with driver.session() as session:
        result = await session.run(
            "CALL dbms.components() "
            "YIELD name, versions "
            "WHERE name = 'Neo4j Kernel' "
            "RETURN versions[0] AS version"
        )
        record = await result.single()
    assert record is not None, "dbms.components() reported no 'Neo4j Kernel' component"
    return str(record["version"])
