"""
The integration testcontainers' image comes from the compose pin — and only an
EXACT calendar tag is accepted (ADR-067 § 3a).

Runs in the always-on unit tier so a compose edit that floats, suffixes, or
drops the tag fails CI before the integration job ever pulls an image.
"""

from pathlib import Path

import pytest

from tests.integration._neo4j_pin import (
    COMPOSE_FILE,
    NEO4J_IMAGE,
    NEO4J_SERVER_VERSION,
    neo4j_image_from_compose,
)


def _compose(tmp_path: Path, body: str) -> Path:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(body, encoding="utf-8")
    return compose


def test_live_compose_pin_is_an_exact_calendar_tag() -> None:
    assert COMPOSE_FILE.is_file(), COMPOSE_FILE
    assert neo4j_image_from_compose() == NEO4J_IMAGE
    assert NEO4J_IMAGE.startswith("neo4j:")
    year, month, patch = NEO4J_SERVER_VERSION.split(".")
    assert len(year) == 4 and len(month) == 2 and patch.isdigit()


@pytest.mark.parametrize(
    "image_line",
    [
        "    image: neo4j:2031.02.3\n",
        "    image: neo4j:2031.02.3  # a comment\n",
        '    image: "neo4j:2031.02.3"\n',
        "    image: 'neo4j:2031.02.3'\n",
    ],
)
def test_exact_tag_is_read_verbatim_bare_or_quoted(tmp_path: Path, image_line: str) -> None:
    compose = _compose(tmp_path, "services:\n  neo4j:\n" + image_line)
    assert neo4j_image_from_compose(compose) == "neo4j:2031.02.3"


@pytest.mark.parametrize(
    "image_line",
    [
        "    image: neo4j:latest\n",
        "    image: neo4j:2031\n",
        "    image: neo4j:2031.02\n",
        "    image: neo4j:5.26.0-community\n",
        "    image: neo4j\n",
        "    image: postgres:16\n",
    ],
)
def test_floating_or_suffixed_tag_fails_loudly(tmp_path: Path, image_line: str) -> None:
    compose = _compose(tmp_path, "services:\n  neo4j:\n" + image_line)
    with pytest.raises(RuntimeError, match=r"exact `neo4j:YYYY\.MM\.N`"):
        neo4j_image_from_compose(compose)


@pytest.mark.parametrize(
    "body",
    [
        "services:\n  neo4j:\n    ports: ['7687:7687']\n",  # service without an image
        "services:\n  postgres:\n    image: neo4j:2031.02.3\n",  # no neo4j service
        "volumes: {}\n",  # no services at all
        "",  # empty file
    ],
)
def test_missing_service_or_image_fails_loudly(tmp_path: Path, body: str) -> None:
    compose = _compose(tmp_path, body)
    with pytest.raises(RuntimeError, match="found None"):
        neo4j_image_from_compose(compose)
