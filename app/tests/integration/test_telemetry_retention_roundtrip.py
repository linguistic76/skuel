"""Telemetry-retention prune — real Neo4j (ADR-080 Horizon 0).

Proves the age-based prune against a real container — what the unit suite
(``tests/unit/test_telemetry_retention.py``, query-shape only) cannot: that the
predicates actually match/delete the right rows on a live 2026.x server.

Load-bearing checks:
- **Temporal-storage-bug-class:** ``:Interaction.created_at`` is seeded as a bare
  ISO STRING (exactly how the universal-backend ``to_neo4j_node`` writer stores
  it), and the ``datetime(e.created_at)`` predicate still selects the old one —
  the single most likely correctness failure here.
- Native-datetime types (:AuthEvent, :SearchEvent, :VIEWED) prune by direct
  comparison.
- **Saved-discussion exclusion:** a full retention pass leaves a stale
  :ConversationSession + its :ConversationTurn completely intact — they are
  user content (ADR-078), never telemetry.
- **VIEWED** prunes the stale edge but never its Ku endpoint.
- dry-run counts exactly what a real run then deletes (no global-isolation needed:
  measured back-to-back).

All nodes carry ``test_tag:'retention_it'`` so seeding + teardown are self-scoped;
assertions target seeded UIDs, so other suites' telemetry cannot perturb them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.session_backend import SessionBackend
from adapters.persistence.neo4j.telemetry_retention_backend import TelemetryRetentionBackend

_TAG = "retention_it"


async def _exists(driver, uid_field: str, uid: str) -> bool:
    async with driver.session() as session:
        result = await session.run(
            f"MATCH (n {{{uid_field}: $uid, test_tag: $tag}}) RETURN count(n) AS c",
            uid=uid,
            tag=_TAG,
        )
        record = await result.single()
    return record["c"] > 0


@pytest_asyncio.fixture(loop_scope="session")
async def seeded(neo4j_driver):
    """Seed old + recent telemetry of every prunable type; wipe around the test.

    Old = 200 days ago (prunable at a 90-day window); recent = 2 days ago (kept).
    Session validity is expiry-based, so its "valid" row expires in the FUTURE.
    ``:Interaction.created_at`` is a bare STRING — the universal-backend storage
    format — while every other temporal is a native ``datetime(...)``.
    """
    now = datetime.now(UTC)
    old = (now - timedelta(days=200)).isoformat()
    recent = (now - timedelta(days=2)).isoformat()
    future = (now + timedelta(days=30)).isoformat()

    async def _wipe() -> None:
        async with neo4j_driver.session() as session:
            await session.run("MATCH (n {test_tag: $tag}) DETACH DELETE n", tag=_TAG)

    await _wipe()
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:AuthEvent {uid:'ret_auth_old', timestamp: datetime($old), test_tag:$tag})
            CREATE (:AuthEvent {uid:'ret_auth_new', timestamp: datetime($recent), test_tag:$tag})
            CREATE (:SearchEvent {uid:'ret_se_old', created_at: datetime($old), test_tag:$tag})
            CREATE (:SearchEvent {uid:'ret_se_new', created_at: datetime($recent), test_tag:$tag})
            // Interaction.created_at is a STRING (universal-backend writer) — NOT datetime()
            CREATE (:Entity:Interaction {uid:'ret_int_old', created_at: $old, test_tag:$tag})
            CREATE (:Entity:Interaction {uid:'ret_int_new', created_at: $recent, test_tag:$tag})
            CREATE (u:User {uid:'ret_user', test_tag:$tag})
            CREATE (ko:Ku {uid:'ret_ku_old', test_tag:$tag})
            CREATE (kn:Ku {uid:'ret_ku_new', test_tag:$tag})
            CREATE (u)-[:VIEWED {last_viewed_at: datetime($old)}]->(ko)
            CREATE (u)-[:VIEWED {last_viewed_at: datetime($recent)}]->(kn)
            CREATE (so:ConversationSession {session_id:'ret_cs_old', last_activity: datetime($old), test_tag:$tag})
            CREATE (sn:ConversationSession {session_id:'ret_cs_new', last_activity: datetime($recent), test_tag:$tag})
            CREATE (so)-[:HAS_TURN]->(:ConversationTurn {turn_id:'ret_ct_old', test_tag:$tag})
            CREATE (sn)-[:HAS_TURN]->(:ConversationTurn {turn_id:'ret_ct_new', test_tag:$tag})
            CREATE (:Session {uid:'ret_sess_expired', expires_at: datetime($old), test_tag:$tag})
            CREATE (:Session {uid:'ret_sess_valid', expires_at: datetime($future), test_tag:$tag})
            """,
            old=old,
            recent=recent,
            future=future,
            tag=_TAG,
        )

    backend = TelemetryRetentionBackend(Neo4jQueryExecutor(neo4j_driver))
    yield backend
    await _wipe()


@pytest.mark.asyncio(loop_scope="session")
async def test_interaction_string_timestamp_is_pruned(neo4j_driver, seeded):
    """The STRING-stored Interaction.created_at is still selected by datetime()-parse.

    This is the temporal-storage-bug-class guard: if the predicate compared a
    string to a datetime it would match zero rows and silently prune nothing.
    """
    assert await _exists(neo4j_driver, "uid", "ret_int_old")

    dry = await seeded.prune_interactions(days=90, batch_size=500, dry_run=True)
    assert dry.is_ok and dry.value >= 1

    real = await seeded.prune_interactions(days=90, batch_size=500, dry_run=False)
    assert real.is_ok
    assert real.value == dry.value  # dry-run count == real deletions

    assert not await _exists(neo4j_driver, "uid", "ret_int_old")
    assert await _exists(neo4j_driver, "uid", "ret_int_new")  # recent kept


@pytest.mark.asyncio(loop_scope="session")
async def test_native_datetime_types_prune_old_keep_recent(neo4j_driver, seeded):
    """AuthEvent + SearchEvent (native timestamps) prune old rows, keep recent."""
    await seeded.prune_auth_events(days=90, batch_size=500, dry_run=False)
    await seeded.prune_search_events(days=90, batch_size=500, dry_run=False)

    assert not await _exists(neo4j_driver, "uid", "ret_auth_old")
    assert await _exists(neo4j_driver, "uid", "ret_auth_new")
    assert not await _exists(neo4j_driver, "uid", "ret_se_old")
    assert await _exists(neo4j_driver, "uid", "ret_se_new")


@pytest.mark.asyncio(loop_scope="session")
async def test_viewed_edge_pruned_but_ku_survives(neo4j_driver, seeded):
    """A stale VIEWED edge is deleted; its Ku endpoint is untouched."""
    result = await seeded.prune_viewed_edges(days=90, batch_size=500, dry_run=False)
    assert result.is_ok and result.value >= 1

    # The stale edge is gone...
    async with neo4j_driver.session() as session:
        edge = await session.run(
            "MATCH (:User {uid:'ret_user'})-[r:VIEWED]->(:Ku {uid:'ret_ku_old'}) RETURN count(r) AS c"
        )
        assert (await edge.single())["c"] == 0
    # ...but both Ku nodes and the recent edge survive.
    assert await _exists(neo4j_driver, "uid", "ret_ku_old")
    async with neo4j_driver.session() as session:
        kept = await session.run(
            "MATCH (:User {uid:'ret_user'})-[r:VIEWED]->(:Ku {uid:'ret_ku_new'}) RETURN count(r) AS c"
        )
        assert (await kept.single())["c"] == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_saved_conversations_survive_full_retention(neo4j_driver, seeded):
    """Saved discussions are user content (ADR-078) — no prune ever touches them.

    A full real retention pass (all four SYSTEM-telemetry prunes) at a window that
    catches the 200-day-old rows must leave the old ConversationSession AND its
    turn completely intact. This is the load-bearing exclusion guard.
    """
    for prune in (
        seeded.prune_auth_events,
        seeded.prune_search_events,
        seeded.prune_interactions,
        seeded.prune_viewed_edges,
    ):
        assert (await prune(days=90, batch_size=500, dry_run=False)).is_ok

    assert await _exists(neo4j_driver, "session_id", "ret_cs_old")  # stale, but saved → kept
    assert await _exists(neo4j_driver, "turn_id", "ret_ct_old")
    assert await _exists(neo4j_driver, "session_id", "ret_cs_new")
    assert await _exists(neo4j_driver, "turn_id", "ret_ct_new")


@pytest.mark.asyncio(loop_scope="session")
async def test_dry_run_deletes_nothing(neo4j_driver, seeded):
    """A dry run reports counts but leaves every seeded row in place."""
    for prune in (
        seeded.prune_auth_events,
        seeded.prune_search_events,
        seeded.prune_interactions,
        seeded.prune_viewed_edges,
    ):
        result = await prune(days=90, batch_size=500, dry_run=True)
        assert result.is_ok and result.value >= 1

    # Nothing was deleted.
    assert await _exists(neo4j_driver, "uid", "ret_auth_old")
    assert await _exists(neo4j_driver, "uid", "ret_int_old")


@pytest.mark.asyncio(loop_scope="session")
async def test_expired_session_count_sees_seeded_expired(neo4j_driver, seeded):
    """SessionBackend.count_expired_sessions (dry-run reporting) counts the expired one.

    Read-only — deliberately NOT calling cleanup_expired_sessions() here, whose
    windowless global delete would reach across suites. The seeded expired session
    (expires 200d ago) is guaranteed present; the valid one (+30d) is not counted.
    """
    session_backend = SessionBackend(neo4j_driver)
    assert await _exists(neo4j_driver, "uid", "ret_sess_expired")

    count = await session_backend.count_expired_sessions()
    assert count.is_ok
    assert count.value >= 1  # at least our seeded expired session

    # The valid (future-expiry) session must still be present — never counted.
    assert await _exists(neo4j_driver, "uid", "ret_sess_valid")
