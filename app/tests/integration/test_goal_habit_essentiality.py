"""Real-Neo4j round-trip for goal↔habit essentiality tiers (end-to-end reconciliation).

The essentiality feature ("a goal's essential / critical / supporting / optional habits",
James Clear's systems lens) was dead at four layers, all fixed in this change:

1. WRITE — ``link_goal_to_habit`` stored the tier under ``contribution_type``, but the read
   mappings filter on ``essentiality``. The canonical edge is now
   ``(Habit)-[:SUPPORTS_GOAL {essentiality}]->(Goal)`` and the writer writes that key.
2. READ path 1 (``get_related_uids`` → ``GoalRelationships``) dropped ``filter_property``,
   so every tier field returned the same unfiltered set. The service now passes the spec's
   edge filter to the backend (which already applies ``WHERE r.<prop> = $value``).
3. READ path 2 (``get_cross_domain_context`` categorization) never read ``filter_property``,
   so the ``contributing_habits`` catch-all swallowed every habit via the first-match
   ``break``. The Cypher now emits ``incident_rel_properties`` and the loop tries
   property-filtered mappings before the catch-all.
4. A competing dead ``REQUIRES_HABIT {essentiality}`` convention (no live writer/reader, no
   edges) was retired.

These tests write the four tiers via the canonical ``create_relationship`` path (exactly what
``link_goal_to_habit`` delegates to), then read them back through BOTH read paths and assert
correct partitioning. The negative control (an un-tiered habit) proves the catch-all still
works and the result reflects the graph. Mocked tests can't catch this (the filter mismatch
is a silent wrong/empty set); the guard must run against real Cypher.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.query import generate_context_query
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.goal.goal_dto import GoalDTO
from core.models.relationship_registry import GOALS_CONFIG
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

P = "esstest_"
GOAL = P + "goal"
GOAL_BARE = P + "goal_untiered"  # control: a single un-tiered (supporting) habit
H_ESSENTIAL = P + "h_essential"
H_CRITICAL = P + "h_critical"
H_SUPPORTING = P + "h_supporting"
H_OPTIONAL = P + "h_optional"
H_PLAIN = P + "h_plain"  # linked with the default "supporting" tier


@pytest.fixture
def rel_backend(neo4j_driver):
    """Generic Entity backend — the shape injected as a domain's relationships backend."""
    return UniversalNeo4jBackend[GoalDTO](neo4j_driver, "Entity", GoalDTO)


@pytest.fixture
def goal_rel(rel_backend):
    return UnifiedRelationshipService[Any, Any, Any](
        backend=rel_backend, config=GOALS_CONFIG, graph_intel=None
    )


async def _seed_goal_and_habits(session, goal_uid: str, habit_uids: list[str]) -> None:
    await session.run(
        "CREATE (n:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
        "status:'active', created_at:datetime()})",
        u=goal_uid,
    )
    for uid in habit_uids:
        await session.run(
            "CREATE (n:Entity:Habit {uid:$u, entity_type:'habit', title:$u, "
            "status:'active', created_at:datetime()})",
            u=uid,
        )


@pytest.mark.asyncio
async def test_essentiality_write_stores_property_and_orients_edge(
    neo4j_driver, goal_rel, clean_neo4j
):
    """The canonical write path stores ``essentiality`` and orients (Habit)->(Goal).

    ``create_relationship("supporting_habits", goal, habit, {...})`` is exactly what
    ``link_goal_to_habit`` delegates to. The incoming spec swaps endpoints, so the edge is
    ``(Habit)-[:SUPPORTS_GOAL {essentiality}]->(Goal)`` — the shape the read mappings expect.
    """
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL, [H_ESSENTIAL])

    res = await goal_rel.create_relationship(
        "supporting_habits", GOAL, H_ESSENTIAL, {"weight": 1.0, "essentiality": "essential"}
    )
    assert res.is_ok, res

    async with neo4j_driver.session() as s:
        rec = await (
            await s.run(
                "MATCH (h:Habit {uid:$h})-[r:SUPPORTS_GOAL]->(g:Goal {uid:$g}) "
                "RETURN r.essentiality AS essentiality, r.weight AS weight",
                h=H_ESSENTIAL,
                g=GOAL,
            )
        ).single()
    assert rec is not None, "edge not written as (Habit)-[:SUPPORTS_GOAL]->(Goal)"
    assert rec["essentiality"] == "essential"
    assert rec["weight"] == 1.0


@pytest.mark.asyncio
async def test_essentiality_tiers_partition_via_get_related_uids(
    neo4j_driver, goal_rel, clean_neo4j
):
    """READ path 1: each tier field filters to its own edges; the catch-all returns all."""
    habits = [H_ESSENTIAL, H_CRITICAL, H_SUPPORTING, H_OPTIONAL]
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL, habits)

    for habit, tier in [
        (H_ESSENTIAL, "essential"),
        (H_CRITICAL, "critical"),
        (H_SUPPORTING, "supporting"),
        (H_OPTIONAL, "optional"),
    ]:
        res = await goal_rel.create_relationship(
            "supporting_habits", GOAL, habit, {"weight": 1.0, "essentiality": tier}
        )
        assert res.is_ok, res

    async def uids(key: str) -> set[str]:
        r = await goal_rel.get_related_uids(key, GOAL)
        assert r.is_ok, r
        return set(r.value)

    # Filtered tiers each return ONLY their tier (pre-fix: all returned the full set).
    assert await uids("essential_habits") == {H_ESSENTIAL}
    assert await uids("critical_habits") == {H_CRITICAL}
    assert await uids("optional_habits") == {H_OPTIONAL}
    # The no-filter catch-all returns every supporting habit regardless of tier.
    assert await uids("supporting_habits") == set(habits)


@pytest.mark.asyncio
async def test_essentiality_tiers_partition_via_cross_domain_context(
    neo4j_driver, goal_rel, clean_neo4j
):
    """READ path 2: categorization routes each habit to its tier bucket, not the catch-all.

    Pre-fix, the unfiltered ``contributing_habits`` mapping sorted first and the first-match
    ``break`` swallowed every habit, leaving the three tier buckets always empty. The
    filtered-first sort + ``incident_rel_properties`` filter now partitions them; the
    ``supporting`` habit (no matching tier filter) falls through to the catch-all.
    """
    habits = [H_ESSENTIAL, H_CRITICAL, H_SUPPORTING, H_OPTIONAL]
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL, habits)

    for habit, tier in [
        (H_ESSENTIAL, "essential"),
        (H_CRITICAL, "critical"),
        (H_SUPPORTING, "supporting"),
        (H_OPTIONAL, "optional"),
    ]:
        res = await goal_rel.create_relationship(
            "supporting_habits", GOAL, habit, {"weight": 1.0, "essentiality": tier}
        )
        assert res.is_ok, res

    ctx_res = await goal_rel.get_cross_domain_context(GOAL, depth=1, min_confidence=0.7)
    assert ctx_res.is_ok, ctx_res
    raw = ctx_res.value

    def bucket(name: str) -> set[str]:
        return {e["uid"] for e in raw.get(name) or []}

    # Each habit lands in EXACTLY its tier bucket; the un-tiered "supporting" one in the
    # catch-all. No bucket overlap (the first-match break partitions them).
    assert bucket("essential_habits") == {H_ESSENTIAL}
    assert bucket("critical_habits") == {H_CRITICAL}
    assert bucket("optional_habits") == {H_OPTIONAL}
    assert bucket("contributing_habits") == {H_SUPPORTING}

    # The four tier buckets union to every supporting habit, de-duplicated — the
    # path-aware reader aggregates them the same way.
    all_habit_uids = (
        bucket("essential_habits")
        | bucket("critical_habits")
        | bucket("optional_habits")
        | bucket("contributing_habits")
    )
    assert all_habit_uids == set(habits)


@pytest.mark.asyncio
async def test_untiered_habit_falls_to_catch_all(neo4j_driver, goal_rel, clean_neo4j):
    """Control: a default ``supporting`` habit lands in the catch-all, not a tier bucket.

    Proves the partitioning reflects the edge property (not a hard-coded routing) and that
    the catch-all still functions for the default tier.
    """
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL_BARE, [H_PLAIN])

    # Default essentiality from link_goal_to_habit is "supporting".
    res = await goal_rel.create_relationship(
        "supporting_habits", GOAL_BARE, H_PLAIN, {"weight": 1.0, "essentiality": "supporting"}
    )
    assert res.is_ok, res

    # get_related_uids: tiers empty, catch-all + supporting filter both find it.
    ess = await goal_rel.get_related_uids("essential_habits", GOAL_BARE)
    assert ess.is_ok and ess.value == []
    allh = await goal_rel.get_related_uids("supporting_habits", GOAL_BARE)
    assert allh.is_ok and allh.value == [H_PLAIN]

    # get_cross_domain_context: catch-all only.
    ctx_res = await goal_rel.get_cross_domain_context(GOAL_BARE, depth=1, min_confidence=0.7)
    assert ctx_res.is_ok, ctx_res
    raw = ctx_res.value
    assert {e["uid"] for e in raw.get("contributing_habits") or []} == {H_PLAIN}
    assert (raw.get("essential_habits") or []) == []


@pytest.mark.asyncio
async def test_create_via_filtered_key_round_trips(neo4j_driver, goal_rel, clean_neo4j):
    """Write/read symmetry: creating via a FILTERED key stamps the edge property.

    Codex P2: the new read filter (``r.essentiality = "essential"``) would make a bare-edge
    create via the same key invisible — create succeeds, read returns empty. ``_orient_edge``
    now stamps the filtered spec's property on write, so ``create_relationship`` and
    ``get_related_uids`` round-trip through the ``essential_habits`` key with no explicit
    property from the caller.
    """
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL, [H_ESSENTIAL])

    # Create via the FILTERED key, passing NO explicit essentiality property.
    res = await goal_rel.create_relationship("essential_habits", GOAL, H_ESSENTIAL)
    assert res.is_ok, res

    # The edge carries the stamped tier property.
    async with neo4j_driver.session() as s:
        rec = await (
            await s.run(
                "MATCH (h:Habit {uid:$h})-[r:SUPPORTS_GOAL]->(g:Goal {uid:$g}) "
                "RETURN r.essentiality AS e",
                h=H_ESSENTIAL,
                g=GOAL,
            )
        ).single()
    assert rec is not None and rec["e"] == "essential"

    # And it reads back through the same filtered key (pre-fix: empty).
    r = await goal_rel.get_related_uids("essential_habits", GOAL)
    assert r.is_ok and r.value == [H_ESSENTIAL]


@pytest.mark.asyncio
async def test_essentiality_tiers_filter_via_get_with_context_path(
    neo4j_driver, goal_rel, clean_neo4j
):
    """READ path 3: the build_entity_with_context (generate_context_query) path filters too.

    ``to_relationship_spec()`` used to drop ``filter_property``, so this path's per-tier
    aliases (essential_habits / critical_habits / optional_habits) all collapsed to the
    same unfiltered set. The spec now carries the filter and ``build_entity_with_context``
    emits a parameterized ``WHERE r.<prop> = $value``, so the three context read paths
    (get_related_uids, get_cross_domain_context, get_with_context) finally agree.
    """
    habits = [H_ESSENTIAL, H_CRITICAL, H_SUPPORTING, H_OPTIONAL]
    async with neo4j_driver.session() as s:
        await _seed_goal_and_habits(s, GOAL, habits)

    for habit, tier in [
        (H_ESSENTIAL, "essential"),
        (H_CRITICAL, "critical"),
        (H_SUPPORTING, "supporting"),
        (H_OPTIONAL, "optional"),
    ]:
        res = await goal_rel.create_relationship(
            "supporting_habits", GOAL, habit, {"weight": 1.0, "essentiality": tier}
        )
        assert res.is_ok, res

    # The exact runtime query the get_with_context path builds from the registry.
    query, params = generate_context_query("Goal")
    params["uid"] = GOAL
    async with neo4j_driver.session() as s:
        rec = await (await s.run(query, params)).single()
    assert rec is not None

    def alias(name: str) -> set[str]:
        return {h["uid"] for h in rec[name] if h and h.get("uid")}

    # The fix: each tier alias now filters to its own edge (pre-fix all three returned
    # the full set of four). Each alias is an INDEPENDENT OPTIONAL MATCH here — there is
    # no first-match partition like get_cross_domain_context — so the unfiltered
    # ``contributing_habits`` catch-all returns ALL supporting habits, matching
    # get_related_uids("supporting_habits"). The two unfiltered views agree; the union is
    # identical either way.
    assert alias("essential_habits") == {H_ESSENTIAL}
    assert alias("critical_habits") == {H_CRITICAL}
    assert alias("optional_habits") == {H_OPTIONAL}
    assert alias("contributing_habits") == set(habits)
