"""
advanced_search Ownership Scoping — per-strategy cross-user negatives
======================================================================

Proves the SearchVisibility mechanism end to end against a real Neo4j
container (the #512 follow-up):

    SearchRouter.advanced_search(request with user_uid)
        → strategies 1-3 (graph traversal / tags / text)
        → backend raw methods with the visibility WHERE clause

Coverage:
- Activity (Task, OWNER_ONLY): every strategy hides other users' content,
  positive controls prove the owner still finds their own.
- No-user calls fail closed: user-owned domains contribute nothing.
- Exercise (SCOPE_AWARE) matrix: CURRICULUM visible to strangers,
  PERSONAL owner-only, ASSIGNED reachable through group membership
  (MEMBER_OF + SHARED_WITH_GROUP) — ADR-038/040 semantics.
- Faceted single-domain exercise path honors the same matrix (the
  pre-existing OWNS-only seam hid CURRICULUM exercises entirely), and the
  faceted OWNER_ONLY path is cross-user scoped like the other strategies.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from core.models.enums import EntityStatus, ExerciseScope
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.models.relationship_names import RelationshipName
from core.models.search_request import SearchRequest
from core.models.task.task import Task
from core.orchestrator.search_router import SearchRouter
from core.services.exercises.exercise_service import ExerciseService

OWNER = "user_scope_owner"
STRANGER = "user_scope_stranger"
TEACHER = "user_scope_teacher"
GROUP_UID = "group_scope_test"


@pytest.fixture
def exercise_service(neo4j_driver) -> ExerciseService:
    backend = ExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.EXERCISE,
        entity_class=Exercise,
        base_label=NeoLabel.ENTITY,
    )
    return ExerciseService(backend=backend)


@pytest.fixture
def search_router(tasks_service, exercise_service) -> SearchRouter:
    """SearchRouter wired with only tasks + exercises."""
    return SearchRouter(tasks=tasks_service, exercises=exercise_service)


async def _seed_users_and_group(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            UNWIND $uids AS uid
            MERGE (u:User {uid: uid})
            """,
            uids=[OWNER, STRANGER, TEACHER],
        )
        await session.run(
            """
            MERGE (g:Group {uid: $group_uid})
            WITH g
            MATCH (member:User {uid: $member})
            MERGE (member)-[:MEMBER_OF]->(g)
            """,
            group_uid=GROUP_UID,
            member=STRANGER,
        )


async def _seed_tasks(neo4j_driver, tasks_service) -> dict[str, str]:
    """One distinctive tagged task per user, plus a goal connected to the
    owner's task for the graph-traversal strategy."""
    created: dict[str, str] = {}
    specs = [
        ("owner_task", OWNER, "Aurora secret plan", ["aurora"]),
        ("stranger_task", STRANGER, "Aurora other note", ["aurora"]),
    ]
    for key, user, title, tags in specs:
        task = Task(
            uid=f"task_scope_{key}",
            user_uid=user,
            title=title,
            description="advanced_search scoping fixture",
            status=EntityStatus.ACTIVE,
            tags=tags,
        )
        result = await tasks_service.create(task)
        assert result.is_ok, result.expect_error()
        created[key] = task.uid

    # Both tasks fulfill the same goal — the graph strategy must still
    # keep each owner's slice separate.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (g:Entity:Goal {uid: $goal_uid})
            ON CREATE SET g.entity_type = 'goal', g.title = 'Scope goal'
            WITH g
            MATCH (t:Task) WHERE t.uid IN $task_uids
            MERGE (t)-[:FULFILLS_GOAL]->(g)
            """,
            goal_uid="goal_scope_hub",
            task_uids=list(created.values()),
        )
    created["goal"] = "goal_scope_hub"
    return created


async def _seed_exercises(exercise_service) -> dict[str, str]:
    """The exercise visibility matrix: curriculum / personal / assigned."""
    specs = [
        # key, scope, owner, group
        ("curriculum", ExerciseScope.CURRICULUM, None, None),
        ("personal", ExerciseScope.PERSONAL, OWNER, None),
        ("assigned", ExerciseScope.ASSIGNED, TEACHER, GROUP_UID),
    ]
    created: dict[str, str] = {}
    for key, scope, owner, group in specs:
        exercise = Exercise(
            uid=f"exercise_scope_{key}",
            title=f"Nebula {key} drill",
            entity_type=EntityType.EXERCISE,
            instructions="advanced_search scoping fixture",
            scope=scope,
            owner_uid=owner,
            group_uid=group,
        )
        result = await exercise_service.create(exercise)
        assert result.is_ok, result.expect_error()
        created[key] = exercise.uid
    return created


async def _seed_assigned_share(neo4j_driver, exercise_uid: str) -> None:
    """ExerciseService.create writes SHARED_WITH_GROUP via the sharing
    service (not wired here) — seed the ADR-040 edge directly."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Exercise {uid: $uid}), (g:Group {uid: $group_uid})
            MERGE (e)-[:SHARED_WITH_GROUP]->(g)
            """,
            uid=exercise_uid,
            group_uid=GROUP_UID,
        )


def _uids(result, entity_type) -> set[str]:
    items = result.value.results_by_domain.get(entity_type, [])
    return {item.uid for item in items}


# ============================================================================
# Activity domain: per-strategy cross-user negatives
# ============================================================================


@pytest.mark.asyncio
async def test_text_strategy_is_owner_scoped(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(query_text="Aurora", entity_types=[EntityType.TASK], user_uid=STRANGER)
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.TASK)
    assert created["stranger_task"] in uids  # positive control
    assert created["owner_task"] not in uids  # the #512 follow-up leak


@pytest.mark.asyncio
async def test_tags_strategy_is_owner_scoped(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(
        query_text="Aurora",
        entity_types=[EntityType.TASK],
        tags_contain=["aurora"],
        user_uid=STRANGER,
    )
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.TASK)
    assert created["stranger_task"] in uids
    assert created["owner_task"] not in uids


@pytest.mark.asyncio
async def test_graph_traversal_strategy_is_owner_scoped(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(
        query_text="Aurora",
        entity_types=[EntityType.TASK],
        connected_to_uid=created["goal"],
        connected_relationship=RelationshipName.FULFILLS_GOAL,
        connected_direction="incoming",
        user_uid=STRANGER,
    )
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.TASK)
    assert created["stranger_task"] in uids
    assert created["owner_task"] not in uids


@pytest.mark.asyncio
async def test_no_user_fails_closed_for_user_owned_domains(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """Without a requesting user, user-owned domains contribute nothing."""
    await _seed_users_and_group(neo4j_driver)
    await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(query_text="Aurora", entity_types=[EntityType.TASK])
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    assert result.value.total_count == 0


@pytest.mark.asyncio
async def test_faceted_strategy_is_owner_scoped(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """The faceted path is owner-scoped like every other strategy.

    It is the last one to get here: OWNER_ONLY used to anchor on
    ``(User)-[:OWNS]->(entity)`` in ``faceted_search_raw`` rather than compose
    ``build_search_visibility_clause``, so it was the one strategy whose answer
    could differ from the rest on a graph where property and edge disagreed.
    """
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    # Ungated control: both rows exist and match the text, so a scoped
    # assertion below can actually fail.
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (t:Task) WHERE toLower(t.title) CONTAINS 'aurora' RETURN t.uid AS uid"
        )
        assert {record["uid"] async for record in result} == {
            created["owner_task"],
            created["stranger_task"],
        }

    request = SearchRequest(query_text="Aurora", entity_types=[EntityType.TASK])
    faceted = await search_router.faceted_search(request, user_uid=STRANGER)
    assert faceted.is_ok, faceted.expect_error()
    uids = {r.get("uid") for r in faceted.value.results}
    assert created["stranger_task"] in uids  # positive control
    assert created["owner_task"] not in uids


@pytest.mark.asyncio
async def test_faceted_no_user_fails_closed_for_user_owned_domains(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """An anonymous faceted call over an OWNER_ONLY domain yields nothing.

    Three independent floors have to hold for this:

    1. ``_graph_aware_domain_search`` admits anonymous callers for PUBLIC
       domains only;
    2. ``search()`` refuses an OWNER_ONLY domain with no user, so the
       cross-domain fallback below it contributes nothing;
    3. and if a caller ever reaches the backend directly, the emitted
       ``entity.user_uid = $user_uid`` predicate is null on a null parameter
       and matches no row (``test_faceted_null_user_fails_closed``).

    Floor 2 was missing: an anonymous single-domain faceted call fell through
    ``_graph_aware_domain_search`` → ``_simple_domain_search`` (no "tasks"
    entry) → ``_cross_domain_search`` → the scored text sweep → ``search()``
    with no uid → no ownership clause → every user's rows. See
    ``test_anonymous_library_route_request_cannot_read_user_owned_rows`` for
    the public route that reached it.
    """
    await _seed_users_and_group(neo4j_driver)
    await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(query_text="Aurora", entity_types=[EntityType.TASK])
    result = await search_router.faceted_search(request, user_uid=None)
    assert result.is_ok, result.expect_error()
    assert result.value.results == []


@pytest.mark.asyncio
async def test_anonymous_library_route_request_cannot_read_user_owned_rows(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """The reachability half: /api/explore/search builds this request from ?type=.

    ``_library_search_request`` resolves the raw ``type`` query param through
    ``EntityType.from_string`` with no catalog whitelist, so ``?type=task``
    yields ``entity_types=[TASK]`` — and that route serves anonymous callers
    (``user_uid = ... if is_authenticated(request) else None``). Building the
    request the way the route does keeps this honest about what is reachable
    rather than asserting on a hand-made SearchRequest.

    ⚠️ This particular shape was ALREADY safe and stays green with the
    ``search()`` gate removed: the library clamps sort away from RELEVANCE, so
    the request lands on ``_faceted_sweep``, which has its own anonymous gate.
    It is kept as a route-shaped floor, not as the leak repro. The reachable
    leak went through a domain that ``_simple_domain_search`` maps —
    ``?type=revised_exercise`` — and is pinned without a database in
    ``test_search_router_registry.py::
    TestOwnerOnlySearchScopeGate::test_anonymous_faceted_single_domain_never_queries_unscoped``.
    """
    from adapters.inbound.explore_ui import _library_search_request

    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    request = _library_search_request("Aurora", "task", "", "created_desc", 0)
    assert EntityType.TASK.value in [str(t) for t in request.entity_types], (
        "guard the premise: ?type=task must still resolve to the TASK domain, "
        "otherwise this test stops covering the route it names"
    )

    result = await search_router.faceted_search(request, user_uid=None)
    assert result.is_ok, result.expect_error()
    uids = {r.get("uid") for r in result.value.results}
    assert created["owner_task"] not in uids
    assert created["stranger_task"] not in uids


@pytest.mark.asyncio
async def test_faceted_relationship_filter_still_composes_without_the_owner_match(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """A relationship filter and the ownership predicate coexist in one query.

    The relationship fragments (``ready_to_learn`` and friends) each open with
    their own ``MATCH (user:User {uid: $user_uid})`` inside an ``EXISTS`` block.
    While the faceted path anchored on ``(user:User)-[:OWNS]->(entity)`` those
    were re-binding a variable the outer MATCH had already introduced; now they
    bind it fresh. Same node either way — but "the Cypher still parses and still
    scopes" is worth executing rather than reasoning about, since a stray
    unbound reference would either error or quietly widen the match.
    """
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    request = SearchRequest(
        query_text="Aurora",
        entity_types=[EntityType.TASK],
        ready_to_learn=True,
    )
    result = await search_router.faceted_search(request, user_uid=STRANGER)
    assert result.is_ok, result.expect_error()

    uids = {r.get("uid") for r in result.value.results}
    # Neither task has REQUIRES_KNOWLEDGE edges, so ready_to_learn admits both —
    # which is what makes this a scoping assertion and not a filter assertion.
    assert created["stranger_task"] in uids
    assert created["owner_task"] not in uids


@pytest.mark.asyncio
async def test_owner_only_text_search_refuses_without_a_user(
    clean_neo4j, neo4j_driver, tasks_service, search_router
) -> None:
    """``search()`` is the chokepoint: it refuses rather than returning rows.

    Asserted at the chokepoint itself because every aggregate caller treats a
    failed domain result as "contributes nothing" — a test that only checked
    the aggregate would pass against a gate that returned an empty list for
    the wrong reason.
    """
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_tasks(neo4j_driver, tasks_service)

    unscoped = await search_router.search(EntityType.TASK, "Aurora", 50)
    assert unscoped.is_error, "an unscoped OWNER_ONLY text search must be refused"

    # Positive control: the same query WITH a user returns that user's row.
    scoped = await search_router.search(EntityType.TASK, "Aurora", 50, user_uid=OWNER)
    assert scoped.is_ok, scoped.expect_error()
    assert {entity.uid for entity in scoped.value} == {created["owner_task"]}


# ============================================================================
# Exercise matrix (SCOPE_AWARE — the design ruling)
# ============================================================================


@pytest.mark.asyncio
async def test_exercise_matrix_for_group_member_stranger(
    clean_neo4j, neo4j_driver, exercise_service, search_router
) -> None:
    """A non-owner group member sees CURRICULUM + their group's ASSIGNED
    exercise, never someone else's PERSONAL exercise."""
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_exercises(exercise_service)
    await _seed_assigned_share(neo4j_driver, created["assigned"])

    request = SearchRequest(
        query_text="Nebula", entity_types=[EntityType.EXERCISE], user_uid=STRANGER
    )
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.EXERCISE)
    assert created["curriculum"] in uids
    assert created["assigned"] in uids
    assert created["personal"] not in uids


@pytest.mark.asyncio
async def test_exercise_matrix_for_owner(
    clean_neo4j, neo4j_driver, exercise_service, search_router
) -> None:
    """The personal-exercise owner (not a group member) sees CURRICULUM +
    their own PERSONAL exercise, not the group's ASSIGNED one."""
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_exercises(exercise_service)
    await _seed_assigned_share(neo4j_driver, created["assigned"])

    request = SearchRequest(query_text="Nebula", entity_types=[EntityType.EXERCISE], user_uid=OWNER)
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.EXERCISE)
    assert created["curriculum"] in uids
    assert created["personal"] in uids
    assert created["assigned"] not in uids


@pytest.mark.asyncio
async def test_exercise_unscoped_call_returns_curriculum_only(
    clean_neo4j, neo4j_driver, exercise_service, search_router
) -> None:
    """Shared content is the fail-closed floor for SCOPE_AWARE domains."""
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_exercises(exercise_service)

    request = SearchRequest(query_text="Nebula", entity_types=[EntityType.EXERCISE])
    result = await search_router.advanced_search(request)
    assert result.is_ok, result.expect_error()
    uids = _uids(result, EntityType.EXERCISE)
    assert uids == {created["curriculum"]}


@pytest.mark.asyncio
async def test_faceted_exercise_path_honors_scope_matrix(
    clean_neo4j, neo4j_driver, exercise_service, search_router
) -> None:
    """The /search single-domain faceted path: CURRICULUM must not vanish
    (the pre-existing OWNS-only MATCH hid it from everyone), and group
    membership grants the ASSIGNED exercise."""
    await _seed_users_and_group(neo4j_driver)
    created = await _seed_exercises(exercise_service)
    await _seed_assigned_share(neo4j_driver, created["assigned"])

    request = SearchRequest(query_text="Nebula", entity_types=[EntityType.EXERCISE])
    result = await search_router.faceted_search(request, user_uid=STRANGER)
    assert result.is_ok, result.expect_error()
    uids = {r.get("uid") for r in result.value.results}
    assert created["curriculum"] in uids
    assert created["assigned"] in uids
    assert created["personal"] not in uids
