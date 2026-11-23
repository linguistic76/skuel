"""Each writer stores only properties a read names: a field, or registered node state.

Over the testcontainer, the measurement is the stored node:

- the soft delete stamps ``deleted_at``, which the ``User`` read reads, and stores no
  ``status`` (the account's state is ``is_active``);
- the two User learning-state writers refuse a key outside their registered set and
  store nothing, and store a registered key;
- the create door refuses a model of another class than its backend reads, whose
  own fields that read never reads, and stores nothing.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.curriculum import Curriculum
from core.models.enums import Domain
from core.models.enums.learning_enums import SELCategory
from core.models.ku.ku import Ku
from core.models.user.user import User, create_user
from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends

pytestmark = pytest.mark.asyncio(loop_scope="session")

CURRICULUM_KU = "ku.test.raw-writes-curriculum"
PLAIN_KU = "ku.test.raw-writes-plain"


async def _props(driver, label: str, uid: str) -> dict | None:
    records, _, _ = await driver.execute_query(f"MATCH (n:{label} {{uid: $uid}}) RETURN n", uid=uid)
    return dict(records[0]["n"]) if records else None


async def _seed_user(backends, name: str) -> str:
    made = await backends["users_backend"].create_user(
        create_user(username=name, email=f"{name}@example.com")
    )
    assert made.is_ok, made
    return made.value.uid


async def test_the_soft_delete_stamps_deleted_at_and_stores_no_status(
    clean_neo4j, neo4j_driver
) -> None:
    backends = build_production_backends(neo4j_driver)
    uid = await _seed_user(backends, "zzzsoftdelete")

    deleted = await backends["users_backend"].delete_user(uid)
    assert deleted.is_ok and deleted.value is True

    stored = await _props(neo4j_driver, "User", uid)
    assert stored is not None
    assert "status" not in stored
    user = from_neo4j_node(stored, User)
    assert user.deleted_at is not None
    assert user.is_active is False


async def test_task_duration_learning_state_refuses_a_key_outside_its_set(
    clean_neo4j, neo4j_driver
) -> None:
    backends = build_production_backends(neo4j_driver)
    uid = await _seed_user(backends, "zzzdurationstate")
    tasks = backends["tasks_backend"]

    refused = await tasks.update_user_learning_state(
        uid, {"task_duration_ratio": 1.2, "recently_completed_tasks": ["task_x"]}
    )
    assert refused.is_error
    assert refused.expect_error().category is ErrorCategory.VALIDATION
    assert "recently_completed_tasks" in refused.expect_error().message
    stored = await _props(neo4j_driver, "User", uid)
    assert stored is not None
    assert "task_duration_ratio" not in stored
    assert "recently_completed_tasks" not in stored

    written = await tasks.update_user_learning_state(uid, {"task_duration_ratio": 1.2})
    assert written.is_ok, written
    read = await tasks.get_user_learning_state(uid)
    assert read.is_ok and read.value["task_duration_ratio"] == 1.2


async def test_teacher_feedback_state_refuses_a_key_outside_its_set(
    clean_neo4j, neo4j_driver
) -> None:
    backends = build_production_backends(neo4j_driver)
    uid = await _seed_user(backends, "zzzfeedbackstate")
    entries = backends["user_entry_backend"]

    refused = await entries.update_teacher_feedback_state(
        uid, {"feedback_ema_hours": 3.0, "feedback_ema_days": 1.0}
    )
    assert refused.is_error
    assert refused.expect_error().category is ErrorCategory.VALIDATION
    assert "feedback_ema_days" in refused.expect_error().message
    stored = await _props(neo4j_driver, "User", uid)
    assert stored is not None
    assert "feedback_ema_hours" not in stored
    assert "feedback_ema_days" not in stored

    written = await entries.update_teacher_feedback_state(uid, {"feedback_ema_hours": 3.0})
    assert written.is_ok, written
    read = await entries.get_teacher_feedback_state(uid)
    assert read.is_ok and read.value["feedback_ema_hours"] == 3.0


async def test_the_create_door_refuses_a_model_its_backend_does_not_read(
    clean_neo4j, neo4j_driver
) -> None:
    kus = build_production_backends(neo4j_driver)["ku_backend"]
    curriculum = Curriculum(
        uid=CURRICULUM_KU,
        title="Not a Ku",
        domain=Domain.TECH,
        sel_category=SELCategory.SELF_AWARENESS,
    )
    try:
        refused = await kus.create(curriculum)
        assert refused.is_error
        assert refused.expect_error().category is ErrorCategory.SYSTEM
        assert await _props(neo4j_driver, "Ku", CURRICULUM_KU) is None

        made = await kus.create(Ku(uid=PLAIN_KU, title="A Ku", domain=Domain.TECH))
        assert made.is_ok, made
        assert await _props(neo4j_driver, "Ku", PLAIN_KU) is not None
    finally:
        await neo4j_driver.execute_query(
            "MATCH (n) WHERE n.uid IN [$a, $b] DETACH DELETE n", a=CURRICULUM_KU, b=PLAIN_KU
        )
