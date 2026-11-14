"""No write door stores a value its field's type cannot read.

Over the testcontainer, through each door that writes a node through the mapper: a CRUD
patch, a status-guarded patch, a locked rewrite, a model create, and both vault doors. A
value every later read of the node would refuse (``due_date: soon``, a bare
``tags: work``, a null title) is refused before the write, and the node is as it was;
an enum spelling the read tolerates is stored as its member's value. At the vault door
the file holding the value is refused against its field, and the rest of the batch —
and every list read of its owner — goes on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from core.models.event.event import Event
from core.models.task.task import Task
from core.models.update_contracts import StatusWriteGuard
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = seed_user_uid("test_integration")  # seeded by the ensure_test_users fixture
TASK = "task_7c1d2e3f4a5b6c7d"
EVENT = "event_7c1d2e3f4a5b6c7d"


async def _props(neo4j_driver, uid: str) -> dict[str, Any] | None:  # boundary: node properties
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (n {uid: $uid}) RETURN properties(n) AS p", uid=uid)
        ).single()
    return dict(record["p"]) if record else None


@pytest.fixture
async def task(clean_neo4j, ensure_test_users, neo4j_driver):
    tasks = build_production_backends(neo4j_driver)["tasks_backend"]
    created = await tasks.create(Task(uid=TASK, title="Clean", user_uid=OWNER))
    assert created.is_ok, created
    return tasks


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        pytest.param("recurrence_pattern", "bogus", id="an-enum-outside-the-vocabulary"),
        pytest.param("due_date", "soon", id="an-unparseable-date"),
        pytest.param("title", None, id="a-null-on-a-field-that-requires-a-value"),
    ],
)
async def test_a_patch_holding_an_unreadable_value_leaves_the_node_as_it_was(
    task, neo4j_driver, field_name: str, value: object
) -> None:
    before = await _props(neo4j_driver, TASK)

    result = await task.update(TASK, {field_name: value})

    assert await _props(neo4j_driver, TASK) == before
    assert (await task.get(TASK)).is_ok
    assert result.is_error
    assert field_name in result.expect_error().message


async def test_an_enum_patch_is_stored_as_its_members_value(task, neo4j_driver) -> None:
    result = await task.update(TASK, {"recurrence_pattern": "WEEKLY"})

    assert result.is_ok, result
    stored = await _props(neo4j_driver, TASK)
    assert stored is not None and stored["recurrence_pattern"] == "weekly"


async def test_a_guarded_patch_holding_an_unreadable_value_writes_nothing(
    task, neo4j_driver
) -> None:
    before = await _props(neo4j_driver, TASK)

    result = await task.update_with_status_guard(TASK, {"due_date": "soon"}, StatusWriteGuard())

    assert result.is_error
    assert await _props(neo4j_driver, TASK) == before


@dataclass(frozen=True)
class _Plan:
    updates: dict[str, Any] = field(default_factory=dict)  # boundary: a pre-serialization patch
    guard: StatusWriteGuard = field(default_factory=StatusWriteGuard)


def _plan_an_unreadable_due_date(_task: Task) -> _Plan:
    return _Plan(updates={"due_date": "soon"})


async def test_a_locked_rewrite_whose_plan_is_refused_rolls_back(task, neo4j_driver) -> None:
    before = await _props(neo4j_driver, TASK)

    result = await task.rewrite_under_lock(TASK, _plan_an_unreadable_due_date)

    assert result.is_error
    after = await _props(neo4j_driver, TASK)
    assert after == before, "the lock sentinel or the value was committed"


async def test_a_model_holding_a_value_of_another_type_is_not_created(
    clean_neo4j, ensure_test_users, neo4j_driver
) -> None:
    events = build_production_backends(neo4j_driver)["events_backend"]
    # A datetime where the field reads a time: what an untyped construction can hold.
    event = Event(uid=EVENT, title="E", user_uid=OWNER, start_time=datetime(2026, 11, 14, 9))  # type: ignore[arg-type]  # the wrong type is the point

    result = await events.create(event)

    assert await _props(neo4j_driver, EVENT) is None
    assert result.is_error
    assert "start_time" in result.expect_error().message


def _task_file(directory: Path, slug: str, extra: str = "") -> Path:
    path = directory / f"{slug}.md"
    path.write_text(
        f"---\ntype: task\nuid: task.{slug}\ntitle: Task {slug}\nuser_uid: {OWNER}\n{extra}---\n"
        "Body.\n"
    )
    return path


async def test_the_directory_door_refuses_the_file_and_writes_the_rest(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _task_file(vault, "gate-good", "due_date: 2026-11-20\n")
    _task_file(vault, "gate-bad", "due_date: soon\n")

    result = await ingestion_service.ingest_directory(vault)

    assert result.is_ok, result
    errors = result.value.errors or []
    refused = [error for error in errors if "gate-bad" in str(error.get("file", ""))]
    assert [(error.get("stage"), error.get("field")) for error in refused] == [
        ("validation", "due_date")
    ], errors
    assert await _props(neo4j_driver, "task.gate-bad") is None
    assert await _props(neo4j_driver, "task.gate-good") is not None
    tasks = build_production_backends(neo4j_driver)["tasks_backend"]
    listed = await tasks.find_by(user_uid=OWNER)
    assert listed.is_ok, listed
    assert "task.gate-good" in {task.uid for task in listed.value}


async def test_the_single_file_door_refuses_a_file_naming_its_field(
    clean_neo4j, ensure_test_users, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    result = await ingestion_service.ingest_file(_task_file(tmp_path, "gate-tags", "tags: work\n"))

    assert result.is_error
    error = result.expect_error()
    assert error.details.get("field") == "tags"
    assert "tags" in error.display_message and "gate-tags" in error.display_message
    assert await _props(neo4j_driver, "task.gate-tags") is None
