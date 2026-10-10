"""The far-end admission rule a link door applies before it writes an edge.

``admit_far_ends_for_source`` reads the owner from the source node;
``admit_far_ends_for_owner`` is handed the owner by a door that creates the source.
Both answer a refusal as ``not_found`` of the far end's resource, whatever the
reason — a draft included — and write nothing on an unreadable endpoint map.
``partition_link_edges`` / ``keep_permitted_link_edges`` (the create doors and the
vault door) apply the same rule to a list.
``UnifiedRelationshipService`` admits before every edge it writes, or writes on the
proof of an admission it already made.

The rule over a real graph and real HTTP:
``tests/integration/routes/test_link_door_far_end.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.models.relationship_registry import GOALS_CONFIG
from core.models.type_hints import EntityUID, Neo4jProperties
from core.services.mixins.link_edge_guard import (
    GOAL_FAR_END,
    HABIT_FAR_END,
    KNOWLEDGE_FAR_END,
    KNOWLEDGE_LABELS,
    LinkEdge,
    LinkFarEnd,
    admit_far_ends_for_owner,
    admit_far_ends_for_source,
    keep_permitted_link_edges,
    partition_link_edges,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import ErrorCategory, Errors, Result

ALICE = "user_alice"
BOB = "user_bob"

_LABELS = {
    "goal_alice": ["Entity", "Goal"],
    "habit_alice": ["Entity", "Habit"],
    "habit_bob": ["Entity", "Habit"],
    "habit_shared_between_both": ["Entity", "Habit"],
    "ku_shared": ["Entity", "Ku"],
    "ku_draft": ["Entity", "Ku"],
    "ps_shared": ["Entity", "PathStep"],
    "exercise_alice_draft": ["Entity", "Exercise"],
}
_OWNERS = {
    "goal_alice": [ALICE],
    "habit_alice": [ALICE],
    "habit_bob": [BOB],
    "habit_shared_between_both": [BOB, ALICE],
    "exercise_alice_draft": [ALICE],
}
# Nodes marked ``publication_state: draft`` — absent from the publication read.
_DRAFTS = frozenset({"ku_draft", "exercise_alice_draft"})
EXERCISE_FAR_END = LinkFarEnd(frozenset({"Exercise"}), "Exercise")


@dataclass
class Endpoints:
    """The three batched endpoint reads, over fixed maps."""

    owners_error: bool = False
    labels_error: bool = False
    publication_error: bool = False
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

    async def get_published_uids_batch(self, uids: list[str]) -> Result[frozenset[str]]:
        if self.publication_error:
            return Result.fail(Errors.database("get_published_uids_batch", "unreachable"))
        return Result.ok(frozenset(uid for uid in uids if uid in _LABELS and uid not in _DRAFTS))


@dataclass
class WritingEndpoints(Endpoints):
    """The endpoint reads plus the batch write, recording every edge written."""

    written: list[tuple[str, str, str]] = field(default_factory=list)

    async def create_relationships_batch(
        self, relationships: list[tuple[str, str, str, Neo4jProperties | None]]
    ) -> Result[int]:
        self.written.extend((source, target, name) for source, target, name, _ in relationships)
        return Result.ok(len(relationships))


async def _from_source(
    source_uid: str, far_uid: str, far_end: LinkFarEnd = HABIT_FAR_END
) -> Result[frozenset[str]]:
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
            ("ku_draft", KNOWLEDGE_FAR_END, "draft"),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_refusal_is_not_found_of_the_far_ends_resource(
        self, far_uid: str, far_end: LinkFarEnd, reason: str
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
    async def test_a_source_nobody_owns_links_to_no_draft(self) -> None:
        refused = await _from_source("ps_shared", "ku_draft", KNOWLEDGE_FAR_END)

        assert refused.is_error
        assert refused.expect_error().details["reason"] == "draft"

    @pytest.mark.asyncio
    async def test_the_owners_own_entity_is_admitted_whatever_its_publication_state(
        self,
    ) -> None:
        """Publication is asked of shared content; a user's own entity is theirs."""
        assert (await _from_source("goal_alice", "exercise_alice_draft", EXERCISE_FAR_END)).is_ok

    @pytest.mark.asyncio
    async def test_another_users_draft_is_refused_as_another_users_node(self) -> None:
        refused = await admit_far_ends_for_owner(
            Endpoints(), owner_uid=BOB, far_uids=["exercise_alice_draft"], far_end=EXERCISE_FAR_END
        )

        assert refused.is_error
        assert refused.expect_error().details["reason"] == "cross_user"

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

    @pytest.mark.parametrize("failing", ["owners_error", "labels_error", "publication_error"])
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

    @pytest.mark.parametrize(("far_uid", "admitted"), [("ku_shared", True), ("ku_draft", False)])
    @pytest.mark.asyncio
    async def test_shared_knowledge_is_admitted_when_published(
        self, far_uid: str, admitted: bool
    ) -> None:
        result = await admit_far_ends_for_owner(
            Endpoints(), owner_uid=ALICE, far_uids=[far_uid], far_end=KNOWLEDGE_FAR_END
        )

        assert result.is_ok is admitted
        if not admitted:
            assert result.expect_error().message == f"Ku not found: {far_uid}"

    @pytest.mark.parametrize("failing", ["owners_error", "labels_error", "publication_error"])
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


class TestTheServiceWritesOnAnAdmission:
    """``UnifiedRelationshipService``: admit once, then write on the proof."""

    @staticmethod
    def _service(endpoints: WritingEndpoints) -> UnifiedRelationshipService[Any, Any, Any]:
        return UnifiedRelationshipService(backend=endpoints, config=GOALS_CONFIG)

    @pytest.mark.asyncio
    async def test_a_declared_far_end_is_admitted_then_written(self) -> None:
        endpoints = WritingEndpoints()

        linked = await self._service(endpoints).create_relationship(
            "supporting_habits", "goal_alice", "habit_alice", far_end=HABIT_FAR_END
        )

        assert linked.is_ok, linked.error
        assert len(endpoints.asked) == 1
        assert endpoints.written == [("habit_alice", "goal_alice", "SUPPORTS_GOAL")]

    @pytest.mark.asyncio
    async def test_a_refused_far_end_writes_nothing(self) -> None:
        endpoints = WritingEndpoints()

        refused = await self._service(endpoints).create_relationship(
            "supporting_habits", "goal_alice", "habit_bob", far_end=HABIT_FAR_END
        )

        assert refused.is_error
        assert endpoints.written == []

    @pytest.mark.asyncio
    async def test_the_proof_of_an_admission_writes_without_reading_again(self) -> None:
        endpoints = WritingEndpoints()
        service = self._service(endpoints)
        admission = await service.admit_far_ends("goal_alice", ["habit_alice"], HABIT_FAR_END)
        assert admission.is_ok, admission.error
        reads_at_admission = len(endpoints.asked)

        linked = await service.create_relationship(
            "supporting_habits", "goal_alice", "habit_alice", far_end=admission.value
        )

        assert linked.is_ok, linked.error
        assert len(endpoints.asked) == reads_at_admission
        assert endpoints.written == [("habit_alice", "goal_alice", "SUPPORTS_GOAL")]

    @pytest.mark.parametrize(
        ("from_uid", "to_uid"),
        [("goal_alice", "habit_bob"), ("habit_bob", "habit_alice")],
    )
    @pytest.mark.asyncio
    async def test_a_proof_is_good_for_its_own_link_only(self, from_uid: str, to_uid: str) -> None:
        endpoints = WritingEndpoints()
        service = self._service(endpoints)
        admission = await service.admit_far_ends("goal_alice", ["habit_alice"], HABIT_FAR_END)
        assert admission.is_ok, admission.error

        refused = await service.create_relationship(
            "supporting_habits", from_uid, to_uid, far_end=admission.value
        )

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.VALIDATION
        assert endpoints.written == []

    @pytest.mark.asyncio
    async def test_a_batch_admits_every_far_end_before_the_first_write(self) -> None:
        endpoints = WritingEndpoints()

        refused = await self._service(endpoints).create_relationships_batch(
            EntityUID("goal_alice"),
            {"supporting_habits": ["habit_alice", "habit_bob"]},
            far_ends={"supporting_habits": HABIT_FAR_END},
        )

        assert refused.is_error
        assert endpoints.written == []

    @pytest.mark.asyncio
    async def test_a_batch_key_with_no_declared_far_end_is_refused(self) -> None:
        endpoints = WritingEndpoints()

        refused = await self._service(endpoints).create_relationships_batch(
            EntityUID("goal_alice"), {"supporting_habits": ["habit_alice"]}, far_ends={}
        )

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.VALIDATION
        assert endpoints.written == []


def _knowledge_edge(ku_uid: str) -> LinkEdge:
    return LinkEdge(
        ("task_alice", ku_uid, "APPLIES_KNOWLEDGE", None),
        other_uid=ku_uid,
        allowed_labels=KNOWLEDGE_LABELS,
    )


class TestAListOfLinks:
    """The create doors and the vault door: the same rule, applied to a list."""

    @pytest.mark.asyncio
    async def test_a_draft_is_refused_and_the_rest_kept(self) -> None:
        partition = await partition_link_edges(
            Endpoints(),
            candidates=[_knowledge_edge("ku_shared"), _knowledge_edge("ku_draft")],
            owner_uid=ALICE,
        )

        assert partition.is_ok, partition.error
        assert [c.other_uid for c in partition.value.kept] == ["ku_shared"]
        assert [(c.other_uid, r) for c, r in partition.value.refused] == [("ku_draft", "draft")]

    @pytest.mark.asyncio
    async def test_a_pending_uid_is_the_owners_and_needs_no_publication(self) -> None:
        """A file this sync is about to create is the owner's, not shared content."""
        partition = await partition_link_edges(
            Endpoints(),
            candidates=[_knowledge_edge("ku_pending")],
            owner_uid=ALICE,
            pending_labels={"ku_pending": ["Entity", "Ku"]},
        )

        assert partition.is_ok, partition.error
        assert [c.other_uid for c in partition.value.kept] == ["ku_pending"]

    @pytest.mark.asyncio
    async def test_a_create_door_keeps_the_published_links(self) -> None:
        kept = await keep_permitted_link_edges(
            Endpoints(),
            candidates=[_knowledge_edge("ku_shared"), _knowledge_edge("ku_draft")],
            subject_uid="task_alice",
            owner_uid=ALICE,
            logger=logging.getLogger("test"),
        )

        assert kept == [("task_alice", "ku_shared", "APPLIES_KNOWLEDGE", None)]

    @pytest.mark.asyncio
    async def test_an_unreadable_publication_map_keeps_no_link(self) -> None:
        kept = await keep_permitted_link_edges(
            Endpoints(publication_error=True),
            candidates=[_knowledge_edge("ku_shared")],
            subject_uid="task_alice",
            owner_uid=ALICE,
            logger=logging.getLogger("test"),
        )

        assert kept == []

    @pytest.mark.asyncio
    async def test_an_unreadable_publication_map_fails_the_partition(self) -> None:
        partition = await partition_link_edges(
            Endpoints(publication_error=True),
            candidates=[_knowledge_edge("ku_shared")],
            owner_uid=ALICE,
        )

        assert partition.is_error
        assert partition.expect_error().category == ErrorCategory.DATABASE
