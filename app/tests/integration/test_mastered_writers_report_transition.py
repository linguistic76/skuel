"""Every MASTERED writer reports whether its write was the transition — atomically.

Three backends write ``(User)-[:MASTERED]->(…)`` — ``_LearningStateMixin.mark_mastered``
(report approval and the derived step), ``KuBackend.mark_mastered`` (the Ku page's
"understood") and ``UserBackend.record_knowledge_mastery`` (the pathways progress
route). Each reads the edge's prior existence in the same statement and returns it as
``was_mastered``: False for the write that created the edge, True for every repeat.
The publishers hang on that flag, so it is pinned against real Neo4j for all three —
including under concurrency: the flag is set inside the ``MERGE``, under its lock, so
N simultaneous first writes report exactly one transition and leave one edge.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend, PsBackend
from adapters.persistence.neo4j.user_backend import UserBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID

USER = UserUID("user_transition_flag")
KU_A = "ku.flag.a"
KU_B = "ku.flag.b"
KU_C = "ku.flag.c"


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j) -> None:
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $u})", u=USER)
        await session.run(
            """
            CREATE (:Entity:Ku {uid: $a, entity_type: 'ku', title: 'A'})
            CREATE (:Entity:Ku {uid: $b, entity_type: 'ku', title: 'B'})
            CREATE (:Entity:Ku {uid: $c, entity_type: 'ku', title: 'C'})
            """,
            a=KU_A,
            b=KU_B,
            c=KU_C,
        )


@pytest.mark.asyncio
async def test_learning_state_writer(neo4j_driver, graph) -> None:
    backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    now = datetime.now(UTC).isoformat()

    first = await backend.mark_mastered(USER, KU_A, now, 0.8, "report_approval")
    assert first.is_ok and first.value == [{"mastery_score": 0.8, "was_mastered": False}]

    repeat = await backend.mark_mastered(USER, KU_A, now, 0.95, "report_approval")
    assert repeat.is_ok and repeat.value == [{"mastery_score": 0.95, "was_mastered": True}]

    missing = await backend.mark_mastered(USER, "ku.flag.nope", now, 0.8, "report_approval")
    assert missing.is_ok and missing.value == [], "no entity, no row — never a false transition"


@pytest.mark.asyncio
async def test_ku_backend_writer(neo4j_driver, graph) -> None:
    backend = KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)

    first = await backend.mark_mastered(USER, KU_B, mastery_score=0.7, method="self_report")
    assert first.is_ok and first.value == [{"mastery_score": 0.7, "was_mastered": False}]

    repeat = await backend.mark_mastered(USER, KU_B, mastery_score=0.7, method="self_report")
    assert repeat.is_ok and repeat.value == [{"mastery_score": 0.7, "was_mastered": True}]


@pytest.mark.asyncio
async def test_user_backend_writer(neo4j_driver, graph) -> None:
    backend = UserBackend(neo4j_driver)

    first = await backend.record_knowledge_mastery(USER, KU_C, 0.85)
    assert first.is_ok and first.value == {"mastery_score": 0.85, "was_mastered": False}

    repeat = await backend.record_knowledge_mastery(USER, KU_C, 0.9)
    assert repeat.is_ok and repeat.value == {"mastery_score": 0.9, "was_mastered": True}


async def _edge_count(neo4j_driver, ku_uid: str) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $u})-[m:MASTERED]->(:Entity {uid: $k}) RETURN count(m) AS n",
            u=USER,
            k=ku_uid,
        )
        return int((await result.single())["n"])


@pytest.mark.asyncio
async def test_concurrent_first_writes_report_one_transition(neo4j_driver, graph) -> None:
    ps = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    ku = KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    user = UserBackend(neo4j_driver)
    now = datetime.now(UTC).isoformat()

    learning_state = await asyncio.gather(
        *(ps.mark_mastered(USER, KU_A, now, 0.8, "report_approval") for _ in range(6))
    )
    ku_page = await asyncio.gather(
        *(ku.mark_mastered(USER, KU_B, mastery_score=0.7, method="self_report") for _ in range(6))
    )
    pathways = await asyncio.gather(
        *(user.record_knowledge_mastery(USER, KU_C, 0.85) for _ in range(6))
    )

    for label, writes, flags in (
        ("learning-state", learning_state, [w.value[0]["was_mastered"] for w in learning_state]),
        ("ku-page", ku_page, [w.value[0]["was_mastered"] for w in ku_page]),
        ("pathways", pathways, [w.value["was_mastered"] for w in pathways]),
    ):
        assert all(w.is_ok for w in writes), f"{label}: a concurrent write failed"
        assert flags.count(False) == 1, f"{label}: {flags.count(False)} transitions reported"
    for ku_uid in (KU_A, KU_B, KU_C):
        assert await _edge_count(neo4j_driver, ku_uid) == 1
