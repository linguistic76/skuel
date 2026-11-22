"""No write door stores a key that names no field of the class its node is read as.

Over the testcontainer: a CRUD patch carrying such a key answers SYSTEM and leaves the
node as it was; at the vault door the file authoring one is refused, its report naming
the field the author most likely meant, and the rest of the batch is written; a file's
relationship keys stay edge sources and ``moc`` goes no further than the preparer. A
task update's prerequisites become the create door's edges, never properties, and the
calibrated duration (ADR-048 learning state) is written by its own statement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = seed_user_uid("test_integration")  # seeded by the ensure_test_users fixture
TASK = "task_8d2e3f4a5b6c7d8e"


async def _props(neo4j_driver, uid: str) -> dict[str, Any] | None:  # boundary: node properties
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (n {uid: $uid}) RETURN properties(n) AS p", uid=uid)
        ).single()
    return dict(record["p"]) if record else None


async def _targets(neo4j_driver, uid: str, relationship: RelationshipName) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH ({{uid: $uid}})-[:{relationship.value}]->(t) RETURN t.uid AS uid ORDER BY uid",
            uid=uid,
        )
        return [record["uid"] async for record in result]


def _file(directory: Path, name: str, frontmatter: str, body: str = "Body.\n") -> Path:
    path = directory / f"{name}.md"
    path.write_text(f"---\n{frontmatter}---\n{body}")
    return path


async def test_a_patch_naming_no_field_answers_system_and_writes_nothing(
    clean_neo4j, ensure_test_users, neo4j_driver
) -> None:
    tasks = build_production_backends(neo4j_driver)["tasks_backend"]
    assert (await tasks.create(Task(uid=TASK, title="Clean", user_uid=OWNER))).is_ok
    before = await _props(neo4j_driver, TASK)

    result = await tasks.update(TASK, {"title": "Renamed", "titel": "Renamed"})

    assert await _props(neo4j_driver, TASK) == before
    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.SYSTEM
    assert "'titel' (did you mean 'title'?)" in error.message


async def test_the_directory_door_refuses_the_file_naming_the_field_it_meant(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    habit = f"type: habit\nuser_uid: {OWNER}\n"
    _file(
        vault,
        "gate-good",
        f"{habit}uid: habit.gate-good\ntitle: Good\nhabit_category: mindfulness\n",
    )
    _file(vault, "gate-bad", f"{habit}uid: habit.gate-bad\ntitle: Bad\ncategory: mindfulness\n")

    result = await ingestion_service.ingest_directory(vault)

    assert result.is_ok, result
    errors = result.value.errors or []
    refused = [error for error in errors if "gate-bad" in str(error.get("file", ""))]
    assert [(error.get("stage"), error.get("field")) for error in refused] == [
        ("validation", "category")
    ], errors
    assert "did you mean 'habit_category'?" in str(refused[0].get("error")), refused
    assert await _props(neo4j_driver, "habit.gate-bad") is None
    good = await _props(neo4j_driver, "habit.gate-good")
    assert good is not None and good["habit_category"] == "mindfulness"


async def test_the_single_file_door_refuses_a_key_on_the_relationship_skip_list(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _file(
        tmp_path,
        "lp-prereq",
        "type: learning_path\nuid: lp.gate-prereq\ntitle: Path\nprerequisites:\n  - lp.other\n",
    )

    result = await ingestion_service.ingest_file(path)

    assert result.is_error
    error = result.expect_error()
    assert error.details.get("field") == "prerequisites"
    assert "LearningPath has no field 'prerequisites'" in error.display_message
    assert await _props(neo4j_driver, "lp.gate-prereq") is None


async def test_a_moc_step_with_edge_sources_stores_neither_as_a_property(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    ku = _file(tmp_path, "gate-ku", "type: ku\nuid: ku.gate.atom\ntitle: Atom\n")
    assert (await ingestion_service.ingest_file(ku)).is_ok
    step = _file(
        tmp_path,
        "gate-step",
        "type: lesson\nuid: ps.gate.step\ntitle: Step\nmoc: true\nuses_kus:\n  - ku.gate.atom\n",
        "[[gate-ku]]\n",
    )

    result = await ingestion_service.ingest_file(step)

    assert result.is_ok, result
    stored = await _props(neo4j_driver, "ps.gate.step")
    assert stored is not None
    assert not {"moc", "uses_kus"} & set(stored), sorted(stored)
    assert await _targets(neo4j_driver, "ps.gate.step", RelationshipName.USES_KU) == [
        "ku.gate.atom"
    ]


async def test_a_group_file_naming_its_owner_stores_no_user_uid(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    path = _file(
        tmp_path, "gate-group", f"type: group\nuid: group.gate\nname: Gate\nowner_uid: {OWNER}\n"
    )

    result = await ingestion_service.ingest_file(path)

    assert result.is_ok, result
    stored = await _props(neo4j_driver, "group.gate")
    assert stored is not None
    assert stored.get("owner_uid") == OWNER
    assert "user_uid" not in stored


class TestATaskUpdatesItsPrerequisitesAsEdges:
    async def test_the_update_writes_the_create_doors_edges_and_no_property(
        self, services, neo4j_driver, clean_neo4j, ensure_test_users, ingestion_service, tmp_path
    ) -> None:
        ku = _file(tmp_path, "pre-ku", "type: ku\nuid: ku.gate.prereq\ntitle: Prerequisite\n")
        assert (await ingestion_service.ingest_file(ku)).is_ok
        first = await services.tasks.create_task(TaskCreateRequest(title="First"), OWNER)
        second = await services.tasks.create_task(TaskCreateRequest(title="Second"), OWNER)
        assert first.is_ok and second.is_ok
        other_owner = seed_user_uid("test_integration_other")
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.title = $uid, u.created_at = datetime()",
                uid=other_owner,
            )
        foreign = await services.tasks.create_task(
            TaskCreateRequest(title="Not yours"), other_owner
        )
        assert foreign.is_ok

        intent = TaskUpdateRequest(
            prerequisite_task_uids=[first.value.uid, foreign.value.uid],
            prerequisite_knowledge_uids=["ku.gate.prereq"],
        ).to_intent()
        updated = await services.tasks.update_task(second.value.uid, intent)

        assert updated.is_ok, updated
        uid = second.value.uid
        assert await _targets(neo4j_driver, uid, RelationshipName.BLOCKED_BY) == [first.value.uid]
        assert await _targets(neo4j_driver, uid, RelationshipName.REQUIRES_KNOWLEDGE) == [
            "ku.gate.prereq"
        ]
        stored = await _props(neo4j_driver, uid)
        assert stored is not None
        assert not {"prerequisite_task_uids", "prerequisite_knowledge_uids"} & set(stored)

    async def test_an_empty_list_clears_them(
        self, services, neo4j_driver, clean_neo4j, ensure_test_users
    ) -> None:
        first = await services.tasks.create_task(TaskCreateRequest(title="First"), OWNER)
        assert first.is_ok
        second = await services.tasks.create_task(
            TaskCreateRequest(title="Second", prerequisite_task_uids=[first.value.uid]), OWNER
        )
        assert second.is_ok
        assert await _targets(neo4j_driver, second.value.uid, RelationshipName.BLOCKED_BY) == [
            first.value.uid
        ]

        updated = await services.tasks.update_task(
            second.value.uid, TaskUpdateRequest(prerequisite_task_uids=[]).to_intent()
        )

        assert updated.is_ok, updated
        assert await _targets(neo4j_driver, second.value.uid, RelationshipName.BLOCKED_BY) == []


async def test_the_calibrated_duration_is_written_by_its_own_statement(
    clean_neo4j, ensure_test_users, neo4j_driver
) -> None:
    tasks = build_production_backends(neo4j_driver)["tasks_backend"]
    assert (await tasks.create(Task(uid=TASK, title="Timed", user_uid=OWNER))).is_ok

    written = await tasks.set_predicted_duration(TASK, 34)

    assert written.is_ok, written
    stored = await _props(neo4j_driver, TASK)
    assert stored is not None and stored["predicted_duration_minutes"] == 34
    assert (await tasks.get(TASK)).is_ok
