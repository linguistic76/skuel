"""
The integration testcontainer's image comes from the compose pin — and only an
EXACT calendar tag is accepted (ADR-067 § 3a).

Runs in the always-on unit tier so a compose edit that floats the tag, drops
it, or duplicates it fails CI before the integration job ever pulls an image.
"""

from pathlib import Path

import pytest

from tests.integration._neo4j_pin import (
    COMPOSE_FILE,
    NEO4J_IMAGE,
    NEO4J_SERVER_VERSION,
    neo4j_image_from_compose,
)


def test_live_compose_pin_is_an_exact_calendar_tag() -> None:
    assert COMPOSE_FILE.is_file(), COMPOSE_FILE
    assert neo4j_image_from_compose() == NEO4J_IMAGE
    assert NEO4J_IMAGE.startswith("neo4j:")
    year, month, patch = NEO4J_SERVER_VERSION.split(".")
    assert len(year) == 4 and len(month) == 2 and patch.isdigit()


def test_exact_tag_is_read_verbatim(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  neo4j:\n    image: neo4j:2031.02.3  # a comment\n")
    assert neo4j_image_from_compose(compose) == "neo4j:2031.02.3"


@pytest.mark.parametrize(
    "image_line",
    [
        "    image: neo4j:latest\n",
        "    image: neo4j:2031\n",
        "    image: neo4j:2031.02\n",
        "    image: neo4j:5.26.0-community\n",
        "    image: neo4j\n",
    ],
)
def test_floating_or_suffixed_tag_fails_loudly(tmp_path: Path, image_line: str) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  neo4j:\n" + image_line)
    with pytest.raises(RuntimeError, match="exactly one exact"):
        neo4j_image_from_compose(compose)


def test_two_pins_fail_loudly(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("    image: neo4j:2031.02.3\n    image: neo4j:2031.03.0\n")
    with pytest.raises(RuntimeError, match="found 2"):
        neo4j_image_from_compose(compose)
