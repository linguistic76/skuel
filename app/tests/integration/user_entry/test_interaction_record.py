"""
Interaction Audit Record Integration Test — systems-review Arc A
=================================================================

Pins the Interaction Contract (ADR-051) write path that the existing flow
tests skip (their ``user_entry_service`` fixture leaves ``interaction_service``
unset, which is exactly how the silent-failure bug survived):

    student → UserEntryService.create_entry(fulfills_exercise_uid, about_path_step_uid)
              → (:Entity:Interaction) node
              → [:RECORDS] → (:UserEntry)
              → [:INTERACTION_DURING] → (:PathStep)   (curriculum context)

Live-graph evidence (2026-07-03): 0 Interaction nodes despite a real
FULFILLS_EXERCISE submission — the fire-and-forget ``_create_interaction_record``
swallowed its failure, and it never passed the PathStep context the
PS submissions-and-feedback reader requires (INTERACTION_DURING).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from adapters.persistence.neo4j.backends.misc_backends import InteractionBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.interaction.interaction import Interaction
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.interaction.interaction_service import InteractionService
from core.services.user_entry.user_entry_service import UserEntryService


@pytest_asyncio.fixture
async def interaction_service(neo4j_driver) -> "AsyncIterator[InteractionService]":
    """Real ``InteractionService`` over a real ``InteractionBackend``."""
    backend = InteractionBackend(
        driver=neo4j_driver,
        label=NeoLabel.INTERACTION,
        entity_class=Interaction,
        prometheus_metrics=None,
        base_label=NeoLabel.ENTITY,
    )
    yield InteractionService(backend=backend)


@pytest_asyncio.fixture
async def user_entry_service_with_interactions(
    user_entry_backend,
    sharing_service,
    interaction_service: InteractionService,
) -> "AsyncIterator[UserEntryService]":
    """``UserEntryService`` wired like production compose: interaction_service set."""
    yield UserEntryService(
        backend=user_entry_backend,  # type: ignore[arg-type]
        sharing_service=sharing_service,
        interaction_service=interaction_service,
    )


@pytest_asyncio.fixture
async def seed_path_step(neo4j_driver):
    """MERGE an ``(:Entity:PathStep)`` node for INTERACTION_DURING context."""

    async def _seed(ps_uid: str, title: str = "Test PathStep") -> str:
        now_iso = datetime.now().isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (ps:Entity:PathStep {uid: $ps_uid})
                ON CREATE SET ps.title = $title,
                              ps.entity_type = 'path_step',
                              ps.status = 'active',
                              ps.created_at = datetime($now),
                              ps.updated_at = datetime($now)
                """,
                ps_uid=ps_uid,
                title=title,
                now=now_iso,
            )
        return ps_uid

    return _seed


@pytest.mark.asyncio
async def test_create_interaction_direct(
    clean_neo4j,
    interaction_service: InteractionService,
    neo4j_driver,
) -> None:
    """Layer isolation: InteractionService.create_interaction against real Neo4j."""
    from core.models.enums.entity_enums import EntityType
    from core.models.enums.interaction_enums import InteractionType
    from core.utils.uid_generator import UIDGenerator

    ia = Interaction(
        uid=UIDGenerator.generate_random_uid("ia"),
        title="user_entry — ex.direct",
        entity_type=EntityType.INTERACTION,
        user_uid="user_ue_student",
        interaction_type=InteractionType.EXERCISE_SUBMISSION,
        target_uid="exercise.ue_demo",
        source_entity_uid="ue_direct_test",
    )
    result = await interaction_service.create_interaction(ia)
    assert result.is_ok, f"create_interaction failed: {result.expect_error()}"

    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (i:Entity:Interaction {uid: $uid}) RETURN i.uid AS uid",
                uid=ia.uid,
            )
        ).single()
    assert row is not None, "Interaction node not persisted"


@pytest.mark.asyncio
async def test_exercise_submission_creates_interaction_with_ps_context(
    clean_neo4j,
    user_entry_service_with_interactions,
    neo4j_driver,
    seed_classroom,
    seed_path_step,
) -> None:
    ctx = await seed_classroom()
    ps_uid = await seed_path_step("ps.ue_demo_step")

    request = UserEntryCreateRequest(
        title="Worked exercise",
        content="Here is my completed worksheet.",
        pipeline=Pipeline.LLM_SUMMARY,
        fulfills_exercise_uid=ctx["exercise_uid"],
        about_path_step_uid=ps_uid,
    )

    create_result = await user_entry_service_with_interactions.create_entry(
        request=request,
        user_uid=ctx["student_uid"],
    )
    assert create_result.is_ok, create_result.expect_error()
    entry, _outcome = create_result.value

    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (i:Entity:Interaction)-[:RECORDS]->(u:UserEntry {uid: $uid})
                OPTIONAL MATCH (i)-[:INTERACTION_DURING]->(ps:PathStep)
                RETURN i.uid AS interaction_uid,
                       i.interaction_type AS interaction_type,
                       i.target_uid AS target_uid,
                       ps.uid AS ps_uid
                """,
                uid=entry.uid,
            )
        ).single()

    assert row is not None, (
        "No Interaction node RECORDS the submission — the Interaction Contract "
        "write path failed (this was silent in production: fire-and-forget)"
    )
    assert row["interaction_type"] == "exercise_submission"
    assert row["target_uid"] == ctx["exercise_uid"]
    assert row["ps_uid"] == ps_uid, (
        "Interaction lacks INTERACTION_DURING → PathStep context; the PS "
        "submissions-and-feedback query requires it (about_path_step_uid must "
        "flow through create_entry into the Interaction record)"
    )


@pytest.mark.asyncio
async def test_result_status_transitions_forward_only(
    clean_neo4j,
    interaction_service: InteractionService,
    neo4j_driver,
) -> None:
    """ADR-051 Phase 2: record_result moves the record forward and the
    server-side guard rejects stale (backwards) transitions."""
    from core.models.enums.entity_enums import EntityType
    from core.models.enums.interaction_enums import InteractionResult, InteractionType
    from core.utils.uid_generator import UIDGenerator

    entry_uid = "ue_transition_test"
    ia = Interaction(
        uid=UIDGenerator.generate_random_uid("ia"),
        title="user_entry — ex.transition",
        entity_type=EntityType.INTERACTION,
        user_uid="user_ue_student",
        interaction_type=InteractionType.EXERCISE_SUBMISSION,
        target_uid="exercise.ue_demo",
        source_entity_uid=entry_uid,
    )
    create_result = await interaction_service.create_interaction(ia)
    assert create_result.is_ok, create_result.expect_error()

    async def _status() -> str:
        async with neo4j_driver.session() as session:
            row = await (
                await session.run(
                    "MATCH (i:Entity:Interaction {uid: $uid}) RETURN i.result_status AS s",
                    uid=ia.uid,
                )
            ).single()
        return row["s"]

    assert await _status() == "pending"

    # PENDING → REPORT_GENERATED applies
    forward = await interaction_service.record_result(entry_uid, InteractionResult.REPORT_GENERATED)
    assert forward.is_ok and forward.value is True
    assert await _status() == "report_generated"

    # Stale SHARED_WITH_TEACHER arriving late is a no-op, never a demotion
    stale = await interaction_service.record_result(
        entry_uid, InteractionResult.SHARED_WITH_TEACHER
    )
    assert stale.is_ok and stale.value is False
    assert await _status() == "report_generated"

    # REPORT_GENERATED → COMPLETED applies; a repeat no-ops (terminal)
    done = await interaction_service.record_result(entry_uid, InteractionResult.COMPLETED)
    assert done.is_ok and done.value is True
    repeat = await interaction_service.record_result(entry_uid, InteractionResult.COMPLETED)
    assert repeat.is_ok and repeat.value is False
    assert await _status() == "completed"

    # An entry with no Interaction record no-ops cleanly (journal entries)
    missing = await interaction_service.record_result(
        "ue_no_such_entry", InteractionResult.COMPLETED
    )
    assert missing.is_ok and missing.value is False
