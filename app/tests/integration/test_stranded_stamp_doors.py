"""A bare completion stamp is refused at the doors that can send one (ADR-087).

``{"completion_date": …}`` with no ``status`` resolves against whatever status the node
already holds, so nothing before the write can judge it: on an open entity it strands a
stamp that reads to every consumer as done. The rule therefore travels to the write as
the prior it REQUIRES, and the refusal comes back as ``applied=False`` for the chokepoint
to voice.

Driven through the real services against a real graph, because the claim is about what
the database does with the guard and about what the caller is told — neither of which a
mocked backend can settle. Both doors that can reach the shape are here:

- ``TaskUpdateRequest`` carries a status as well, so it satisfies the rule in one call;
- ``ChoiceUpdateRequest`` exposes ``completed_at`` and NO status at all, which is why the
  rule demands a PRIOR rather than a status in the same patch — the latter would be
  unsatisfiable at this door rather than strict.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from core.models.choice.choice import Choice
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums.entity_enums import EntityStatus
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent

OWNER = "user_test_integration"  # seeded by the ensure_test_users fixture


# boundary: raw Neo4j node properties — a heterogeneous property map read straight off
# the driver, which is the shape these assertions are about.
async def _props(neo4j_driver, uid: str) -> dict[str, Any]:
    async with neo4j_driver.session() as session:
        result = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=uid)
        record = await result.single()
        return dict(record["n"]) if record else {}


@pytest.mark.asyncio
async def test_a_bare_stamp_on_an_open_task_is_refused(services, neo4j_driver, clean_neo4j) -> None:
    uid = "task.bare-stamp-open"
    assert (
        await services.tasks.core.backend.create(
            Task(uid=uid, user_uid=OWNER, title="open", status=EntityStatus.ACTIVE)
        )
    ).is_ok

    result = await services.tasks.update_task(
        uid, TaskUpdateIntent(completion_date=date(2026, 3, 4))
    )

    assert result.is_error
    error = result.expect_error()
    assert "completion_date can only be set on a completed task" in error.message
    assert "'active'" in error.message, "the message names the status the WRITE saw"
    props = await _props(neo4j_driver, uid)
    assert "completion_date" not in props
    assert props["status"] == EntityStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_the_refused_write_leaves_the_rest_of_the_patch_unwritten(
    services, neo4j_driver, clean_neo4j
) -> None:
    """A refusal is whole-write: the title in the same patch must not land either.

    That is what makes it a refusal rather than a partial apply the caller has to guess
    at — and it is why the caller is told, instead of the stamp being dropped silently.
    """
    uid = "task.bare-stamp-whole"
    assert (
        await services.tasks.core.backend.create(
            Task(uid=uid, user_uid=OWNER, title="original", status=EntityStatus.ACTIVE)
        )
    ).is_ok

    result = await services.tasks.update_task(
        uid, TaskUpdateIntent(title="renamed", completion_date=date(2026, 3, 4))
    )

    assert result.is_error
    assert (await _props(neo4j_driver, uid))["title"] == "original"


@pytest.mark.asyncio
async def test_a_bare_stamp_on_a_completed_task_re_dates_it(
    services, neo4j_driver, clean_neo4j
) -> None:
    """The shape the gate preserves: correcting the date of a task that IS completed."""
    uid = "task.bare-stamp-done"
    assert (
        await services.tasks.core.backend.create(
            Task(
                uid=uid,
                user_uid=OWNER,
                title="done",
                status=EntityStatus.COMPLETED,
                completion_date=date(2026, 1, 1),
            )
        )
    ).is_ok

    result = await services.tasks.update_task(
        uid, TaskUpdateIntent(completion_date=date(2026, 3, 4))
    )

    assert result.is_ok
    assert (await _props(neo4j_driver, uid))["completion_date"] == "2026-03-04"


@pytest.mark.asyncio
async def test_naming_the_status_in_the_same_patch_satisfies_the_rule(
    services, neo4j_driver, clean_neo4j
) -> None:
    """The remedy the message offers a door that carries a status — in one call."""
    uid = "task.bare-stamp-together"
    assert (
        await services.tasks.core.backend.create(
            Task(uid=uid, user_uid=OWNER, title="open", status=EntityStatus.ACTIVE)
        )
    ).is_ok

    result = await services.tasks.update_task(
        uid, TaskUpdateIntent(status="completed", completion_date=date(2026, 3, 4))
    )

    assert result.is_ok
    props = await _props(neo4j_driver, uid)
    assert props["status"] == EntityStatus.COMPLETED.value
    assert props["completion_date"] == "2026-03-04"


@pytest.mark.asyncio
async def test_a_choice_is_told_to_complete_first(services, neo4j_driver, clean_neo4j) -> None:
    """The door with no status field: the message must name a remedy it can follow."""
    uid = "choice.bare-stamp-open"
    assert (
        await services.choices.core.backend.create(
            Choice(uid=uid, user_uid=OWNER, title="undecided", status=EntityStatus.DRAFT)
        )
    ).is_ok

    result = await services.choices.update_choice(
        uid, ChoiceUpdateIntent(completed_at=datetime(2026, 3, 4, 9, 0))
    )

    assert result.is_error
    assert "Complete it first" in result.expect_error().message
    assert "completed_at" not in await _props(neo4j_driver, uid)
