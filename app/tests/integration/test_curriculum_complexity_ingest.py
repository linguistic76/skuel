"""A PathStep or LearningPath file's ``complexity:`` reaches its model through the content-vault door.

An authored value is stored and reads back as ``KuComplexity``; a file that authors none
stores no property and reads back ``None`` — no stand-in level is read in its place.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums import KuComplexity
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from tests.helpers.production_backends import build_production_backends

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ABSENT = object()


def _write(directory: Path, name: str, frontmatter: str) -> Path:
    path = directory / f"{name}.md"
    path.write_text(f"---\n{frontmatter}---\nBody.\n", encoding="utf-8")
    return path


async def _has_property(neo4j_driver, uid: str) -> bool:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN 'complexity' IN keys(n) AS has_property",
            {"uid": uid},
        )
        record = await result.single()
    assert record is not None, f"{uid} was not written"
    return bool(record["has_property"])


async def test_a_path_step_with_no_complexity_reads_none(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _write(tmp_path, "ps-absent", "type: ps\nuid: ps.test.cx-absent\ntitle: Absent\n")

    assert (await ingestion_service.ingest_file(path)).is_ok

    assert await _has_property(neo4j_driver, "ps.test.cx-absent") is False
    result = await build_production_backends(neo4j_driver)["ps_backend"].get("ps.test.cx-absent")
    assert result.is_ok, result
    assert isinstance(result.value, PathStep)
    assert getattr(result.value, "complexity", _ABSENT) is None


async def test_a_path_step_reads_back_the_complexity_it_authored(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        "ps-authored",
        "type: ps\nuid: ps.test.cx-authored\ntitle: Authored\ncomplexity: advanced\n",
    )

    assert (await ingestion_service.ingest_file(path)).is_ok

    result = await build_production_backends(neo4j_driver)["ps_backend"].get("ps.test.cx-authored")
    assert result.is_ok, result
    assert getattr(result.value, "complexity", _ABSENT) is KuComplexity.ADVANCED


async def test_a_learning_path_with_no_complexity_reads_none(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _write(tmp_path, "lp-absent", "type: lp\nuid: lp.test.cx-absent\ntitle: Absent\n")

    assert (await ingestion_service.ingest_file(path)).is_ok

    assert await _has_property(neo4j_driver, "lp.test.cx-absent") is False
    result = await build_production_backends(neo4j_driver)["lp_backend"].get("lp.test.cx-absent")
    assert result.is_ok, result
    assert isinstance(result.value, LearningPath)
    assert getattr(result.value, "complexity", _ABSENT) is None
