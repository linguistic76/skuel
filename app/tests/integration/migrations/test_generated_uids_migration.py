"""The generated-uid migration, census and write, against a real Neo4j.

``scripts/migrations/generated_uids_2026_10.py`` renames every node uid outside
the grammar to ``hashed_uid(prefix, old uid)`` — the default group to
``default_group_uid`` of its teacher, flagged ``is_default`` — re-mints the
chunks of a renamed entity, and rewrites every value naming a renamed uid.

The seed is the graph the old writers left: 8-hex, 12-hex, 32-hex, titled,
composite and bare-UUID uids, a minted note with a chunked body and a tracker
row, references by string (a session, a habit, an insight list, a JSON map), a
reply quoting a uid in prose — plus what the run must leave alone: a uid in the
one shape, an authored Ku with its chunk, and the users.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

from core.models.group.group import default_group_uid
from core.models.ps_content.content_chunks import ChunkStore, chunk_uid
from core.utils.uid_grammar import hashed_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/migrations/generated_uids_2026_10.py"


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("generated_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

OWNER = "user_zzzgumig"
TEACHER = "user_zzzguteach"
TASK = "task_a1b2c3d4"
TASK_NEW = hashed_uid("task", TASK)
CHOICE = "choice_decide-what-to-ask_87e6315d"
NOTE = "ue_aa11bb22"
NOTE_NEW = hashed_uid("ue", NOTE)
LISTING = "ue_cc33dd44"
SESSION = "session_" + "0123456789abcdef" * 2
SESSION_NEW = hashed_uid("session", SESSION)
AUTH = "auth_" + "fedcba9876543210" * 2
HABIT = "habit_e1f401b7"
HABIT_NEW = hashed_uid("habit", HABIT)
COMPLETION = f"hc.{OWNER}.{HABIT}.1789135868"
INSIGHT = f"insight.completion_pattern.{TASK}.20260918075359"
INSIGHT_NEW = hashed_uid("insight", INSIGHT)
REPORT = "ar_11112222"
SEARCH = "5f348e63-fe54-45b9-a6b5-d4205be31270"
MESSAGE = "msg_0123456789ab"
OLD_GROUP = f"group_default_{TEACHER}"
NEW_GROUP = default_group_uid(TEACHER)
FITTING = "task_3f9a0c41d2e87b65"
KU = "ku.zzzgumig.stays"
VAULT_FILE = "/vault/knowledge/minted.md"
VECTOR = [0.5, 0.25, 0.125]
PROSE = f"Your task {TASK} is due on Monday."
LISTING_MD = json.dumps({"activity_extraction": {"tasks": [TASK], "count": 1}})


async def _run(
    driver: AsyncDriver, query: str, **params: Any
) -> list[Any]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


_SEED = """
MERGE (o:User {uid: $owner})
MERGE (t:User {uid: $teacher})
CREATE (o)-[:OWNS]->(task:Entity:Task {uid: $task, user_uid: $owner, embedding: $vector})
CREATE (o)-[:OWNS]->(:Entity:Task {uid: $fitting, user_uid: $owner})
CREATE (o)-[:OWNS]->(:Entity:Choice {uid: $choice, user_uid: $owner})
CREATE (o)-[:OWNS]->(note:Entity:UserEntry {uid: $note, user_uid: $owner, metadata: '{}'})
CREATE (note)-[:HAS_CONTENT]->(nc:Content)
CREATE (nc)-[:HAS_CHUNK {sequence: 0}]->(:ContentChunk {uid: $note_chunk0, start_index: 0,
                                                          embedding: $vector})
CREATE (nc)-[:HAS_CHUNK {sequence: 1}]->(:ContentChunk {uid: $note_chunk1, start_index: 1})
CREATE (:IngestionMetadata {file_path: $vault_file, entity_uid: $note})
CREATE (o)-[:OWNS]->(:Entity:UserEntry {uid: $listing, user_uid: $owner, metadata: $listing_md})
CREATE (o)-[:HAS_SESSION]->(:Session {uid: $session, user_uid: $owner})
CREATE (:AuthEvent {uid: $auth, user_uid: $owner, session_uid: $session})
CREATE (o)-[:OWNS]->(habit:Entity:Habit {uid: $habit, user_uid: $owner})
CREATE (:HabitCompletion {uid: $completion, user_uid: $owner, habit_uid: $habit})
CREATE (o)-[:HAS_INSIGHT]->(insight:Insight {uid: $insight, user_uid: $owner, entity_uid: $task})
CREATE (insight)-[:ABOUT_ENTITY]->(task)
CREATE (o)-[:OWNS]->(:Entity:ActivityReport {uid: $report, user_uid: $owner,
                                             insights_referenced: [$insight]})
CREATE (:SearchEvent {uid: $search, user_uid: $owner})
CREATE (o)-[:HAS_MESSAGE]->(:ConversationMessage {uid: $message, content: $prose})
CREATE (t)-[:OWNS]->(g:Group {uid: $old_group, name: 'Default Group', is_active: true})
CREATE (o)-[:MEMBER_OF]->(g)
CREATE (ku:Entity:Ku {uid: $ku})-[:HAS_CONTENT]->(kc:Content)
CREATE (kc)-[:HAS_CHUNK {sequence: 0}]->(:ContentChunk {uid: $ku_chunk, start_index: 0})
"""

_SEED_PARAMS: dict[str, Any] = {  # boundary: cypher parameters
    "owner": OWNER,
    "teacher": TEACHER,
    "task": TASK,
    "fitting": FITTING,
    "choice": CHOICE,
    "note": NOTE,
    "note_chunk0": chunk_uid(ChunkStore.CONTENT, NOTE, 0),
    "note_chunk1": chunk_uid(ChunkStore.CONTENT, NOTE, 1),
    "vault_file": VAULT_FILE,
    "listing": LISTING,
    "listing_md": LISTING_MD,
    "session": SESSION,
    "auth": AUTH,
    "habit": HABIT,
    "completion": COMPLETION,
    "insight": INSIGHT,
    "report": REPORT,
    "search": SEARCH,
    "message": MESSAGE,
    "prose": PROSE,
    "old_group": OLD_GROUP,
    "ku": KU,
    "ku_chunk": chunk_uid(ChunkStore.CONTENT, KU, 0),
    "vector": VECTOR,
}


@pytest.fixture
async def old_graph(neo4j_driver: AsyncDriver, clean_neo4j: None) -> AsyncIterator[None]:
    """The old shapes on an otherwise empty graph — the census reads every uid."""
    await _run(neo4j_driver, _SEED, **_SEED_PARAMS)
    yield
    await _run(
        neo4j_driver,
        "MATCH (u:User) WHERE u.uid IN [$owner, $teacher] DETACH DELETE u",
        owner=OWNER,
        teacher=TEACHER,
    )


async def _value(driver: AsyncDriver, query: str, **params: Any) -> Any:  # boundary: cypher-params
    rows = await _run(driver, query, **params)
    return rows[0][0] if rows else None


async def _uids(driver: AsyncDriver) -> set[str]:
    rows = await _run(driver, "MATCH (n) WHERE n.uid IS NOT NULL RETURN n.uid AS uid")
    return {str(row["uid"]) for row in rows}


@pytest.mark.usefixtures("old_graph")
class TestTheRename:
    async def test_census_plans_every_old_shape_and_leaves_the_rest(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        assert plan.stops == [], plan.stops
        assert {r.old: r.new for r in plan.renames} == {
            TASK: TASK_NEW,
            CHOICE: hashed_uid("choice", CHOICE),
            NOTE: NOTE_NEW,
            LISTING: hashed_uid("ue", LISTING),
            SESSION: SESSION_NEW,
            AUTH: hashed_uid("auth", AUTH),
            HABIT: HABIT_NEW,
            COMPLETION: hashed_uid("hc", COMPLETION),
            INSIGHT: INSIGHT_NEW,
            REPORT: hashed_uid("ar", REPORT),
            SEARCH: hashed_uid("search", SEARCH),
            MESSAGE: hashed_uid("msg", MESSAGE),
            OLD_GROUP: NEW_GROUP,
        }
        assert [r.default_group for r in plan.renames if r.old == OLD_GROUP] == [True]
        assert {(c.old, c.new) for c in plan.chunks} == {
            (chunk_uid(ChunkStore.CONTENT, NOTE, i), chunk_uid(ChunkStore.CONTENT, NOTE_NEW, i))
            for i in (0, 1)
        }
        assert sorted((w.holder, w.key) for w in plan.rewrites) == [
            ("ActivityReport", "insights_referenced"),
            ("AuthEvent", "session_uid"),
            ("HabitCompletion", "habit_uid"),
            ("IngestionMetadata", "entity_uid"),
            ("Insight", "entity_uid"),
            ("UserEntry", "metadata"),
        ]
        assert dict(plan.quoted) == {"ConversationMessage.content": 1}
        assert plan.embedded == 1

    async def test_confirm_renames_in_place_and_rewrites_every_value(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        written = await migration.migrate(neo4j_driver, plan)

        assert written == {
            "renamed": 13,
            "chunks re-minted": 2,
            "node values rewritten": 6,
            "edge values rewritten": 0,
        }
        assert await migration._read_back(neo4j_driver, plan) == []
        uids = await _uids(neo4j_driver)
        assert not uids & {r.old for r in plan.renames}
        assert {FITTING, KU, chunk_uid(ChunkStore.CONTENT, KU, 0), OWNER, TEACHER} <= uids
        # Each node kept its edges and its vector.
        assert (
            await _value(
                neo4j_driver,
                "MATCH (:User {uid: $o})-[:OWNS]->(t:Task {uid: $t})<-[:ABOUT_ENTITY]-(:Insight {uid: $i}) "
                "RETURN t.embedding",
                o=OWNER,
                t=TASK_NEW,
                i=INSIGHT_NEW,
            )
            == VECTOR
        )
        chunks = await _run(
            neo4j_driver,
            "MATCH (:UserEntry {uid: $n})-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(c) "
            "RETURN c.uid AS uid, c.start_index AS i, c.embedding IS NOT NULL AS embedded "
            "ORDER BY i",
            n=NOTE_NEW,
        )
        assert [(row["uid"], row["embedded"]) for row in chunks] == [
            (chunk_uid(ChunkStore.CONTENT, NOTE_NEW, 0), True),
            (chunk_uid(ChunkStore.CONTENT, NOTE_NEW, 1), False),
        ]
        # The default group: at the uid the enrollment MERGE derives, flagged, roster kept.
        group = await _run(
            neo4j_driver,
            "MATCH (:User {uid: $t})-[:OWNS]->(g:Group)<-[:MEMBER_OF]-(:User {uid: $o}) "
            "RETURN g.uid AS uid, g.is_default AS is_default",
            t=TEACHER,
            o=OWNER,
        )
        assert [(row["uid"], row["is_default"]) for row in group] == [(NEW_GROUP, True)]
        # Every value naming a renamed uid names its new one.
        assert await _value(neo4j_driver, "MATCH (a:AuthEvent) RETURN a.session_uid") == SESSION_NEW
        assert (
            await _value(
                neo4j_driver,
                "MATCH (m:IngestionMetadata {file_path: $f}) RETURN m.entity_uid",
                f=VAULT_FILE,
            )
            == NOTE_NEW
        )
        assert (
            await _value(neo4j_driver, "MATCH (h:HabitCompletion) RETURN h.habit_uid") == HABIT_NEW
        )
        assert await _value(neo4j_driver, "MATCH (i:Insight) RETURN i.entity_uid") == TASK_NEW
        assert await _value(
            neo4j_driver, "MATCH (r:ActivityReport) RETURN r.insights_referenced"
        ) == [INSIGHT_NEW]
        listing_md = await _value(
            neo4j_driver,
            "MATCH (n:UserEntry {uid: $u}) RETURN n.metadata",
            u=hashed_uid("ue", LISTING),
        )
        assert json.loads(listing_md) == {"activity_extraction": {"tasks": [TASK_NEW], "count": 1}}
        # Prose quoting a uid is left as written.
        assert await _value(neo4j_driver, "MATCH (m:ConversationMessage) RETURN m.content") == PROSE

    async def test_a_re_run_writes_nothing_and_reads_back_clean(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        before = await migration.census(neo4j_driver)
        await migration.migrate(neo4j_driver, before)

        again = await migration.census(neo4j_driver)

        assert again.stops == [] and again.writes == 0
        assert again.left_exempt["user_from_username"] >= 2
        assert await migration._read_back(neo4j_driver, again) == []

    async def test_a_graph_changed_after_the_census_rolls_the_whole_run_back(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)
        await _run(neo4j_driver, "MATCH (a:AuthEvent) SET a.session_uid = 'session_other'")

        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(neo4j_driver, plan)

        uids = await _uids(neo4j_driver)
        assert {TASK, OLD_GROUP, chunk_uid(ChunkStore.CONTENT, NOTE, 0)} <= uids
        assert TASK_NEW not in uids

    async def test_the_enrollment_merge_before_the_run_stops_it(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Booting the app between merge and migration makes a second default group."""
        await _run(
            neo4j_driver,
            "MATCH (t:User {uid: $t}) "
            "CREATE (t)-[:OWNS]->(:Group {uid: $g, name: 'Default Group', is_default: true})",
            t=TEACHER,
            g=NEW_GROUP,
        )

        plan = await migration.census(neo4j_driver)

        assert f"{NEW_GROUP} (for {OLD_GROUP}) is already held by a node" in plan.stops


# case → (the Cypher that seeds it, its extra parameters, the stop it raises)
_STOPS: dict[str, tuple[str, dict[str, Any], str]] = {  # boundary: cypher parameters
    "a uid inside other text": (
        "MATCH (t:Task {uid: $task}) SET t.description = 'see ' + $task",
        {},
        "node Task.description names a renamed uid inside other text",
    ),
    "JSON that does not read back to its own text": (
        "MATCH (n:UserEntry {uid: $listing}) SET n.metadata = '{\"tasks\":[\"' + $task + '\"]}'",
        {},
        "node UserEntry.metadata names a renamed uid inside other text",
    ),
    "a default group of two teachers": (
        "MATCH (g:Group {uid: $old_group}), (o:User {uid: $owner}) CREATE (o)-[:OWNS]->(g)",
        {},
        "owned by",
    ),
    "is_default off a default group": (
        "MATCH (t:User {uid: $teacher}) CREATE (t)-[:OWNS]->(:Group {uid: 'group_0123456789abcdef', is_default: true})",
        {},
        "is_default on a group that is no teacher's default",
    ),
    "a chunk off its derived uid": (
        "MATCH (:Content)-[:HAS_CHUNK]->(c:ContentChunk {uid: $chunk}) SET c.start_index = 7",
        {"chunk": chunk_uid(ChunkStore.CONTENT, NOTE, 1)},
        "not chunk_uid of",
    ),
    "an edge file naming a renamed source": (
        "CREATE (:IngestionMetadata {file_path: '/vault/edges/applies.yaml', "
        "entity_uid: 'edge:' + $task + '|APPLIES_KNOWLEDGE|ku.zzzgumig.stays'})",
        {},
        "tracker row /vault/edges/applies.yaml: its file names a renamed uid",
    ),
    "an edge file naming a renamed target": (
        "CREATE (:IngestionMetadata {file_path: '/vault/edges/serves.yaml', "
        "entity_uid: 'edge:ku.zzzgumig.stays|RELATED_TO|' + $task})",
        {},
        "tracker row /vault/edges/serves.yaml: its file names a renamed uid",
    ),
    "a file authoring an edge to a renamed uid": (
        "MATCH (m:IngestionMetadata {file_path: $vault_file}) "
        "SET m.authored_edges = ['RELATED_TO|outgoing|' + $task]",
        {},
        f"tracker row {VAULT_FILE}: its file names a renamed uid",
    ),
    "a uid two nodes hold": (
        "CREATE (:Notification {uid: $task})",
        {},
        f"{TASK} is already held by 2 nodes",
    ),
    "a new uid already held": (
        "CREATE (:Entity:Task {uid: $taken})",
        {"taken": TASK_NEW},
        f"{TASK_NEW} (for {TASK}) is already held by a node",
    ),
    "a renamed node holding reference chunks": (
        "MATCH (t:Task {uid: $task}) CREATE (t)-[:HAS_REFERENCE_CHUNK]->(:ReferenceChunk {uid: 'chunk_00000000000000aa'})",
        {},
        f"{TASK}: holds reference chunks",
    ),
}


@pytest.mark.usefixtures("old_graph")
@pytest.mark.parametrize("case", sorted(_STOPS))
async def test_the_census_stops_on_what_the_rename_cannot_account_for(
    neo4j_driver: AsyncDriver, case: str
) -> None:
    query, extra, reason = _STOPS[case]
    await _run(neo4j_driver, query, **(_SEED_PARAMS | extra))
    try:
        plan = await migration.census(neo4j_driver)

        assert any(reason in stop for stop in plan.stops), plan.stops
        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(neo4j_driver, plan)
        assert TASK in await _uids(neo4j_driver)
    finally:
        await _run(neo4j_driver, "MATCH (u:User {uid: 'zzzgumig-admin'}) DETACH DELETE u")


@pytest.mark.usefixtures("old_graph")
async def test_a_user_uid_in_no_shape_is_reported_and_left(neo4j_driver: AsyncDriver) -> None:
    """User uids are unruled: the run renames none and reports one that fits no shape."""
    await _run(neo4j_driver, "CREATE (:User {uid: 'zzzgumig-admin'})")
    try:
        plan = await migration.census(neo4j_driver)

        assert plan.stops == [], plan.stops
        assert "zzzgumig-admin" in plan.users_outside
        assert "zzzgumig-admin" not in {r.old for r in plan.renames}
    finally:
        await _run(neo4j_driver, "MATCH (u:User {uid: 'zzzgumig-admin'}) DETACH DELETE u")
