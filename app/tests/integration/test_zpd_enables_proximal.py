"""ZPD zone traversal against a real graph — the ENABLES-proximal ruling.

Mike's ruling (2026-07-10, PR 5 of the discovery-analytics arc):
ENABLES counts for PROXIMAL EXPANSION ONLY — "you engaged A, A ENABLES B →
B is proximal" joins the PREREQUISITE_FOR forward step. Readiness scoring and
blocking-gap logic stay strictly prerequisite-only: an enabler must NEVER
become a gate or a requirement.

Seeds an engagement edge (task -[:APPLIES_KNOWLEDGE]-> Ku) plus authored
ENABLES / PREREQUISITE_FOR edges, then asserts on ZPDBackend.get_zone_data
directly (no MIN_KU_THRESHOLD service guard in the way). Also exercises the
CALL (vars) {...} scope syntax against the live 2026.05 server.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.zpd_backend import ZPDBackend

USER_UID = "user_test_zpd_enables"

KU_ENGAGED = "ku.test.zpd-engaged"  # engaged via task
KU_ENABLED = "ku.test.zpd-enabled"  # KU_ENGAGED -ENABLES-> this → proximal
KU_PREREQ_NEXT = "ku.test.zpd-prereq-next"  # KU_ENGAGED -PREREQUISITE_FOR-> this → proximal
KU_UNENGAGED_ENABLER = "ku.test.zpd-unengaged-enabler"  # -ENABLES-> KU_ENABLED, NOT a gap
KU_UNENGAGED_PREREQ = "ku.test.zpd-unengaged-prereq"  # -PREREQUISITE_FOR-> KU_PREREQ_NEXT, IS a gap
TASK_UID = "task_test_zpd_enables"

_ALL_UIDS = [
    USER_UID,
    TASK_UID,
    KU_ENGAGED,
    KU_ENABLED,
    KU_PREREQ_NEXT,
    KU_UNENGAGED_ENABLER,
    KU_UNENGAGED_PREREQ,
]


@pytest_asyncio.fixture
async def zpd_graph(neo4j_driver, clean_neo4j):
    """Seed the minimal ZPD graph: one engagement + authored curriculum edges."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.title = $uid",
            uid=USER_UID,
        )
        for ku_uid in (
            KU_ENGAGED,
            KU_ENABLED,
            KU_PREREQ_NEXT,
            KU_UNENGAGED_ENABLER,
            KU_UNENGAGED_PREREQ,
        ):
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.entity_type = 'ku', k.title = $uid, k.status = 'active'
                """,
                uid=ku_uid,
            )
        # Engagement: (User)-[:OWNS]->(Task)-[:APPLIES_KNOWLEDGE]->(Ku)
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Ku {uid: $ku_uid})
            MERGE (t:Entity:Task {uid: $task_uid})
            SET t.entity_type = 'task', t.title = 'ZPD probe task', t.status = 'active'
            MERGE (u)-[:OWNS]->(t)
            MERGE (t)-[:APPLIES_KNOWLEDGE]->(k)
            """,
            user_uid=USER_UID,
            ku_uid=KU_ENGAGED,
            task_uid=TASK_UID,
        )
        # Authored curriculum edges
        for from_uid, rel, to_uid in [
            (KU_ENGAGED, "ENABLES", KU_ENABLED),
            (KU_ENGAGED, "PREREQUISITE_FOR", KU_PREREQ_NEXT),
            (KU_UNENGAGED_ENABLER, "ENABLES", KU_ENABLED),
            (KU_UNENGAGED_PREREQ, "PREREQUISITE_FOR", KU_PREREQ_NEXT),
        ]:
            await session.run(
                f"""
                MATCH (a:Ku {{uid: $from_uid}})
                MATCH (b:Ku {{uid: $to_uid}})
                MERGE (a)-[:{rel}]->(b)
                """,
                from_uid=from_uid,
                to_uid=to_uid,
            )

    yield

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=_ALL_UIDS,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_enables_expands_proximal_zone(neo4j_driver, zpd_graph) -> None:
    """Engaged A, A-ENABLES->B → B is proximal (alongside the prereq path)."""
    backend = ZPDBackend(neo4j_driver)

    result = await backend.get_zone_data(USER_UID)

    assert result.is_ok, f"zone query failed: {result.error}"
    current_zone, proximal_zone, *_ = result.value

    assert current_zone == [KU_ENGAGED]
    assert KU_ENABLED in proximal_zone, "ENABLES must expand the proximal zone"
    assert KU_PREREQ_NEXT in proximal_zone, "PREREQUISITE_FOR forward step must still work"
    # Unengaged non-adjacent KUs never leak into the zone
    assert KU_UNENGAGED_ENABLER not in proximal_zone
    assert KU_UNENGAGED_ENABLER not in current_zone


@pytest.mark.asyncio(loop_scope="session")
async def test_unengaged_enabler_is_never_a_blocking_gap(neo4j_driver, zpd_graph) -> None:
    """The ruling's negative control: an enabler must NEVER become a gate.

    KU_UNENGAGED_ENABLER enables a proximal KU but is not engaged — were
    ENABLES treated like a prerequisite, it would surface as a blocking gap
    and depress readiness. It must do neither.
    """
    backend = ZPDBackend(neo4j_driver)

    result = await backend.get_zone_data(USER_UID)

    assert result.is_ok, f"zone query failed: {result.error}"
    _, _, _, prereq_data, blocking_gaps, *_ = result.value

    assert KU_UNENGAGED_ENABLER not in blocking_gaps, (
        "ENABLES leaked into blocking-gap logic — enablers must never gate"
    )
    # Positive control: the unmet PREREQUISITE_FOR edge IS a gap
    assert KU_UNENGAGED_PREREQ in blocking_gaps

    # Readiness stays prereq-only: KU_ENABLED has no prerequisites → fully
    # ready (1.0-equivalent: total == 0), despite its unengaged enabler.
    by_ku = {entry["ku_uid"]: entry for entry in prereq_data}
    assert by_ku[KU_ENABLED]["total"] == 0, (
        "an ENABLES edge counted as a prerequisite in readiness scoring"
    )
    # KU_PREREQ_NEXT has 2 prereqs (engaged + unengaged), 1 met
    assert by_ku[KU_PREREQ_NEXT]["total"] == 2
    assert by_ku[KU_PREREQ_NEXT]["met"] == 1
