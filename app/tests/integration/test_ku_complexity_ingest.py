"""A Ku file's ``complexity:`` reaches the Ku model through the real content-vault door.

An authored value is stored and reads back as ``KuComplexity``; an absent one stores no
property and reads back ``None``; a value outside the vocabulary is refused before
anything is written; and a stray value already in the graph refuses the read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums import KuComplexity
from core.models.ku.ku import Ku
from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ABSENT = object()


def _ku_file(directory: Path, slug: str, frontmatter: str = "") -> Path:
    path = directory / f"ku_{slug}.md"
    path.write_text(
        f"---\ntype: ku\nuid: ku.test.{slug}\ntitle: {slug}\n{frontmatter}---\nBody.\n",
        encoding="utf-8",
    )
    return path


async def _stored(neo4j_driver, uid: str) -> dict | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity:Ku {uid: $uid}) "
            "RETURN n.complexity AS complexity, 'complexity' IN keys(n) AS has_property",
            {"uid": uid},
        )
        record = await result.single()
        return dict(record) if record else None


async def _read_ku(neo4j_driver, uid: str) -> Ku:
    result = await build_production_backends(neo4j_driver)["ku_backend"].get(uid)
    assert result.is_ok, result
    assert isinstance(result.value, Ku)
    return result.value


async def test_an_authored_complexity_reads_back_as_the_enum(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _ku_file(tmp_path, "cx-authored", "complexity: basic\n")

    assert (await ingestion_service.ingest_file(path)).is_ok

    assert await _stored(neo4j_driver, "ku.test.cx-authored") == {
        "complexity": "basic",
        "has_property": True,
    }
    ku = await _read_ku(neo4j_driver, "ku.test.cx-authored")
    assert getattr(ku, "complexity", _ABSENT) is KuComplexity.BASIC


async def test_an_absent_complexity_stores_nothing_and_reads_none(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _ku_file(tmp_path, "cx-absent")

    assert (await ingestion_service.ingest_file(path)).is_ok

    assert await _stored(neo4j_driver, "ku.test.cx-absent") == {
        "complexity": None,
        "has_property": False,
    }
    ku = await _read_ku(neo4j_driver, "ku.test.cx-absent")
    assert getattr(ku, "complexity", _ABSENT) is None


async def test_a_complexity_outside_the_vocabulary_is_refused(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """The ingestion vocabulary gate refuses a Ku complexity outside the vocabulary
    before anything is written."""
    path = _ku_file(tmp_path, "cx-bogus", "complexity: bogus\n")

    result = await ingestion_service.ingest_file(path)

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.VALIDATION
    assert "'complexity' must be one of" in error.message
    assert await _stored(neo4j_driver, "ku.test.cx-bogus") is None


async def test_a_stray_value_in_the_graph_refuses_the_read(clean_neo4j, neo4j_driver) -> None:
    """A value no ``KuComplexity`` names, stored around the ingestion gate, fails the
    read as an error naming the node — it never reads as absent or as the raw value."""
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Ku {uid: 'ku.test.cx-stray', title: 'Stray', entity_type: 'ku', "
            "complexity: 'bogus', publication_state: 'published'})"
        )

    result = await build_production_backends(neo4j_driver)["ku_backend"].get("ku.test.cx-stray")

    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.SYSTEM
    assert "ku.test.cx-stray" in str(error.details)
