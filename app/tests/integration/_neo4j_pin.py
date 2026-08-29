"""
The pinned Neo4j server image, read from the ONE place it is authored.

ADR-067 § 3a pins the server to an exact calendar release (``neo4j:YYYY.MM.N``)
in ``infrastructure/docker-compose.yml``. The integration testcontainer and the
version canary used to carry a *copy* of that tag; both drifted from the compose
pin for a month unnoticed (2026.06.0 vs the published 2026.07.1). Deriving the
tag here means a bump is one line in one file, and CI's testcontainer runs the
image the compose file names — the canary then proves the two agree by
construction rather than by discipline.

The regex is deliberately exact: a floating tag (``neo4j:latest``, ``neo4j:2026``)
fails loudly here, which is ADR-067's "never a floating tag" rule enforced at
the only reader that could silently tolerate one.
"""

import re
from pathlib import Path

# tests/integration/_neo4j_pin.py → parents: [0] integration, [1] tests, [2] app, [3] repo root
COMPOSE_FILE = Path(__file__).resolve().parents[3] / "infrastructure" / "docker-compose.yml"

_EXACT_CALENDAR_PIN = re.compile(
    r"^\s*image:\s*(neo4j:(\d{4}\.\d{2}\.\d+))\s*(?:#.*)?$", re.MULTILINE
)


def neo4j_image_from_compose(compose_file: Path = COMPOSE_FILE) -> str:
    """Return the exact ``neo4j:YYYY.MM.N`` tag pinned in the compose file.

    Raises ``RuntimeError`` when the file holds no exact calendar pin — a missing
    or floating tag must fail the whole integration session, not fall back.
    """
    text = compose_file.read_text(encoding="utf-8")
    matches = _EXACT_CALENDAR_PIN.findall(text)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one exact `image: neo4j:YYYY.MM.N` pin in {compose_file}, "
            f"found {len(matches)} (ADR-067 § 3a: exact calendar tag, never floating)"
        )
    return matches[0][0]


NEO4J_IMAGE: str = neo4j_image_from_compose()
"""``neo4j:2026.07.1``-shaped tag the testcontainer starts."""

NEO4J_SERVER_VERSION: str = NEO4J_IMAGE.removeprefix("neo4j:")
"""What ``CALL dbms.components()`` must report for the running container."""
