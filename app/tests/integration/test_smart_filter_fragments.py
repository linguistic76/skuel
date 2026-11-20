"""
Smart-filter fragments — seed-and-match integration proof.

Each /search Smart Filter is realized as a Cypher WHERE fragment in
``relationship_filter_fragments.py``. Before the 2026-07 remap, six of the
eleven filters were silent no-ops: they queried edges nothing ever wrote
(PRACTICES, ADHERES_TO, EMBODIES_KNOWLEDGE, ENABLES_LEARNING, PURSUING_GOAL),
a PathStep hop that doesn't exist (PS-[:REQUIRES_KNOWLEDGE]->), or compared a
string-stored ``updated_at`` against a native datetime (null → row dropped).

These tests prove each fragment MATCHES when its canonical pattern is seeded
with production-shaped data (string ISO timestamps where DTOs write strings),
and does NOT match for a different user. A mocked backend cannot catch any of
this — the failure mode is Cypher evaluating to null against real Neo4j.
"""

from dataclasses import fields
from datetime import UTC, datetime

import pytest

from adapters.persistence.neo4j.query.cypher.relationship_filter_fragments import (
    build_relationship_filter_fragments,
)
from core.models.relationship_filters import RelationshipFilters
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PREFIX = "sffrag"
USER = seed_user_uid(f"{_PREFIX}_owner")
OTHER = seed_user_uid(f"{_PREFIX}_other")


def _fragment(flag: str) -> str:
    """The single Cypher fragment realizing one filter flag."""
    filters = RelationshipFilters(**{flag: True})
    fragments = build_relationship_filter_fragments(filters)
    assert len(fragments) == 1
    return fragments[0]


async def _matches(driver, fragment: str, entity_uid: str, user_uid: str) -> bool:
    query = f"MATCH (entity:Entity {{uid: $entity_uid}}) WHERE {fragment} RETURN entity.uid AS uid"
    async with driver.session() as session:
        result = await session.run(query, entity_uid=entity_uid, user_uid=user_uid)
        return await result.single() is not None


@pytest.fixture(scope="module", autouse=True)
async def seeded_graph(neo4j_driver):
    """Seed one canonical pattern per Smart Filter, torn down after the module.

    Timestamps that DTOs write as ISO strings in production are seeded as
    strings here — that shape is exactly what the coercion fix exists for.
    """
    now_iso = datetime.now(UTC).isoformat()
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $user}) ON CREATE SET u.title = $user
            MERGE (o:User {uid: $other}) ON CREATE SET o.title = $other

            // ready_to_learn: entity with one prereq the user mastered
            MERGE (rtl:Entity:Ku {uid: $p + '.rtl'}) ON CREATE SET rtl.title = $p + '.rtl'
            MERGE (rtl_pre:Entity:Ku {uid: $p + '.rtl-pre'}) ON CREATE SET rtl_pre.title = $p + '.rtl-pre'
            MERGE (rtl)-[:REQUIRES_KNOWLEDGE]->(rtl_pre)
            MERGE (u)-[:MASTERED]->(rtl_pre)

            // builds_on_mastered: mastered neighbor RELATED_TO entity
            MERGE (bom:Entity:Ku {uid: $p + '.bom'}) ON CREATE SET bom.title = $p + '.bom'
            MERGE (bom_m:Entity:Ku {uid: $p + '.bom-m'}) ON CREATE SET bom_m.title = $p + '.bom-m'
            MERGE (u)-[:MASTERED]->(bom_m)
            MERGE (bom_m)-[:RELATED_TO]->(bom)

            // in_active_path: enrollment (no status) -> lp -> step -> USES_KU
            MERGE (iap:Entity:Ku {uid: $p + '.iap'}) ON CREATE SET iap.title = $p + '.iap'
            MERGE (iap_lp:Entity:LearningPath {uid: $p + '.iap-lp'}) ON CREATE SET iap_lp.title = $p + '.iap-lp'
            MERGE (iap_ps:Entity:PathStep {uid: $p + '.iap-ps'}) ON CREATE SET iap_ps.title = $p + '.iap-ps'
            MERGE (u)-[:ENROLLED_IN]->(iap_lp)
            MERGE (iap_lp)-[:HAS_STEP]->(iap_ps)
            MERGE (iap_ps)-[:USES_KU]->(iap)

            // in_active_path variant: CONTAINS_KNOWLEDGE hop also matches
            MERGE (iap2:Entity:Ku {uid: $p + '.iap2'}) ON CREATE SET iap2.title = $p + '.iap2'
            MERGE (iap_ps)-[:CONTAINS_KNOWLEDGE]->(iap2)

            // supports_goals: OWNS active goal REQUIRES_KNOWLEDGE entity
            MERGE (sg:Entity:Ku {uid: $p + '.sg'}) ON CREATE SET sg.title = $p + '.sg'
            MERGE (sg_goal:Entity:Goal {uid: $p + '.sg-goal'}) ON CREATE SET sg_goal.user_uid = u.uid ON CREATE SET sg_goal.title = $p + '.sg-goal'
            SET sg_goal.status = 'active'
            MERGE (u)-[:OWNS]->(sg_goal)
            MERGE (sg_goal)-[:REQUIRES_KNOWLEDGE]->(sg)

            // builds_on_habits: OWNS active habit REINFORCES_KNOWLEDGE entity
            MERGE (bh:Entity:Ku {uid: $p + '.bh'}) ON CREATE SET bh.title = $p + '.bh'
            MERGE (bh_habit:Entity:Habit {uid: $p + '.bh-habit'}) ON CREATE SET bh_habit.user_uid = u.uid ON CREATE SET bh_habit.title = $p + '.bh-habit'
            SET bh_habit.status = 'active'
            MERGE (u)-[:OWNS]->(bh_habit)
            MERGE (bh_habit)-[:REINFORCES_KNOWLEDGE]->(bh)

            // applied_in_tasks: recent task with STRING updated_at (DTO shape)
            MERGE (at:Entity:Ku {uid: $p + '.at'}) ON CREATE SET at.title = $p + '.at'
            MERGE (at_task:Entity:Task {uid: $p + '.at-task'}) ON CREATE SET at_task.user_uid = u.uid ON CREATE SET at_task.title = $p + '.at-task'
            SET at_task.status = 'completed', at_task.updated_at = $now_iso
            MERGE (u)-[:OWNS]->(at_task)
            MERGE (at_task)-[:APPLIES_KNOWLEDGE]->(at)

            // aligned_with_principles: OWNS active principle GROUNDED_IN_KNOWLEDGE
            MERGE (ap:Entity:Ku {uid: $p + '.ap'}) ON CREATE SET ap.title = $p + '.ap'
            MERGE (ap_pr:Entity:Principle {uid: $p + '.ap-pr'}) ON CREATE SET ap_pr.user_uid = u.uid ON CREATE SET ap_pr.title = $p + '.ap-pr'
            SET ap_pr.status = 'active'
            MERGE (u)-[:OWNS]->(ap_pr)
            MERGE (ap_pr)-[:GROUNDED_IN_KNOWLEDGE]->(ap)

            // next_logical_step: mastered ENABLES_KNOWLEDGE entity, no prereqs
            MERGE (nls:Entity:Ku {uid: $p + '.nls'}) ON CREATE SET nls.title = $p + '.nls'
            MERGE (nls_m:Entity:Ku {uid: $p + '.nls-m'}) ON CREATE SET nls_m.title = $p + '.nls-m'
            MERGE (u)-[:MASTERED]->(nls_m)
            MERGE (nls_m)-[:ENABLES_KNOWLEDGE]->(nls)

            // viewed_not_mastered / not_yet_viewed
            MERGE (vnm:Entity:Ku {uid: $p + '.vnm'}) ON CREATE SET vnm.title = $p + '.vnm'
            MERGE (u)-[:VIEWED]->(vnm)
            MERGE (nyv:Entity:Ku {uid: $p + '.nyv'}) ON CREATE SET nyv.title = $p + '.nyv'

            // ready_to_review: mastered 60 days ago (native datetime — the
            // writer is Cypher datetime($now) in mark_mastered)
            MERGE (rtr:Entity:Ku {uid: $p + '.rtr'}) ON CREATE SET rtr.title = $p + '.rtr'
            MERGE (u)-[m:MASTERED]->(rtr)
            SET m.mastered_at = datetime() - duration({days: 60})
            """,
            user=USER,
            other=OTHER,
            p=_PREFIX,
            now_iso=now_iso,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid STARTS WITH $p OR n.uid IN [$user, $other] DETACH DELETE n",
            p=_PREFIX,
            user=USER,
            other=OTHER,
        )


# (flag, entity uid suffix) — each seeded above
_CASES = [
    ("ready_to_learn", ".rtl"),
    ("builds_on_mastered", ".bom"),
    ("in_active_path", ".iap"),
    ("supports_goals", ".sg"),
    ("builds_on_habits", ".bh"),
    ("applied_in_tasks", ".at"),
    ("aligned_with_principles", ".ap"),
    ("next_logical_step", ".nls"),
    ("not_yet_viewed", ".nyv"),
    ("viewed_not_mastered", ".vnm"),
    ("ready_to_review", ".rtr"),
]


async def test_cases_cover_every_filter_flag() -> None:
    assert {flag for flag, _ in _CASES} == {f.name for f in fields(RelationshipFilters)}


@pytest.mark.parametrize(("flag", "suffix"), _CASES)
async def test_filter_matches_its_seeded_pattern(neo4j_driver, flag: str, suffix: str) -> None:
    fragment = _fragment(flag)
    assert await _matches(neo4j_driver, fragment, _PREFIX + suffix, USER), (
        f"{flag} did not match its canonical seeded pattern — "
        "the fragment queries an edge/shape the writers don't produce"
    )


@pytest.mark.parametrize(
    ("flag", "suffix"),
    [(f, s) for f, s in _CASES if f != "not_yet_viewed"],  # not_yet_viewed matches any stranger
)
async def test_filter_is_user_scoped(neo4j_driver, flag: str, suffix: str) -> None:
    fragment = _fragment(flag)
    assert not await _matches(neo4j_driver, fragment, _PREFIX + suffix, OTHER), (
        f"{flag} matched for a user with none of the seeded relationships"
    )


async def test_in_active_path_matches_contains_knowledge_hop(neo4j_driver) -> None:
    """All three composition edges (USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE) count."""
    fragment = _fragment("in_active_path")
    assert await _matches(neo4j_driver, fragment, _PREFIX + ".iap2", USER)


async def test_applied_in_tasks_survives_string_updated_at(neo4j_driver) -> None:
    """Regression: the seeded task's updated_at is an ISO STRING (DTO shape).

    Without datetime() coercion the comparison is null and this returns no
    rows — exactly the pre-remap bug (56 of 58 dev tasks were strings).
    """
    fragment = _fragment("applied_in_tasks")
    assert "datetime(task.updated_at)" in fragment
    assert await _matches(neo4j_driver, fragment, _PREFIX + ".at", USER)
