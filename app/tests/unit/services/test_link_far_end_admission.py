"""The far-end admission rule a link door applies before it writes an edge.

``admit_far_ends_for_source`` reads the owner from the source node;
``admit_far_ends_for_owner`` is handed the owner by a door that creates the source.
Both answer a refusal as ``not_found`` of the far end's resource, whatever the
reason, and write nothing on an unreadable endpoint map.

The rule over a real graph and real HTTP:
``tests/integration/routes/test_link_door_far_end.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.services.mixins.link_edge_guard import (
    GOAL_FAR_END,
    HABIT_FAR_END,
    KNOWLEDGE_FAR_END,
    admit_far_ends_for_owner,
    admit_far_ends_for_source,
)
from core.utils.result_simplified import ErrorCategory, Errors, Result

ALICE = "user_alice"
BOB = "user_bob"

_LABELS = {
    "goal_alice": ["Entity", "Goal"],
    "habit_alice": ["Entity", "Habit"],
    "habit_bob": ["Entity", "Habit"],
    "habit_shared_between_both": ["Entity", "Habit"],
    "ku_shared": ["Entity", "Ku"],
    "ps_shared": ["Entity", "PathStep"],
}
_OWNERS = {
    "goal_alice": [ALICE],
    "habit_alice": [ALICE],
    "habit_bob": [BOB],
    "habit_shared_between_both": [BOB, ALICE],
}


@dataclass
class Endpoints:
    """The two batched endpoint reads, over fixed maps."""

    owners_error: bool = False
    labels_error: bool = False
    asked: list[list[str]] = field(default_factory=list)

    async def get_owner_uids_batch(self, uids: list[str]) -> Result[dict[str, list[str]]]:
        self.asked.append(uids)
        if self.owners_error:
            return Result.fail(Errors.database("get_owner_uids_batch", "unreachable"))
        return Result.ok({uid: _OWNERS[uid] for uid in uids if uid in _OWNERS})

    async def get_node_labels_batch(self, uids: list[str]) -> Result[dict[str, list[str]]]:
        if self.labels_error:
            return Result.fail(Errors.database("get_node_labels_batch", "unreachable"))
        return Result.ok({uid: _LABELS[uid] for uid in uids if uid in _LABELS})


async def _from_source(source_uid: str, far_uid: str, far_end=HABIT_FAR_END) -> Result[None]:
    return await admit_far_ends_for_source(
        Endpoints(),
        source_uid=source_uid,
        source_resource="Entity",
        far_uids=[far_uid],
        far_end=far_end,
    )


class TestForSource:
    @pytest.mark.asyncio
    async def test_the_owners_own_entity_of_the_right_kind_is_admitted(self) -> None:
        assert (await _from_source("goal_alice", "habit_alice")).is_ok

    @pytest.mark.asyncio
    async def test_shared_content_of_the_right_kind_is_admitted(self) -> None:
        assert (await _from_source("goal_alice", "ku_shared", KNOWLEDGE_FAR_END)).is_ok

    @pytest.mark.asyncio
    async def test_an_entity_with_several_owners_is_admitted_for_each_of_them(self) -> None:
        assert (await _from_source("goal_alice", "habit_shared_between_both")).is_ok

    @pytest.mark.parametrize(
        ("far_uid", "far_end", "reason"),
        [
            ("habit_bob", HABIT_FAR_END, "cross_user"),
            ("habit_nowhere", HABIT_FAR_END, "missing"),
            ("ku_shared", HABIT_FAR_END, "wrong_kind"),
            ("ps_shared", KNOWLEDGE_FAR_END, "wrong_kind"),
            ("habit_alice", KNOWLEDGE_FAR_END, "wrong_kind"),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_refusal_is_not_found_of_the_far_ends_resource(
        self, far_uid: str, far_end, reason: str
    ) -> None:
        refused = await _from_source("goal_alice", far_uid, far_end)

        assert refused.is_error
        error = refused.expect_error()
        assert error.category == ErrorCategory.NOT_FOUND
        assert error.message == f"{far_end.resource} not found: {far_uid}"
        assert error.details == {
            "resource": far_end.resource,
            "identifier": far_uid,
            "reason": reason,
        }

    @pytest.mark.parametrize("far_uid", ["goal_alice", "habit_bob"])
    @pytest.mark.asyncio
    async def test_a_source_nobody_owns_links_to_no_owned_entity(self, far_uid: str) -> None:
        far_end = GOAL_FAR_END if far_uid.startswith("goal") else HABIT_FAR_END

        refused = await _from_source("ps_shared", far_uid, far_end)

        assert refused.is_error
        assert refused.expect_error().details["reason"] == "cross_user"

    @pytest.mark.asyncio
    async def test_a_source_nobody_owns_links_to_shared_content(self) -> None:
        assert (await _from_source("ps_shared", "ku_shared", KNOWLEDGE_FAR_END)).is_ok

    @pytest.mark.asyncio
    async def test_a_source_that_names_nothing_is_not_found(self) -> None:
        refused = await _from_source("goal_nowhere", "ku_shared", KNOWLEDGE_FAR_END)

        assert refused.is_error
        assert refused.expect_error().message == "Entity not found: goal_nowhere"

    @pytest.mark.asyncio
    async def test_an_entity_is_not_linked_to_itself(self) -> None:
        refused = await _from_source("habit_alice", "habit_alice")

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.VALIDATION

    @pytest.mark.asyncio
    async def test_one_refused_far_end_refuses_the_list(self) -> None:
        refused = await admit_far_ends_for_source(
            Endpoints(),
            source_uid="goal_alice",
            source_resource="Entity",
            far_uids=["habit_alice", "habit_bob"],
            far_end=HABIT_FAR_END,
        )

        assert refused.is_error
        assert refused.expect_error().details["identifier"] == "habit_bob"

    @pytest.mark.asyncio
    async def test_no_far_ends_reads_nothing(self) -> None:
        endpoints = Endpoints()

        admitted = await admit_far_ends_for_source(
            endpoints,
            source_uid="goal_alice",
            source_resource="Entity",
            far_uids=[],
            far_end=HABIT_FAR_END,
        )

        assert admitted.is_ok
        assert endpoints.asked == []

    @pytest.mark.parametrize("failing", ["owners_error", "labels_error"])
    @pytest.mark.asyncio
    async def test_an_unreadable_endpoint_map_admits_nothing(self, failing: str) -> None:
        refused = await admit_far_ends_for_source(
            Endpoints(**{failing: True}),
            source_uid="goal_alice",
            source_resource="Entity",
            far_uids=["habit_alice"],
            far_end=HABIT_FAR_END,
        )

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.DATABASE


class TestForOwner:
    @pytest.mark.parametrize(
        ("far_uid", "admitted"),
        [
            ("habit_alice", True),
            ("habit_shared_between_both", True),
            ("habit_bob", False),
            ("habit_nowhere", False),
            ("goal_alice", False),
        ],
    )
    @pytest.mark.asyncio
    async def test_the_far_end_is_the_owners_and_of_the_right_kind(
        self, far_uid: str, admitted: bool
    ) -> None:
        result = await admit_far_ends_for_owner(
            Endpoints(), owner_uid=ALICE, far_uids=[far_uid], far_end=HABIT_FAR_END
        )

        assert result.is_ok is admitted
        if not admitted:
            assert result.expect_error().message == f"Habit not found: {far_uid}"

    @pytest.mark.parametrize("failing", ["owners_error", "labels_error"])
    @pytest.mark.asyncio
    async def test_an_unreadable_endpoint_map_admits_nothing(self, failing: str) -> None:
        refused = await admit_far_ends_for_owner(
            Endpoints(**{failing: True}),
            owner_uid=ALICE,
            far_uids=["habit_alice"],
            far_end=HABIT_FAR_END,
        )

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.DATABASE
